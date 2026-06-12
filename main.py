from contextlib import asynccontextmanager
from pathlib import Path
import asyncio
import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from gustobot.config.settings import settings
from gustobot.infrastructure.core.logger import get_logger
from gustobot.interfaces.http.exceptions import register_exception_handlers
from gustobot.interfaces.http.router import register_routers

logger = get_logger(service="http")


async def _startup_check_milvus() -> None:
    """启动自检：检查 Milvus 集合是否可用，并尝试最小化自愈。"""
    from gustobot.application.services import knowledge_service

    def _check() -> None:
        try:
            milvus = knowledge_service._get_milvus()
            collection_name = milvus.collection_name

            if not milvus.has_collection():
                logger.warning(
                    "Milvus 启动自检：集合 %s 不存在。若需恢复检索数据，请执行重建脚本。",
                    collection_name,
                )
                return

            if not milvus.load_collection():
                logger.warning("Milvus 启动自检：集合 %s 无法加载，尝试补建索引", collection_name)
                if milvus.create_index() and milvus.load_collection():
                    logger.info("Milvus 启动自检：集合 %s 索引修复成功", collection_name)
                else:
                    logger.error(
                        "Milvus 启动自检：集合 %s 索引修复失败，请手动执行重建脚本。",
                        collection_name,
                    )
                    return

            stats = milvus.get_collection_stats()
            logger.info(
                "Milvus 启动自检通过：collection=%s, row_count=%s",
                collection_name,
                stats.get("row_count", 0),
            )
        except Exception as exc:
            logger.error("Milvus 启动自检失败: %s", exc)

    await asyncio.to_thread(_check)


@asynccontextmanager
async def lifespan(application: FastAPI):
    """启动时异步初始化 LangGraph 主图（含 Redis checkpointer）。"""
    from gustobot.application.agents.lg_builder import init_graph
    await init_graph()
    await _startup_check_milvus()
    yield


app = FastAPI(
    title=settings.APP_NAME,
    description="菜谱知识智能助手",
    version=settings.APP_VERSION,
    lifespan=lifespan,
)


def _build_cors_origins(raw_origins: str) -> list[str]:
    """解析 CORS 源，并自动补全 localhost/127.0.0.1 等价源。"""
    base = [o.strip() for o in raw_origins.split(",") if o.strip()]
    origin_set = set(base)

    for origin in base:
        if "localhost" in origin:
            origin_set.add(origin.replace("localhost", "127.0.0.1"))
        if "127.0.0.1" in origin:
            origin_set.add(origin.replace("127.0.0.1", "localhost"))

    return sorted(origin_set)


LOCAL_CORS_ORIGIN_REGEX = r"^https?://(localhost|127\.0\.0\.1|0\.0\.0\.0)(:\d+)?$|^null$"

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=_build_cors_origins(settings.CORS_ORIGINS),
    allow_origin_regex=LOCAL_CORS_ORIGIN_REGEX,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_request_time(request: Request, call_next):
    """记录每个请求的耗时"""
    start = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = (time.perf_counter() - start) * 1000
    logger.info(
        "%s %s → %d (%.1fms)",
        request.method, request.url.path, response.status_code, elapsed_ms,
    )
    return response


# 注册全局异常处理
register_exception_handlers(app)

# 注册路由
register_routers(app)


@app.get("/health", tags=["运维"], summary="健康检查")
async def health_check():
    """检查各基础设施服务的连通性，适用于 Docker / K8s 探活探针。"""
    import asyncio
    checks: dict[str, str] = {}

    # Redis
    try:
        import redis.asyncio as aioredis
        r = aioredis.from_url(settings.REDIS_URL)
        await r.ping()
        await r.aclose()
        checks["redis"] = "ok"
    except Exception as e:
        checks["redis"] = f"error: {e}"

    # Milvus
    try:
        from pymilvus import connections
        await asyncio.to_thread(
            connections.connect, alias="health",
            host=settings.MILVUS_HOST, port=str(settings.MILVUS_PORT),
        )
        await asyncio.to_thread(connections.disconnect, "health")
        checks["milvus"] = "ok"
    except Exception as e:
        checks["milvus"] = f"error: {e}"

    # Neo4j
    try:
        from neo4j import GraphDatabase
        driver = GraphDatabase.driver(settings.NEO4J_URI)
        await asyncio.to_thread(driver.verify_connectivity)
        await asyncio.to_thread(driver.close)
        checks["neo4j"] = "ok"
    except Exception as e:
        checks["neo4j"] = f"error: {e}"

    # MySQL
    try:
        from sqlalchemy import create_engine, text as sa_text
        def _check_mysql():
            engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)
            with engine.connect() as conn:
                conn.execute(sa_text("SELECT 1"))
            engine.dispose()
        await asyncio.to_thread(_check_mysql)
        checks["mysql"] = "ok"
    except Exception as e:
        checks["mysql"] = f"error: {e}"

    all_ok = all(v == "ok" for v in checks.values())
    from fastapi.responses import JSONResponse
    return JSONResponse(
        status_code=200 if all_ok else 503,
        content={"status": "healthy" if all_ok else "degraded", "services": checks},
    )

# 静态文件 & 测试面板
_static_dir = Path(__file__).parent / "static"
if _static_dir.is_dir():
    app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")

    @app.get("/", include_in_schema=False)
    async def serve_index():
        return FileResponse(str(_static_dir / "index.html"))

    @app.get("/favicon.ico", include_in_schema=False)
    async def serve_favicon():
        return FileResponse(str(_static_dir / "favicon.ico"), media_type="image/x-icon")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
    )
