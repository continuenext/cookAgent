"""
知识库服务层

封装 Milvus 向量库与 Neo4j 图谱的业务操作，为路由层提供统一入口。
"""
from __future__ import annotations

import uuid
import re
from typing import Any, Dict, List, Optional

from langchain_core.documents import Document
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from gustobot.config.settings import settings
from gustobot.infrastructure.core.logger import get_logger

logger = get_logger(service="knowledge_service")

# ---------------------------------------------------------------------------
# 单例缓存（惰性初始化）
# ---------------------------------------------------------------------------
_milvus_module = None
_neo4j_db = None
_graph_rag = None
_mysql_engine: Optional[Engine] = None


def _get_milvus():
    """惰性获取 MilvusIndexConstructorModule 单例"""
    global _milvus_module
    if _milvus_module is None:
        from gustobot.application.agents.rag_sub_graph.components.graph_rag.rag_modules import (
            MilvusIndexConstructorModule,
        )
        _milvus_module = MilvusIndexConstructorModule()
        _milvus_module.collection_created = _milvus_module.has_collection()
    return _milvus_module


def _get_neo4j():
    """惰性获取 Neo4jDatabase 单例"""
    global _neo4j_db
    if _neo4j_db is None:
        from gustobot.infrastructure.knowledge.recipe_kg.graph_db_client import Neo4jDatabase
        _neo4j_db = Neo4jDatabase()
    return _neo4j_db


def _get_graph_rag():
    """惰性获取 GraphRAGRetrieval 单例"""
    global _graph_rag
    if _graph_rag is None:
        from types import SimpleNamespace

        from gustobot.application.agents.rag_sub_graph.components.graph_rag.rag_modules import (
            GraphRAGRetrieval,
        )
        from gustobot.application.agents.utils.llm_factory import get_llm
        from gustobot.config.settings import Settings

        cfg = SimpleNamespace(
            neo4j_uri=Settings.NEO4J_URI,
            neo4j_user=Settings.NEO4J_USER,
            neo4j_password=Settings.NEO4J_PASSWORD,
            llm_model=Settings.LLM_MODEL,
        )
        llm = get_llm(tags=["knowledge_service"])
        _graph_rag = GraphRAGRetrieval(config=cfg, llm_client=llm)
    return _graph_rag


def _get_mysql_engine() -> Engine:
    """惰性获取 MySQL Engine 单例。"""
    global _mysql_engine
    if _mysql_engine is None:
        _mysql_engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True, future=True)
    return _mysql_engine


# ── 向量知识库操作 ────────────────────────────────────


