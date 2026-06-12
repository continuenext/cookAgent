"""只运行测试 4 和测试 5，复用 test_benchmark 中的逻辑"""
import asyncio
import sys
from datetime import datetime

import httpx

# 复用主测试模块中的组件
from tests.test_benchmark import (
    BASE_URL,
    TIMEOUT,
    _created_session_ids,
    cleanup_test_data,
    test_hallucination_and_out_of_scope,
    test_session_isolation_and_token,
)


async def main():
    print(f"  开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  目标服务: {BASE_URL}")
    print(f"  超时: {TIMEOUT}s")

    async with httpx.AsyncClient() as client:
        try:
            health = await client.get(f"{BASE_URL}/health", timeout=10)
            print(f"  健康检查: {health.status_code}")
        except Exception as e:
            print(f"  无法连接: {e}")
            sys.exit(1)

    results = {}
    async with httpx.AsyncClient() as client:
        try:
            print("\n>>> 运行测试 4...")
            results["test4"] = await test_session_isolation_and_token(client)
            print("\n>>> 运行测试 5...")
            results["test5"] = await test_hallucination_and_out_of_scope(client)
        except Exception as e:
            print(f"\n  异常: {e}")
            import traceback
            traceback.print_exc()
        finally:
            await cleanup_test_data(client)

    t4 = results.get("test4", {})
    t5 = results.get("test5", {})

    print("\n" + "=" * 60)
    print("  测试 4 结果汇总:")
    print(f"    会话隔离: {t4.get('isolation_pass', 'N/A')}/{t4.get('isolation_total', 'N/A')}")
    print(f"    Token 节省: {t4.get('token_save_pct', 'N/A')}%")
    print(f"    平均延迟: {t4.get('avg_latency_ms', 'N/A')}ms")
    print(f"    首轮延迟: {t4.get('first_turn_latency_ms', 'N/A')}ms")
    print(f"    后续延迟: {t4.get('later_turn_latency_ms', 'N/A')}ms")
    print(f"    延迟差: {t4.get('latency_diff_ms', 'N/A')}ms")

    print("\n  测试 5 结果汇总:")
    print(f"    越界拒答率: {t5.get('oos_rate', 'N/A')}%")
    print(f"    幻觉率: {t5.get('halluc_rate', 'N/A')}%")
    print(f"    综合越界/幻觉率: {t5.get('boundary_violation_rate', 'N/A')}%")
    print(f"\n  完成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == "__main__":
    asyncio.run(main())
