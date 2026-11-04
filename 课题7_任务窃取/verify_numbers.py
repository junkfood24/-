#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Consistency checks for the numbers quoted in the report and code document.

Usage:
    python verify_numbers.py

Checks (all standard library, no third-party packages):
  * simulation accounting: completed + dropped == arrivals, window <= total
  * every simulated percentile is <= makespan
  * throughput_mops is the fixed-window rate, drain_mops is completed/makespan
  * table 13 / table 14 / affinity numbers match results/*.json
  * C++ 3-round medians match table 16, and every C++ percentile <= makespan
"""
import json
import re
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RES = ROOT / "results"
failures = []


def check(cond, msg):
    if not cond:
        failures.append(msg)
        print("FAIL:", msg)


def close(a, b, tol=0.051):
    return abs(float(a) - float(b)) <= tol


main = json.loads((RES / "sim_main.json").read_text(encoding="utf-8"))
rows = {(r["workload"], r["policy"]): r for r in main["rows"]}
expected = {
    ("uniform", "fifo"): (154.7, 0.696, 0.0, 16),
    ("uniform", "local"): (880.0, 0.696, 0.0, 82),
    ("uniform", "ws"): (229.1, 0.696, 0.0, 29),
    ("skew", "fifo"): (172.1, 0.696, 0.0, 15),
    ("skew", "local"): (759390.3, 0.497, 10.0, 64489),
    ("skew", "ws"): (251.7, 0.696, 0.0, 22),
    ("dynamic", "fifo"): (186.4, 0.697, 0.0, 15),
    ("dynamic", "local"): (764707.5, 0.483, 12.8, 62777),
    ("dynamic", "ws"): (252.3, 0.697, 0.0, 19),
}
for key, (p99, tput, drop, backlog) in expected.items():
    r = rows[key]
    label = "/".join(key)
    check(close(r["p99_us"], p99), f"{label} P99 {r['p99_us']} != {p99}")
    check(close(r["throughput_mops"], tput), f"{label} throughput {r['throughput_mops']} != {tput}")
    check(close(r["drop_rate"], drop), f"{label} drop {r['drop_rate']} != {drop}")
    check(r["backlog_at_horizon"] == backlog,
          f"{label} backlog {r['backlog_at_horizon']} != {backlog}")
    check(r["completed"] + r["dropped"] == r["arrivals"], f"{label} accounting")
    check(r["window_completed"] <= r["completed"], f"{label} window > completed")
    check(r["p999_us"] <= r["makespan_us"], f"{label} P99.9 > makespan")
    check(r["p99_us"] <= r["makespan_us"], f"{label} P99 > makespan")
    check(close(r["throughput_mops"], r["window_completed"] / main["config"]["horizon"]),
          f"{label} throughput formula")
    check(close(r["drain_mops"], r["completed"] / r["makespan_us"]),
          f"{label} drain formula")

sweep = json.loads((RES / "sim_sweep.json").read_text(encoding="utf-8"))
sweep_expected = {
    1: (222.0, 450.6), 2: (251.7, 373.5), 4: (328.7, 330.2),
    8: (534.2, 304.2), 16: (1085.9, 291.7), 32: (2261.4, 286.6),
    64: (4368.0, 285.2),
}
for r in sweep:
    p99, spk = sweep_expected[r["thresh"]]
    check(close(r["p99_us"], p99), f"sweep k={r['thresh']} P99 {r['p99_us']} != {p99}")
    check(close(r["steals_per_k"], spk), f"sweep k={r['thresh']} steals/k != {spk}")
    check(r["p999_us"] <= r["makespan_us"], f"sweep k={r['thresh']} P99.9 > makespan")

aff = json.loads((RES / "sim_affinity.json").read_text(encoding="utf-8"))
aff_expected = {
    ("uniform", "ws_random"): (251.8, 10.5),
    ("uniform", "ws_affinity"): (236.1, 4.2),
    ("skew", "ws_random"): (284.2, 23.3),
    ("skew", "ws_affinity"): (276.1, 19.7),
}
for r in aff:
    p99, remote = aff_expected[(r["workload"], r["mode"])]
    check(close(r["p99_us"], p99), f"affinity {r['workload']}/{r['mode']} P99")
    check(close(r["remote_pct"], remote), f"affinity {r['workload']}/{r['mode']} remote")

# C++ log: parse 3 rounds per workload and check medians / percentile bounds.
LOG = RES / "bench_rounds.log"
pat = re.compile(
    r"^=== (\w+) round (\d) ===\n"
    r"tasks=.*?\npolicy.*?\n"
    r"fifo\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+(\d+)\n"
    r"local\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+(\d+)\n"
    r"ws\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+(\d+)\n"
    r"checksum OK", re.M)
text = LOG.read_text(encoding="utf-8")
found = {}
for m in pat.finditer(text):
    workload, rnd = m.group(1), int(m.group(2))
    vals = list(map(float, m.groups()[2:]))
    policies = {}
    for i, pol in enumerate(("fifo", "local", "ws")):
        fields = vals[i * 6:(i + 1) * 6]
        policies[pol] = fields
        check(fields[3] <= fields[0] * 1000,
              f"C++ {workload} r{rnd} {pol} P99 > makespan")
        check(fields[4] <= fields[0] * 1000,
              f"C++ {workload} r{rnd} {pol} P99.9 > makespan")
    found[(workload, rnd)] = policies

for workload in ("uniform", "skew"):
    for rnd in (1, 2, 3):
        check((workload, rnd) in found, f"missing C++ {workload} round {rnd}")
    for pol in ("fifo", "local", "ws"):
        med = statistics.median(found[(workload, r)][pol][0] for r in (1, 2, 3))
        expected_ms = {"uniform": {"fifo": 772.0, "local": 495.0, "ws": 516.5},
                       "skew": {"fifo": 571.7, "local": 1326.2, "ws": 511.4}}[workload][pol]
        check(close(med, expected_ms, 0.051),
              f"C++ median {workload}/{pol} {med} != {expected_ms}")
    checksums = {int(found[(workload, r)][p][5]) for r in (1, 2, 3)
                 for p in ("fifo", "local", "ws")}
    check(len(checksums) == 1, f"C++ {workload} checksums differ: {checksums}")

print(f"checked {len(rows)} main rows, {len(sweep)} sweep points, "
      f"{len(aff)} affinity points, {len(found)} C++ rounds")
if failures:
    print(f"{len(failures)} FAILURE(S)")
    raise SystemExit(1)
print("ALL CHECKS PASSED")