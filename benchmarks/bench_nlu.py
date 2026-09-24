"""
Script Benchmark đo lường độ trễ thực tế của Fast-Path NLU (V2.1).
Thực thi kiểm thử hiệu năng trên phần cứng thực tế (Arch Linux / CPU).
"""

import sys
import os
import time
import statistics
import json

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from ai_assistant.core.nlu import fast_path_nlu
from ai_assistant.tools.apps import build_app_index

BENCHMARK_COMMANDS = [
    # 1. Âm lượng & Độ sáng
    "tăng âm lượng 20%",
    "giảm âm lượng",
    "tắt tiếng",
    "bật tiếng",
    "tăng độ sáng màn hình",
    "giảm độ sáng",
    # 2. Kết nối & Phần cứng
    "bật wifi",
    "tắt bluetooth",
    "chế độ turbo",
    "chế độ im lặng",
    "pin còn bao nhiêu",
    "kiểm tra ram",
    # 3. Thời gian & Thông tin
    "bây giờ là mấy giờ",
    "hôm nay ngày mấy",
    "thời tiết hà nội thế nào",
    # 4. Quản lý Ứng dụng & Cửa sổ
    "mở visual studio code",
    "mở google chrome",
    "đóng cửa sổ",
    "phóng to màn hình",
    # 5. Công cụ Lập trình viên
    "giải phóng cổng 8080",
    "kiểm tra trạng thái git",
    "kiểm tra docker",
    "phiên bản java",
    # 6. Hẹn giờ
    "hẹn giờ 5 phút",
    "hủy hẹn giờ"
]

def run_benchmark(iterations: int = 200) -> dict:
    print(f"🚀 Bắt đầu Benchmark Fast-Path NLU ({len(BENCHMARK_COMMANDS)} câu lệnh x {iterations} vòng = {len(BENCHMARK_COMMANDS) * iterations} lượt đo)...")

    app_index = build_app_index()

    # Warmup
    for cmd in BENCHMARK_COMMANDS[:5]:
        _ = fast_path_nlu(cmd, app_index, dry_run=True)

    latencies_us = []

    for _ in range(iterations):
        for cmd in BENCHMARK_COMMANDS:
            t0 = time.perf_counter_ns()
            _ = fast_path_nlu(cmd, app_index, dry_run=True)
            t1 = time.perf_counter_ns()
            latencies_us.append((t1 - t0) / 1000.0)  # microsecond

    latencies_ms = [us / 1000.0 for us in latencies_us]
    sorted_ms = sorted(latencies_ms)
    n = len(sorted_ms)

    mean_ms = statistics.mean(sorted_ms)
    median_ms = statistics.median(sorted_ms)
    stdev_ms = statistics.stdev(sorted_ms) if n > 1 else 0.0
    min_ms = sorted_ms[0]
    max_ms = sorted_ms[-1]
    p90_ms = sorted_ms[int(n * 0.90)]
    p95_ms = sorted_ms[int(n * 0.95)]
    p99_ms = sorted_ms[int(n * 0.99)]
    throughput_qps = 1000.0 / mean_ms if mean_ms > 0 else 0

    results = {
        "total_queries": n,
        "unique_commands": len(BENCHMARK_COMMANDS),
        "iterations": iterations,
        "throughput_qps": round(throughput_qps, 1),
        "mean_ms": round(mean_ms, 3),
        "median_ms": round(median_ms, 3),
        "stdev_ms": round(stdev_ms, 3),
        "min_ms": round(min_ms, 3),
        "max_ms": round(max_ms, 3),
        "p90_ms": round(p90_ms, 3),
        "p95_ms": round(p95_ms, 3),
        "p99_ms": round(p99_ms, 3)
    }

    print("\n" + "="*50)
    print("       KẾT QUẢ BENCHMARK FAST-PATH NLU (REAL)")
    print("="*50)
    print(f"Tổng số lượt thực thi : {n:,}")
    print(f"Thông lượng (Throughput): {results['throughput_qps']:,} queries/sec")
    print(f"Thời gian trung bình  : {results['mean_ms']} ms")
    print(f"Trung vị (Median)     : {results['median_ms']} ms")
    print(f"P90 Latency           : {results['p90_ms']} ms")
    print(f"P95 Latency           : {results['p95_ms']} ms")
    print(f"P99 Latency           : {results['p99_ms']} ms")
    print(f"Min / Max Latency     : {results['min_ms']} ms / {results['max_ms']} ms")
    print("="*50)

    # Lưu kết quả
    out_dir = os.path.dirname(__file__)
    out_file = os.path.join(out_dir, "results_nlu.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"📁 Kết quả chi tiết đã được lưu tại: {out_file}\n")

    return results

if __name__ == "__main__":
    run_benchmark(iterations=200)
