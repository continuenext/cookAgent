"""
Mem0 记忆管理器 — 为 Agent 提供跨会话长期记忆能力。

核心功能:
- 自动从对话中提取关键事实并持久化存储
- 按语义相关性检索用户历史记忆
- 所有操作均带 try/except 保护，mem0 故障不影响主聊天流程

使用示例:
    mgr = get_memory_manager()
    if mgr:
        mgr.add_memory(messages, user_id="user_123")
        memories = mgr.search_memory("用户喜欢什么口味", user_id="user_123")
"""

from typing import Any, Dict, List, Optional

from gustobot.config.settings import settings
from gustobot.infrastructure.core.logger import get_logger

logger = get_logger(service="memory_manager")

# 模块级单例
_memory_manager_instance: Optional["MemoryManager"] = None


class MemoryManager:
    """封装 mem0 Memory 实例，提供记忆增删查接口。"""

    def __init__(self) -> None:
        from mem0 import Memory

        config = self._build_config()
        logger.info("正在初始化 Mem0 Memory 实例...")
        self._memory = Memory.from_config(config)
        logger.info("Mem0 Memory 初始化完成")

    # ──────────────────── 配置构建 ────────────────────

    @staticmethod
    def _build_config() -> Dict[str, Any]:
        """根据 settings 构建 mem0 配置字典。LLM / Embedding 参数为空时自动复用主配置。"""
        config: Dict[str, Any] = {
            "llm": {
                "provider": settings.MEM0_LLM_PROVIDER or "openai",
                "config": {
                    "model": settings.MEM0_LLM_MODEL or settings.LLM_MODEL,
                    "api_key": settings.MEM0_LLM_API_KEY or settings.LLM_API_KEY,
                    "openai_base_url": settings.MEM0_LLM_BASE_URL or settings.LLM_BASE_URL,
                    "temperature": 0.1,
                    "max_tokens": 1500,
                },
            },
            "embedder": {
                "provider": "openai",
                "config": {
                    "model": settings.EMBEDDING_MODEL,
                    "api_key": settings.EMBEDDING_API_KEY,
                    "openai_base_url": settings.EMBEDDING_BASE_URL,
                    "embedding_dims": settings.EMBEDDING_DIMENSION,
                },
            },
        }
        logger.debug(
            "Mem0 配置: LLM=%s/%s, Embedder=%s/%s",
            config["llm"]["provider"],
            config["llm"]["config"]["model"],
            config["embedder"]["provider"],
            config["embedder"]["config"]["model"],
        )
        return config

    # ──────────────────── 核心接口 ────────────────────

    def add_memory(
        self,
        messages: List[Dict[str, str]],
        user_id: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """从对话消息中提取并存储记忆。

        Args:
            messages: OpenAI 格式消息列表 [{"role": "user", "content": "..."}]
            user_id: 用户唯一标识
            metadata: 附加元数据（可选）

        Returns:
            mem0 返回的结果字典，失败返回 None
        """
        try:
            result = self._memory.add(messages, user_id=user_id, metadata=metadata or {})
            logger.info("记忆存储成功: user_id=%s", user_id)
            logger.debug("记忆存储结果: %s", result)
            return result
        except Exception as e:
            logger.warning("记忆存储失败 (不影响主流程): %s", e)
            return None

    def search_memory(
        self,
        query: str,
        user_id: str,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """按语义搜索用户相关记忆。

        Args:
            query: 搜索查询文本
            user_id: 用户唯一标识
            limit: 返回结果上限，默认使用 settings.MEM0_SEARCH_LIMIT

        Returns:
            匹配的记忆列表，失败返回空列表
        """
        try:
            _limit = limit or settings.MEM0_SEARCH_LIMIT
            results = self._memory.search(query=query, user_id=user_id, limit=_limit)
            # mem0 返回格式: {"results": [{"memory": "...", "id": "...", ...}, ...]}
            memories = results.get("results", []) if isinstance(results, dict) else results
            logger.info("记忆检索成功: user_id=%s, query=%s, 命中=%d条", user_id, query[:50], len(memories))
            return memories
        except Exception as e:
            logger.warning("记忆检索失败 (不影响主流程): %s", e)
            return []

    def get_all_memories(self, user_id: str) -> List[Dict[str, Any]]:
        """获取指定用户的全部记忆。

        Args:
            user_id: 用户唯一标识

        Returns:
            全部记忆列表，失败返回空列表
        """
        try:
            results = self._memory.get_all(user_id=user_id)
            memories = results.get("results", []) if isinstance(results, dict) else results
            logger.info("获取全部记忆: user_id=%s, 共%d条", user_id, len(memories))
            return memories
        except Exception as e:
            logger.warning("获取全部记忆失败: %s", e)
            return []

    def delete_memory(self, memory_id: str) -> bool:
        """删除指定记忆。

        Args:
            memory_id: 记忆 ID

        Returns:
            是否成功删除
        """
        try:
            self._memory.delete(memory_id=memory_id)
            logger.info("记忆删除成功: memory_id=%s", memory_id)
            return True
        except Exception as e:
            logger.warning("记忆删除失败: %s", e)
            return False


def get_memory_manager() -> Optional[MemoryManager]:
    """获取 MemoryManager 单例。MEM0_ENABLED=false 时返回 None。

    Returns:
        MemoryManager 实例或 None（未启用时）
    """
    global _memory_manager_instance

    if not settings.MEM0_ENABLED:
        return None

    if _memory_manager_instance is None:
        try:
            _memory_manager_instance = MemoryManager()
        except Exception as e:
            logger.error("MemoryManager 初始化失败，记忆功能将不可用: %s", e)
            return None

    return _memory_manager_instance
