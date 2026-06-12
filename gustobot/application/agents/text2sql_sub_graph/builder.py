"""
Text2SQL 子图构建器
基于 LangGraph 构建的 Text2SQL 工作流。

流程: START → guardrails → [条件路由: proceed/end]
      → query_analysis → sql_generation → sql_validation
      → [条件路由: retry/execute] → sql_execution → format_answer → END
"""
from typing import Optional

from langgraph.graph import StateGraph, START, END
from langgraph.graph.state import CompiledStateGraph

from gustobot.application.agents.text2sql_sub_graph.guardrails import create_guardrails_node
from gustobot.application.agents.text2sql_sub_graph.query_analysis import create_query_analysis_node
from gustobot.application.agents.text2sql_sub_graph.sql_generation import create_sql_generation_node
from gustobot.application.agents.text2sql_sub_graph.sql_validation import create_sql_validation_node
from gustobot.application.agents.text2sql_sub_graph.sql_execution import create_sql_execution_node
from gustobot.application.agents.text2sql_sub_graph.format_answer import create_answer_formatter_node
from gustobot.application.agents.text2sql_sub_graph.states import (
    Text2SQLState,
    Text2SQLInputState,
    Text2SQLOutputState,
)
from gustobot.infrastructure.core.logger import get_logger

logger = get_logger(service="text2sql_builder")


def _route_after_guardrails(state: Text2SQLState) -> str:
    """guardrails 后条件路由：proceed → 继续查询分析，end → 直接格式化输出。"""
    return "format_answer" if state.get("next_action") == "end" else "query_analysis"


def _should_retry_or_execute(state: Text2SQLState) -> str:
    """验证后条件路由：通过 → 执行，失败 → 重试或跳到执行（会被执行节点短路）。"""
    if state.get("is_valid", False):
        return "sql_execution"
    if state.get("retry_count", 0) < state.get("max_retries", 3):
        return "sql_generation"
    return "sql_execution"


def build_text2sql_subgraph(
    connection_string: Optional[str] = None,
    db_type: str = "MySQL",
) -> CompiledStateGraph:
    """
    构建 Text2SQL 子图工作流。

    Parameters
    ----------
    connection_string : Optional[str]
        数据库连接字符串，为 None 时使用 settings 默认配置。
    db_type : str
        数据库类型，默认 "MySQL"。
    """
    logger.info("构建 Text2SQL 子图")

    # 创建各节点（LLM 由各节点内部通过 get_llm() 获取）
    guardrails = create_guardrails_node()
    query_analysis = create_query_analysis_node()
    sql_generation = create_sql_generation_node(db_type=db_type)
    sql_validation = create_sql_validation_node(db_type=db_type)
    sql_execution = create_sql_execution_node(connection_string=connection_string)
    format_answer = create_answer_formatter_node()

    # 构建状态图
    builder = StateGraph(
        Text2SQLState,
        input=Text2SQLInputState,
        output=Text2SQLOutputState,
    )

    # 注册节点
    builder.add_node("guardrails", guardrails)
    builder.add_node("query_analysis", query_analysis)
    builder.add_node("sql_generation", sql_generation)
    builder.add_node("sql_validation", sql_validation)
    builder.add_node("sql_execution", sql_execution)
    builder.add_node("format_answer", format_answer)

    # 连接边
    builder.add_edge(START, "guardrails")

    # guardrails 条件路由：proceed → 查询分析，end → 直接格式化
    builder.add_conditional_edges(
        "guardrails",
        _route_after_guardrails,
        {
            "query_analysis": "query_analysis",
            "format_answer": "format_answer",
        },
    )

    builder.add_edge("query_analysis", "sql_generation")
    builder.add_edge("sql_generation", "sql_validation")

    # 验证后条件路由：通过→执行，失败→重试或执行（短路）
    builder.add_conditional_edges(
        "sql_validation",
        _should_retry_or_execute,
        {
            "sql_execution": "sql_execution",
            "sql_generation": "sql_generation",
        },
    )

    builder.add_edge("sql_execution", "format_answer")
    builder.add_edge("format_answer", END)

    return builder.compile()
