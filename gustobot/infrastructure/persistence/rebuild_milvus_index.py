"""
Milvus 向量索引重建脚本

从 Neo4j 加载图谱数据 → 构建文档 → 分块 → 生成向量 → 写入 Milvus
"""
import asyncio
import sys
import os

# 确保项目根目录在 sys.path 中
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from gustobot.config.settings import Settings
from gustobot.application.agents.rag_sub_graph.components.graph_rag.rag_modules import (
    MilvusIndexConstructorModule,
    GraphDataPreparation,
)
from gustobot.infrastructure.core.logger import get_logger

logger = get_logger(service="rebuild_milvus")


async def main():
    neo4j_config = {
        "uri": Settings.NEO4J_URI,
        "username": Settings.NEO4J_USER,
        "password": Settings.NEO4J_PASSWORD,
    }

    # 1. 从 Neo4j 加载图谱数据
    logger.info("正在连接 Neo4j 并加载图谱数据...")
    data_module = GraphDataPreparation(neo4j_config)
    await data_module.connect()
    await data_module.load_graph_data()

    logger.info(
        f"加载完成: Recipe={len(data_module.recipes)}, "
        f"Ingredient={len(data_module.ingredients)}, "
        f"CookingStep={len(data_module.cooking_steps)}"
    )

    # 2. 构建文档并分块
    logger.info("正在构建文档并分块...")
    await data_module.build_recipe_documents()
    data_module.chunk_documents()

    chunks = data_module.chunks
    logger.info(f"文档分块完成，共 {len(chunks)} 个块")

    if not chunks:
        logger.error("未生成任何文档块，退出")
        return

    # 3. 构建 Milvus 向量索引
    logger.info("正在构建 Milvus 向量索引...")
    milvus_module = MilvusIndexConstructorModule()
    success = milvus_module.build_vector_index(chunks)

    if success:
        stats = milvus_module.get_collection_stats()
        logger.info(f"Milvus 索引重建成功: {stats}")
    else:
        logger.error("Milvus 索引重建失败")

    # 4. 断开 Neo4j 连接
    await data_module.close()
    milvus_module.close()


if __name__ == "__main__":
    asyncio.run(main())
