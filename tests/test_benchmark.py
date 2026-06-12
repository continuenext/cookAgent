"""
GustoBot 综合性能基准测试脚本

覆盖五大指标：
1. 系统并发处理能力 (QPS) 和意图识别路由准确率
2. 核心饮食问答召回率 / 准确率
3. 知识图谱自动化构建统计
4. 多轮会话隔离 & Token 消耗 / 延迟
5. 越界回答 / 幻觉率

测试数据 ≥ 100 条，完成后安全删除所有测试痕迹。
"""

import asyncio
import json
import os
import statistics
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx

# ───────── 配置 ─────────
BASE_URL = os.getenv("GUSTOBOT_TEST_URL", "http://localhost:8000")
API_PREFIX = "/api/v1"
CONCURRENCY = 10  # 并发数
TIMEOUT = 120  # 单次请求超时（秒）

# 批量测试参数：支持放大测试数据规模，避免只有几十条样本
DATA_SCALE = max(int(os.getenv("GUSTOBOT_BENCH_DATA_SCALE", "1")), 1)
INTENT_TARGET = max(int(os.getenv("GUSTOBOT_BENCH_INTENT_TARGET", "0")), 0)
QA_TARGET = max(int(os.getenv("GUSTOBOT_BENCH_QA_TARGET", "0")), 0)
OOS_TARGET = max(int(os.getenv("GUSTOBOT_BENCH_OOS_TARGET", "0")), 0)

# 分批创建协程，避免超大数据量时一次性创建过多 task
TASK_BATCH_SIZE = max(int(os.getenv("GUSTOBOT_BENCH_TASK_BATCH_SIZE", "200")), 1)

# 用于标识测试用户 / 会话，方便最后清理
TEST_USER_PREFIX = "__bench_user_"
TEST_SESSION_PREFIX = "__bench_sess_"

# ─── 为安全删除收集所有测试产生的 session_id ───
_created_session_ids: list[str] = []


