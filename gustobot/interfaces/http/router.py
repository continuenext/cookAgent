"""
路由注册

集中注册所有 HTTP 路由到 FastAPI 应用。
四大模块: /knowledge, /sessions, /chat, /upload
"""
from __future__ import annotations

from fastapi import APIRouter, FastAPI

from gustobot.config.settings import settings


def register_routers(app: FastAPI) -> None:
    """将所有路由挂载到 FastAPI 实例，统一前缀"""
    from gustobot.interfaces.http.knowledge import router as knowledge_router
    from gustobot.interfaces.http.sessions import router as sessions_router
    from gustobot.interfaces.http.chat import router as chat_router
    from gustobot.interfaces.http.upload import router as upload_router

    api_router = APIRouter(prefix=settings.API_PREFIX)
    api_router.include_router(knowledge_router)
    api_router.include_router(sessions_router)
    api_router.include_router(chat_router)
    api_router.include_router(upload_router)

    app.include_router(api_router)
