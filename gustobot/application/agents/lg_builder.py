from openai import AsyncOpenAI
import base64
import io
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, cast
from PIL import Image
from pydantic import SecretStr
from langchain.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langchain_core.messages import AnyMessage, AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.redis.aio import AsyncRedisSaver
from gustobot.application.agents.lg_states import (
    AgentState, Router, InputState, GradeHallucinations,
)
from gustobot.application.agents.lg_models import GuardrailsOutput
from gustobot.application.prompts.lg_prompts import *
from gustobot.config.settings import settings
from gustobot.infrastructure.core.logger import get_logger
from gustobot.infrastructure.knowledge.recipe_kg.graph_db_client import Neo4jDatabase
from gustobot.application.agents.rag_sub_graph.rag_builder import build_rag_subgraph
from gustobot.application.agents.text2sql_sub_graph.builder import build_text2sql_subgraph
from gustobot.application.agents.utils.neo4j_connect import get_neo4j_graph
from gustobot.application.agents.rag_sub_graph.components.predefined_cypher.cypher_dict import predefined_cypher_dict
from gustobot.application.agents.utils.llm_factory import get_llm
from gustobot.application.agents.utils.neo4j_connect import graph_schema_to_nl
from gustobot.application.agents.utils.memory_manager import get_memory_manager
from gustobot.infrastructure.core.context_manager import (
    build_context_window,
    compress_if_needed,
    count_tokens,
)

logger = get_logger(service="lg_builder")

# 模块级子图实例，在 build_graph() 中初始化
text2sql_subgraph: Optional[Any] = None


def _extract_configurable(config: Any) -> Dict[str, Any]:
    """提取 LangGraph RunnableConfig 中的 configurable 字段，确保返回字典。"""
    if not config:
        return {}

    # RunnableConfig 是 TypedDict（本质为 dict），优先用字典接口
    if isinstance(config, dict):
        value = config.get("configurable", {})
        return value if isinstance(value, dict) else {}

    # 支持属性访问的非标准配置对象
    value = getattr(config, "configurable", None)
    return value if isinstance(value, dict) else {}


async def analyze_and_route_query(state: AgentState, *, config: RunnableConfig) -> Dict[str, Router]:
    """
    查询意图识别
    输入: 当前对话历史
    输出: 更新 State 中的 'router' 字段
    """
    try:
        model = get_llm(tags=["router"])

        if not state.messages:
            logger.warning("analyze_and_route_query: 没有找到用户消息，使用默认路由")
            return {
                "router": Router(
                    type="general-query",
                    logic="没有用户消息",
                    question=""
                )
            }
        
        # ── Mem0 记忆检索（旁路，不影响主流程） ──
        memory_context = ""
        try:
            mem_mgr = get_memory_manager()
            if mem_mgr:
                cfg = _extract_configurable(config)
                mem_user_id = cfg.get("thread_id", "default_user")
                mem_query = str(state.messages[-1].content) if state.messages else ""
                if mem_query:
                    memories = mem_mgr.search_memory(query=mem_query, user_id=mem_user_id)
                    if memories:
                        memory_lines = [f"- {m.get('memory', '')}" for m in memories if m.get('memory')]
                        if memory_lines:
                            memory_context = "\n用户历史记忆：\n" + "\n".join(memory_lines)
                            logger.info("Mem0 检索到 %d 条相关记忆", len(memory_lines))
        except Exception as e:
            logger.debug("Mem0 记忆检索跳过: %s", e)

        # 构建 LLM 输入消息（自适应压缩历史，防止上下文溢出）
        compressed = await compress_if_needed(list(state.messages))
        router_prompt = ROUTER_SYSTEM_PROMPT
        if memory_context:
            router_prompt = router_prompt + memory_context
        messages = build_context_window(
            system_prompt=router_prompt,
            messages=compressed,
        )
        logger.debug(f"History messages: {len(state.messages)} 条, 压缩后 {len(compressed)} 条")
        user_query = str(state.messages[-1].content) if hasattr(state.messages[-1], 'content') else str(state.messages[-1])

        # 调用 llm 进行意图识别
        logger.info(f"analyze_and_route_query: 正在分析用户查询{user_query[:100]}并进行路由决策...")
        raw_response = await model.with_structured_output(Router).ainvoke(messages)
        logger.debug(f"LLM 意图识别原始回复: {raw_response}")

        if isinstance(raw_response, Router):
            response = raw_response
        elif isinstance(raw_response, dict):
            response = Router(**raw_response)
        else:
            logger.warning(f"意图识别返回了非预期类型: {type(raw_response)}")
            response = Router(type="general-query", logic="LLM 返回类型异常", question=user_query)
        router_type = response.type
        logic = response.logic or ""
        
        # 验证意图类型
        allow_types = {
            "general-query", 
            "additional-query", 
            "graphrag-query", 
            "text2sql-query", 
            "image-query", 
            "file-query"
        }
        
        if not router_type or router_type not in allow_types:
            logger.warning(f"llm 识别的意图类型无效: {router_type}，进行后备路由匹配")
            heuristic_router = _heuristic_router(user_query, allow_types)
            if heuristic_router:
                logger.info(f"后备路由匹配成功，路由到: {heuristic_router.type}")
                return {"router": heuristic_router}
            else:
                logger.warning("后备路由匹配失败，默认路由到 general-query")
                return {
                    "router": Router(
                        type="general-query",
                        logic="LLM 识别的意图类型无效，后备路由匹配失败",
                        question=user_query
                    )
                }

        logger.info(f"意图识别结果: {router_type}")
        
        return {
            "router": Router(
                type=router_type,
                logic=logic,
                question=response.question or user_query,
                decision=response.decision,
                confidence=response.confidence,
                reasoning=response.reasoning
            ),
        }
        
    except Exception as e:
        logger.error(f"意图识别失败: {e}", exc_info=True)
        # 失败时返回默认路由
        return {
            "router": Router(
                type="general-query",
                logic=f"意图识别失败: {str(e)}",
                question=""
            )
        }


