"""
答案格式化节点
"""
from __future__ import annotations

import json
from typing import Any, Callable, Coroutine, Dict, List
from langchain_core.messages import HumanMessage, SystemMessage

from gustobot.application.agents.utils.llm_factory import get_llm
from gustobot.application.agents.text2sql_sub_graph.states import Text2SQLState
from gustobot.infrastructure.core.logger import get_logger

logger = get_logger(service="text2sql.answer_formatter")


def create_answer_formatter_node() -> Callable[[Text2SQLState], Coroutine[Any, Any, Dict[str, Any]]]:
    """构建 LangGraph 节点，将查询结果组装为用户可读的最终回答。"""

    async def format_answer(state: Text2SQLState) -> Dict[str, Any]:
        logger.info("-----格式化最终回答-----")

        execution_error = state.get("execution_error")
        sql_statement = state.get("sql_statement", "")
        results = state.get("execution_results") or []
        analysis_text = state.get("analysis_text") or ""
        question = state.get("question", "")

        if execution_error:
            answer = f"抱歉，执行 SQL 时出现错误：{execution_error}"
        else:
            # 先构造可用于生成回答的结构化上下文
            preview = json.dumps(results[:10], ensure_ascii=False, indent=2) if results else "[]"
            nlg_system = (
                "你是菜谱数据分析助手。请基于 SQL 查询结果，直接回答用户问题。"
                "要求：\n"
                "1) 优先给出明确结论；\n"
                "2) 包含关键数字或排序信息；\n"
                "3) 不要输出 SQL，不要输出 Markdown 标题，不要输出代码块；\n"
                "4) 如果结果为空，明确说明未查到符合条件的数据。"
            )
            nlg_user = (
                f"用户问题：{question or '（未提供）'}\n\n"
                f"查询分析：{analysis_text or '无'}\n\n"
                f"SQL（仅供参考）：{sql_statement or '无'}\n\n"
                f"查询结果（JSON，最多10条）：\n{preview}"
            )

            answer = ""
            try:
                model = get_llm(tags=["text2sql_answer"]) 
                response = await model.ainvoke([
                    SystemMessage(content=nlg_system),
                    HumanMessage(content=nlg_user),
                ])
                answer = str(response.content).strip()
            except Exception as exc:
                logger.warning("Text2SQL 自然语言生成失败，使用兜底模板: %s", exc)

            # 兜底：确保始终给出可读回答
            if not answer:
                if not results:
                    answer = "未查询到符合条件的数据。"
                else:
                    answer = f"查询已完成，共返回 {len(results)} 条记录。"

        return {
            "answer": answer,
            "sql_statement": sql_statement,
            "execution_results": results,
            "steps": ["format_answer"],
        }

    return format_answer