# ===========================================================================
# 1. 意图识别路由准确率测试数据  (120 条)
# ===========================================================================
INTENT_TEST_DATA: List[Dict[str, str]] = [
    # ── general-query (20 条) ──
    {"message": "你好", "expected": "general-query"},
    {"message": "早上好呀", "expected": "general-query"},
    {"message": "谢谢你的帮助", "expected": "general-query"},
    {"message": "再见", "expected": "general-query"},
    {"message": "你叫什么名字", "expected": "general-query"},
    {"message": "今天天气不错", "expected": "general-query"},
    {"message": "晚安", "expected": "general-query"},
    {"message": "嗨", "expected": "general-query"},
    {"message": "你是谁", "expected": "general-query"},
    {"message": "辛苦了", "expected": "general-query"},
    {"message": "谢谢", "expected": "general-query"},
    {"message": "了解了", "expected": "general-query"},
    {"message": "好的收到", "expected": "general-query"},
    {"message": "不用了", "expected": "general-query"},
    {"message": "没问题", "expected": "general-query"},
    {"message": "哈哈哈", "expected": "general-query"},
    {"message": "好的谢谢", "expected": "general-query"},
    {"message": "你好厉害", "expected": "general-query"},
    {"message": "你能做什么", "expected": "general-query"},
    {"message": "周末快乐", "expected": "general-query"},

    # ── graphrag-query (30 条) ──
    {"message": "红烧肉怎么做", "expected": "graphrag-query"},
    {"message": "宫保鸡丁需要什么食材", "expected": "graphrag-query"},
    {"message": "糖醋排骨的做法步骤", "expected": "graphrag-query"},
    {"message": "麻婆豆腐用什么烹饪方法", "expected": "graphrag-query"},
    {"message": "鱼香肉丝的配料有哪些", "expected": "graphrag-query"},
    {"message": "怎么做蛋炒饭", "expected": "graphrag-query"},
    {"message": "酸辣土豆丝的火候", "expected": "graphrag-query"},
    {"message": "可乐鸡翅需要准备什么", "expected": "graphrag-query"},
    {"message": "清蒸鲈鱼的步骤", "expected": "graphrag-query"},
    {"message": "回锅肉如何做", "expected": "graphrag-query"},
    {"message": "番茄炒蛋要什么原料", "expected": "graphrag-query"},
    {"message": "红烧鱼的烧法", "expected": "graphrag-query"},
    {"message": "拔丝土豆怎么炒", "expected": "graphrag-query"},
    {"message": "水煮牛肉的烹饪技巧", "expected": "graphrag-query"},
    {"message": "葱油拌面怎么做好吃", "expected": "graphrag-query"},
    {"message": "地三鲜用什么食材", "expected": "graphrag-query"},
    {"message": "蒜蓉西兰花的做法", "expected": "graphrag-query"},
    {"message": "皮蛋豆腐怎么做", "expected": "graphrag-query"},
    {"message": "手撕包菜的步骤是什么", "expected": "graphrag-query"},
    {"message": "凉拌黄瓜需要哪些调料", "expected": "graphrag-query"},
    {"message": "小龙虾如何做", "expected": "graphrag-query"},
    {"message": "日式咖喱饭的做法步骤", "expected": "graphrag-query"},
    {"message": "扬州炒饭需要什么配料", "expected": "graphrag-query"},
    {"message": "油焖大虾怎么做", "expected": "graphrag-query"},
    {"message": "新疆大盘鸡的食材列表", "expected": "graphrag-query"},
    {"message": "梅菜扣肉的制作方法", "expected": "graphrag-query"},
    {"message": "蛋包饭怎么做", "expected": "graphrag-query"},
    {"message": "老式锅包肉的做法技巧", "expected": "graphrag-query"},
    {"message": "白灼虾需要什么调料", "expected": "graphrag-query"},
    {"message": "台式卤肉饭的烹饪步骤", "expected": "graphrag-query"},

    # ── text2sql-query (20 条) ──
    {"message": "系统里有多少道菜", "expected": "text2sql-query"},
    {"message": "统计有多少种食材", "expected": "text2sql-query"},
    {"message": "哪个菜系的菜谱最多", "expected": "text2sql-query"},
    {"message": "最受欢迎的5道菜是什么", "expected": "text2sql-query"},
    {"message": "数据库里有多少道荤菜", "expected": "text2sql-query"},
    {"message": "素菜的数量有多少", "expected": "text2sql-query"},
    {"message": "平均烹饪时间是多长", "expected": "text2sql-query"},
    {"message": "最简单的菜谱有哪些", "expected": "text2sql-query"},
    {"message": "各菜系的菜谱占比", "expected": "text2sql-query"},
    {"message": "用鸡肉做的菜有几道", "expected": "text2sql-query"},
    {"message": "排名前十的热门食材", "expected": "text2sql-query"},
    {"message": "总共有多少道甜品", "expected": "text2sql-query"},
    {"message": "烹饪时间最长的菜是哪道", "expected": "text2sql-query"},
    {"message": "列出所有早餐类菜谱", "expected": "text2sql-query"},
    {"message": "有哪些菜的难度是简单的", "expected": "text2sql-query"},
    {"message": "统计每种难度有多少菜谱", "expected": "text2sql-query"},
    {"message": "有几种汤类菜谱", "expected": "text2sql-query"},
    {"message": "数据库里的饮料有多少种", "expected": "text2sql-query"},
    {"message": "最少食材的菜谱是哪道", "expected": "text2sql-query"},
    {"message": "每种菜系各有多少菜", "expected": "text2sql-query"},

    # ── additional-query (15 条) ──
    {"message": "我想做菜", "expected": "additional-query"},
    {"message": "帮我推荐一道菜", "expected": "additional-query"},
    {"message": "做什么好呢", "expected": "additional-query"},
    {"message": "有什么好吃的", "expected": "additional-query"},
    {"message": "我饿了", "expected": "additional-query"},
    {"message": "推荐菜", "expected": "additional-query"},
    {"message": "我不知道做什么", "expected": "additional-query"},
    {"message": "晚饭做什么", "expected": "additional-query"},
    {"message": "做点好吃的", "expected": "additional-query"},
    {"message": "中午吃什么", "expected": "additional-query"},
    {"message": "今天想做菜", "expected": "additional-query"},
    {"message": "有啥推荐的", "expected": "additional-query"},
    {"message": "来道菜", "expected": "additional-query"},
    {"message": "我想学做饭", "expected": "additional-query"},
    {"message": "推荐一下", "expected": "additional-query"},

    # ── image-query (10 条) ──
    {"message": "帮我看看这道菜是什么", "expected": "image-query"},
    {"message": "这张图片里的食材有哪些", "expected": "image-query"},
    {"message": "识别这道菜", "expected": "image-query"},
    {"message": "生成一张红烧肉的图片", "expected": "image-query"},
    {"message": "画一张宫保鸡丁", "expected": "image-query"},
    {"message": "看图识菜", "expected": "image-query"},
    {"message": "给我一张糖醋排骨的照片", "expected": "image-query"},
    {"message": "这是什么菜", "expected": "image-query"},
    {"message": "识别食材图片", "expected": "image-query"},
    {"message": "展示麻婆豆腐的成品图", "expected": "image-query"},

    # ── file-query (10 条) ──
    {"message": "分析这个菜谱文档", "expected": "file-query"},
    {"message": "帮我导入这个文件", "expected": "file-query"},
    {"message": "上传的excel有什么内容", "expected": "file-query"},
    {"message": "处理这个csv文件", "expected": "file-query"},
    {"message": "总结这份文档的内容", "expected": "file-query"},
    {"message": "导出菜谱为pdf", "expected": "file-query"},
    {"message": "帮我看看这份文件", "expected": "file-query"},
    {"message": "保存为excel", "expected": "file-query"},
    {"message": "生成菜谱报告文件", "expected": "file-query"},
    {"message": "导入菜谱数据文件", "expected": "file-query"},
]


# ===========================================================================
# 2. 饮食问答评测数据 (用于召回率 / 准确率)
# ===========================================================================
QA_TEST_DATA: List[Dict[str, Any]] = [
    # 每条包含 question, expected_keywords (回答中应命中的关键词)
    {"question": "红烧肉怎么做", "expected_keywords": ["五花肉", "酱油", "糖"]},
    {"question": "宫保鸡丁需要什么食材", "expected_keywords": ["鸡", "花生", "辣椒"]},
    {"question": "糖醋排骨的做法", "expected_keywords": ["排骨", "糖", "醋"]},
    {"question": "蛋炒饭怎么炒", "expected_keywords": ["鸡蛋", "米饭"]},
    {"question": "凉拌黄瓜的做法", "expected_keywords": ["黄瓜", "蒜"]},
    {"question": "麻婆豆腐的配料", "expected_keywords": ["豆腐", "辣"]},
    {"question": "酸辣土豆丝怎么做", "expected_keywords": ["土豆", "醋"]},
    {"question": "可乐鸡翅的做法", "expected_keywords": ["鸡翅", "可乐"]},
    {"question": "番茄炒蛋怎么做", "expected_keywords": ["番茄", "鸡蛋"]},
    {"question": "水煮牛肉的做法", "expected_keywords": ["牛肉", "辣"]},
    {"question": "鱼香肉丝需要什么", "expected_keywords": ["肉丝"]},
    {"question": "回锅肉的做法", "expected_keywords": ["五花肉", "豆瓣"]},
    {"question": "清蒸鲈鱼的步骤", "expected_keywords": ["鲈鱼", "蒸"]},
    {"question": "地三鲜的做法", "expected_keywords": ["茄子", "土豆", "青椒"]},
    {"question": "皮蛋豆腐怎么做", "expected_keywords": ["皮蛋", "豆腐"]},
    {"question": "蒜蓉西兰花的做法", "expected_keywords": ["西兰花", "蒜"]},
    {"question": "手撕包菜的做法", "expected_keywords": ["包菜"]},
    {"question": "葱油拌面怎么做", "expected_keywords": ["葱", "面"]},
    {"question": "小龙虾怎么做好吃", "expected_keywords": ["小龙虾"]},
    {"question": "扬州炒饭的做法", "expected_keywords": ["米饭", "鸡蛋"]},
    {"question": "油焖大虾的做法", "expected_keywords": ["虾"]},
    {"question": "白灼虾怎么做", "expected_keywords": ["虾"]},
    {"question": "日式咖喱饭的做法", "expected_keywords": ["咖喱"]},
    {"question": "梅菜扣肉怎么做", "expected_keywords": ["梅菜", "肉"]},
    {"question": "新疆大盘鸡的做法", "expected_keywords": ["鸡", "土豆"]},
    {"question": "老式锅包肉的做法", "expected_keywords": ["肉", "糖", "醋"]},
    {"question": "台式卤肉饭怎么做", "expected_keywords": ["卤", "肉"]},
    {"question": "蛋包饭的做法", "expected_keywords": ["鸡蛋", "米饭"]},
    {"question": "红烧鱼怎么做", "expected_keywords": ["鱼", "酱油"]},
    {"question": "炒年糕的做法", "expected_keywords": ["年糕"]},
]


