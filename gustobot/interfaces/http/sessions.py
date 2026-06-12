"""
会话管理路由 (/sessions)

提供无鉴权要求的轻量级会话创建、查询、更新、软删除以及消息记录和快照管理。
"""
from __future__ import annotations

from typing import Dict, List

from fastapi import APIRouter, HTTPException

from gustobot.application.services.session_service import (
    count_user_sessions,
    create_session,
    delete_session,
    get_session,
    get_session_history,
    list_sessions,
    list_user_sessions,
    update_session,
)
from gustobot.domain.models.schemas import (
    SessionCountResponse,
    SessionCreateRequest,
    SessionHistoryResponse,
    SessionMeta,
    SessionUpdateRequest,
)
from gustobot.infrastructure.core.logger import get_logger

logger = get_logger(service="http.sessions")

router = APIRouter(prefix="/sessions", tags=["会话管理"])


@router.post("", response_model=SessionMeta, status_code=201, summary="创建会话")
async def create(req: SessionCreateRequest) -> SessionMeta:
    """创建新的对话会话，返回会话元数据。"""
    meta = await create_session(title=req.title, user_id=req.user_id)
    return SessionMeta(**meta)


@router.get("", response_model=List[SessionMeta], summary="列出所有会话")
async def list_all(
    user_id: str | None = None,
    skip: int = 0,
    limit: int = 20,
) -> List[SessionMeta]:
    """返回会话列表，按更新时间倒序。支持 user_id 过滤和分页。"""
    if user_id:
        all_sessions = [SessionMeta(**m) for m in await list_user_sessions(user_id)]
    else:
        all_sessions = [SessionMeta(**m) for m in await list_sessions()]
    return all_sessions[skip : skip + limit]


@router.get("/user/{user_id}/count", response_model=SessionCountResponse, summary="用户会话数量")
async def user_session_count(user_id: str) -> SessionCountResponse:
    """获取指定用户的会话总数。"""
    count = await count_user_sessions(user_id)
    return SessionCountResponse(user_id=user_id, count=count)


@router.get("/{session_id}", response_model=SessionMeta, summary="获取会话详情",
           responses={404: {"description": "会话不存在"}})
async def get_detail(session_id: str) -> SessionMeta:
    """获取指定会话的元数据。"""
    meta = await get_session(session_id)
    if not meta:
        raise HTTPException(status_code=404, detail="会话不存在")
    return SessionMeta(**meta)


@router.patch("/{session_id}", response_model=SessionMeta, summary="更新会话",
             responses={404: {"description": "会话不存在"}})
async def update(session_id: str, req: SessionUpdateRequest) -> SessionMeta:
    """更新会话标题和/或状态。"""
    meta = await update_session(session_id, title=req.title, status=req.status)
    if not meta:
        raise HTTPException(status_code=404, detail="会话不存在")
    return SessionMeta(**meta)


@router.get("/{session_id}/history", response_model=SessionHistoryResponse, summary="获取会话历史")
async def history(session_id: str) -> SessionHistoryResponse:
    """获取指定会话的完整消息历史。"""
    messages = await get_session_history(session_id)
    return SessionHistoryResponse(session_id=session_id, messages=messages)


@router.delete("/{session_id}", status_code=200, summary="删除会话",
              responses={404: {"description": "会话不存在"}})
async def delete(session_id: str) -> Dict[str, str]:
    """删除指定会话。"""
    if not await delete_session(session_id):
        raise HTTPException(status_code=404, detail="会话不存在")
    return {"status": "success", "session_id": session_id}
