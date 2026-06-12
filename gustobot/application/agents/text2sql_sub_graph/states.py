"""
Text2SQL 子图状态定义
"""
from operator import add
from typing import Annotated, Any, Dict, List, Optional

try:
    from typing_extensions import TypedDict
except ImportError:
    from typing import TypedDict


class Text2SQLInputState(TypedDict, total=False):
    """Text2SQL 子图的输入状态，由主图在调用时填充。"""
    question: str
    db_type: str  # 默认 "MySQL"
    max_rows: int  # 默认 1000
    max_retries: int  # 默认 3
    connection_string: Optional[str]


class Text2SQLOutputState(TypedDict, total=False):
    """Text2SQL 子图返回给主图的输出状态。"""
    answer: str
    sql_statement: str
    execution_results: List[Dict[str, Any]]
    steps: List[str]


class Text2SQLState(TypedDict, total=False):
    """
    Text2SQL 子图全局状态。

    字段说明：
    - question           : 用户的自然语言问题
    - db_type            : 数据库类型（默认 MySQL）
    - max_rows           : 最大返回行数
    - max_retries        : SQL 生成最大重试次数
    - connection_string  : 数据库连接字符串（可选覆盖）
    - next_action        : guardrails 路由决策（"proceed" / "end"）
    - schema_context     : 检索到的数据库 schema 上下文
    - value_mappings     : 值映射信息
    - mappings_str       : 值映射的文本表示
    - analysis           : 结构化查询分析结果（dict）
    - analysis_text      : 查询分析的 Markdown 文本
    - sql_statement      : 生成的 SQL 语句
    - is_valid           : SQL 验证是否通过
    - validation_errors  : 验证错误列表
    - retry_count        : 当前重试次数
    - execution_results  : SQL 执行结果
    - execution_error    : 执行错误信息
    - answer             : 格式化后的最终答案
    - steps              : 执行步骤追踪（聚合追加）
    """
    question: str
    db_type: str
    max_rows: int
    max_retries: int
    connection_string: Optional[str]

    # guardrails 输出
    next_action: str
    schema_context: Dict[str, Any]
    value_mappings: Dict[str, Any]
    mappings_str: str

    # query_analysis 输出
    analysis: Dict[str, Any]
    analysis_text: str

    # sql_generation 输出
    sql_statement: str

    # sql_validation 输出
    is_valid: bool
    validation_errors: List[str]
    retry_count: int

    # sql_execution 输出
    execution_results: List[Dict[str, Any]]
    execution_error: Optional[str]

    # formatting 输出
    answer: str

    # 全局
    steps: Annotated[List[str], add]
