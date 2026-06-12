"""
SQL 生成提示词模板
"""
from __future__ import annotations

from typing import Dict, List, Any

from langchain_core.prompts import ChatPromptTemplate

from ..domain_knowledge import COLUMN_DESCRIPTIONS, DOMAIN_SUMMARY, TABLE_DESCRIPTIONS


def create_sql_generation_prompt() -> ChatPromptTemplate:
    system_message = """
    你是一名资深 SQL 开发工程师。请根据提供的数据库 Schema、值映射信息和查询分析结果，生成符合 {db_type} 语法的 SQL 查询。

    约束条件：
    1. 只使用提供的表与字段。
    2. 严格遵循查询分析给出的意图、筛选条件、连接方式等，如需调整请在最终解释中说明。
    3. 使用值映射信息将自然语言术语转换为数据库中的真实值。
    4. 输出必须是**单条 SQL 语句**，不能包含额外解释或多条语句。
    5. 默认只生成只读查询（SELECT/CTE）。
"""
    system_message = (
        system_message.strip()
        + "\n\n数据库真实结构背景：\n"
        + DOMAIN_SUMMARY
    )

    human_message = """
    ## 数据库 Schema
    ```sql
    {schema}
    ```

    ## 值映射
    {value_mappings}

    ## 查询分析摘要
    {analysis_summary}

    ## 用户问题
    {question}

    请输出最终 SQL 语句。
    """

    return ChatPromptTemplate.from_messages(
        [
            ("system", system_message.strip()),
            ("human", human_message.strip()),
        ]
    )
