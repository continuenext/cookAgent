"""
上下文工程管理模块 —— 负责 token 计数、对话历史压缩、上下文窗口预算分配。

核心能力：
1. count_tokens / count_messages_tokens — 精确 token 计数
2. trim_messages           — 滑动窗口截断（保留最近 N 轮）
3. summarize_history       — LLM 摘要压缩旧对话
4. compress_if_needed      — 自适应压缩（超阈值自动摘要）
5. build_context_window    — 按预算分配 system / history / retrieval 三段上下文
6. compress_schema         — 按用户问题过滤图谱 schema 中无关段落
7. compress_retrieval_results — 渐进式摘要压缩大段检索结果
"""

from __future__ import annotations

import re
import tiktoken
from typing import Any, Dict, List, Optional, Sequence

from langchain_core.messages import (
    AIMessage,
    AnyMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    trim_messages as lc_trim_messages,
)

from gustobot.config.settings import settings
from gustobot.infrastructure.core.logger import get_logger

logger = get_logger(service="context_manager")

# ───────────── 配置常量 ─────────────
# qwen / gpt 系列模型统一使用 cl100k_base 编码
_ENCODING_NAME = "cl100k_base"
_enc: Optional[tiktoken.Encoding] = None

# 每条消息的固定开销 token（role 标记、分隔符等），参考 OpenAI 计算规则
_MSG_OVERHEAD = 4


def _get_encoding() -> tiktoken.Encoding:
    """懒加载 tiktoken 编码器（进程内单例）。"""
    global _enc
    if _enc is None:
        _enc = tiktoken.get_encoding(_ENCODING_NAME)
    return _enc


# ───────────── 1. Token 计数 ─────────────

def count_tokens(text: str) -> int:
    """计算单段文本的 token 数。"""
    return len(_get_encoding().encode(text))


def count_message_tokens(msg: Any) -> int:
    """计算单条 LangChain Message 的 token 数（含消息体开销）。"""
    content = ""
    if isinstance(msg, BaseMessage):
        content = str(msg.content or "")
    elif isinstance(msg, dict):
        content = str(msg.get("content", ""))
    else:
        content = str(msg)
    return count_tokens(content) + _MSG_OVERHEAD


def count_messages_tokens(messages: Sequence[Any]) -> int:
    """计算消息列表的总 token 数。"""
    return sum(count_message_tokens(m) for m in messages)


# ───────────── 2. 滑动窗口截断 ─────────────

def trim_messages(
    messages: List[AnyMessage],
    *,
    max_tokens: int,
    strategy: str = "last",
    allow_partial: bool = False,
) -> List[AnyMessage]:
    """
    按 token 预算截断消息列表。
    
    Args:
        messages: 原始消息列表
        max_tokens: 允许的最大 token 数
        strategy: "last"=保留最新消息（从尾部）, "first"=保留最早消息
        allow_partial: 是否允许截断单条消息内容（默认整条保留或丢弃）
    
    Returns:
        截断后的消息列表
    """
    return lc_trim_messages(
        messages,
        max_tokens=max_tokens,
        token_counter=count_message_tokens,
        strategy=strategy,
        allow_partial=allow_partial,
    )


# ───────────── 3. LLM 摘要压缩 ─────────────

_SUMMARIZE_PROMPT = """
你是一名菜谱管理系统中的对话历史压缩专家。你的任务是将长篇的多轮对话浓缩为高密度的核心上下文，以供下游的图谱查询（Cypher）或结构化查询（SQL）模块精准提取参数。

请遵循以下压缩规则：

## 压缩原则
1. **彻底去噪**：删除所有日常寒暄、系统致歉、重复解释等无效沟通内容。
2. **实体保护**：必须一字不差地保留用户提及的"食材名称"（如：五花肉）、"菜谱实体"（如：麻婆豆腐）以及具体的"数值/过滤条件"（如：卡路里<300、排名前5）。
3. **偏好提取**：准确抓取并单独提取用户的长期饮食偏好（如：忌口、过敏原、口味偏好）。
4. **聚焦未决**：精准识别并点明用户当前最终尚未解决的核心诉求。

## 输出格式要求
请严格使用中文，总字数控制在 300 字以内。必须精确按照以下列表格式输出结果，不要输出任何额外的解释性前缀或后缀：

- 用户偏好：[提取的忌口或偏好，若无则写"无"]
- 涉及实体：[提取的关键食材、菜品或数值条件]
- 当前诉求：[一句话概括当前需要解决的问题]

以下是需要压缩的原始对话历史：

<dialogue_history>
{history}
</dialogue_history>
"""


