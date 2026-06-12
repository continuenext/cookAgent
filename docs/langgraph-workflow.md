# GustoBot LangGraph 完整工作流（主图 + 子图）

```mermaid
graph TD
    classDef startEnd fill:#2d3436,color:#fff,stroke:#2d3436,stroke-width:2px
    classDef router fill:#e17055,color:#fff,stroke:#d63031,stroke-width:2px
    classDef business fill:#0984e3,color:#fff,stroke:#0652DD,stroke-width:2px
    classDef process fill:#00b894,color:#fff,stroke:#00a381,stroke-width:2px
    classDef ragNode fill:#6c5ce7,color:#fff,stroke:#5f27cd,stroke-width:2px
    classDef sqlNode fill:#fdcb6e,color:#2d3436,stroke:#f39c12,stroke-width:2px

    START((START)):::startEnd
    END_NODE((END)):::startEnd

    START --> analyze_and_route_query

    analyze_and_route_query["🔀 analyze_and_route_query<br/><i>意图识别 + 路由</i>"]:::router

    analyze_and_route_query -->|"general-query"| process_general_query
    analyze_and_route_query -->|"additional-query"| process_additional_query
    analyze_and_route_query -->|"graphrag-query"| rag_subgraph_wrapper
    analyze_and_route_query -->|"text2sql-query"| process_text2sql_query
    analyze_and_route_query -->|"image-query"| process_image_query
    analyze_and_route_query -->|"file-query"| process_file_query

    process_general_query["💬 process_general_query<br/><i>闲聊回复</i>"]:::business
    process_additional_query["❓ process_additional_query<br/><i>追问补充信息</i>"]:::business
    process_image_query["🖼️ process_image_query<br/><i>图片分析/生成</i>"]:::business
    process_file_query["📄 process_file_query<br/><i>文件处理</i>"]:::business

    subgraph RAG_SUBGRAPH ["📊 RAG 子图 (Neo4j GraphRAG)"]
        direction TB
        rag_start((START)):::startEnd
        rag_guardrails["🛡️ guardrails<br/><i>范围检查</i>"]:::ragNode
        rag_planner["📋 planner<br/><i>查询规划</i>"]:::ragNode
        rag_tool_selection["🔧 tool_selection<br/><i>工具选择</i>"]:::ragNode
        rag_cypher["⚡ cypher_query<br/><i>动态 Cypher</i>"]:::ragNode
        rag_predefined["📦 predefined_cypher<br/><i>预定义 Cypher</i>"]:::ragNode
        rag_graphrag["🔗 graphrag_query<br/><i>图谱多跳遍历</i>"]:::ragNode
        rag_summarize["📝 summarize<br/><i>结果摘要</i>"]:::ragNode
        rag_final["✅ final_answer<br/><i>生成回答</i>"]:::ragNode
        rag_end((END)):::startEnd

        rag_start --> rag_guardrails
        rag_guardrails -->|"planner"| rag_planner
        rag_guardrails -->|"end (超范围)"| rag_end
        rag_planner --> rag_tool_selection
        rag_tool_selection -->|"cypher_query"| rag_cypher
        rag_tool_selection -->|"predefined_cypher"| rag_predefined
        rag_tool_selection -->|"graphrag_query"| rag_graphrag
        rag_tool_selection -->|"summarize (直接)"| rag_summarize
        rag_cypher --> rag_summarize
        rag_predefined --> rag_summarize
        rag_graphrag --> rag_summarize
        rag_summarize --> rag_final
        rag_final --> rag_end
    end

    rag_subgraph_wrapper["🔀 rag_subgraph<br/><i>状态映射 wrapper</i>"]:::business
    rag_subgraph_wrapper -.-> RAG_SUBGRAPH

    subgraph TEXT2SQL_SUBGRAPH ["🗃️ Text2SQL 子图 (MySQL)"]
        direction TB
        sql_start((START)):::startEnd
        sql_guardrails["🛡️ guardrails<br/><i>范围检查</i>"]:::sqlNode
        sql_analysis["🔍 query_analysis<br/><i>需求分析</i>"]:::sqlNode
        sql_generation["⚙️ sql_generation<br/><i>SQL 生成</i>"]:::sqlNode
        sql_validation["✔️ sql_validation<br/><i>SQL 验证</i>"]:::sqlNode
        sql_execution["▶️ sql_execution<br/><i>SQL 执行</i>"]:::sqlNode
        sql_format["📊 format_answer<br/><i>格式化结果</i>"]:::sqlNode
        sql_end((END)):::startEnd

        sql_start --> sql_guardrails
        sql_guardrails -->|"proceed"| sql_analysis
        sql_guardrails -->|"end (超范围)"| sql_format
        sql_analysis --> sql_generation
        sql_generation --> sql_validation
        sql_validation -->|"valid"| sql_execution
        sql_validation -->|"invalid & retries < 3"| sql_generation
        sql_validation -->|"max retries"| sql_execution
        sql_execution --> sql_format
        sql_format --> sql_end
    end

    process_text2sql_query["🗃️ process_text2sql_query<br/><i>Text2SQL 入口</i>"]:::business
    process_text2sql_query -.-> TEXT2SQL_SUBGRAPH

    process_general_query --> process_response
    process_additional_query --> process_response
    rag_subgraph_wrapper --> process_response
    process_text2sql_query --> process_response
    process_image_query --> process_response
    process_file_query --> process_response

    process_response["📤 process_response<br/><i>统一回复处理</i>"]:::process

    process_response -->|"有检索文档"| check_hallucinations
    process_response -->|"无检索文档"| END_NODE

    check_hallucinations["🔍 check_hallucinations<br/><i>幻觉检查</i>"]:::process
    check_hallucinations -->|"无幻觉"| END_NODE
    check_hallucinations -->|"有幻觉 & 重试<3 & graphrag"| rag_subgraph_wrapper
    check_hallucinations -->|"有幻觉 & 重试<3 & text2sql"| process_text2sql_query
    check_hallucinations -->|"重试≥3"| hallucination_reject

    hallucination_reject["🚫 hallucination_reject<br/><i>拒绝式回答</i>"]:::process
    hallucination_reject --> END_NODE
```