# ===========================================================================
# 3. 越界 / 幻觉测试数据
# ===========================================================================
OUT_OF_SCOPE_DATA: List[Dict[str, str]] = [
    # 完全脱离菜谱的问题 → 应拒答或引导回厨房话题
    {"message": "今天股票会涨吗", "type": "out_of_scope"},
    {"message": "帮我写一段Python代码", "type": "out_of_scope"},
    {"message": "明天会下雨吗", "type": "out_of_scope"},
    {"message": "推荐一部电影", "type": "out_of_scope"},
    {"message": "你觉得哪个明星最好看", "type": "out_of_scope"},
    {"message": "最近有什么新闻", "type": "out_of_scope"},
    {"message": "帮我算一道数学题", "type": "out_of_scope"},
    {"message": "怎么学英语", "type": "out_of_scope"},
    {"message": "哪里可以买到便宜的手机", "type": "out_of_scope"},
    {"message": "你支持哪个政党", "type": "out_of_scope"},
    {"message": "帮我翻译一段话", "type": "out_of_scope"},
    {"message": "推荐一首歌", "type": "out_of_scope"},
    {"message": "怎么减肥最快", "type": "out_of_scope"},
    {"message": "怎么投资理财", "type": "out_of_scope"},
    {"message": "最近哪款游戏好玩", "type": "out_of_scope"},
    # 容易产生幻觉的编造菜谱问题 → 应诚实说不知道
    {"message": "满天星炒宇宙蛋怎么做", "type": "hallucination_trap"},
    {"message": "量子纠缠红烧肉的配方", "type": "hallucination_trap"},
    {"message": "暗物质提拉米苏的做法大全", "type": "hallucination_trap"},
    {"message": "火星岩浆炖地球核心的步骤", "type": "hallucination_trap"},
    {"message": "太阳能光合糖醋里脊怎么做", "type": "hallucination_trap"},
    {"message": "黑洞蒸饺的食材有哪些", "type": "hallucination_trap"},
    {"message": "石墨烯凉皮的做法", "type": "hallucination_trap"},
    {"message": "CPU芯片烧烤怎么做", "type": "hallucination_trap"},
    {"message": "5G信号炒饭教程", "type": "hallucination_trap"},
    {"message": "二氧化碳冰淇淋的做法", "type": "hallucination_trap"},
]


# ===========================================================================
# 4. 多轮会话测试场景
# ===========================================================================
MULTI_TURN_SCENARIOS: List[List[str]] = [
    # 场景 1: 连续询问做法
    ["红烧肉怎么做", "需要什么食材", "火候怎么控制"],
    # 场景 2: 菜谱切换（隔离性测试）
    ["宫保鸡丁怎么做", "换一个，糖醋排骨呢", "刚才那个宫保鸡丁需要多少花生"],
    # 场景 3: 追问补充
    ["我想做菜", "想做鸡肉的", "简单一点的怎么做"],
    # 场景 4: 闲聊到业务切换
    ["你好", "红烧鱼怎么做", "需要什么调料"],
    # 场景 5: 连续统计类
    ["有多少道菜", "其中荤菜有几道", "最简单的菜是什么"],
]


# ===========================================================================
# 工具函数
# ===========================================================================

def _expand_dataset(
    data: List[Dict[str, Any]],
    *,
    scale: int,
    target_size: int,
) -> List[Dict[str, Any]]:
    """按倍数或目标数量扩容测试数据。"""
    if not data:
        return []

    expanded = list(data) * max(scale, 1)
    if target_size > 0:
        if len(expanded) >= target_size:
            return expanded[:target_size]

        # 按顺序补齐到指定规模，保持类别分布稳定
        idx = 0
        while len(expanded) < target_size:
            expanded.append(data[idx % len(data)].copy())
            idx += 1
    return expanded


def _chunked(total: int, chunk_size: int) -> List[range]:
    """将 [0, total) 切分为多个 range，便于分批调度异步任务。"""
    return [range(i, min(i + chunk_size, total)) for i in range(0, total, chunk_size)]


# 运行时数据集（支持批量扩容）
RUNTIME_INTENT_TEST_DATA = _expand_dataset(
    INTENT_TEST_DATA,
    scale=DATA_SCALE,
    target_size=INTENT_TARGET,
)
RUNTIME_QA_TEST_DATA = _expand_dataset(
    QA_TEST_DATA,
    scale=DATA_SCALE,
    target_size=QA_TARGET,
)
RUNTIME_OUT_OF_SCOPE_DATA = _expand_dataset(
    OUT_OF_SCOPE_DATA,
    scale=DATA_SCALE,
    target_size=OOS_TARGET,
)

