"""
预定义菜谱 Cypher 查询字典

基于 recipe_kg 图谱的实际 Schema:
- 节点: 统一 :Concept 标签, conceptType 区分类型
  Recipe / Ingredient / CookingStep / RecipeCategory / DifficultyLevel
- 关系: 数字字符串 (由 apoc.create.relationship 创建)
  `801000001` = has_ingredient  (Recipe -> Ingredient, 属性: amount, unit)
  `801000003` = has_step        (Recipe -> CookingStep, 属性: stepOrder)
  `801000004` = belongs_to_category (Recipe -> RecipeCategory)
  `801000005` = has_difficulty  (Recipe -> DifficultyLevel)
"""
from typing import Dict

predefined_cypher_dict: Dict[str, str] = {
    # ==================== 1. 菜品属性查询 ====================

    "dish_cook_time": """
MATCH (d:Concept {conceptType: 'Recipe', name: $dish_name})
RETURN d.name AS 菜名, d.prepTime AS 准备时间, d.cookTime AS 烹饪时间
""",

    "dish_tags": """
MATCH (d:Concept {conceptType: 'Recipe', name: $dish_name})
RETURN d.name AS 菜名, d.tags AS 小贴士
""",

    "dish_category": """
MATCH (d:Concept {conceptType: 'Recipe', name: $dish_name})-[:`801000004`]->(c:Concept {conceptType: 'RecipeCategory'})
RETURN d.name AS 菜名, c.name AS 分类
""",

    "dish_difficulty": """
MATCH (d:Concept {conceptType: 'Recipe', name: $dish_name})-[:`801000005`]->(dl:Concept {conceptType: 'DifficultyLevel'})
RETURN d.name AS 菜名, dl.name AS 难度等级
""",

    "dish_complete_info": """
MATCH (d:Concept {conceptType: 'Recipe', name: $dish_name})
OPTIONAL MATCH (d)-[:`801000004`]->(c:Concept {conceptType: 'RecipeCategory'})
OPTIONAL MATCH (d)-[:`801000005`]->(dl:Concept {conceptType: 'DifficultyLevel'})
RETURN d.name AS 菜名,
       d.prepTime AS 准备时间,
       d.cookTime AS 烹饪时间,
       d.servings AS 份量,
       d.tags AS 小贴士,
       c.name AS 分类,
       dl.name AS 难度等级
""",

    # ==================== 2. 条件筛选查询 ====================

    "dishes_by_category": """
MATCH (d:Concept {conceptType: 'Recipe'})-[:`801000004`]->(c:Concept {conceptType: 'RecipeCategory', name: $category_name})
RETURN d.name AS 菜名 LIMIT 15
""",

    "dishes_by_difficulty": """
MATCH (d:Concept {conceptType: 'Recipe'})-[:`801000005`]->(dl:Concept {conceptType: 'DifficultyLevel', name: $difficulty_name})
RETURN d.name AS 菜名 LIMIT 15
""",

    "dishes_by_category_and_difficulty": """
MATCH (d:Concept {conceptType: 'Recipe'})-[:`801000004`]->(c:Concept {conceptType: 'RecipeCategory', name: $category_name})
WHERE EXISTS {
    MATCH (d)-[:`801000005`]->(dl:Concept {conceptType: 'DifficultyLevel', name: $difficulty_name})
}
RETURN d.name AS 菜名 LIMIT 15
""",

    # ==================== 3. 食材关系查询 ====================

    "dishes_by_main_ingredient": """
MATCH (d:Concept {conceptType: 'Recipe'})-[r:`801000001`]->(i:Concept {conceptType: 'Ingredient', name: $ingredient_name})
WHERE i.isMain = true
RETURN d.name AS 菜名 LIMIT 15
""",

    "dishes_by_aux_ingredient": """
MATCH (d:Concept {conceptType: 'Recipe'})-[r:`801000001`]->(i:Concept {conceptType: 'Ingredient', name: $ingredient_name})
WHERE i.isMain = false
RETURN d.name AS 菜名 LIMIT 15
""",

    "ingredients_of_dish": """
MATCH (d:Concept {conceptType: 'Recipe', name: $dish_name})-[r:`801000001`]->(i:Concept {conceptType: 'Ingredient'})
RETURN i.name AS 食材,
       CASE WHEN i.isMain = true THEN '主料' ELSE '辅料' END AS 类型,
       r.amount AS 用量, r.unit AS 单位
ORDER BY i.isMain DESC, i.name
""",

    "main_ingredients_of_dish": """
MATCH (d:Concept {conceptType: 'Recipe', name: $dish_name})-[r:`801000001`]->(i:Concept {conceptType: 'Ingredient'})
WHERE i.isMain = true
RETURN i.name AS 主食材, r.amount AS 用量, r.unit AS 单位
""",

    "aux_ingredients_of_dish": """
MATCH (d:Concept {conceptType: 'Recipe', name: $dish_name})-[r:`801000001`]->(i:Concept {conceptType: 'Ingredient'})
WHERE i.isMain = false
RETURN i.name AS 辅料, r.amount AS 用量, r.unit AS 单位
""",

    # ==================== 4. 食材用量查询 ====================

    "ingredient_amount_in_dish": """
MATCH (d:Concept {conceptType: 'Recipe', name: $dish_name})-[r:`801000001`]->(i:Concept {conceptType: 'Ingredient', name: $ingredient_name})
RETURN r.amount AS 用量, r.unit AS 单位
""",

    "main_ingredient_amount": """
MATCH (d:Concept {conceptType: 'Recipe', name: $dish_name})-[r:`801000001`]->(i:Concept {conceptType: 'Ingredient', name: $ingredient_name})
WHERE i.isMain = true
RETURN r.amount AS 用量, r.unit AS 单位
""",

    "aux_ingredient_amount": """
MATCH (d:Concept {conceptType: 'Recipe', name: $dish_name})-[r:`801000001`]->(i:Concept {conceptType: 'Ingredient', name: $ingredient_name})
WHERE i.isMain = false
RETURN r.amount AS 用量, r.unit AS 单位
""",

    # ==================== 5. 烹饪步骤查询 ====================

    "cooking_steps": """
MATCH (d:Concept {conceptType: 'Recipe', name: $dish_name})-[r:`801000003`]->(s:Concept {conceptType: 'CookingStep'})
RETURN s.stepNumber AS 步骤序号, s.description AS 步骤说明, s.methods AS 操作方法, s.tools AS 工具
ORDER BY r.stepOrder
""",

    "step_by_order": """
MATCH (d:Concept {conceptType: 'Recipe', name: $dish_name})-[r:`801000003`]->(s:Concept {conceptType: 'CookingStep'})
WHERE s.stepNumber = $step_order
RETURN s.stepNumber AS 步骤序号, s.description AS 步骤说明, s.methods AS 操作方法, s.tools AS 工具
""",

    # ==================== 6. 统计分析查询 ====================

    "ingredient_usage_count": """
MATCH (d:Concept {conceptType: 'Recipe'})-[:`801000001`]->(i:Concept {conceptType: 'Ingredient', name: $ingredient_name})
RETURN count(DISTINCT d) AS 菜品数量
""",

    "dishes_count_by_category": """
MATCH (d:Concept {conceptType: 'Recipe'})-[:`801000004`]->(c:Concept {conceptType: 'RecipeCategory'})
WITH c.name AS 菜品分类, count(d) AS 菜品数量
RETURN 菜品分类, 菜品数量
ORDER BY 菜品数量 DESC
""",

    "dishes_count_by_difficulty": """
MATCH (d:Concept {conceptType: 'Recipe'})-[:`801000005`]->(dl:Concept {conceptType: 'DifficultyLevel'})
WITH dl.name AS 难度等级, count(d) AS 菜品数量
RETURN 难度等级, 菜品数量
ORDER BY 菜品数量 DESC
""",

    "most_used_ingredients": """
MATCH (d:Concept {conceptType: 'Recipe'})-[:`801000001`]->(i:Concept {conceptType: 'Ingredient'})
WITH i.name AS 食材, count(DISTINCT d) AS 出现次数
RETURN 食材, 出现次数
ORDER BY 出现次数 DESC LIMIT 10
""",

    # ==================== 7. 推荐/相似菜品查询 ====================

    "dishes_with_ingredient": """
MATCH (d:Concept {conceptType: 'Recipe'})-[r:`801000001`]->(i:Concept {conceptType: 'Ingredient', name: $ingredient_name})
OPTIONAL MATCH (d)-[:`801000004`]->(c:Concept {conceptType: 'RecipeCategory'})
RETURN d.name AS 菜名, d.cookTime AS 烹饪时间, c.name AS 分类
LIMIT 10
""",

    "similar_dishes_by_category": """
MATCH (d1:Concept {conceptType: 'Recipe', name: $dish_name})-[:`801000004`]->(c:Concept {conceptType: 'RecipeCategory'})<-[:`801000004`]-(d2:Concept {conceptType: 'Recipe'})
WHERE d1 <> d2
RETURN d2.name AS 相似菜品, c.name AS 共同分类
LIMIT 10
""",

    "similar_dishes_by_ingredients": """
MATCH (d1:Concept {conceptType: 'Recipe', name: $dish_name})-[:`801000001`]->(i:Concept {conceptType: 'Ingredient'})<-[:`801000001`]-(d2:Concept {conceptType: 'Recipe'})
WHERE d1 <> d2
WITH d2, count(DISTINCT i) AS 共同食材数
RETURN d2.name AS 相似菜品, 共同食材数
ORDER BY 共同食材数 DESC LIMIT 10
""",
}
