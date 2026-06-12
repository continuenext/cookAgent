#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Neo4j 知识图谱 Schema 可视化
输出交互式 HTML 图 + 文本摘要
"""
import os
import sys
import json
sys.path.insert(0, '/Users/dengjiayi/Documents/study/gustobot')

from neo4j import GraphDatabase
from pyvis.network import Network

# ── 连接配置（Docker 映射端口：17687；容器内端口：7687）────────────────────
NEO4J_URI      = os.getenv("NEO4J_URI",      "bolt://localhost:17687")
NEO4J_USER     = os.getenv("NEO4J_USER",     "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "recipepass")

# 节点标签 → 颜色映射
LABEL_COLORS = {
    "Recipe":      "#FF6B6B",
    "Ingredient":  "#4ECDC4",
    "CookingStep": "#45B7D1",
    "Category":    "#96CEB4",
    "Tag":         "#FFEAA7",
    "Cuisine":     "#DDA0DD",
    "Nutrition":   "#98D8C8",
}
DEFAULT_COLOR = "#ADB5BD"


def get_driver():
    return GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))


# ── 1. 查询 Schema ─────────────────────────────────────────────────────────

def fetch_schema(driver) -> dict:
    """
    使用 db.schema.visualization() 获取 Schema 级别的节点与关系，
    并额外采样每个标签的属性键。
    """
    schema = {"nodes": {}, "relationships": []}

    with driver.session() as session:
        # --- Schema 图（节点 + 关系骨架）---
        result = session.run("CALL db.schema.visualization()")
        record = result.single()
        if record:
            for node in record["nodes"]:
                label = list(node.labels)[0] if node.labels else "Unknown"
                eid = node.element_id
                schema["nodes"][eid] = {
                    "label": label,
                    "id":    eid,
                }
            for rel in record["relationships"]:
                schema["relationships"].append({
                    "start":  rel.start_node.element_id,
                    "end":    rel.end_node.element_id,
                    "type":   rel.type,
                })

        # --- 每个标签的属性键（采样 1 条）---
        labels_result = session.run("CALL db.labels() YIELD label RETURN label")
        labels = [r["label"] for r in labels_result]

        for label in labels:
            try:
                sample = session.run(
                    f"MATCH (n:{label}) RETURN keys(n) AS keys LIMIT 1"
                ).single()
                props = sample["keys"] if sample else []
            except Exception:
                props = []

            # 如果 schema.visualization 没有此标签，补充进去
            existing = next(
                (v for v in schema["nodes"].values() if v["label"] == label),
                None
            )
            if existing:
                existing["properties"] = props
            else:
                schema["nodes"][f"extra_{label}"] = {
                    "label":      label,
                    "id":         f"extra_{label}",
                    "properties": props,
                }

        # --- 关系类型（补全 db.schema 可能遗漏的）---
        rel_types_result = session.run(
            "CALL db.relationshipTypes() YIELD relationshipType RETURN relationshipType"
        )
        existing_types = {r["type"] for r in schema["relationships"]}
        for r in rel_types_result:
            rtype = r["relationshipType"]
            if rtype not in existing_types:
                schema["relationships"].append({
                    "start": None, "end": None, "type": rtype
                })

    return schema


# ── 2. 文本摘要 ─────────────────────────────────────────────────────────────

def print_schema_summary(schema: dict):
    print("\n" + "=" * 60)
    print("  Neo4j Schema 摘要")
    print("=" * 60)

    print(f"\n【节点标签】共 {len(schema['nodes'])} 个\n")
    for info in schema["nodes"].values():
        props = info.get("properties", [])
        props_str = "、".join(props) if props else "（无属性采样）"
        print(f"  ● {info['label']}")
        print(f"    属性: {props_str}")

    rels = [r for r in schema["relationships"] if r["start"] is not None]
    orphan_rels = [r for r in schema["relationships"] if r["start"] is None]

    print(f"\n【关系类型】共 {len(schema['relationships'])} 个\n")
    node_map = {v["id"]: v["label"] for v in schema["nodes"].values()}
    for r in rels:
        src = node_map.get(r["start"], r["start"])
        tgt = node_map.get(r["end"],   r["end"])
        print(f"  ({src}) --[{r['type']}]--> ({tgt})")
    for r in orphan_rels:
        print(f"  [孤立关系类型] {r['type']}")

    print("\n" + "=" * 60 + "\n")


# ── 3. Pyvis 可视化 ─────────────────────────────────────────────────────────

def build_html_graph(schema: dict, output_path: str):
    net = Network(
        height="800px",
        width="100%",
        bgcolor="#1a1a2e",
        font_color="#ffffff",
        directed=True,
        notebook=False,
    )
    net.set_options("""
    {
      "physics": {
        "barnesHut": {
          "gravitationalConstant": -8000,
          "springLength": 200
        }
      },
      "edges": {
        "arrows": { "to": { "enabled": true } },
        "color": { "color": "#888888" },
        "font": { "color": "#cccccc", "size": 12 }
      },
      "nodes": {
        "font": { "size": 14, "bold": true }
      }
    }
    """)

    node_map = {}  # id → label

    # 添加节点
    for info in schema["nodes"].values():
        label = info["label"]
        node_id = info["id"]
        props = info.get("properties", [])
        color = LABEL_COLORS.get(label, DEFAULT_COLOR)
        tooltip = f"<b>{label}</b><br/>属性: {', '.join(props) if props else '无'}"
        net.add_node(
            node_id,
            label=label,
            color=color,
            size=35,
            title=tooltip,
            shape="dot",
        )
        node_map[node_id] = label

    # 添加关系边（跳过无端点的）
    added_edges = set()
    for r in schema["relationships"]:
        if r["start"] is None or r["end"] is None:
            continue
        edge_key = (r["start"], r["end"], r["type"])
        if edge_key in added_edges:
            continue
        added_edges.add(edge_key)
        net.add_edge(r["start"], r["end"], label=r["type"])

    net.save_graph(output_path)
    print(f"✅ 交互式 HTML 图已保存: {os.path.abspath(output_path)}")


# ── 主函数 ──────────────────────────────────────────────────────────────────

def main():
    output_dir = os.path.join(os.path.dirname(__file__), "schema_output")
    os.makedirs(output_dir, exist_ok=True)
    html_path  = os.path.join(output_dir, "schema_graph.html")
    json_path  = os.path.join(output_dir, "schema_data.json")

    print(f"正在连接 Neo4j: {NEO4J_URI} ...")
    driver = get_driver()

    try:
        print("正在查询 Schema ...")
        schema = fetch_schema(driver)

        # 输出文本摘要
        print_schema_summary(schema)

        # 保存原始 JSON（便于调试）
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(schema, f, ensure_ascii=False, indent=2)
        print(f"✅ Schema JSON 已保存: {os.path.abspath(json_path)}")

        # 生成 HTML 可视化
        build_html_graph(schema, html_path)

    finally:
        driver.close()


if __name__ == "__main__":
    main()
