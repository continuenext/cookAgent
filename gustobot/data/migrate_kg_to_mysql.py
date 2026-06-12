"""
从 kg_output CSVs 迁移数据到 MySQL
用法: .venv/bin/python gustobot/data/migrate_kg_to_mysql.py
"""
import csv
import re
from pathlib import Path

import pymysql

# ── 数据库连接 ──────────────────────────────────────────────────────────────────
DB_CONF = dict(
    host="127.0.0.1",
    port=13306,
    user="recipe_user",
    password="recipepass",
    database="recipe_db",
    charset="utf8mb4",
)

# ── CSV 路径 ────────────────────────────────────────────────────────────────────
DATA_DIR = Path(__file__).parent / "kg_output"
NODES_CSV = DATA_DIR / "nodes.csv"
RELS_CSV = DATA_DIR / "relationships.csv"

# ── 关系类型 ID ─────────────────────────────────────────────────────────────────
REL_HAS_INGREDIENT = "801000001"  # Recipe -> Ingredient
REL_HAS_STEP = "801000003"        # Recipe -> CookingStep
REL_HAS_CATEGORY = "801000004"    # Recipe -> RecipeCategory
REL_HAS_DIFFICULTY = "801000005"  # Recipe -> DifficultyLevel

# ── 难度映射（数字 / 中文 → MySQL ENUM）────────────────────────────────────────
_DIFF_MAP: dict[str, str] = {
    "1": "easy", "1.0": "easy",
    "2": "easy", "2.0": "easy",
    "3": "medium", "3.0": "medium",
    "4": "hard", "4.0": "hard",
    "5": "hard", "5.0": "hard",
    "简单": "easy", "容易": "easy",
    "中等": "medium", "普通": "medium",
    "困难": "hard", "难": "hard",
}


def _parse_time_str(s: str) -> int:
    """把 '5分钟'/'1小时30分钟' 转为分钟整数，解析失败返回 0"""
    if not s:
        return 0
    total = 0
    for h in re.findall(r"(\d+(?:\.\d+)?)\s*小时", s):
        total += int(float(h) * 60)
    for m in re.findall(r"(\d+(?:\.\d+)?)\s*分钟", s):
        total += int(float(m))
    if total == 0:
        try:
            total = int(float(s))
        except ValueError:
            pass
    return total