def _heuristic_router(query: str, allow_types: set) -> Optional[Router]:
    """基于关键词的后备路由匹配"""
    if not query:
        return None
    query_lower = query.lower()

    # 路由类型 → 关键词列表（按优先级排序）
    _keyword_map: Dict[str, List[str]] = {
        "graphrag-query": [
            "怎么做", "如何做", "做法", "步骤", "火候", "食材", "原料", "需要什么", "配料", "用什么",
            "烹饪", "烧法", "炒法", "蒸法", "煮法", "技巧", "窍门", "诀窍", "关系", "搭配",
            "替代", "口感", "营养",
        ],
        "text2sql-query": [
            "统计", "多少", "总数", "数量", "排名", "排行", "最多", "最少", "平均", "占比",
            "比例", "列表", "有哪些菜", "所有菜", "几道菜", "几种",
        ],
        "image-query": [
            "图片", "照片", "拍照", "看图", "识别图", "这是什么菜", "识别食材", "生成图", "画一张",
            "展示图", "成品图", "摆盘",
        ],
        "file-query": [
            "文件", "上传", "下载", "导出", "导入", "pdf", "excel", "csv", "文档", "报告",
            "保存为", "生成文件",
        ],
        "additional-query": [
            "补充", "更多细节", "没说清", "再详细", "具体点", "展开说", "详细说明",
        ],
    }

    for route_type, keywords in _keyword_map.items():
        if any(kw in query_lower for kw in keywords):
            return Router(type=route_type, logic=f"基于关键词匹配到 {route_type}", question=query)  # ty:ignore[invalid-argument-type]

    # 无法匹配时，回退到通用查询
    return Router(type="general-query", logic="关键词未命中任何专项路由，回退到 general-query", question=query)


def route_query(state: AgentState, config: RunnableConfig) -> str:
    """[条件边] 根据 state.router.type 返回目标节点函数名。"""
    if not state.router:
        logger.warning("没有 router 信息，默认路由到 process_general_query")
        return "process_general_query"

    router = _ensure_router(state.router, fallback_question=str(state.messages[-1].content) if state.messages else "")
    state.router = router
    _type = router.type or "general-query"

    # 优先：config 中包含图片/文件路径时直接路由
    cfg = _extract_configurable(config)
    if cfg.get("image_path"):
        logger.info("检测到图片路径配置，路由到 process_image_query")
        return "process_image_query"
    if cfg.get("file_path"):
        logger.info("检测到文件路径配置，路由到 process_file_query")
        return "process_file_query"

    # 路由映射表（Router.type → 注册的节点名称）
    _route_map: Dict[str, str] = {
        "general-query": "process_general_query",
        "graphrag-query": "rag_subgraph",
        "text2sql-query": "process_text2sql_query",
        "additional-query": "process_additional_query",
        "image-query": "process_image_query",
        "file-query": "process_file_query",
    }

    node_name = _route_map.get(_type, "process_general_query")
    logger.info(f"路由决策: {_type} → {node_name}")
    return node_name


def _ensure_router(router_obj: Any, *, fallback_question: str = "") -> Router:
    """确保 router_obj 是 Router 实例，如果不是则进行转换"""
    if isinstance(router_obj, Router):
        return router_obj
    elif isinstance(router_obj, dict):
        try:
            return Router(**router_obj)
        except Exception as e:
            logger.error(f"Router 构造失败: {e}", exc_info=True)
            return Router(type="general-query", logic=f"Router 构造失败: {str(e)}", question=fallback_question)
    else:
        logger.warning(f"无法解析 router 对象，类型不匹配: {type(router_obj)}, 默认返回一般查询类型的 Router")
        return Router(type="general-query", logic="无法解析 router 对象，类型不匹配", question=fallback_question)


