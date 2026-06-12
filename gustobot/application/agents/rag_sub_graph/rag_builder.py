"""
RAG 子图构建器
基于 LangGraph 构建的 Neo4j GraphRAG 多工具代理工作流。
"""
from pydantic import BaseModel
from typing import Any, Dict, List, Optional, Sequence
from langchain_neo4j import Neo4jGraph
from langgraph.graph import StateGraph, START, END
from langgraph.graph.state import CompiledStateGraph
from gustobot.application.agents.rag_sub_graph.rag_nodes import (
    create_guardrails_node,
    create_planner_node,
    create_cypher_query_node,
    create_predefined_cypher_node,
    create_graphrag_query_node,
    create_tool_selection_node,
    create_summarization_node,
    create_final_answer_node,
)
from gustobot.infrastructure.core.logger import get_logger
from gustobot.application.agents.rag_sub_graph.rag_states import (
    RAGSubGraphState,
    RAGSubGraphInputState,
    RAGSubGraphOutputState,
)
from gustobot.application.agents.rag_sub_graph.tools_list import (
    cypher_query as CypherQuerySchema,
    predefined_cypher as PredefinedCypherSchema,
    graphrag_query as GraphRAGQuerySchema,
)

logger = get_logger(service="rag_builder")

# 内置工具 schema 列表
_TOOL_SCHEMAS: list[type[BaseModel]] = [
    CypherQuerySchema,
    PredefinedCypherSchema,
    GraphRAGQuerySchema,
]


# 条件路由函数
def guardrails_conditional_edge(state: RAGSubGraphState) -> str:
    """Guardrails 之后的条件路由：根据 next_action 跳转到 planner 或 END。"""
    next_action = state.get("next_action", "end")
    if next_action == "planner":
        return "planner"
    return "__end__"
# 子图构建
def build_rag_subgraph(
    graph: Neo4jGraph,
    predefined_cypher_dict: Dict[str, str],
    scope_description: Optional[str] = None,
    default_to_text2cypher: bool = True,
) -> CompiledStateGraph:
    """
    使用 LangGraph 创建 RAG 子图工作流。

    流程: START → guardrails → [planner | END] → tool_selection
              → [cypher_query | graphrag_query | predefined_cypher_query]
              → summarize → final_answer → END
    """

    # 创建节点（均为 async 工厂函数）
    guardrails = create_guardrails_node(
        graph=graph,
        scope_description=scope_description,
    )
    planner = create_planner_node()
    tool_selection = create_tool_selection_node(
        tool_schemas=_TOOL_SCHEMAS,
        default_to_text2cypher=default_to_text2cypher,
    )
    graphrag_query = create_graphrag_query_node()
    cypher_query = create_cypher_query_node()
    predefined_cypher = create_predefined_cypher_node(
        graph=graph, predefined_cypher_dict=predefined_cypher_dict,
    )
    summarize = create_summarization_node()
    final_answer = create_final_answer_node()

    # 构建状态图
    sub_graph_builder = StateGraph(
        RAGSubGraphState,
        input=RAGSubGraphInputState,
        output=RAGSubGraphOutputState,
    )

    # 注册节点
    sub_graph_builder.add_node("guardrails", guardrails)
    sub_graph_builder.add_node("planner", planner)
    sub_graph_builder.add_node("tool_selection", tool_selection)
    sub_graph_builder.add_node("cypher_query", cypher_query)
    sub_graph_builder.add_node("predefined_cypher", predefined_cypher)
    sub_graph_builder.add_node("graphrag_query", graphrag_query)
    sub_graph_builder.add_node("summarize", summarize)
    sub_graph_builder.add_node("final_answer", final_answer)

    # 连接边
    sub_graph_builder.add_edge(START, "guardrails")
    sub_graph_builder.add_conditional_edges(
        "guardrails",
        guardrails_conditional_edge,
        {"planner": "planner", "__end__": END},
    )
    sub_graph_builder.add_edge("planner", "tool_selection")
    # 注意：tool_selection 节点内部通过 Command(goto=Send(...)) 完成动态并行路由，
    # 这里不再额外配置条件边，避免出现双重路由导致的重复执行。
    sub_graph_builder.add_edge("cypher_query", "summarize")
    sub_graph_builder.add_edge("predefined_cypher", "summarize")
    sub_graph_builder.add_edge("graphrag_query", "summarize")
    sub_graph_builder.add_edge("summarize", "final_answer")
    sub_graph_builder.add_edge("final_answer", END)

    return sub_graph_builder.compile()