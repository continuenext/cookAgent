"""
RAG 子图节点实现
包含：Guardrails 范围判定、Planner 任务拆解、Tool Selection 工具路由、
      GraphRAG 检索、Cypher 查询、预定义 Cypher、文档汇总、最终答案生成。
"""
from pydantic import BaseModel
from langchain.output_parsers import PydanticToolsParser
from langchain.prompts import ChatPromptTemplate
from langchain_neo4j import Neo4jGraph
from typing import Any, Dict, List, Callable, Optional, Coroutine, Sequence, Literal, Set
from langchain_openai import ChatOpenAI
from langgraph.types import Command, Send
from gustobot.application.agents.lg_models import GuardrailsOutput
from gustobot.application.agents.rag_sub_graph.prompts.rag_prompts import *
from gustobot.config.settings import settings
from gustobot.infrastructure.core.logger import get_logger
from gustobot.application.agents.utils.llm_factory import get_llm
from gustobot.application.agents.utils.neo4j_connect import graph_schema_to_nl
from gustobot.infrastructure.core.context_manager import count_tokens, compress_schema, compress_retrieval_results
from gustobot.application.agents.rag_sub_graph.rag_states import *
from gustobot.application.agents.rag_sub_graph.models.models import Task, PlannerOutput
from gustobot.application.agents.rag_sub_graph.components.predefined_cypher.node import create_predefined_cypher_node
from gustobot.application.agents.rag_sub_graph.components.graph_rag.node import create_graphrag_query_node
from gustobot.application.agents.rag_sub_graph.components.text2cypher.node import create_cypher_query_node

logger = get_logger(service="rag_sub_graph_nodes")


def _should_force_split_recommend_and_steps(question: str) -> bool:
    """识别“选菜/推荐 + 做法步骤”复合意图，触发强制拆分。"""
    if not question:
        return False

    recommend_markers = [
        "做什么", "推荐", "有什么", "能做", "选什么", "安排", "搭配", "适合做", "哪些菜",
    ]
    step_markers = [
        "怎么做", "做法", "步骤", "如何做", "怎么烹饪", "详细做", "具体做",
    ]
    return any(m in question for m in recommend_markers) and any(m in question for m in step_markers)


def _build_forced_tasks_for_compound_question(question: str) -> list[Task]:
    """将复合问题拆分为“先推荐菜，再给做法”两个子任务。"""
    return [
        Task(
            question=f"基于用户现有食材，推荐可制作的菜品：{question}",
            parent_task=question,
        ),
        Task(
            question="针对推荐出的菜品，给出清晰的做法与关键步骤说明",
            parent_task=question,
        ),
    ]