async def summarize_history(
    messages: List[AnyMessage],
    *,
    llm: Any = None,
) -> SystemMessage:
    """
    用 LLM 将一段旧对话压缩为摘要 SystemMessage。
    
    Args:
        messages: 需要被压缩的历史消息
        llm: LangChain ChatModel 实例；为 None 时内部创建默认实例
    
    Returns:
        包含摘要内容的 SystemMessage（可直接插入消息列表）
    """
    if not messages:
        return SystemMessage(content="")

    if llm is None:
        from gustobot.application.agents.utils.llm_factory import get_llm
        llm = get_llm(tags=["context_summarize"])

    # 将消息格式化为文本
    lines: list[str] = []
    for msg in messages:
        role = "用户" if isinstance(msg, HumanMessage) else "助手"
        if isinstance(msg, SystemMessage):
            continue  # 跳过 system 消息
        content = str(msg.content) if hasattr(msg, "content") else str(msg)
        lines.append(f"[{role}] {content}")

    history_text = "\n".join(lines)
    prompt = _SUMMARIZE_PROMPT.format(history=history_text)

    response = await llm.ainvoke([HumanMessage(content=prompt)])
    summary = str(response.content).strip()
    logger.info("对话历史压缩完成: %d 条消息 → %d tokens 摘要", len(messages), count_tokens(summary))

    return SystemMessage(content=f"[对话历史摘要]\n{summary}")


async def compress_if_needed(
    messages: List[AnyMessage],
    *,
    llm: Any = None,
) -> List[AnyMessage]:
    """
    自适应压缩：当对话历史总 token 超过阈值时，
    将旧消息用 LLM 摘要替换，保留最近 N 条原文。
    
    流程：
    1. 计算全部消息 token 数
    2. 如果未超过 CONTEXT_SUMMARY_THRESHOLD → 原样返回
    3. 超过 → 将旧消息（除最近 keep_recent 条）压缩为摘要 SystemMessage
    4. 返回 [摘要, ...最近 keep_recent 条消息]
    """
    threshold = settings.CONTEXT_SUMMARY_THRESHOLD
    keep_recent = settings.CONTEXT_SUMMARY_KEEP_RECENT

    total = count_messages_tokens(messages)
    if total <= threshold:
        return messages

    logger.info(
        "对话历史 %d tokens 超过阈值 %d，触发摘要压缩 (保留最近 %d 条)",
        total, threshold, keep_recent,
    )

    # 拆分：旧消息 | 最近消息
    if len(messages) <= keep_recent:
        return messages  # 消息条数太少，不压缩
    
    old_messages = messages[:-keep_recent] # 需要被压缩的旧消息
    recent_messages = messages[-keep_recent:] # 保留最近 N 条原文

    summary_msg = await summarize_history(old_messages, llm=llm)
    return [summary_msg] + recent_messages


# ───────────── 4. 上下文窗口预算分配 ─────────────

class ContextBudget:
    """
    上下文窗口预算管理器。
    
    将总 token 预算按比例分配给三个区段：
    - system_prompt:  固定系统指令
    - history:        对话历史
    - retrieval:      检索上下文（RAG / schema / 文件等）
    
    剩余空间留给模型输出。
    """

    def __init__(
        self,
        total_context: int = 0,
        output_reserve: int = 0,
        system_tokens: int = 0,
        retrieval_tokens: int = 0,
    ):
        """
        Args:
            total_context:   模型上下文窗口总量（例如 131072 for qwen3-max）
            output_reserve:  为输出保留的 token 数
            system_tokens:   system prompt 实际占用的 token 数
            retrieval_tokens: 检索上下文实际占用的 token 数
        """
        _total = total_context or settings.CONTEXT_WINDOW_TOTAL
        _reserve = output_reserve or settings.CONTEXT_OUTPUT_RESERVE
        self.total_context = _total
        self.output_reserve = _reserve
        self.system_tokens = system_tokens
        self.retrieval_tokens = retrieval_tokens

    @property
    def history_budget(self) -> int:
        """对话历史可用的最大 token 数（总量 - 输出预留 - system - retrieval）。"""
        available = self.total_context - self.output_reserve - self.system_tokens - self.retrieval_tokens
        return max(available, 0)


