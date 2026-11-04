#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Regenerate the Chase-Lev n=30k comparison CSVs used by the dataset report.

The benchmark package is not vendored into the report directory.  Point
KV_BENCH at the extracted ``KV_Scheduling_Benchmark_WS`` directory, or put it
next to this project as ``../../benchmark_student/KV_Scheduling_Benchmark_WS``.

    python run_cl_compare.py

Outputs (under dataset_test/results/):
  chaselev_k0.csv          probe=0.00, policies fifo/local/steal/steal_cl
  chaselev_k0_probe005.csv probe=0.05, policies local/steal/steal_cl
  *_summary.csv            median/min/max over the three seeds
"""
import csv
import os
import sys
from statistics import median

HERE = os.path.dirname(os.path.abspath(__file__))
BENCH = os.environ.get("KV_BENCH") or os.path.abspath(
    os.path.join(HERE, "..", "..", "benchmark_student", "KV_Scheduling_Benchmark_WS")
)
if not os.path.isdir(os.path.join(BENCH, "kvsched")):
    raise SystemExit(f"benchmark package not found: {BENCH}; set KV_BENCH")
sys.path.insert(0, BENCH)

from kvsched.sim import simulate  # noqa: E402
from kvsched.workload import generate  # noqa: E402

CASES = [
    "T1_C", "T1_B", "T1_A", "T2_UNIFORM", "T2_ZIPF090", "T2_ZIPF099",
    "T3_STATIC", "T3_DYNAMIC", "T3_SHUFFLED", "T4_SMALL", "T4_K10", "T4_K100",
    "T4_K1000", "T5_BG0", "T5_BG10", "T5_BG25", "T5_BG10_FIXED", "T5_BG25_FIXED",
]
SEEDS = (0, 1, 2)
N = 30000
OUT = os.path.join(HERE, "results")

FIELDS = [
    "case", "policy", "seed", "foreground_mean_latency", "foreground_p50",
    "foreground_p95", "foreground_p99", "foreground_p999", "steal_count",
    "steal_probe_count", "worker_migration_count", "probe_cost",
]


def run(name, policies, probe):
    rows = []
    for case in CASES:
        for seed in SEEDS:
            trace = generate(case, N, seed, 0.70, 8, 100000, 32)
            for policy in policies:
                kwargs = {"steal_probe": probe}
                if policy == "steal_cl":
                    kwargs.update(steal_threshold=0, steal_owner="lifo")
                r = simulate(trace, policy, **kwargs)
                rows.append({
                    "case": case, "policy": policy, "seed": seed,
                    "foreground_mean_latency": r["foreground_mean_latency"],
                    "foreground_p50": r["foreground_p50"],
                    "foreground_p95": r["foreground_p95"],
                    "foreground_p99": r["foreground_p99"],
                    "foreground_p999": r["foreground_p999"],
                    "steal_count": r["steal_count"],
                    "steal_probe_count": r["steal_probe_count"],
                    "worker_migration_count": r["worker_migration_count"],
                    "probe_cost": probe,
                })
        print(name, case, "done", flush=True)

    path = os.path.join(OUT, name + ".csv")
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)

    # summary: median/min/max per (case, policy)
    groups = {}
    for r in rows:
        groups.setdefault((r["case"], r["policy"]), []).append(r)
    fields = ["case", "policy", "seeds"]
    for metric in ("foreground_mean_latency", "foreground_p99",
                   "foreground_p999", "steal_count", "steal_probe_count"):
        fields += [metric + "_median", metric + "_min", metric + "_max"]
    with open(os.path.join(OUT, name + "_summary.csv"), "w", newline="",
              encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for (case, policy), rs in sorted(groups.items()):
            row = {"case": case, "policy": policy, "seeds": len(rs)}
            for metric in ("foreground_mean_latency", "foreground_p99",
                           "foreground_p999", "steal_count", "steal_probe_count"):
                vals = [float(r[metric]) for r in rs if r[metric] not in (None, "")]
                if not vals:
                    row[metric + "_median"] = ""
                    row[metric + "_min"] = ""
                    row[metric + "_max"] = ""
                    continue
                row[metric + "_median"] = median(vals)
                row[metric + "_min"] = min(vals)
                row[metric + "_max"] = max(vals)
            w.writerow(row)
    print("wrote", path, len(rows), "rows", flush=True)


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    run("chaselev_k0", ("fifo", "local", "steal", "steal_cl"), 0.0)
    run("chaselev_k0_probe005", ("local", "steal", "steal_cl"), 0.05)