async def process_general_query(state: AgentState, *, config: RunnableConfig) -> Dict[str, List[BaseMessage]]:
    """
    生成对一般查询的响应，完全基于大模型，不会触发任何外部服务的调用，包括自定义工具、知识库查询等。
    当路由器将查询分类为一般问题时，将调用此节点。
    Args:
        state (AgentState): 当前代理状态，包括对话历史和路由逻辑。
        config (RunnableConfig): 用于配置响应生成的模型。
    Returns:
        Dict[str, List[BaseMessage]]: 包含'messages'键的字典，其中包含生成的响应。
    """
    logger.info("正在处理 general_query 节点")
    
    try:
        model = get_llm(tags=["general_query"])

        # 构建信息提示
        router = _ensure_router(getattr(state, "router", None), fallback_question=str(state.messages[-1].content) if state.messages else "")
        state.router = router  # 确保 state.router 是 Router 实例
        system_prompt = GENERAL_QUERY_SYSTEM_PROMPT.format(logic=state.router.logic if state.router else "无")
        latest_question = str(state.messages[-1].content) if state.messages else ""

        # 上下文窗口管理：压缩 + 截断
        compressed = await compress_if_needed(list(state.messages))
        messages = build_context_window(
            system_prompt=system_prompt,
            messages=compressed,
        )
        if latest_question:
            # 强化“以当前问题为准”，避免被历史上下文带偏。
            messages.append(HumanMessage(content=f"请仅回答我这次最新问题：{latest_question}"))
        
        # 调用 LLM
        response = await model.ainvoke(messages)
        logger.info(f"general_query 回复生成成功: {response.content[:50]}...")
        return {"messages": [AIMessage(content=response.content)]}
        
    except Exception as e:
        logger.error(f"general_query 处理失败: {e}", exc_info=True)
        return {"messages": [AIMessage(content="抱歉，我暂时无法处理这个问题。")]}


async def process_text2sql_query(state: AgentState, *, config: RunnableConfig) -> Dict[str, Any]:
    """[节点] Text2SQL 查询：将用户自然语言查询转换为 SQL，执行后返回结果。"""
    logger.info("正在处理 text2sql_query 节点")
    if not state.messages:
        logger.warning("text2sql_query: 没有用户消息，无法生成 SQL 查询")
        return {"messages": [AIMessage(content="请问您能提供更多细节吗？")]}

    question = state.router.question if state.router else str(state.messages[-1].content)

    try:
        assert text2sql_subgraph is not None, "text2sql_subgraph 未初始化"
        sub_input = {"question": question}
        result = await text2sql_subgraph.ainvoke(sub_input, config=config)
        answer = result.get("answer", "")
        return {
            "answer": answer,
            "messages": [AIMessage(content=answer)],
        }
    except Exception as e:
        logger.error(f"text2sql_query 处理失败: {e}", exc_info=True)
        return {"messages": [AIMessage(content="抱歉，统计查询出现异常，请稍后重试。")]}


async def process_image_query(state: AgentState, *, config: RunnableConfig) -> Dict[str, List[BaseMessage]]:
    """[节点] 图片处理 (生成或理解)"""
    logger.info("正在处理 image_query 节点")

    try:
        image_path = _extract_configurable(config).get("image_path")
        user_query = str(state.messages[-1].content) if state.messages else ""

        # 判断是图像识别还是图像生成
        generate_keywords = ["生成", "画", "创建", "制作图片", "做一张", "给我一张", "来一张"]
        is_generate = any(kw in user_query for kw in generate_keywords)

        if is_generate and not image_path:
            return await _generate_image(user_query, state)

        # ---------- 图像理解分支 ----------
        if not image_path or not os.path.exists(image_path):
            logger.warning("image_query: 没有可用的图片路径")
            return {"messages": [AIMessage(content="请提供图片路径以处理图片查询。")]}

        if not all([settings.VISION_API_KEY, settings.VISION_BASE_URL, settings.VISION_MODEL]):
            logger.error("视觉模型配置不完整")
            return {"messages": [AIMessage(content="视觉模型配置不完整，无法处理图片查询。")]}

        # 1) 读取并压缩图片 → base64
        image_data = _encode_image(image_path)

        # 2) 调用视觉模型获取图片描述
        vision_llm = ChatOpenAI(
            model_name=settings.VISION_MODEL,
            openai_api_base=settings.VISION_BASE_URL,
            openai_api_key=SecretStr(settings.VISION_API_KEY),
            max_tokens=4000,
            temperature=0.7,
            request_timeout=60,
        )
        vision_messages = [
            SystemMessage(content="你是一个专业的菜谱图像分析助手。请详细分析图片中的内容，特别关注菜品名称、食材、烹饪方法、摆盘等细节。"),
            HumanMessage(content=[
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_data}"}},
                {"type": "text", "text": user_query or "请分析这张图片"},
            ]),
        ]
        vision_response = await vision_llm.ainvoke(vision_messages)
        image_description = vision_response.content
        logger.info("视觉模型图片描述生成成功")

        # 3) 结合图片描述 + 用户问题，生成最终回复
        model = get_llm(tags=["image_query"])
        system_prompt = GET_IMAGE_SYSTEM_PROMPT.format(image_description=image_description)
        compressed = await compress_if_needed(list(state.messages))
        final_messages = build_context_window(
            system_prompt=system_prompt,
            messages=compressed,
        )
        response = await model.ainvoke(final_messages)
        return {"messages": [response]}

    except Exception as e:
        logger.error(f"image_query 处理失败: {e}", exc_info=True)
        return {"messages": [AIMessage(content="抱歉，处理图片时发生错误。")]}

            