def build_context_window(
    *,
    system_prompt: str,
    messages: List[AnyMessage],
    retrieval_context: str = "",
    max_history_tokens: int = 0,
) -> List[AnyMessage]:
    """
    组装最终发送给 LLM 的消息列表，自动进行历史截断。
    
    Args:
        system_prompt:     系统提示词文本
        messages:          完整对话历史
        retrieval_context: 检索到的上下文（RAG 文档、schema 等），
                        #    会作为 SystemMessage 追加在 system_prompt 之后
        max_history_tokens: 对话历史最大 token 数；
                            为 0 时自动根据 ContextBudget 计算
    
    Returns:
        [SystemMessage, (optional SystemMessage for retrieval), ...trimmed history]
    """
    sys_tokens = count_tokens(system_prompt)
    ret_tokens = count_tokens(retrieval_context) if retrieval_context else 0

    if max_history_tokens <= 0:
        budget = ContextBudget(system_tokens=sys_tokens, retrieval_tokens=ret_tokens)
        max_history_tokens = budget.history_budget

    # 截断对话历史
    trimmed = trim_messages(messages, max_tokens=max_history_tokens)

    if len(trimmed) < len(messages):
        logger.info(
            "对话历史已截断: %d → %d 条 (预算 %d tokens)",
            len(messages), len(trimmed), max_history_tokens,
        )

    # 拼装最终消息列表
    result: List[AnyMessage] = [SystemMessage(content=system_prompt)]
    if retrieval_context:
        result.append(SystemMessage(content=retrieval_context))
    result.extend(trimmed)
    return result


# ───────────── 6. Schema 相关性过滤 ─────────────

def compress_schema(schema_text: str, question: str, *, max_tokens: int = 2000) -> str:
    """
    按用户问题过滤图谱 schema，只保留与问题关键词相关的段落。
    
    策略：
    1. 将 schema 按段落拆分（每个节点/关系类型为一段）
    2. 对每段计算与问题的关键词重叠度
    3. 优先保留高重叠段落，直到 token 预算用完
    4. 如果所有段落都不匹配（纯结构性问题），保留前 max_tokens 的内容
    
    Args:
        schema_text: graph_schema_to_nl() 返回的完整 schema 文本
        question:    用户问题
        max_tokens:  schema 最大允许 token 数
    
    Returns:
        过滤/截断后的 schema 文本
    """
    if not schema_text:
        return schema_text

    current_tokens = count_tokens(schema_text)
    if current_tokens <= max_tokens:
        return schema_text  # 未超限，原样返回

    # 按段落拆分（以 "- **" 开头或空行分隔的段落）
    paragraphs = re.split(r'\n(?=- \*\*|\n)', schema_text)
    if len(paragraphs) <= 1:
        paragraphs = schema_text.split('\n\n')

    # 提取问题关键词：2-gram + 3-gram（适合中文短语匹配，比单字符精确）
    q_clean = re.sub(r'[^\u4e00-\u9fff\w]', '', question.lower())
    q_ngrams: set[str] = set()
    for n in (2, 3):
        for i in range(len(q_clean) - n + 1):
            q_ngrams.add(q_clean[i:i + n])
    # 补充完整的英文单词
    q_ngrams.update(re.findall(r'[a-z]+', question.lower()))

    # 为每段计算相关性分数
    scored: list[tuple[float, int, str]] = []
    for idx, para in enumerate(paragraphs):
        para = para.strip()
        if not para:
            continue
        para_lower = re.sub(r'[^\u4e00-\u9fff\w]', '', para.lower())
        # 统计问题 n-gram 在段落中出现的次数（命中越多越相关）
        hits = sum(1 for ng in q_ngrams if ng in para_lower)
        scored.append((hits, idx, para))

    # 按相关性降序排列
    scored.sort(key=lambda x: (-x[0], x[1]))

    # 贪心选取每段，不超过预算
    selected: list[tuple[int, str]] = []
    used_tokens = 0
    for _score, idx, para in scored:
        para_tokens = count_tokens(para)
        if used_tokens + para_tokens > max_tokens:
            continue
        selected.append((idx, para))
        used_tokens += para_tokens

    if not selected:
        # 兜底：至少保留第一段
        first = scored[0][2] if scored else schema_text
        return first[:int(max_tokens * 0.7)] + "\n... [图谱结构已压缩]"

    # 按原始顺序恢复
    selected.sort(key=lambda x: x[0])
    result = "\n\n".join(para for _, para in selected)

    if len(selected) < len(scored):
        result += f"\n\n... [已保留 {len(selected)}/{len(scored)} 个相关段落]"

    logger.info("schema 压缩: %d → %d tokens (%d/%d 段落)",
                current_tokens, count_tokens(result), len(selected), len(scored))
    return result