def create_guardrails_node(
    graph: Neo4jGraph,
    scope_description: Optional[str] = None,
) -> Callable[[RAGSubGraphState], Coroutine[Any, Any, Dict[str, Any]]]:
    """
    创建 Guardrails 节点，负责判断问题是否在知识图谱范围内。

    返回字段：next_action, summary, steps
    """
    logger.info("创建 Guardrails 节点")

    llm = get_llm(tags=["rag_sub_graph_guardrails_node"])

    scope_context = f"参考此范围描述来决策:\n{scope_description}" if scope_description else ""
    graph_nl_raw = graph_schema_to_nl(graph) if graph else ""

    async def guardrails(state: RAGSubGraphState) -> Dict[str, Any]:
        logger.info("Guardrails 节点开始执行")
        heuristics_keywords = [
            "菜", "菜谱", "食材", "烹饪", "做法", "步骤", "口味", "炒",
            "煮", "炖", "蒸", "统计", "多少", "用量", "营养", "功效",
        ]

        question = state.get("question", "")
        logger.info(f"Guardrails 收到问题: {question}")
        # 关键词匹配
        if any(keyword in question for keyword in heuristics_keywords) or "?" in question or "？" in question:
            logger.info("Guardrails 前置规则命中菜谱/统计关键词，直接进入 planner。", extra={"question": question})
            return {"next_action": "planner", "steps": ["guardrails"]}

        # 根据用户问题动态过滤 schema，只保留相关段落
        filtered_schema = compress_schema(graph_nl_raw, question, max_tokens=settings.CONTEXT_SCHEMA_MAX_TOKENS)
        graph_context = f"\n参考图表结构来回答:\n{filtered_schema}" if filtered_schema else ""
        user_prompt = scope_context + graph_context + f"\nQuestion: {question}"

        guardrails_prompt = ChatPromptTemplate.from_messages(
            [
                ("system", GUARDRAILS_SYSTEM_PROMPT),
                ("human", user_prompt),
            ]
        )
        guardrails_chain = guardrails_prompt | llm.with_structured_output(GuardrailsOutput)

        # LLM 决策
        try:
            raw_guardrails = await guardrails_chain.ainvoke({"question": question})
        except Exception as exc:
            logger.warning("Guardrails LLM 调用失败，回退到 planner: %s", exc)
            return {"next_action": "planner", "steps": ["guardrails"]}

        # 兼容性处理：with_structured_output 可能返回 None
        if raw_guardrails is None:
            logger.warning("Guardrails 输出为空，默认放行到 planner")
            guardrails_output = GuardrailsOutput(decision="proceed")
        elif isinstance(raw_guardrails, GuardrailsOutput):
            guardrails_output = raw_guardrails
        else:
            guardrails_output = GuardrailsOutput.model_validate(raw_guardrails)

        decision = guardrails_output.decision
        summary = None

        if decision == "end":
            summary = "厨友您好～抱歉哦，这个问题不太属于我们的菜谱范围呢，我主要帮您解答菜谱和烹饪方面的问题～😊"

        # decision == "proceed" 映射到 next_action == "planner"
        next_action = "end" if decision == "end" else "planner"

        result: Dict[str, Any] = {"next_action": next_action, "steps": ["guardrails"]}
        if summary is not None:
            result["summary"] = summary
        logger.info(f"Guardrails 决策: next_action={next_action}")
        return result

    return guardrails


def create_planner_node() -> Callable[[RAGSubGraphState], Coroutine[Any, Any, Dict[str, Any]]]:
    """
    创建 Planner 节点，将用户问题拆解为多个独立子任务。

    返回字段：tasks, next_action, steps
    """
    logger.info("创建 Planner 节点")
    rule = """规则:
        * 确保任务不会返回重复或相似的信息。
        * 确保任务不依赖于从其他任务收集的信息！
        * 相互依赖的任务应该合并为单个问题。
        * 返回相同信息的任务应该合并为单个问题。

        问题: {question}
    """
    prompt = ChatPromptTemplate.from_messages(
        [("system", PLANNER_SYSTEM_PROMPT), ("human", rule)]
    )

    async def planner(state: RAGSubGraphState) -> Dict[str, Any]:
        logger.info("Planner 节点开始执行")
        llm = get_llm(tags=["rag_sub_graph_planner_node"])
        question = state.get("question", "")

        # 对“推荐菜 + 做法”复合问句做强制拆分，避免被合并成一个子任务
        if _should_force_split_recommend_and_steps(question):
            tasks = _build_forced_tasks_for_compound_question(question)
            logger.info("Planner 命中复合问句规则，强制拆分为 %d 个子任务", len(tasks))
            for i, task in enumerate(tasks):
                logger.info(f"Sub Task[{i+1}]: {task.question}")
            return {
                "tasks": tasks,
                "next_action": "tool_selection",
                "steps": ["planner"],
            }

        try:
            planner_chain = prompt | llm.with_structured_output(PlannerOutput)
            response = await planner_chain.ainvoke({"question": question})

            # 兼容性处理：with_structured_output 可能返回 None
            if response is None:
                logger.warning("Guardrails 输出为空，默认放行到 planner")
                planner_output = PlannerOutput(tasks=[Task(question=question, parent_task=question)])
            elif isinstance(response, PlannerOutput):
                planner_output = response
            else:
                planner_output = PlannerOutput.model_validate(response)
        except Exception as e:
            logger.info(f"Planner LLM 调用失败，回退到单任务: {e}")
            planner_output = PlannerOutput(tasks=[Task(question=question, parent_task=question)])

        tasks = planner_output.tasks or [
            Task(question=question, parent_task=question)
        ]

        logger.info(f"Planner 输出 {len(tasks)} 个子任务")
        for i, task in enumerate(tasks):
            logger.info(f"Sub Task[{i+1}]: {task.question}")

        return {
            "tasks": tasks,
            "next_action": "tool_selection",
            "steps": ["planner"],
        }

    return planner