async def _generate_image(user_query: str, state: AgentState) -> Dict[str, List[BaseMessage]]:
    """生成图片：LLM 优化提示词 → 调用图像生成 API → 返回图片链接。

    Args:
        user_query: 用户的图片生成请求
        state: 当前代理状态

    Returns:
        包含生成图片信息的消息字典
    """
    logger.info("正在处理图片生成请求")
    try:
        async def _persist_image_to_local(image_url: str) -> str:
            """将远程生成图下载到本地 uploads/images，返回可访问 API 路径。"""
            try:
                import httpx
                import uuid

                base_dir = Path(settings.BASE_DIR)
                image_dir = base_dir / "uploads" / "images"
                image_dir.mkdir(parents=True, exist_ok=True)

                filename = f"generated_{uuid.uuid4().hex[:12]}.png"
                local_path = image_dir / filename

                async with httpx.AsyncClient(timeout=60) as http_client:
                    resp = await http_client.get(image_url)
                    if resp.status_code != 200:
                        logger.warning(f"下载生成图失败({resp.status_code}): {image_url}")
                        return ""
                    local_path.write_bytes(resp.content)

                return f"{settings.API_PREFIX}/upload/images/{filename}"
            except Exception as e:
                logger.warning(f"保存生成图到本地失败: {e}")
                return ""

        api_key = settings.IMAGE_GENERATION_API_KEY
        if not api_key:
            logger.error("IMAGE_GENERATION_API_KEY 未配置")
            return {"messages": [AIMessage(content="抱歉，图片生成服务配置不完整，无法生成图片。")]}

        # 步骤 1: 使用 LLM 优化提示词
        model = get_llm(tags=["image_generation"])
        enhance_prompt = IMAGE_GENERATION_ENHANCE_PROMPT.format(user_query=user_query)
        enhanced_response = await model.ainvoke([HumanMessage(content=enhance_prompt)])
        enhanced_prompt = str(enhanced_response.content).strip()
        logger.info(f"优化后提示词: {enhanced_prompt[:100]}...")

        # 步骤 2: 调用图像生成 API（OpenAI images 接口）
        # 兼容不同厂商模型命名差异：按候选模型列表依次尝试，避免单一模型 404 直接失败。
        client = AsyncOpenAI(
            api_key=api_key,
            base_url=settings.IMAGE_GENERATION_BASE_URL,
        )

        configured_model = (settings.IMAGE_GENERATION_MODEL or "").strip()
        model_candidates = [m for m in [
            configured_model,
            "qwen-image",
            "qwen-image-2.0",
            "wanx2.1-t2i-plus",
        ] if m]
        # 去重并保持顺序
        seen_models: set[str] = set()
        model_candidates = [m for m in model_candidates if not (m in seen_models or seen_models.add(m))]

        gen_response = None
        last_error: Exception | None = None
        for model_name in model_candidates:
            try:
                logger.info(f"尝试图片生成模型: {model_name}")
                gen_response = await client.images.generate(
                    model=model_name,
                    prompt=enhanced_prompt,
                    size=cast(Any, settings.IMAGE_GENERATION_SIZE),
                )
                if gen_response and gen_response.data and gen_response.data[0].url:
                    break
            except Exception as e:
                last_error = e
                logger.warning(f"图片模型 {model_name} 调用失败: {e}")
                continue

        if (not gen_response or not gen_response.data or not gen_response.data[0].url) and last_error is not None:
            # 对常见 404 场景给出可执行提示
            err_text = str(last_error)
            if "404" in err_text:
                # DashScope 兼容层常见 404：回退到原生文生图接口重试
                if "dashscope.aliyuncs.com" in (settings.IMAGE_GENERATION_BASE_URL or ""):
                    try:
                        import httpx

                        base_host = "https://dashscope-intl.aliyuncs.com" if "dashscope-intl" in (settings.IMAGE_GENERATION_BASE_URL or "") else "https://dashscope.aliyuncs.com"
                        native_url = f"{base_host}/api/v1/services/aigc/multimodal-generation/generation"
                        native_models = [
                            configured_model,
                            "qwen-image-2.0-pro",
                            "qwen-image-2.0",
                            "qwen-image",
                        ]
                        seen_native: set[str] = set()
                        native_models = [m for m in native_models if m and not (m in seen_native or seen_native.add(m))]

                        size = (settings.IMAGE_GENERATION_SIZE or "1024x1024").replace("x", "*")
                        headers = {
                            "Authorization": f"Bearer {api_key}",
                            "Content-Type": "application/json",
                        }

                        last_native_error = ""
                        for native_model in native_models:
                            logger.info(f"兼容层404，尝试DashScope原生模型: {native_model}")
                            payload = {
                                "model": native_model,
                                "input": {
                                    "messages": [
                                        {
                                            "role": "user",
                                            "content": [{"text": enhanced_prompt}],
                                        }
                                    ]
                                },
                                "parameters": {
                                    "size": size,
                                    "watermark": False,
                                },
                            }
                            async with httpx.AsyncClient(timeout=60) as http_client:
                                resp = await http_client.post(native_url, headers=headers, json=payload)
                            if resp.status_code != 200:
                                last_native_error = f"{resp.status_code}: {resp.text[:200]}"
                                logger.warning(f"DashScope原生接口失败({resp.status_code}): {resp.text[:200]}")
                                continue

                            data = resp.json()
                            choices = ((data.get("output") or {}).get("choices") or [])
                            content = []
                            if choices and isinstance(choices[0], dict):
                                content = (((choices[0].get("message") or {}).get("content")) or [])
                            image_url = ""
                            if content and isinstance(content[0], dict):
                                image_url = str(content[0].get("image") or "")

                            if image_url:
                                dish_match = re.search(r"(?:画|生成|创建|做|来)(?:一[张个份道])?(.+?)(?:的?(?:图片|照片|图|美食图))?$", user_query)
                                dish_name = dish_match.group(1).strip() if dish_match else "菜品"
                                success_message = IMAGE_GENERATION_SUCCESS_PROMPT.format(dish_name=dish_name)
                                local_url = await _persist_image_to_local(image_url)
                                content = f"{success_message}\n\n图片链接: {image_url}"
                                if local_url:
                                    content += f"\n本地访问: {local_url}"
                                return {"messages": [AIMessage(content=content)]}

                        if last_native_error:
                            return {"messages": [AIMessage(content=(
                                "抱歉，图片生成接口返回 404，且 DashScope 原生接口兜底也失败了。"
                                f"最后一次原生错误：{last_native_error}"
                            ))]}
                    except Exception as native_exc:
                        logger.warning(f"DashScope原生接口回退失败: {native_exc}")

                return {"messages": [AIMessage(content=(
                    "抱歉，图片生成接口返回 404。通常是模型名或服务端点不匹配导致。"
                    f"当前配置模型为：{configured_model or '未配置'}，"
                    "请检查 IMAGE_GENERATION_MODEL / IMAGE_GENERATION_BASE_URL。"
                ))]}
            raise last_error

        if not gen_response or not gen_response.data or not gen_response.data[0].url:
            return {"messages": [AIMessage(content="抱歉，图片生成失败，请稍后再试。")]}

        image_url = gen_response.data[0].url
        logger.info(f"图片生成成功: {image_url}")

        # 步骤 3: 从用户请求中提取菜名（简易方式：取"画/生成/做"后面的内容）
        dish_match = re.search(r"(?:画|生成|创建|做|来)(?:一[张个份道])?(.+?)(?:的?(?:图片|照片|图|美食图))?$", user_query)
        dish_name = dish_match.group(1).strip() if dish_match else "菜品"

        # 步骤 4: 格式化响应
        success_message = IMAGE_GENERATION_SUCCESS_PROMPT.format(dish_name=dish_name)
        local_url = await _persist_image_to_local(image_url)
        content = f"{success_message}\n\n图片链接: {image_url}"
        if local_url:
            content += f"\n本地访问: {local_url}"
        return {"messages": [AIMessage(content=content)]}

    except TimeoutError:
        return {"messages": [AIMessage(content="抱歉，图片生成超时，请稍后再试。")]}
    except Exception as e:
        logger.error(f"图片生成失败: {e}", exc_info=True)
        return {"messages": [AIMessage(content=f"抱歉，图片生成过程中出现错误：{str(e)}")]}