def compress_sql_schema(
    schema_context: Dict[str, Any],
    question: str,
    *,
    max_tokens: int = 0,
) -> Dict[str, Any]:
    """
    根据用户问题裁剪 SQL schema，减少传入 LLM 的列数。
    
    策略：
    1. 对每张表的每列进行相关性评分（基于列名/描述与问题的 n-gram 匹配）
    2. 每张表至少保留主键列和外键列（保证 JOIN 能力）
    3. 按评分排序，在 token 预算内尽可能多保留高分列
    4. 如果原始 schema 未超预算，原样返回
    
    Args:
        schema_context: 包含 "tables" 和 "relationships" 的 schema 字典
        question:       用户问题
        max_tokens:     schema 文本最大 token 预算；0 时使用 settings 默认值
    
    Returns:
        裁剪后的 schema_context 字典（结构与输入一致）
    """
    if not schema_context or not schema_context.get("tables"):
        return schema_context

    if max_tokens <= 0:
        max_tokens = settings.CONTEXT_SQL_SCHEMA_MAX_TOKENS

    # 先检查原始 schema 是否超预算
    from gustobot.application.agents.text2sql_sub_graph.utils import format_schema_to_text
    original_text = format_schema_to_text(schema_context)
    original_tokens = count_tokens(original_text)

    if original_tokens <= max_tokens:
        return schema_context

    logger.info("SQL schema %d tokens 超过预算 %d，开始列级裁剪", original_tokens, max_tokens)

    # 提取问题 n-gram
    q_clean = re.sub(r'[^\u4e00-\u9fff\w]', '', question.lower())
    q_ngrams: set[str] = set()
    for n in (2, 3):
        for i in range(len(q_clean) - n + 1):
            q_ngrams.add(q_clean[i:i + n])
    q_ngrams.update(re.findall(r'[a-z_]+', question.lower()))

    trimmed_tables: list[Dict[str, Any]] = []

    for table in schema_context["tables"]:
        columns = table.get("columns", [])
        scored_cols: list[tuple[int, bool, Dict[str, Any]]] = []

        for col in columns:
            col_name = col.get("column_name", "").lower()
            col_desc = col.get("description", "").lower()
            is_key = col.get("is_primary_key") or col.get("is_foreign_key")

            # 计算相关性
            text_to_match = col_name + " " + col_desc
            text_clean = re.sub(r'[^\u4e00-\u9fff\w]', '', text_to_match)
            hits = sum(1 for ng in q_ngrams if ng in text_clean)

            scored_cols.append((hits, bool(is_key), col))

        # 排序：关键列优先，然后按相关性降序
        scored_cols.sort(key=lambda x: (-int(x[1]), -x[0]))

        # 保留逻辑：主键/外键必留，其余按分数贪心选取
        kept_cols: list[Dict[str, Any]] = []
        for _score, is_key, col in scored_cols:
            if is_key or _score > 0:
                kept_cols.append(col)
            elif len(kept_cols) < 3:
                # 每张表至少保留 3 列（避免上下文太少导致 SQL 生成失败）
                kept_cols.append(col)

        trimmed_table = {**table, "columns": kept_cols}
        trimmed_tables.append(trimmed_table)

    result = {
        "tables": trimmed_tables,
        "relationships": schema_context.get("relationships", []),
    }

    # 验证裁剪后大小
    result_text = format_schema_to_text(result)
    result_tokens = count_tokens(result_text)
    total_cols_before = sum(len(t.get("columns", [])) for t in schema_context["tables"])
    total_cols_after = sum(len(t.get("columns", [])) for t in trimmed_tables)
    logger.info("SQL schema 列级裁剪: %d → %d tokens, 列数 %d → %d",
                original_tokens, result_tokens, total_cols_before, total_cols_after)

    return result


# ───────────── 7. 渐进式检索结果压缩 ─────────────

