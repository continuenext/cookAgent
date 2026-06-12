# Neo4j 菜谱图谱 Schema 参考

> 基于 `gustobot/data/kg_output/` 中的导入数据分析得出，
> 导入脚本见 `neo4j_import.cypher`。

## 节点

所有节点统一使用 `:Concept` 标签，通过 `conceptType` 属性区分类型。

### Recipe（菜谱）

| 属性 | 类型 | 说明 | 示例 |
|------|------|------|------|
| `nodeId` | String | 唯一标识 | `201000001` |
| `name` | String | 菜名 | `皮蛋豆腐` |
| `preferredTerm` | String | 首选术语 | `皮蛋豆腐` |
| `conceptType` | String | 固定 `Recipe` | `Recipe` |
| `category` | String | 菜品分类（冗余，另有 RecipeCategory 节点） | `素菜` |
| `difficulty` | Integer | 难度数值（1-5） | `1` |
| `prepTime` | String | 准备时间 | `5分钟` |
| `cookTime` | String | 烹饪时间 | `0分钟` |
| `servings` | String | 份量/人数 | `1` |
| `tags` | String | 备注/小贴士 | `豆腐焯水去豆腥味,皮蛋切瓣时刀抹香油防粘` |
| `filePath` | String | 来源 Markdown 文件路径 | `dishes/vegetable_dish/皮蛋豆腐.md` |

### Ingredient（食材）

| 属性 | 类型 | 说明 | 示例 |
|------|------|------|------|
| `nodeId` | String | 唯一标识 | `201000002` |
| `name` | String | 食材名 | `皮蛋` |
| `conceptType` | String | 固定 `Ingredient` | `Ingredient` |
| `category` | String | 食材分类 | `蛋白质` / `调料` / `蔬菜` / `淀粉类` / `其他` |
| `amount` | String | 用量数值（节点级，与关系上的可能重复） | `2` |
| `unit` | String | 用量单位 | `个` / `g` / `ml` / `盒` / `根` |
| `isMain` | Boolean | 是否主食材（`true`=主料, `false`=辅料/调味料） | `true` |

> **注意**: 每个 Recipe 有独立的 Ingredient 节点实例（非共享），因此 `isMain` 是食谱级别的。

### CookingStep（烹饪步骤）

| 属性 | 类型 | 说明 | 示例 |
|------|------|------|------|
| `nodeId` | String | 唯一标识 | `201000012` |
| `name` | String | 步骤名 | `步骤1` |
| `conceptType` | String | 固定 `CookingStep` | `CookingStep` |
| `description` | String | 步骤说明文本 | `先把皮蛋剥壳，切成四瓣。` |
| `stepNumber` | Integer | 步骤序号 | `1` |
| `methods` | String | 本步骤使用的操作方法 | `切` |
| `tools` | String | 本步骤使用的工具 | `刀,案板` |
| `timeEstimate` | String | 预估耗时（可为空） | — |

### RecipeCategory（菜品分类）

| 属性 | 类型 | 说明 |
|------|------|------|
| `nodeId` | String | 唯一标识 |
| `name` | String | 分类名 |
| `conceptType` | String | 固定 `RecipeCategory` |

**已有分类（9 种）**:

| nodeId | 名称 |
|--------|------|
| `710000000` | 素菜 |
| `720000000` | 荤菜 |
| `730000000` | 水产 |
| `740000000` | 早餐 |
| `750000000` | 主食 |
| `760000000` | 汤类 |
| `770000000` | 甜品 |
| `780000000` | 饮料 |
| `790000000` | 调料 |

### DifficultyLevel（难度等级）

| nodeId | 名称 |
|--------|------|
| `610000000` | 一星 |
| `620000000` | 二星 |
| `630000000` | 三星 |
| `640000000` | 四星 |
| `650000000` | 五星 |

### CookingMethod（烹饪方法）⚠️ 仅根节点

> 当前数据中仅有根概念节点 `400000000`（烹饪方法），**无具体方法实例**。
> 烹饪方法信息存储在 CookingStep 节点的 `methods` 属性中。

### CookingTool（烹饪工具）⚠️ 仅根节点

> 当前数据中仅有根概念节点 `500000000`（烹饪工具），**无具体工具实例**。
> 工具信息存储在 CookingStep 节点的 `tools` 属性中。

---

## 关系

关系类型为**数字字符串**，由 `apoc.create.relationship()` 创建。
在 Cypher 查询中使用反引号引用：`` `-[:`801000001`]->` ``

### 关系类型总览

| 类型代码 | 语义名称 | 方向 | 关系属性 | 数据中是否存在 |
|----------|----------|------|----------|:-:|
| `801000001` | has_ingredient | Recipe → Ingredient | `amount`, `unit` | ✅ |
| `801000002` | requires_tool | Recipe → CookingTool | — | ❌ 无数据 |
| `801000003` | has_step | Recipe → CookingStep | `stepOrder` | ✅ |
| `801000004` | belongs_to_category | Recipe → RecipeCategory | — | ✅ |
| `801000005` | has_difficulty | Recipe → DifficultyLevel | — | ✅ |
| `801000006` | uses_method | Recipe → CookingMethod | — | ❌ 无数据 |
| `801000007` | has_amount | — | — | ❌ 未使用 |
| `801000008` | step_follows | — | — | ❌ 未使用 |
| `801000009` | serves_people | — | — | ❌ 未使用 |

