#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build the KV benchmark dataset test report (DOCX)."""

import csv
import os
import sys
from statistics import median

from docx.shared import Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import docx_kit as K

BASE = os.path.join(HERE, "dataset_test")
RES = os.path.join(BASE, "results")
OUT = os.path.join(BASE, "KV数据集_任务窃取测试报告.docx")

MAIN_CASES = [
    "T1_C", "T1_B", "T1_A", "T2_UNIFORM", "T2_ZIPF090", "T2_ZIPF099",
    "T3_STATIC", "T3_DYNAMIC", "T3_SHUFFLED", "T4_SMALL", "T4_K10", "T4_K100",
    "T4_K1000", "T5_BG0", "T5_BG10", "T5_BG25", "T5_BG10_FIXED", "T5_BG25_FIXED",
]


def load(name):
    with open(os.path.join(RES, name), encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def pick(rows, case=None, policy=None, **filters):
    out = []
    for r in rows:
        if case is not None and r["case"] != case:
            continue
        if policy is not None and r["policy"] != policy:
            continue
        ok = True
        for key, want in filters.items():
            have = r.get(key)
            if isinstance(want, float):
                try:
                    if abs(float(have) - want) > 1e-9:
                        ok = False
                except (TypeError, ValueError):
                    ok = False
            elif str(have) != str(want):
                ok = False
            if not ok:
                break
        if ok:
            out.append(r)
    return out


def med(rows, field):
    return median(float(r[field]) for r in rows) if rows else float("nan")


def f2(x):
    return f"{x:,.2f}" if abs(x) >= 1000 else f"{x:.2f}"


def pct(x):
    return f"{x*100:.1f}%"


official = load("official_main.csv")
official_d1 = load("official_d1.csv")
cl0 = load("chaselev_k0.csv")
cl5 = load("chaselev_k0_probe005.csv")
sweep = load("threshold_sweep_summary.csv")

# ---------------------------------------------------------------- document
doc = K.setup("KV 调度 Benchmark 数据集测试 · 任务窃取")
doc.core_properties.title = "KV 调度 Benchmark 数据集测试：任务窃取与 Chase-Lev 变体"
doc.core_properties.author = "课题7 任务窃取小组"
doc.core_properties.subject = "KV_Scheduling_Benchmark_Student_20261104 数据集测试"

# cover
p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
p.paragraph_format.space_before = Pt(110)
r = p.add_run("KV 调度 Benchmark 数据集")
r.bold = True
r.font.size = Pt(26)
r.font.name = "SimHei"
r._element.rPr.rFonts.set(qn("w:eastAsia"), "SimHei")

p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
r = p.add_run("任务窃取（A5）测试与 Chase-Lev 变体评估")
r.bold = True
r.font.size = Pt(17)
r.font.name = "SimHei"
r._element.rPr.rFonts.set(qn("w:eastAsia"), "SimHei")

p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
p.paragraph_format.space_before = Pt(28)
r = p.add_run("数据集：KV_Scheduling_Benchmark_Student_20261104")
r.font.size = Pt(11)
r.font.color.rgb = K.GRAY

p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
r = p.add_run("课程项目“内存键值存储引擎中的轻量级任务调度优化”")
r.font.size = Pt(11)
r.font.color.rgb = K.GRAY

p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
p.paragraph_format.space_before = Pt(150)
r = p.add_run("2026 年 11 月 4 日")
r.font.size = Pt(11)

K.page_break()

# ---------------------------------------------------------------- abstract
K.h1("摘要")
K.body(
    "本文记录使用课程组提供的 KV 调度基准数据集（2026-11-04 版）对任务窃取（A5）进行的独立测试。"
    "测试分为三部分：先原样运行官方基准的全部自动化检查与主套件，确认数据与代码管线可用；"
    "再把 Chase-Lev 双端队列语义接入同一仿真引擎，作为 A5 的一个可比较变体；"
    "最后做阈值与探测成本敏感性实验，检查该变体在什么条件下值得采用。"
)
K.body(
    "主要结论如下。第一，把官方四种算法放在一起，P99 排名是 FIFO ≈ Priority > Steal ≫ Local："
    "FIFO 与 Priority 在 13/18 个场景并列最低，Priority 在 4 个 T5 场景略优，Steal 只在 T4_K100 胜出，"
    "Local 从未胜出。但这个排名是在调度、探测、迁移成本全为 0、全局队列没有锁竞争的模型下得到的，不能直接外推。"
    "第二，官方 A5（最长队列受害者、队尾窃取）相对 A4 本地队列显著降低前台 P99："
    "按 T1—T5 组均值，A5 的 P99 只有 A4 的 5.7%—24.8%，即降低 75%—94%。"
    "第三，同键热点 D1 中四种算法 P99 都约为 11 202，其中键依赖等待约 11 201，说明窃取无法突破同键串行上限，"
    "这与设计文档的预期一致。第四，Chase-Lev 变体在阈值 k=0、零探测成本时与最长队列策略基本持平"
    "（12/18 个场景不劣于或优于，平均 P99 比 0.983）；当每次探测计入 0.05 单位成本时，"
    "随机早停探测在 18/18 个场景全部优于最长队列（平均 0.853，最低 0.650）。"
)
K.body(
    "第五，也是最重要的修正：把阈值设为 k=2 在 8 worker、70% 负载下会造成严重退化，"
    "P99 达到最长队列策略的 2.5—3.2 倍。原因是该规模下就绪队列普遍只有 0—2 个任务，"
    "k=2 实际上关闭了大多数窃取。阈值必须随队列深度和 worker 数缩放，不能把 20 线程实验中的 k=2 直接搬到 8 线程。"
    "第六，owner 端 LIFO 与 FIFO 在本模型中没有稳定差异；该数据集不建模缓存、NUMA 与锁竞争，"
    "因此只能验证派发与尾延迟，不能验证 Chase-Lev 的局部性收益。"
)
K.body(
    "本文的所有数值都来自抽象服务时间单位的离散事件仿真，不是真实微秒，也不是真实 Redis/Memcached 压测。"
    "结果用于比较调度策略，不用于宣称硬件性能提升。"
)

K.h1("目录")
for line in [
    "1  数据集、被测算法与测试方法",
    "2  官方基线：A5 相对 A4 与四种算法总览",
    "3  Chase-Lev 变体：接入、阈值与全量结果",
    "4  探测成本敏感性",
    "5  讨论、对课题报告的修订建议与限制",
    "附录 A  复现命令",
    "附录 B  结果文件清单",
]:
    K.body(line, indent=False, after=2)
K.page_break()

# ---------------------------------------------------------------- 1
K.h1("1  数据集、被测算法与测试方法")

K.h2("1.1  数据集是什么")
K.body(
    "该数据集是一个单线程离散事件仿真器，用虚拟时间模拟 8 个 worker 执行 KV 请求。"
    "输入是开环泊松到达的请求轨迹（CSV），每行包含 id、到达时刻、GET/UPDATE、key、服务工作量、"
    "value 大小标签和热点阶段；输出是每个请求的等待、开始、完成时刻，以及队列、窃取、迁移和 CPU 利用率统计。"
    "它不连接真实数据库，也不测量真实缓存命中或网络时延。"
)
K.body(
    "主套件包含 T1—T5 共 18 个 Case，另有 D1 两个同键诊断 Case。T1 改变读写比例，T2 改变静态 Key 分布，"
    "T3 改变热点在时间上的位置，T4 引入 0.125% 的长请求（K=1/10/100/1000），"
    "T5 引入每 32 次 UPDATE 触发的后台维护工作。默认 8 worker、100 000 Key、目标前台负载 0.70、"
    "普通 GET 1.0 单位、UPDATE 1.4 单位。"
)

K.h2("1.2  四种算法与本文关注点")
K.body(
    "官方基准固定比较四种算法：A1 集中 FIFO、A3 固定两级优先级、A4 按 Key 稳定哈希的本地 FIFO、"
    "A5 本地队列加工作窃取。A5 的官方实现是“空闲 worker 扫描所有受害者，选择队列最长者，"
    "从该队列尾部取一个任务”，每次成功窃取按 c−1 次探测计费。"
)
K.body(
    "本文关注 A5，并在不改动原数据集的前提下，把 Chase-Lev 语义作为第五种策略 `steal_cl` 接入同一引擎："
    "owner 从自己队列的 bottom 取（LIFO），thief 从受害者 top 取（FIFO），受害者按随机顺序探测，"
    "仅当受害者队列长度大于阈值 k 时才窃取，成功时按实际探测次数计费。"
    "这样可以在完全相同的请求轨迹、Key 依赖门和统计口径下比较两种窃取策略。"
)

K.h2("1.3  测试环境与完整性检查")
K.body(
    "测试使用 Python 3.12.14，仅依赖标准库；机器为 20 逻辑处理器 Windows 工作站。"
    "原始数据集解压后先运行 `python -m unittest discover -s tests -v`，11 项测试全部通过；"
    "随后运行 `python run.py suite --preset main`，完成 18 Case × 3 seed × 4 算法 = 216 次仿真；"
    "D1 另跑 2 Case × 3 seed × 4 算法 = 24 次。轨迹的 SHA256 在生成、写盘、回放三个阶段一致，"
    "官方示例轨迹 `examples/T2_ZIPF099_1p5k.csv` 也能正常回放。"
)
K.body(
    "为接入 `steal_cl`，复制了一份数据集到 `KV_Scheduling_Benchmark_WS`，只修改 `kvsched/sim.py` 与 "
    "`kvsched/cli.py`，原始解压目录的源代码保持未改动，只新增结果 CSV。新增策略通过同一套单元测试，且不改变 fifo/priority/local/steal "
    "的任何行为；用相同 seed 重跑时，这四种策略的 P99 与官方结果逐项一致。"
)

# ---------------------------------------------------------------- 2
K.h1("2  官方基线：A5 相对 A4 与四种算法总览")
K.body(
    "表 1 是主套件 3 个 seed 的中位数。A4 是本地队列，A5 是最长队列受害者加队尾窃取；"
    "“A5/A4”小于 1 表示窃取降低了 P99。Qmax 是就绪队列峰值，steals 是成功窃取次数。"
)

official_rows = []
for case in MAIN_CASES:
    a4 = pick(official, case, "local")
    a5 = pick(official, case, "steal")
    p4 = med(a4, "foreground_p99")
    p5 = med(a5, "foreground_p99")
    official_rows.append([
        case, f2(p4), f2(p5), f"{p5/p4:.2f}",
        f"{med(a4, 'ready_queue_peak'):.0f}",
        f"{med(a5, 'ready_queue_peak'):.0f}",
        f"{med(a5, 'steal_count'):.0f}",
    ])

K.table(
    ["Case", "A4 P99", "A5 P99", "A5/A4", "A4 Qmax", "A5 Qmax", "steals"],
    official_rows,
    [3.2, 2.2, 2.2, 1.8, 2.2, 2.2, 2.2],
    caption_text="表 1  官方主套件：A4 本地队列与 A5 工作窃取的 P99（n=30 000，3 seeds，中位数）",
    font=8.6,
)

K.body(
    "按组汇总，A5/A4 的 P99 比均值分别为：T1 0.248、T2 0.129、T3 0.057、T4 0.187、T5 0.140。"
    "也就是说，在这套数据集上，窃取把本地队列的尾延迟压低了 75%—94%。"
)
K.body(
    "T2 与 T3 的差异最能说明问题。T2_ZIPF099 的 A4 P99 为 363.54，A5 为 2.06；"
    "T3_DYNAMIC 的 A4 P99 为 632.13，A5 为 2.05。静态热点和动态热点都会让固定哈希的本地队列严重倾斜，"
    "而 A5 能把尚未执行的就绪任务从过载队列搬到空闲 worker。T3_SHUFFLED 只有 12.11 对 1.97，"
    "因为它的 Key 在时间上被刻意打散，本地队列本来就没有那么严重的持续偏斜；这正好构成 T3 的对照。"
)
K.body(
    "T4 说明窃取的边界。T4_K1000 的 A4 P99 为 2 389.11，A5 为 690.60，确实大幅下降，"
    "但 690 仍远高于短请求的 1 单位服务量；原因是 A5 不能抢占已经在执行的长任务，"
    "P99 仍被长任务自身及其队头阻塞支配。T5 也类似：A5 把 T5_BG25 从 111.59 降到 12.13，"
    "但后台工作仍要与前台竞争 CPU，不能凭空消失。"
)
K.body(
    "T1 是负面对照。T1_C 没有写依赖，A4 的 P99 仍有 7.57，A5 为 1.91；"
    "差异来自哈希把不同 Key 分到不同本地队列后的随机不均衡，而不是读写比例本身。"
    "这也说明“本地队列”即使在 Uniform 下也可能因为有限样本的哈希方差而受损。"
)

K.h2("2.1  D1：窃取不能突破同键串行")
K.body(
    "D1 用 95% UPDATE、5% GET 制造同键写冲突。表 2 显示 D1_HOTKEY 下四种算法的 P99 都在 11 202 左右，"
    "其中键依赖等待约 11 201，队列峰值只有 3；A5 只发生了 22 次窃取，仍然没有改善。"
    "原因是 KeyGate 让同一 Key 的 UPDATE 必须串行，任务在依赖解除前不占用 worker，"
    "窃取只能搬动“已经就绪”的任务，不能把被依赖挡住的任务变并行。"
)

d1_rows = []
for case in ("D1_HOTKEY", "D1_SPREAD"):
    vals = {}
    for pol in ("fifo", "priority", "local", "steal"):
        rs = pick(official_d1, case, pol)
        vals[pol] = (med(rs, "foreground_p99"), med(rs, "foreground_key_wait_p99"),
                     med(rs, "ready_queue_peak"))
    d1_rows.append([
        case,
        f2(vals["fifo"][0]), f2(vals["priority"][0]), f2(vals["local"][0]), f2(vals["steal"][0]),
        f2(vals["steal"][1]), f"{vals['steal'][2]:.0f}",
    ])

K.table(
    ["Case", "FIFO", "Priority", "A4", "A5", "A5 键等待", "A5 Qmax"],
    d1_rows,
    [2.9, 2.2, 2.2, 2.2, 2.2, 2.8, 2.0],
    caption_text="表 2  D1 同键诊断：四种算法的 P99 都被 KeyGate 串行上限支配（n=10 000，3 seeds）",
    font=8.6,
)

K.body(
    "D1_SPREAD 则是同负载但 Key 分散的对照：A4 P99 为 12.06，A5 为 2.68，键等待为 0。"
    "两组一起说明：A5 的收益来自“可并行的就绪任务”，而不是“让同键写并行”。"
    "这一点应作为课题报告里工作窃取的适用边界明确写出。"
)

K.h2("2.2  四种算法总览：FIFO ≈ Priority > Steal ≫ Local")
K.body(
    "表 1 只比较了 A4 与 A5。数据集同时提供了 A1 集中 FIFO 与 A3 两级优先级；把四种算法放在一起，"
    "排名会发生变化。表 3 选 7 个代表场景，表 4 给出 T1—T5 的组平均 P99；所有数字都是 3 个 seed 的中位数。"
)

rep_specs = [
    ("T1_A", "FIFO/Priority 并列"),
    ("T2_ZIPF099", "Local 约 191× FIFO"),
    ("T3_DYNAMIC", "Local 约 333× FIFO"),
    ("T4_K100", "Steal 唯一胜出"),
    ("T4_K1000", "FIFO 明显胜"),
    ("T5_BG25_FIXED", "Priority 略胜"),
    ("D1_HOTKEY", "四种几乎相同"),
]
rep_rows = []
for case, note in rep_specs:
    src = official_d1 if case.startswith("D1") else official
    vals = [med(pick(src, case, p), "foreground_p99") for p in ("fifo", "priority", "local", "steal")]
    rep_rows.append([case] + [f2(v) for v in vals] + [note])

K.table(
    ["场景", "FIFO", "Priority", "Local", "Steal", "说明"],
    rep_rows,
    [3.0, 1.7, 1.8, 1.9, 1.8, 3.9],
    caption_text="表 3  四种算法的代表场景 P99（n=30 000，D1 为 n=10 000；3 seeds 中位数）",
    font=8.4,
)

K.body(
    "从全量 18 个主场景看，FIFO 与 Priority 在 13 个场景并列最低或完全同序；Priority 在 4 个 T5 后台场景略低；"
    "Steal 只在 T4_K100 一个场景最低；Local 一次都没有胜出。T1—T3 中 FIFO 的 P99 为 1.84—1.88，"
    "Steal 为 2.00—2.07（约 1.08—1.10 倍），Local 为 8.35—335.93；Local 在 T3_DYNAMIC 上达到 FIFO 的约 333 倍。"
)

group_rows = []
for group in ("T1", "T2", "T3", "T4", "T5"):
    sub = [c for c in MAIN_CASES if c.startswith(group)]
    vals = []
    for p in ("fifo", "priority", "local", "steal"):
        vals.append(sum(med(pick(official, c, p), "foreground_p99") for c in sub) / len(sub))
    group_rows.append([group] + [f2(v) for v in vals])

K.table(
    ["组", "FIFO", "Priority", "Local", "Steal"],
    group_rows,
    [2.2, 2.8, 2.8, 2.8, 2.8],
    caption_text="表 4  T1—T5 组平均 P99（各组内 Case 等权平均，n=30 000，3 seeds）",
    font=9.0,
)

K.body(
    "FIFO 的优势不是因为它“更会调度”，而是因为模型把全局队列的锁、缓存行竞争和派发成本都设成了 0。"
    "集中队列是晚绑定：哪个 worker 空出来，才从同一个队列取下一个任务，天然接近理想负载均衡。"
    "所以 FIFO 在这套数据上接近“免费的最优解”；这恰好是数据集最需要说明的边界，而不是 FIFO 在真实系统里一定最好。"
)
K.body(
    "Priority 在没有后台任务时与 FIFO 完全同序，因此 T1—T4 的 P99 逐项相同。T5 中它只把前台 P99 降低 2%—14%："
    "BG10 从 2.52 到 2.48，BG25 从 5.38 到 5.37，BG10_FIXED 从 2.58 到 2.50，BG25_FIXED 从 6.05 到 5.21。"
    "原因是后台份额只有 10%—25%、老化阈值 20，前台优先的空间有限；而且它是以推迟后台为代价的。"
    "30 000 请求下后台有效样本不足 1 000，后台 P99 按规则留空，因此本数据集无法评估这个代价。"
)
K.body(
    "Local 是早绑定：Key 经稳定哈希固定到某个 worker，热点 Key 把该本地队列压垮，而本地队列没有迁移手段。"
    "T1 均匀负载下它已经是 FIFO 的 4.4 倍（8.35 对 1.88），因为 30 000 个 Key 分到 8 个队列本身就有方差；"
    "T2 平均 70 倍、T3 平均 180 倍，T2_ZIPF099 和 T3_DYNAMIC 分别达到约 191 倍和 333 倍。"
    "这正是 Local 作为负面对照的意义：没有迁移，哈希偏斜会直接变成尾延迟。"
)
K.body(
    "Steal 是最好的去中心化方案，但不是整体最优。它把 T2_ZIPF099 从 363.54 修到 2.06、T3_DYNAMIC 从 632.13 修到 2.05，"
    "相对 FIFO 只慢 8%—10%；T4_K100 还以 2.39 对 3.17 胜出，因为长任务 K=100 还不足以长期占住 worker，"
    "把长任务所在队列里排队的短任务偷走能降低短请求等待。但 T4_K1000 是 690.60 对 313.18（2.2 倍），"
    "T5 组平均是 7.10 对 3.73（1.9 倍）：窃取只能搬“还在队列里”的任务，不能抢占已经在跑的长任务或后台任务；"
    "本地队列一旦被长任务占住，后面的短任务就要等，而 FIFO 的全局队列可以让其他 worker 继续取短任务。"
)
K.body(
    "因此，四种算法的关系不是“窃取最好”，而是：FIFO/Priority 在零成本模型下接近理想；Local 是必须避免的偏斜基线；"
    "Steal 用本地队列换可扩展性，修好了 Local 的偏斜，但仍要为本地队列、探测和不可抢占的长任务付出代价。"
    "A5 相对 A4 的 75%—94% 提升是真实的，但它修的是 Local，不是打败 FIFO。"
    "只有在真实系统里全局队列的锁/竞争成本足够高时，Steal 的相对位置才会改善；这套数据集没有对那部分计费。"
)

K.h1("3  Chase-Lev 变体：接入、阈值与全量结果")

K.h2("3.1  与官方 A5 的语义差异")
K.body(
    "官方 A5 与 Chase-Lev 变体在四个维度上不同。第一，受害者选择：A5 扫描全部 worker 选最长队列，"
    "Chase-Lev 变体随机打乱 victim 顺序，遇到第一个“长度大于 k”的队列就停止。第二，窃取端："
    "A5 从受害者队尾取（对受害者是 LIFO），Chase-Lev 从队首取（对受害者是 FIFO），"
    "把最老的任务先偷走。第三，owner 端：A5 从自己队首取（FIFO），Chase-Lev 从自己队尾取（LIFO）。"
    "第四，计费：A5 每次成功固定按 c−1=7 次探测计费，Chase-Lev 按实际探测次数计费。"
)
K.body(
    "这四点的组合决定了它们在不同的成本模型下互有胜负：A5 的“最长队列”在零成本时最接近理想负载均衡；"
    "Chase-Lev 的“随机早停”在探测有成本时更省，但可能偷到不够长的队列，阈值 k 则直接决定它愿不愿意偷。"
)

K.h2("3.2  实现要点")
K.body(
    "接入点只有 `Engine._pick` 与 `Engine._dispatch` 两处。下面省略了任务执行与 KeyGate 部分，"
    "只保留策略相关逻辑；完整代码在 `KV_Scheduling_Benchmark_WS/kvsched/sim.py`。"
)
K.code_block(
    "if self.local[worker]:\n"
    "    if self.policy == 'steal_cl' and self.steal_owner == 'lifo':\n"
    "        return self.local[worker].pop(), 0      # owner LIFO\n"
    "    return self.local[worker].popleft(), 0\n"
    "order = list(range(self.c)); self.rng.shuffle(order)\n"
    "probes = 0\n"
    "for j in order:\n"
    "    if j == worker: continue\n"
    "    probes += 1\n"
    "    if len(self.local[j]) > self.steal_threshold:\n"
    "        self.steal_attempts += probes; self.steals += 1\n"
    "        return self.local[j].popleft(), probes   # thief FIFO\n"
    "    if probes >= self.steal_probe_limit: break\n"
    "return None, 0"
)
K.body(
    "随机数生成器用 `trace.seed` 初始化，因此同一条轨迹的探测顺序可复现，配对比较仍然成立。"
    "`steal_probe_limit` 默认 2c，阈值 k 与 owner 端可通过 `--steal-threshold`、`--steal-owner` 控制。"
    "这套实现是基准引擎里的 Python 策略复刻，不是把 C++ `ws_deque.hpp` 直接链接进来；"
    "两者语义一致，但 C++ 侧的原子操作与内存序需要在真实硬件上单独验证。"
)

K.h2("3.3  阈值扫描：k=2 在 8 worker 下是负结果")
K.body(
    "表 5 固定 owner=LIFO、探测成本为 0，只改变阈值 k。每个格子是该 Case 在 3 个 seed 上的 P99 中位数，"
    "最后一列给出同 Case 的官方 A5 P99 作为参照。扫描用 n=20 000，因此绝对值与表 1 的 n=30 000 不可直接逐项对比。"
)

sweep_rows = []
for case in ("T1_A", "T2_ZIPF099", "T3_DYNAMIC", "T4_K100", "T5_BG10"):
    cells = []
    for k in (0, 1, 2, 4, 8):
        rs = [r for r in sweep if r["case"] == case and r["policy"] == "steal_cl"
              and r["owner"] == "lifo" and str(r["threshold"]) == str(k)
              and abs(float(r["probe_cost"])) < 1e-9]
        cells.append(f2(med(rs, "p99_median")))
    a5 = pick(official, case, "steal")
    sweep_rows.append([case] + cells + [f2(med(a5, "foreground_p99"))])

K.table(
    ["Case", "k=0", "k=1", "k=2", "k=4", "k=8", "官方 A5"],
    sweep_rows,
    [3.4, 1.9, 1.9, 1.9, 1.9, 1.9, 2.2],
    caption_text="表 5  阈值 k 对 P99 的影响（owner=LIFO，probe=0，n=20 000，3 seeds）",
    font=9.0,
)

K.body(
    "k=0 与官方 A5 基本持平：T2 2.01 对 2.03，T3 2.07 对 2.03，T1 2.34 对 2.36；"
    "T4 和 T5 略差（2.79 对 2.51、3.36 对 3.12），因为随机受害者不如“最长队列”稳定。"
    "k=1 开始退化，k=2 已经是 2.5—3.2 倍，k=4/8 则接近放弃窃取。原因不是随机数，而是队列深度："
    "8 worker、70% 负载、30 000 请求时，就绪队列峰值只有 12—24，绝大多数时刻每个本地队列只有 0—2 个任务。"
    "k=2 要求受害者长度至少为 3，空闲 worker 往往探测完所有 victim 也找不到合格者，于是继续空转，"
    "过载队列却因为“还没超过 3”而拒绝被偷。"
)
K.body(
    "这直接修正了课题报告里的一个隐含假设。我们在 20 线程、80 shard、动态热点的仿真中使用 k=2，"
    "当时队列更深，k=2 可以过滤掉“只偷一个任务反而增加迁移”的抖动；但在 8 worker、70% 负载的课程基准里，"
    "同样的 k=2 会把窃取关掉。阈值应写成队列深度的函数，例如 k = max(1, ⌊平均就绪队列长度/2⌋)，"
    "或至少按 worker 数/负载做敏感性扫描，不能作为跨规模常数。"
)

K.h2("3.4  全量结果：k=0 时的 Chase-Lev 与官方 A5")
K.body(
    "表 6 把阈值固定为 k=0（只要 victim 非空就允许窃取），在完整 18 Case × 3 seed 上重跑。"
    "左半部分是零探测成本，右半部分是每次探测 0.05 单位成本；两半的 A5 与 CL 都来自各自同一次运行，因此可以配对比较。"
)

full_rows = []
for case in MAIN_CASES:
    a4 = med(pick(cl0, case, "local"), "foreground_p99")
    a5 = med(pick(cl0, case, "steal"), "foreground_p99")
    cl = med(pick(cl0, case, "steal_cl"), "foreground_p99")
    a5c = med(pick(cl5, case, "steal"), "foreground_p99")
    clc = med(pick(cl5, case, "steal_cl"), "foreground_p99")
    full_rows.append([
        case, f2(a4), f2(a5), f2(cl), f"{cl/a5:.2f}",
        f2(a5c), f2(clc), f"{clc/a5c:.2f}",
    ])

K.table(
    ["Case", "A4", "A5@0", "CL@0", "CL/A5", "A5@.05", "CL@.05", "CL/A5"],
    full_rows,
    [3.0, 1.9, 1.9, 1.9, 1.6, 1.9, 1.9, 1.6],
    caption_text="表 6  Chase-Lev k=0 与官方 A5 的全量对比（n=30 000，3 seeds，中位数）",
    font=8.4,
)

K.body(
    "零成本时，CL 在 18 个场景中 12 个不劣于或优于 A5，平均 P99 比为 0.983，范围 0.731—1.158。"
    "差异主要出现在 T4_K100 与 T5_BG10_FIXED：CL 分别慢 16% 和 6%，因为随机 victim 可能偷到不够长的队列，"
    "而 A5 的最长队列选择在零成本下几乎总是更接近理想均衡。"
)
K.body(
    "但 T4_K1000 的 0.73 需要谨慎解读。该 Case 的 seed 间方差很大：A5 的 P99 范围是 267—923，"
    "CL 是 181—890，3 个 seed 的中位数差异不足以支撑“CL 稳定快 27%”的结论。"
    "更稳妥的表述是：在长任务场景，两种策略都可能被“长任务何时被哪个 worker 取到”主导，"
    "需要更多 seed 或逐事件追踪才能下结论。"
)
K.body(
    "有探测成本时，CL 在 18/18 个场景全部优于 A5，平均 P99 比 0.853，最低 0.650（T5_BG25），"
    "最高 0.915（T5_BG10）。这不是因为 CL 的负载均衡更好，而是因为它平均只探测 3.6—3.8 个 victim 就停止，"
    "而 A5 每次成功都固定计 7 次探测；在 0.05 单位/次的假设下，探测开销直接进入任务开始时间，"
    "省下来的探测时间转化为更低的排队延迟。"
)

# ---------------------------------------------------------------- 4
K.h1("4  探测成本敏感性")

K.body(
    "表 7 把同一批 Case 的 A5 与 CL(k=0) 放在两档探测成本下对比。探测成本是模型假设，不是硬件实测；"
    "0.05 单位约等于普通 GET 服务量（1.0）的 5%，用于表示一次跨核队列观察的代价。"
    "最后一列是 CL 相对 A5 的 P99 变化，负数表示 CL 更好。"
)

probe_rows = []
for case in ("T1_A", "T2_ZIPF099", "T3_DYNAMIC", "T4_K100", "T5_BG10"):
    a0 = med(pick(cl0, case, "steal"), "foreground_p99")
    c0 = med(pick(cl0, case, "steal_cl"), "foreground_p99")
    a5 = med(pick(cl5, case, "steal"), "foreground_p99")
    c5 = med(pick(cl5, case, "steal_cl"), "foreground_p99")
    probe_rows.append([
        case, f2(a0), f2(c0), f2(a5), f2(c5), f"{c5/a5-1:+.1%}",
    ])

K.table(
    ["Case", "A5@0", "CL@0", "A5@0.05", "CL@0.05", "CL 变化"],
    probe_rows,
    [3.4, 2.4, 2.4, 2.6, 2.6, 2.2],
    caption_text="表 7  探测成本 0 与 0.05 下的 P99（n=30 000，3 seeds，中位数）",
    font=9.0,
)

K.body(
    "探测次数的直接证据来自 `steal_probe_count / steal_count`。零成本、T2_ZIPF099 下，"
    "A5 为 86 926 / 12 418 ≈ 7.00 次/窃取，CL 为 47 602 / 12 629 ≈ 3.77 次/窃取；"
    "T4_K100 为 84 945 / 12 135 ≈ 7.00 对 46 212 / 12 363 ≈ 3.74；T5_BG10 为 89 957 / 12 851 ≈ 7.00 对 47 305 / 13 067 ≈ 3.62。"
    "随机早停把探测数压到约一半，这是成本敏感场景下 CL 胜出的主因。"
)
K.body(
    "反过来，当探测成本为 0 时，A5 的最长队列选择仍然略优：它把“偷哪个队列”这一步做到了近似最优，"
    "而 CL 的随机选择会浪费一部分窃取机会。因此两种策略的取舍不是“谁绝对更好”，而是"
    "“探测贵不贵、队列深不深”：探测越贵、队列越浅，随机早停越有价值；探测免费、队列深，最长队列越稳。"
)

K.h2("4.1  owner LIFO 与 FIFO 的消融")
K.body(
    "阈值扫描同时跑了 owner=FIFO 的消融（k=0）：T1_A 2.28 对 LIFO 2.34，T2_ZIPF099 2.03 对 2.01，"
    "T3_DYNAMIC 2.02 对 2.07，T4_K100 2.60 对 2.79，T5_BG10 3.14 对 3.36。"
    "差异在 −3% 到 +3% 之间，没有稳定方向。这个模型没有缓存、NUMA 或队列锁成本，"
    "owner 端 LIFO 的局部性收益无法体现；它只能说明“在本模型里，owner 端顺序不是尾延迟的主要因素”。"
    "因此不能把本数据集的 CL 结果解释为“LIFO 降低了 P99”；LIFO 的动机仍是真实硬件上的缓存亲和与减少跨核迁移，"
    "需要用 C++ 微基准或真实机器实验验证。"
)

# ---------------------------------------------------------------- 5
K.h1("5  讨论、对课题报告的修订建议与限制")

K.h2("5.1  对课题报告的四条修订建议")
K.body(
    "第一，给阈值 k 加上适用条件。报告里 k=2 是在 20 线程、80 shard、动态热点、较高队列深度下选的；"
    "课程基准的 8 worker/70% 负载下 k=2 会把窃取关掉。建议改成“k 随平均就绪队列长度缩放”，"
    "并至少报告 k=0/1/2 的敏感性，而不是把 2 写成固定最优值。"
)
K.body(
    "第二，把“工作窃取的收益”和“工作窃取不能做什么”分开写。数据集给出了很干净的正反两组证据："
    "T2/T3 中 A5 把 P99 降低 87%—94%，这是可并行就绪任务的收益；D1_HOTKEY 中四种算法都被 11 201 的键等待支配，"
    "这是同键串行的边界。报告应把 D1 作为负对照，而不是只展示有利场景。"
)
K.body(
    "第三，把探测成本作为选择受害者策略的依据，而不是只比较零成本 P99。零成本时最长队列略优；"
    "0.05 成本时随机早停 18/18 胜出。报告可以据此解释为什么 Chase-Lev 采用随机 victim 而不是全局最长队列："
    "不是为了零成本最优，而是为了在真实探测/竞争成本下更稳。"
)
K.body(
    "第四，明确 A1 与 A5 的取舍，不要把 A5 写成“P99 绝对最优”。本数据集在零成本下 FIFO/Priority 在 13/18 个场景最低，"
    "A5 只在 T4_K100 胜出，T4_K1000 慢 2.2 倍、T5 慢 1.9 倍。更准确的定位是：A5 避免了全局队列的锁与竞争，"
    "用 8%—10% 的 T1—T3 P99 代价换可扩展性；只有把全局队列的真实成本计入，才能公平比较 A1 与 A5。"
)

K.h2("5.2  有效性与限制")
K.body(
    "本测试的结论受以下限制。其一，所有时间都是抽象单位，不能换算成微秒或 QPS；"
    "0.05 的探测成本是假设，不是测量。其二，仿真没有缓存、NUMA、内存带宽、桶锁、队列 CAS 竞争等硬件效应，"
    "因此不能验证 Chase-Lev 的局部性/低竞争优势，只能验证派发顺序与探测开销。"
    "其三，每个配置只有 3 个 seed，表中给的是中位数；没有计算置信区间，长任务 Case 的 seed 间方差很大。"
    "其四，`steal_cl` 是基准引擎中的 Python 语义复刻，不是 C++ 代码本身；C++ 的原子操作、内存序和伪共享需要单独测试。"
    "其五，T5 的完成触发模式会让不同算法的后台到达时刻略有不同，这是因果系统的一部分；"
    "固定触发模式更适合比较派发机制，但不代表真实维护触发语义。"
)

K.h2("5.3  结论")
K.body(
    "把四种算法放在一起，本数据集上的 P99 排名是 FIFO ≈ Priority > Steal ≫ Local：FIFO/Priority 在 13/18 个场景并列最低，"
    "Priority 在 4 个 T5 场景略优，Steal 只在 T4_K100 胜出，Local 从未胜出。但这个排名是“全局队列零锁/零竞争成本”的模型结论，"
    "不能直接外推到真实系统。A5 相对 A4 的 75%—94% 提升是真实的，它修的是 Local 的哈希偏斜；但 A5 不是零成本下的绝对赢家："
    "T1—T3 比 FIFO 慢 8%—10%，T4_K1000 慢 2.2 倍，T5 慢 1.9 倍。"
)
K.body(
    "Chase-Lev 变体在 k=0 时与 A5 基本持平；在探测有成本时，随机早停把探测数减半，从而在全部 18 个场景取得更低 P99。"
    "阈值 k 是真正的敏感参数：在浅队列下 k=2 会让窃取失效，必须按队列深度缩放。owner 端 LIFO 的局部性收益在本模型中不可见，"
    "不能据此宣称 LIFO 改善尾延迟。"
)
K.body(
    "因此，建议把本数据集作为课题报告的“外部验证”一节：它用统一的请求轨迹、Key 依赖门和统计口径，"
    "既复现了 A5 相对 A4 的主要趋势，也给出了 A1/A5 的取舍和 D1 这个清晰的负对照；同时用它来校准阈值和探测成本的假设，"
    "而不是用自己生成的泊松仿真同时扮演“提出方法”和“证明方法”两个角色。"
)

# ---------------------------------------------------------------- appendix
appendix = K.h1("附录 A  复现命令")
appendix.paragraph_format.page_break_before = True
K.body("以下命令均在数据集根目录执行；`py` 替换为实际 Python 3.10+ 解释器。", indent=False)
K.code_block(
    "# 1) 官方检查\n"
    "python -m unittest discover -s tests -v\n"
    "python run.py suite --preset main --out results/dataset_main.csv\n"
    "python run.py suite --cases D1_HOTKEY D1_SPREAD --n 10000 --seeds 3 \\\n"
    "  --out results/dataset_d1.csv\n"
    "\n"
    "# 2) 回放官方示例轨迹\n"
    "python run.py replay --input examples/T2_ZIPF099_1p5k.csv \\\n"
    "  --out results/example_replay.csv --policies local steal\n"
    "\n"
    "# 3) Chase-Lev 变体（在 KV_Scheduling_Benchmark_WS 中）\n"
    "python run.py suite --preset main --policies fifo local steal steal_cl \\\n"
    "  --steal-threshold 0 --out results/dataset_ws_k0.csv\n"
    "python run.py suite --preset main --policies local steal steal_cl \\\n"
    "  --steal-threshold 0 --probe-cost 0.05 \\\n"
    "  --out results/dataset_ws_k0_cost05.csv\n"
    "\n"
    "# 4) 阈值/成本扫描\n"
    "python sweep_ws.py"
)
K.body(
    "注意：`--steal-threshold` 只影响 `steal_cl`；`--probe-cost` 对所有策略生效，"
    "但 fifo/local 没有探测，因此不受影响。原始解压目录与修改副本是两套独立目录，"
    "复现官方数字请用原始目录；复现 CL 数字请用 `KV_Scheduling_Benchmark_WS`。"
)

K.h1("附录 B  结果文件清单")
for line in [
    "`dataset_test/results/official_main.csv`：官方主套件 216 行原始结果。",
    "`official_main_summary.csv`：按 Case×算法聚合的 3-seed 中位数/范围。",
    "`official_d1.csv` / `official_d1_summary.csv`：D1 的 24 行结果与汇总。",
    "`chaselev_k0.csv` / `chaselev_k0_summary.csv`：CL k=0 全量 216 行。",
    "`chaselev_k0_probe005.csv` / `..._summary.csv`：探测成本 0.05 的 162 行。",
    "`threshold_sweep.csv` / `threshold_sweep_summary.csv`：k=0/1/2/4/8 与 owner 消融的 210 行。",
    "`example_replay.csv`：官方 1 500 条示例轨迹的回放结果。",
]:
    K.body(line, indent=False)

K.body(
    "修改副本：`工作区/benchmark_student/KV_Scheduling_Benchmark_WS/`；"
    "原始数据集：`工作区/benchmark_student/KV_Scheduling_Benchmark_Student_20261104/`。",
    indent=False,
)

doc.save(OUT)
print("saved", OUT)