def _encode_image(image_path: str, max_size: int = 1024, quality: int = 85) -> str:
    """读取图片文件，压缩后返回 base64 编码字符串。"""
    with Image.open(image_path) as img:
        width, height = img.size
        ratio = min(max_size / width, max_size / height)

        if ratio < 1.0:
            resized = img.resize((int(width * ratio), int(height * ratio)), Image.Resampling.LANCZOS)
        else:
            resized = img

        buf = io.BytesIO()
        resized.save(buf, format="JPEG", quality=quality)
        logger.info(f"图片处理完成，原始尺寸: {width}x{height}, 压缩后: {resized.size[0]}x{resized.size[1]}")
        return base64.b64encode(buf.getvalue()).decode("utf-8")


async def process_file_query(state: AgentState, *, config: RunnableConfig) -> Dict[str, List[BaseMessage]]:
    """[节点] 文件处理：读取用户上传文件内容，结合 LLM 生成回复。

    支持文件类型：.txt / .md / .csv / .log / .json / .xlsx / .xls
    Excel 文件转发至外部 kb_ingest 服务处理。
    """
    from pathlib import Path
    import json
    import uuid

    logger.info("正在处理 file_query 节点")

    config_opts = _extract_configurable(config)
    file_path = config_opts.get("file_path")

    if not file_path:
        logger.warning("file_query: 未提供文件路径")
        return {"messages": [AIMessage(content="请提供要处理的文件路径。")]}

    p = Path(file_path)
    if not p.exists() or not p.is_file():
        logger.warning("file_query: 文件不存在: %s", file_path)
        return {"messages": [AIMessage(content="抱歉，未找到该文件，请确认路径是否正确。")]}

    try:
        # 大小校验
        size_bytes = p.stat().st_size # 获取文件大小
        max_mb = settings.FILE_UPLOAD_MAX_MB
        if size_bytes > max_mb * 1024 * 1024:
            return {"messages": [AIMessage(content=f"文件过大（>{max_mb}MB），请分割后重新上传。")]}

        suffix = p.suffix.lower()

        # Excel 分支：转发至外部 ingest 服务
        if suffix in {".xlsx", ".xls"}:
            return await _forward_excel_to_ingest(p, config_opts)

        # 文本类文件：读取内容
        if suffix in {".txt", ".md", ".csv", ".log"}:
            raw_text = p.read_text(encoding="utf-8", errors="ignore")
        elif suffix == ".json":
            data = json.loads(p.read_text(encoding="utf-8", errors="ignore"))
            raw_text = json.dumps(data, ensure_ascii=False, indent=2)
        else:
            return {"messages": [AIMessage(
                content=f"暂不支持该文件类型：{suffix}。当前支持 .txt/.md/.json/.csv/.log/.xlsx/.xls"
            )]}

        # 截断过长内容，避免超出上下文窗口
        max_chars = 8000
        truncated = raw_text[:max_chars]
        if len(raw_text) > max_chars:
            truncated += f"\n\n... [文件内容已截断，原始 {len(raw_text)} 字符，仅展示前 {max_chars} 字符]"

        # ---- 用 LLM 基于文件内容回答用户问题 ----
        user_question = str(state.messages[-1].content) if state.messages else f"总结文件《{p.stem}》的内容"
        model = get_llm(tags=["file_query"])
        prompt = (
            f"以下是用户上传的文件《{p.name}》的内容：\n\n"
            f"```\n{truncated}\n```\n\n"
            f"用户的问题是：{user_question}\n\n"
            "请根据文件内容回答用户问题。如果文件内容与烹饪/菜谱/食材相关，请提供专业的分析。"
        )
        response = await model.ainvoke([
            SystemMessage(content="你是菜谱领域的智能助手，擅长分析和总结用户上传的文件内容。"),
            HumanMessage(content=prompt),
        ])

        # TODO: 后续实现 KnowledgeService，将文件内容写入向量知识库用于持久化检索
        logger.info(f"文件 {p.name} 处理完成")
        return {"messages": [response]}

    except Exception as exc:
        logger.exception("文件处理失败: %s", exc)
        return {"messages": [AIMessage(content="文件导入出现异常，请稍后再试或联系管理员。")]}


