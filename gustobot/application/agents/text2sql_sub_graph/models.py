"""
Text2SQL 子图 Pydantic 模型定义
"""
from typing import List

from pydantic import BaseModel, Field


class SQLAnalysis(BaseModel):
    """结构化查询分析结果，由 LLM 生成。"""
    query_intent: str = Field(default="", description="用户查询的核心诉求")
    required_tables: List[str] = Field(default_factory=list, description="需要查询的表")
    required_columns: List[str] = Field(default_factory=list, description="需要查询的字段")
    join_conditions: str = Field(default="", description="表连接逻辑")
    filter_conditions: str = Field(default="", description="筛选条件")
    aggregation: str = Field(default="", description="聚合需求")
    order_by: str = Field(default="", description="排序需求")
    notes: str = Field(default="", description="补充说明")


