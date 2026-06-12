"""
菜谱场景 Cypher 示例检索器

基于关键词意图分类，为 Text2Cypher LLM 提供与用户问题最相关的 few-shot Cypher 示例。
所有查询基于实际图 schema：:Concept 统一标签 + 数字字符串关系类型。
"""

import re
from typing import Dict, List

from gustobot.infrastructure.core.logger import get_logger

logger = get_logger(service="recipe_cypher_retriever")


# 按查询意图分类的示例库
# 关系类型: 801000001=has_ingredient, 801000003=has_step,
#          801000004=belongs_to_category, 801000005=has_difficulty

_EXAMPLES_BY_TYPE: Dict[str, List[Dict[str, str]]] = {
    "ingredient_query": [
        {
            "question": "皮蛋豆腐需要哪些食材？",
            "cypher": "MATCH (r:Concept {conceptType: 'Recipe', name: '皮蛋豆腐'})-[:`801000001`]->(i:Concept {conceptType: 'Ingredient'}) RETURN i.name AS 食材, i.amount AS 用量, i.unit AS 单位, i.isMain AS 是否主料 ORDER BY i.isMain DESC",
        },
        {
            "question": "红烧肉的主料有哪些？",
            "cypher": "MATCH (r:Concept {conceptType: 'Recipe', name: '红烧肉'})-[:`801000001`]->(i:Concept {conceptType: 'Ingredient', isMain: true}) RETURN i.name AS 主料, i.amount AS 用量, i.unit AS 单位",
        },
        {
            "question": "红烧肉需要多少五花肉？",
            "cypher": "MATCH (r:Concept {conceptType: 'Recipe', name: '红烧肉'})-[rel:`801000001`]->(i:Concept {conceptType: 'Ingredient'}) WHERE i.name CONTAINS '五花肉' RETURN i.name AS 食材, rel.amount AS 用量, rel.unit AS 单位",
        },
    ],
    "step_query": [
        {
            "question": "番茄炒蛋的做法步骤是什么？",
            "cypher": "MATCH (r:Concept {conceptType: 'Recipe', name: '番茄炒蛋'})-[:`801000003`]->(s:Concept {conceptType: 'CookingStep'}) RETURN s.stepNumber AS 步骤序号, s.description AS 步骤说明 ORDER BY s.stepNumber",
        },
        {
            "question": "红烧肉怎么做？",
            "cypher": "MATCH (r:Concept {conceptType: 'Recipe', name: '红烧肉'})-[:`801000003`]->(s:Concept {conceptType: 'CookingStep'}) RETURN s.stepNumber AS 步骤序号, s.description AS 步骤说明, s.methods AS 方法 ORDER BY s.stepNumber",
        },
    ],
    "category_query": [
        {
            "question": "有哪些素菜菜谱？",
            "cypher": "MATCH (r:Concept {conceptType: 'Recipe'})-[:`801000004`]->(c:Concept {conceptType: 'RecipeCategory', name: '素菜'}) RETURN r.name AS 菜名, r.cookTime AS 烹饪时间, r.difficulty AS 难度",
        },
        {
            "question": "汤类菜谱有哪些？",
            "cypher": "MATCH (r:Concept {conceptType: 'Recipe'})-[:`801000004`]->(c:Concept {conceptType: 'RecipeCategory', name: '汤类'}) RETURN r.name AS 菜名, r.prepTime AS 准备时间, r.cookTime AS 烹饪时间",
        },
    ],
    "difficulty_query": [
        {
            "question": "难度为一星的菜谱有哪些？",
            "cypher": "MATCH (r:Concept {conceptType: 'Recipe'})-[:`801000005`]->(d:Concept {conceptType: 'DifficultyLevel', name: '一星'}) RETURN r.name AS 菜名, r.category AS 分类",
        },
        {
            "question": "最简单的菜谱是哪些？",
            "cypher": "MATCH (r:Concept {conceptType: 'Recipe'})-[:`801000005`]->(d:Concept {conceptType: 'DifficultyLevel'}) WHERE d.name IN ['一星', '二星'] RETURN r.name AS 菜名, d.name AS 难度等级 ORDER BY d.name",
        },
    ],
    "reverse_ingredient": [
        {
            "question": "哪些菜谱用到了豆腐？",
            "cypher": "MATCH (r:Concept {conceptType: 'Recipe'})-[:`801000001`]->(i:Concept {conceptType: 'Ingredient'}) WHERE i.name CONTAINS '豆腐' RETURN r.name AS 菜名, i.name AS 食材, i.amount AS 用量, i.unit AS 单位",
        },
        {
            "question": "五花肉可以做什么菜？",
            "cypher": "MATCH (r:Concept {conceptType: 'Recipe'})-[:`801000001`]->(i:Concept {conceptType: 'Ingredient'}) WHERE i.name CONTAINS '五花肉' RETURN DISTINCT r.name AS 菜名, r.category AS 分类",
        },
    ],
    "statistics": [
        {
            "question": "数据库中一共有多少道菜谱？",
            "cypher": "MATCH (r:Concept {conceptType: 'Recipe'}) RETURN count(r) AS 菜谱总数",
        },
        {
            "question": "每个分类有多少道菜？",
            "cypher": "MATCH (r:Concept {conceptType: 'Recipe'})-[:`801000004`]->(c:Concept {conceptType: 'RecipeCategory'}) RETURN c.name AS 分类, count(r) AS 菜谱数量 ORDER BY 菜谱数量 DESC",
        },
        {
            "question": "使用最多的食材是什么？",
            "cypher": "MATCH (r:Concept {conceptType: 'Recipe'})-[:`801000001`]->(i:Concept {conceptType: 'Ingredient'}) WITH i.name AS 食材名, count(DISTINCT r) AS 使用次数 RETURN 食材名, 使用次数 ORDER BY 使用次数 DESC LIMIT 10",
        },
    ],
    "recipe_property": [
        {
            "question": "红烧肉的烹饪时间是多少？",
            "cypher": "MATCH (r:Concept {conceptType: 'Recipe', name: '红烧肉'}) RETURN r.prepTime AS 准备时间, r.cookTime AS 烹饪时间, r.servings AS 份量",
        },
        {
            "question": "皮蛋豆腐有什么小贴士？",
            "cypher": "MATCH (r:Concept {conceptType: 'Recipe', name: '皮蛋豆腐'}) RETURN r.tags AS 小贴士",
        },
    ],
}