def create_tool_selection_node(
    tool_schemas: List[type[BaseModel]],
    default_to_text2cypher: bool = True,
) -> Callable[[RAGSubGraphState], Coroutine[Any, Any, Dict[str, Any]]]:
    """
    创建 Tool Selection 节点，遍历 planner 拆解的子任务，
    为每个子任务选择查询工具并通过 Send 并行分发。

    返回字段：next_action, steps
    """
    logger.info("创建 Tool Selection 节点")
    DESCRIPTIVE_KEYWORDS = [
        "口味", "特色", "风味", "营养", "功效", "健康", "介绍", "概况", "食材", "材料",
    ]
    prompts = ChatPromptTemplate.from_messages(
        [
            ("system", TOOL_SELECTION_SYSTEM_PROMPT),
            ("human", "根据问题和上下文选择最合适的工具来执行任务。\nQuestion: {question}"),
        ]
    )
    available_tools: Set[str] = {
        schema.model_json_schema().get("title", "") for schema in tool_schemas
    }

    recommendation_keywords = ["做什么", "推荐", "有什么", "能做", "选什么", "安排", "搭配", "哪些菜"]
    inventory_keywords = ["我有", "现有", "手头", "冰箱", "食材", "材料", "原料"]

    async def tool_selection(state: RAGSubGraphState) -> Command[Literal["cypher_query", "predefined_cypher", "graphrag_query", "summarize"]]:
        logger.info("Tool Selection 节点开始执行")
        tasks = state.get("tasks", [])
        question = state.get("question", "")

        # 如果 planner 没有拆出子任务，以原始问题作为单任务
        if not tasks:
            tasks = [Task(question=question, parent_task=question)]

        sends: List[Send] = []
        llm = get_llm(tags=["rag_sub_graph_tool_selection_node"])
        tool_selection_chain = prompts | llm.bind_tools(tool_schemas) | PydanticToolsParser(tools=tool_schemas, first_tool_only=True)

        for task in tasks:
            task_question = task.question
            logger.info(f"为子任务选择工具: {task_question}")

            # 手头食材求推荐场景优先走 GraphRAG，避免误选 predefined_cypher 模板
            if any(kw in task_question for kw in recommendation_keywords) and any(
                kw in task_question for kw in inventory_keywords
            ):
                logger.info(f"子任务命中食材推荐场景，优先使用 GraphRAG: {task_question}")
                sends.append(Send("graphrag_query", {
                    "task": task_question,
                    "query_name": "graphrag_query",
                    "query_parameters": {"query": task_question},
                    "steps": ["tool_selection"],
                }))
                continue

            # 关键词路由：描述性需求 → GraphRAG
            if any(kw in task_question for kw in DESCRIPTIVE_KEYWORDS):
                logger.info(f"子任务命中描述类关键词，使用 GraphRAG: {task_question}")
                sends.append(Send("graphrag_query", {
                    "task": task_question,
                    "query_name": "graphrag_query",
                    "query_parameters": {"query": task_question},
                    "steps": ["tool_selection"],
                }))
                continue

            # LLM 工具选择
            try:
                tool_selection_output = await tool_selection_chain.ainvoke({"question": task_question})
                if tool_selection_output is not None:
                    tool_name: str = tool_selection_output.model_json_schema().get("title", "")
                    tool_args: Dict[str, Any] = tool_selection_output.model_dump()
                    if tool_name in available_tools:
                        logger.info(f"LLM 为子任务选择工具: {tool_name}")
                        sends.append(Send(tool_name, {
                            "task": task_question,
                            "query_name": tool_name,
                            "query_parameters": tool_args,
                            "steps": ["tool_selection"],
                        }))
                        continue
            except Exception as e:
                logger.warning(f"Tool Selection LLM 调用失败: {e}")

            # 兜底：默认路由到 cypher_query
            if default_to_text2cypher:
                logger.info(f"子任务无法匹配工具，默认使用 cypher_query: {task_question}")
                sends.append(Send("cypher_query", {
                    "task": task_question,
                    "query_name": "cypher_query",
                    "query_parameters": {},
                    "steps": ["tool_selection"],
                }))
            else:
                logger.info(f"子任务无法匹配工具，跳过: {task_question}")

        if not sends:
            logger.info("所有子任务均无法路由，返回兜底摘要")
            return Command(
                update={
                    "summary": "抱歉，我暂时无法理解您的问题，请尝试换个方式描述～",
                    "steps": ["tool_selection_fallback"],
                },
                goto="summarize",
            )

        logger.info(f"Tool Selection 共分发 {len(sends)} 个子任务查询")
        return Command(goto=sends)

    return tool_selection


