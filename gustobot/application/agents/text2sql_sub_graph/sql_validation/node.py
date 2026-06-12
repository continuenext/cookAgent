"""
SQL 验证节点
"""
from __future__ import annotations

import re
from typing import Any, Callable, Coroutine, Dict, List, Set, Tuple

from gustobot.application.agents.text2sql_sub_graph.states import Text2SQLState
from gustobot.infrastructure.core.logger import get_logger


logger = get_logger(service="text2sql.sql_validation")


def create_sql_validation_node(
    db_type: str = "MySQL",
) -> Callable[[Text2SQLState], Coroutine[Any, Any, Dict[str, Any]]]:
    """构建 LangGraph 节点，对上游生成的 SQL 进行语法和安全校验。"""
    logger.info("创建 SQL 验证节点，数据库类型: %s", db_type)

    async def validate_sql(state: Text2SQLState) -> Dict[str, Any]:
        logger.info("-----开始验证 SQL 语句-----")

        sql_statement = state.get("sql_statement", "")
        current_retry = state.get("retry_count", 0) # 获取当前重试次数，默认为 0

        if not sql_statement:
            logger.warning("SQL 语句为空，跳过验证")
            return {
                "is_valid": False,
                "validation_errors": ["SQL 语句为空"],
                "retry_count": current_retry + 1,
                "steps": ["sql_validation_failed"],
            }

        errors: List[str] = []

        try:
            syntax_ok, syntax_errors = validate_sql_syntax(sql_statement, db_type)
            if not syntax_ok:
                errors.extend(syntax_errors)
                logger.warning("SQL 语法验证失败: %s", syntax_errors)

            security_ok, security_warnings = validate_sql_security(sql_statement)
            if not security_ok:
                errors.extend(security_warnings)
                logger.warning("SQL 安全检查警示: %s", security_warnings)

            # Schema 校验：检查 SQL 中引用的表名和列名是否在 schema_context 中存在
            schema_context = state.get("schema_context") or {}
            if schema_context.get("tables"):
                schema_ok, schema_errors = validate_sql_schema(sql_statement, schema_context)
                if not schema_ok:
                    errors.extend(schema_errors)
                    logger.warning("SQL Schema 校验失败: %s", schema_errors)

            is_valid = not errors
            next_retry = current_retry if is_valid else current_retry + 1

            if is_valid:
                logger.info("SQL 验证通过")
            else:
                logger.error("SQL 验证失败: %s", errors)

            return {
                "is_valid": is_valid,
                "validation_errors": errors,
                "retry_count": next_retry,
                "steps": ["sql_validation" if is_valid else "sql_validation_failed"],
            }
        except Exception as exc:
            logger.exception("SQL 验证过程出错: %s", exc)
            return {
                "is_valid": False,
                "validation_errors": [f"验证过程出错: {exc}"],
                "retry_count": current_retry + 1,
                "steps": ["sql_validation_error"],
            }

    return validate_sql

def validate_sql_syntax(sql: str, db_type: str = "MySQL") -> Tuple[bool, List[str]]:
    """
    对 LLM 生成的 SQL 进行轻量级语法检查：是否为空，以 SELECT 或 WITH 开头、括号和引号匹配等。
    """
    errors: List[str] = []

    if not sql or not sql.strip():
        errors.append("SQL 语句为空")
        return False, errors

    sql_upper = sql.upper()
    leading_sql = sql_upper.lstrip()
    if not (leading_sql.startswith("SELECT") or leading_sql.startswith("WITH")):
        errors.append("仅支持以 SELECT 或 WITH 开头的只读查询")

    if sql.count("(") != sql.count(")"):
        errors.append("括号不匹配")
    if sql.count("'") % 2 != 0:
        errors.append("单引号不匹配")
    if sql.count('"') % 2 != 0:
        errors.append("双引号不匹配")

    return len(errors) == 0, errors


def validate_sql_security(sql: str) -> Tuple[bool, List[str]]:
    """
    检测明显的破坏性 SQL 操作。
    """
    warnings: List[str] = []
    sql_upper = sql.upper()

    dangerous_keywords = [
        "DROP TABLE",
        "DROP DATABASE",
        "TRUNCATE",
        "DELETE FROM",
        "INSERT INTO",
        "UPDATE ",
        "MERGE ",
        "ALTER TABLE",
        "CREATE TABLE",
        "CREATE DATABASE",
        "GRANT",
        "REVOKE",
        "CALL ",
        "EXEC ",
    ]

    for keyword in dangerous_keywords:
        if keyword in sql_upper:
            warnings.append(f"检测到危险操作: {keyword}")

    if "DELETE FROM" in sql_upper or "UPDATE" in sql_upper:
        if "WHERE" not in sql_upper:
            warnings.append("UPDATE/DELETE 语句缺少 WHERE 子句，可能影响所有行")

    return len(warnings) == 0, warnings


