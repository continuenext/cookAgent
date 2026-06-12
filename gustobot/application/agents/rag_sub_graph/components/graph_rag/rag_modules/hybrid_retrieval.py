"""
混合检索模块
基于双层检索范式：实体级 + 主题级检索
结合图结构检索和向量检索，使用Round-robin轮询策略
"""

import json
import logging
from typing import List, Dict, Tuple, Any
from dataclasses import dataclass

from langchain_core.documents import Document
from langchain_community.retrievers import BM25Retriever
from neo4j import GraphDatabase
from .graph_indexing import GraphIndexingModule
from gustobot.infrastructure.core.logger import get_logger

logger = get_logger(service="HybridRetrievalModule")

@dataclass
class RetrievalResult:
    """检索结果数据结构"""
    content: str
    node_id: str
    node_type: str
    relevance_score: float
    retrieval_level: str  # 'entity' or 'topic'
    metadata: Dict[str, Any]


class HybridRetrievalModule:
    """
    混合检索模块
    核心特点：
    1. 双层检索范式（实体级 + 主题级）
    2. 关键词提取和匹配
    3. 图结构+向量检索结合
    4. 一跳邻居扩展
    5. Round-robin轮询合并策略
    """
    
    def __init__(self, config, milvus_module, data_module, llm_client):
        self.config = config
        self.milvus_module = milvus_module
        self.data_module = data_module
        self.llm_client = llm_client
        
        self.driver = None
        self.bm25_retriever = None
        
        # 图索引模块
        self.graph_indexing = GraphIndexingModule(config, llm_client)
        self.graph_index = None
        
    def initialize(self, chunks: List[Document]):
        """初始化检索系统"""
        logger.info("初始化混合检索模块...")
        try:
            self.driver = GraphDatabase.driver(self.config.neo4j_uri, auth=(self.config.neo4j_user, self.config.neo4j_password))
            
            if chunks:
                self.bm25_retriever = BM25Retriever.from_documents(chunks) # 输出一个可以"按关键词打分排序"的检索器对象
                logger.info(f"BM25检索器初始化完成，文档数量: {len(chunks)}")
            
            # 构建图索引
            if not self.graph_index:
                self._build_graph_index()

        except Exception as e:
            logger.error(f"混合检索模块初始化失败: {e}")
            raise e
        

    def _build_graph_index(self):
        """构建图索引"""
        logger.info("开始构建图索引...")
        try:
            recipes = self.data_module.recipes
            ingredients = self.data_module.ingredients
            cooking_steps = self.data_module.cooking_steps
            self.graph_indexing.create_entity_key_values(recipes, ingredients, cooking_steps)

            relationships = self._extract_relation_from_graph()
            self.graph_indexing.create_relation_key_values(relationships)

            self.graph_indexing.deduplicate_entities_and_relations()

            self.graph_index = True
            # 统计信息
            stats = self.graph_indexing.get_statistics()

            logger.info(f"图索引构建完成: {stats}")
        except Exception as e:
            logger.error(f"图索引构建失败: {e}")
            raise e

    def _extract_relation_from_graph(self) -> List[Tuple[str, str, str]]:
        """从Neo4j图中提取关系"""
        if not self.driver:
            logger.warning("Neo4j驱动未初始化，无法提取关系")
            return []
        try:
            logger.info("从Neo4j图中提取关系...")
            relationships = []
            query = """
                MATCH (source)-[r]->(target)
                WHERE source.nodeId >= '200000000' OR target.nodeId >= '200000000'
                RETURN source.nodeId as source_id, type(r) as relation_type, target.nodeId as target_id
                LIMIT 1000
                """
            with self.driver.session() as session:
                result = session.run(query)
                for record in result:
                    relationships.append((record["source_id"], record["relation_type"], record["target_id"]))
            logger.info(f"提取到 {len(relationships)} 条关系")
            return relationships

        except Exception as e:
            logger.error(f"提取关系失败: {e}")
            return []


    def hybrid_search(self, query: str, top_k: int = 5) -> List[Document]:
        """
        混合检索：使用Round-robin轮询合并策略
        公平轮询合并不同检索结果，不使用权重配置
        """
        logger.info(f"开始混合检索: {query}")
        try:
            # 双层检索：实体级检索+主体级检索
            dual_docs = self.dual_level_retrieval(query, top_k)
            # 向量检索增强：BM25 + 向量检索
            vector_docs = self.vector_search_enhanced(query, top_k)

            # Round-robin 轮询合并
            merged_docs = []
            saved_doc_ids = set()
            max_len = max(len(dual_docs), len(vector_docs))
            origin_len = len(dual_docs) + len(vector_docs)

            for i in range(max_len):
                # 双层检索
                if i < len(dual_docs):
                    doc = dual_docs[i]
                    doc_id = doc.metadata.get("node_id", hash(doc.page_content))
                    if doc_id not in saved_doc_ids:
                        doc.metadata["search_method"] = "dual_level"
                        doc.metadata["round_robin_order"] = len(merged_docs)
                        if "final_score" not in doc.metadata:
                            doc.metadata["final_score"] = doc.metadata.get("relevance_score", 0)
                        merged_docs.append(doc)
                        saved_doc_ids.add(doc_id)

                # 向量检索增强
                if i < len(vector_docs):
                    doc = vector_docs[i]
                    doc_id = doc.metadata.get("node_id", hash(doc.page_content))
                    if doc_id not in saved_doc_ids:
                        doc.metadata["search_method"] = "vector_enhanced"
                        doc.metadata["round_robin_order"] = len(merged_docs)
                        # vector_search_enhanced 已通过 RRF 计算好 final_score，直接保留
                        if "final_score" not in doc.metadata:
                            doc.metadata["final_score"] = 0.0
                        merged_docs.append(doc)
                        saved_doc_ids.add(doc_id)

            final_docs = merged_docs[:top_k]
            logger.info(f"Round-robin合并：从总共{origin_len}个结果合并为{len(final_docs)}个文档")
            logger.info(f"混合检索完成，返回 {len(final_docs)} 个文档")
            return final_docs
        except Exception as e:
            logger.error(f"混合检索失败: {e}")
            return []
    

    def dual_level_retrieval(self, query: str, top_k: int = 5) -> List[Document]:
        """
        双层检索：结合实体级和主题级检索
        """
        logger.info(f"开始双层检索: {query}")
        try:
            entity_keywords, topic_keywords = self.extract_query_keywords(query)
            
            entity_results = self.entity_level_retrieval(entity_keywords, top_k)
            topic_results = self.topic_level_retrieval(topic_keywords, top_k)
            all_results = entity_results + topic_results

            # 去重和排序
            seen_node_ids = set()
            unique_results: List[RetrievalResult] = []
            for res in sorted(all_results, key=lambda x: x.relevance_score, reverse=True):
                if res.node_id not in seen_node_ids:
                    unique_results.append(res)
                    seen_node_ids.add(res.node_id)

            documents = []
            for result in unique_results[:top_k]:
                recipe_name = result.metadata.get("name") or result.metadata.get("entity_name", "未知菜谱")
                doc = Document(
                    page_content=result.content,
                    metadata={
                        "node_id": result.node_id,
                        "node_type": result.node_type,
                        "relevance_score": result.relevance_score,
                        "retrieval_level": result.retrieval_level,
                        "recipe_name": recipe_name,
                        "search_type": "dual_level",
                        **result.metadata
                    }
                )
                documents.append(doc)
            logger.info(f"双层检索完成，返回 {len(documents)} 个文档")
            return documents
        except Exception as e:
            logger.error(f"双层检索失败: {e}")
            return []

            
    def extract_query_keywords(self, query: str) -> Tuple[List[str], List[str]]:
        """
        提取查询关键词：实体级 + 主题级
        """
        prompt = f"""
        作为烹饪知识助手，请分析以下查询并提取关键词，分为两个层次：

        查询：{query}

        提取规则：
        1. 实体级关键词：具体的食材、菜品名称、工具、品牌等有形实体
           - 例如：鸡胸肉、西兰花、红烧肉、平底锅、老干妈
           - 对于抽象查询，推测相关的具体食材/菜品

        2. 主题级关键词：抽象概念、烹饪主题、饮食风格、营养特点等
           - 例如：减肥、低热量、川菜、素食、下饭菜、快手菜
           - 排除动作词：推荐、介绍、制作、怎么做等

        示例：
        查询："推荐几个减肥菜" 
        {{
            "entity_keywords": ["鸡胸肉", "西兰花", "水煮蛋", "胡萝卜", "黄瓜"],
            "topic_keywords": ["减肥", "低热量", "高蛋白", "低脂"]
        }}

        查询："川菜有什么特色"
        {{
            "entity_keywords": ["麻婆豆腐", "宫保鸡丁", "水煮鱼", "辣椒", "花椒"],
            "topic_keywords": ["川菜", "麻辣", "香辣", "下饭菜"]
        }}

        请严格按照JSON格式返回，不要包含多余的文字：
        {{
            "entity_keywords": ["实体1", "实体2", ...],
            "topic_keywords": ["主题1", "主题2", ...]
        }}
        """
        try:
            response = self.llm_client.chat.completions.create(
                model=self.config.llm_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=500
            )
            raw_content = response.choices[0].message.content.strip()
            # 去除 LLM 可能返回的 Markdown 代码块标记
            if raw_content.startswith("```"):
                raw_content = raw_content.split("\n", 1)[-1]  # 去掉 ```json
                raw_content = raw_content.rsplit("```", 1)[0]  # 去掉尾部 ```
            results = json.loads(raw_content)
            entity_keywords = results.get("entity_keywords", [])
            topic_keywords = results.get("topic_keywords", [])
            logger.info(f"提取到实体级关键词: {entity_keywords}, 主题级关键词: {topic_keywords}")
            return entity_keywords, topic_keywords
        except Exception as e:
            logger.error(f"关键词提取失败: {e}")
            return [], []

    
    def entity_level_retrieval(self, entity_keywords: List[str], top_k: int = 5) -> List[RetrievalResult]:
        """
        实体级检索：专注于具体实体和关系
        使用图索引的键值对结构进行检索
        """
        try:
            results = []
            for keyword in entity_keywords:
                # 检索匹配的实体
                entities = self.graph_indexing.get_entities_by_key(keyword)
                for entity in entities:
                    # 获取邻居信息
                    neighbors = self._get_node_neighbors(entity.metadata["node_id"])
                    # 构建增强内容
                    enhanced_content = entity.content_value
                    if neighbors:
                        enhanced_content += f"\n相关信息：{', '.join(neighbors)}"
                    
                    results.append(RetrievalResult(
                        content=enhanced_content,
                        node_id=entity.metadata["node_id"],
                        node_type=entity.entity_type,
                        relevance_score=0.9, # 实体匹配默认相关度较高
                        retrieval_level="entity",
                        metadata={
                            "entity_name": entity.entity_name,
                            "entity_type": entity.entity_type,
                            "index_keys": entity.index_keys,
                            "match_keyword": keyword
                        }))

            if len(results) < top_k:
                # Neo4j补充检索
                neo4j_results = self._neo4j_entity_level_search(entity_keywords, top_k - len(results))
                results.extend(neo4j_results)
            
            results.sort(key=lambda x: x.relevance_score, reverse=True)

            logger.info(f"实体级检索完成，找到 {len(results)} 个结果")
            return results[:top_k]
        except Exception as e:
            logger.error(f"实体级检索失败: {e}")
            return []

    
    def _get_node_neighbors(self, node_id: str, max_neighbors: int = 3) -> List[str]:
        """获取节点的邻居信息"""
        if not self.driver:
            logger.warning("Neo4j驱动未初始化，无法获取邻居信息")
            return []
        try:
            with self.driver.session() as session:
                query = """
                MATCH (n {nodeId: $node_id})-[r]-(neighbor)
                RETURN neighbor.name as name
                LIMIT $limit
                """
                result = session.run(query, {"node_id": node_id, "limit": max_neighbors})
                neighbors = [record["name"] for record in result if record["name"]]
                return neighbors
        except Exception as e:
            logger.error(f"获取邻居信息失败: {e}")
            return []

    
    def _neo4j_entity_level_search(self, keywords: List[str], limit: int) -> List[RetrievalResult]:
        """Neo4j补充检索"""
        logger.info(f"使用Neo4j补充实体级检索，关键词: {keywords}")
        if not self.driver:
            logger.warning("Neo4j驱动未初始化，无法执行补充检索")
            return []
        try:
            with self.driver.session() as session:
                cypher_query = """
                UNWIND $keywords as keyword
                CALL db.index.fulltext.queryNodes('recipe_fulltext_index', keyword + '*') 
                YIELD node, score
                WHERE node:Recipe
                RETURN 
                    node.nodeId as node_id,
                    node.name as name,
                    node.description as description,
                    labels(node) as labels,
                    score
                ORDER BY score DESC
                LIMIT $limit
                """

                result = session.run(cypher_query, {"keywords": keywords, "limit": limit})
                results = []
                for record in result:
                    content_parts = []
                    if record["name"]:
                        content_parts.append(f"菜品: {record['name']}")
                    if record["description"]:
                        content_parts.append(f"描述: {record['description']}")

                    results.append(RetrievalResult(
                        content="\n".join(content_parts),
                        node_id=record["node_id"],
                        node_type="Recipe",
                        relevance_score=float(record["score"]) * 0.7, # Neo4j补充检索相关度稍低
                        retrieval_level="entity",
                        metadata={
                            "name": record["name"],
                            "labels": record["labels"],
                            "source": "neo4j_entity_fallback"
                        }))
                logger.info(f"Neo4j补充实体级检索找到 {len(results)} 个结果")
                return results

        except Exception as e:
            logger.error(f"Neo4j补充实体级检索失败: {e}")
            return []

    
    def topic_level_retrieval(self, topic_keywords: List[str], top_k: int = 5) -> List[RetrievalResult]:
        """
        主题级检索：专注于广泛主题和概念
        使用图索引的关系键值对结构进行主题检索
        """
        logger.info(f"开始主题级检索，关键词: {topic_keywords}")
        try:
            results = []

            # 1. 使用图索引进行关系/主题检索
            for keyword in topic_keywords:
                # 检索匹配的关系
                relations = self.graph_indexing.get_relations_by_key(keyword)
                for relation in relations:
                    source_entity = self.graph_indexing.entities_kv_store.get(relation.source_entity)
                    target_entity = self.graph_indexing.entities_kv_store.get(relation.target_entity)

                    # 两端实体都存在才构建完整内容
                    if not (source_entity and target_entity):
                        continue

                    content_parts = [
                        f"主题：{keyword}",
                        relation.content_value,
                        f"相关菜品：{source_entity.entity_name}",
                        f"相关信息：{target_entity.entity_name}",
                    ]

                    # 添加源实体的详细信息
                    if source_entity.entity_type == "Recipe":
                        first_line = source_entity.content_value.split('\n')[0]
                        content_parts.append(f"菜品详情: {first_line}")

                    results.append(RetrievalResult(
                        content="\n".join(content_parts),
                        node_id=relation.source_entity, # 以主要实体为ID
                        node_type=relation.relation_type,
                        relevance_score=0.95, # 主题匹配相关度
                        retrieval_level="topic",
                        metadata={
                            "relation_id": relation.relation_id,
                            "relation_type": relation.relation_type,
                            "source_name": source_entity.entity_name,
                            "target_name": target_entity.entity_name,
                            "index_keys": keyword,
                            "match_keyword": keyword,
                            "source": "relation_match"
                        }))

            # 2. 使用实体的分类信息进行主题检索
            for keyword in topic_keywords:
                entities = self.graph_indexing.get_entities_by_key(keyword)
                for entity in entities:
                    if entity.entity_type == "Recipe":
                        content_parts = [
                            f"主题：{keyword}",
                            entity.content_value
                        ]

                        results.append(RetrievalResult(
                            content="\n".join(content_parts),
                            node_id=entity.metadata["node_id"],
                            node_type=entity.entity_type,
                            relevance_score=0.85, # 分类匹配相关度
                            retrieval_level="topic",
                            metadata={
                                "entity_name": entity.entity_name,
                                "entity_type": entity.entity_type,
                                "source": "category_match",
                                "match_keyword": keyword
                            }))

            if len(results) < top_k:
                # Neo4j补充检索
                neo4j_results = self._neo4j_topic_level_search(topic_keywords, top_k - len(results))
                results.extend(neo4j_results)
            
            results.sort(key=lambda x: x.relevance_score, reverse=True)

            logger.info(f"主题级检索完成，返回 {len(results)} 个结果")
            return results[:top_k]
        except Exception as e:
            logger.error(f"主题级检索失败: {e}")
            return []
    

    def _neo4j_topic_level_search(self, keywords: List[str], limit: int) -> List[RetrievalResult]:
        """Neo4j主题级检索补充"""
        logger.info(f"使用Neo4j补充主题级检索，关键词: {keywords}")
        if not self.driver:
            logger.warning("Neo4j驱动未初始化，无法执行补充检索")
            return []
        try:
            with self.driver.session() as session:
                cypher_query = """
                UNWIND $keywords as keyword
                MATCH (r:Recipe)
                WHERE r.category CONTAINS keyword 
                   OR r.cuisineType CONTAINS keyword
                   OR r.tags CONTAINS keyword
                WITH r, keyword
                OPTIONAL MATCH (r)-[:REQUIRES]->(i:Ingredient)
                WITH r, keyword, collect(i.name)[0..3] as ingredients
                RETURN 
                    r.nodeId as node_id,
                    r.name as name,
                    r.category as category,
                    r.cuisineType as cuisine_type,
                    r.difficulty as difficulty,
                    ingredients,
                    keyword as matched_keyword
                ORDER BY r.difficulty ASC, r.name
                LIMIT $limit
                """

                result = session.run(cypher_query, {"keywords": keywords, "limit": limit})
                results = []
                for record in result:
                    content_parts = []
                    if record["name"]:
                        content_parts.append(f"菜品: {record['name']}")
                    if record["category"]:
                        content_parts.append(f"分类: {record['category']}")
                    if record["cuisine_type"]:
                        content_parts.append(f"菜系: {record['cuisine_type']}")
                    if record["difficulty"]:
                        content_parts.append(f"难度: {record['difficulty']}")
                    if record["ingredients"]:
                        ingredients_str = ', '.join(record["ingredients"][:3])
                        content_parts.append(f"主要食材: {ingredients_str}")

                    results.append(RetrievalResult(
                        content="\n".join(content_parts),
                        node_id=record["node_id"],
                        node_type="Recipe",
                        relevance_score=0.75, # Neo4j主题级补充检索相关度更低
                        retrieval_level="topic",
                        metadata={
                            "name": record["name"],
                            "category": record["category"],
                            "cuisine_type": record["cuisine_type"],
                            "difficulty": record["difficulty"],
                            "matched_keyword": record["matched_keyword"],
                            "source": "neo4j_topic_fallback"
                        }))
                logger.info(f"Neo4j补充主题级检索找到 {len(results)} 个结果")
                return results

        except Exception as e:
            logger.error(f"Neo4j补充主题级检索失败: {e}")
            return []
    
    
    def vector_search_enhanced(self, query: str, top_k: int = 5) -> List[Document]:
        """
        增强的向量检索：BM25 + Milvus向量检索 + 图信息增强
        使用 Reciprocal Rank Fusion (RRF) 融合两路检索结果
        """
        logger.info(f"开始向量检索+BM25: {query}")
        try:
            bm25_docs: List[Document] = []
            vector_docs: List[Dict[str, Any]] = []

            # BM25 关键词检索
            if self.bm25_retriever:
                bm25_docs = self.bm25_retriever.get_relevant_documents(query)
                bm25_docs = bm25_docs[:top_k * 2] # 取前2倍结果，后续融合排序
                logger.info(f"BM25检索返回 {len(bm25_docs)} 个结果")
            else:
                logger.warning("BM25检索器未初始化，跳过BM25检索")

            # Milvus 向量检索
            if self.milvus_module:
                vector_docs = self.milvus_module.similarity_search(query, k=top_k * 2)
                logger.info(f"Milvus向量检索返回 {len(vector_docs)} 个结果")
            else:
                logger.warning("Milvus模块未初始化，跳过向量检索")

            if not bm25_docs and not vector_docs:
                logger.warning("BM25和向量检索均无结果")
                return []

            # RRF 融合打分
            # Reciprocal Rank Fusion: score = Σ 1/(k + rank)，k=60 为平滑常数
            rrf_k = 60
            score_map: Dict[str, float] = {}     # doc_key -> rrf_score
            doc_store: Dict[str, Document] = {}   # doc_key -> Document

            # BM25 结果按排名赋分（BM25Retriever 返回结果已按相关性排序）
            for rank, doc in enumerate(bm25_docs):
                doc_key = doc.metadata.get("node_id") or str(hash(doc.page_content))
                rrf_score = 1.0 / (rrf_k + rank + 1)
                score_map[doc_key] = score_map.get(doc_key, 0.0) + rrf_score

                if doc_key not in doc_store:
                    doc_store[doc_key] = Document(
                        page_content=doc.page_content,
                        metadata={
                            **doc.metadata,
                            "recipe_name": doc.metadata.get("recipe_name", "未知菜品"),
                            "search_type": "vector_enhanced",
                            "bm25_rank": rank + 1,
                        }
                    )

            # Milvus 结果按排名赋分（similarity_search 返回结果已按 distance 排序）
            for rank, result in enumerate(vector_docs):
                metadata = result.get("metadata", {})
                doc_key = metadata.get("node_id") or str(hash(result.get("text", "")))
                rrf_score = 1.0 / (rrf_k + rank + 1)
                score_map[doc_key] = score_map.get(doc_key, 0.0) + rrf_score # Milvus结果得分叠加到 BM25 得分上

                if doc_key not in doc_store:
                    content = result.get("text", "")
                    recipe_name = metadata.get("recipe_name", "未知菜品")
                    vector_distance = result.get("score", 0.0)

                    doc_store[doc_key] = Document(
                        page_content=content,
                        metadata={
                            **metadata,
                            "recipe_name": recipe_name,
                            "search_type": "vector_enhanced",
                            "score": vector_distance,
                            "vector_rank": rank + 1,
                        }
                    )

            # 图信息增强
            for doc_key, doc in doc_store.items():
                node_id = doc.metadata.get("node_id")
                if node_id:
                    neighbors = self._get_node_neighbors(node_id)
                    if neighbors:
                        doc.page_content += f"\n相关信息：{', '.join(neighbors)}"

            # 按 RRF 融合分排序输出
            sorted_keys = sorted(score_map, key=score_map.get, reverse=True)  # type: ignore
            final_docs = []
            for key in sorted_keys[:top_k]:
                doc = doc_store[key]
                doc.metadata["final_score"] = score_map[key]
                final_docs.append(doc)

            logger.info(
                f"BM25+向量融合检索完成：BM25={len(bm25_docs)}条, "
                f"Milvus={len(vector_docs)}条, 融合后返回 {len(final_docs)} 个文档"
            )
            return final_docs[:top_k]

        except Exception as e:
            logger.error(f"增强的向量检索失败: {e}")
            return []

        
    def close(self):
        """关闭资源连接"""
        logger.info("关闭混合检索模块资源连接...")
        if self.driver:
            self.driver.close()