from operator import add
from typing import Annotated, Any, Dict, List, Optional

try:
    from typing_extensions import TypedDict
except ImportError:
    from typing import TypedDict

from pydantic import BaseModel, Field
    
# 任务模型
class Task(BaseModel):
    """Planner 拆解出的单个子任务。"""
    question: str = Field(..., description="该任务需要解决的问题。")
    parent_task: str = Field(
        ..., description="这个任务派生自哪个父任务。"
    )
    data: Optional[Dict[str, Any]] = Field(
        default=None, description="Cypher 查询结果的详细信息。"
    )


class PlannerOutput(BaseModel):
    """Planner 节点的 LLM 结构化输出。"""
    tasks: list[Task] = Field(
        default_factory=list,
        description="LLM 输出的任务列表，每个任务包含问题、父任务、是否需要可视化等信息。",
    )