## 节点说明

### 主图节点

| 节点 | 源文件 | 说明 |
|---|---|---|
| `analyze_and_route_query` | `lg_builder.py` | LLM 意图识别，输出 `Router` 结构体，6 种路由类型 |
| `process_general_query` | `lg_builder.py` | 纯 LLM 闲聊回复，不调用外部数据源 |
| `process_additional_query` | `lg_builder.py` | 用户意图模糊时追问补充信息 |
| `rag_subgraph` | `rag_sub_graph/rag_builder.py` | GraphRAG 子图，Neo4j 图谱查询 |
| `process_text2sql_query` | `lg_builder.py` | Text2SQL 子图入口，MySQL 统计查询 |
| `process_image_query` | `lg_builder.py` | 图片分析（视觉模型）或图片生成 |
| `process_file_query` | `lg_builder.py` | 文件上传处理 |
| `process_response` | `lg_builder.py` | 统一回复后处理（answer 提取） |
| `check_hallucinations` | `lg_builder.py` | 幻觉检查：有幻觉且重试<3次 → 回到业务节点重新生成；重试≥3 → 拒绝式回答；无幻觉 → END |
| `hallucination_reject` | `lg_builder.py` | 重试耗尽后生成拒绝式回复，避免输出不可靠内容 |

### RAG 子图节点

| 节点 | 说明 |
|---|---|
| `guardrails` | 范围检查：问题是否属于菜谱领域 |
| `planner` | 查询规划：分析问题需要什么类型的图谱查询 |
| `tool_selection` | 工具选择：动态 Cypher / 预定义 Cypher / GraphRAG 多跳 |
| `cypher_query` | LLM 生成 Cypher 查询并执行 |
| `predefined_cypher` | 匹配预定义 Cypher 模板执行 |
| `graphrag_query` | 图谱多跳遍历 + 知识子图提取 |
| `summarize` | 对查询结果进行摘要压缩 |
| `final_answer` | 生成最终用户回答 |

### Text2SQL 子图节点

| 节点 | 说明 |
|---|---|
| `guardrails` | 范围检查：问题是否适合 SQL 查询 |
| `query_analysis` | 分析用户需求，提取查询意图 |
| `sql_generation` | LLM 生成 SQL 语句 |
| `sql_validation` | 验证 SQL 语法和安全性 |
| `sql_execution` | 执行 SQL 并获取结果 |
| `format_answer` | 将查询结果格式化为用户友好的回答 |
