"""
Guardrails + Schema 检索节点

职责：
1. 判断用户问题是否属于数据库查询范围（菜谱关系型数据查询、统计分析等）
2. 若在范围内，从 MySQL INFORMATION_SCHEMA 检索表结构
3. 若超出范围，直接返回友好拒绝信息并短路到 END
"""
from __future__ import annotations

import re
from typing import Any, Callable, Coroutine, Dict, Iterable, List, Optional, Set, Tuple
from gustobot.application.agents.text2sql_sub_graph.states import Text2SQLState
from gustobot.application.prompts.lg_prompts import GUARDRAILS_SYSTEM_PROMPT, SCOPE_DESCRIPTION
from langchain.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from gustobot.application.agents.utils.llm_factory import get_llm
from gustobot.config.settings import settings
from gustobot.infrastructure.core.logger import get_logger
from ..domain_knowledge import (
    COLUMN_DESCRIPTIONS,
    RELATIONSHIP_FACTS,
    TABLE_DESCRIPTIONS,
)

logger = get_logger(service="text2sql.guardrails")


# ---------- 范围判定相关 ----------

class _GuardrailsDecision(BaseModel):
    """LLM 范围判定结构化输出"""
    decision: str = Field(
        description="'proceed' 表示问题属于菜谱数据库查询范围，'end' 表示超出范围"
    )


# 数据查询/统计相关关键词
_SCOPE_KEYWORDS = [
    "菜", "菜谱", "食材", "烹饪", "做法", "步骤", "口味", "工具",
    "菜系", "配料", "用量", "营养", "统计", "多少", "排行", "排名",
    "哪些", "列出", "查询", "数据", "平均", "最多", "最少", "总共",
    "recipe", "ingredient", "cuisine", "cooking", "dish",
]

_OUT_OF_SCOPE_ANSWER = (
    "厨友您好～抱歉哦，这个问题不太属于我们菜谱数据库的查询范围呢，"
    "我主要帮您检索和统计菜谱、食材、烹饪步骤等数据～😊"
)


# ---------- 停用词（用于 schema 过滤） ----------

_STOP_WORDS: Set[str] = {
    "the", "and", "for", "from", "with", "into",
    "what", "which", "when", "who", "where", "how",
    "many", "much", "that", "this", "those", "these",
    "all", "any", "year", "month", "day",
    "query", "please", "show", "list", "give",
    "查询", "一下", "所有", "哪些", "什么", "数据",
}