async def _forward_excel_to_ingest(file_path: Path, config_opts: Dict[str, Any]) -> Dict[str, List[BaseMessage]]:
    """将 Excel 文件转发至外部 kb_ingest 微服务处理。"""
    import httpx

    ingest_url = settings.INGEST_SERVICE_URL
    if not ingest_url:
        return {"messages": [AIMessage(content="未配置外部接入服务 INGEST_SERVICE_URL，无法处理 Excel 导入。")]}

    def _to_bool(val: Any, default: bool) -> bool:
        """将配置值转换为布尔值"""
        if val is None:
            return default
        if isinstance(val, bool):
            return val
        return str(val).lower() in ("true", "1", "yes")

    payload = {
        "excel_path": str(file_path),
        "incremental": _to_bool(config_opts.get("incremental"), settings.INGEST_INCREMENTAL_DEFAULT),
        "regenerate": _to_bool(config_opts.get("regenerate"), False),
    }

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(f"{ingest_url.rstrip('/')}/api/ingest/excel", json=payload)
        if resp.status_code not in (200, 202):
            return {"messages": [AIMessage(content=f"外部 Excel 导入请求失败（{resp.status_code}）：{resp.text}")]}

    return {"messages": [AIMessage(content="已启动 Excel 导入（外部服务），完成后可直接检索或提问。")]}


async def process_additional_query(state: AgentState, *, config: RunnableConfig) -> Dict[str, List[AnyMessage]]:
    """
    [节点] 追问/澄清用户信息。
    当路由判定信息不足时调用，结合知识图谱 schema 上下文向用户提出针对性追问。
    """
    logger.info("正在处理 additional_query 追问节点")

    if not state.messages:
        logger.warning("additional_query: 没有用户消息，无法追问")
        return {"messages": [AIMessage(content="请问您能提供更多细节吗？")]}

    user_query = str(state.messages[-1].content) if hasattr(state.messages[-1], "content") else str(state.messages[-1])

    # 获取知识图谱 schema 的自然语言描述（一次获取，多处复用）
    schema_nl = ""
    try:
        neo4j_graph = get_neo4j_graph()
        schema_nl = graph_schema_to_nl(neo4j_graph)
    except Exception as e:
        logger.warning(f"获取 Neo4j schema 失败，将不附带知识图谱上下文: {e}")

    try:
        model = get_llm(tags=["additional_query"])

        # 构建 Guardrails 安全检查
        scope_context = f"参考此范围描述来决策:\n{SCOPE_DESCRIPTION}"
        graph_context = f"\n参考图数据库结构来回答:\n{schema_nl}" if schema_nl else "没有图数据库结构信息"
        guardrails_prompt = ChatPromptTemplate.from_messages([
            ("system", GUARDRAILS_SYSTEM_PROMPT),
            ("human", f"{scope_context}\n\n{graph_context}\n\nQuestion: {{question}}"),
        ])
        guardrails_chain = guardrails_prompt | model.with_structured_output(GuardrailsOutput)
        raw_guardrails = await guardrails_chain.ainvoke({"question": user_query})

        if raw_guardrails is None:
            logger.warning("Guardrails 输出为空，默认为 proceed")
            guardrails_output = GuardrailsOutput(decision="proceed")
        elif isinstance(raw_guardrails, GuardrailsOutput):
            guardrails_output = raw_guardrails
        else:
            guardrails_output = GuardrailsOutput.model_validate(raw_guardrails)

        if guardrails_output.decision != "proceed":
            logger.info("Guardrails 决策: end（超范围）")
            return {"messages": [AIMessage(
                content="厨友您好～抱歉哦，这个问题不太属于我们的菜谱范围呢，我主要帮您解答菜谱和烹饪方面的问题～😊"
            )]}

        # 生成追问
        logger.info("Guardrails 决策: proceed")
        router = _ensure_router(getattr(state, "router", None), fallback_question=user_query)
        state.router = router

        prompt = GET_ADDITIONAL_SYSTEM_PROMPT.format(logic=router.logic or "无")
        compressed = await compress_if_needed(list(state.messages))
        messages = build_context_window(
            system_prompt=prompt,
            messages=compressed,
        )
        response = await model.ainvoke(messages)

        logger.info(f"additional_query 追问生成成功: {response.content[:50]}...")
        return {"messages": [AIMessage(content=response.content)]}

    except Exception as e:
        logger.error(f"additional_query 处理失败: {e}", exc_info=True)
        return {"messages": [AIMessage(content="请问您能提供更多细节吗？")]}


