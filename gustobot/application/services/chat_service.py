"""
对话服务层

封装 LangGraph 工作流调用，为路由层提供业务逻辑入口。
"""
from __future__ import annotations

import asyncio
from typing import Any, AsyncGenerator, Dict

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableConfig

from gustobot.application.agents import lg_builder
from gustobot.application.services.session_service import touch_session
from gustobot.infrastructure.core.logger import get_logger

logger = get_logger(service="chat_service")


async def chat(
    message: str,
    session_id: str,
    *,
    user_id: str | None = None,
    image_path: str | None = None,
    file_path: str | None = None,
) -> Dict[str, Any]:
    """
    调用 LangGraph 主图完成一轮对话。

    返回字典包含: answer, router_type, steps, sources, documents,
                  sql_statement, execution_results 等可选字段。
    """
    # 构建 RunnableConfig，传递 session_id 以及可选的 image_path 和 file_path
    configurable: Dict[str, Any] = {"thread_id": session_id}
    if user_id:
        configurable["user_id"] = user_id
    if image_path:
        configurable["image_path"] = image_path
    if file_path:
        configurable["file_path"] = file_path

    run_config = RunnableConfig(configurable=configurable)
    input_state = {"messages": [HumanMessage(content=message)]}

    logger.info("开始对话调用, session=%s, user=%s, message=%s", session_id, user_id, message[:80])

    if lg_builder.graph is None:
        raise RuntimeError("LangGraph 主图尚未初始化，请等待服务启动完成")

    # 更新会话元数据
    await touch_session(session_id, user_id=user_id)

    result = await lg_builder.graph.ainvoke(input_state, config=run_config)

    # 从结果 dict 提取字段（LangGraph ainvoke 返回 dict）
    answer = result.get("answer", "") or ""
    router = result.get("router", None)
    router_type = router.type if router else "unknown"
    documents = result.get("documents", []) or []
    sources = result.get("sources", []) or []

    # 如果 answer 为空，尝试从最后一条 AI 消息中提取
    if not answer:
        messages = result.get("messages", [])
        for msg in reversed(messages):
            if isinstance(msg, AIMessage) and msg.content:
                answer = str(msg.content)
                break

    return {
        "answer": answer,
        "router_type": router_type,
        "documents": documents if documents else None,
        "sources": sources,
        "steps": [],
    }


async def chat_stream(
    message: str,
    session_id: str,
    *,
    user_id: str | None = None,
    image_path: str | None = None,
    file_path: str | None = None,
) -> AsyncGenerator[Dict[str, Any], None]:
    """
    流式调用 LangGraph 主图。

    以 SSE 格式逐步产出 Dict，由路由层序列化为 JSON 发送。
    chunk 格式: {"type": "metadata"|"message"|"done"|"error", ...}
    """
    configurable: Dict[str, Any] = {"thread_id": session_id}
    if user_id:
        configurable["user_id"] = user_id
    if image_path:
        configurable["image_path"] = image_path
    if file_path:
        configurable["file_path"] = file_path

    run_config = RunnableConfig(configurable=configurable)
    input_state = {"messages": [HumanMessage(content=message)]}

    logger.info("开始流式对话, session=%s, user=%s", session_id, user_id)

    if lg_builder.graph is None:
        yield {"type": "error", "content": "LangGraph 主图尚未初始化", "session_id": session_id}
        return

    await touch_session(session_id, user_id=user_id)

    # 发送初始状态
    yield {"type": "metadata", "metadata": {"status": "processing"}, "session_id": session_id}

    try:
        # 先完整执行获得结果，再模拟流式输出（LangGraph 本身不直接支持 token 级流式）
        result = await lg_builder.graph.ainvoke(input_state, config=run_config)

        router = result.get("router", None)
        router_type = router.type if router else "unknown"

        # 发送路由信息
        yield {
            "type": "metadata",
            "metadata": {"route": router_type},
            "session_id": session_id,
            "route": router_type,
        }

        # 提取回答
        answer = result.get("answer", "") or ""
        if not answer:
            messages = result.get("messages", [])
            for msg in reversed(messages):
                if isinstance(msg, AIMessage) and msg.content:
                    answer = str(msg.content)
                    break

        # 逐句流式输出
        sentences = _split_sentences(answer)
        for sentence in sentences:
            yield {"type": "message", "content": sentence, "session_id": session_id}
            await asyncio.sleep(0.03)

        # 完成信号
        sources = result.get("sources", []) or []
        yield {
            "type": "done",
            "metadata": {"sources": sources},
            "session_id": session_id,
        }

    except Exception as exc:
        logger.exception("流式对话失败: %s", exc)
        yield {"type": "error", "content": f"对话处理异常: {exc}", "session_id": session_id}


def _split_sentences(text: str) -> list[str]:
    """将文本按句子/换行拆分，保留分隔符"""
    import re
    # 按中文句号、换行等拆分
    parts = re.split(r'(?<=[。！？\n])', text)
    return [p for p in parts if p]
