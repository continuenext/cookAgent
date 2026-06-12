from pydantic.dataclasses import dataclass
import datetime
from pydantic import Field
from typing import Annotated, Any, Dict, List, Literal, Optional, TypedDict
from langchain_core.messages import AnyMessage
from langgraph.graph import add_messages


@dataclass(kw_only=True)
class Router():
    """
    路由结果
    """
    logic: str = ""  # 思考过程/逻辑
    type: Literal[
        "general-query",    # 闲聊
        "additional-query", # 需要追问
        "graphrag-query",   # 查图谱（graphrag）
        "image-query",      # 处理图片
        "file-query",       # 处理文件
        "text2sql-query",   # 统计查询
    ] = "general-query"
    question: str = ""      # 提取出的核心问题
    decision: Optional[str] = None  # 最终决策（可选）
    confidence: Optional[float] = None  # 置信度（可选）
    reasoning: Optional[str] = None  # 额外的推理信息（可选）

@dataclass(kw_only=True)
class InputState():
    messages: Annotated[list[AnyMessage], add_messages]

@dataclass(kw_only=True)
class GradeHallucinations():
    """
    生成答案中幻觉的二分类评分。
    """
    binary_score: str = Field(
        description="回答是否基于事实, '1'是基于事实 or '0'是出现幻觉"
    )

@dataclass(kw_only=True) # 必须使用关键字参数
class AgentState:
    """
    Agent 的全局状态。
    LangGraph 会在节点间传递这个对象。
    """
    messages: Annotated[list[AnyMessage], add_messages] # 消息历史 (核心)，使用 add_messages reducer 自动处理消息追加
    router: Router = Field(default_factory=lambda: Router(type="general-query", logic="")) # 路由决策结果
    documents: list[str] = Field(default_factory=list) # 检索到的文档/上下文
    answer: str = Field(default_factory=str) # 最终答案
    hallucination: GradeHallucinations = Field(default_factory=lambda: GradeHallucinations(binary_score="0"))
    hallucination_retry: int = 0  # 幻觉检查重试计数
    sources: list = Field(default_factory=list) # 额外的来源信息
    