async def process_response(state: AgentState, *, config: RunnableConfig) -> Dict[str, Any]:
    """
    [统一回复处理节点]
    职责：
    1. 从最后一条 AI 消息提取回复内容
    2. 同步 answer 字段（保证 state.answer 始终与最终消息一致）
    3. 基础内容安全过滤
    4. 日志记录
    """
    try:
        # 提取最后一条 AI 回复
        last_content = ""
        if state.messages:
            last_msg = state.messages[-1]
            if hasattr(last_msg, "content") and last_msg.content:
                last_content = str(last_msg.content)

        if not last_content:
            logger.warning("process_response: 没有可处理的回复内容")
            fallback = "抱歉，我暂时无法回答这个问题。"
            return {
                "answer": fallback,
                "messages": [AIMessage(content=fallback)],
            }

        # 内容安全：过滤潜在的敏感信息泄露（如数据库连接串）
        import re
        _SENSITIVE_PATTERNS = [
            r"mysql\+pymysql://[^\s]+",
            r"bolt://[^\s]+",
            r"redis://[^\s]+",
        ]
        sanitized = last_content
        for pattern in _SENSITIVE_PATTERNS:
            sanitized = re.sub(pattern, "[已隐藏]", sanitized, flags=re.IGNORECASE)

        logger.info("处理回复: %s...", sanitized[:100])

        # 如果内容被过滤，更新消息；否则保留原始消息
        if sanitized != last_content:
            logger.warning("process_response: 检测到敏感信息并已过滤")
            return {
                "answer": sanitized,
                "messages": [AIMessage(content=sanitized)],
            }

        # ── Mem0 记忆存储（旁路，不影响主流程） ──
        try:
            mem_mgr = get_memory_manager()
            if mem_mgr and state.messages and len(state.messages) >= 2:
                cfg = _extract_configurable(config)
                mem_user_id = cfg.get("thread_id", "default_user")
                # 提取最近一轮 user + assistant 消息
                recent_msgs = []
                for msg in reversed(state.messages):
                    role = getattr(msg, "type", "")
                    content = str(getattr(msg, "content", ""))
                    if role == "ai" and not recent_msgs:
                        recent_msgs.insert(0, {"role": "assistant", "content": content})
                    elif role == "human" and len(recent_msgs) <= 1:
                        recent_msgs.insert(0, {"role": "user", "content": content})
                        break
                if len(recent_msgs) == 2:
                    mem_mgr.add_memory(recent_msgs, user_id=mem_user_id)
        except Exception as e:
            logger.debug("Mem0 记忆存储跳过: %s", e)

        # 同步 answer 字段（确保每轮都以当前最后一条 AI 消息为准）
        return {
            "answer": last_content,
        }

    except Exception as e:
        logger.error("回复处理失败: %s", e)
        return {"messages": state.messages[-1:] if state.messages else []}


async def check_hallucinations(state: AgentState, *, config: RunnableConfig) -> Dict[str, Any]:
    """[节点] 检查和处理幻觉，检测到幻觉时累加重试计数。"""
    retry_count = state.hallucination_retry
    logger.info("正在处理 hallucination_check 节点 (第 %d 次检查)", retry_count + 1)
    try:
        model = get_llm(tags=["hallucination_check"])
        system_prompt = CHECK_HALLUCINATIONS.format(
            documents=state.documents,
            generation=state.messages[-1] if state.messages else ""
        )
        messages = build_context_window(
            system_prompt=system_prompt,
            messages=list(state.messages[-2:]) if state.messages else [],  # 幻觉检查只需最近的问答对
        )

        raw = await model.with_structured_output(GradeHallucinations).ainvoke(messages)
        if isinstance(raw, GradeHallucinations):
            response = raw
        elif isinstance(raw, dict):
            response = GradeHallucinations(**raw)
        else:
            logger.warning(f"幻觉检查返回非预期类型: {type(raw)}，默认无幻觉")
            response = GradeHallucinations(binary_score="1")

        is_hallucination = response.binary_score == "0"
        logger.info("幻觉检查结果: %s (0=有幻觉, 1=无幻觉)", response.binary_score)

        result: Dict[str, Any] = {"hallucination": response}
        if is_hallucination:
            result["hallucination_retry"] = retry_count + 1
            logger.warning("检测到幻觉，重试计数: %d/3", retry_count + 1)
        return result

    except Exception as e:
        logger.error("幻觉检查失败: %s", e, exc_info=True)
        return {"hallucination": GradeHallucinations(binary_score="1")}  # 默认认为没有幻觉


