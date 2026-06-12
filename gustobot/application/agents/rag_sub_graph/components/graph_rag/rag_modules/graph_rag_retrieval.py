"""
真正的图RAG检索模块
基于图结构的知识推理和检索，而非简单的关键词匹配
"""
import json
import re
from collections import defaultdict
from typing import List, Dict, Any, Optional
from enum import Enum
from langchain.schema import Document
from neo4j import GraphDatabase
from dataclasses import dataclass, field
from gustobot.infrastructure.core.logger import get_logger

logger = get_logger(service="GraphRAGRetrieval")

class QueryType(Enum):
    """查询类型枚举"""
    MULTI_HOP = "multi_hop"  # 顺向推导：A的详细步骤是什么？怎么做？
    SUBGRAPH = "subgraph"  # 全貌科普：川菜的相关知识网络是什么样的？
    REVERSE_SEARCH = "reverse_search" # 反向组合：我有土豆、牛肉、咖喱，能做出什么菜

@dataclass
class GraphQuery:
    """图查询结果"""
    query_type: QueryType
    source_entities: List[str]
    target_entities: List[str] = field(default_factory=list)
    relation_types: List[str] = field(default_factory=list)
    max_depth: int = 2
    max_nodes: int = 50
    constraints: Dict[str, Any] = field(default_factory=dict)

@dataclass
class GraphPath:
    """图路径结构"""
    nodes: List[Dict[str, Any]]
    relationships: List[Dict[str, Any]]
    path_length: int
    relevance_score: float
    path_type: str

@dataclass
class KnowledgeSubgraph:
    """知识子图结构"""
    central_nodes: List[Dict[str, Any]]
    connected_nodes: List[Dict[str, Any]]
    relationships: List[Dict[str, Any]]
    graph_metrics: Dict[str, Any]
    reasoning_chains: List[str]
    