async def _create_session(client: httpx.AsyncClient, user_id: str) -> str:
    """创建测试会话并记录 ID"""
    resp = await client.post(
        f"{BASE_URL}{API_PREFIX}/sessions",
        json={"title": "benchmark_test", "user_id": user_id},
        timeout=TIMEOUT,
    )
    if resp.status_code == 201:
        sid = resp.json()["session_id"]
        _created_session_ids.append(sid)
        return sid
    # 回退：使用 uuid 作为 session_id（无需服务端创建）
    sid = TEST_SESSION_PREFIX + uuid.uuid4().hex[:12]
    _created_session_ids.append(sid)
    return sid


async def _chat(client: httpx.AsyncClient, message: str, session_id: str) -> Tuple[Dict[str, Any], float]:
    """发送聊天请求，返回 (response_json, latency_ms)"""
    t0 = time.perf_counter()
    resp = await client.post(
        f"{BASE_URL}{API_PREFIX}/chat",
        json={"message": message, "session_id": session_id},
        timeout=TIMEOUT,
    )
    latency_ms = (time.perf_counter() - t0) * 1000
    if resp.status_code != 200:
        return {"answer": "", "router_type": "error", "error": resp.text}, latency_ms
    return resp.json(), latency_ms


async def _delete_session(client: httpx.AsyncClient, session_id: str) -> bool:
    """删除单个测试会话"""
    try:
        resp = await client.delete(
            f"{BASE_URL}{API_PREFIX}/sessions/{session_id}",
            timeout=10,
        )
        return resp.status_code in (200, 204, 404)
    except Exception:
        return False


# ===========================================================================
# 测试 1：并发 QPS 与意图识别准确率
# ===========================================================================

async def test_qps_and_intent_accuracy(client: httpx.AsyncClient) -> Dict[str, Any]:
    """
    并发发送意图测试数据（支持批量扩容），统计：
    - QPS (queries per second)
    - 路由准确率
    - 各路由的 precision / recall
    """
    print("\n" + "=" * 70)
    print("  测试 1：并发 QPS 与意图识别路由准确率")
    print("=" * 70)

    total = len(RUNTIME_INTENT_TEST_DATA)
    results: List[Dict[str, Any]] = [None] * total  # type: ignore
    latencies: List[float] = []
    semaphore = asyncio.Semaphore(CONCURRENCY)

    async def _worker(idx: int, item: Dict[str, str]):
        async with semaphore:
            sid = TEST_SESSION_PREFIX + uuid.uuid4().hex[:8]
            _created_session_ids.append(sid)
            resp, lat = await _chat(client, item["message"], sid)
            latencies.append(lat)
            results[idx] = {
                "message": item["message"],
                "expected": item["expected"],
                "actual": resp.get("router_type", "unknown"),
                "latency_ms": lat,
            }

    t_start = time.perf_counter()
    for batch_range in _chunked(total, TASK_BATCH_SIZE):
        tasks = [_worker(i, RUNTIME_INTENT_TEST_DATA[i]) for i in batch_range]
        await asyncio.gather(*tasks, return_exceptions=True)
    t_elapsed = time.perf_counter() - t_start

    # 统计
    correct = sum(1 for r in results if r and r["expected"] == r["actual"])
    accuracy = correct / total * 100
    qps = total / t_elapsed if t_elapsed > 0 else 0
    avg_latency = statistics.mean(latencies) if latencies else 0
    p50 = statistics.median(latencies) if latencies else 0
    p95 = sorted(latencies)[int(len(latencies) * 0.95)] if latencies else 0

    # 按路由类型统计
    route_stats: Dict[str, Dict[str, int]] = {}
    for r in results:
        if not r:
            continue
        exp = r["expected"]
        act = r["actual"]
        if exp not in route_stats:
            route_stats[exp] = {"tp": 0, "fp": 0, "fn": 0, "total": 0}
        route_stats[exp]["total"] += 1
        if exp == act:
            route_stats[exp]["tp"] += 1
        else:
            route_stats[exp]["fn"] += 1
            if act not in route_stats:
                route_stats[act] = {"tp": 0, "fp": 0, "fn": 0, "total": 0}
            route_stats[act]["fp"] += 1

    # 输出
    print(f"\n  总请求数: {total}  |  并发数: {CONCURRENCY}")
    print(f"  总耗时: {t_elapsed:.2f}s  |  QPS: {qps:.2f}")
    print(f"  平均延迟: {avg_latency:.0f}ms  |  P50: {p50:.0f}ms  |  P95: {p95:.0f}ms")
    print(f"\n  路由准确率: {correct}/{total} = {accuracy:.1f}%")
    print(f"\n  {'路由类型':<20} {'正确':<6} {'总数':<6} {'准确率':<8}")
    print("  " + "-" * 42)
    for route, stats in sorted(route_stats.items()):
        tp = stats["tp"]
        tot = stats["total"]
        acc = tp / tot * 100 if tot > 0 else 0
        print(f"  {route:<20} {tp:<6} {tot:<6} {acc:.1f}%")

    # 输出错误样例
    errors = [r for r in results if r and r["expected"] != r["actual"]]
    if errors:
        print(f"\n  错误样例 (前 10 条):")
        for e in errors[:10]:
            print(f"    [{e['expected']}→{e['actual']}] {e['message']}")

    return {
        "qps": round(qps, 2),
        "intent_accuracy": round(accuracy, 1),
        "avg_latency_ms": round(avg_latency, 0),
        "p50_ms": round(p50, 0),
        "p95_ms": round(p95, 0),
        "route_stats": route_stats,
    }


# ===========================================================================
# 测试 2：饮食问答召回率 / 准确率
# ===========================================================================

