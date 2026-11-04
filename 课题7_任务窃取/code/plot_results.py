#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""由 sim_main.json / sim_sweep.json / sim_affinity.json 生成报告插图。"""

import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.ticker import FuncFormatter

plt.rcParams.update({
    "font.family": ["Microsoft YaHei"],
    "axes.unicode_minus": False,
    "font.size": 10.5,
    "axes.titlesize": 12,
    "axes.labelsize": 10.5,
    "figure.dpi": 200,
    "savefig.dpi": 200,
    "savefig.bbox": "tight",
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": True,
    "grid.alpha": 0.25,
    "grid.linestyle": "--",
    "legend.frameon": False,
})

HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, "..", "results")
FIG = os.path.join(HERE, "..", "fig")
os.makedirs(FIG, exist_ok=True)

COLORS = {"fifo": "#4C72B0", "local": "#DD8452", "ws": "#55A868"}
LABELS = {"fifo": "集中式 FIFO", "local": "本地队列", "ws": "工作窃取"}
WORK = {"uniform": "均匀访问", "skew": "偏斜访问", "dynamic": "动态热点"}


def load(name):
    with open(os.path.join(RES, name), encoding="utf-8") as f:
        return json.load(f)


def fmt_us(v):
    if v >= 1000:
        return f"{v/1000:.1f} ms"
    return f"{v:.0f} µs"


def fig_overview(main):
    rows = {(r["policy"], r["workload"]): r for r in main["rows"]}
    kinds = ["uniform", "skew", "dynamic"]
    fig, axes = plt.subplots(1, 2, figsize=(10.6, 4.0))
    x = np.arange(len(kinds))
    w = 0.26

    ax = axes[0]
    for i, p in enumerate(["fifo", "local", "ws"]):
        vals = [rows[(p, k)]["throughput_mops"] for k in kinds]
        b = ax.bar(x + (i - 1) * w, vals, w, label=LABELS[p],
                   color=COLORS[p], edgecolor="white", linewidth=0.6)
        for rect, v in zip(b, vals):
            ax.text(rect.get_x() + rect.get_width() / 2, v + 0.012,
                    f"{v:.2f}", ha="center", va="bottom", fontsize=8.2)
    ax.set_xticks(x, [WORK[k] for k in kinds])
    ax.set_ylabel("吞吐率（Mtask/s）")
    ax.set_ylim(0, 0.83)
    ax.set_title("(a) 吞吐率：偏斜负载下本地队列塌陷")
    ax.legend(loc="upper right", ncol=1, fontsize=9)

    ax = axes[1]
    for i, p in enumerate(["fifo", "local", "ws"]):
        vals = [rows[(p, k)]["p99_us"] for k in kinds]
        b = ax.bar(x + (i - 1) * w, vals, w, label=LABELS[p],
                   color=COLORS[p], edgecolor="white", linewidth=0.6)
        for rect, v in zip(b, vals):
            ax.text(rect.get_x() + rect.get_width() / 2, v * 1.25,
                    fmt_us(v), ha="center", va="bottom", fontsize=7.6,
                    rotation=90 if v > 10000 else 0)
    ax.set_yscale("log")
    ax.set_xticks(x, [WORK[k] for k in kinds])
    ax.set_ylabel("P99 延迟（µs，对数轴）")
    ax.set_ylim(80, 5e6)
    ax.set_title("(b) P99：窃取以少量尾延迟换取负载均衡")
    fig.tight_layout()
    fig.savefig(os.path.join(FIG, "fig1_overview.png"))
    plt.close(fig)


def fig_cdf(main):
    cdf = main["cdf"]
    fig, ax = plt.subplots(figsize=(7.0, 4.2))
    for p in ["fifo", "local", "ws"]:
        data = np.array(cdf[f"skew|{p}"])
        ax.plot(data[:, 1], data[:, 0] * 100, color=COLORS[p],
                label=LABELS[p], linewidth=1.9)
    ax.set_xscale("log")
    ax.set_xlabel("端到端延迟（µs，对数轴）")
    ax.set_ylabel("累计比例（%）")
    ax.set_ylim(49, 100)
    ax.set_xlim(10, 2e6)
    ax.axvline(1000, color="#888888", linestyle=":", linewidth=1)
    ax.text(1100, 55, "1 ms", color="#666666", fontsize=9)
    ax.set_title("偏斜访问下的延迟分布（P50–P99.99）")
    ax.legend(loc="lower right")
    fig.tight_layout()
    fig.savefig(os.path.join(FIG, "fig2_cdf_skew.png"))
    plt.close(fig)


