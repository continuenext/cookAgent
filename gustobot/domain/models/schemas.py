"""
HTTP 接口层请求/响应模型

统一定义所有 API 端点的 Pydantic 模型，供路由层直接引用。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """主对话请求体"""
    message: str = Field(..., min_length=1, max_length=4096, description="用户消息")
    session_id: str = Field(..., min_length=1, max_length=128, description="会话标识")
    user_id: Optional[str] = Field(None, max_length=128, description="用户标识（可选，用于对话管理）")
    image_path: Optional[str] = Field(None, description="图片路径（可选，用于图片识别）")
    file_path: Optional[str] = Field(None, description="文件路径（可选，用于文件分析）")


class ChatResponse(BaseModel):
    """主对话响应体"""
    answer: str = Field(..., description="助手回复")
    router_type: str = Field(..., description="实际路由类型")
    session_id: str = Field(..., description="会话标识")
    steps: List[str] = Field(default_factory=list, description="执行步骤追踪")
    sources: List[Any] = Field(default_factory=list, description="来源信息")
    sql_statement: Optional[str] = Field(None, description="SQL 语句（text2sql 路由时返回）")
    execution_results: Optional[List[Dict[str, Any]]] = Field(None, description="SQL 执行结果")
    documents: Optional[List[str]] = Field(None, description="检索文档")


class ChatStreamChunk(BaseModel):
    """SSE 流式响应块"""
    type: str = Field(..., description="块类型: message / metadata / error / done")
    content: Optional[str] = Field(None, description="文本内容")
    metadata: Optional[Dict[str, Any]] = Field(None, description="元数据")
    session_id: Optional[str] = Field(None, description="会话标识")
    route: Optional[str] = Field(None, description="路由类型")


# ── 文件上传 ─────────────────────────────────────────

class FileUploadResponse(BaseModel):
    """文件/图片上传响应"""
    file_id: str = Field(..., description="文件唯一标识")
    filename: str = Field(..., description="服务端存储文件名")
    original_name: str = Field(..., description="原始文件名")
    size_bytes: int = Field(..., description="文件大小（字节）")
    file_path: str = Field(..., description="服务端保存路径")
    file_url: str = Field(..., description="文件访问 URL")
    file_type: str = Field(..., description="文件扩展名")


# ── 对话管理 ─────────────────────────────────────────

class SessionCreateRequest(BaseModel):
    """创建会话请求"""
    title: Optional[str] = Field(None, max_length=128, description="会话标题（可选）")
    user_id: Optional[str] = Field(None, max_length=128, description="用户标识（可选）")


class SessionUpdateRequest(BaseModel):
    """更新会话请求"""
    title: Optional[str] = Field(None, max_length=128, description="新标题")
    status: Optional[str] = Field(None, max_length=32, description="会话状态（如 active / archived）")


class SessionMeta(BaseModel):
    """会话元数据"""
    session_id: str
    title: str
    created_at: str
    updated_at: str
    message_count: int
    user_id: Optional[str] = None
    status: str = "active"


class SessionHistoryResponse(BaseModel):
    """会话历史响应"""
    session_id: str
    messages: List[Dict[str, str]] = Field(default_factory=list, description="消息列表 [{role, content}]")


class SessionCountResponse(BaseModel):
    """用户会话数量响应"""
    user_id: str
    count: int


# ── 知识库（向量） ───────────────────────────────────

class RecipeAddRequest(BaseModel):
    """添加菜谱到向量库的请求"""
    id: Optional[str] = Field(None, description="菜谱标识（为空时自动生成）")
    name: str = Field(..., description="菜谱名称")
    category: Optional[str] = Field(None, description="分类")
    difficulty: Optional[str] = Field(None, description="难度等级")
    time: Optional[str] = Field(None, description="烹饪时间")
    ingredients: Optional[List[str]] = Field(None, description="食材列表")
    steps: Optional[List[str]] = Field(None, description="制作步骤")
    tips: Optional[str] = Field(None, description="烹饪技巧")
    nutrition: Optional[Dict[str, Any]] = Field(None, description="营养信息")


class KBSearchRequest(BaseModel):
    """向量知识库搜索请求"""
    query: str = Field(..., min_length=1, description="查询文本")
    top_k: int = Field(5, ge=1, le=20, description="返回结果数量")


class KBSearchResponse(BaseModel):
    """向量知识库搜索响应"""
    results: List[Dict[str, Any]] = Field(..., description="匹配文档列表")
    count: int = Field(..., description="结果数量")


class KBStatsResponse(BaseModel):
    """菜谱业务统计信息（来源 MySQL）"""
    total_recipes: int = Field(0, description="菜谱总数")
    total_cuisines: int = Field(0, description="菜系总数")
    total_ingredients: int = Field(0, description="食材总数")
    total_steps: int = Field(0, description="步骤总数")
    avg_total_time_minutes: float = Field(0.0, description="平均总时长（分钟）")
    difficulty_distribution: Dict[str, int] = Field(default_factory=dict, description="难度分布")
    cuisine_distribution: Dict[str, int] = Field(default_factory=dict, description="菜系分布")
    top_ingredients: List[Dict[str, Any]] = Field(default_factory=list, description="高频食材 TopN")


# ── 图谱（Neo4j） ───────────────────────────────────

class GraphSnapshotResponse(BaseModel):
    """Neo4j 图谱快照"""
    nodes: List[Dict[str, Any]] = Field(..., description="节点列表")
    relationships: List[Dict[str, Any]] = Field(..., description="关系列表")


class GraphQARequest(BaseModel):
    """图谱自然语言问答请求"""
    query: str = Field(..., min_length=1, description="用户问题")
    include_graph: bool = Field(False, description="是否在响应中包含图谱数据")


class GraphQAResponse(BaseModel):
    """图谱问答响应"""
    answer: str = Field(..., description="自然语言回答")
    question_type: str = Field("", description="检测到的问题类型")
    cypher: List[str] = Field(default_factory=list, description="生成的 Cypher 查询")
    graph: Optional[GraphSnapshotResponse] = Field(None, description="可选的图谱数据")


# ── 通用操作响应 ─────────────────────────────────────

class OperationResponse(BaseModel):
    """通用操作成功响应"""
    status: str = Field("success", description="操作状态")
    message: str = Field(..., description="描述信息")


class RecipeAddResponse(OperationResponse):
    """添加菜谱响应"""
    recipe_id: str = Field(..., description="菜谱标识")


class RecipeBatchResponse(OperationResponse):
    """批量添加菜谱响应"""
    statistics: Dict[str, Any] = Field(..., description="插入统计")

