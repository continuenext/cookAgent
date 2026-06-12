"""
统一异常处理

提供全局异常处理器和标准错误响应模型，确保所有接口返回一致的错误格式。
"""
from __future__ import annotations

from typing import Any, Dict

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from gustobot.infrastructure.core.logger import get_logger

logger = get_logger(service="http.exceptions")


class ErrorResponse:
    """标准错误响应构造器。"""

    @staticmethod
    def build(status_code: int, message: str, detail: Any = None) -> JSONResponse:
        body: Dict[str, Any] = {
            "status": "error",
            "code": status_code,
            "message": message,
        }
        if detail is not None:
            body["detail"] = detail
        return JSONResponse(status_code=status_code, content=body)


def register_exception_handlers(app: FastAPI) -> None:
    """将全局异常处理器注册到 FastAPI 应用。"""

    @app.exception_handler(HTTPException)
    async def http_exception_handler(_request: Request, exc: HTTPException) -> JSONResponse:
        return ErrorResponse.build(exc.status_code, str(exc.detail))

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
        errors = []
        for err in exc.errors():
            loc = " → ".join(str(l) for l in err.get("loc", []))
            errors.append({"field": loc, "message": err.get("msg", "")})
        return ErrorResponse.build(422, "请求参数校验失败", detail=errors)

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(_request: Request, exc: Exception) -> JSONResponse:
        logger.exception("未处理异常: %s", exc)
        return ErrorResponse.build(500, "服务内部错误，请稍后重试")
