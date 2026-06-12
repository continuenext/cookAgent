"""
SQL 生成节点
"""
from __future__ import annotations

from typing import Any, Callable, Coroutine, Dict, List

from langchain_core.output_parsers import StrOutputParser
from gustobot.application.agents.text2sql_sub_graph.models import SQLAnalysis
from gustobot.application.agents.text2sql_sub_graph.states import Text2SQLState
from gustobot.application.agents.text2sql_sub_graph.utils import render_analysis_markdown
from gustobot.application.agents.utils.llm_factory import get_llm
from gustobot.infrastructure.core.logger import get_logger
from gustobot.infrastructure.core.context_manager import compress_sql_schema
from .prompts import create_sql_generation_prompt
from ..utils import format_schema_to_text

logger = get_logger(service="text2sql.sql_generation")


def create_sql_generation_node(
    db_type: str = "MySQL",
) -> Callable[[Text2SQLState], Coroutine[Any, Any, Dict[str, Any]]]:
    """构建 LangGraph 节点，根据查询分析结果生成 SQL 语句。"""
    prompt = create_sql_generation_prompt()
    llm = get_llm(tags=["text2sql_sql_generation"])

    sql_chain = prompt | llm | StrOutputParser()

    async def generate_sql(state: Text2SQLState) -> Dict[str, Any]:
        logger.info("-----开始生成 SQL 语句-----")

        schema_context = state.get("schema_context") or {}
        analysis_dict = state.get("analysis") or {}
        analysis_text = state.get("analysis_text") or ""

        if not schema_context:
            logger.warning("缺少 Schema 信息，无法生成 SQL")
            return {
                "sql_statement": "",
                "steps": ["sql_generation_failed_no_schema"],
            }

        # 根据用户问题裁剪 schema（列级过滤，减少 token 消耗）
        question = state.get("question", "")
        trimmed_schema = compress_sql_schema(schema_context, question)
        schema_text = format_schema_to_text(trimmed_schema)
        # TODO value_mappings 功能已简化移除
        mappings_str = ""
        analysis_summary = analysis_text or render_analysis_markdown(SQLAnalysis(**analysis_dict))

        inputs = {
            "db_type": db_type,
            "schema": schema_text,
            "value_mappings": mappings_str or "无值映射信息",
            "analysis_summary": analysis_summary or "无分析信息",
            "question": question,
        }

        # 如果是重试，将上一次的验证错误和 SQL 语句注入 prompt，帮助 LLM 修正
        validation_errors = state.get("validation_errors") or []
        prev_sql = state.get("sql_statement") or ""
        if validation_errors and prev_sql:
            retry_hint = (
                f"\n\n## 上一次生成的 SQL（验证失败）\n```sql\n{prev_sql}\n```\n"
                f"## 验证错误\n" + "\n".join(f"- {e}" for e in validation_errors)
                + "\n\n请根据上述错误修正 SQL，确保只使用 Schema 中存在的表名和列名。"
            )
            inputs["question"] = question + retry_hint

        try:
            sql_raw = await sql_chain.ainvoke(inputs)
            sql_statement = _clean_sql_statement(sql_raw)
            logger.info("SQL 生成完成")
            return {
                "sql_statement": sql_statement,
                "steps": ["sql_generation"],
            }
        except Exception as exc:
            logger.exception("SQL 生成失败: %s", exc)
            return {
                "sql_statement": "",
                "steps": ["sql_generation_failed"],
            }

    return generate_sql


def _clean_sql_statement(sql: str) -> str:
    """移除 Markdown 代码围栏并规范化空白。"""
    cleaned = sql.replace("```sql", "").replace("```", "").strip()
    lines = [line.strip() for line in cleaned.splitlines() if line.strip()]
    return "\n".join(lines)


