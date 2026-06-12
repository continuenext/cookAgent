"""
Text2SQL 工具函数
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from gustobot.application.agents.text2sql_sub_graph.models import SQLAnalysis
from .domain_knowledge import COLUMN_DESCRIPTIONS, TABLE_DESCRIPTIONS

def render_analysis_markdown(
    analysis: SQLAnalysis,
    value_mappings: Optional[Dict[str, Any]] = None,
) -> str:
    """将 SQLAnalysis 渲染为 Markdown 文本，供后续 LLM 上下文使用。"""
    lines = [f"**查询意图**：{analysis.query_intent}"]

    if analysis.required_tables:
        lines.append(f"**涉及表**：{', '.join(analysis.required_tables)}")
    if analysis.required_columns:
        lines.append(f"**涉及字段**：{', '.join(analysis.required_columns)}")
    if analysis.join_conditions:
        lines.append(f"**连接条件**：{analysis.join_conditions}")
    if analysis.filter_conditions:
        lines.append(f"**筛选条件**：{analysis.filter_conditions}")
    if analysis.aggregation:
        lines.append(f"**聚合需求**：{analysis.aggregation}")
    if analysis.order_by:
        lines.append(f"**排序需求**：{analysis.order_by}")
    if analysis.notes:
        lines.append(f"**备注**：{analysis.notes}")

    return "\n".join(lines)


def format_schema_to_text(schema_context: Dict[str, Any]) -> str:
    """将 schema 上下文转换为 SQL 风格的文本描述，供提示词使用。"""
    if not schema_context or not schema_context.get("tables"):
        return "-- 无可用的 Schema 信息"
        
    lines: List[str] = []

    for table in schema_context.get("tables", []):
        table_name = table.get("table_name", "unknown_table")
        table_key = table_name.lower()
        description = table.get("description") or TABLE_DESCRIPTIONS.get(table_key) or ""

        lines.append(f"-- 表: {table_name}")
        if description:
            lines.append(f"-- 说明: {description}")

        lines.append(f"CREATE TABLE {table_name} (")
        columns = table.get("columns", [])
        for index, column in enumerate(columns):
            column_name = column.get("column_name", "col")
            data_type = column.get("data_type", "TEXT")
            column_key = (table_key, column_name.lower())
            column_description = column.get("description") or COLUMN_DESCRIPTIONS.get(column_key) or ""
            column_constraints: List[str] = []
            if column.get("is_primary_key"):
                column_constraints.append("PRIMARY KEY")
            if column.get("is_foreign_key"):
                column_constraints.append("FOREIGN KEY")
            if column.get("is_unique"):
                column_constraints.append("UNIQUE")

            constraint_str = f" {' '.join(column_constraints)}" if column_constraints else ""
            comma = "," if index < len(columns) - 1 else ""
            lines.append(f"    {column_name} {data_type}{constraint_str}{comma}")
            if column_description:
                lines.append(f"    -- {column_description}")

        lines.append(");")
        lines.append("")

    relationships = schema_context.get("relationships") or []
    if relationships:
        lines.append("-- 表关系")
        for rel in relationships:
            source_table = rel.get("source_table")
            source_column = rel.get("source_column")
            target_table = rel.get("target_table")
            target_column = rel.get("target_column")
            relationship_type = rel.get("relationship_type", "N/A")
            description = rel.get("description") or ""
            lines.append(
                f"-- {source_table}.{source_column} -> {target_table}.{target_column} ({relationship_type})"
            )
            if description:
                lines.append(f"--   {description}")

    return "\n".join(lines)