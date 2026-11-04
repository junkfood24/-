# KV 调度 Benchmark 数据集：任务窃取测试

本目录记录用课程组提供的 `KV_Scheduling_Benchmark_Student_20261104` 数据集对任务窃取（A5）所做的独立测试，以及 Chase-Lev 语义变体 `steal_cl` 的对比实验。

## 结论摘要

- 数据集完整可运行：11/11 单元测试通过；官方主套件 216 次仿真、D1 24 次仿真、Chase-Lev 全量 216 次、探测成本实验 162 次、参数扫描 210 次，均正常结束，所有任务都被消费且 KeyGate 清零。
- 把四种官方算法放在一起，P99 排名是 **FIFO ≈ Priority > Steal ≫ Local**：FIFO/Priority 在 13/18 个场景并列最低，Priority 在 4 个 T5 场景略优，Steal 只在 T4_K100 胜出，Local 从未胜出。这是“全局队列零锁/零竞争成本”的模型结论，不能直接外推。
- 官方 A5（最长队列受害者、队尾窃取）相对 A4 本地队列显著降低 P99：按 T1—T5 组均值，A5 的 P99 为 A4 的 **5.7%—24.8%**（降低 75%—94%）。
- D1_HOTKEY 中四种算法的 P99 都约 **11 202**，键依赖等待约 **11 201**；A5 只窃取 22 次仍无改善。工作窃取不能突破同键写串行，这是清晰的负对照。
- `steal_cl`（owner LIFO / thief FIFO / 随机 victim / 阈值 k）在 k=0、探测成本为 0 时与 A5 基本持平：12/18 个场景不劣于或优于，平均 P99 比 **0.983**（范围 0.731—1.158）。
- 当每次探测计 0.05 单位成本、且**失败探测也计费**时，CL 只在 3/18 个场景优于 A5（T4_K1000 0.632、T5_BG25 0.717、T5_BG25_FIXED 0.744），其余 15 个场景是 A5 的 1.49—2.42 倍，平均 1.84。原因是 CL 在每个空闲循环都可能空扫 3—4 个 victim，而 A5 只在成功时按 7 次探测计费；没有退避/预算时，早停并不自动省钱。
- **关键修正**：k=2 在 8 worker、70% 负载下是负结果，P99 达到 A5 的 **2.53—3.23 倍**。该规模下本地队列普遍只有 0—2 个任务，k=2 实际关闭了大多数窃取。阈值必须随队列深度/worker 数缩放，不能把 20 线程实验中的 k=2 直接搬到 8 线程。
- owner 端 LIFO 与 FIFO 在本模型中的差异为 **−6.8%…+1.0%**，没有稳定优势。数据集不建模缓存、NUMA、锁竞争，不能验证 Chase-Lev 的局部性收益，只能验证派发与尾延迟。

## 文件

| 文件 | 内容 |
|---|---|
| `KV数据集_任务窃取测试报告.docx` / `.pdf` | 15 页测试报告（封面、摘要、5 节正文、2 个附录） |
| `results/official_main.csv` | 官方主套件 216 行原始结果 |
| `results/official_main_summary.csv` | 官方 3-seed 中位数/范围汇总 |
| `results/official_d1.csv` | D1 两个 Case 的 24 行结果 |
| `results/chaselev_k0.csv` | `steal_cl` k=0 全量 216 行 |
| `results/chaselev_k0_probe005.csv` | 探测成本 0.05 的 162 行 |
| `results/threshold_sweep.csv` | k=0/1/2/4/8 与 owner 消融的 210 行 |
| `results/ws_sweep.csv` / `_summary.csv` | 与 `threshold_sweep` 同配置的 CL 扫描（表 5 的来源） |
| `results/cl_compare_rerun.log` | n=30k 的 CL/A5 重跑日志 |
| `results/example_replay.csv` | 官方 1500 条示例轨迹回放 |
| `results/example_replay_all.txt` | 6 条官方示例轨迹的回放日志 |
| `steal_cl.patch` | 相对原始数据集的 `sim.py`/`cli.py` 补丁（可用 `git apply --check` 验证） |
| `sweep_ws.py` | 阈值/成本扫描脚本（需 `KV_BENCH` 指向基准包） |
| `run_cl_compare.py` | 重跑 n=30k 的 CL/A5 对比（生成表 6/7 的 CSV） |

