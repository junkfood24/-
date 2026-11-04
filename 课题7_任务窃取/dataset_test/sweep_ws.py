"""Sweep the Chase-Lev policy variant against the benchmark's own steal policy."""
import csv
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from kvsched.sim import simulate
from kvsched.workload import generate

CASES = ["T1_A", "T2_ZIPF099", "T3_DYNAMIC", "T4_K100", "T5_BG10"]
SEEDS = [0, 1, 2]
N = 20000
OUT = os.path.join(HERE, "results", "ws_sweep.csv")
SUM = os.path.join(HERE, "results", "ws_sweep_summary.csv")

CONFIGS = [
    ("fifo", None, None, 0.0),
    ("local", None, None, 0.0),
    ("steal", None, None, 0.0),
    ("steal_cl", "lifo", 0, 0.0),
    ("steal_cl", "lifo", 1, 0.0),
    ("steal_cl", "lifo", 2, 0.0),
    ("steal_cl", "lifo", 4, 0.0),
    ("steal_cl", "lifo", 8, 0.0),
    ("steal_cl", "fifo", 0, 0.0),
    ("steal_cl", "fifo", 2, 0.0),
    ("steal", None, None, 0.05),
    ("steal_cl", "lifo", 0, 0.05),
    ("steal_cl", "lifo", 2, 0.05),
    ("steal_cl", "lifo", 4, 0.05),
]

FIELDS = [
    "case", "seed", "policy", "owner", "threshold", "probe_cost",
    "p99", "mean", "qmax", "steals", "steal_probes", "migrations", "drain", "cpu_skew",
]

rows = []
for case in CASES:
    for seed in SEEDS:
        tr = generate(case, N, seed, 0.70, 8, 100000, 32)
        for policy, owner, k, probe in CONFIGS:
            kwargs = dict(steal_probe=probe)
            if policy == "steal_cl":
                kwargs.update(steal_threshold=k, steal_owner=owner)
            r = simulate(tr, policy, **kwargs)
            row = {
                "case": case, "seed": seed, "policy": policy,
                "owner": owner or "-", "threshold": k if k is not None else "-",
                "probe_cost": probe,
                "p99": r["foreground_p99"],
                "mean": r["foreground_mean_latency"],
                "qmax": r["ready_queue_peak"],
                "steals": r["steal_count"],
                "steal_probes": r["steal_probe_count"],
                "migrations": r["worker_migration_count"],
                "drain": r["drain_time_after_last_arrival"],
                "cpu_skew": r["cpu_util_skew"],
            }
            rows.append(row)
        print(case, "seed", seed, "done", flush=True)

with open(OUT, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=FIELDS)
    w.writeheader()
    w.writerows(rows)

# median across seeds per configuration
from statistics import median

groups = {}
for r in rows:
    key = (r["case"], r["policy"], r["owner"], r["threshold"], r["probe_cost"])
    groups.setdefault(key, []).append(r)

summary = []
for key, rs in sorted(groups.items()):
    summary.append({
        "case": key[0], "policy": key[1], "owner": key[2], "threshold": key[3],
        "probe_cost": key[4],
        "p99_median": median(x["p99"] for x in rs),
        "mean_median": median(x["mean"] for x in rs),
        "qmax_median": median(x["qmax"] for x in rs),
        "steals_median": median(x["steals"] for x in rs),
        "probes_median": median(x["steal_probes"] for x in rs),
        "migrations_median": median(x["migrations"] for x in rs),
        "drain_median": median(x["drain"] for x in rs),
    })

with open(SUM, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(summary[0].keys()))
    w.writeheader()
    w.writerows(summary)

print("wrote", OUT, SUM, "rows", len(rows), "groups", len(summary))