def _load_nodes() -> dict[str, dict]:
    """加载全部节点，返回 {nodeId: row} 字典"""
    nodes: dict[str, dict] = {}
    with open(NODES_CSV, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            nodes[row["nodeId"]] = row
    return nodes


def _load_rel_map(
    nodes: dict[str, dict],
) -> tuple[
    dict[str, list[str]],  # recipe_id -> [ingredient_nodeIds]
    dict[str, list[str]],  # recipe_id -> [step_nodeIds]
    dict[str, str],        # recipe_id -> category_name
    dict[str, str],        # recipe_id -> difficulty_name
]:
    """读取 relationships.csv，按类型分组"""
    recipe_ingredients: dict[str, list[str]] = {}
    recipe_steps: dict[str, list[str]] = {}
    recipe_category: dict[str, str] = {}
    recipe_difficulty: dict[str, str] = {}

    with open(RELS_CSV, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            src, dst, rt = row["startNodeId"], row["endNodeId"], row["relationshipType"]
            if rt == REL_HAS_INGREDIENT:
                recipe_ingredients.setdefault(src, []).append(dst)
            elif rt == REL_HAS_STEP:
                recipe_steps.setdefault(src, []).append(dst)
            elif rt == REL_HAS_CATEGORY:
                cat_name = nodes.get(dst, {}).get("name", "")
                if cat_name:
                    recipe_category[src] = cat_name
            elif rt == REL_HAS_DIFFICULTY:
                diff_name = nodes.get(dst, {}).get("name", "")
                if diff_name:
                    recipe_difficulty[src] = diff_name

    return recipe_ingredients, recipe_steps, recipe_category, recipe_difficulty


def _ensure_cuisine(cur: pymysql.cursors.Cursor, name: str) -> int | None:
    """按名称找或创建 cuisine，返回 id"""
    if not name:
        return None
    cur.execute("SELECT id FROM cuisines WHERE name=%s", (name,))
    row = cur.fetchone()
    if row:
        return row[0]
    cur.execute(
        "INSERT INTO cuisines (name) VALUES (%s) ON DUPLICATE KEY UPDATE id=LAST_INSERT_ID(id)",
        (name,),
    )
    return cur.lastrowid


def _ensure_ingredient(cur: pymysql.cursors.Cursor, name: str, category: str) -> int:
    """按名称找或创建 ingredient，返回 id"""
    cur.execute("SELECT id FROM ingredients WHERE name=%s", (name,))
    row = cur.fetchone()
    if row:
        return row[0]
    cur.execute(
        "INSERT INTO ingredients (name, category) VALUES (%s, %s) "
        "ON DUPLICATE KEY UPDATE id=LAST_INSERT_ID(id)",
        (name, category or None),
    )
    return cur.lastrowid


def main() -> None:
    print("正在加载 CSV 数据...")
    nodes = _load_nodes()
    recipe_ingredients_map, recipe_steps_map, recipe_category_map, recipe_difficulty_map = (
        _load_rel_map(nodes)
    )

    # 过滤有效 Recipe 节点（排除根节点 '菜谱'）
    recipes = [
        n for n in nodes.values()
        if n["labels"] == "Recipe" and n["name"] not in ("菜谱", "")
    ]
    print(f"待导入菜谱数量: {len(recipes)}")

    conn = pymysql.connect(**DB_CONF)
    try:
        with conn.cursor() as cur:
            inserted_recipes = 0
            inserted_ingredients = 0
            inserted_steps = 0
            inserted_ri = 0  # recipe_ingredients 关联

            for rec in recipes:
                nid = rec["nodeId"]
                name = rec["name"].strip()
                if not name:
                    continue

                # ── difficulty ──────────────────────────────────────────────────
                diff_raw = rec.get("difficulty", "").strip()
                difficulty = _DIFF_MAP.get(diff_raw)
                if not difficulty:
                    # 尝试从 DifficultyLevel 节点名
                    diff_node_name = recipe_difficulty_map.get(nid, "")
                    difficulty = _DIFF_MAP.get(diff_node_name, "easy")

                # ── time ────────────────────────────────────────────────────────
                prep_min = _parse_time_str(rec.get("prepTime", ""))
                cook_min = _parse_time_str(rec.get("cookTime", ""))
                total_time = prep_min + cook_min

                # ── servings ────────────────────────────────────────────────────
                try:
                    servings = int(float(rec.get("servings") or 4))
                except ValueError:
                    servings = 4

                # ── cuisine ─────────────────────────────────────────────────────
                cuisine_name = (
                    rec.get("cuisineType") or recipe_category_map.get(nid, "")
                ).strip()
                cuisine_id = _ensure_cuisine(cur, cuisine_name) if cuisine_name else None

                # ── tags / tips → description ───────────────────────────────────
                tags = rec.get("tags", "")
                description = tags if tags else None

                # ── 写入 recipes（存在则跳过）──────────────────────────────────
                cur.execute("SELECT id FROM recipes WHERE name=%s", (name,))
                existing = cur.fetchone()
                if existing:
                    recipe_db_id = existing[0]
                else:
                    cur.execute(
                        """INSERT INTO recipes
                               (name, description, total_time, servings, difficulty, cuisine_id)
                           VALUES (%s, %s, %s, %s, %s, %s)""",
                        (name, description, total_time, servings, difficulty, cuisine_id),
                    )
                    recipe_db_id = cur.lastrowid
                    inserted_recipes += 1

                # ── 食材 ────────────────────────────────────────────────────────
                for ing_nid in recipe_ingredients_map.get(nid, []):
                    ing_node = nodes.get(ing_nid)
                    if not ing_node:
                        continue
                    ing_name = ing_node["name"].strip()
                    if not ing_name or ing_name == "食材":
                        continue

                    ing_db_id = _ensure_ingredient(
                        cur, ing_name, ing_node.get("category", "")
                    )
                    inserted_ingredients += 1

                    # recipe_ingredients 关联
                    qty = ing_node.get("amount", "").strip() or "适量"
                    unit = ing_node.get("unit", "").strip() or None
                    is_main = ing_node.get("isMain", "").strip().lower() == "true"

                    cur.execute(
                        "SELECT id FROM recipe_ingredients WHERE recipe_id=%s AND ingredient_id=%s",
                        (recipe_db_id, ing_db_id),
                    )
                    if not cur.fetchone():
                        ing_type = "main" if is_main else "auxiliary"
                        cur.execute(
                            """INSERT INTO recipe_ingredients
                                   (recipe_id, ingredient_id, quantity, unit, is_main, ingredient_type)
                               VALUES (%s, %s, %s, %s, %s, %s)""",
                            (recipe_db_id, ing_db_id, qty, unit, is_main, ing_type),
                        )
                        inserted_ri += 1

                # ── 烹饪步骤 ────────────────────────────────────────────────────
                step_nids = recipe_steps_map.get(nid, [])
                # 按 stepNumber 排序
                step_nodes = []
                for s_nid in step_nids:
                    s_node = nodes.get(s_nid)
                    if s_node:
                        try:
                            step_num = int(float(s_node.get("stepNumber") or 0))
                        except ValueError:
                            step_num = 0
                        step_nodes.append((step_num, s_node))
                step_nodes.sort(key=lambda x: x[0])

                for step_num, s_node in step_nodes:
                    if step_num == 0:
                        continue
                    instruction = (s_node.get("description") or "").strip()
                    if not instruction:
                        continue
                    action = (s_node.get("methods") or "操作").strip() or "操作"
                    tools_raw = s_node.get("tools", "")
                    tools_json = (
                        None if not tools_raw else
                        "[" + ", ".join(f'"{t.strip()}"' for t in tools_raw.split(",") if t.strip()) + "]"
                    )
                    duration = _parse_time_str(s_node.get("timeEstimate", ""))

                    cur.execute(
                        "SELECT id FROM recipe_steps WHERE recipe_id=%s AND step_number=%s",
                        (recipe_db_id, step_num),
                    )
                    if not cur.fetchone():
                        cur.execute(
                            """INSERT INTO recipe_steps
                                   (recipe_id, step_number, action, instruction, duration, tools_used)
                               VALUES (%s, %s, %s, %s, %s, %s)""",
                            (recipe_db_id, step_num, action[:100], instruction, duration, tools_json),
                        )
                        inserted_steps += 1

            conn.commit()
            print(f"\n导入完成:")
            print(f"  菜谱:       {inserted_recipes}")
            print(f"  食材 (新增): {inserted_ingredients}")
            print(f"  烹饪步骤:   {inserted_steps}")
            print(f"  食材关联:   {inserted_ri}")

            # 汇总
            cur.execute("SELECT COUNT(*) FROM recipes")
            print(f"\n当前 recipes 总数: {cur.fetchone()[0]}")
            cur.execute("SELECT COUNT(*) FROM ingredients")
            print(f"当前 ingredients 总数: {cur.fetchone()[0]}")
            cur.execute("SELECT COUNT(*) FROM recipe_steps")
            print(f"当前 recipe_steps 总数: {cur.fetchone()[0]}")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
