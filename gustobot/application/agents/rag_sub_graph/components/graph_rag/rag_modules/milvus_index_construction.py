"""
Milvus索引构建模块
"""
import time
from langchain_openai import OpenAIEmbeddings
from langchain.schema import Document
from typing import List, Dict, Any, Optional
from pydantic import SecretStr
import os
from pymilvus import MilvusClient, CollectionSchema, FieldSchema, DataType, Collection, connections
from dotenv import load_dotenv
from gustobot.infrastructure.core.logger import get_logger

load_dotenv()
logger = get_logger(service="MilvusIndexConstructorModule")

class MilvusIndexConstructorModule:
    """Milvus索引构建模块 - 负责向量化和Milvus索引构建"""
    def __init__(self, 
                host: str = "localhost", 
                port: int = 19530, 
                dimension: int = 1024, 
                collection_name: str = "recipes",
                api_key: Optional[str] = None,
                base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1",
                model_name: str = "text-embedding-v3"):
        self.host: str = os.getenv("MILVUS_HOST", host)
        self.port: str = str(os.getenv("MILVUS_PORT", port))
        self.model_name: str = os.getenv("EMBEDDING_MODEL", model_name)
        self.api_key: str | None = os.getenv("EMBEDDING_API_KEY") or os.getenv("LLM_API_KEY") or api_key
        self.base_url: str = os.getenv("EMBEDDING_BASE_URL", base_url)
        self.dimension: int = int(os.getenv("EMBEDDING_DIMENSION", dimension))
        self.collection_name: str = os.getenv("MILVUS_COLLECTION_NAME", collection_name)
        self.metric_type: str = os.getenv("MILVUS_METRIC_TYPE", "COSINE")
        self.index_type: str = os.getenv("MILVUS_INDEX_TYPE", "HNSW")
        self.collection_created: bool = False


        self.client: Optional[MilvusClient] = None
        self.embedding_model = None

        self._setup_client()
        self._setup_embeddings()

    
    def _ensure_client(self) -> MilvusClient:
        """确保 client 已初始化，返回类型缩窄后的 MilvusClient"""
        if self.client is None:
            raise RuntimeError("Milvus client 未初始化，请检查 _setup_client() 是否成功执行")
        return self.client

    
    def _ensure_embeddings(self) -> OpenAIEmbeddings:
        """确保 embeddings 已初始化"""
        if self.embedding_model is None:
            raise RuntimeError("嵌入模型未初始化，请检查 _setup_embeddings() 是否成功执行")
        return self.embedding_model


    def _setup_client(self):
        """初始化Milvus客户端"""
        logger.info("Milvus客户端初始化中...")
        try:
            self.client = MilvusClient(uri=f"http://{self.host}:{self.port}")
            collections = self.client.list_collections() # 测试连接
            logger.info(f"连接Milvus服务器成功: {self.host}:{self.port}，当前集合数量: {len(collections)}")
        except Exception as e:
            logger.error(f"连接Milvus服务器失败: {e}")
            raise ConnectionError(f"无法连接到Milvus服务器: {e}")


    def _setup_embeddings(self):
        """初始化阿里云百炼平台嵌入模型"""
        logger.info(f"正在初始化嵌入模型: {self.model_name} (base_url: {self.base_url})")
        try:
            self.embedding_model = OpenAIEmbeddings(
                model=self.model_name,
                openai_api_key=SecretStr(self.api_key) if self.api_key else None,
                openai_api_base=self.base_url,
                check_embedding_ctx_length=False,
            )
            logger.info("嵌入模型初始化成功")
        except Exception as e:
            logger.error(f"嵌入模型初始化失败: {e}")
            raise ValueError(f"无法初始化嵌入模型: {e}")


    def _create_collection_schema(self) -> CollectionSchema:
        """
        创建集合模式
        
        Returns:
            集合模式对象
        """
        # 定义字段
        fields = [
            FieldSchema(name="id", dtype=DataType.VARCHAR, max_length=150, is_primary=True),
            FieldSchema(name="vector", dtype=DataType.FLOAT_VECTOR, dim=self.dimension),
            FieldSchema(name="text", dtype=DataType.VARCHAR, max_length=15000),
            FieldSchema(name="node_id", dtype=DataType.VARCHAR, max_length=100),
            FieldSchema(name="recipe_name", dtype=DataType.VARCHAR, max_length=300),
            FieldSchema(name="node_type", dtype=DataType.VARCHAR, max_length=100),
            FieldSchema(name="category", dtype=DataType.VARCHAR, max_length=100),
            FieldSchema(name="cuisine_type", dtype=DataType.VARCHAR, max_length=200),
            FieldSchema(name="difficulty", dtype=DataType.INT64),
            FieldSchema(name="doc_type", dtype=DataType.VARCHAR, max_length=50),
            FieldSchema(name="chunk_id", dtype=DataType.VARCHAR, max_length=150),
            FieldSchema(name="parent_id", dtype=DataType.VARCHAR, max_length=100)
        ]
        
        # 创建集合模式
        schema = CollectionSchema(fields=fields, description="菜谱知识图谱节点和关系")
        return schema


    def _safe_truncate(self, text: Optional[str], max_length: int) -> str:
        """安全截断字符串，避免超过Milvus字段长度限制"""
        if text is None:
            return ""
        if len(text) > max_length:
            logger.warning(f"文本长度 {len(text)} 超过限制 {max_length}，将被截断")
            return text[:max_length]
        return text


    def _flush_collection(self) -> None:
        """兼容不同 pymilvus 版本执行 flush。"""
        client = self._ensure_client()
        flush_fn = getattr(client, "flush", None)
        if callable(flush_fn):
            flush_fn(collection_name=self.collection_name)
            return

        # 旧版/兼容路径：通过 ORM Collection.flush()
        connections.connect(alias="default", host=self.host, port=self.port)
        Collection(self.collection_name).flush()


    def _count_entities(self) -> int:
        """返回集合实体数（必要时通过 ORM 路径兜底）。"""
        try:
            connections.connect(alias="default", host=self.host, port=self.port)
            return int(Collection(self.collection_name).num_entities)
        except Exception:
            return 0


    def _ensure_collection_ready(self) -> bool:
        """确保目标集合存在；不存在时自动创建。"""
        try:
            client = self._ensure_client()
            exists = client.has_collection(collection_name=self.collection_name)
            if exists:
                self.collection_created = True
                # 兼容历史集合：可能存在但未建索引，导致无法 load/query
                if not self.load_collection():
                    logger.warning(f"集合 '{self.collection_name}' 加载失败，尝试补建索引")
                    if not self.create_index():
                        return False
                    if not self.load_collection():
                        logger.error(f"集合 '{self.collection_name}' 补建索引后仍无法加载")
                        return False
                return True

            logger.warning(f"集合 '{self.collection_name}' 不存在，开始自动创建")
            created = self.create_collection(force_recreate=False)
            if not created:
                logger.error(f"集合 '{self.collection_name}' 自动创建失败")
                return False

            # 新建集合后补建索引并加载，保证后续查询/删除可用
            if not self.create_index():
                return False
            if not self.load_collection():
                return False

            self.collection_created = True
            return True
        except Exception as e:
            logger.error(f"确保集合 '{self.collection_name}' 就绪失败: {e}")
            return False
        

    def create_collection(self, force_recreate: bool = False) -> bool:
        """
        创建Milvus集合
        
        Args:
            force_recreate: 是否强制重新创建集合
        
        Returns:
            是否创建成功
        """
        try:
            client = self._ensure_client()
            if client.has_collection(collection_name=self.collection_name):
                if force_recreate:
                    logger.warning(f"集合 '{self.collection_name}' 已存在，正在删除并重新创建...")
                    client.drop_collection(collection_name=self.collection_name)
                else:
                    logger.info(f"集合 '{self.collection_name}' 已存在，跳过创建")
                    self.collection_created = True
                    return True

            collection_schema = self._create_collection_schema()
            client.create_collection(
                collection_name=self.collection_name,
                schema=collection_schema,
                metric_type=self.metric_type,
                consistency_level="Strong",
            )
            logger.info(f"集合 '{self.collection_name}' 创建成功")
            self.collection_created = True
            return True

        except Exception as e:
            logger.error(f"创建集合 '{self.collection_name}' 失败: {e}")
            return False


    def create_index(self) -> bool:
        """
        创建向量索引
        
        Returns:
            是否创建成功
        """
        try:
            if not self.collection_created:
                raise ValueError("请先创建集合")

            client = self._ensure_client()
            # 创建一个空的索引参数容器
            index_params = client.prepare_index_params()

            index_params.add_index(
                field_name="vector",
                index_type=self.index_type,
                metric_type=self.metric_type,
                params={
                    "M": 16,              # 每层最大连接数，越大召回率越高，内存占用越多
                    "efConstruction": 200  # 建索引时的搜索范围，越大索引质量越好，建索引越慢
                }
            )

            # 正式在服务端构建索引
            client.create_index(
                collection_name=self.collection_name,
                index_params=index_params,
            )
            logger.info(f"集合 '{self.collection_name}' 向量索引创建成功 "
                       f"(index_type={self.index_type}, metric_type={self.metric_type})")
            return True

        except Exception as e:
            logger.error(f"创建集合 '{self.collection_name}' 的向量索引失败: {e}")
            return False


    def build_vector_index(self, chunks: List[Document]) -> bool:
        """
        构建集合-生成向量-插入数据-构建索引
        
        Args:
            chunks: 文档块列表
            
        Returns:
            是否构建成功
        """
        logger.info(f"正在构建Milvus向量索引，文档数量: {len(chunks)}...")
        try:
            if not chunks:
                logger.error("没有文档块可供构建索引.")
                raise ValueError("文档块列表不能为空")

            if not self.collection_created:
                logger.info("集合尚未创建，正在创建集合...")

            # 创建集合
            if not self.create_collection(force_recreate=True):
                return False

            client = self._ensure_client()
            embedding_model = self._ensure_embeddings()

            logger.info("正在生成向量embeddings...")
            texts = [chunk.page_content if chunk.page_content else " " for chunk in chunks]
            # 分批生成向量，避免 API 单次请求过大（阿里云百炼限制 batch_size ≤ 10）
            embed_batch_size = 10
            vectors = []
            for i in range(0, len(texts), embed_batch_size):
                batch_texts = texts[i:i + embed_batch_size]
                batch_vectors = embedding_model.embed_documents(batch_texts)
                vectors.extend(batch_vectors)
                logger.info(f"Embedding 进度: {min(i + embed_batch_size, len(texts))}/{len(texts)}")


            # 插入数据
            entities = []
            for i, (chunk, vector) in enumerate(zip(chunks, vectors)):
                entity = {
                    "id": self._safe_truncate(chunk.metadata.get("chunk_id", f"chunk_{i}"), 150),
                    "vector": vector,
                    "text": self._safe_truncate(chunk.page_content, 15000),
                    "node_id": self._safe_truncate(chunk.metadata.get("node_id", ""), 100),
                    "recipe_name": self._safe_truncate(chunk.metadata.get("recipe_name", ""), 300),
                    "node_type": self._safe_truncate(chunk.metadata.get("node_type", ""), 100),
                    "category": self._safe_truncate(chunk.metadata.get("category", ""), 100),
                    "cuisine_type": self._safe_truncate(chunk.metadata.get("cuisine_type", ""), 200),
                    "difficulty": int(chunk.metadata.get("difficulty", 0)),
                    "doc_type": self._safe_truncate(chunk.metadata.get("doc_type", ""), 50),
                    "chunk_id": self._safe_truncate(chunk.metadata.get("chunk_id", f"chunk_{i}"), 150),
                    "parent_id": self._safe_truncate(chunk.metadata.get("parent_id", ""), 100)
                }
                entities.append(entity)
            
            # 批量插入数据到Milvus，避免一次性插入过多导致内存问题
            batch_size = 100
            for i in range(0, len(entities), batch_size):
                batch_entities = entities[i:i+batch_size]
                client.insert(collection_name=self.collection_name, data=batch_entities)
                logger.info(f"已批量插入 {len(batch_entities)} 条数据到集合 '{self.collection_name}'")

            # 触发持久化，避免 get_collection_stats 读到 row_count=0
            self._flush_collection()

            logger.info(f"成功插入 {len(entities)} 条数据到集合 '{self.collection_name}'，向量索引构建完成")

            # 构建索引
            if not self.create_index():
                return False

            # 加载集合到内存，提升查询性能
            logger.info("等待集合加载到内存...")
            client.load_collection(collection_name=self.collection_name)
            for _ in range(10):  # 最多等待10秒
                state = client.get_load_state(collection_name=self.collection_name)
                if state["state"].name == "Loaded":
                    break
                time.sleep(1)
            else:
                logger.warning(f"集合 '{self.collection_name}' 加载超时，当前状态: {state}")
                raise TimeoutError(f"集合 '{self.collection_name}' 加载超时")
            logger.info(f"集合 '{self.collection_name}' 已加载到内存.")

            logger.info(f"向量索引构建完成，包含 {len(chunks)} 个向量")
            return True

        except Exception as e:
            logger.error(f"构建向量索引失败: {e}")
            return False


    def add_documents(self, new_chunks: List[Document]) -> bool:
        """
        向现有索引添加新文档
        
        Args:
            new_chunks: 新的文档块列表
            
        Returns:
            是否添加成功
        """
        try:
            if not new_chunks:
                logger.warning("没有新的文档块可供添加.")
                return False

            if not self._ensure_collection_ready():
                raise ValueError("集合不存在且自动创建失败")

            client = self._ensure_client()
            embedding_model = self._ensure_embeddings()

            logger.info(f"正在为 {len(new_chunks)} 个新文档块生成向量...")
            texts = [chunk.page_content for chunk in new_chunks]
            vectors = embedding_model.embed_documents(texts)

            entities = []
            for i, (chunk, vector) in enumerate(zip(new_chunks, vectors)):
                entity = {
                    "id": self._safe_truncate(chunk.metadata.get("chunk_id", f"chunk_{i}"), 150),
                    "vector": vector,
                    "text": self._safe_truncate(chunk.page_content, 15000),
                    "node_id": self._safe_truncate(chunk.metadata.get("node_id", ""), 100),
                    "recipe_name": self._safe_truncate(chunk.metadata.get("recipe_name", ""), 300),
                    "node_type": self._safe_truncate(chunk.metadata.get("node_type", ""), 100),
                    "category": self._safe_truncate(chunk.metadata.get("category", ""), 100),
                    "cuisine_type": self._safe_truncate(chunk.metadata.get("cuisine_type", ""), 200),
                    "difficulty": int(chunk.metadata.get("difficulty", 0)),
                    "doc_type": self._safe_truncate(chunk.metadata.get("doc_type", ""), 50),
                    "chunk_id": self._safe_truncate(chunk.metadata.get("chunk_id", f"chunk_{i}"), 150),
                    "parent_id": self._safe_truncate(chunk.metadata.get("parent_id", ""), 100)
                }
                entities.append(entity)

            client.insert(collection_name=self.collection_name, data=entities)
            self._flush_collection()
            logger.info(f"成功添加 {len(entities)} 个新文档块到集合 '{self.collection_name}'")
            return True

        except Exception as e:
            logger.error(f"添加新文档失败: {e}")
            return False
        

    def similarity_search(self, query: str, k: int = 5, filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        相似度搜索
        
        Args:
            query: 查询文本
            k: 返回结果数量
            filters: 过滤条件
            
        Returns:
            搜索结果列表
        """
        try:
            client = self._ensure_client()
            embedding_model = self._ensure_embeddings()

            query_vector = embedding_model.embed_query(query)

            # 过滤
            filter_expr = ""
            if filters:
                filter_conditions = []
                for key, value in filters.items():
                    if isinstance(value, str):
                        filter_conditions.append(f'{key} == "{value}"')
                    elif isinstance(value, (int, float)):
                        filter_conditions.append(f"{key} == {value}")
                    elif isinstance(value, list):
                        if all(isinstance(v, str) for v in value):
                            quoted = ', '.join(f'"{v}"' for v in value)
                            filter_conditions.append(f'{key} in [{quoted}]')
                        else:
                            value_str = ', '.join(str(v) for v in value)
                            filter_conditions.append(f"{key} in [{value_str}]")
                if filter_conditions:
                    filter_expr = " and ".join(filter_conditions)


            # 执行搜索
            results = client.search(
                collection_name=self.collection_name,
                data=[query_vector],
                anns_field="vector",
                limit=k,
                output_fields=["text", "node_id", "recipe_name", "node_type",
                                "category", "cuisine_type", "difficulty", "doc_type",
                                "chunk_id", "parent_id"],
                search_params={
                    "metric_type": self.metric_type,
                    "params": {"ef": 60}  # 搜索时的探索范围，越大召回率越高，搜索越慢
                },
                filter=filter_expr if filter_expr else "",
            )

            formatted_results = []
            if results:
                for res in results[0]: # 第1条查询的所有匹配项
                    result = {
                        "id": res["id"],
                        "score": res["distance"],
                        "text": res["entity"]["text"],
                        "metadata": {
                            "node_id": res["entity"]["node_id"],
                            "recipe_name": res["entity"]["recipe_name"],
                            "node_type": res["entity"]["node_type"],
                            "category": res["entity"]["category"], 
                            "cuisine_type": res["entity"]["cuisine_type"],
                            "difficulty": res["entity"]["difficulty"],
                            "doc_type": res["entity"]["doc_type"],
                            "chunk_id": res["entity"]["chunk_id"],
                            "parent_id": res["entity"]["parent_id"]
                        }
                    }
                    formatted_results.append(result)

            return formatted_results

        except Exception as e:
            logger.error(f"相似度搜索失败: {e}")
            return []

    
    def get_collection_stats(self) -> Dict[str, Any]:
        """
        获取集合统计信息
        
        Returns:
            统计信息字典
        """
        try:
            client = self._ensure_client()
            self._flush_collection()
            stats = client.get_collection_stats(collection_name=self.collection_name)
            row_count = stats.get("row_count", 0)
            if not row_count:
                row_count = self._count_entities()
            return {
                "collection_name": self.collection_name,
                "row_count": row_count,
                "index_building_progress": stats.get("index_building_progress", 0),
                "stats": stats
            }

        except Exception as e:
            logger.error(f"获取集合统计信息失败: {e}")
            return {"collection_name": self.collection_name, "error": str(e)}


    def delete_collection(self) -> bool:
        """
        删除集合
        
        Returns:
            是否删除成功
        """
        try:
            client = self._ensure_client()
            if client.has_collection(collection_name=self.collection_name):
                client.drop_collection(collection_name=self.collection_name)
                logger.info(f"集合 '{self.collection_name}' 已删除")
                self.collection_created = False
                return True
            else:
                logger.warning(f"集合 '{self.collection_name}' 不存在，无法删除")
                return False
        except Exception as e:
            logger.error(f"删除集合 '{self.collection_name}' 失败: {e}")
            return False
            



    def has_collection(self) -> bool:
        """
        检查集合是否存在
        
        Returns:
            集合是否存在
        """
        try:
            client = self._ensure_client()
            return client.has_collection(collection_name=self.collection_name)

        except Exception as e:
            logger.error(f"检查集合 '{self.collection_name}' 存在性失败: {e}")
            return False


    def load_collection(self) -> bool:
        """
        加载集合到内存
        
        Returns:
            是否加载成功
        """
        try:
            client = self._ensure_client()

            if not client.has_collection(collection_name=self.collection_name):
                logger.error(f"集合 '{self.collection_name}' 不存在，无法加载")
                return False

            client.load_collection(collection_name=self.collection_name)
            self.collection_created = True
            logger.info(f"集合 '{self.collection_name}' 已加载到内存")
            return True
        except Exception as e:
            logger.error(f"加载集合 '{self.collection_name}' 失败: {e}")
            return False


    def close(self):
        """关闭连接"""
        if hasattr(self, "client") and self.client is not None:
            # Milvus客户端不需要显式关闭
            logger.info("Milvus连接已关闭")
    
    def __del__(self):
        """析构函数"""
        self.close()


