from pydantic import SecretStr
from langchain_openai import ChatOpenAI
from typing import Optional, List
from gustobot.infrastructure.core.logger import get_logger
from gustobot.config.settings import settings

logger = get_logger(service="llm_factory")

def get_llm(tags: Optional[List[str]] = None) -> ChatOpenAI:
    """获取配置好的 LLM 实例（所有参数从 settings 读取）"""
    if not settings.LLM_API_KEY:
        logger.error("LLM_API_KEY 未在 .env 中配置。")
        raise ValueError("请在 .env 中设置 LLM_API_KEY")
    return ChatOpenAI(
        model_name=settings.LLM_MODEL,
        openai_api_key=SecretStr(settings.LLM_API_KEY),
        openai_api_base=settings.LLM_BASE_URL,
        temperature=settings.LLM_TEMPERATURE,
        max_tokens=settings.LLM_MAX_TOKENS,
        tags=tags or []
    )
