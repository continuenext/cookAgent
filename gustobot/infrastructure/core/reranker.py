"""
Reranker 服务

调用阿里云百炼 Rerank API（qwen3-rerank）对检索结果进行语义重排序。
作为基础设施模块，供检索层统一调用。
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Tuple

import aiohttp

from gustobot.config.settings import settings
from gustobot.infrastructure.core.logger import get_logger

logger = get_logger(service="reranker")


async def rerank_documents(
    query: str,
    documents: List[str],
    *,
    top_n: Optional[int] = None,
    model: Optional[str] = None,
) -> List[Tuple[int, float]]:
    """
    调用 Rerank API 对候选文档进行语义重排序。

    Args:
        query: 用户查询
        documents: 候选文本列表
        top_n: 返回前 N 个结果（默认 settings.RERANK_TOP_N）
        model: 重排模型名（默认 settings.RERANK_MODEL）

    Returns:
        按相关性降序排列的 (原始索引, 分数) 列表
    """
    if not documents:
        logger.debug("Rerank 跳过: 候选文档为空")
        return []

    if not settings.RERANK_ENABLED:
        logger.debug("Reranker 未启用，跳过重排序")
        return [(i, 1.0) for i in range(len(documents))]

    api_key = settings.RERANK_API_KEY
    if not api_key:
        logger.warning("缺少 RERANK_API_KEY，跳过重排序")
        return [(i, 1.0) for i in range(len(documents))]

    top_n = top_n or settings.RERANK_TOP_N
    model = model or settings.RERANK_MODEL
    url = f"{settings.RERANK_BASE_URL}{settings.RERANK_ENDPOINT}"

    # 截断候选数量，避免超过 API 限制
    max_candidates = settings.RERANK_MAX_CANDIDATES
    truncated = documents[:max_candidates]

    logger.info(
        "Rerank 开始: model=%s, top_n=%d, 候选=%d(截断后=%d)",
        model,
        top_n,
        len(documents),
        len(truncated),
    )

    payload: Dict[str, Any] = {
        "model": model,
        "input": {
            "query": query,
            "documents": truncated,
        },
        "parameters": {
            "top_n": min(top_n, len(truncated)),
        },
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        started_at = time.perf_counter()
        timeout = aiohttp.ClientTimeout(total=settings.RERANK_TIMEOUT)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, headers=headers, json=payload) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    logger.error("Rerank API 返回 %d: %s", resp.status, error_text[:200])
                    return [(i, 1.0) for i in range(len(documents))]

                data = await resp.json()

        results_raw = data.get("output", {}).get("results", [])
        ranked: List[Tuple[int, float]] = []
        for item in results_raw:
            idx = item.get("index", 0)
            score = item.get("relevance_score", 0.0)
            ranked.append((idx, score))

        # 按分数降序排列
        ranked.sort(key=lambda x: x[1], reverse=True)
        elapsed_ms = (time.perf_counter() - started_at) * 1000
        logger.info("Rerank 完成: %d 候选 → %d 结果 (%.1fms)", len(truncated), len(ranked), elapsed_ms)
        return ranked

    except Exception as exc:
        logger.error("Rerank API 调用失败: %s", exc)
        return [(i, 1.0) for i in range(len(documents))]