def create_summarization_node() -> Callable[[RAGSubGraphState], Coroutine[Any, Any, Dict[str, Any]]]:
    """
    创建文档汇总节点，将 Cypher 查询结果汇总为自然语言摘要。

    返回字段：summary, steps
    """
    logger.info("创建 Summarization 节点")

    summarize_prompt = ChatPromptTemplate.from_messages(
        [
            ("system", SUMMARIZE_SYSTEM_PROMPT),
            ("human", "用户问题: {question}\n\n查询结果:\n{formatted_results}"),
        ]
    )

    def _format_rows(rows: List[Any]) -> str:
        """格式化结果行，自动识别烹饪步骤和食材列表。
        兼容 Dict 行和纯字符串哨兵（如 NO_CYPHER_RESULTS）。
        """
        if not rows:
            return ""

        # 过滤掉非 dict 的哨兵字符串（如 "未检索到相关数据"）
        dict_rows = [r for r in rows if isinstance(r, dict)]
        str_rows = [r for r in rows if isinstance(r, str)]

        if not dict_rows:
            # 全部是字符串哨兵，直接拼接返回
            return "\n".join(str_rows)

        if len(dict_rows) == 1:
            row = dict_rows[0]
            if len(row) == 1:
                key, value = next(iter(row.items()))
                return f"{key}：{value}"
            return "; ".join(f"{key}：{value}" for key, value in row.items())

        is_cooking_steps = all(
            "步骤序号" in row and "步骤说明" in row for row in dict_rows
        )
        is_ingredients = all(
            "食材" in row and "用量" in row for row in dict_rows
        )

        lines: List[str] = []
        for idx, row in enumerate(dict_rows, 1):
            if is_cooking_steps:
                lines.append(f"{row.get('步骤序号', idx)}. {row.get('步骤说明', '')}")
            elif is_ingredients:
                marker = "★ " if "MAIN" in row.get("关系类型", "") else "  "
                lines.append(f"{marker}{row.get('食材', '')}：{row.get('用量', '')}")
            else:
                row_desc = ", ".join(f"{k}：{v}" for k, v in row.items())
                lines.append(f"{idx}. {row_desc}")
        return "\n".join(lines)

    async def summarize(state: RAGSubGraphState) -> Dict[str, Any]:
        logger.info("汇总检索到的文档")
        question = state.get("question", "")
        cyphers = state.get("cyphers", [])
        tasks = state.get("tasks", [])
        existing_summary = state.get("summary", "")

        # 只有在无查询结果时才透传预填 summary（tool_selection 兜底场景）
        if existing_summary and not cyphers:
            logger.info("无查询结果且有预填 summary（tool_selection 兜底），直接透传")
            return {"summary": existing_summary, "steps": ["summarize"]}

        # 解析 cypher 结果为结构化文本
        sections: List[str] = []

        # 如果有预生成的摘要（如 GraphRAG），作为额外上下文纳入
        if existing_summary:
            sections.append(existing_summary)

        for cypher in cyphers:
            data: Dict[str, Any] = cypher if isinstance(cypher, dict) else {}

            task_label = data.get("task", "")
            records = data.get("records", [])
            errors = data.get("errors") or []

            if errors:
                sections.append(f"[{task_label}] 查询出错：{'；'.join(errors)}" if task_label else f"查询出错：{'；'.join(errors)}")
                continue
            if not records:
                continue

            if isinstance(records, dict):
                result_text = records.get("result", "")
                if isinstance(result_text, str) and result_text.strip():
                    sections.append(result_text.strip())
                answer = records.get("answer")
                if answer:
                    sections.append(f"{task_label}：{answer}".strip() if task_label else str(answer))
                rows = records.get("rows")
                if isinstance(rows, list) and rows:
                    formatted = _format_rows(rows)
                    if formatted:
                        sections.append(f"{task_label}：\n{formatted}".rstrip() if task_label else formatted)
            elif isinstance(records, list):
                formatted = _format_rows(records)
                if formatted:
                    sections.append(f"{task_label}：\n{formatted}".rstrip() if task_label else formatted)
            else:
                sections.append(str(records))

        formatted_results = "\n\n".join(sections) if sections else "未检索到相关数据。"

        # 渐进式摘要压缩：超过 token 阈值时，逐块 LLM 摘要而非截断
        formatted_results = await compress_retrieval_results(
            formatted_results, max_tokens=settings.CONTEXT_RETRIEVAL_MAX_TOKENS,
        )

        # LLM 汇总
        try:
            llm = get_llm(tags=["rag_sub_graph_summarize_node"])
            chain = summarize_prompt | llm
            response = await chain.ainvoke({"question": question, "formatted_results": formatted_results})
            summary = response.content if hasattr(response, "content") else str(response)
        except Exception as e:
            logger.warning(f"Summarization LLM 调用失败: {e}")
            summary = formatted_results

        return {"summary": summary, "steps": ["summarize"]}

    return summarize