async def hallucination_reject(state: AgentState, *, config: RunnableConfig) -> Dict[str, Any]:
    """[节点] 幻觉重试耗尽后生成拒绝式回答，避免输出不可靠内容。"""
    logger.warning("幻觉重试已达上限(%d次)，生成拒绝式回复", state.hallucination_retry)
    reject_msg = (
        "非常抱歉，经过多次验证，我无法确保回答的准确性。"
        "为避免提供不准确的信息，建议您换一种方式描述问题，或联系人工客服获取帮助～"
    )
    return {
        "answer": reject_msg,
        "messages": [AIMessage(content=reject_msg)],
    }


def build_graph(*, checkpointer: Optional[AsyncRedisSaver] = None):
    """组装 LangGraph 状态图（checkpointer 需单独在 async 上下文中设置）。"""
    global text2sql_subgraph
    builder = StateGraph(AgentState, input=InputState)

    neo4j_graph = get_neo4j_graph()
    subgraph = build_rag_subgraph(
        graph=neo4j_graph,
        predefined_cypher_dict=predefined_cypher_dict,
        scope_description=SCOPE_DESCRIPTION,
        )
    text2sql_subgraph = build_text2sql_subgraph()

    # Wrapper：主图 AgentState → 子图 RAGSubGraphInputState → 主图 AgentState
    async def rag_subgraph_node(state: AgentState, *, config: RunnableConfig) -> Dict[str, Any]:
        sub_input = {"question": state.router.question}
        result = await subgraph.ainvoke(sub_input, config=config)
        answer = result.get("answer", "")
        return {
            "answer": answer,
            "messages": [AIMessage(content=answer)],
        }

    # ── 节点 ──
    builder.add_node(analyze_and_route_query)
    builder.add_node(process_general_query)
    builder.add_node("rag_subgraph", rag_subgraph_node)  # RAG 子图（通过 wrapper 映射主图↔子图状态）
    builder.add_node(process_text2sql_query)
    builder.add_node(process_additional_query)
    builder.add_node(process_image_query)
    builder.add_node(process_file_query)
    builder.add_node(process_response)
    builder.add_node(check_hallucinations) 
    builder.add_node(hallucination_reject)

    # ── 边 ──
    builder.add_edge(START, "analyze_and_route_query")

    # 条件路由：route_query() 直接返回目标节点函数名
    builder.add_conditional_edges(
        source="analyze_and_route_query",
        path=route_query,
    )

    # 所有业务节点 → 统一回复处理
    for node_name in [
        "process_general_query",
        "rag_subgraph",
        "process_text2sql_query",
        "process_additional_query",
        "process_image_query",
        "process_file_query",
    ]:
        builder.add_edge(node_name, "process_response")

    def _should_check_hallucinations(state: AgentState, config: RunnableConfig) -> str:
        """无检索文档时跳过幻觉检查（general-query 等不需要）"""
        if not state.documents:
            return END
        return "check_hallucinations"

    builder.add_conditional_edges(
        source="process_response",
        path=_should_check_hallucinations,
    )

    # 路由映射：Router.type → 注册的节点名称（与 route_query 保持一致）
    _hallucination_route_map: Dict[str, str] = {
        "graphrag-query": "rag_subgraph",
        "text2sql-query": "process_text2sql_query",
    }

    def _after_hallucination_check(state: AgentState, config: RunnableConfig) -> str:
        """幻觉检查后路由：有幻觉且重试未超限 → 回到业务节点重新生成；重试耗尽 → 拒绝回复；无幻觉 → END。"""
        h = state.hallucination
        if h and h.binary_score == "0":
            if state.hallucination_retry < 3:
                router_type = state.router.type if state.router else ""
                target = _hallucination_route_map.get(router_type)
                if target:
                    logger.info("幻觉重试: %s → %s (第 %d 次)", router_type, target, state.hallucination_retry)
                    return target
            # 重试耗尽或无法映射回业务节点 → 拒绝式回复
            return "hallucination_reject"
        return END

    builder.add_conditional_edges(
        source="check_hallucinations",
        path=_after_hallucination_check,
    )

    builder.add_edge("hallucination_reject", END)

    graph = builder.compile(checkpointer=checkpointer)

    return graph


graph = None


async def init_graph():
    """异步初始化 LangGraph 主图（需在 event loop 中调用）。"""
    global graph
    checkpointer = AsyncRedisSaver(redis_url=settings.REDIS_URL)
    await checkpointer.asetup()
    graph = build_graph(checkpointer=checkpointer)