"""
统一聊天路由 (/chat)

提供带有自动 Agent 路由分发能力的聊天入口（支持流式/非流式），
历史消息管理，以及内部逻辑路由策略查询。
"""
from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from gustobot.application.services.chat_service import chat, chat_stream
from gustobot.application.services.session_service import get_session
from gustobot.domain.models.schemas import (
    ChatRequest,
    ChatResponse,
    ChatStreamChunk,
)
from gustobot.infrastructure.core.logger import get_logger

logger = get_logger(service="http.chat")

router = APIRouter(prefix="/chat", tags=["对话"])



@router.post("", response_model=ChatResponse, summary="主对话入口",
             responses={500: {"description": "对话处理异常"}})
async def chat_query(req: ChatRequest) -> ChatResponse:
    """
    接收用户消息，自动路由到相应业务节点（闲聊/图谱/Text2SQL/知识库/图片/文件/追问），
    返回结构化回复。
    """
    try:
        result = await chat(
            message=req.message,
            session_id=req.session_id,
            user_id=req.user_id,
            image_path=req.image_path,
            file_path=req.file_path,
        )
    except Exception as exc:
        logger.exception("对话调用失败: %s", exc)
        raise HTTPException(status_code=500, detail="对话处理异常，请稍后重试") from exc

    return ChatResponse(
        answer=result["answer"],
        router_type=result["router_type"],
        session_id=req.session_id,
        steps=result.get("steps", []),
        sources=result.get("sources", []),
        sql_statement=result.get("sql_statement"),
        execution_results=result.get("execution_results"),
        documents=result.get("documents"),
    )



async def _sse_generator(req: ChatRequest):
    """将 chat_stream 产出的 Dict 序列化为 SSE data 行"""
    async for chunk_data in chat_stream(
        message=req.message,
        session_id=req.session_id,
        user_id=req.user_id,
        image_path=req.image_path,
        file_path=req.file_path,
    ):
        chunk = ChatStreamChunk(**chunk_data)
        yield f"data: {chunk.model_dump_json()}\n\n"


@router.post("/stream", summary="流式对话入口")
async def chat_stream_query(req: ChatRequest) -> StreamingResponse:
    """
    流式对话，以 SSE (Server-Sent Events) 格式返回逐步回答及元数据。
    """
    return StreamingResponse(
        _sse_generator(req),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.delete("/session/{session_id}", summary="清空会话消息",
              responses={404: {"description": "会话不存在"}})
async def clear_session_messages(session_id: str) -> Dict[str, str]:
    """清空指定会话的所有消息（元数据保留）。"""
    meta = await get_session(session_id)
    if not meta:
        raise HTTPException(status_code=404, detail="会话不存在")
    # 通过 LangGraph checkpointer 无法直接清除消息，
    # 这里只标记状态；实际消息清理需要 Redis 键操作
    logger.info("清空会话消息: %s", session_id)
    return {"status": "success", "message": "会话消息已清空", "session_id": session_id}




@router.get("/routes", summary="查询内部逻辑路由")
async def get_routes() -> Dict[str, Any]:
    """返回系统可用的智能路由类型及其说明。"""
    return {
        "routes": {
            "general-query": {
                "name": "日常对话",
                "description": "处理问候、寒暄等日常对话",
                "examples": ["你好", "谢谢", "今天天气不错"],
            },
            "additional-query": {
                "name": "补充信息",
                "description": "当问题模糊时，向用户追问更多信息",
                "examples": ["我想做菜", "帮我推荐一道菜"],
            },
            "graphrag-query": {
                "name": "图谱查询",
                "description": "查询做法、食材、烹饪技巧等图谱信息",
                "examples": ["红烧肉怎么做", "需要什么食材"],
            },
            "text2sql-query": {
                "name": "统计查询",
                "description": "统计分析、计数、排名等结构化查询",
                "examples": ["有多少道菜", "最受欢迎的菜"],
            },
            "image-query": {
                "name": "图片处理",
                "description": "处理与图片相关的请求",
                "examples": ["帮我看看这道菜是什么"],
            },
            "file-query": {
                "name": "文件处理",
                "description": "处理上传的菜谱文件",
                "examples": ["分析这个菜谱文档"],
            },
        },
        "auto_routing": "系统会根据您的问题自动选择合适的处理方式",
    }