def fig_dynamic(main):
    rows = {(r["policy"], r["workload"]): r for r in main["rows"]}
    fig, ax = plt.subplots(figsize=(7.4, 4.2))
    for p in ["local", "ws"]:
        bins = rows[(p, "dynamic")]["bins"]
        xy = np.array(bins)
        ax.step(xy[:, 0], xy[:, 1], where="mid", color=COLORS[p],
                label=LABELS[p], linewidth=1.8)
    ax.set_xlabel("时间（ms）")
    ax.set_ylabel("每 10 ms 完成任务数")
    ax.set_title("动态热点（热点分片每 25 ms 轮换）下的吞吐时序")
    ax.legend(loc="lower right")
    ax.set_xlim(0, 700)
    fig.tight_layout()
    fig.savefig(os.path.join(FIG, "fig3_dynamic.png"))
    plt.close(fig)


def fig_threshold(sweep):
    th = [r["thresh"] for r in sweep]
    p99 = [r["p99_us"] for r in sweep]
    steals = [r["steals_per_k"] for r in sweep]
    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    ax.plot(th, p99, "o-", color=COLORS["ws"], linewidth=2, label="P99")
    ax.set_xscale("log", base=2)
    ax.set_yscale("log")
    ax.set_xticks(th, [str(t) for t in th])
    ax.set_xlabel("窃取阈值 k（受害者队列长度 > k 才允许窃取）")
    ax.set_ylabel("P99 延迟（µs，对数轴）")
    ax2 = ax.twinx()
    ax2.plot(th, steals, "s--", color="#8172B3", linewidth=1.6,
             label="每千任务窃取次数")
    ax2.set_ylabel("每千任务窃取次数", color="#8172B3")
    ax2.tick_params(axis="y", colors="#8172B3")
    ax2.grid(False)
    ax2.spines["right"].set_visible(True)
    ax.set_title("窃取阈值：尾延迟与迁移开销的权衡（偏斜访问）")
    lines = ax.get_lines() + ax2.get_lines()
    ax.legend(lines, [l.get_label() for l in lines], loc="upper left")
    fig.tight_layout()
    fig.savefig(os.path.join(FIG, "fig4_threshold.png"))
    plt.close(fig)


def fig_affinity(aff):
    fig, ax = plt.subplots(figsize=(7.0, 4.0))
    kinds = ["uniform", "skew"]
    modes = ["ws_random", "ws_affinity"]
    labels = {"ws_random": "随机窃取", "ws_affinity": "亲和感知窃取"}
    colors = {"ws_random": "#DD8452", "ws_affinity": "#55A868"}
    x = np.arange(len(kinds))
    w = 0.32
    for i, m in enumerate(modes):
        vals = [next(r for r in aff if r["workload"] == k and r["mode"] == m)["p99_us"]
                for k in kinds]
        rem = [next(r for r in aff if r["workload"] == k and r["mode"] == m)["remote_pct"]
               for k in kinds]
        b = ax.bar(x + (i - 0.5) * w, vals, w, color=colors[m], label=labels[m],
                   edgecolor="white", linewidth=0.6)
        for rect, v, rr in zip(b, vals, rem):
            ax.text(rect.get_x() + rect.get_width() / 2, v + 12,
                    f"{v:.0f} µs\n远程 {rr:.0f}%", ha="center", va="bottom",
                    fontsize=8.2)
    ax.set_xticks(x, [WORK[k] for k in kinds])
    ax.set_ylabel("P99 延迟（µs）")
    ax.set_ylim(0, 420)
    ax.set_title("NUMA 亲和感知窃取：远程执行比例与尾延迟", pad=12)
    ax.legend(loc="upper right", ncol=1)
    fig.tight_layout()
    fig.savefig(os.path.join(FIG, "fig5_affinity.png"))
    plt.close(fig)


if __name__ == "__main__":
    main = load("sim_main.json")
    sweep = load("sim_sweep.json")
    aff = load("sim_affinity.json")
    fig_overview(main)
    fig_cdf(main)
    fig_dynamic(main)
    fig_threshold(sweep)
    fig_affinity(aff)
    print("figures written to", os.path.abspath(FIG))