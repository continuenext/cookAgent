"""
对话管理服务层

管理对话会话的创建、列表、历史查询与删除。
会话元数据持久化到 Redis（Hash），对话状态通过 LangGraph AsyncRedisSaver checkpointer 管理。
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import redis.asyncio as aioredis
from langchain_core.messages import AIMessage, HumanMessage, messages_from_dict

from gustobot.application.agents import lg_builder
from gustobot.config.settings import settings
from gustobot.infrastructure.core.logger import get_logger

logger = get_logger(service="session_service")

# Redis Key 前缀
_META_PREFIX = "gustobot:session:meta:"
_META_INDEX_KEY = "gustobot:session:index"
_USER_INDEX_PREFIX = "gustobot:session:user:"

# 惰性初始化异步 Redis 连接
_redis_client: Optional[aioredis.Redis] = None


def _get_redis() -> aioredis.Redis:
    """获取异步 Redis 客户端单例。"""
    global _redis_client
    if _redis_client is None:
        _redis_client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis_client


async def create_session(title: Optional[str] = None, user_id: Optional[str] = None) -> Dict[str, Any]:
    """创建新会话，元数据持久化到 Redis。"""
    session_id = uuid.uuid4().hex
    now = datetime.now(timezone.utc).isoformat()
    meta = {
        "session_id": session_id,
        "title": title or "新对话",
        "created_at": now,
        "updated_at": now,
        "message_count": 0,
        "user_id": user_id,
        "status": "active",
    }
    r = _get_redis()
    await r.set(_META_PREFIX + session_id, json.dumps(meta, ensure_ascii=False))
    await r.sadd(_META_INDEX_KEY, session_id)  # type: ignore[misc]
    if user_id:
        await r.sadd(_USER_INDEX_PREFIX + user_id, session_id)  # type: ignore[misc]
    logger.info("创建会话: %s (user=%s)", session_id, user_id)
    return meta


async def list_sessions() -> List[Dict[str, Any]]:
    """返回所有会话元数据列表，按更新时间倒序。"""
    r = _get_redis()
    session_ids: set[str] = await r.smembers(_META_INDEX_KEY)  # type: ignore[assignment]
    if not session_ids:
        return []

    pipe = r.pipeline()
    for sid in session_ids:
        pipe.get(_META_PREFIX + sid)
    values = await pipe.execute()

    sessions: List[Dict[str, Any]] = []
    for raw in values:
        if raw:
            sessions.append(json.loads(raw))

    return sorted(sessions, key=lambda s: s.get("updated_at", ""), reverse=True)


async def get_session(session_id: str) -> Optional[Dict[str, Any]]:
    """获取单个会话元数据。"""
    r = _get_redis()
    raw = await r.get(_META_PREFIX + session_id)
    if not raw:
        return None
    return json.loads(raw)


async def update_session(session_id: str, *, title: Optional[str] = None, status: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """更新会话的标题和/或状态。返回更新后的元数据，不存在时返回 None。"""
    r = _get_redis()
    raw = await r.get(_META_PREFIX + session_id)
    if not raw:
        return None
    meta: Dict[str, Any] = json.loads(raw)
    if title is not None:
        meta["title"] = title
    if status is not None:
        meta["status"] = status
    meta["updated_at"] = datetime.now(timezone.utc).isoformat()
    await r.set(_META_PREFIX + session_id, json.dumps(meta, ensure_ascii=False))
    logger.info("更新会话: %s (title=%s, status=%s)", session_id, title, status)
    return meta


async def list_user_sessions(user_id: str) -> List[Dict[str, Any]]:
    """返回指定用户的所有会话，按更新时间倒序。"""
    r = _get_redis()
    session_ids: set[str] = await r.smembers(_USER_INDEX_PREFIX + user_id)  # type: ignore[assignment]
    if not session_ids:
        return []

    pipe = r.pipeline()
    for sid in session_ids:
        pipe.get(_META_PREFIX + sid)
    values = await pipe.execute()

    sessions: List[Dict[str, Any]] = []
    for raw in values:
        if raw:
            sessions.append(json.loads(raw))
    return sorted(sessions, key=lambda s: s.get("updated_at", ""), reverse=True)


async def count_user_sessions(user_id: str) -> int:
    """返回指定用户的会话总数。"""
    r = _get_redis()
    count = await r.scard(_USER_INDEX_PREFIX + user_id)  # type: ignore[misc]
    return count if isinstance(count, int) else 0


async def get_session_history(session_id: str) -> List[Dict[str, str]]:
    """
    获取指定会话的消息历史。

    通过 LangGraph checkpointer 的 aget_state 从 Redis 读取历史。
    """
    config = {"configurable": {"thread_id": session_id}}
    try:
        if lg_builder.graph is None:
            logger.warning("LangGraph 主图未初始化，无法获取会话历史")
            return []
        state_snapshot = await lg_builder.graph.aget_state(config)
    except Exception:
        logger.warning("获取会话历史失败: %s", session_id)
        return []

    if not state_snapshot or not state_snapshot.values:
        return []

    messages = state_snapshot.values.get("messages", [])
    history: List[Dict[str, str]] = []

    def _append_history(role: str, content: Any) -> None:
        text = str(content) if content is not None else ""
        if text:
            history.append({"role": role, "content": text})

    for msg in messages:
        if isinstance(msg, HumanMessage):
            _append_history("user", msg.content)
        elif isinstance(msg, AIMessage):
            _append_history("assistant", msg.content)
        elif isinstance(msg, dict):
            # 优先尝试官方反序列化（兼容 LangChain 序列化消息）
            try:
                restored = messages_from_dict([msg])
            except Exception:
                restored = []

            if restored:
                restored_msg = restored[0]
                if isinstance(restored_msg, HumanMessage):
                    _append_history("user", restored_msg.content)
                    continue
                if isinstance(restored_msg, AIMessage):
                    _append_history("assistant", restored_msg.content)
                    continue

            # 兼容不同版本 checkpointer 的消息字典结构
            msg_type = str(msg.get("type", "")).lower()
            data = msg.get("data") if isinstance(msg.get("data"), dict) else {}
            content = msg.get("content", data.get("content"))

            if msg_type in {"human", "user"}:
                _append_history("user", content)
            elif msg_type in {"ai", "assistant"}:
                _append_history("assistant", content)

    if not history and messages:
        logger.warning("会话 %s 检测到 %d 条原始消息，但未能解析为 user/assistant 结构", session_id, len(messages))
    return history


async def delete_session(session_id: str) -> bool:
    """删除会话元数据（从 Redis 中移除）。"""
    r = _get_redis()
    # 先读取 meta 以获取 user_id，清理用户索引
    raw = await r.get(_META_PREFIX + session_id)
    if raw:
        meta = json.loads(raw)
        user_id = meta.get("user_id")
        if user_id:
            await r.srem(_USER_INDEX_PREFIX + user_id, session_id)  # type: ignore[misc]
    removed = await r.delete(_META_PREFIX + session_id)
    await r.srem(_META_INDEX_KEY, session_id)  # type: ignore[misc]
    if removed:
        logger.info("删除会话: %s", session_id)
        return True
    return False


async def touch_session(session_id: str, user_id: str | None = None) -> None:
    """更新会话的最后活跃时间和消息计数。供 chat_service 调用。"""
    r = _get_redis()
    raw = await r.get(_META_PREFIX + session_id)

    if raw:
        meta: Dict[str, Any] = json.loads(raw)
        # 会话已存在但尚未绑定 user_id 时，补充关联
        if user_id and not meta.get("user_id"):
            meta["user_id"] = user_id
            await r.sadd(_USER_INDEX_PREFIX + user_id, session_id)  # type: ignore[misc]
    else:
        # 首次使用该 session_id 对话时自动注册
        meta = {
            "session_id": session_id,
            "title": "新对话",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "message_count": 0,
            "user_id": user_id,
            "status": "active",
        }
        await r.sadd(_META_INDEX_KEY, session_id)  # type: ignore[misc]
        if user_id:
            await r.sadd(_USER_INDEX_PREFIX + user_id, session_id)  # type: ignore[misc]

    meta["updated_at"] = datetime.now(timezone.utc).isoformat()
    meta["message_count"] = int(meta.get("message_count") or 0) + 1
    await r.set(_META_PREFIX + session_id, json.dumps(meta, ensure_ascii=False))
