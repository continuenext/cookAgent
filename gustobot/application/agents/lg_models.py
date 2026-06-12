from pydantic import Field, BaseModel
from typing import Literal


class GuardrailsOutput(BaseModel):
    """
    格式化输出，用于判断用户的问题是否与图谱内容相关
    """
    decision: Literal["end", "proceed"] = Field(
        description="如果用户的问题与图谱内容无关，返回 'end'，否则返回 'proceed'"
    )