_CHUNK_SUMMARIZE_PROMPT = """
你是菜谱系统中的检索内容提纯引擎。你的任务是将底层数据库（图数据库/向量库）返回的冗长检索结果，浓缩为高密度的知识摘要，供下游节点准确回答用户问题。

请严格遵循以下提纯规则：

## 提纯原则
1. **核心事实保护**：必须一字不差地保留与菜谱相关的绝对事实，包括：具体的食材清单及精确用量、核心烹饪步骤（火候/时间）、营养数值、以及特定的历史文化节点。
2. **极致去重去噪**：合并语义重复的句子，坚决删去无关的解释性连词、多余的 HTML/JSON 结构符以及冗余的描述。
3. **零幻觉红线**：仅对提供的文本进行客观压缩，绝对不要在摘要中加入任何你的个人推断、评价或外部知识。

## 输出要求
请严格使用中文，采用精简的短句或项目符号，总字数必须控制在 200 字以内。

以下是需要提纯的原始检索结果：

<retrieved_context>
{chunk}
</retrieved_context>
"""


async def compress_retrieval_results(
    formatted_results: str,
    *,
    max_tokens: int = 6000,
    llm: Any = None,
) -> str:
    """
    渐进式摘要压缩检索结果。当结果超过 max_tokens 时，
    将其分块后逐块 LLM 摘要，最终合并为一段紧凑的上下文。
    
    Args:
        formatted_results: 格式化的检索结果文本
        max_tokens:        允许的最大 token 数
        llm:               LangChain ChatModel；为 None 时内部创建
    
    Returns:
        压缩后的检索结果文本
    """
    current_tokens = count_tokens(formatted_results)
    if current_tokens <= max_tokens:
        return formatted_results

    logger.info("检索结果 %d tokens 超过阈值 %d，启动渐进式摘要压缩", current_tokens, max_tokens)

    if llm is None:
        from gustobot.application.agents.utils.llm_factory import get_llm
        llm = get_llm(tags=["context_compress"])

    # 按双换行拆分为多个块，并过滤空段
    sections = [s for s in formatted_results.split("\n\n") if s.strip()]

    def _split_by_token_limit(text: str, token_limit: int) -> list[str]:
        """将超长文本按 token 上限切片，避免单块超过模型输入限制。"""
        if not text.strip():
            return []
        text_tokens = _get_encoding().encode(text)
        if len(text_tokens) <= token_limit:
            return [text]

        parts: list[str] = []
        for i in range(0, len(text_tokens), token_limit):
            part = _get_encoding().decode(text_tokens[i:i + token_limit]).strip()
            if part:
                parts.append(part)
        return parts

    # 将相邻段落合并为不超过 chunk_size tokens 的块
    chunks: list[str] = []
    current_chunk: list[str] = []
    chunk_tokens = 0
    _chunk_size = settings.CONTEXT_CHUNK_SIZE

    for section in sections:
        if not section.strip():
            continue
        sec_tokens = count_tokens(section)

        # 单段超过 chunk_size 时，先切片再入队，避免把超长段整体送入 LLM
        if sec_tokens > _chunk_size:
            if current_chunk:
                chunks.append("\n\n".join(current_chunk))
                current_chunk = []
                chunk_tokens = 0
            chunks.extend(_split_by_token_limit(section, _chunk_size))
            continue

        if chunk_tokens + sec_tokens > _chunk_size and current_chunk:
            chunks.append("\n\n".join(current_chunk))
            current_chunk = [section]
            chunk_tokens = sec_tokens
        else:
            current_chunk.append(section)
            chunk_tokens += sec_tokens

    if current_chunk:
        chunks.append("\n\n".join(current_chunk))

    # 逐块 LLM 摘要
    summaries: list[str] = []
    for i, chunk in enumerate(chunks):
        if not chunk.strip():
            continue
        try:
            prompt = _CHUNK_SUMMARIZE_PROMPT.format(chunk=chunk)
            response = await llm.ainvoke([HumanMessage(content=prompt)])
            summary = str(response.content).strip()
            summaries.append(summary)
        except Exception as e:
            logger.warning("第 %d 块摘要失败，保留原文: %s", i, e)
            summaries.append(chunk)

    result = "\n\n".join(summaries)
    result_tokens = count_tokens(result)
    logger.info("检索结果压缩完成: %d → %d tokens (%d 块)", current_tokens, result_tokens, len(chunks))

    # 如果摘要后仍然超限，进行硬截断
    if result_tokens > max_tokens:
        max_chars = int(max_tokens * 0.7)
        result = result[:max_chars] + "\n\n... [检索结果已压缩摘要]"

    return result
