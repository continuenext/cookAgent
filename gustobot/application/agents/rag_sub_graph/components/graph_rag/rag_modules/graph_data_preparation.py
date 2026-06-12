"""
数据加载和分块模块
"""

from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter
import asyncio
from dataclasses import dataclass
import os
from dotenv import load_dotenv
from gustobot.infrastructure.core.logger import get_logger
from langchain.schema import Document
from typing import List, Dict, Any, Optional
from neo4j import AsyncGraphDatabase, AsyncDriver

load_dotenv()

logger = get_logger(service="graph_data_preparation")

@dataclass
class GraphNode:
    """图节点数据结构"""
    node_id: str
    labels: List[str]
    name: str
    properties: Dict[str, Any]

@dataclass
class Relationship:
    """图关系数据结构"""
    start_node_id: str
    end_node_id: str
    relation_type: str
    properties: Dict[str, Any]


class GraphDataPreparation:
    """图数据库数据准备模块 - 从Neo4j读取数据并转换为文档"""
    def __init__(self, neo4j_config: dict):
        self.uri = os.getenv("NEO4J_URI", neo4j_config.get("uri", "bolt://localhost:7687"))
        self.username = os.getenv("NEO4J_USER", neo4j_config.get("username", "neo4j"))
        self.password = os.getenv("NEO4J_PASSWORD", neo4j_config.get("password", "password"))
        self.database = neo4j_config.get("database", "neo4j")  # 默认数据库名称
        self.driver: AsyncDriver | None = None  # 明确类型注解

        self.recipes: List[GraphNode] = []
        self.ingredients: List[GraphNode] = []
        self.cooking_steps: List[GraphNode] = []
        self.documents: List[Document] = []
        self.chunks: List[Document] = []


    @classmethod
    async def create(cls, neo4j_config: dict) -> "GraphDataPreparation":
        """异步工厂方法，替代直接实例化"""
        instance = cls(neo4j_config)
        await instance.connect()
        return instance


    async def connect(self):
        """建立与Neo4j数据库的连接"""
        try:
            self.driver = AsyncGraphDatabase.driver(
                self.uri,
                auth=(self.username, self.password)
            )
            logger.info(f"已连接到Neo4j数据库: {self.uri}")

            async with self.driver.session(database=self.database) as session:
                result = await session.run("RETURN 1")  # 测试连接
                test_result = await result.single()
                if test_result is None or test_result[0] != 1:
                    raise Exception("Neo4j连接测试失败")
                logger.info("Neo4j连接测试成功")
        except Exception as e:
            logger.error(f"连接Neo4j失败: {e}")
            raise

    async def load_graph_data(self) -> Dict[str, Any]:
        """
        从Neo4j加载图数据
        
        Returns:
            包含节点和关系的数据字典
        """
        logger.info("正在从Neo4j加载图数据...")


        async def _fetch_recipes_tx(tx):
            """加载所有菜谱节点，并集成分类信息"""
            recipes_query = """
            MATCH (r:Concept {conceptType: 'Recipe'})
            OPTIONAL MATCH (r)-[:`801000004`]->(c:Concept {conceptType: 'RecipeCategory'})
            WITH r, collect(c.name) as categories
            RETURN r.nodeId as nodeId, labels(r) as labels, r.name as name, 
                   properties(r) as originalProperties,
                   CASE WHEN size(categories) > 0 
                        THEN categories[0] 
                        ELSE COALESCE(r.category, '未知') END as mainCategory,
                   CASE WHEN size(categories) > 0 
                        THEN categories 
                        ELSE [COALESCE(r.category, '未知')] END as allCategories
            ORDER BY r.nodeId
            """
            # 合并原始属性和新的分类信息
            recipes = []
            result = await tx.run(recipes_query)
            async for record in result:
                properties = dict(record["originalProperties"])
                properties["category"] = record["mainCategory"]
                properties["allCategories"] = record["allCategories"]

                node = GraphNode(
                    node_id=record["nodeId"],
                    labels=record["labels"],
                    name=record["name"],
                    properties=properties
                )
                recipes.append(node)
            return recipes
        
 
        async def _fetch_ingredients_tx(tx):
            """加载所有食材节点"""
            ingredients_query = """
            MATCH (i:Concept {conceptType: 'Ingredient'})
            RETURN i.nodeId as nodeId, labels(i) as labels, i.name as name,
                   properties(i) as properties
            ORDER BY i.nodeId
            """
            ingredients = []
            result = await tx.run(ingredients_query)
            async for record in result:
                node = GraphNode(
                    node_id=record["nodeId"],
                    labels=record["labels"],
                    name=record["name"],
                    properties=dict(record["properties"])
                )
                ingredients.append(node)
            return ingredients


        async def _fetch_cooking_steps_tx(tx):
            """加载所有烹饪步骤节点"""
            steps_query = """
            MATCH (s:Concept {conceptType: 'CookingStep'})
            RETURN s.nodeId as nodeId, labels(s) as labels, s.name as name,
                   properties(s) as properties
            ORDER BY s.nodeId
            """
            steps = []
            result = await tx.run(steps_query)
            async for record in result:
                node = GraphNode(
                    node_id=record["nodeId"],
                    labels=record["labels"],
                    name=record["name"],
                    properties=dict(record["properties"])
                )
                steps.append(node)
            return steps

        if self.driver is None:
            raise RuntimeError("Neo4j driver 未初始化，请通过 GraphDataPreparation.create() 创建实例")

        driver = self.driver  # 类型缩窄为 AsyncDriver

        # 每个事务使用独立 session（Neo4j session 不支持并发事务）
        async def _run_in_session(tx_func):
            async with driver.session(database=self.database) as session:
                return await session.execute_read(tx_func)

        recipes, ingredients, cooking_steps = await asyncio.gather(
            _run_in_session(_fetch_recipes_tx),
            _run_in_session(_fetch_ingredients_tx),
            _run_in_session(_fetch_cooking_steps_tx),
        )

        self.recipes = recipes
        self.ingredients = ingredients
        self.cooking_steps = cooking_steps

        logger.info(f"并发加载完成：{len(recipes)}个菜谱节点, {len(ingredients)}个食材节点, {len(cooking_steps)}个烹饪步骤节点。")

        return {
            "recipes": len(self.recipes),
            "ingredients": len(self.ingredients),
            "cooking_steps": len(self.cooking_steps)
        }

    
    async def build_recipe_documents(self) -> List[Document]:
        """
        构建菜谱文档，集成相关的食材和步骤信息
        
        Returns:
            结构化的菜谱文档列表
        """
        logger.info("正在构建菜谱文档...")

        if not self.recipes:
            raise RuntimeError("菜谱数据为空，请先调用 load_graph_data()")
        if self.driver is None:
            raise RuntimeError("Neo4j driver 未初始化，请通过 GraphDataPreparation.create() 创建实例")

        driver = self.driver  # 类型缩窄为 AsyncDriver

        async def _fetch_recipe_details_tx(tx, recipe_id):
            """获取菜谱的相关食材和烹饪步骤"""
            ingredients_query = """
            MATCH (r:Concept {nodeId: $recipe_id})-[req:`801000001`]->(i:Concept {conceptType: 'Ingredient'})
            RETURN i.name as name, i.category as category, 
                req.amount as amount, req.unit as unit,
                i.description as description
            ORDER BY i.name
            """
            ingredients_result = await tx.run(ingredients_query, {"recipe_id": recipe_id})
            ingredients: List[Dict] = [dict(record) async for record in ingredients_result]

            steps_query = """
            MATCH (r:Concept {nodeId: $recipe_id})-[c:`801000003`]->(s:Concept {conceptType: 'CookingStep'})
            RETURN s.name as name, s.description as description,
                s.stepNumber as stepNumber, s.methods as methods,
                s.tools as tools, s.timeEstimate as timeEstimate,
                c.stepOrder as stepOrder
            ORDER BY COALESCE(c.stepOrder, s.stepNumber, 999)
            """
            steps_result = await tx.run(steps_query, {"recipe_id": recipe_id})
            steps: List[Dict] = [dict(record) async for record in steps_result]

            return ingredients, steps

        semaphore = asyncio.Semaphore(50)  # 控制并发量，避免过多同时查询数据库

        async def _process_single_recipe(recipe: GraphNode) -> Optional[Document]:
            """处理单个菜谱节点，构建对应的文档"""
            recipe_id = recipe.node_id
            recipe_name = recipe.name
            async with semaphore:
                try:
                    async with driver.session(database=self.database) as session:
                        ingredients_results, steps_results = await session.execute_read(
                            _fetch_recipe_details_tx, recipe_id
                        )

                    # 构建食材信息文本，包含名称、用量、单位和描述
                    ingredients_info = []
                    for ing_record in ingredients_results:
                        amount = ing_record.get("amount", "")
                        unit = ing_record.get("unit", "")
                        ingredient_text = f"{ing_record['name']}"
                        if amount and unit:
                            ingredient_text += f"({amount}{unit})" # 用量+单位
                        if ing_record.get("description"):
                            ingredient_text += f" - {ing_record['description']}"
                        ingredients_info.append(ingredient_text)

                    # 构建步骤信息文本，包含步骤名字、步骤描述、方法、工具和时间估计
                    steps_info = []
                    for step_record in steps_results:
                        step_text = f"步骤: {step_record['name']}"
                        if step_record.get("description"):
                            step_text += f"\n描述: {step_record['description']}"
                        if step_record.get("methods"):
                            step_text += f"\n方法: {step_record['methods']}"
                        if step_record.get("tools"):
                            step_text += f"\n工具: {step_record['tools']}"
                        if step_record.get("timeEstimate"):
                            step_text += f"\n时间: {step_record['timeEstimate']}"
                        steps_info.append(step_text)

                    # 构建完整的菜谱文档内容，包括菜品描述、菜系、难度、准备时间、烹饪时间、份量、所需食材和步骤信息
                    content_parts = [f"# {recipe_name}"]
                    if recipe.properties.get("description"):
                        content_parts.append(f"\n## 菜品描述\n{recipe.properties['description']}")
                    if recipe.properties.get("cuisineType"):
                        content_parts.append(f"\n菜系: {recipe.properties['cuisineType']}")
                    if recipe.properties.get("difficulty"):
                        content_parts.append(f"难度: {recipe.properties['difficulty']}星")
                    if recipe.properties.get("prepTime") or recipe.properties.get("cookTime"):
                        time_info = []
                        if recipe.properties.get("prepTime"):
                            time_info.append(f"准备时间: {recipe.properties['prepTime']}")
                        if recipe.properties.get("cookTime"):
                            time_info.append(f"烹饪时间: {recipe.properties['cookTime']}")
                        content_parts.append(f"\n时间信息: {', '.join(time_info)}")
                    if recipe.properties.get("servings"):
                        content_parts.append(f"份量: {recipe.properties['servings']}")

                    if ingredients_info:
                        content_parts.append("\n## 所需食材")
                        for i, ingredient in enumerate(ingredients_info, 1):
                            content_parts.append(f"{i}. {ingredient}")

                    if steps_info:
                        content_parts.append("\n## 制作步骤")
                        for i, step in enumerate(steps_info, 1):
                            content_parts.append(f"\n### 第{i}步\n{step}")

                    if recipe.properties.get("tags"):
                        content_parts.append(f"\n## 标签\n{recipe.properties['tags']}")

                    full_content = "\n".join(content_parts)

                    doc = Document(
                        page_content=full_content,
                        metadata={
                            "node_id": recipe_id, # 唯一标识符，方便后续查询和关联
                            "recipe_name": recipe_name, # 菜谱名称
                            "node_type": "Recipe",  # 节点类型
                            "category": recipe.properties.get("category", "未知"), # 主分类信息
                            "cuisine_type": recipe.properties.get("cuisineType", "未知"), # 菜系信息
                            "difficulty": recipe.properties.get("difficulty", 0), # 难度等级
                            "prep_time": recipe.properties.get("prepTime", ""), # 准备时间
                            "cook_time": recipe.properties.get("cookTime", ""), # 烹饪时间
                            "servings": recipe.properties.get("servings", ""), # 份量
                            "ingredients_count": len(ingredients_info), # 食材数量
                            "steps_count": len(steps_info), # 步骤数量
                            "doc_type": "recipe", # 文档类型标签，方便后续过滤和查询
                            "content_length": len(full_content) # 文档内容长度
                        }
                    )
                    logger.info(f"成功构建菜谱文档: {recipe_name} (ID: {recipe_id})")
                    return doc
                except Exception as e:
                    logger.warning(f"构建菜谱文档失败 {recipe.name} (ID: {recipe.node_id}): {e}")
                    return None

        
        task = [_process_single_recipe(recipe) for recipe in self.recipes]
        results = await asyncio.gather(*task)

        documents = [doc for doc in results if doc is not None]
        
        self.documents = documents
        logger.info(f"成功并发构建 {len(documents)} 个菜谱文档")
        return documents

    def chunk_documents(self, chunk_size: int = 500, overlap_size: int = 50) -> List[Document]:
        """对文档进行分块"""

        # 策略 1: 定义 Markdown 语义映射层级，遇到这些符号就切一刀，并把标题内容作为 Metadata 存下来
        headers_to_split_on = [
            ("#", "recipe_name"),      # 对应一级标题：菜谱名
            ("##", "section_title"),    # 对应二级标题：菜品描述 / 所需食材 / 制作步骤 / 标签
        ]
        
        markdown_splitter = MarkdownHeaderTextSplitter(
            headers_to_split_on=headers_to_split_on,
            strip_headers=False  # 设为 False，保留原始标题文本，有助于大模型理解上下文
        )
        
        # 策略 2: 字符长度兜底切分（预留一些重叠，防止长步骤被切断时丢失上下文）
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=overlap_size,
            separators=["\n\n", "\n", "。", "，", " ", ""] # 优先按段落和句号切
        )

        chunks = []

        for doc in self.documents:
            # 提取从 Neo4j 拼出来的原始 Metadata
            original_meta = doc.metadata

            parent_id = original_meta.get("node_id", "unknown")  # 父级 ID，使用菜谱节点 ID 作为标识
            
            md_splits: list[Document] = markdown_splitter.split_text(doc.page_content)
            final_splits: list[Document] = text_splitter.split_documents(md_splits)
            
            total_chunks = len(final_splits)

            for i, chunk in enumerate(final_splits, 1):
                merged_meta = original_meta.copy()

                merged_meta.update(chunk.metadata)

                merged_meta["parent_id"] = parent_id
                merged_meta["chunk_id"] = f"{parent_id}_chunk_{i}"
                merged_meta["chunk_index"] = i
                merged_meta["total_chunks"] = total_chunks
                merged_meta["chunk_size"] = len(chunk.page_content)
                merged_meta["doc_type"] = "chunk"

                # 给当前的 Chunk 绑定融合后的 Metadata
                chunk.metadata = merged_meta
                chunks.append(chunk)

        logger.info(f"分块完成！{len(self.documents)} 篇整文档被拆分为 {len(chunks)} 个检索语义块(Chunks)。")
        self.chunks = chunks
        return chunks

    
    def get_statistics(self) -> Dict[str, Any]:
        """
        获取数据统计信息
        
        Returns:
            统计信息字典
        """
        stats: Dict[str, Any] = {
            'total_recipes': len(self.recipes), # 统计菜谱数量
            'total_ingredients': len(self.ingredients), # 统计食材数量
            'total_cooking_steps': len(self.cooking_steps), # 统计烹饪步骤数量
            'total_documents': len(self.documents), # 统计构建的菜谱文档数量
            'total_chunks': len(self.chunks) # 统计分块后的文档数量
        }
        
        if self.documents:
            # 分类统计
            categories = {} # 分类
            cuisines = {} # 菜系
            difficulties = {} # 难度等级
            
            for doc in self.documents:
                category = doc.metadata.get('category', '未知')
                categories[category] = categories.get(category, 0) + 1
                
                cuisine = doc.metadata.get('cuisine_type', '未知')
                cuisines[cuisine] = cuisines.get(cuisine, 0) + 1
                
                difficulty = doc.metadata.get('difficulty', 0)
                difficulties[str(difficulty)] = difficulties.get(str(difficulty), 0) + 1
            
            stats.update({
                'categories': categories,
                'cuisines': cuisines,
                'difficulties': difficulties,
                'avg_content_length': sum(doc.metadata.get('content_length', 0) for doc in self.documents) / len(self.documents), # 平均文档内容长度
                'avg_chunk_size': sum(len(chunk.page_content) for chunk in self.chunks) / len(self.chunks) if self.chunks else 0 # 平均分块大小
            })
        
        return stats


    async def close(self):
        """关闭Neo4j数据库连接"""
        try:
            if self.driver:
                await self.driver.close()
                logger.info("Neo4j连接已关闭")
        except Exception as e:
            logger.error(f"关闭Neo4j连接失败: {e}")

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
