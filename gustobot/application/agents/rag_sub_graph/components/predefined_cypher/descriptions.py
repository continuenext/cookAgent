"""预定义菜谱 Cypher 查询的描述信息.

该模块为 recipe_kg 图谱准备的固定查询提供语义描述, 用于帮助 LLM 根据用户提问快速匹配合适的查询。
描述应覆盖查询意图、适用场景以及可能的自然语言问法提示。

图谱 Schema 说明
- 所有节点统一标签 :Concept, 通过 conceptType 属性区分:
  Recipe / Ingredient / CookingStep / RecipeCategory / DifficultyLevel
- 关系类型(数字字符串, 由 apoc.create.relationship 创建):
  801000001 = has_ingredient  (Recipe -> Ingredient)  关系属性: amount, unit
  801000003 = has_step        (Recipe -> CookingStep)  关系属性: stepOrder
  801000004 = belongs_to_category (Recipe -> RecipeCategory)
  801000005 = has_difficulty  (Recipe -> DifficultyLevel)
- Recipe 属性: name, category, difficulty, prepTime, cookTime, servings, tags
- Ingredient 属性: name, category, amount, unit, isMain
- CookingStep 属性: name, description, stepNumber, methods, tools, timeEstimate
"""

# 空结果占位
NO_CYPHER_RESULTS: list[str] = ["未检索到相关数据"]

# 1. 菜品属性查询
DISH_PROPERTY_QUERY_DESCRIPTIONS = {
    "dish_cook_time": "查询某道菜的准备和烹饪耗时, 适用于用户询问这道菜需要多久能完成。",
    "dish_tags": "查询菜品的备注标签/小贴士, 适用于用户想了解烹饪技巧或注意事项。",
    "dish_category": "查询菜品所属的分类(素菜/荤菜/水产等), 适用于用户了解菜的类型。",
    "dish_difficulty": "查询菜品难度等级(一星到五星), 适用于用户想知道做这道菜的难度。",
    "dish_complete_info": "汇总菜品的耗时、分类、难度、份量与备注等综合信息, 适用于需要一次性掌握菜谱全貌的场景。",
}

# 2. 条件筛选查询
FILTER_QUERY_DESCRIPTIONS = {
    "dishes_by_category": "按菜品分类筛选菜谱(素菜/荤菜/水产/早餐/主食/汤类/甜品/饮料), 适用于用户想按类型查找菜。",
    "dishes_by_difficulty": "按难度等级筛选菜品(一星到五星), 适用于用户想找简单或有挑战的菜。",
    "dishes_by_category_and_difficulty": "同时按分类和难度筛选菜品, 适用于用户提出多条件组合需求。",
}

# 3. 食材关系查询
INGREDIENT_RELATION_QUERY_DESCRIPTIONS = {
    "dishes_by_main_ingredient": "根据主食材反查菜品, 适用于用户想知道某种主料能做哪些菜。",
    "dishes_by_aux_ingredient": "根据辅料/调味料反查菜品, 适用于用户想利用某个辅料安排菜谱。",
    "ingredients_of_dish": "列出菜品所有主辅食材及用量, 适用于用户想完整掌握需要准备的材料。",
    "main_ingredients_of_dish": "仅查询菜品的主食材和对应用量, 适用于强调菜品主体食材的场景。",
    "aux_ingredients_of_dish": "仅查询菜品的辅料/调味料及用量, 适用于用户关注配料或调味细节。",
}

# 4. 食材用量查询
INGREDIENT_AMOUNT_QUERY_DESCRIPTIONS = {
    "ingredient_amount_in_dish": "查询某道菜中指定食材的用量(主辅料均可), 适用于确认单一食材份量。",
    "main_ingredient_amount": "查询菜品中某个主食材的用量, 适用于主料精确配比的需求。",
    "aux_ingredient_amount": "查询菜品中某个辅料的用量, 适用于调味料或辅料的定量问题。",
}

# 5. 烹饪步骤查询
COOKING_STEP_QUERY_DESCRIPTIONS = {
    "cooking_steps": "按顺序列出菜品的全部烹饪步骤及其使用的操作方法和工具, 适用于用户想逐步学习做法。",
    "step_by_order": "查询菜品在特定步骤号对应的烹饪说明, 适用于用户追问某一步的详细说明。",
}

# 6. 统计分析查询
STATS_QUERY_DESCRIPTIONS = {
    "ingredient_usage_count": "统计某个食材在多少道菜中出现, 适用于评估食材用途广度。",
    "dishes_count_by_category": "统计各菜品分类下的菜品数量, 适用于查看菜谱类型分布。",
    "dishes_count_by_difficulty": "统计各难度等级下的菜品数量, 适用于了解难度分布。",
    "most_used_ingredients": "统计使用最多的食材及出现频次, 适用于了解常见食材。",
}

# 7. 推荐/相似菜品查询
RECOMMENDATION_QUERY_DESCRIPTIONS = {
    "dishes_with_ingredient": "根据指定食材推荐菜品及基本信息, 适用于手头有某食材能做什么类问题。",
    "similar_dishes_by_category": "查找与目标菜同分类的其他菜, 适用于想找同类菜谱的用户。",
    "similar_dishes_by_ingredients": "基于共享食材寻找与目标菜相似的菜, 适用于想找类似菜品的用户。",
}

# 合并所有查询描述
QUERY_DESCRIPTIONS = {}
QUERY_DESCRIPTIONS.update(DISH_PROPERTY_QUERY_DESCRIPTIONS)
QUERY_DESCRIPTIONS.update(FILTER_QUERY_DESCRIPTIONS)
QUERY_DESCRIPTIONS.update(INGREDIENT_RELATION_QUERY_DESCRIPTIONS)
QUERY_DESCRIPTIONS.update(INGREDIENT_AMOUNT_QUERY_DESCRIPTIONS)
QUERY_DESCRIPTIONS.update(COOKING_STEP_QUERY_DESCRIPTIONS)
QUERY_DESCRIPTIONS.update(STATS_QUERY_DESCRIPTIONS)
QUERY_DESCRIPTIONS.update(RECOMMENDATION_QUERY_DESCRIPTIONS)
