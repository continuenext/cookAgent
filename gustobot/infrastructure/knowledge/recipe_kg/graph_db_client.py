from gustobot.config.settings import settings
from typing import Any, Dict, List, Optional, cast, LiteralString
from neo4j import GraphDatabase, Result, Query
from neo4j.graph import Graph
from gustobot.infrastructure.core.logger import get_logger

logger = get_logger("neo4j_client")

class Neo4jDatabase:
    """
    Neo4j 驱动的轻量级封装。
    管理数据库连接，执行 Cypher 查询。
    """

    def __init__(self) -> None:
        """初始化 Neo4j 驱动"""
        self._driver = None
        try:
            self._driver = GraphDatabase.driver(
                settings.NEO4J_URI, 
                auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD)
                )
            # 测试连接
            self._driver.verify_connectivity()
            logger.info("成功连接到 Neo4j 数据库。")

        except Exception as e:
            logger.error(f"连接 Neo4j 数据库失败: {e}")
            raise ConnectionError(f"无法连接 Neo4j 数据库: {e}")

    def close(self) -> None:
        """关闭驱动连接"""
        if self._driver:
            self._driver.close()
            logger.info("Neo4j 连接关闭。")

    def execute(self, query: str, parameters: Optional[Dict[str, Any]] = None) -> None:
        """
        执行增删改操作（不返回结果）。
        Args:
            query: Cypher 查询语句
            parameters: 查询参数字典
        """
        if not self._driver:
            raise ConnectionError("Neo4j driver 没有初始化。")
        
        try:
            with self._driver.session() as session:
                cypher_query = Query(cast(LiteralString, query))  # 使用 cast 解决 LiteralString 类型检查问题
                session.run(cypher_query, parameters or {})
                logger.debug(f"执行查询: {query} 。参数: {parameters}")
        except Exception as e:
            logger.error(f"执行查询失败: {e}")
            raise

    def fetch(self, query: str, parameters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        执行查询操作，返回字典列表。
        Args:
            query: Cypher 查询语句
            parameters: 查询参数
        Returns:
            List[Dict]: 查询结果，每一行是一个字典
        """
        if not self._driver:
            raise ConnectionError("Neo4j driver 没有初始化。")
        
        try:
            with self._driver.session() as session:
                cypher_query = Query(cast(LiteralString, query)) # 使用 cast 解决 LiteralString 类型检查问题
                result = session.run(cypher_query, parameters or {})
                
                # 将结果转换为字典列表
                records = []
                for record in result:
                    records.append(dict(record))
                
                logger.debug(f"Fetched {len(records)} records for query: {query}")
                return records
                
        except Exception as e:
            logger.error(f"Failed to fetch data: {e}")
            raise
    
    # 如果需要处理复杂的图对象（节点/关系），可以预留这个接口
    def fetch_graph(self, query: str, parameters: Optional[Dict[str, Any]] = None) -> Graph:  # ty:ignore[empty-body]
        """返回 Neo4j Graph 对象"""
        pass
    
    def get_schema(self) -> Dict[str, Any]:
        """
        获取 Neo4j 数据库的完整 schema 信息。
        使用 APOC 或单次查询获取节点-关系-节点三元组模式，
        避免 N+1 查询，并保留关系方向信息。
        
        Returns:
            Dict 包含:
                - labels: 节点标签列表
                - relationship_types: 关系类型列表
                - node_properties: {标签: [属性名]}
                - relationship_properties: {关系类型: [属性名]}
                - triples: [{"from": str, "rel": str, "to": str}] 关系三元组
        """
        if not self._driver:
            raise ConnectionError("Neo4j driver 没有初始化。")
        
        empty_schema = {
            "labels": [],
            "relationship_types": [],
            "node_properties": {},
            "relationship_properties": {},
            "triples": []
        }
        
        try:
            schema_info: Dict[str, Any] = {
                "labels": [],
                "relationship_types": [],
                "node_properties": {},
                "relationship_properties": {},
                "triples": []
            }
            
            with self._driver.session() as session:
                # 1) 一次性获取所有节点标签及其属性（使用 apoc 或回退到手动）
                try:
                    # 尝试使用 APOC 的 meta.schema (更高效)
                    meta_query = Query(cast(LiteralString, 
                        "CALL apoc.meta.schema() YIELD value RETURN value"
                    ))
                    meta_result = session.run(meta_query)
                    meta_record = meta_result.single()
                    
                    if meta_record:
                        meta = meta_record["value"]
                        for label, info in meta.items():
                            if info.get("type") == "node":
                                schema_info["labels"].append(label)
                                schema_info["node_properties"][label] = list(info.get("properties", {}).keys())
                                # 从 relationships 中提取三元组
                                for rel_name, rel_info in info.get("relationships", {}).items():
                                    rel_direction = rel_info.get("direction", "out")
                                    for target_label in rel_info.get("labels", []):
                                        if rel_direction == "out":
                                            triple = {"from": label, "rel": rel_name, "to": target_label}
                                        else:
                                            triple = {"from": target_label, "rel": rel_name, "to": label}
                                        if triple not in schema_info["triples"]:
                                            schema_info["triples"].append(triple)
                            elif info.get("type") == "relationship":
                                schema_info["relationship_types"].append(label)
                                schema_info["relationship_properties"][label] = list(info.get("properties", {}).keys())
                        
                        logger.info(
                            f"通过 APOC 获取 Neo4j schema: "
                            f"{len(schema_info['labels'])} 个节点标签, "
                            f"{len(schema_info['relationship_types'])} 个关系类型, "
                            f"{len(schema_info['triples'])} 个三元组模式"
                        )
                        return schema_info
                        
                except Exception:
                    logger.debug("APOC 不可用，回退到手动查询方式获取 schema")
                
                # 2) 回退：手动查询
                # 获取所有节点标签
                labels_result = session.run(Query(cast(LiteralString, "CALL db.labels()")))
                schema_info["labels"] = [r["label"] for r in labels_result]
                
                # 获取所有关系类型
                rel_result = session.run(Query(cast(LiteralString, "CALL db.relationshipTypes()")))
                schema_info["relationship_types"] = [r["relationshipType"] for r in rel_result]
                
                # 批量获取节点属性（一次查询搞定所有标签）
                if schema_info["labels"]:
                    for label in schema_info["labels"]:
                        props_result = session.run(Query(cast(
                            LiteralString,
                            f"MATCH (n:`{label}`) WITH keys(n) AS ks UNWIND ks AS k RETURN DISTINCT k LIMIT 200"
                        )))
                        schema_info["node_properties"][label] = [r["k"] for r in props_result]
                
                # 批量获取关系属性
                if schema_info["relationship_types"]:
                    for rel_type in schema_info["relationship_types"]:
                        rel_props_result = session.run(Query(cast(
                            LiteralString,
                            f"MATCH ()-[r:`{rel_type}`]->() WITH keys(r) AS ks UNWIND ks AS k RETURN DISTINCT k LIMIT 200"
                        )))
                        schema_info["relationship_properties"][rel_type] = [r["k"] for r in rel_props_result]
                
                # 获取关系三元组模式（一次查询获取所有）
                triples_result = session.run(Query(cast(LiteralString,
                    "MATCH (a)-[r]->(b) "
                    "RETURN DISTINCT labels(a)[0] AS from_label, type(r) AS rel_type, labels(b)[0] AS to_label "
                    "LIMIT 500"
                )))
                for r in triples_result:
                    schema_info["triples"].append({
                        "from": r["from_label"],
                        "rel": r["rel_type"],
                        "to": r["to_label"]
                    })
            
            logger.info(
                f"成功获取 Neo4j schema: "
                f"{len(schema_info['labels'])} 个节点标签, "
                f"{len(schema_info['relationship_types'])} 个关系类型, "
                f"{len(schema_info['triples'])} 个三元组模式"
            )
            return schema_info
            
        except Exception as e:
            logger.error(f"获取 Neo4j schema 失败: {e}")
            return empty_schema

    @staticmethod
    def schema_to_natural_language(schema: Dict[str, Any]) -> str:
        """
        将 get_schema() 返回的 schema 字典转换为自然语言描述，
        可直接嵌入 Prompt 供 LLM 理解。
        """
        if not schema or not schema.get("labels"):
            return "当前知识图谱为空，暂无结构信息。"
        
        parts: List[str] = ["当前菜谱知识图谱包含以下结构：\n"]
        
        # 节点描述
        parts.append("【实体类型】")
        for label in schema["labels"]:
            props = schema.get("node_properties", {}).get(label, [])
            props_str = "、".join(props) if props else "无属性"
            parts.append(f"  • {label}（属性：{props_str}）")
        
        # 关系描述
        if schema.get("relationship_types"):
            parts.append("\n【关系类型】")
            for rel_type in schema["relationship_types"]:
                props = schema.get("relationship_properties", {}).get(rel_type, [])
                props_str = "、".join(props) if props else "无属性"
                parts.append(f"  • {rel_type}（属性：{props_str}）")
        
        # 三元组模式
        if schema.get("triples"):
            parts.append("\n【关系模式（实体→关系→实体）】")
            for t in schema["triples"]:
                parts.append(f"  • ({t['from']})-[{t['rel']}]->({t['to']})")
        
        return "\n".join(parts)