def create_guardrails_node(
    scope_description: Optional[str] = None,
) -> Callable[[Text2SQLState], Coroutine[Any, Any, Dict[str, Any]]]:
    """
    创建 Text2SQL Guardrails 节点。
    职责：范围判定 + Schema 检索。

    返回字段：next_action, schema_context, value_mappings, mappings_str, answer(仅拒绝时), steps
    """
    logger.info("创建 Text2SQL Guardrails 节点")

    llm = get_llm(tags=["text2sql_guardrails"])
    scope_desc = scope_description or SCOPE_DESCRIPTION
    scope_ctx = f"\n参考范围描述:\n{scope_description}" if scope_description else ""
    guardrails_prompt = ChatPromptTemplate.from_messages([
        ("system", GUARDRAILS_SYSTEM_PROMPT),
        ("human", scope_ctx + "\n用户问题: {question}"),
    ])
    guardrails_chain = guardrails_prompt | llm.with_structured_output(_GuardrailsDecision)

    async def guardrails(state: Text2SQLState) -> Dict[str, Any]:
        question = (state.get("question") or "").strip()
        logger.info("Guardrails 收到问题: %s", question)

        # —— 1. 关键词快速通过 ——
        if any(kw in question for kw in _SCOPE_KEYWORDS):
            logger.info("关键词命中，直接放行到 schema 检索")
            return await _retrieve_and_return(question)

        # —— 2. LLM 判定 ——
        try:
            result = await guardrails_chain.ainvoke({"question": question})
        except Exception as exc:
            logger.warning("Guardrails LLM 调用失败，回退放行: %s", exc)
            return await _retrieve_and_return(question)

        if result is None or not isinstance(result, _GuardrailsDecision):
            logger.warning("Guardrails 输出异常，默认放行")
            return await _retrieve_and_return(question)

        if result.decision == "end":
            logger.info("Guardrails 判定问题超出范围")
            return {
                "next_action": "end",
                "answer": _OUT_OF_SCOPE_ANSWER,
                "schema_context": {},
                "value_mappings": {},
                "mappings_str": "",
                "steps": ["guardrails_rejected"],
            }

        # decision == "proceed"
        return await _retrieve_and_return(question)

    async def _retrieve_and_return(question: str) -> Dict[str, Any]:
        """范围通过后，执行 Schema 检索并返回。若无匹配表则拒绝。"""
        try:
            schema_context = await _retrieve_schema_from_mysql(question)
            matched_tables = schema_context.get("tables", [])

            if not matched_tables:
                logger.info("Schema 检索无匹配表，判定为超出数据库查询范围")
                return {
                    "next_action": "end",
                    "answer": "抱歉，您的问题在当前数据库中没有找到相关的表或字段，暂时无法查询哦～",
                    "schema_context": {},
                    "value_mappings": {},
                    "mappings_str": "",
                    "steps": ["guardrails_no_matching_tables"],
                }

            logger.info("Schema 检索完成，匹配到 %d 张表", len(matched_tables))
            return {
                "next_action": "proceed",
                "schema_context": schema_context,
                "value_mappings": {},
                "mappings_str": "",
                "steps": ["guardrails"],
            }
        except Exception as exc:
            logger.exception("Schema 检索失败: %s", exc)
            return {
                "next_action": "end",
                "schema_context": {},
                "value_mappings": {},
                "mappings_str": "",
                "steps": ["guardrails_schema_failed"],
            }

    return guardrails


def _extract_keywords(question: str) -> List[str]:
    if not question:
        return []

    tokens = re.findall(r"[a-zA-Z0-9_]+", question.lower())
    return [token for token in tokens if token and token not in _STOP_WORDS]


def _score_table(table: Dict[str, Any], keywords: Iterable[str]) -> float:
    if not keywords:
        return 0.0

    score = 0.0
    name = (table.get("table_name") or "").lower()
    description = (table.get("description") or "").lower()

    for kw in keywords:
        if kw in name:
            score += 2.0
        if kw in description:
            score += 1.0

    for column in table.get("columns", []):
        column_name = (column.get("column_name") or "").lower()
        column_desc = (column.get("description") or "").lower()
        for kw in keywords:
            if kw in column_name:
                score += 1.5
            if kw in column_desc:
                score += 0.75

    return score