class GraphRAGRetrieval:
    """
    真正的图RAG检索系统
    核心特点：
    1. 查询意图理解：识别图查询模式
    2. 多跳图遍历：深度关系探索
    3. 子图提取：相关知识网络
    4. 图结构推理：基于拓扑的推理
    5. 动态查询规划：自适应遍历策略
    """
    
    def __init__(self, config, llm_client):
        self.config = config
        self.llm_client = llm_client
        self.driver = None

        # 图结构缓存，在 hybrid_retrieval 中复用
        self.entity_cache = {}
        self.relation_cache = {}
        self.subgraph_cache = {}

        self._initialize()


    def _initialize(self):
        """初始化图RAG检索系统"""
        logger.info("初始化图RAG检索系统...")
        # 连接Neo4j
        try:
            self.driver = GraphDatabase.driver(
                self.config.neo4j_uri, 
                auth=(self.config.neo4j_user, self.config.neo4j_password)
            )
            # 测试连接
            with self.driver.session() as session:
                session.run("RETURN 1")
            logger.info("Neo4j连接成功")
        except Exception as e:
            logger.error(f"Neo4j连接失败: {e}")
            
        # 缓存图结构信息以加速后续查询
        self._build_graph_index()
        
    def _build_graph_index(self):
        """构建图索引以加速查询"""
        logger.info("构建图结构索引...")
        if not self.driver:
            logger.error("无法构建图索引: Neo4j驱动未初始化")
            return
        
        try:
            with self.driver.session() as session:
                # 构建实体索引 - 修复Neo4j语法兼容性问题
                entity_query = """
                MATCH (n)
                WHERE n.nodeId IS NOT NULL
                WITH n, COUNT { (n)--() } as degree
                RETURN labels(n) as node_labels, n.nodeId as node_id, 
                       n.name as name, n.category as category, degree
                ORDER BY degree DESC
                LIMIT 1000
                """
                
                result = session.run(entity_query)
                for record in result:
                    node_id = record["node_id"]
                    self.entity_cache[node_id] = {
                        "labels": record["node_labels"],
                        "name": record["name"],
                        "category": record["category"],
                        "degree": record["degree"]
                    }
                
                # 构建关系类型索引
                relation_query = """
                MATCH ()-[r]->()
                RETURN type(r) as rel_type, count(r) as frequency
                ORDER BY frequency DESC
                """
                
                result = session.run(relation_query)
                for record in result:
                    rel_type = record["rel_type"]
                    self.relation_cache[rel_type] = record["frequency"]
                    
                logger.info(f"索引构建完成: {len(self.entity_cache)}个实体, {len(self.relation_cache)}个关系类型")
                
        except Exception as e:
            logger.error(f"构建图索引失败: {e}")


    def graph_rag_search(self, query: str, top_k: int = 5) -> List[Document]:
        """
        图RAG主搜索接口：整合所有图RAG能力
        """
        logger.info(f"开始图RAG检索: {query}")
        try:
            query_intent = self.understand_graph_query(query)
            logger.info(f"查询意图理解结果: {query_intent}")

            if query_intent.query_type == QueryType.MULTI_HOP:
                paths = self.multi_hop_traversal(query_intent)
                documents = self._paths_to_documents(paths, query)
            elif query_intent.query_type == QueryType.SUBGRAPH:
                subgraph = self.extract_knowledge_subgraph(query_intent)
                reasoning_chains = self.graph_structure_reasoning(subgraph, query)
                documents = self._subgraph_to_documents(subgraph, reasoning_chains, query)
            elif query_intent.query_type == QueryType.REVERSE_SEARCH:
                reverse_results = self.reverse_ingredient_search(query_intent)
                documents = self._reverse_results_to_documents(reverse_results, query)
            else:
                logger.warning(f"未知的查询类型: {query_intent.query_type}")
                return []

            ranked_docs = self._rank_by_graph_relevance(documents, query)
            return ranked_docs[:top_k]

        except Exception as e:
            logger.error(f"图RAG检索失败: {e}")
            return []


    def understand_graph_query(self, query: str) -> GraphQuery:
        """
        理解查询的图结构意图
        这是图RAG的核心：从自然语言到图查询的转换
        """

        prompt = f"""
        作为图数据库专家，分析以下查询的图结构意图，并将自然语言问题映射到**已有图结构**上。
        
        已知图中大致有以下节点和关系：
        - 节点类型：
          - Recipe：菜谱节点，包含 name、description、cuisineType（如"川菜"）、category、tags、prepTime、cookTime 等属性
          - Ingredient：食材节点，包含 name、category（如"蔬菜"、"蛋白质" 等）
          - Category：菜品分类（如"川菜"、"家常菜"、"素菜"）
          - CookingStep：烹饪步骤
        - 主要关系：
          - (Recipe)-[:REQUIRES]->(Ingredient)
          - (Recipe)-[:BELONGS_TO_CATEGORY]->(Category)
          - (Recipe)-[:CONTAINS_STEP]->(CookingStep)
        
        请根据上述图结构分析下面的查询：
        
        查询：{query}
        
        请识别：
        1. 查询类型（必须严格在以下3个中选择其一）：
           - multi_hop: 顺向推导。需要探索实体间的关联、步骤或路径（如：鸡肉配什么蔬菜？需要从鸡肉推导到菜品再到蔬菜；或者询问某道菜的具体做法）
           - subgraph: 全貌科普。需要获取某个核心概念的完整知识子图（如：川菜有什么特色？麻婆豆腐的历史和周边知识是什么？）
           - reverse_search: 反向组合。已知多个底层实体（如零散的食材），反向寻找能够同时包含/需要它们的上层实体（如：我有土豆、牛肉、咖喱，能做出什么菜？）

        2. source_entities：
           - 只包含在图中**很有可能有对应节点**的具体实体名称
           - 优先选择：菜系（如"川菜"）、具体菜名（如"宫保鸡丁"）、食材名（如"鸡肉"、"豆腐"）
           - 不要把抽象概念或约束（如"糖尿病饮食限制"、"具体川菜菜品"、"健康饮食"、"30分钟内"）放进 source_entities
           - 特别注意：对于 reverse_search 查询，这里通常填入用户拥有的多个食材名称列表。
        
        3. target_entities：
           - 只在确实需要限制「路径终点」时填写
           - 同样只能使用可能出现在 Recipe / Ingredient / Category 节点上的名称（如"蔬菜"、"素菜"、具体菜名）
           - 如果不确定目标实体怎么映射到图中，请返回空列表 []
        
        4. relation_types：本次推理中希望优先考虑的关系类型列表
           - 例如：["REQUIRES", "BELONGS_TO_CATEGORY"]
        
        5. max_depth：建议的图遍历深度（1-3 之间的整数）
        
        6. constraints：可选的**属性级约束**，用于表达图结构之外的过滤条件，例如：
           - 健康/饮食限制（如"糖尿病"、"低糖"）
           - 时间限制（如"30分钟内"）
           - 口味偏好（如"清淡"、"少油"）
           用一个字典描述，例如：
           {{
             "health": ["糖尿病", "低糖"],
             "time": {{"max_minutes": 30}},
             "style": ["川菜"]
           }}
        
        示例1：
        查询："鸡肉配什么蔬菜好？"
        期望分析：这是 multi_hop 查询，需要通过"鸡肉→使用鸡肉的菜品→这些菜品使用的蔬菜"的路径推理。
        
        返回JSON示例：
        {{
          "query_type": "multi_hop",
          "source_entities": ["鸡肉"],
          "target_entities": ["蔬菜"],
          "relation_types": ["REQUIRES", "BELONGS_TO_CATEGORY"],
          "max_depth": 3,
          "constraints": {{}}
        }}
        
        示例2：
        查询："适合糖尿病人吃的低糖川菜有哪些，并且制作时间不超过30分钟？"
        期望分析：
          - 图中可以直接对应的实体：主要是菜系 "川菜"
          - 糖尿病/低糖/30分钟 属于属性级约束，不能当作节点
          - 可以使用 subgraph 或 multi_hop，以 "川菜" 为核心实体，结合属性约束做后续过滤

        示例3：
        查询："冰箱里有土豆、牛肉和咖喱，能做什么菜？"
        期望分析：这是 reverse_search 查询，需要反向寻找同时 REQUIRES 这三种食材的菜谱。
        
        返回JSON示例：
        {{
          "query_type": "reverse_search",
          "source_entities": ["土豆", "牛肉", "咖喱"],
          "target_entities": [],
          "relation_types": ["REQUIRES"],
          "max_depth": 1,
          "constraints": {{}}
        }}
        
        返回JSON示例：
        {{
          "query_type": "subgraph",
          "source_entities": ["川菜"],
          "target_entities": [],
          "relation_types": ["BELONGS_TO_CATEGORY", "REQUIRES"],
          "max_depth": 2,
          "constraints": {{
            "health": ["糖尿病", "低糖"],
            "time": {{"max_minutes": 30}}
          }}
        }}
        
        请严格返回一个合法的 JSON 对象，不要包含任何多余的说明文字。
        """
        try:
            logger.info(f"理解查询意图: {query}")
            response = self.llm_client.chat.completions.create(
                model=self.config.llm_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=1000
            )
            result = json.loads(response.choices[0].message.content.strip())

            return GraphQuery(
                query_type=QueryType(result.get("query_type", "subgraph")),
                source_entities=result.get("source_entities", []),
                target_entities=result.get("target_entities", []),
                relation_types=result.get("relation_types", []),
                max_depth=result.get("max_depth", 2),
                max_nodes=50,
                constraints=result.get("constraints", {})
            )
        except Exception as e:
            logger.error(f"查询意图理解失败: {e}")
            # 返回一个默认的 GraphQuery 对象
            return GraphQuery(
                query_type=QueryType.SUBGRAPH,
                source_entities=[query],
                max_depth=2
            )


    def multi_hop_traversal(self, graph_query: GraphQuery) -> List[GraphPath]:
        """
        多跳图、实体关系、路径查找：根据查询类型执行不同的图遍历策略
        """
        logger.info(f"执行多跳遍历: {graph_query.source_entities} -> {graph_query.target_entities}")

        paths = []

        if not self.driver:
            logger.error("无法执行多跳遍历: Neo4j驱动未初始化")
            return paths

        try:
            with self.driver.session() as session:
                source_entities = graph_query.source_entities
                target_keywords = graph_query.target_entities or [] # 目标实体可能是模糊关键词，需要在路径终点进行匹配筛选
                max_depth = graph_query.max_depth
                relation_types = graph_query.relation_types

                # 对目标节点进行模糊匹配筛选
                target_filter_clause = ""
                if target_keywords:
                    target_filter_clause = """
                    AND ANY(kw IN $target_keywords WHERE
                        (target.name IS NOT NULL AND (toString(target.name) CONTAINS kw OR kw CONTAINS toString(target.name))) OR
                        (target.category IS NOT NULL AND (toString(target.category) CONTAINS kw OR kw CONTAINS toString(target.category)))
                    )"""
                
                cypher_query = f"""
                    // 多跳推理查询
                    UNWIND $source_entities as source_name
                    MATCH (source)
                    WHERE source.name CONTAINS source_name OR source.nodeId = source_name
                    
                    // 执行多跳遍历
                    MATCH path = (source)-[*1..{max_depth}]-(target)
                    WHERE NOT source = target{target_filter_clause}
                        
                    // 计算路径相关性
                    WITH path, source, target,
                            length(path) as path_len,
                            relationships(path) as rels,
                            nodes(path) as path_nodes
                    
                    // 路径评分：短路径 + 高度数节点 + 关系类型匹配
                    WITH path, source, target, path_len, rels, path_nodes,
                            (1.0 / path_len) + 
                            (REDUCE(s = 0.0, n IN path_nodes | s + COUNT {{ (n)--() }}) / 10.0 / size(path_nodes)) +
                            (CASE WHEN ANY(r IN rels WHERE type(r) IN $relation_types) THEN 0.3 ELSE 0.0 END) as relevance
                    
                    ORDER BY relevance DESC
                    LIMIT 20
                    
                    RETURN path, source, target, path_len, rels, path_nodes, relevance
                    """
                params = {
                    "source_entities": source_entities,
                    "relation_types": relation_types or [],
                }
                if target_keywords:
                    params["target_keywords"] = target_keywords

                result = session.run(cypher_query, params)  # ty:ignore[invalid-argument-type]
                paths = []
                for record in result:
                    path_data = self._parse_neo4j_path(record)
                    if path_data:
                        paths.append(path_data)

                return paths

        except Exception as e:
            logger.error(f"遍历失败: {e}")
            return paths


    def _parse_neo4j_path(self, record) -> Optional[GraphPath]:
        """解析Neo4j路径记录"""
        try:
            path_nodes = []
            for node in record["path_nodes"]:
                path_nodes.append({
                    "id": node.get("nodeId", ""),
                    "name": node.get("name", ""),
                    "labels": list(node.labels),
                    "properties": dict(node)
                })
            
            relationships = []
            for rel in record["rels"]:
                relationships.append({
                    "type": rel.type,
                    "properties": dict(rel)
                })
            
            return GraphPath(
                nodes=path_nodes,
                relationships=relationships,
                path_length=record["path_len"],
                relevance_score=record["relevance"],
                path_type="multi_hop"
            )
        except Exception as e:
            logger.error(f"解析Neo4j路径失败: {e}")
            return None


    def extract_knowledge_subgraph(self, graph_query: GraphQuery) -> KnowledgeSubgraph:
        """
        提取知识子图：获取实体相关的完整知识网络
        这体现了图RAG的整体性思维
        """
        logger.info(f"提取知识子图: {graph_query.source_entities}")
        if not self.driver:
            logger.error("无法提取知识子图: Neo4j驱动未初始化")
            return self._fallback_subgraph_extraction(graph_query)
        
        try:
            with self.driver.session() as session:
                cypher_query = f"""
                // 找到源实体
                UNWIND $source_entities as entity_name
                MATCH (source)
                WHERE source.name CONTAINS entity_name 
                   OR source.nodeId = entity_name
                
                // 获取指定深度的邻居
                MATCH path = (source)-[r*1..{graph_query.max_depth}]-(neighbor)
                UNWIND nodes(path) AS single_node
                UNWIND relationships(path) AS single_rel
                WITH source, 
                    collect(DISTINCT single_node) AS neighbors, 
                    collect(DISTINCT single_rel) AS relationships
                WHERE size(neighbors) <= $max_nodes
                
                // 计算图指标
                WITH source, neighbors, relationships,
                     size(neighbors) as node_count,
                     size(relationships) as rel_count
                
                RETURN 
                    source,
                    neighbors[0..{graph_query.max_nodes}] as nodes,
                    relationships[0..{graph_query.max_nodes}] as rels,
                    {{
                        node_count: node_count,
                        relationship_count: rel_count,
                        density: CASE WHEN node_count > 1 THEN toFloat(rel_count) / (node_count * (node_count - 1) / 2) ELSE 0.0 END
                    }} as metrics
                """

                result = session.run(cypher_query,{  # type: ignore
                    "source_entities": graph_query.source_entities,
                    "max_nodes": graph_query.max_nodes
                })

                # 只有一条记录，包含完整的子图信息
                record = result.single()
                if record:
                    logger.info(f"知识子图提取成功: {record}")
                    return self._build_knowledge_subgraph(record)
                else:
                    logger.warning("没有找到相关的知识子图")
                    return self._fallback_subgraph_extraction(graph_query)

        except Exception as e:
            logger.error(f"提取知识子图失败: {e}")
            return self._fallback_subgraph_extraction(graph_query)


    def graph_structure_reasoning(self, subgraph: KnowledgeSubgraph, query: str) -> List[str]:
        """
        基于图结构的推理：这是图RAG的智能之处
        不仅检索信息，还能进行逻辑推理
        """
        logger.info("执行图结构推理...")
        reasoning_chains = []
        try:
            reasoning_patterns = self._identify_reasoning_patterns(subgraph)

            for pattern in reasoning_patterns:
                chain_text = self._build_reasoning_chain(pattern, subgraph)
                if chain_text:
                    reasoning_chains.append(chain_text)
                
            valid_chains = self._validate_reasoning_chains(reasoning_chains, query)
            logger.info(f"图结构推理完成，生成 {len(valid_chains)} 条推理链")
            return valid_chains

        except Exception as e:
            logger.error(f"图结构推理失败: {e}")
        return []


    def _build_knowledge_subgraph(self, record) -> KnowledgeSubgraph:
        """构建知识子图对象"""
        try:
            central_nodes = [dict(record["source"])]
            connected_nodes = [dict(node) for node in record["nodes"]]
            relationships = []
            for rel in record["rels"]:
                rel_dict = dict(rel)
                rel_dict["type"] = rel.type
                rel_dict["source_name"] = rel.start_node.get("name", "") if rel.start_node else ""
                rel_dict["target_name"] = rel.end_node.get("name", "") if rel.end_node else ""
                relationships.append(rel_dict)
            
            return KnowledgeSubgraph(
                central_nodes=central_nodes,
                connected_nodes=connected_nodes,
                relationships=relationships,
                graph_metrics=record["metrics"], # 节点数、关系数、密度等指标
                reasoning_chains=[]
            )
        except Exception as e:
            logger.error(f"构建知识子图失败: {e}")
            return KnowledgeSubgraph(
                central_nodes=[],
                connected_nodes=[],
                relationships=[],
                graph_metrics={},
                reasoning_chains=[]
            )


    def reverse_ingredient_search(self, graph_query: GraphQuery) -> List[Dict[str, Any]]:
        """
        反向食材搜索：给定若干食材，反向找到能用这些食材制作的菜谱
        核心策略：
        1. 匹配度优先：优先返回覆盖用户食材最多的菜谱
        2. 可行性评估：计算菜谱所需食材中用户已有的比例
        3. 缺失提示：告知用户还缺少哪些食材
        """
        logger.info(f"执行反向食材搜索: {graph_query.source_entities}")

        if not self.driver:
            logger.error("无法执行反向搜索: Neo4j驱动未初始化")
            return []

        try:
            with self.driver.session() as session:
                ingredients = graph_query.source_entities
                constraints = graph_query.constraints or {}

                # 找到包含任一食材的菜谱，按匹配数量排序
                cypher_query = """
                    // 1. 找到与用户食材匹配的 Ingredient 节点
                    UNWIND $ingredients AS ing_name
                    MATCH (i:Ingredient)
                    WHERE i.name CONTAINS ing_name OR ing_name CONTAINS i.name
                    WITH collect(DISTINCT i) AS matched_ingredients, $ingredients AS raw_names

                    // 2. 找到 REQUIRES 这些食材的菜谱
                    UNWIND matched_ingredients AS mi
                    MATCH (r:Recipe)-[:REQUIRES]->(mi)
                    WITH r, matched_ingredients, raw_names,
                         collect(DISTINCT mi.name) AS hit_ingredient_names

                    // 3. 获取该菜谱的全部所需食材
                    MATCH (r)-[:REQUIRES]->(all_ing:Ingredient)
                    WITH r, hit_ingredient_names, raw_names,
                         collect(DISTINCT all_ing.name) AS all_ingredient_names

                    // 4. 计算匹配度和覆盖率
                    WITH r,
                         hit_ingredient_names,
                         all_ingredient_names,
                         size(hit_ingredient_names) AS hit_count,
                         size(all_ingredient_names) AS total_count,
                         toFloat(size(hit_ingredient_names)) / size(all_ingredient_names) AS coverage,
                         [x IN all_ingredient_names WHERE NOT x IN hit_ingredient_names] AS missing_ingredients

                    // 5. 排序：命中数量 DESC → 覆盖率 DESC
                    ORDER BY hit_count DESC, coverage DESC
                    LIMIT 20

                    RETURN r.name AS recipe_name,
                           r.nodeId AS recipe_id,
                           r.description AS description,
                           r.cuisineType AS cuisine_type,
                           r.prepTime AS prep_time,
                           r.cookTime AS cook_time,
                           r.difficulty AS difficulty,
                           r.tags AS tags,
                           hit_ingredient_names AS matched_ingredients,
                           all_ingredient_names AS all_ingredients,
                           missing_ingredients,
                           hit_count,
                           total_count,
                           coverage
                    """

                result = session.run(cypher_query, {"ingredients": ingredients})

                recipes = []
                for record in result:
                    recipe = {
                        "recipe_name": record["recipe_name"],
                        "recipe_id": record["recipe_id"],
                        "description": record["description"],
                        "cuisine_type": record["cuisine_type"],
                        "prep_time": record["prep_time"],
                        "cook_time": record["cook_time"],
                        "difficulty": record["difficulty"],
                        "labels": record["tags"],
                        "matched_ingredients": record["matched_ingredients"],
                        "all_ingredients": record["all_ingredients"],
                        "missing_ingredients": record["missing_ingredients"],
                        "hit_count": record["hit_count"],
                        "total_count": record["total_count"],
                        "coverage": record["coverage"],
                    }
                    recipes.append(recipe)

                # 应用属性级约束过滤
                if constraints:
                    recipes = self._apply_reverse_constraints(recipes, constraints)

                logger.info(f"反向搜索完成，找到 {len(recipes)} 个匹配菜谱")
                return recipes

        except Exception as e:
            logger.error(f"反向搜索失败: {e}")
            return []

    def _apply_reverse_constraints(self, recipes: List[Dict[str, Any]], 
                                    constraints: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        对反向搜索结果应用属性级约束过滤
        如：时间限制、菜系偏好、健康标签等
        """
        filtered = recipes

        # 时间约束
        time_constraint = constraints.get("time", {})
        max_minutes = time_constraint.get("max_minutes")
        if max_minutes is not None:
            filtered = [
                r for r in filtered
                if r.get("cook_time") is None or self._parse_minutes(r["cook_time"]) <= max_minutes
            ]

        # 菜系约束
        style = constraints.get("style", [])
        if style:
            filtered = [
                r for r in filtered
                if r.get("cuisine_type") and any(s in r["cuisine_type"] for s in style)
            ]

        return filtered

    @staticmethod
    def _parse_minutes(time_str) -> float:
        """尝试从时间字符串中解析分钟数"""
        if isinstance(time_str, (int, float)):
            return float(time_str)
        match = re.search(r'(\d+)', str(time_str))
        return float(match.group(1)) if match else float('inf')


    def _reverse_results_to_documents(self, results: List[Dict[str, Any]], query: str) -> List[Document]:
        """
        将反向搜索结果转换为 Document 对象
        重点：生成对 LLM 友好的结构化自然语言描述
        """
        documents = []
        for r in results:
            # 构建描述
            desc_parts = []
            desc_parts.append(f"### 菜谱: {r['recipe_name']}")
            if r.get("description"):
                desc_parts.append(f"简介: {r['description']}")
            if r.get("cuisine_type"):
                desc_parts.append(f"菜系: {r['cuisine_type']}")

            matched = r.get("matched_ingredients", [])
            missing = r.get("missing_ingredients", [])
            all_ing = r.get("all_ingredients", [])
            coverage_pct = round(r.get("coverage", 0) * 100, 1)

            desc_parts.append(f"食材匹配: 共需 {len(all_ing)} 种食材，你已有 {len(matched)} 种 ({coverage_pct}%)")
            desc_parts.append(f"已有食材: {', '.join(matched)}")
            if missing:
                desc_parts.append(f"还需购买: {', '.join(missing)}")
            else:
                desc_parts.append("你拥有该菜谱的全部食材！")

            if r.get("prep_time") or r.get("cook_time"):
                time_info = []
                if r.get("prep_time"):
                    time_info.append(f"备料 {r['prep_time']}")
                if r.get("cook_time"):
                    time_info.append(f"烹饪 {r['cook_time']}")
                desc_parts.append(f"时间: {' | '.join(time_info)}")

            if r.get("difficulty"):
                desc_parts.append(f"难度: {r['difficulty']}")

            doc = Document(
                page_content="\n".join(desc_parts),
                metadata={
                    "type": "reverse_search",
                    "recipe_name": r.get("recipe_name", ""),
                    "relevance_score": r.get("coverage", 0.0),
                    "hit_count": r.get("hit_count", 0),
                    "total_ingredients": r.get("total_count", 0),
                    "coverage": r.get("coverage", 0.0),
                    "missing_ingredients": missing,
                }
            )
            documents.append(doc)

        return documents


    def _paths_to_documents(self, paths: List[GraphPath], query: str) -> List[Document]:
        """将图路径转换为Document对象"""
        try:
            documents = []
            
            for i, path in enumerate(paths):
                # 构建路径描述
                path_desc = self._build_path_description(path)
                
                doc = Document(
                    page_content=path_desc,
                    metadata={
                        "type": "graph_path",
                        "path_length": path.path_length,
                        "relevance_score": path.relevance_score,
                        "path_type": path.path_type,
                        "node_count": len(path.nodes),
                        "relationship_count": len(path.relationships),
                        "recipe_name": path.nodes[0].get("name", "路径") if path.nodes else "路径"
                    }
                )
                documents.append(doc)
                
            return documents
        except Exception as e:
            logger.error(f"构建Document对象失败: {e}")
            return []


    def _subgraph_to_documents(self, subgraph: KnowledgeSubgraph, 
                              reasoning_chains: List[str], query: str) -> List[Document]:
        """将知识子图转换为Document对象"""
        try:
            logger.info("正在将知识子图转换为Document对象···")
            documents = []
            if reasoning_chains:
                subgraph.reasoning_chains = reasoning_chains

            # 构建子图描述
            subgraph_desc = self._build_subgraph_description(subgraph)
            
            # 计算子图相关性分数：综合密度、节点规模和推理链数量
            density = subgraph.graph_metrics.get("density", 0.0)
            chain_bonus = min(len(reasoning_chains) * 0.1, 0.5)
            node_bonus = min(len(subgraph.connected_nodes) / 100.0, 0.3)
            relevance_score = round(density + chain_bonus + node_bonus, 4)

            doc = Document(
                page_content=subgraph_desc,
                metadata={
                    "type": "knowledge_subgraph",
                    "node_count": len(subgraph.connected_nodes),
                    "relationship_count": len(subgraph.relationships),
                    "graph_density": density,
                    "reasoning_chains": reasoning_chains,
                    "relevance_score": relevance_score,
                    "recipe_name": subgraph.central_nodes[0].get("name", "知识子图") if subgraph.central_nodes else "知识子图"
                }
            )
            documents.append(doc)
                
            return documents
        except Exception as e:
            logger.error(f"构建Document对象失败: {e}")
            return []
        

    def _build_path_description(self, path: GraphPath) -> str:
        """构建路径的自然语言描述"""
        try:
            logger.info("正在构建路径描述···")
            if not path.nodes:
                return "空路径"

            path_desc = []
            for i, node in enumerate(path.nodes):
                path_desc.append(node.get('name', f'节点{i}'))
                if i < len(path.relationships):
                    rel_type = path.relationships[i].get("type", f"关系{i}")
                    path_desc.append(f" --{rel_type}--> ")
            return "".join(path_desc)

        except Exception as e:
            logger.error(f"构建路径描述失败: {e}")
            return "空路径"

    
    def _build_subgraph_description(self, subgraph: KnowledgeSubgraph) -> str:
        """构建子图的自然语言描述"""
        if not subgraph.central_nodes and not subgraph.connected_nodes:
            return "当前子图为空，未找到相关图谱信息。"

        desc_parts: List[str] = []
        
        # 1. 核心实体与网络规模概览 (为大模型奠定全局上下文)
        central_names = [n.get("name", f"节点{i}") for i, n in enumerate(subgraph.central_nodes)]
        node_count = len(subgraph.connected_nodes) + len(subgraph.central_nodes)
        rel_count = len(subgraph.relationships)
        
        desc_parts.append("### 【知识子图概览】")
        desc_parts.append(f"- 核心探讨实体: {', '.join(central_names)}")
        desc_parts.append(f"- 图谱规模: 包含 {node_count} 个关联节点，{rel_count} 条拓扑连线。")
        
        # 2. 按关系类型进行拓扑聚合 (核心优化点：消除冗余边描述)
        # 将散乱的 (A)-[R]->(B1), (A)-[R]->(B2) 聚合为 R: B1, B2
        relation_groups = defaultdict(list)
        for i, rel in enumerate(subgraph.relationships):
            # 假设 rel 具有 source_name, target_name, type 属性
            relation_groups[rel.get("type", f"关系{i}")].append(rel.get("target_name", f"目标节点{i}"))
            
        if relation_groups:
            desc_parts.append("\n### 【实体关联网络】")
            # 将底层图谱 Schema 映射为 LLM 容易理解的业务自然语言
            rel_type_mapping = {
                "REQUIRES": "所需核心食材",
                "BELONGS_TO_CATEGORY": "所属菜系/分类",
                "CONTAINS_STEP": "关键制作步骤",
                "CAN_SUBSTITUTE": "可替代选项"
            }
            
            for rel_type, targets in relation_groups.items():
                friendly_name = rel_type_mapping.get(rel_type, rel_type)
                # 去重处理，避免同一目标被反复提及
                unique_targets = list(dict.fromkeys(targets))
                
                # 截断保护：防止超大星型网络撑爆 LLM 窗口
                if len(unique_targets) > 20:
                    display_targets = ", ".join(unique_targets[:20])
                    display_targets += f" ...等 (共{len(unique_targets)}项)"
                else:
                    display_targets = ", ".join(unique_targets)
                    
                desc_parts.append(f"- **{friendly_name}**: {display_targets}")

        # 3. 核心节点高价值属性提取 (过滤掉长文本噪音，只保留标量特征)
        if subgraph.central_nodes:
            desc_parts.append("\n### 【核心节点特征】")
            for node in subgraph.central_nodes:
                props = node.get("properties", {})
                if props:
                    # 只提取对推理有实质帮助的关键属性
                    essential_keys = ['prepTime', 'cookTime', 'difficulty', 'cuisineType', 'taste']
                    essential_props = {k: v for k, v in props.items() if k in essential_keys}
                    
                    if essential_props:
                        prop_str = " | ".join([f"{k}: {v}" for k, v in essential_props.items()])
                        desc_parts.append(f"- {node.get('name', '未知节点')}: {prop_str}")
        
        # 4. 补充图谱计算得出的推理链
        if hasattr(subgraph, 'reasoning_chains') and subgraph.reasoning_chains:
            desc_parts.append("\n### 【拓扑推理路径】")
            # 最多保留 3 条最具代表性的路径
            for chain in subgraph.reasoning_chains[:3]: 
                desc_parts.append(f"- {chain}")
                
        return "\n".join(desc_parts) 


    def _rank_by_graph_relevance(self, documents: List[Document], query: str) -> List[Document]:
        """基于图结构相关性排序"""
        return sorted(documents, key=lambda x: x.metadata.get("relevance_score", 0.0), reverse=True)

    
    def _identify_reasoning_patterns(self, subgraph: KnowledgeSubgraph) -> List[str]:
        """
        基于子图的拓扑结构识别可用推理模式
        分析关系类型分布和节点连接特征，返回推理模式标签列表
        """
        try:
            logger.info("正在识别推理模式···")
            patterns = []
            if not subgraph.relationships:
                return ["通用关联"]

            # 统计关系类型分布
            rel_type_counts: Dict[str, int] = defaultdict(int)
            for rel in subgraph.relationships:
                rel_type_counts[rel.get("type", "UNKNOWN")] += 1

            # 组成关系：菜谱由食材/步骤组成
            if "REQUIRES" in rel_type_counts or "CONTAINS_STEP" in rel_type_counts:
                patterns.append("组成关系")

            # 分类关系：菜谱属于某菜系/分类
            if "BELONGS_TO_CATEGORY" in rel_type_counts:
                patterns.append("分类关系")

            # 替代关系：食材可被替换
            if "CAN_SUBSTITUTE" in rel_type_counts:
                patterns.append("替代关系")

            # 共现关系：多个同类节点连接到同一中心节点（如多种蔬菜出现在同一菜谱）
            if len(subgraph.connected_nodes) > 3:
                node_categories: Dict[str, int] = defaultdict(int)
                for node in subgraph.connected_nodes:
                    cat = node.get("category", "unknown")
                    node_categories[cat] += 1
                if any(count >= 2 for count in node_categories.values()):
                    patterns.append("共现关系")

            # 流程链关系：存在多个烹饪步骤，可推理制作顺序
            if rel_type_counts.get("CONTAINS_STEP", 0) > 1:
                patterns.append("流程链关系")

            return patterns if patterns else ["通用关联"]
        except Exception as e:
            logger.error(f"识别推理模式失败: {e}")
            return ["通用关联"]

    def _build_reasoning_chain(self, pattern: str, subgraph: KnowledgeSubgraph) -> Optional[str]:
        """
        根据推理模式，从子图数据中构建一条结构化推理链
        每种模式对应不同的信息聚合策略
        """
        try:
            logger.info(f"正在构建推理链，模式: {pattern}···")
            if not subgraph.central_nodes:
                return None

            central_name = subgraph.central_nodes[0].get("name", "核心实体")

            # 按关系类型聚合目标节点
            rel_groups: Dict[str, List[str]] = defaultdict(list)
            for rel in subgraph.relationships:
                target = rel.get("target_name", "")
                if target:
                    rel_groups[rel.get("type", "UNKNOWN")].append(target)

            if pattern == "组成关系":
                ingredients = list(dict.fromkeys(rel_groups.get("REQUIRES", [])))[:8]
                steps = list(dict.fromkeys(rel_groups.get("CONTAINS_STEP", [])))
                parts = []
                if ingredients:
                    parts.append(f"需要食材: {', '.join(ingredients)}")
                if steps:
                    parts.append(f"包含 {len(steps)} 个制作步骤")
                return f"[组成] {central_name} → {'；'.join(parts)}" if parts else None

            elif pattern == "分类关系":
                categories = list(dict.fromkeys(rel_groups.get("BELONGS_TO_CATEGORY", [])))[:5]
                return f"[分类] {central_name} → 属于: {', '.join(categories)}" if categories else None

            elif pattern == "替代关系":
                substitutes = list(dict.fromkeys(rel_groups.get("CAN_SUBSTITUTE", [])))[:5]
                return f"[替代] {central_name} → 可替代为: {', '.join(substitutes)}" if substitutes else None

            elif pattern == "共现关系":
                all_targets = []
                for targets in rel_groups.values():
                    all_targets.extend(targets)
                unique_targets = list(dict.fromkeys(all_targets))[:6]
                return f"[共现] 与 {central_name} 高度关联: {', '.join(unique_targets)}" if unique_targets else None

            elif pattern == "流程链关系":
                steps = list(dict.fromkeys(rel_groups.get("CONTAINS_STEP", [])))[:5]
                return f"[流程] {central_name} 的制作流程: {'→'.join(steps)}" if steps else None

            else:  # 通用关联
                info_parts = []
                for rel_type, targets in rel_groups.items():
                    unique = list(dict.fromkeys(targets))[:3]
                    info_parts.append(f"{rel_type}: {', '.join(unique)}")
                return f"[关联] {central_name} → {'；'.join(info_parts[:3])}" if info_parts else None
        except Exception as e:
            logger.error(f"构建推理链失败: {e}")
            return None

    def _validate_reasoning_chains(self, chains: List[str], query: str) -> List[str]:
        """
        对推理链进行质量评估和筛选
        综合考量：内容长度、与查询的关键词重叠度、信息丰度
        """
        try:
            logger.info("正在评估推理链质量···")
            if not chains:
                return []

            # 提取查询中的中文词组和英文词作为关键词集合
            query_tokens = set(re.findall(r'[\u4e00-\u9fff]{2,}|[a-zA-Z]+', query))

            scored_chains: List[tuple] = []
            for chain_text in chains:
                # 过滤过短的无效推理链
                if len(chain_text) < 5:
                    continue

                score = 1.0  # 基础分

                # 关键词重叠度：推理链中包含查询关键词越多越好
                chain_tokens = set(re.findall(r'[\u4e00-\u9fff]{2,}|[a-zA-Z]+', chain_text))
                overlap = query_tokens & chain_tokens # 求查询和推理链的关键词重叠
                score += len(overlap) * 0.5

                # 信息丰度：推理链中包含的实体/元素数量
                entity_count = len(re.split(r'[,，→;；]', chain_text))
                score += min(entity_count * 0.2, 2.0)

                # 推理模式标记加分
                if any(tag in chain_text for tag in ['[组成]', '[分类]', '[替代]', '[共现]', '[流程]', '[关联]']):
                    score += 0.5

                scored_chains.append((chain_text, score))

            # 按得分降序，取前 3 条
            scored_chains.sort(key=lambda x: x[1], reverse=True)
            return [c for c, _ in scored_chains[:3]]
        except Exception as e:
            logger.error(f"评估推理链失败: {e}")
            return []

    
    def _fallback_subgraph_extraction(self, graph_query: GraphQuery) -> KnowledgeSubgraph:
        """降级子图提取，返回子图对象防止后续处理失败"""
        return KnowledgeSubgraph(
            central_nodes=[],
            connected_nodes=[],
            relationships=[],
            graph_metrics={},
            reasoning_chains=[]
        )

    
    def close(self):
        """关闭资源连接"""
        logger.info("正在关闭GraphRAGRetrieval资源连接···")
        if self.driver:
            self.driver.close()
            self.driver = None