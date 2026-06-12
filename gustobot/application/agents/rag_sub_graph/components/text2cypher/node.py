"""
Text2Cypher 查询节点

将 Cypher 生成、验证、纠正、执行四阶段整合为单个异步节点函数。
接收 QueryInputState，返回格式与 graphrag_query / predefined_cypher 对齐。

内部流程: generate → validate → (correct → validate)* → execute
"""

from typing import Any, Callable, Coroutine, Dict, List

from langchain_core.output_parsers import StrOutputParser
from langchain_neo4j import Neo4jGraph
from langchain_neo4j.chains.graph_qa.cypher_utils import CypherQueryCorrector, Schema
from neo4j.exceptions import CypherSyntaxError

from gustobot.application.agents.rag_sub_graph.rag_states import QueryInputState
from gustobot.application.agents.rag_sub_graph.components.text2cypher.prompts import (
    create_text2cypher_generation_prompt_template,
    create_text2cypher_correction_prompt_template,
)
from gustobot.application.agents.rag_sub_graph.components.text2cypher.recipe_retriever import (
    RecipeCypherRetriever,
)
from gustobot.application.agents.utils.llm_factory import get_llm
from gustobot.application.agents.utils.neo4j_connect import get_neo4j_graph
from gustobot.infrastructure.core.logger import get_logger

logger = get_logger(service="cypher_query_node")

# Cypher 写操作关键字，用于检测生成的 Cypher 是否包含写操作
WRITE_CLAUSES: list[str] = [
    "CREATE",
    "MERGE",
    "DELETE",
    "DETACH DELETE",
    "SET",
    "REMOVE",
    "DROP",
    "CALL",
]

# 查询无结果时的默认返回
NO_CYPHER_RESULTS: list[str] = ["未检索到相关数据"]


def _validate_syntax(graph: Neo4jGraph, statement: str) -> List[str]:
    """通过 EXPLAIN 检查 Cypher 语法。"""
    try:
        graph.query(f"EXPLAIN {statement}")
    except CypherSyntaxError as e:
        return [str(e.message)]
    return []


def _validate_no_writes(statement: str) -> List[str]:
    """检查是否包含写操作关键字。"""
    errors: List[str] = []
    upper = statement.upper()
    for wc in WRITE_CLAUSES:
        if wc in upper:
            errors.append(f"Cypher 包含写操作: {wc}")
    return errors


def _correct_relationship_direction(graph: Neo4jGraph, statement: str) -> str:
    """利用图 schema 自动修正关系方向。"""
    corrector_schema = [
        Schema(el["start"], el["type"], el["end"])
        for el in graph.structured_schema.get("relationships", [])
    ]
    corrector = CypherQueryCorrector(corrector_schema)
    return corrector(statement)



def create_cypher_query_node(
    max_attempts: int = 3,
) -> Callable[[QueryInputState], Coroutine[Any, Any, Dict[str, Any]]]:
    """
    创建 Cypher 查询节点。

    无需外部参数，内部通过工厂函数获取 Neo4jGraph 和 LLM。
    接收 QueryInputState，返回 ``{"cyphers": [...], "steps": [...]}``。
    """
    logger.info("创建 Cypher 查询节点")

    graph = get_neo4j_graph()
    llm = get_llm(tags=["cypher_query_node"])
    retriever = RecipeCypherRetriever()

    # 生成链
    generation_prompt = create_text2cypher_generation_prompt_template()
    generation_chain = generation_prompt | llm | StrOutputParser()

    # 纠正链
    correction_prompt = create_text2cypher_correction_prompt_template()
    correction_chain = correction_prompt | llm | StrOutputParser()

    async def cypher_query(state: QueryInputState) -> Dict[str, Any]:
        task = state.get("task", "")
        logger.info(f"Cypher 查询节点收到任务: {task}")

        statement = ""
        errors: List[str] = []
        records: List[Dict[str, Any]] = []
        step_trace: List[str] = []

        # 1. 生成 Cypher（检索相关 few-shot 示例）
        try:
            fewshot_examples = retriever.get_examples(query=task, k=5)
            statement = await generation_chain.ainvoke({
                "question": task,
                "fewshot_examples": fewshot_examples,
                "schema": graph.schema,
            })
            step_trace.append("generate_cypher")
            logger.info(f"生成 Cypher: {statement[:200]}")
        except Exception as exc:
            logger.error(f"Cypher 生成失败: {exc}")
            errors.append(f"Cypher 生成失败: {exc}")
            return _build_result(task, statement, state, errors, records, step_trace)

        # 2. 验证 + 纠正循环
        for attempt in range(1, max_attempts + 1):
            current_errors: List[str] = []

            # 语法检查
            current_errors.extend(_validate_syntax(graph, statement))

            # 写保护
            current_errors.extend(_validate_no_writes(statement))

            # 关系方向修正（无论有无错误都执行）
            statement = _correct_relationship_direction(graph, statement)

            step_trace.append(f"validate_cypher(attempt={attempt})")

            if not current_errors:
                break  # 验证通过，进入执行

            if attempt < max_attempts:
                # 尝试纠正
                try:
                    statement = await correction_chain.ainvoke({
                        "question": task,
                        "errors": current_errors,
                        "cypher": statement,
                        "schema": graph.schema,
                    })
                    step_trace.append("correct_cypher")
                    logger.info(f"纠正 Cypher (attempt {attempt}): {statement[:200]}")
                except Exception as exc:
                    logger.error(f"Cypher 纠正失败: {exc}")
                    errors.extend(current_errors)
                    errors.append(f"Cypher 纠正失败: {exc}")
                    return _build_result(task, statement, state, errors, records, step_trace)
            else:
                # 最后一次尝试仍有错误
                errors.extend(current_errors)
                logger.warning(f"Cypher 验证在 {max_attempts} 次尝试后仍有错误")
                return _build_result(task, statement, state, errors, records, step_trace)

        # 3. 执行
        try:
            records = graph.query(statement)
            step_trace.append("execute_cypher")
            logger.info(f"Cypher 执行成功, 返回 {len(records)} 条记录")
        except Exception as exc:
            logger.error(f"Cypher 执行失败: {exc}")
            errors.append(f"Cypher 执行失败: {exc}")

        return _build_result(task, statement, state, errors, records, step_trace)

    return cypher_query


def _build_result(
    task: str,
    statement: str,
    state: QueryInputState,
    errors: List[str],
    records: List[Dict[str, Any]],
    step_trace: List[str],
) -> Dict[str, Any]:
    """构造标准输出字典，与 graphrag_query / predefined_cypher 风格对齐。"""
    return {
        "cyphers": [
            {
                "task": task,
                "statement": statement,
                "parameters": state.get("query_parameters", {}),
                "errors": errors,
                "records": records if records else NO_CYPHER_RESULTS,
                "steps": step_trace,
            }
        ],
        "steps": ["cypher_query"],
    }
