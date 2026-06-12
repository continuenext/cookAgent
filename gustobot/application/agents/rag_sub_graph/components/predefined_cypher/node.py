from typing import Any, Callable, Coroutine, Dict, List
import re

from langchain_neo4j import Neo4jGraph
from gustobot.application.agents.rag_sub_graph.rag_states import QueryInputState
from gustobot.application.agents.rag_sub_graph.components.predefined_cypher.vector_query_matcher import (
    create_vector_query_matcher,
)
from gustobot.application.agents.rag_sub_graph.components.predefined_cypher.cypher_dict import predefined_cypher_dict
from gustobot.application.agents.rag_sub_graph.components.predefined_cypher.descriptions import QUERY_DESCRIPTIONS, NO_CYPHER_RESULTS
from gustobot.application.agents.utils.llm_factory import get_llm
from gustobot.infrastructure.core.logger import get_logger

logger = get_logger("predefined_cypher_node")


# 兼容历史/别名查询名，统一映射到当前 cypher_dict 键
_QUERY_ALIASES: Dict[str, str] = {
    "dishes_by_type": "dishes_by_category",
    "dishes_with_ingredients": "dishes_with_ingredient",
    "similar_dishes": "similar_dishes_by_ingredients",
}


def _normalize_query_name(query_name: str) -> str:
    return _QUERY_ALIASES.get(query_name, query_name)


def create_predefined_cypher_node(
    graph: Neo4jGraph, predefined_cypher_dict: Dict[str, str]
) -> Callable[
    [QueryInputState], Coroutine[Any, Any, Dict[str, Any]]
]:
    
    matcher = create_vector_query_matcher(predefined_cypher_dict, QUERY_DESCRIPTIONS)

    llm = get_llm(tags=["predefined_cypher_node"])

    async def predefined_cypher(
        state: QueryInputState,
    ) -> Dict[str, Any]:
        logger.info(f"预定义 Cypher 查询节点")
        errors: List[str] = []

        question = state.get("task", "")
        params = state.get("query_parameters", {}) or {}
        query_name = params.get("query") or state.get("query_name", "") # 用于匹配 cypher 模板的查询名称，优先级：输入状态参数 > 直接字段
        query_name = _normalize_query_name(query_name)

        # 如果输入状态没有明确的 query_name，则使用向量匹配器尝试从问题中推断出最相关的预定义查询
        if not query_name:
            matches = matcher.match_query(question, top_k=1)
            if matches:
                query_name = matches[0]["query_name"]
            else:
                errors.append("无法为当前问题匹配到预定义查询。")

        # 从预定义查询字典中获取对应的 Cypher 模板
        statement = predefined_cypher_dict.get(query_name) if query_name else None
        parameters: Dict[str, Any] = params.get("parameters") or {}
        # 如果 statement 存在但参数缺失，则尝试从用户问题中提取参数
        if statement and not parameters:
            parameters = matcher.extract_parameters(question, query_name, llm=llm)

        # 针对常见分类查询补一层兜底，避免“早餐推荐”等短问句丢参
        if query_name in {"dishes_by_category", "dishes_by_category_and_difficulty"} and not parameters.get("category_name"):
            category_candidates = ["早餐", "主食", "甜品", "汤类", "饮料", "荤菜", "素菜", "水产"]
            hit = next((c for c in category_candidates if c in question), None)
            if hit:
                parameters["category_name"] = hit

        # 清洗 category_name 中可能夹带的噪声词（如“早餐推荐”）
        if parameters.get("category_name"):
            category_name = str(parameters.get("category_name", "")).strip()
            for suffix in ["推荐", "菜谱", "菜", "有哪些", "有什么", "怎么做"]:
                category_name = category_name.replace(suffix, "")
            category_name = category_name.strip()
            if category_name:
                parameters["category_name"] = category_name

        # 确保参数类型为字符串键
        parameters = {str(k): v for k, v in parameters.items()}

        records = []
        if not statement:
            errors.append(f"未找到对应的 Cypher 模板：{query_name}")
        else:
            required_params = {name for name in re.findall(r"\$(\w+)", statement)}
            missing = [name for name in required_params if not parameters.get(name)]
            if missing:
                errors.append(f"缺少查询参数: {', '.join(missing)}")
            else:
                records = graph.query(query=statement, params=parameters) or []

        return {
            "cyphers": [
                {
                    "task": state.get("task", ""),
                    "statement": statement or "",
                    "parameters": {
                        "query": query_name,
                        "parameters": parameters,
                    },
                    "errors": errors,
                    "records": records if records else NO_CYPHER_RESULTS,
                    "steps": ["execute_predefined_cypher"],
                }
            ],
            "steps": ["execute_predefined_cypher"],
        }

    return predefined_cypher
