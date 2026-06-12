"""
知识库与图谱路由 (/knowledge)

负责向量知识库的 CRUD 操作（针对菜谱）以及基于 Neo4j 的图谱自然语言问答。
"""
from __future__ import annotations

import asyncio
from typing import List

from fastapi import APIRouter, HTTPException

from gustobot.application.services import knowledge_service
from gustobot.domain.models.schemas import (
    GraphQARequest,
    GraphQAResponse,
    GraphSnapshotResponse,
    KBSearchRequest,
    KBSearchResponse,
    KBStatsResponse,
    OperationResponse,
    RecipeAddRequest,
    RecipeAddResponse,
    RecipeBatchResponse,
)
from gustobot.infrastructure.core.logger import get_logger

logger = get_logger(service="http.knowledge")

router = APIRouter(prefix="/knowledge", tags=["知识库与图谱"])


# ── 向量知识库 CRUD ──────────────────────────────────


@router.post("/recipes", response_model=RecipeAddResponse, status_code=201)
async def add_recipe(recipe: RecipeAddRequest) -> RecipeAddResponse:
    """添加单条菜谱到向量知识库"""
    try:
        result = await asyncio.to_thread(knowledge_service.add_recipe, recipe.model_dump())
        return RecipeAddResponse(message="菜谱已添加", recipe_id=result["recipe_id"])
    except Exception as exc:
        logger.error(f"添加菜谱失败: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/recipes/batch", response_model=RecipeBatchResponse, status_code=201)
async def add_recipes_batch(recipes: List[RecipeAddRequest]) -> RecipeBatchResponse:
    """批量添加菜谱"""
    try:
        result = await asyncio.to_thread(
            knowledge_service.add_recipes_batch, [r.model_dump() for r in recipes]
        )
        return RecipeBatchResponse(
            message=f"已插入 {result['success']} 条菜谱",
            statistics=result,
        )
    except Exception as exc:
        logger.error(f"批量添加失败: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/search", response_model=KBSearchResponse)
async def search_knowledge(request: KBSearchRequest) -> KBSearchResponse:
    """向量相似度搜索"""
    try:
        results = await asyncio.to_thread(knowledge_service.search, query=request.query, top_k=request.top_k)
        return KBSearchResponse(results=results, count=len(results))
    except Exception as exc:
        logger.error(f"搜索失败: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.delete("/recipes/{recipe_id}", response_model=OperationResponse)
async def delete_recipe(recipe_id: str) -> OperationResponse:
    """按 ID 删除单条菜谱"""
    try:
        success = await asyncio.to_thread(knowledge_service.delete_recipe, recipe_id)
        if not success:
            raise HTTPException(status_code=404, detail="菜谱未找到或删除失败")
        return OperationResponse(message=f"菜谱 {recipe_id} 已删除")
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"删除失败: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.delete("/clear", response_model=OperationResponse)
async def clear_knowledge_base(confirm: bool = False) -> OperationResponse:
    """清空向量知识库（需要 confirm=true 确认）"""
    if not confirm:
        raise HTTPException(status_code=400, detail="需要 confirm=true 确认清空操作")
    try:
        success = await asyncio.to_thread(knowledge_service.clear)
        if not success:
            raise HTTPException(status_code=500, detail="清空失败")
        return OperationResponse(message="向量知识库已清空")
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"清空失败: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/stats", response_model=KBStatsResponse)
async def get_stats() -> KBStatsResponse:
    """获取菜谱业务统计信息（来源 MySQL）"""
    try:
        stats = await asyncio.to_thread(knowledge_service.get_stats)
        return KBStatsResponse(**stats)
    except Exception as exc:
        logger.error(f"获取统计信息失败: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


# ── 图谱自然语言问答 ─────────────────────────────────


@router.get("/graph", response_model=GraphSnapshotResponse)
async def get_graph_snapshot(limit: int = 200) -> GraphSnapshotResponse:
    """获取 Neo4j 图谱快照（节点 + 关系）"""
    try:
        data = await asyncio.to_thread(knowledge_service.get_graph_snapshot, limit=limit)
        return GraphSnapshotResponse(**data)
    except Exception as exc:
        logger.error(f"获取图谱快照失败: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/graph/qa", response_model=GraphQAResponse)
async def graph_qa(request: GraphQARequest) -> GraphQAResponse:
    """基于 Neo4j 图谱的自然语言问答"""
    try:
        qa_result = await asyncio.to_thread(knowledge_service.graph_qa, request.query)
        graph_data = None
        if request.include_graph:
            raw = await asyncio.to_thread(knowledge_service.get_graph_snapshot, limit=200)
            graph_data = GraphSnapshotResponse(**raw)

        return GraphQAResponse(
            answer=qa_result["answer"],
            question_type=qa_result.get("question_type", ""),
            cypher=qa_result.get("cypher", []),
            graph=graph_data,
        )
    except Exception as exc:
        logger.error(f"图谱问答失败: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))