def validate_sql_schema(
    sql: str, schema_context: Dict[str, Any]
) -> Tuple[bool, List[str]]:
    """
    校验 SQL 中引用的表名和列名是否在 schema_context 中真实存在。
    支持 table.column 格式和无前缀列名两种情况。
    """
    errors: List[str] = []

    # 构建 schema 映射：table_name -> {col1, col2, ...}
    tables_info: Dict[str, Set[str]] = {}
    for table in schema_context.get("tables", []):
        tname = table["table_name"].lower()
        cols = {c["column_name"].lower() for c in table.get("columns", [])}
        tables_info[tname] = cols

    if not tables_info:
        return True, errors

    all_columns: Set[str] = set()
    for cols in tables_info.values():
        all_columns |= cols

    # 提取 SQL 中的表别名映射：alias -> real_table_name
    alias_map: Dict[str, str] = {}
    alias_pattern = re.compile(
        r"(?:FROM|JOIN)\s+`?(\w+)`?\s+(?:AS\s+)?`?(\w+)`?",
        re.IGNORECASE,
    )
    for match in alias_pattern.finditer(sql):
        table_name = match.group(1).lower()
        alias = match.group(2).lower()
        if alias not in _SQL_KEYWORDS:
            alias_map[alias] = table_name

    # 提取 FROM/JOIN 中涉及的真实表名
    referenced_tables: Set[str] = set()
    all_sql_tables: Set[str] = set()  # SQL 中所有引用的表名（含不存在的）
    table_ref_pattern = re.compile(r"(?:FROM|JOIN)\s+`?(\w+)`?", re.IGNORECASE)
    for match in table_ref_pattern.finditer(sql):
        tname = match.group(1).lower()
        all_sql_tables.add(tname)
        if tname in tables_info:
            referenced_tables.add(tname)

    # 检查 SQL 中引用的表是否存在于 schema_context 中
    for tname in all_sql_tables:
        if tname not in tables_info:
            available = ", ".join(sorted(tables_info.keys()))
            errors.append(
                f"表 `{tname}` 不存在于当前 Schema 中，可用的表: {available}"
            )

    # 提取 AS 定义的别名（SELECT 列别名和子查询别名），避免误判
    as_aliases: Set[str] = set()
    as_pattern = re.compile(r"\bAS\s+`?(\w+)`?", re.IGNORECASE)
    for match in as_pattern.finditer(sql):
        as_aliases.add(match.group(1).lower())

    # 记录已报错的列名，避免重复
    reported_cols: Set[str] = set()

    # 1) 检查 table.column 格式的引用
    qualified_pattern = re.compile(r"`?(\w+)`?\.`?(\w+)`?")
    for match in qualified_pattern.finditer(sql):
        ref_table = match.group(1).lower()
        ref_col = match.group(2).lower()
        real_table = alias_map.get(ref_table, ref_table)

        if real_table not in tables_info:
            continue

        if ref_col not in tables_info[real_table] and ref_col not in reported_cols:
            reported_cols.add(ref_col)
            suggestions = _find_similar_columns(ref_col, tables_info[real_table])
            hint = f"，你是否想用: {', '.join(suggestions)}" if suggestions else ""
            errors.append(f"列 `{ref_col}` 不存在于表 `{real_table}` 中{hint}")

    # 2) 检查无前缀列名：先移除字符串和 qualified 引用，再检查每个裸标识符
    sql_no_strings = re.sub(r"'[^']*'", "", sql)  # 移除字符串字面值
    sql_no_qualified = re.sub(r"`?\w+`?\.`?\w+`?", "", sql_no_strings)  # 移除 table.col

    # 当只引用单表时，裸列名必须属于该表
    single_table_cols: Set[str] | None = None
    if len(referenced_tables) == 1:
        single_table = next(iter(referenced_tables))
        single_table_cols = tables_info.get(single_table, set())

    bare_col_pattern = re.compile(r"\b(\w+)\b")
    for match in bare_col_pattern.finditer(sql_no_qualified):
        token = match.group(1).lower()
        # 跳过 SQL 关键词、表名、别名、数字、AS 别名
        if (token in _SQL_KEYWORDS or token in tables_info or token in alias_map
                or token in as_aliases or token.isdigit() or token.startswith("0x")):
            continue
        if token in reported_cols:
            continue

        # 单表查询：裸列名必须属于该表
        if single_table_cols is not None:
            if token in single_table_cols:
                continue  # 列名正确
            # token 不在该表中 → 检查是否在其他表中（常见错列引用）
            if token in all_columns:
                single_table = next(iter(referenced_tables))
                suggestions = _find_similar_columns(token, single_table_cols)
                hint = f"，你是否想用: {', '.join(suggestions)}" if suggestions else ""
                reported_cols.add(token)
                errors.append(
                    f"列 `{token}` 不存在于表 `{single_table}` 中{hint}"
                )
                continue
        else:
            # 多表查询：裸列名只要在任意引用表中存在即可
            if token in all_columns:
                continue

        # 到这里是一个未知标识符 → 检查它是否是某个已知列的近似（子串关系）
        # 如果是，大概率是 LLM 缩写/简写了列名
        similar = _find_similar_columns(token, all_columns)
        if similar:
            reported_cols.add(token)
            errors.append(
                f"列 `{token}` 不存在于任何已知表中，你是否想用: {', '.join(similar)}"
            )

    return len(errors) == 0, errors


def _find_similar_columns(target: str, candidates: Set[str]) -> List[str]:
    """找到候选集中与 target 有子串关系的列名。"""
    return sorted(c for c in candidates if target in c or c in target)


_SQL_KEYWORDS: Set[str] = {
    "select", "from", "where", "join", "left", "right", "inner", "outer",
    "cross", "natural", "group", "order", "having", "limit", "union", "set",
    "and", "or", "not", "as", "on", "in", "is", "null", "like", "between",
    "exists", "case", "when", "then", "else", "end", "asc", "desc", "by",
    "distinct", "all", "any", "some", "true", "false", "count", "sum", "avg",
    "min", "max", "cast", "coalesce", "ifnull", "concat", "substring",
    "trim", "upper", "lower", "length", "round", "floor", "ceil", "abs",
    "now", "date", "year", "month", "day", "hour", "minute", "second",
    "with", "recursive", "offset", "fetch", "next", "rows", "only",
    "over", "partition", "row_number", "rank", "dense_rank", "ntile",
    "lead", "lag", "first_value", "last_value", "into",
    "unsigned", "signed", "int", "bigint", "varchar", "text", "decimal",
    "float", "double", "boolean", "datetime", "timestamp",
}
