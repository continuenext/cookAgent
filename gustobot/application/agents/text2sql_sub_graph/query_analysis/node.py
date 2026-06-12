"""
查询意图分析节点
"""
from __future__ import annotations

from typing import Any, Callable, Coroutine, Dict
from gustobot.application.agents.text2sql_sub_graph.states import Text2SQLState
from gustobot.application.agents.text2sql_sub_graph.models import SQLAnalysis
from gustobot.application.agents.text2sql_sub_graph.utils import render_analysis_markdown
from gustobot.application.agents.utils.llm_factory import get_llm
from gustobot.infrastructure.core.logger import get_logger

from ..utils import format_schema_to_text
from .prompts import create_query_analysis_prompt

logger = get_logger(service="text2sql.query_analysis")


def create_query_analysis_node() -> Callable[[Text2SQLState], Coroutine[Any, Any, Dict[str, Any]]]:
    """构建 LangGraph 节点，对用户问题进行结构化查询分析。"""

    prompt = create_query_analysis_prompt()
    llm = get_llm(tags=["text2sql_query_analysis"])
    analysis_chain = prompt | llm.with_structured_output(SQLAnalysis)

    async def analyze(state: Text2SQLState) -> Dict[str, Any]:
        logger.info("-----开始分析查询意图-----")

        question = state.get("question", "")
        schema_context = state.get("schema_context") or {}

        mappings_str = "" # TODO: value_mappings 功能已简化移除，后续如果需要再添加相关信息输入

        schema_text = format_schema_to_text(schema_context)

        inputs = {
            "db_type": state.get("db_type", "MySQL"),
            "schema": schema_text,
            "value_mappings": mappings_str or "无值映射信息",
            "question": question,
        }

        analysis: SQLAnalysis = await analysis_chain.ainvoke(inputs)  # ty:ignore[invalid-assignment]
        analysis_dict = analysis.model_dump()
        rendered_markdown = render_analysis_markdown(analysis, None)

        logger.info(
            "查询分析完成，涉及表：%s", ", ".join(analysis.required_tables or [])
        )

        return {
            "analysis": analysis_dict,
            "analysis_text": rendered_markdown,  # 用户问题的结构化分析
            "steps": ["query_analysis"],
        }

    return analyze