def create_final_answer_node() -> Callable[[RAGSubGraphState], Coroutine[Any, Any, Dict[str, Any]]]:
    """
    创建最终答案节点，使用 LLM 润色摘要并组装历史记录。

    返回字段：summary(answer), steps, history
    """
    logger.info("创建 Final Answer 节点")

    final_prompt = ChatPromptTemplate.from_messages(
        [
            ("system", FINAL_ANSWER_SYSTEM_PROMPT),
            ("human", "用户问题: {question}\n\n整理后的信息:\n{summary}"),
        ]
    )

    async def generate_final_answer(state: RAGSubGraphState) -> Dict[str, Any]:
        logger.info("生成最终答案")
        raw_summary = state.get("summary", "")
        question = state.get("question", "")

        # LLM 润色
        try:
            llm = get_llm(tags=["rag_sub_graph_final_answer_node"])
            chain = final_prompt | llm
            response = await chain.ainvoke({"question": question, "summary": raw_summary})
            answer = response.content if hasattr(response, "content") else str(response)
        except Exception as e:
            logger.warning(f"Final Answer LLM 调用失败，使用原始摘要: {e}")
            answer = raw_summary

        history_record = {
            "question": question,
            "answer": answer,
            "cyphers": [
                {
                    "task": c.get("task", "") if isinstance(c, dict) else "",
                    "statement": c.get("statement", "") if isinstance(c, dict) else "",
                    "records": c.get("records", []) if isinstance(c, dict) else [],
                }
                for c in state.get("cyphers", [])
            ],
        }

        return {
            "answer": answer,
            "steps": ["final_answer"],
            "history": [history_record],
        }

    return generate_final_answer