# 意图关键词映射
_INTENT_KEYWORDS: Dict[str, List[str]] = {
    "ingredient_query": ["食材", "材料", "配料", "用料", "需要什么", "用什么", "主料", "辅料", "调料", "用量", "多少克", "多少个"],
    "step_query": ["做法", "步骤", "怎么做", "怎么烧", "怎么炒", "怎么煮", "怎么炖", "怎么蒸", "烹饪方法", "制作方法", "操作"],
    "category_query": ["素菜", "荤菜", "水产", "早餐", "主食", "汤类", "甜品", "饮料", "分类", "类型", "哪一类"],
    "difficulty_query": ["难度", "简单", "容易", "复杂", "一星", "二星", "三星", "四星", "五星", "入门"],
    "reverse_ingredient": ["可以做什么", "能做什么", "做哪些菜", "有什么菜", "什么菜用了", "哪些菜用到"],
    "statistics": ["多少", "统计", "数量", "最多", "最少", "排名", "排行", "一共", "总共", "平均"],
    "recipe_property": ["时间", "耗时", "多久", "几分钟", "份量", "几人份", "贴士", "技巧", "诀窍", "注意"],
}


def _classify_intent(query: str) -> List[str]:
    """
    基于关键词匹配对用户问题进行意图分类。
    返回按匹配度排序的意图类型列表。
    """
    scores: Dict[str, int] = {}
    for intent, keywords in _INTENT_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in query)
        if score > 0:
            scores[intent] = score
    # 按匹配度降序排列
    sorted_intents = sorted(scores, key=lambda k: scores[k], reverse=True)
    return sorted_intents


def _compute_relevance(example: Dict[str, str], query: str) -> float:
    """计算单个示例与查询的相关度分数。"""
    query_chars = set(query)
    example_chars = set(example["question"])
    overlap = len(query_chars & example_chars)

    # 关键词匹配加权
    bonus = 0
    important_terms = ["食材", "步骤", "做法", "分类", "难度", "用量", "统计"]
    for term in important_terms:
        if term in query and term in example["question"]:
            bonus += 3
    return overlap + bonus


class RecipeCypherRetriever:
    """
    菜谱场景 Cypher 示例检索器。

    基于关键词意图分类 + 相关性排序，为 Text2Cypher LLM 生成 few-shot 示例。
    无外部依赖，所有示例基于实际 Neo4j 图 schema。
    """

    def get_examples(self, query: str, k: int = 5) -> str:
        """
        根据用户查询返回最相关的 Cypher 示例。

        Parameters
        ----------
        query : str
            用户的自然语言查询
        k : int, optional
            返回的示例数量，默认 5

        Returns
        -------
        str
            格式化的示例字符串，每个示例包含问题和对应的 Cypher 查询
        """
        # 1. 意图分类
        intents = _classify_intent(query)
        logger.debug(f"问题意图分类: {intents}")

        # 2. 按意图优先级收集候选示例
        candidates: List[Dict[str, str]] = []
        seen: set = set()  # 去重

        for intent in intents:
            for ex in _EXAMPLES_BY_TYPE.get(intent, []):
                key = ex["cypher"]
                if key not in seen:
                    candidates.append(ex)
                    seen.add(key)

        # 3. 补充其他类型的示例（确保多样性）
        for intent, examples in _EXAMPLES_BY_TYPE.items():
            for ex in examples:
                key = ex["cypher"]
                if key not in seen:
                    candidates.append(ex)
                    seen.add(key)

        # 4. 相关性排序 + 截取
        scored = sorted(candidates, key=lambda ex: _compute_relevance(ex, query), reverse=True)
        final = scored[:k]

        # 5. 格式化输出
        return "\n\n".join(
            f"问题: {ex['question']}\nCypher: {ex['cypher']}" for ex in final
        )