async def _retrieve_schema_from_mysql(question: str) -> Dict[str, Any]:
    """
    直接从 MySQL INFORMATION_SCHEMA 读取表结构信息。
    """
    import asyncio

    def _sync_retrieve():
        engine: Engine = create_engine(settings.DATABASE_URL, future=True)
        try:
            with engine.connect() as conn:
                # 获取所有表信息
                tables_query = text("""
                    SELECT
                        TABLE_NAME,
                        TABLE_COMMENT
                    FROM INFORMATION_SCHEMA.TABLES
                    WHERE TABLE_SCHEMA = DATABASE()
                    AND TABLE_TYPE = 'BASE TABLE'
                    ORDER BY TABLE_NAME
                """)
                table_rows = conn.execute(tables_query).fetchall()

                tables: List[Dict[str, Any]] = []

                for table_row in table_rows:
                    table_name = table_row[0]
                    table_comment = table_row[1] or ""
                    table_key = table_name.lower()

                    # 使用领域知识库补充描述
                    table_description = table_comment or TABLE_DESCRIPTIONS.get(table_key) or ""

                    # 获取列信息
                    columns_query = text("""
                        SELECT
                            COLUMN_NAME,
                            DATA_TYPE,
                            COLUMN_COMMENT,
                            COLUMN_KEY
                        FROM INFORMATION_SCHEMA.COLUMNS
                        WHERE TABLE_SCHEMA = DATABASE()
                        AND TABLE_NAME = :table_name
                        ORDER BY ORDINAL_POSITION
                    """)
                    column_rows = conn.execute(columns_query, {"table_name": table_name}).fetchall()

                    columns: List[Dict[str, Any]] = []
                    for col_row in column_rows:
                        column_name = col_row[0]
                        data_type = col_row[1]
                        column_comment = col_row[2] or ""
                        column_key = col_row[3]

                        # 使用领域知识库补充描述
                        column_desc_key = (table_key, column_name.lower())
                        column_description = column_comment or COLUMN_DESCRIPTIONS.get(column_desc_key) or ""

                        columns.append({
                            "column_name": column_name,
                            "data_type": data_type,
                            "description": column_description,
                            "is_primary_key": column_key == "PRI",
                            "is_foreign_key": column_key in ("MUL", "FK"),
                            "is_unique": column_key == "UNI",
                        })

                    tables.append({
                        "table_name": table_name,
                        "description": table_description,
                        "columns": columns,
                    })

                # 获取外键关系
                fk_query = text("""
                    SELECT
                        kcu.TABLE_NAME as source_table,
                        kcu.COLUMN_NAME as source_column,
                        kcu.REFERENCED_TABLE_NAME as target_table,
                        kcu.REFERENCED_COLUMN_NAME as target_column
                    FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE kcu
                    WHERE kcu.TABLE_SCHEMA = DATABASE()
                    AND kcu.REFERENCED_TABLE_NAME IS NOT NULL
                    ORDER BY kcu.TABLE_NAME, kcu.COLUMN_NAME
                """)
                fk_rows = conn.execute(fk_query).fetchall()

                relationships: List[Dict[str, Any]] = []
                seen_keys: Set[Tuple[str, str, str, str]] = set()

                for fk_row in fk_rows:
                    key = (fk_row[0], fk_row[1], fk_row[2], fk_row[3])
                    if key in seen_keys:
                        continue
                    seen_keys.add(key)

                    relationships.append({
                        "source_table": fk_row[0],
                        "source_column": fk_row[1],
                        "target_table": fk_row[2],
                        "target_column": fk_row[3],
                        "relationship_type": "FOREIGN_KEY",
                        "description": f"{fk_row[0]}.{fk_row[1]} references {fk_row[2]}.{fk_row[3]}",
                    })

                # 添加领域知识关系
                table_name_lookup = {t["table_name"].lower(): t["table_name"] for t in tables}
                for relationship in RELATIONSHIP_FACTS:
                    source_lower = relationship["source_table"].lower()
                    target_lower = relationship["target_table"].lower()
                    if source_lower not in table_name_lookup or target_lower not in table_name_lookup:
                        continue

                    source_name = table_name_lookup[source_lower]
                    target_name = table_name_lookup[target_lower]

                    key = (
                        source_name,
                        relationship["source_column"],
                        target_name,
                        relationship["target_column"],
                    )
                    if key in seen_keys:
                        continue
                    seen_keys.add(key)

                    relationships.append({
                        "source_table": source_name,
                        "source_column": relationship["source_column"],
                        "target_table": target_name,
                        "target_column": relationship["target_column"],
                        "relationship_type": relationship.get("relationship_type", ""),
                        "description": relationship.get("description", ""),
                    })

                return tables, relationships
        finally:
            engine.dispose()

    # 在线程池中执行同步查询
    tables, relationships = await asyncio.to_thread(_sync_retrieve)

    # 根据问题关键词过滤表
    keywords = _extract_keywords(question)
    if keywords:
        scored_tables = [(table, _score_table(table, keywords)) for table in tables]
        positive = [item for item in scored_tables if item[1] > 0]
        if positive:
            positive.sort(key=lambda item: item[1], reverse=True)
            max_tables = 6
            tables = [item[0] for item in positive[:max_tables]]

            # 过滤关系，只保留相关表的关系
            table_names = {table["table_name"] for table in tables}
            relationships = [
                rel for rel in relationships
                if rel["source_table"] in table_names and rel["target_table"] in table_names
            ]
        else:
            # 有关键词但无任何表匹配 → 返回空 schema，由 guardrails 拒绝
            tables = []
            relationships = []

    schema_context = {
        "tables": tables,
        "relationships": relationships,
    }
    return schema_context
