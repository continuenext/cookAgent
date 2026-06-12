"""
全局配置单例 - 所有参数通过 os.getenv() 从项目根目录 .env 文件中读取。
修改配置只需编辑 .env 文件即可。
"""

import os
from dotenv import load_dotenv

# ---- 加载 .env ----
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv(os.path.join(_BASE_DIR, ".env"), override=True)


def _getenv_bool(key: str, default: bool = False) -> bool:
    """将 .env 中的字符串转为 bool（支持 true/1/yes）"""
    val = os.getenv(key)
    if val is None:
        return default
    return val.strip().lower() in ("true", "1", "yes")


def _getenv_int(key: str, default: int = 0) -> int:
    val = os.getenv(key)
    if val is None:
        return default
    return int(val)


def _getenv_float(key: str, default: float = 0.0) -> float:
    val = os.getenv(key)
    if val is None:
        return default
    return float(val)


class Settings:
    """
    配置单例：每个属性都直接通过 os.getenv 从 .env 读取，
    只需修改 .env 文件即可更改全部配置。
    """

    # --- 应用基础配置 ---
    APP_NAME: str = os.getenv("APP_NAME", "GustoBot")
    APP_VERSION: str = os.getenv("APP_VERSION", "0.1.0")
    DEBUG: bool = _getenv_bool("DEBUG", True)

    # API 配置
    API_PREFIX: str = os.getenv("API_PREFIX", "/api/v1")
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = _getenv_int("PORT", 8000)

    # --- LLM (大模型) 服务配置 ---
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "openai")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "qwen3-max")
    LLM_API_KEY: str = os.getenv("LLM_API_KEY", "")
    LLM_BASE_URL: str = os.getenv("LLM_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    LLM_TEMPERATURE: float = _getenv_float("LLM_TEMPERATURE", 0.1)
    LLM_MAX_TOKENS: int = _getenv_int("LLM_MAX_TOKENS", 2048)

    # --- 视觉模型配置 ---
    VISION_API_KEY: str = os.getenv("VISION_API_KEY", "")
    VISION_BASE_URL: str = os.getenv("VISION_BASE_URL", "")
    VISION_MODEL: str = os.getenv("VISION_MODEL", "glm-4.6")

    # --- 图像生成模型配置 ---
    IMAGE_GENERATION_API_KEY: str = os.getenv("IMAGE_GENERATION_API_KEY", "")
    IMAGE_GENERATION_BASE_URL: str = os.getenv("IMAGE_GENERATION_BASE_URL", "")
    IMAGE_GENERATION_MODEL: str = os.getenv("IMAGE_GENERATION_MODEL", "")
    IMAGE_GENERATION_SIZE: str = os.getenv("IMAGE_GENERATION_SIZE", "1024x1024")

    # --- Embedding 服务配置 ---
    EMBEDDING_PROVIDER: str = os.getenv("EMBEDDING_PROVIDER", "openai")
    EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "text-embedding-v3")
    EMBEDDING_API_KEY: str = os.getenv("EMBEDDING_API_KEY", "")
    EMBEDDING_BASE_URL: str = os.getenv("EMBEDDING_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    EMBEDDING_DIMENSION: int = _getenv_int("EMBEDDING_DIMENSION", 1024)

    # --- Reranker 服务配置 ---
    RERANK_ENABLED: bool = _getenv_bool("RERANK_ENABLED", True)
    RERANK_PROVIDER: str = os.getenv("RERANK_PROVIDER", "custom")
    RERANK_BASE_URL: str = os.getenv("RERANK_BASE_URL", "https://dashscope.aliyuncs.com/api/v1/services")
    RERANK_ENDPOINT: str = os.getenv("RERANK_ENDPOINT", "/rerank/text-rerank/text-rerank")
    RERANK_MODEL: str = os.getenv("RERANK_MODEL", "qwen3-rerank")
    RERANK_API_KEY: str = os.getenv("RERANK_API_KEY", "")
    RERANK_MAX_CANDIDATES: int = _getenv_int("RERANK_MAX_CANDIDATES", 20)
    RERANK_TOP_N: int = _getenv_int("RERANK_TOP_N", 6)
    RERANK_TIMEOUT: int = _getenv_int("RERANK_TIMEOUT", 30)
    RERANK_SCORE_FUSION_ALPHA: float = _getenv_float("RERANK_SCORE_FUSION_ALPHA", 0.5)

    # --- Milvus 向量数据库配置 ---
    MILVUS_HOST: str = os.getenv("MILVUS_HOST", "milvus")
    MILVUS_PORT: int = _getenv_int("MILVUS_PORT", 19530)
    MILVUS_COLLECTION_NAME: str = os.getenv("MILVUS_COLLECTION_NAME", "recipes")
    MILVUS_INDEX_TYPE: str = os.getenv("MILVUS_INDEX_TYPE", "HNSW")
    MILVUS_METRIC_TYPE: str = os.getenv("MILVUS_METRIC_TYPE", "COSINE")

    # --- Redis 配置 ---
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    # --- 数据库配置 ---
    DATABASE_URL: str = os.getenv("DATABASE_URL", "mysql+pymysql://recipe_user:recipepass@mysql:3306/recipe_db")

    # --- Neo4j 图数据库配置 ---
    NEO4J_URI: str = os.getenv("NEO4J_URI", "bolt://neo4j:7687")
    NEO4J_USER: str = os.getenv("NEO4J_USER", "neo4j")
    NEO4J_PASSWORD: str = os.getenv("NEO4J_PASSWORD", "recipepass")
    NEO4J_DATABASE: str = "neo4j"
    NEO4J_DEFAULT_GRAPH_QUERY: str = os.getenv("NEO4J_DEFAULT_GRAPH_QUERY", "MATCH (a)-[r]-(b) RETURN a, r, b LIMIT 100")

    # --- Agent 配置 ---
    MAX_ITERATIONS: int = _getenv_int("MAX_ITERATIONS", 10)
    AGENT_TIMEOUT: int = _getenv_int("AGENT_TIMEOUT", 300)
    GUSTOBOT_MEMORY_TURNS: int = _getenv_int("GUSTOBOT_MEMORY_TURNS", 5)

    # --- Mem0 记忆层配置 ---
    MEM0_ENABLED: bool = _getenv_bool("MEM0_ENABLED", False)
    MEM0_LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "openai")
    MEM0_LLM_MODEL: str = os.getenv("LLM_MODEL", "")          # 为空时复用 LLM_MODEL
    MEM0_LLM_API_KEY: str = os.getenv("LLM_API_KEY", "")       # 为空时复用 LLM_API_KEY
    MEM0_LLM_BASE_URL: str = os.getenv("LLM_BASE_URL", "")     # 为空时复用 LLM_BASE_URL
    MEM0_SEARCH_LIMIT: int = _getenv_int("MEM0_SEARCH_LIMIT", 5)

    # --- 上下文窗口管理 ---
    CONTEXT_WINDOW_TOTAL: int = _getenv_int("CONTEXT_WINDOW_TOTAL", 131072)      # 模型上下文窗口总量（qwen3-max = 128k）
    CONTEXT_OUTPUT_RESERVE: int = _getenv_int("CONTEXT_OUTPUT_RESERVE", 4096)     # 为输出保留的 token 数
    CONTEXT_HISTORY_MAX_TOKENS: int = _getenv_int("CONTEXT_HISTORY_MAX_TOKENS", 8000)  # 对话历史最大 token 数（0=自动计算）
    CONTEXT_SUMMARY_THRESHOLD: int = _getenv_int("CONTEXT_SUMMARY_THRESHOLD", 4000)   # 超过此 token 数时触发历史摘要压缩
    CONTEXT_SUMMARY_KEEP_RECENT: int = _getenv_int("CONTEXT_SUMMARY_KEEP_RECENT", 4)  # 摘要压缩时保留最近 N 条消息原文
    CONTEXT_SCHEMA_MAX_TOKENS: int = _getenv_int("CONTEXT_SCHEMA_MAX_TOKENS", 2000)   # 图谱 schema 过滤后最大 token 数
    CONTEXT_RETRIEVAL_MAX_TOKENS: int = _getenv_int("CONTEXT_RETRIEVAL_MAX_TOKENS", 6000)  # 检索结果压缩后最大 token 数
    CONTEXT_CHUNK_SIZE: int = _getenv_int("CONTEXT_CHUNK_SIZE", 2000)              # 渐进摘要时每块的 token 上限
    CONTEXT_SQL_SCHEMA_MAX_TOKENS: int = _getenv_int("CONTEXT_SQL_SCHEMA_MAX_TOKENS", 3000)  # SQL schema 裁剪后最大 token 数

    # --- 知识库配置 ---
    KB_TOP_K: int = _getenv_int("KB_TOP_K", 5)
    KB_SIMILARITY_THRESHOLD: float = _getenv_float("KB_SIMILARITY_THRESHOLD", 0.35)
    KB_RERANK_SCORE_THRESHOLD: float = _getenv_float("KB_RERANK_SCORE_THRESHOLD", 0.0)
    KB_CHUNK_SIZE: int = _getenv_int("KB_CHUNK_SIZE", 512)
    KB_CHUNK_OVERLAP: int = _getenv_int("KB_CHUNK_OVERLAP", 80)

    # --- 数据接入服务配置 ---
    INGEST_SERVICE_URL: str = os.getenv("INGEST_SERVICE_URL", "http://kb_ingest:8000")
    INGEST_INCREMENTAL_DEFAULT: bool = _getenv_bool("INGEST_INCREMENTAL_DEFAULT", True)
    FILE_UPLOAD_MAX_MB: int = _getenv_int("FILE_UPLOAD_MAX_MB", 50)

    # --- CORS 配置 ---
    CORS_ORIGINS: str = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:5173")

    # --- Ollama 配置 ---
    OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    OLLAMA_EMBEDDING_MODEL: str = os.getenv("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text")

    # --- 路径配置 ---
    BASE_DIR: str = _BASE_DIR


# 实例化单例
settings = Settings()