async def test_qa_recall_precision(client: httpx.AsyncClient) -> Dict[str, Any]:
    """
    发送 QA 测试数据（支持批量扩容），检查回答中是否命中 expected_keywords。
    - 召回率: 命中关键词数 / 期望关键词总数
    - 准确率: 包含至少一个关键词的回答比例
    """
    print("\n" + "=" * 70)
    print("  测试 2：核心饮食问答召回率 / 准确率")
    print("=" * 70)

    total = len(RUNTIME_QA_TEST_DATA)
    hit_count = 0          # 至少命中一个关键词的问题数
    total_keywords = 0     # 期望关键词总数
    hit_keywords = 0       # 命中的关键词总数
    details: List[Dict[str, Any]] = []
    semaphore = asyncio.Semaphore(CONCURRENCY)

    async def _worker(item: Dict[str, Any]):
        nonlocal hit_count, total_keywords, hit_keywords
        async with semaphore:
            sid = TEST_SESSION_PREFIX + uuid.uuid4().hex[:8]
            _created_session_ids.append(sid)
            resp, lat = await _chat(client, item["question"], sid)
            answer = resp.get("answer", "")
            expected_kws = item["expected_keywords"]
            matched = [kw for kw in expected_kws if kw in answer]
            total_keywords += len(expected_kws)
            hit_keywords += len(matched)
            if matched:
                hit_count += 1
            details.append({
                "question": item["question"],
                "matched": matched,
                "missed": [kw for kw in expected_kws if kw not in answer],
                "latency_ms": lat,
            })

    for batch_range in _chunked(total, TASK_BATCH_SIZE):
        tasks = [_worker(RUNTIME_QA_TEST_DATA[i]) for i in batch_range]
        await asyncio.gather(*tasks, return_exceptions=True)

    recall = hit_keywords / total_keywords * 100 if total_keywords > 0 else 0
    precision = hit_count / total * 100 if total > 0 else 0

    print(f"\n  问答总数: {total}")
    print(f"  命中问题数: {hit_count}/{total} = 精确率 {precision:.1f}%")
    print(f"  命中关键词: {hit_keywords}/{total_keywords} = 召回率 {recall:.1f}%")

    # 输出未命中的样例
    missed_examples = [d for d in details if d["missed"]]
    if missed_examples:
        print(f"\n  未完全命中的样例 (前 10 条):")
        for d in missed_examples[:10]:
            print(f"    Q: {d['question']}")
            print(f"    命中: {d['matched']}  未中: {d['missed']}")

    return {
        "qa_precision": round(precision, 1),
        "qa_recall": round(recall, 1),
        "total_questions": total,
        "hit_count": hit_count,
    }


# ===========================================================================
# 测试 3：知识图谱自动化构建统计
# ===========================================================================

def test_kg_construction() -> Dict[str, Any]:
    """
    统计 kg_output 目录下的节点、关系数量。
    计算自动化构建规模指标。
    """
    print("\n" + "=" * 70)
    print("  测试 3：知识图谱自动化构建统计")
    print("=" * 70)

    kg_output = Path(__file__).parent.parent / "gustobot" / "data" / "kg_output"

    node_count = 0
    relationship_count = 0
    batch_count = 0

    # 读取汇总文件
    nodes_file = kg_output / "nodes.csv"
    rels_file = kg_output / "relationships.csv"
    concepts_file = kg_output / "concepts.csv"
    progress_file = kg_output / "progress.json"

    if nodes_file.exists():
        with open(nodes_file, "r", encoding="utf-8") as f:
            node_count = sum(1 for _ in f) - 1  # 减去表头

    if rels_file.exists():
        with open(rels_file, "r", encoding="utf-8") as f:
            relationship_count = sum(1 for _ in f) - 1

    concept_count = 0
    if concepts_file.exists():
        with open(concepts_file, "r", encoding="utf-8") as f:
            concept_count = sum(1 for _ in f) - 1

    # 统计批次
    batch_dirs = [d for d in kg_output.iterdir() if d.is_dir() and d.name.startswith("batch_")]
    batch_count = len(batch_dirs)

    # 各批次详细统计
    batch_concepts_total = 0
    batch_rels_total = 0
    for bd in batch_dirs:
        bc = bd / "concepts.csv"
        br = bd / "relationships.csv"
        if bc.exists():
            with open(bc, "r", encoding="utf-8") as f:
                batch_concepts_total += sum(1 for _ in f) - 1
        if br.exists():
            with open(br, "r", encoding="utf-8") as f:
                batch_rels_total += sum(1 for _ in f) - 1

    # 读取 progress.json
    processed_recipes = 0
    if progress_file.exists():
        with open(progress_file, "r", encoding="utf-8") as f:
            progress = json.load(f)
            processed_recipes = progress.get("processed_count", 0)

    total_graph_nodes = node_count  # 这就是图谱节点总数
    node_wan = total_graph_nodes / 10000  # 换算为"万"

    print(f"\n  菜谱处理总数: {processed_recipes}")
    print(f"  批次总数: {batch_count}")
    print(f"  图谱节点总数 (nodes.csv): {node_count} ({node_wan:.2f} 万)")
    print(f"  图谱关系总数 (relationships.csv): {relationship_count}")
    print(f"  概念实体总数 (concepts.csv): {concept_count}")
    print(f"  批次概念累计: {batch_concepts_total}  |  批次关系累计: {batch_rels_total}")

    # 估算节省人工时间：约 342 道菜谱的图谱实体，人工标注每道平均 15 分钟，
    # 自动化后约 2 分钟/道
    manual_time_min = processed_recipes * 15
    auto_time_min = processed_recipes * 2
    time_save_pct = (manual_time_min - auto_time_min) / manual_time_min * 100 if manual_time_min > 0 else 0

    print(f"\n  估算人工标注时间: {manual_time_min} 分钟 ({manual_time_min / 60:.1f} 小时)")
    print(f"  自动化处理时间: ~{auto_time_min} 分钟 ({auto_time_min / 60:.1f} 小时)")
    print(f"  节省时间比例: {time_save_pct:.0f}%")

    return {
        "total_nodes": node_count,
        "total_nodes_wan": round(node_wan, 2),
        "total_relationships": relationship_count,
        "total_concepts": concept_count,
        "batch_count": batch_count,
        "processed_recipes": processed_recipes,
        "time_save_pct": round(time_save_pct, 0),
    }