### 关系属性详情

#### `801000001`（has_ingredient）

| 属性 | 类型 | 说明 | 示例 |
|------|------|------|------|
| `relationshipId` | String | 关系唯一标识 | `R_000001` |
| `amount` | String | 用量数值 | `2` / `15` / `0.8` |
| `unit` | String | 用量单位 | `个` / `g` / `ml` / `盒` / `块` / `根` / `株` |

#### `801000003`（has_step）

| 属性 | 类型 | 说明 | 示例 |
|------|------|------|------|
| `relationshipId` | String | 关系唯一标识 | `R_000011` |
| `stepOrder` | Integer | 步骤顺序 | `1` / `2` / `3` |

#### `801000004`（belongs_to_category）/ `801000005`（has_difficulty）

仅有 `relationshipId`，无其他属性。

---

## 索引

```cypher
CREATE INDEX concept_id_index IF NOT EXISTS FOR (c:Concept) ON (c.nodeId);
CREATE INDEX concept_name_index IF NOT EXISTS FOR (c:Concept) ON (c.name);
CREATE INDEX concept_category_index IF NOT EXISTS FOR (c:Concept) ON (c.category);
```

---

## 常用查询模式

### 查菜品完整信息
```cypher
MATCH (d:Concept {conceptType: 'Recipe', name: $dish_name})
OPTIONAL MATCH (d)-[:`801000004`]->(c:Concept {conceptType: 'RecipeCategory'})
OPTIONAL MATCH (d)-[:`801000005`]->(dl:Concept {conceptType: 'DifficultyLevel'})
RETURN d.name, d.prepTime, d.cookTime, d.servings, d.tags, c.name, dl.name
```

### 查食材清单
```cypher
MATCH (d:Concept {conceptType: 'Recipe', name: $dish_name})-[r:`801000001`]->(i:Concept {conceptType: 'Ingredient'})
RETURN i.name, i.isMain, r.amount, r.unit
ORDER BY i.isMain DESC
```

### 查烹饪步骤
```cypher
MATCH (d:Concept {conceptType: 'Recipe', name: $dish_name})-[r:`801000003`]->(s:Concept {conceptType: 'CookingStep'})
RETURN s.stepNumber, s.description, s.methods, s.tools
ORDER BY r.stepOrder
```

### 按食材反查菜品
```cypher
MATCH (d:Concept {conceptType: 'Recipe'})-[:`801000001`]->(i:Concept {conceptType: 'Ingredient', name: $ingredient_name})
RETURN d.name
```

### 按分类筛选
```cypher
MATCH (d:Concept {conceptType: 'Recipe'})-[:`801000004`]->(c:Concept {conceptType: 'RecipeCategory', name: $category_name})
RETURN d.name
```

---

## 数据统计

| 类别 | 数量 |
|------|------|
| Recipe 节点 | ~35+ |
| Ingredient 节点 | ~400+ |
| CookingStep 节点 | ~100+ |
| RecipeCategory 节点 | 9 |
| DifficultyLevel 节点 | 5 |
| has_ingredient 关系 | ~数千条 |
| has_step 关系 | ~数百条 |
| belongs_to_category 关系 | ~35+ |
| has_difficulty 关系 | ~35+ |

---

## 示例：皮蛋豆腐 完整图结构

```
Recipe: 皮蛋豆腐 (201000001)
  category=素菜, difficulty=1, prepTime=5分钟, cookTime=0分钟, servings=1
  tags=豆腐焯水去豆腥味,皮蛋切瓣时刀抹香油防粘
│
├─ [801000001] ─→ Ingredient: 皮蛋 (主料, 2个)
├─ [801000001] ─→ Ingredient: 内酯豆腐 (主料, 1盒)
├─ [801000001] ─→ Ingredient: 生抽 (辅料, 15ml)
├─ [801000001] ─→ Ingredient: 白砂糖 (辅料, 2.5g)
├─ [801000001] ─→ Ingredient: 醋 (辅料, 15ml)
├─ [801000001] ─→ Ingredient: 香油 (辅料, 15ml)
├─ [801000001] ─→ Ingredient: 辣椒油 (辅料, 10ml)
├─ [801000001] ─→ Ingredient: 花生碎 (辅料, 10g)
├─ [801000001] ─→ Ingredient: 蒜蓉 (辅料, 15g)
├─ [801000001] ─→ Ingredient: 香菜 (辅料, 1株)
│
├─ [801000003] ─→ CookingStep: 步骤1 (切 | 刀,案板)
│   └ 先把皮蛋剥壳，切成四瓣。
├─ [801000003] ─→ CookingStep: 步骤2 ...
├─ [801000003] ─→ CookingStep: 步骤3 ...
│
├─ [801000004] ─→ RecipeCategory: 素菜 (710000000)
└─ [801000005] ─→ DifficultyLevel: 一星 (610000000)
```
