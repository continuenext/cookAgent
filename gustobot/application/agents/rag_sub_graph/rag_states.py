"""
RAG 子图状态定义
定义子图的状态结构、路由决策模型和辅助类型。

核心设计原则：
- 使用 TypedDict (total=False) 以兼容 LangGraph 的状态字典协议
- 需要跨节点聚合的列表字段使用 Annotated[..., add]
- Cypher/Visualization 子状态复用 components 目录下已有的定义，不重复声明
"""
from operator import add
from typing import Annotated, Any, Dict, List, Optional

try:
    from typing_extensions import TypedDict
except ImportError:
    from typing import TypedDict

from pydantic import BaseModel, Field

from gustobot.application.agents.rag_sub_graph.models.models import (
    Task,
)

# 对话历史
class CypherHistoryRecord(TypedDict):
    """Cypher 执行历史的精简记录，用于对话上下文展示。"""
    task: str
    statement: str
    records: List[Dict[str, Any]]

class HistoryRecord(TypedDict):
    """单轮对话历史记录。"""
    question: str
    answer: str
    cyphers: List[CypherHistoryRecord]

def _update_history(
    history: List[HistoryRecord], new: List[HistoryRecord]
) -> List[HistoryRecord]:
    """滑动窗口更新对话历史，保留最近 5 条记录。"""
    SIZE: int = 5
    history.extend(new)
    return history[-SIZE:]

class QueryInputState(TypedDict):
    """输入状态。"""
    task: str
    query_name: str # 预定义查询名称
    query_parameters: Dict[str, Any] # 查询参数
    steps: List[str]
    history: Annotated[List[HistoryRecord], _update_history] # 对话历史（滑动窗口）

class QueryOutputState(TypedDict):
    """输出状态，包含查询语句、参数、结果和错误信息。"""
    task: Annotated[list, add]
    statement: str
    parameters: Optional[Dict[str, Any]]
    errors: List[str]
    records: List[Dict[str, Any]]
    steps: List[str]
    history: Annotated[List[HistoryRecord], _update_history] # 对话历史（滑动窗口）

class RAGSubGraphInputState(TypedDict, total=False):
    """RAG 子图的输入状态，由主图在调用子图时填充。"""
    question: str                                           # 用户核心问题
    history: Annotated[List[HistoryRecord], _update_history] # 对话历史（滑动窗口）

class RAGSubGraphOutputState(TypedDict, total=False):
    """RAG 子图返回给主图的输出状态。"""
    answer: str                                             # 最终生成的回答
    question: str                                           # 用户原始问题（透传）
    steps: List[str]                                        # 执行步骤记录
    cyphers: List[Dict[str, Any]]                           # Cypher 查询结果集
    history: Annotated[List[HistoryRecord], _update_history] # 更新后的对话历史

class RAGSubGraphState(TypedDict, total=False):
    """
    RAG 子图全局状态（核心上下文）。

    字段说明：
    - question      : 用户提出的核心问题，贯穿整个子图生命周期
    - tasks         : Planner 拆解出的子任务列表（聚合追加）
    - next_action   : 路由控制字段，决定下一跳节点（guardrails / planner / tool_selection / end）
    - cyphers       : 各子任务的 Cypher 查询结果（聚合追加）
    - summary       : Summarization 节点生成的摘要文本
    - steps         : 全局执行步骤追踪（聚合追加）
    - history       : 对话历史（滑动窗口聚合）
    """
    question: str
    tasks: Annotated[List[Task], add]
    next_action: str
    cyphers: Annotated[List[Dict[str, Any]], add]
    summary: str
    answer: str
    steps: Annotated[List[str], add]
    history: Annotated[List[HistoryRecord], _update_history]