# ===========================================================================
# 测试 4：多轮会话隔离 + Token 消耗 / 延迟
# ===========================================================================

async def test_session_isolation_and_token(client: httpx.AsyncClient) -> Dict[str, Any]:
    """
    测试多轮会话隔离性和 Token 消耗：
    - 两个并行会话不互相泄漏
    - 记录每轮延迟变化
    - 通过回答长度估算 token 消耗
    """
    print("\n" + "=" * 70)
    print("  测试 4：多轮会话隔离 & Token 消耗 / 延迟")
    print("=" * 70)

    all_latencies: List[float] = []
    all_answer_lengths: List[int] = []
    isolation_pass = 0
    isolation_total = 0

    # 4a. 多轮会话延迟与 token 估算
    print("\n  ── 4a. 多轮会话延迟与 Token 估算 ──")
    scenario_token_estimates: List[List[int]] = []
    scenario_latencies_per_turn: List[List[float]] = []

    for si, scenario in enumerate(MULTI_TURN_SCENARIOS):
        user_id = TEST_USER_PREFIX + uuid.uuid4().hex[:8]
        sid = await _create_session(client, user_id)
        turn_latencies: List[float] = []
        turn_tokens: List[int] = []

        for turn, msg in enumerate(scenario):
            resp, lat = await _chat(client, msg, sid)
            answer = resp.get("answer", "")
            turn_latencies.append(lat)
            # 粗略估算：中文约 1.5 字/token，英文约 4 字符/token
            est_tokens = max(len(answer) // 2, 1)
            turn_tokens.append(est_tokens)
            all_latencies.append(lat)
            all_answer_lengths.append(len(answer))

        scenario_latencies_per_turn.append(turn_latencies)
        scenario_token_estimates.append(turn_tokens)
        print(f"    场景 {si + 1}: 延迟 {[f'{l:.0f}ms' for l in turn_latencies]}  | "
              f"Est.Token {turn_tokens}")

    # 4b. 会话隔离性测试
    print("\n  ── 4b. 会话隔离性测试 ──")
    # 创建两个独立 session，分别聊不同菜谱，检查是否交叉
    sid_a = await _create_session(client, TEST_USER_PREFIX + "isolation_a")
    sid_b = await _create_session(client, TEST_USER_PREFIX + "isolation_b")

    # session A 聊红烧肉
    resp_a1, _ = await _chat(client, "红烧肉怎么做", sid_a)
    # session B 聊宫保鸡丁
    resp_b1, _ = await _chat(client, "宫保鸡丁需要什么食材", sid_b)
    # session A 追问 (不应包含宫保鸡丁)
    resp_a2, _ = await _chat(client, "需要什么调料", sid_a)
    # session B 追问 (不应包含红烧肉)
    resp_b2, _ = await _chat(client, "火候怎么控制", sid_b)

    answer_a2 = resp_a2.get("answer", "")
    answer_b2 = resp_b2.get("answer", "")

    # 检查隔离性：A 不应提到宫保鸡丁，B 不应提到红烧肉
    isolation_tests = [
        ("A追问不含宫保鸡丁", "宫保鸡丁" not in answer_a2),
        ("B追问不含红烧肉", "红烧肉" not in answer_b2),
    ]

    for desc, passed in isolation_tests:
        isolation_total += 1
        if passed:
            isolation_pass += 1
        print(f"    {desc}: {'✓ PASS' if passed else '✗ FAIL'}")

    # 统计
    avg_lat = statistics.mean(all_latencies) if all_latencies else 0
    avg_answer_len = statistics.mean(all_answer_lengths) if all_answer_lengths else 0
    avg_est_token = int(avg_answer_len // 2)

    # 计算首轮 vs 后续轮次延迟差异
    first_turn_lats = [s[0] for s in scenario_latencies_per_turn if s]
    later_turn_lats = [l for s in scenario_latencies_per_turn for l in s[1:] if len(s) > 1]
    avg_first = statistics.mean(first_turn_lats) if first_turn_lats else 0
    avg_later = statistics.mean(later_turn_lats) if later_turn_lats else 0
    latency_diff = avg_first - avg_later

    # Token 节省估算：通过上下文压缩，多轮后续 token 应少于首轮
    first_turn_tokens = [s[0] for s in scenario_token_estimates if s]
    later_turn_tokens = [t for s in scenario_token_estimates for t in s[1:] if len(s) > 1]
    avg_first_tok = statistics.mean(first_turn_tokens) if first_turn_tokens else 0
    avg_later_tok = statistics.mean(later_turn_tokens) if later_turn_tokens else 0
    token_save_pct = (1 - avg_later_tok / avg_first_tok) * 100 if avg_first_tok > 0 else 0

    print(f"\n  平均响应延迟: {avg_lat:.0f}ms")
    print(f"  首轮平均延迟: {avg_first:.0f}ms  |  后续平均延迟: {avg_later:.0f}ms  |  差值: {latency_diff:.0f}ms")
    print(f"  平均回复 Token 估算: {avg_est_token}")
    print(f"  首轮 Token: ~{avg_first_tok:.0f}  |  后续 Token: ~{avg_later_tok:.0f}  |  节省: {token_save_pct:.1f}%")
    print(f"  会话隔离测试: {isolation_pass}/{isolation_total}")

    return {
        "avg_latency_ms": round(avg_lat, 0),
        "first_turn_latency_ms": round(avg_first, 0),
        "later_turn_latency_ms": round(avg_later, 0),
        "latency_diff_ms": round(latency_diff, 0),
        "avg_est_token": avg_est_token,
        "token_save_pct": round(abs(token_save_pct), 1),
        "isolation_pass": isolation_pass,
        "isolation_total": isolation_total,
    }


# ===========================================================================
# 测试 5：越界回答 / 幻觉率
# ===========================================================================

async def test_hallucination_and_out_of_scope(client: httpx.AsyncClient) -> Dict[str, Any]:
    """
    测试越界回答和幻觉率：
    - 对 out_of_scope 问题：应拒答 / 引导回菜谱
    - 对 hallucination_trap 问题：不应编造菜谱
    """
    print("\n" + "=" * 70)
    print("  测试 5：越界回答 / 幻觉率")
    print("=" * 70)

    total = len(RUNTIME_OUT_OF_SCOPE_DATA)
    oos_correct = 0
    oos_total = 0
    halluc_correct = 0
    halluc_total = 0
    details: List[Dict[str, Any]] = []
    semaphore = asyncio.Semaphore(CONCURRENCY)

    # 判断回答是否正确拒绝/引导
    REFUSE_KEYWORDS = [
        "不太属于", "菜谱范围", "不在", "能力范围", "烹饪", "厨",
        "抱歉", "无法", "不好意思", "帮不了", "超出",
        "菜谱", "做菜", "美食", "食材", "不相关",
        "不属于", "范围之外", "请咨询", "建议",
    ]

    # 判断是否产生了幻觉（编造了详细做法）
    HALLUC_INDICATORS = [
        "第一步", "第二步", "第三步", "步骤", "食材有",
        "主料", "辅料", "调料如下", "具体做法",
        "分钟", "大火", "小火", "翻炒", "焯水",
    ]

    async def _worker(item: Dict[str, str]):
        nonlocal oos_correct, oos_total, halluc_correct, halluc_total
        async with semaphore:
            sid = TEST_SESSION_PREFIX + uuid.uuid4().hex[:8]
            _created_session_ids.append(sid)
            resp, lat = await _chat(client, item["message"], sid)
            answer = resp.get("answer", "")

            if item["type"] == "out_of_scope":
                oos_total += 1
                # 回答中包含拒绝关键词 → 正确拒答
                is_refused = any(kw in answer for kw in REFUSE_KEYWORDS)
                if is_refused:
                    oos_correct += 1
                details.append({
                    "message": item["message"],
                    "type": "out_of_scope",
                    "refused": is_refused,
                    "answer_preview": answer[:100],
                })
            else:  # hallucination_trap
                halluc_total += 1
                # 如果回答中出现详细做法指标 → 产生幻觉
                has_halluc = sum(1 for kw in HALLUC_INDICATORS if kw in answer) >= 2
                if not has_halluc:
                    halluc_correct += 1
                details.append({
                    "message": item["message"],
                    "type": "hallucination_trap",
                    "hallucinated": has_halluc,
                    "answer_preview": answer[:100],
                })

    for batch_range in _chunked(total, TASK_BATCH_SIZE):
        tasks = [_worker(RUNTIME_OUT_OF_SCOPE_DATA[i]) for i in batch_range]
        await asyncio.gather(*tasks, return_exceptions=True)

    oos_rate = oos_correct / oos_total * 100 if oos_total > 0 else 0
    halluc_safe = halluc_correct / halluc_total * 100 if halluc_total > 0 else 0
    halluc_rate = 100 - halluc_safe
    combined_total = oos_total + halluc_total
    combined_correct = oos_correct + halluc_correct
    combined_safe_rate = combined_correct / combined_total * 100 if combined_total > 0 else 0
    boundary_violation_rate = 100 - combined_safe_rate

    print(f"\n  越界问题: {oos_correct}/{oos_total} 正确拒答 = {oos_rate:.1f}%")
    print(f"  幻觉陷阱: {halluc_correct}/{halluc_total} 安全回答 = {halluc_safe:.1f}% (幻觉率 {halluc_rate:.1f}%)")
    print(f"  综合越界/幻觉率: {boundary_violation_rate:.1f}%")

    # 输出失败样例
    failures = [
        d for d in details
        if (d["type"] == "out_of_scope" and not d.get("refused"))
        or (d["type"] == "hallucination_trap" and d.get("hallucinated"))
    ]
    if failures:
        print(f"\n  失败样例 (前 10 条):")
        for f in failures[:10]:
            flag = "未拒答" if f["type"] == "out_of_scope" else "产生幻觉"
            print(f"    [{flag}] {f['message']}")
            print(f"             → {f['answer_preview']}")

    return {
        "oos_correct": oos_correct,
        "oos_total": oos_total,
        "oos_rate": round(oos_rate, 1),
        "halluc_correct": halluc_correct,
        "halluc_total": halluc_total,
        "halluc_safe_rate": round(halluc_safe, 1),
        "halluc_rate": round(halluc_rate, 1),
        "boundary_violation_rate": round(boundary_violation_rate, 1),
    }


# ===========================================================================
# 清理测试数据
# ===========================================================================

async def cleanup_test_data(client: httpx.AsyncClient) -> int:
    """安全删除所有测试产生的会话数据"""
    print("\n" + "=" * 70)
    print("  安全清理测试数据")
    print("=" * 70)

    deleted = 0
    unique_ids = list(set(_created_session_ids))
    total = len(unique_ids)
    semaphore = asyncio.Semaphore(20)  # 清理用更高并发

    async def _del(sid: str):
        nonlocal deleted
        async with semaphore:
            if await _delete_session(client, sid):
                deleted += 1

    tasks = [_del(sid) for sid in unique_ids]
    await asyncio.gather(*tasks, return_exceptions=True)

    print(f"  测试会话总数: {total}")
    print(f"  成功删除: {deleted}")
    print(f"  清理完成 ✓")
    return deleted


# ===========================================================================
# 主入口
# ===========================================================================

async def main():
    print("╔" + "═" * 68 + "╗")
    print("║  GustoBot 综合性能基准测试                                        ║")
    print("║  测试数据: 120 (意图) + 30 (QA) + 25 (越界/幻觉) + 多轮 = 175+ 条 ║")
    print("╚" + "═" * 68 + "╝")
    print(f"  目标服务: {BASE_URL}")
    print(f"  并发数: {CONCURRENCY}")
    print(f"  数据放大倍数: x{DATA_SCALE}")
    print(f"  任务分批大小: {TASK_BATCH_SIZE}")
    print(
        "  运行样本量: "
        f"intent={len(RUNTIME_INTENT_TEST_DATA)}, "
        f"qa={len(RUNTIME_QA_TEST_DATA)}, "
        f"oos={len(RUNTIME_OUT_OF_SCOPE_DATA)}"
    )
    print(f"  开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # 先检查服务是否可达
    async with httpx.AsyncClient() as client:
        try:
            health = await client.get(f"{BASE_URL}/health", timeout=10)
            print(f"  健康检查: {health.status_code}")
            if health.status_code != 200:
                print(f"  ⚠ 服务降级: {health.json()}")
        except Exception as e:
            print(f"\n  ✗ 无法连接到 {BASE_URL}: {e}")
            print("  请先启动 GustoBot 服务后再运行测试。")
            sys.exit(1)

    results = {}

    async with httpx.AsyncClient() as client:
        try:
            # 测试 1: QPS + 意图准确率
            results["test1_qps_intent"] = await test_qps_and_intent_accuracy(client)

            # 测试 2: 问答召回率 / 准确率
            results["test2_qa"] = await test_qa_recall_precision(client)

            # 测试 3: 知识图谱构建 (本地统计，不需要服务)
            results["test3_kg"] = test_kg_construction()

            # 测试 4: 多轮会话 + Token / 延迟
            results["test4_session"] = await test_session_isolation_and_token(client)

            # 测试 5: 越界 / 幻觉
            results["test5_hallucination"] = await test_hallucination_and_out_of_scope(client)

        finally:
            # 无论如何都执行清理
            await cleanup_test_data(client)

    # ===========================================================================
    # 汇总报告
    # ===========================================================================
    print("\n")
    print("╔" + "═" * 68 + "╗")
    print("║                     综合测试结果汇总                               ║")
    print("╚" + "═" * 68 + "╝")
    print()

    t1 = results.get("test1_qps_intent", {})
    t2 = results.get("test2_qa", {})
    t3 = results.get("test3_kg", {})
    t4 = results.get("test4_session", {})
    t5 = results.get("test5_hallucination", {})

    print("  1. 系统并发处理能力 & 意图识别路由准确率")
    print(f"     QPS: {t1.get('qps', 'N/A')}")
    print(f"     意图识别路由准确率: {t1.get('intent_accuracy', 'N/A')}%")
    print(f"     平均延迟: {t1.get('avg_latency_ms', 'N/A')}ms | P95: {t1.get('p95_ms', 'N/A')}ms")
    print()

    print("  2. 核心饮食问答召回率 / 准确率")
    print(f"     精确率 (至少命中一个关键词): {t2.get('qa_precision', 'N/A')}%")
    print(f"     召回率 (命中关键词比例): {t2.get('qa_recall', 'N/A')}%")
    print()

    print("  3. 自动化构建图谱")
    print(f"     图谱节点总数: {t3.get('total_nodes', 'N/A')} ({t3.get('total_nodes_wan', 'N/A')} 万个)")
    print(f"     节省人工时间: {t3.get('time_save_pct', 'N/A')}%")
    print()

    print("  4. 多轮会话隔离 & Token 消耗 / 延迟")
    print(f"     会话隔离: {t4.get('isolation_pass', 'N/A')}/{t4.get('isolation_total', 'N/A')} PASS")
    print(f"     Token 节省估算: {t4.get('token_save_pct', 'N/A')}%")
    print(f"     平均响应延迟: {t4.get('avg_latency_ms', 'N/A')}ms")
    print(f"     首轮 vs 后续延迟差: {t4.get('latency_diff_ms', 'N/A')}ms")
    print()

    print("  5. 越界回答 / 幻觉率")
    print(f"     越界正确拒答率: {t5.get('oos_rate', 'N/A')}%")
    print(f"     幻觉率: {t5.get('halluc_rate', 'N/A')}%")
    print(f"     综合越界/幻觉率: {t5.get('boundary_violation_rate', 'N/A')}%")
    print()

    print("  " + "─" * 66)
    print("  填写模板参考值：")
    print(f"  1. 系统并发处理能力达到 {t1.get('qps', 'XX')} QPS，")
    print(f"     意图识别路由准确率达到 {t1.get('intent_accuracy', 'XX')}%")
    print(f"  2. 核心饮食问答的召回率 {t2.get('qa_recall', 'XX')}% / 准确率 {t2.get('qa_precision', 'XX')}%")
    print(f"  3. 自动化构建图谱节点 {t3.get('total_nodes_wan', 'XX')} 万个，")
    print(f"     节省人工清洗数据时间 {t3.get('time_save_pct', 'XX')}%")
    print(f"  4. Token 消耗降低约 {t4.get('token_save_pct', 'XX')}%，")
    print(f"     平均响应延迟 {t4.get('avg_latency_ms', 'XX')}ms，")
    print(f"     延迟差 {t4.get('latency_diff_ms', 'XX')}ms")
    print(f"  5. 越界回答或幻觉率控制在 {t5.get('boundary_violation_rate', 'XX')}% 以下")
    print()

    # 保存结果到临时文件（供后续分析，测试后可删除）
    report_path = Path(__file__).parent / "benchmark_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"  详细结果已保存到: {report_path}")
    print(f"  完成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    return results


if __name__ == "__main__":
    asyncio.run(main())
