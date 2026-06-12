from langchain_core.prompts import ChatPromptTemplate


def create_text2cypher_generation_prompt_template() -> ChatPromptTemplate:
    """创建 Text2Cypher 生成 Prompt 模板。"""
    return ChatPromptTemplate.from_messages(
        [
            (
                "system",
                (
                    "根据输入的问题，将其转换为Cypher查询语句。不要添加任何前言。"
                    "不要在响应中包含任何反引号或其他标记。注意：只返回Cypher语句！"
                ),
            ),
            (
                "human",
                (
                    """你是一位Neo4j专家。根据输入的问题，创建一个语法正确的Cypher查询语句。
                        不要在响应中包含任何反引号或其他标记。只使用MATCH或WITH子句开始查询。只返回Cypher语句！

                        以下是数据库模式信息：
                        {schema}

                        下面是一些问题和对应Cypher查询的示例：

                        {fewshot_examples}

                        用户输入: {question}
                        Cypher查询:"""
                ),
            ),
        ]
    )


def create_text2cypher_correction_prompt_template() -> ChatPromptTemplate:
    """创建 Text2Cypher 纠正 Prompt 模板。"""
    return ChatPromptTemplate.from_messages(
        [
            (
                "system",
                (
                    "你是一位Cypher专家，正在审查一位初级开发者编写的查询语句。"
                    "你需要根据提供的错误信息纠正Cypher语句。不要添加任何前言。"
                    "不要在响应中包含任何反引号或其他标记。只返回Cypher语句！"
                ),
            ),
            (
                "human",
                (
                    """检查以下Cypher语句中的语法或语义错误，并返回纠正后的语句。

                    数据库模式：
                    {schema}

                    注意：不要在响应中包含任何解释或道歉。
                    不要在响应中包含任何反引号或其他标记。
                    只返回Cypher语句！

                    不要回答任何与构建Cypher语句无关的问题。

                    用户问题：
                    {question}

                    当前Cypher语句：
                    {cypher}

                    错误信息：
                    {errors}

                    纠正后的Cypher语句：
                    """
                                ),
                            ),
                        ]
                    )


def create_text2cypher_validation_prompt_template() -> ChatPromptTemplate:
    """创建 Text2Cypher 验证 Prompt 模板。"""

    validate_cypher_system = """你是一位Cypher专家，正在审查一位初级开发者编写的查询语句。"""

    validate_cypher_user = """你必须检查以下内容：
    * Cypher语句中是否存在语法错误？
    * Cypher语句中是否存在缺失或未定义的变量？
    * Cypher语句是否包含足够的信息来回答用户问题？
    * 确保所有节点、关系和属性都存在于提供的数据库模式中。

    良好的错误提示示例：
    * 标签 (:Foo) 不存在，你是否指的是 (:Bar)？
    * 标签 Foo 上不存在属性 bar，你是否指的是 baz？
    * 关系 FOO 不存在，你是否指的是 FOO_BAR？

    数据库模式：
    {schema}

    用户问题：
    {question}

    当前Cypher语句：
    {cypher}

    请仔细检查，不要遗漏任何错误！"""

    return ChatPromptTemplate.from_messages(
        [
            (
                "system",
                validate_cypher_system,
            ),
            (
                "human",
                validate_cypher_user,
            ),
        ]
    )