def add_recipe(recipe_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    添加单条菜谱到 Milvus 向量库。

    将菜谱字段组装为文本 Document，调用 add_documents 写入。
    """
    milvus = _get_milvus()

    recipe_id = recipe_data.get("id") or f"recipe_{uuid.uuid4().hex[:8]}"
    text = _recipe_to_text(recipe_data)

    doc = Document(
        page_content=text,
        metadata={
            "chunk_id": recipe_id,
            "node_id": recipe_id,
            "recipe_name": recipe_data.get("name", ""),
            "node_type": "Recipe",
            "category": recipe_data.get("category", ""),
            "cuisine_type": "",
            "difficulty": 0,
            "doc_type": "recipe",
            "parent_id": "",
        },
    )

    success = milvus.add_documents([doc])
    if not success:
        raise RuntimeError("Milvus add_documents 失败")

    return {"recipe_id": recipe_id}


def add_recipes_batch(recipes: List[Dict[str, Any]]) -> Dict[str, Any]:
    """批量添加菜谱"""
    milvus = _get_milvus()

    docs: List[Document] = []
    ids: List[str] = []
    for r in recipes:
        rid = r.get("id") or f"recipe_{uuid.uuid4().hex[:8]}"
        ids.append(rid)
        text = _recipe_to_text(r)
        docs.append(Document(
            page_content=text,
            metadata={
                "chunk_id": rid,
                "node_id": rid,
                "recipe_name": r.get("name", ""),
                "node_type": "Recipe",
                "category": r.get("category", ""),
                "cuisine_type": "",
                "difficulty": 0,
                "doc_type": "recipe",
                "parent_id": "",
            },
        ))

    success = milvus.add_documents(docs)
    return {
        "total": len(recipes),
        "success": len(recipes) if success else 0,
        "failed": 0 if success else len(recipes),
        "ids": ids,
    }


def search(query: str, top_k: int = 5) -> List[Dict[str, Any]]:
    """向量相似度搜索"""
    milvus = _get_milvus()
    results = milvus.similarity_search(query, k=top_k)
    # 设置最低阈值兜底，避免环境配置过低导致无关查询也返回结果
    threshold = max(float(getattr(settings, "KB_SIMILARITY_THRESHOLD", 0.0) or 0.0), 0.35)

    if threshold <= 0:
        return results

    filtered: List[Dict[str, Any]] = []
    for item in results:
        score = item.get("score", 0)
        try:
            score_val = float(score)
        except (TypeError, ValueError):
            continue
        if score_val >= threshold:
            filtered.append(item)

    return filtered


def delete_recipe(recipe_id: str) -> bool:
    """按 ID 删除单条向量"""
    milvus = _get_milvus()
    client = milvus._ensure_client()
    try:
        if not milvus.has_collection():
            logger.warning(f"集合不存在，无法删除向量: {recipe_id}")
            return False

        if not milvus.load_collection():
            logger.error(f"集合加载失败，无法删除向量: {recipe_id}")
            return False

        existing = client.get(
            collection_name=milvus.collection_name,
            ids=[recipe_id],
            output_fields=["id"],
        )

        if not existing:
            logger.info(f"向量不存在，无需删除: {recipe_id}")
            return False

        result = client.delete(
            collection_name=milvus.collection_name,
            ids=[recipe_id],
        )

        deleted_count = 0
        if isinstance(result, dict):
            deleted_count = int(result.get("delete_count") or result.get("deleted_count") or 0)
        elif isinstance(result, int):
            deleted_count = result

        # 某些 Milvus 版本删除返回不包含 delete_count，
        # 此时只要调用成功且删除前存在记录，就视为成功提交。
        if deleted_count <= 0 and isinstance(result, dict) and ("delete_count" in result or "deleted_count" in result):
            logger.warning(f"删除请求已提交但未删除任何向量: {recipe_id}, result={result}")
            return False

        logger.info(f"已删除向量: {recipe_id}")
        return True
    except Exception as e:
        logger.error(f"删除向量失败: {e}")
        return False


def clear() -> bool:
    """清空整个向量集合并重建空集合"""
    milvus = _get_milvus()
    return milvus.delete_collection()


def get_stats() -> Dict[str, Any]:
    """获取菜谱业务统计信息（来源 MySQL）。"""
    engine = _get_mysql_engine()

    with engine.connect() as conn:
        total_recipes = int(conn.execute(text("SELECT COUNT(*) FROM recipes")).scalar() or 0)
        total_cuisines = int(conn.execute(text("SELECT COUNT(*) FROM cuisines")).scalar() or 0)
        total_ingredients = int(conn.execute(text("SELECT COUNT(*) FROM ingredients")).scalar() or 0)
        total_steps = int(conn.execute(text("SELECT COUNT(*) FROM recipe_steps")).scalar() or 0)
        avg_total_time = float(conn.execute(text("SELECT COALESCE(AVG(total_time), 0) FROM recipes")).scalar() or 0.0)

        difficulty_rows = conn.execute(text(
            """
            SELECT COALESCE(difficulty, 'unknown') AS difficulty, COUNT(*) AS cnt
            FROM recipes
            GROUP BY COALESCE(difficulty, 'unknown')
            ORDER BY cnt DESC
            """
        )).fetchall()

        cuisine_rows = conn.execute(text(
            """
            SELECT COALESCE(c.name, '未知') AS cuisine, COUNT(*) AS cnt
            FROM recipes r
            LEFT JOIN cuisines c ON r.cuisine_id = c.id
            GROUP BY COALESCE(c.name, '未知')
            ORDER BY cnt DESC
            """
        )).fetchall()

        ingredient_rows = conn.execute(text(
            """
            SELECT i.name AS ingredient, COUNT(*) AS usage_count
            FROM recipe_ingredients ri
            JOIN ingredients i ON ri.ingredient_id = i.id
            GROUP BY i.name
            ORDER BY usage_count DESC
            LIMIT 10
            """
        )).fetchall()

    # 标准化菜系字段：拆分混合值（如“川菜,鲁菜,浙菜...”）并聚合
    cuisine_distribution: Dict[str, int] = {}
    for raw_name, raw_cnt in cuisine_rows:
        cnt = int(raw_cnt)
        name = str(raw_name or "未知").strip()
        parts = [p.strip() for p in re.split(r"[,，、/]+", name) if p.strip()]
        if not parts:
            parts = ["未知"]
        for part in parts:
            cuisine_distribution[part] = cuisine_distribution.get(part, 0) + cnt

    cuisine_distribution = dict(
        sorted(cuisine_distribution.items(), key=lambda item: item[1], reverse=True)
    )

    return {
        "total_recipes": total_recipes,
        "total_cuisines": total_cuisines,
        "total_ingredients": total_ingredients,
        "total_steps": total_steps,
        "avg_total_time_minutes": round(avg_total_time, 2),
        "difficulty_distribution": {str(r[0]): int(r[1]) for r in difficulty_rows},
        "cuisine_distribution": cuisine_distribution,
        "top_ingredients": [
            {"name": str(r[0]).strip(), "count": int(r[1])}
            for r in ingredient_rows
        ],
    }


# ── 图谱操作 ─────────────────────────────────────────


def get_graph_snapshot(limit: int = 200) -> Dict[str, Any]:
    """
    获取 Neo4j 图谱快照（节点 + 关系），默认限制 200 条关系。
    """
    db = _get_neo4j()

    nodes_query = (
        "MATCH (n) RETURN id(n) AS id, labels(n) AS labels, properties(n) AS props "
        "LIMIT $limit"
    )
    rels_query = (
        "MATCH (a)-[r]->(b) "
        "RETURN id(r) AS id, type(r) AS type, id(a) AS source, id(b) AS target, "
        "properties(r) AS props LIMIT $limit"
    )

    raw_nodes = db.fetch(nodes_query, {"limit": limit})
    raw_rels = db.fetch(rels_query, {"limit": limit})

    nodes = [
        {"id": r["id"], "labels": r["labels"], "properties": r["props"]}
        for r in raw_nodes
    ]
    relationships = [
        {
            "id": r["id"],
            "type": r["type"],
            "source": r["source"],
            "target": r["target"],
            "properties": r["props"],
        }
        for r in raw_rels
    ]

    return {"nodes": nodes, "relationships": relationships}


def graph_qa(query: str) -> Dict[str, Any]:
    """
    基于 GraphRAG 的自然语言问答。

    调用 GraphRAGRetrieval.graph_rag_search 获取相关文档，
    拼装为回答所需信息。
    """
    rag = _get_graph_rag()
    try:
        docs = rag.graph_rag_search(query, top_k=5)
        answer_parts = [doc.page_content for doc in docs if doc.page_content]
        answer = "\n\n".join(answer_parts) if answer_parts else "未找到相关图谱信息。"
        return {
            "answer": answer,
            "question_type": "",
            "cypher": [],
        }
    except Exception as e:
        logger.error(f"GraphRAG 问答失败: {e}")
        return {"answer": f"图谱问答出错: {e}", "question_type": "error", "cypher": []}


# ── 内部工具 ─────────────────────────────────────────


def _recipe_to_text(recipe: Dict[str, Any]) -> str:
    """将菜谱字典拼接为适合向量化的文本"""
    parts = [f"菜谱: {recipe.get('name', '')}"]
    if recipe.get("category"):
        parts.append(f"分类: {recipe['category']}")
    if recipe.get("difficulty"):
        parts.append(f"难度: {recipe['difficulty']}")
    if recipe.get("time"):
        parts.append(f"时间: {recipe['time']}")
    if recipe.get("ingredients"):
        parts.append(f"食材: {'、'.join(recipe['ingredients'])}")
    if recipe.get("steps"):
        parts.append("步骤:\n" + "\n".join(f"{i+1}. {s}" for i, s in enumerate(recipe["steps"])))
    if recipe.get("tips"):
        parts.append(f"技巧: {recipe['tips']}")
    return "\n".join(parts)