## 复现

原始数据集解压目录的源代码保持未改动（只新增结果 CSV）；`steal_cl` 实验在副本 `../../benchmark_student/KV_Scheduling_Benchmark_WS/` 中进行。

```bash
cd ../../benchmark_student/KV_Scheduling_Benchmark_Student_20261104
python -m unittest discover -s tests -v
python run.py suite --preset main --out results/dataset_main.csv
python run.py suite --cases D1_HOTKEY D1_SPREAD --n 10000 --seeds 3 \
  --out results/dataset_d1.csv

cd ../KV_Scheduling_Benchmark_WS
python run.py suite --preset main --policies fifo local steal steal_cl \
  --steal-threshold 0 --out results/dataset_ws_k0.csv
python run.py suite --preset main --policies local steal steal_cl \
  --steal-threshold 0 --probe-cost 0.05 --out results/dataset_ws_k0_cost05.csv
KV_BENCH=../../benchmark_student/KV_Scheduling_Benchmark_WS python sweep_ws.py
KV_BENCH=../../benchmark_student/KV_Scheduling_Benchmark_WS python run_cl_compare.py
```

## 主要结果表

四种算法组平均 P99：

| 组 | FIFO | Priority | Local | Steal |
|---|---:|---:|---:|---:|
| T1 | 1.88 | 1.88 | 8.35 | 2.07 |
| T2 | 1.84 | 1.84 | 128.64 | 2.00 |
| T3 | 1.87 | 1.87 | 335.93 | 2.02 |
| T4 | 79.93 | 79.93 | 631.78 | 174.20 |
| T5 | 3.73 | 3.54 | 70.24 | 7.10 |

官方 A5/A4 P99 比（先对每个 Case 的 3 个 seed 取中位数，再对组内 Case 的比值等权平均；不是总 P99 之比）：

| 组 | T1 | T2 | T3 | T4 | T5 |
|---|---:|---:|---:|---:|---:|
| A5/A4 均值 | 0.248 | 0.129 | 0.057 | 0.187 | 0.140 |

`steal_cl` k=0 全量对比（节选；完整 18 行见报告表 6）：

| Case | A5@0 | CL@0 | CL/A5 | A5@0.05 | CL@0.05 | CL/A5 |
|---|---:|---:|---:|---:|---:|---:|
| T2_ZIPF099 | 2.06 | 2.06 | 1.00 | 3.03 | 6.47 | 2.14 |
| T3_DYNAMIC | 2.05 | 2.02 | 0.98 | 3.01 | 6.39 | 2.13 |
| T4_K100 | 2.39 | 2.77 | 1.16 | 4.72 | 7.05 | 1.49 |
| T4_K1000 | 690.60 | 505.00 | 0.73 | 890.21 | 562.37 | 0.63 |
| T5_BG25 | 12.13 | 12.30 | 1.01 | 28.56 | 20.48 | 0.72 |

阈值扫描（P99，owner=LIFO，probe=0，n=20 000）：

| Case | k=0 | k=1 | k=2 | k=4 | k=8 |
|---|---:|---:|---:|---:|---:|
| T2_ZIPF099 | 2.01 | 2.79 | 5.13 | 12.35 | 29.43 |
| T4_K100 | 2.79 | 5.50 | 8.11 | 13.60 | 22.55 |
| T5_BG10 | 3.36 | 5.24 | 7.92 | 15.64 | 33.38 |

## 限制

- 时间为抽象服务时间单位，不是真实微秒或 QPS；0.05 的探测成本是模型假设。
- 无缓存、NUMA、内存带宽、桶锁、CAS 竞争建模。
- 每个配置 3 个 seed，报告给中位数；未计算置信区间，长任务 Case（T4_K1000）seed 间方差很大。
- `steal_cl` 是基准引擎中的 Python 语义复刻，不是 C++ `ws_deque.hpp` 本身。
- T5 完成触发模式下不同算法的后台到达时刻略有差异，这是因果系统的一部分。

