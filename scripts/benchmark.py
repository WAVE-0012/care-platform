"""使用临时表比较社区月度查询的执行计划、逻辑读和耗时。"""
import json
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from care.db import connect


def run():
    conn = connect()
    cursor = conn.cursor()
    cursor.execute(
        "CREATE TABLE #order_benchmark(id int PRIMARY KEY,community_id int,scheduled_at datetime2(0),status varchar(16),settlement decimal(12,2),padding char(180))"
    )
    cursor.execute(
        "WITH n AS(SELECT TOP(100000) ROW_NUMBER() OVER(ORDER BY (SELECT NULL)) id FROM sys.all_objects a CROSS JOIN sys.all_objects b) INSERT #order_benchmark SELECT id,id%100+1,DATEADD(day,id%730,'20240101'),CASE WHEN id%3=0 THEN 'pending' ELSE 'completed' END,CAST(id%100+10 AS decimal(12,2)),REPLICATE('x',180) FROM n"
    )
    query = "SELECT COUNT(*) count,SUM(settlement) amount FROM #order_benchmark WHERE community_id=37 AND scheduled_at>='20250101' AND scheduled_at<'20250201' AND status='completed'"

    def measure(label):
        timings = []
        for _ in range(7):
            started = time.perf_counter()
            cursor.execute(query)
            values = tuple(cursor.fetchone())
            timings.append((time.perf_counter() - started) * 1000)
        cursor.execute("SET STATISTICS IO ON")
        cursor.execute(query)
        cursor.fetchall()
        messages = [m[1] for m in cursor.messages]
        cursor.execute("SET STATISTICS IO OFF")
        cursor.execute("SET STATISTICS XML ON")
        cursor.execute(query)
        cursor.fetchall()
        cursor.nextset()
        plan = cursor.fetchval()
        cursor.execute("SET STATISTICS XML OFF")
        (ROOT / f"docs/evidence/plan-{label}.sqlplan").write_text(
            plan, encoding="utf-8"
        )
        return {
            "median_ms": round(statistics.median(timings[1:]), 3),
            "runs_ms": [round(t, 3) for t in timings],
            "result": [str(v) for v in values],
            "statistics_io": messages,
            "operators": sorted(
                set(__import__("re").findall(r'PhysicalOp="([^"]+)"', plan))
            ),
        }

    before = measure("before")
    cursor.execute(
        "CREATE INDEX IX_benchmark_community_date ON #order_benchmark(community_id,scheduled_at) INCLUDE(status,settlement)"
    )
    after = measure("after")
    assert before["result"] == after["result"]
    result = {
        "rows": 100000,
        "table": "#order_benchmark",
        "query": query,
        "before": before,
        "after": after,
        "method": "每阶段7次，第1次预热；报告后6次中位数。临时表测试，无并行用户负载。",
    }
    (ROOT / "docs/evidence/query-benchmark.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    conn.rollback()
    conn.close()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    run()
