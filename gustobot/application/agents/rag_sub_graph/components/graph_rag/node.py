import asyncio
from types import SimpleNamespace
from typing import Any, Callable, Coroutine, Dict, List, Optional
from gustobot.application.agents.utils.llm_factory import get_llm

from gustobot.application.agents.rag_sub_graph.rag_states import QueryInputState
from gustobot.application.agents.rag_sub_graph.components.graph_rag.rag_modules import (
    GraphRAGRetrieval,
    HybridRetrievalModule,
    IntelligentQueryRouter,
    GenerationIntegrationModule,
    MilvusIndexConstructorModule,
    GraphDataPreparation
)

from gustobot.config.settings import Settings
from gustobot.infrastructure.core.logger import get_logger

logger = get_logger(service="graphrag_query_node")


def create_graphrag_query_node(
    top_k: int = 5,
) -> Callable[[QueryInputState], Coroutine[Any, Any, Dict[str, Any]]]:
    """
    创建 GraphRAG 查询节点。

    内部初始化 IntelligentQueryRouter（路由 + 检索）
    通过 Settings 读取所有配置。

    Parameters
    ----------
    top_k : int
        每次检索返回的最大文档数，默认 5。
    """
    logger.info("正在创建 GraphRAG 查询节点")
    # config — SimpleNamespace 供属性访问（GraphRAGRetrieval / HybridRetrieval / Router / Indexing）
    _cfg = SimpleNamespace(
        neo4j_uri=Settings.NEO4J_URI,
        neo4j_user=Settings.NEO4J_USER,
        neo4j_password=Settings.NEO4J_PASSWORD,
        llm_model=Settings.LLM_MODEL,
    )
    # GraphDataPreparation 需要 dict（内部用 .get()）
    _neo4j_dict = {
        "uri": Settings.NEO4J_URI,
        "username": Settings.NEO4J_USER,
        "password": Settings.NEO4J_PASSWORD,
    }
    llm = get_llm(tags=["graphrag_query_node"])

    # 模块准备
    milvus_module = MilvusIndexConstructorModule()
    data_module = GraphDataPreparation(_neo4j_dict)
    graphrag_module = GraphRAGRetrieval(config=_cfg, llm_client=llm)
    generator_module = GenerationIntegrationModule()

    # hybrid_module 与 router_module 延迟到首次查询时初始化
    _initialized = False
    _init_lock = asyncio.Lock()
    _init_task: Optional[asyncio.Task[Any]] = None
    hybrid_module: HybridRetrievalModule | None = None
    router_module: IntelligentQueryRouter | None = None
   

    async def _ensure_initialized():
        """初始化：连接 Neo4j、加载数据、构建图索引与向量检索器。"""
        nonlocal _initialized, hybrid_module, router_module
        if _initialized:
            return

        async with _init_lock:
            if _initialized:
                return

            # 异步加载图数据 → 构建文档 → 分块
            await data_module.connect()
            await data_module.load_graph_data()
            await data_module.build_recipe_documents()
            data_module.chunk_documents()

            chunks = data_module.chunks
            if milvus_module is not None and chunks:
                hybrid_module = HybridRetrievalModule(
                    config=_cfg,
                    milvus_module=milvus_module,
                    data_module=data_module,
                    llm_client=llm,
                )
                hybrid_module.initialize(chunks)

            router_module = IntelligentQueryRouter(
                traditional_retrieval=hybrid_module,
                graph_rag_retrieval=graphrag_module,
                llm_client=llm,
                config=_cfg,
            )
            _initialized = True
            logger.info("GraphRAG 节点初始化完成（预热）")

    def _start_background_warmup() -> None:
        """在节点创建阶段启动后台预热，避免首个 GraphRAG 查询冷启动。"""
        nonlocal _init_task
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            logger.warning("未检测到运行中的事件循环，跳过 GraphRAG 预热")
            return

        if _init_task is None or _init_task.done():
            async def _warmup() -> None:
                try:
                    await _ensure_initialized()
                except Exception as exc:
                    logger.error(f"GraphRAG 预热失败: {exc}")

            _init_task = loop.create_task(_warmup())
            logger.info("已触发 GraphRAG 后台预热任务")

    async def graphrag_query(state: QueryInputState) -> Dict[str, Any]:
        question = state.get("task", "")
        logger.info(f"GraphRAG 节点收到查询: {question}")

        errors: List[str] = []
        records: List[Dict[str, Any]] = []
        answer = ""
        strategy_used = ""

        try:
            await _ensure_initialized()
            assert router_module is not None, "router_module 初始化失败"

            # 1. 智能路由检索
            documents, analysis = await router_module.route_query(question, top_k=top_k)
            strategy_used = analysis.recommended_strategy.value
            logger.info(
                f"检索完成: 策略={strategy_used}, 文档数={len(documents)}"
            )

            records = [
                {
                    "content": doc.page_content,
                    "metadata": doc.metadata,
                }
                for doc in documents
            ]

            # 2. 生成回答
            if documents:
                answer = generator_module.generate_adaptive_answer(question, documents)
            else:
                answer = "未检索到相关文档，无法生成回答。"
                errors.append("GraphRAG 未检索到任何文档")

        except Exception as exc:
            logger.error(f"GraphRAG 查询失败: {exc}")
            errors.append(f"GraphRAG 查询异常: {exc}")

        return {
            "cyphers": [
                {
                    "task": question,
                    "statement": f"[GraphRAG:{strategy_used}]",
                    "parameters": state.get("query_parameters", {}),
                    "errors": errors,
                    "records": records if records else ["未检索到相关文档"],
                    "steps": ["graphrag_query"],
                }
            ],
            "summary": answer,
            "steps": ["graphrag_query"],
            "history": [
                {
                    "question": question,
                    "answer": answer,
                    "cyphers": [
                        {
                            "task": question,
                            "statement": f"[GraphRAG:{strategy_used}]",
                            "records": records if records else [],
                        }
                    ],
                }
            ],
        }

    _start_background_warmup()

    return graphrag_query
