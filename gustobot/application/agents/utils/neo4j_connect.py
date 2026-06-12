import re
from langchain_neo4j import Neo4jGraph
from gustobot.infrastructure.core.logger import get_logger
from gustobot.config.settings import settings

logger = get_logger(service="neo4j_connect")

def get_neo4j_graph() -> Neo4jGraph:
    """
    创建并返回一个Neo4jGraph实例，使用配置文件中的设置。
    
    Returns:
        Neo4jGraph: 配置好的Neo4j图数据库连接实例
    """
    logger.info(f"initialize Neo4j connection: {settings.NEO4J_URI}")
    try:
        if settings.NEO4J_USER and settings.NEO4J_PASSWORD not in (None, ""):
            return Neo4jGraph(
                url=settings.NEO4J_URI,
                database=settings.NEO4J_DATABASE,
                username=settings.NEO4J_USER,
                password=settings.NEO4J_PASSWORD,
            )

        return Neo4jGraph(
            url=settings.NEO4J_URI,
            database=settings.NEO4J_DATABASE,
        )
    except Exception as e:
        logger.error(f"Failed to initialize Neo4j connection: {e}")
        raise


def graph_schema_to_nl(neo4j_graph: Neo4jGraph) -> str:
    """
    从图对象中提取并格式化图结构信息，用于提示词。

    参数:
        graph: 图对象，预期具有 nodes 和 edges 属性

    返回:
        格式化的图结构字符串
    """    

    schema = neo4j_graph.schema
    # 以 "- CypherQuery" 开始的整个段落，直到 "Relationship properties" 或 "- " 为止
    schema_re = r"^(- \*\*CypherQuery\*\*[\s\S]+?)(^Relationship properties|- \*)"
    if "CypherQuery" in schema:
        schema = re.sub(
            schema_re, r"\2", schema, flags=re.MULTILINE
        )

    schema = schema.replace("{", "[").replace("}", "]")

    return schema