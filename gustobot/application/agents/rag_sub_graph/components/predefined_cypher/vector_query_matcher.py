import json
import re
from typing import Any, Dict, List, Optional

import numpy as np
from langchain_core.prompts import ChatPromptTemplate
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


class VectorQueryMatcher:
    """使用 TF-IDF 向量化实现的查询匹配器。"""

    def __init__(
        self,
        predefined_cypher_dict: Dict[str, str],
        query_descriptions: Dict[str, str],
        similarity_threshold: float = 0.5,
    ) -> None:
        self.predefined_cypher_dict = predefined_cypher_dict # 预定义的 Cypher 查询模板字典，键为查询名称，值为 Cypher 语句。
        self.query_descriptions = query_descriptions # 查询模板的自然语言描述字典，用于 TF-IDF 向量化比对。
        self.similarity_threshold = similarity_threshold # 向量匹配的余弦相似度最低阈值，低于此值的匹配结果将被丢弃。默认值为 0.5。

        self._vectorizer = TfidfVectorizer() # 将查询描述文本转化为 TF-IDF 向量
        self._query_vectors = self._compute_query_vectors() # 键为查询名称，值为经过转换的 TF-IDF NumPy 向量数组。

    def _compute_query_vectors(self) -> Dict[str, np.ndarray]:
        """
        功能:
            将所有预定义的查询描述文本转化为 TF-IDF 稀疏向量，构建用于比对的基础特征空间。
        返回:
            Dict[str, np.ndarray]: 一个字典，键为查询名称，值为经过转换的 TF-IDF NumPy 向量数组。
        """
        keys: List[str] = []
        corpus: List[str] = []
        for query_name in self.predefined_cypher_dict:
            description = self.query_descriptions.get(query_name, "")
            keys.append(query_name)
            corpus.append(f"{query_name} {description}".strip())

        if not corpus:
            return {}

        matrix = self._vectorizer.fit_transform(corpus).toarray()
        return {
            key: np.asarray(vector, dtype=np.float32) for key, vector in zip(keys, matrix)
        }

    def _embed(self, texts: List[str]) -> np.ndarray:
        """
        功能:
            使用已训练好的 TF-IDF 向量化器，将新的目标文本（如用户提问）转化为相同维度的向量。
        参数:
            texts (List[str]): 需要进行向量化的文本列表。
        返回:
            np.ndarray: 转化后的 NumPy 向量数组。如果输入为空，则返回零矩阵。
        """
        if not texts:
            return np.zeros((0, len(self._vectorizer.get_feature_names_out())))
        return self._vectorizer.transform(texts).toarray()

    def match_query(self, user_question: str, top_k: int = 3) -> List[Dict[str, Any]]:
        """
        功能:
            计算用户提问与所有预定义模板的余弦相似度，筛选并返回最匹配的图谱查询模板。
        参数:
            user_question (str): 用户的自然语言提问。
            top_k (int, 可选): 返回相似度最高的前 K 个匹配结果。默认值为 3。
        返回:
            List[Dict[str, Any]]: 匹配结果列表。每个字典包含匹配成功的 "query_name" (查询名称), 
            "similarity" (相似度分数) 和 "cypher" (对应的 Cypher 模板)。
        """
        if not user_question or not self._query_vectors:
            return []

        question_vector = self._embed([user_question])
        if question_vector.size == 0:
            return []
        question_vector = question_vector[0]

        similarities: List[tuple[str, float]] = []
        for query_name, vector in self._query_vectors.items():
            score = cosine_similarity([question_vector], [vector])[0][0]
            similarities.append((query_name, float(score)))

        similarities.sort(key=lambda item: item[1], reverse=True)

        results: List[Dict[str, Any]] = []
        for query_name, score in similarities[:top_k]:
            if score >= self.similarity_threshold:
                results.append(
                    {
                        "query_name": query_name,
                        "similarity": score,
                        "cypher": self.predefined_cypher_dict[query_name],
                    }
                )
        return results

    def extract_parameters(
        self, user_question: str, query_name: str, llm: Any | None = None
    ) -> Dict[str, str]:
        """
        功能:
            根据匹配到的图谱模板，解析其中所需的参数变量（形如 $param），
            优先调用大语言模型进行提取，若无大模型或提取失败，则回退至正则表达式规则提取。
        参数:
            user_question (str): 用户的自然语言提问。
            query_name (str): 命中匹配的查询模板名称。
            llm (Any | None, 可选): 提供参数提取能力的大语言模型实例。允许为 None。
        返回:
            Dict[str, str]: 提取出的参数字典，键为参数名（不含$号），值为提取到的具体实体字符串。
        """
        if query_name not in self.predefined_cypher_dict:
            return {}

        cypher_template = self.predefined_cypher_dict[query_name]
        param_names = re.findall(r"\$(\w+)", cypher_template)
        if not param_names:
            return {}

        if llm is not None:
            llm_params = self._extract_parameters_with_llm(
                user_question, param_names, query_name, llm
            )
            if llm_params:
                return llm_params

        return self._extract_parameters_with_rules(user_question, param_names)

    @staticmethod
    def _extract_parameters_with_rules(
        user_question: str, param_names: List[str]
    ) -> Dict[str, str]:
        """
        功能:
            构建 ChatPrompt 引导 LLM 阅读用户提问，并精准提取图谱所需的查询参数。
        参数:
            user_question (str): 用户的自然语言提问。
            param_names (List[str]): 当前模板需要提取的参数名列表。
            query_name (str): 查询类型名称，用于给大模型提供上下文提示。
            llm (Any): 用于生成提取结果的大语言模型实例。
        返回:
            Dict[str, str]: 大模型提取并解析成功的 JSON 参数字典。若解析失败则返回空字典。
        """
        params: Dict[str, str] = {}
        for name in param_names:
            if name == "dish_name":
                match = re.search(r"(?:菜|菜品|做|叫)?([^\s，。,]+)", user_question)
                if match:
                    params[name] = match.group(1)
            elif name == "ingredient_name":
                match = re.search(r"(?:食材|材料|用|加)([^\s，。,]+)", user_question)
                if match:
                    params[name] = match.group(1)
            elif name == "flavor_name":
                match = re.search(r"(麻辣|清淡|酸辣|咸鲜|甜味|香辣)", user_question)
                if match:
                    params[name] = match.group(1)
            elif name == "category_name":
                category_match = re.search(r"(早餐|主食|甜品|汤类|饮料|荤菜|素菜|水产)", user_question)
                if category_match:
                    params[name] = category_match.group(1)
            elif name == "difficulty_name":
                difficulty_match = re.search(r"(一星|二星|三星|四星|五星|简单|中等|困难)", user_question)
                if difficulty_match:
                    value = difficulty_match.group(1)
                    # 简单归一到图谱常见表达
                    if value == "简单":
                        value = "一星"
                    elif value == "中等":
                        value = "三星"
                    elif value == "困难":
                        value = "五星"
                    params[name] = value
            elif name == "step_order":
                step_match = re.search(r"第\s*(\d+)\s*步", user_question)
                if step_match:
                    params[name] = step_match.group(1)
        return params

    @staticmethod
    def _extract_parameters_with_llm(
        user_question: str,
        param_names: List[str],
        query_name: str,
        llm: Any,
    ) -> Dict[str, str]:
        """
        功能:
            使用硬编码的正则表达式规则，从用户提问中提取特定的美食领域参数。
        参数:
            user_question (str): 用户的自然语言提问。
            param_names (List[str]): 当前模板需要提取的参数名列表（如 dish_name, ingredient_name）。
        返回:
            Dict[str, str]: 使用正则提取成功后的参数字典。
        """
        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "你是参数提取助手，从用户问题中提取指定参数，输出 JSON，不要额外说明。",
                ),
                (
                    "human",
                    f"""用户问题: {user_question}
                    查询类型: {query_name}
                    需要提取的参数: {', '.join(param_names)}

                    请以 JSON 返回，形如: {{"参数名": "参数值"}}""",
                ),
            ]
        )

        response = llm.invoke(prompt.format_prompt())
        content = getattr(response, "content", "") or ""
        try:
            match = re.search(r"{.*}", content, re.DOTALL)
            if not match:
                return {}
            parsed = json.loads(match.group(0))
            if isinstance(parsed, dict):
                return {
                    str(k): str(v)
                    for k, v in parsed.items()
                    if v is not None and str(v).strip()
                }
        except Exception as exc:  # pragma: no cover - defensive logging
            print(f"无法解析LLM响应为JSON: {exc}")
        return {}


def create_vector_query_matcher(
    predefined_cypher_dict: Dict[str, str],
    query_descriptions: Optional[Dict[str, str]] = None,
) -> VectorQueryMatcher:
    """
    功能:
        提供一个简化的统一入口来实例化 VectorQueryMatcher。如果在初始化时未提供明确的查询描述，
        将自动回退并使用预定义模板的键名（下划线转为空格）作为描述语料进行构建。
        
    参数:
        predefined_cypher_dict (Dict[str, str]): 预定义的 Cypher 查询模板字典。
        query_descriptions (Optional[Dict[str, str]], 可选): 查询模板的自然语言描述字典。如果未提供，将自动生成默认描述。
    返回:
        VectorQueryMatcher: 初始化完成并经过 TF-IDF 训练的匹配器实例对象。
    """
    descriptions = query_descriptions or {
        key: key.replace("_", " ") for key in predefined_cypher_dict.keys()
    }
    return VectorQueryMatcher(predefined_cypher_dict, descriptions)
