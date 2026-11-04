#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
课题 7 任务窃取调度 —— 离散事件仿真器
=====================================

对比三种调度策略：
  fifo    : 集中式 FIFO 队列（全局一把锁，任意空闲线程取队首）
  local   : 每核本地队列（线程只服务自己的分片，不跨核）
  ws      : 每核本地双端队列 + 工作窃取（owner 底部 LIFO，thief 顶部 FIFO）
  ws_aff  : 工作窃取 + NUMA 亲和感知（优先偷同节点队列）

工作负载：
  uniform : 键均匀分布到 64 个分片
  skew    : Zipf(θ=1.1) 偏斜，少数分片承担大部分请求
  dynamic : 热点分片每 25 ms 轮换一次（动态热点）

用法：
  python sim_ws.py --quick
  python sim_ws.py --out ../results/sim_main.json --figdir ../fig
"""

import argparse
import heapq
import json
import math
import os
import random
from collections import deque

import numpy as np

# ----------------------------------------------------------------------------
# 全局模型参数（与报告第 6 章一致）
# ----------------------------------------------------------------------------
P = 20                      # 工作线程数
NODE_OF = np.array([0] * 10 + [1] * 10, dtype=np.int64)   # 2 个 NUMA 节点
SHARDS = 80                 # 分片数（= 20 核 × 4，保证每核负载基数一致）
OWNER = np.array([s % P for s in range(SHARDS)])          # 分片属主
CAP = 32768                 # 每队列容量（有界队列，满则丢弃/背压）
MEAN_SVC = 20.0             # 基础服务时间均值，微秒
SIGMA = 0.5                 # 对数正态形状参数
LONG_FRAC = 0.01            # 长任务比例（如 compaction 切片）
LONG_MEAN = 300.0           # 长任务平均服务时间，微秒
STEAL_COST = 1.0            # 一次窃取（CAS + 缓存冷启动）的额外开销，微秒
FIFO_OVERHEAD = 0.3         # 集中式队列每次操作的争用开销，微秒
LOCAL_OVERHEAD = 0.02       # 本地队列操作开销，微秒
THRESH = 2                  # 默认窃取阈值：受害者队列长度 > THRESH 才偷
PROBES = 8                  # 每次空闲最多随机探测的受害者数量
HORIZON = 500000.0          # 仿真时长，微秒
UTIL = 0.8                  # 目标利用率


# ----------------------------------------------------------------------------
# 负载生成
# ----------------------------------------------------------------------------
def zipf_weights(n, theta=1.1):
    w = 1.0 / np.power(np.arange(1, n + 1, dtype=np.float64), theta)
    return w / w.sum()


def sample_services(rng, n):
    base = rng.lognormal(mean=math.log(MEAN_SVC) - 0.5 * SIGMA ** 2,
                         sigma=SIGMA, size=n)
    n_long = int(round(n * LONG_FRAC))
    if n_long:
        idx = rng.choice(n, size=n_long, replace=False)
        base[idx] += rng.uniform(0.6 * LONG_MEAN, 1.4 * LONG_MEAN, n_long)
    return base


def build_workload(kind, lam, horizon, rng):
    """返回 (times, shards, services) 三个 numpy 数组，按时间升序。"""
    if kind == "dynamic":
        times, shards = [], []
        weights = zipf_weights(SHARDS)
        hot_cycle = [0, 7, 3, 19, 11, 42, 5, 28]
        step = 25000.0
        t, seg = 0.0, 0
        while t < horizon:
            end = min(t + step, horizon)
            n = rng.poisson(lam * (end - t))
            if n > 0:
                ts = np.sort(rng.uniform(t, end, n))
                w = weights.copy()
                w[hot_cycle[seg % len(hot_cycle)]] *= 3.0
                w /= w.sum()
                sh = np.searchsorted(np.cumsum(w), rng.random(n))
                times.append(ts)
                shards.append(np.minimum(sh, SHARDS - 1))
            t = end
            seg += 1
        times = np.concatenate(times) if times else np.empty(0)
        shards = np.concatenate(shards) if shards else np.empty(0, dtype=np.int64)
    else:
        n = rng.poisson(lam * horizon)
        times = np.sort(rng.uniform(0.0, horizon, n))
        if kind == "uniform":
            shards = rng.integers(0, SHARDS, n)
        elif kind == "skew":
            w = zipf_weights(SHARDS)
            shards = np.minimum(np.searchsorted(np.cumsum(w), rng.random(n)),
                                SHARDS - 1)
        else:
            raise ValueError(kind)
    services = sample_services(rng, len(times))
    return times, shards.astype(np.int64), services


# ----------------------------------------------------------------------------
# 调度仿真
# ----------------------------------------------------------------------------
class Metrics:
    def __init__(self, horizon, bin_width=10000.0):
        self.horizon = horizon
        self.bin_width = bin_width
        self.lat = []
        self.comp = []
        self.completed = 0
        self.dropped = 0
        self.steals = 0
        self.remote = 0
        self.bins = {}

    def add(self, arr, comp, worker=None, owner=None):
        self.lat.append(comp - arr)
        self.comp.append(comp)
        if self.bin_width > 0:
            b = int(comp / self.bin_width)
            self.bins[b] = self.bins.get(b, 0) + 1
        if worker is not None and owner is not None and NODE_OF[worker] != NODE_OF[owner]:
            self.remote += 1

    def summary(self):
        lat = np.asarray(self.lat, dtype=np.float64)
        comp = np.asarray(self.comp, dtype=np.float64)
        makespan_us = float(comp.max()) if comp.size else 0.0
        qs = [0.5, 0.9, 0.99, 0.999]
        pct = np.percentile(lat, np.array(qs) * 100.0) if lat.size else np.zeros(4)
        bins = [[k * self.bin_width / 1000.0, self.bins[k]]
                for k in sorted(self.bins)] if self.bins else []
        return {
            "completed": int(self.completed),
            "dropped": int(self.dropped),
            "makespan_us": makespan_us,
            "throughput_mops": (self.completed / (makespan_us / 1e6) / 1e6) if makespan_us > 0 else 0.0,
            "mean_us": float(lat.mean()) if lat.size else 0.0,
            "p50_us": float(pct[0]), "p90_us": float(pct[1]),
            "p99_us": float(pct[2]), "p999_us": float(pct[3]),
            "steals": int(self.steals),
            "steals_per_k": (self.steals / max(1, self.completed)) * 1000.0,
            "remote_pct": (100.0 * self.remote / max(1, self.completed)),
            "bins": bins,
        }

    def cdf(self, points=300):
        lat = np.asarray(self.lat, dtype=np.float64)
        if not lat.size:
            return []
        qs = np.linspace(0.5, 0.9999, points)
        return [[float(q), float(v)] for q, v in zip(qs, np.quantile(lat, qs))]


def make_idle_helpers():
    idle = set(range(P))
    ilist = list(range(P))

    def take():
        while ilist:
            w = ilist.pop()
            if w in idle:
                idle.remove(w)
                return w
        return -1

    def put(w):
        if w not in idle:
            idle.add(w)
            ilist.append(w)

    return idle, take, put


def simulate_fifo(times, shards, services, rng):
    m = Metrics(HORIZON)
    q = deque()
    heap = []
    idle, take, put = make_idle_helpers()

    n = len(times)
    for i in range(n):
        t = float(times[i])
        while heap and heap[0][0] <= t:
            ft, w = heapq.heappop(heap)
            if q:
                arr, sv, sh = q.popleft()
                c = ft + sv
                m.add(arr, c)
                m.completed += 1
                heapq.heappush(heap, (c, w))
            else:
                put(w)
        sv = float(services[i]) + FIFO_OVERHEAD
        sh = int(shards[i])
        if idle:
            w = take()
            if w >= 0:
                c = t + sv
                m.add(t, c)
                m.completed += 1
                heapq.heappush(heap, (c, w))
            elif len(q) < CAP:
                q.append((t, sv, sh))
            else:
                m.dropped += 1
        elif len(q) < CAP:
            q.append((t, sv, sh))
        else:
            m.dropped += 1

    while heap:
        ft, w = heapq.heappop(heap)
        if q:
            arr, sv, sh = q.popleft()
            c = ft + sv
            m.add(arr, c)
            m.completed += 1
            heapq.heappush(heap, (c, w))
        else:
            put(w)
    return m


def simulate_local(times, shards, services):
    m = Metrics(HORIZON)
    pending = [deque() for _ in range(P)]     # 每个队列存完成时间
    for i in range(len(times)):
        t = float(times[i])
        w = int(OWNER[int(shards[i])])
        q = pending[w]
        while q and q[0] <= t:
            q.popleft()
        if len(q) >= CAP:
            m.dropped += 1
            continue
        start = max(t, q[-1] if q else t)
        c = start + float(services[i]) + LOCAL_OVERHEAD
        q.append(c)
        m.add(t, c)
        m.completed += 1
    return m


def simulate_ws(times, shards, services, rng, thresh=THRESH,
                remote_pen=0.0, affinity=False):
    m = Metrics(HORIZON)
    deques = [deque() for _ in range(P)]
    heap = []
    idle, take, put = make_idle_helpers()
    node_peers = [[w for w in range(P) if NODE_OF[w] == nd] for nd in (0, 1)]

    def pick_thief(owner):
        if affinity:
            peers = [w for w in node_peers[int(NODE_OF[owner])] if w in idle]
            if peers:
                return peers[rng.randrange(len(peers))]
        w = take()
        return w

    def probe_victims(w):
        order = []
        if affinity:
            mine = [v for v in node_peers[int(NODE_OF[w])] if v != w]
            other = [v for v in range(P) if NODE_OF[v] != NODE_OF[w]]
            rng.shuffle(mine)
            rng.shuffle(other)
            order = mine + other
        else:
            order = list(range(P))
            rng.shuffle(order)
        for v in order[:PROBES * 2]:
            if v != w and len(deques[v]) > thresh:
                return v
        return -1

    def execute(w, sv, sh, arr, now, stolen):
        nonlocal_steals = 0
        if stolen and remote_pen > 0.0 and NODE_OF[w] != NODE_OF[OWNER[sh]]:
            sv = sv * (1.0 + remote_pen)
        c = now + sv + (STEAL_COST if stolen else 0.0) + LOCAL_OVERHEAD
        m.add(arr, c, w, int(OWNER[sh]))
        m.completed += 1
        heapq.heappush(heap, (c, w))
        return nonlocal_steals

    n = len(times)
    for i in range(n):
        t = float(times[i])
        while heap and heap[0][0] <= t:
            ft, w = heapq.heappop(heap)
            if deques[w]:
                sv, sh, arr = deques[w].pop()          # owner: 底部 LIFO
                execute(w, sv, sh, arr, ft, False)
                continue
            v = probe_victims(w)
            if v >= 0:
                sv, sh, arr = deques[v].popleft()      # thief: 顶部 FIFO
                m.steals += 1
                execute(w, sv, sh, arr, ft, True)
            else:
                put(w)

        sv, sh = float(services[i]), int(shards[i])
        ow = int(OWNER[sh])
        if ow in idle:
            idle.remove(ow)
            execute(ow, sv, sh, t, t, False)
            continue
        if len(deques[ow]) >= CAP:
            m.dropped += 1
            continue
        deques[ow].append((sv, sh, t))
        if idle and len(deques[ow]) >= thresh:
            th = pick_thief(ow)
            if th >= 0:
                sv2, sh2, arr2 = deques[ow].popleft()
                m.steals += 1
                execute(th, sv2, sh2, arr2, t, True)

    while heap:
        ft, w = heapq.heappop(heap)
        if deques[w]:
            sv, sh, arr = deques[w].pop()
            execute(w, sv, sh, arr, ft, False)
            continue
        v = probe_victims(w)
        if v >= 0:
            sv, sh, arr = deques[v].popleft()
            m.steals += 1
            execute(w, sv, sh, arr, ft, True)
        else:
            put(w)

    # 兜底：若仍有残留（探测失败而进入空闲），唤醒空闲线程继续偷
    leftover = sum(len(d) for d in deques)
    guard = 0
    while leftover and guard < 10 * P:
        guard += 1
        w = take()
        if w < 0:
            break
        v = max(range(P), key=lambda x: len(deques[x]))
        if len(deques[v]) == 0:
            put(w)
            break
        sv, sh, arr = deques[v].popleft()
        m.steals += 1
        execute(w, sv, sh, arr, float(times[-1]) if n else 0.0, True)
        while heap:
            ft, ww = heapq.heappop(heap)
            if deques[ww]:
                sv, sh, arr = deques[ww].pop()
                execute(ww, sv, sh, arr, ft, False)
            else:
                put(ww)
        leftover = sum(len(d) for d in deques)
    return m


# ----------------------------------------------------------------------------
# 实验脚本
# ----------------------------------------------------------------------------
def run_main(out_path, seed=20261104, horizon=HORIZON):
    cap = P / (MEAN_SVC + LONG_FRAC * LONG_MEAN) * 1e6     # 每秒任务数
    lam = UTIL * cap / 1e6                                  # 每微秒任务数
    print(f"[main] capacity≈{cap/1e6:.2f} Mtask/s, offered≈{lam*1e6:.2f} Mtask/s")
    rows = []
    curves = {}
    for kind in ("uniform", "skew", "dynamic"):
        rng = np.random.default_rng(seed)
        times, shards, services = build_workload(kind, lam, horizon, rng)
        print(f"[main] {kind}: {len(times)} tasks")
        for policy in ("fifo", "local", "ws"):
            r = random.Random(seed)
            if policy == "fifo":
                m = simulate_fifo(times, shards, services, r)
            elif policy == "local":
                m = simulate_local(times, shards, services)
            else:
                m = simulate_ws(times, shards, services, r)
            s = m.summary()
            s.update(policy=policy, workload=kind, seed=seed)
            rows.append(s)
            curves[f"{kind}|{policy}"] = m.cdf()
            print(f"  {policy:6s} tput={s['throughput_mops']:.3f} M/s "
                  f"drop={100.0*s['dropped']/max(1,s['completed']+s['dropped']):5.1f}% "
                  f"P99={s['p99_us']:8.1f}us P99.9={s['p999_us']:9.1f}us")
    out = {"config": {"P": P, "shards": SHARDS, "capacity_cap": cap, "lambda": lam,
                      "horizon": horizon, "thresh": THRESH, "seed": seed,
                      "steal_cost_us": STEAL_COST, "fifo_overhead_us": FIFO_OVERHEAD},
           "rows": rows, "cdf": curves}
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    return out


def run_sweep(out_path, seed=20261104):
    cap = P / (MEAN_SVC + LONG_FRAC * LONG_MEAN) * 1e6
    lam = UTIL * cap / 1e6
    rng = np.random.default_rng(seed)
    times, shards, services = build_workload("skew", lam, HORIZON, rng)
    rows = []
    for th in (1, 2, 4, 8, 16, 32, 64):
        r = random.Random(seed)
        m = simulate_ws(times, shards, services, r, thresh=th)
        s = m.summary()
        s.update(thresh=th)
        rows.append(s)
        print(f"[sweep] thresh={th:3d} tput={s['throughput_mops']:.3f} "
              f"P99={s['p99_us']:8.1f} P99.9={s['p999_us']:9.1f} "
              f"steals/k={s['steals_per_k']:.1f}")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=1)
    return rows


def run_affinity(out_path, seed=20261104):
    cap = P / (MEAN_SVC + LONG_FRAC * LONG_MEAN) * 1e6
    lam = UTIL * cap / 1e6
    rows = []
    for kind in ("uniform", "skew"):
        rng = np.random.default_rng(seed)
        times, shards, services = build_workload(kind, lam, HORIZON, rng)
        for mode, aff in (("ws_random", False), ("ws_affinity", True)):
            r = random.Random(seed)
            m = simulate_ws(times, shards, services, r, remote_pen=0.35, affinity=aff)
            s = m.summary()
            s.update(mode=mode, workload=kind)
            rows.append(s)
            print(f"[aff] {kind:7s} {mode:12s} tput={s['throughput_mops']:.3f} "
                  f"P99={s['p99_us']:8.1f} remote={s['remote_pct']:5.1f}%")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=1)
    return rows


def run_quick():
    rng = np.random.default_rng(1)
    times, shards, services = build_workload("uniform", 0.1, 50000.0, rng)
    print("tasks:", len(times))
    for pol in ("fifo", "local", "ws"):
        r = random.Random(1)
        m = {"fifo": lambda: simulate_fifo(times, shards, services, r),
             "local": lambda: simulate_local(times, shards, services),
             "ws": lambda: simulate_ws(times, shards, services, r)}[pol]()
        print(pol, json.dumps(m.summary(), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--out", default=os.path.join(os.path.dirname(__file__),
                                                  "..", "results", "sim_main.json"))
    ap.add_argument("--figdir", default="")
    args = ap.parse_args()
    if args.quick:
        run_quick()
    else:
        base = os.path.dirname(os.path.abspath(args.out))
        run_main(args.out)
        run_sweep(os.path.join(base, "sim_sweep.json"))
        run_affinity(os.path.join(base, "sim_affinity.json"))
        print("done")