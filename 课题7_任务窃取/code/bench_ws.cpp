// bench_ws.cpp —— 20 线程上的三种调度策略实测（集中式 FIFO / 本地队列 / 工作窃取）
//
// 构造：2,000,000 个任务，键按 uniform 或 Zipf(1.1) 映射到 80 个分片，
//       分片 s 的属主为 s % 20；每个任务做 512 次（1% 长任务 16384 次）
//       相关哈希探测，约 4–7 µs（随机器与编译器变化）。三种策略处理同一批任务，比较 makespan、
//       吞吐与端到端延迟分位数（提交时刻统一取 barrier 之后的 t0）。
//
// 编译： g++ -O2 -std=c++17 -pthread bench_ws.cpp -o bench_ws
// 运行： ./bench_ws [任务数] [线程数] [uniform|skew] [--selftest]

#include "ws_deque.hpp"

#include <algorithm>
#include <atomic>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <memory>
#include <random>
#include <string>
#include <thread>
#include <vector>

namespace {

constexpr int kShards = 80;
constexpr int kTableBits = 13;                 // 8192 项 / 分片
constexpr int kBaseProbes = 512;
constexpr int kLongProbes = 16384;
constexpr double kLongFrac = 0.01;

struct Task {
    uint64_t key;
    uint32_t id;
    uint32_t shard;
    uint32_t owner;
    uint32_t is_long;
};

using Clock = std::chrono::steady_clock;

inline uint64_t run_task(const Task& t,
                         const std::vector<std::vector<uint64_t>>& tables) {
    const auto& tab = tables[t.shard];
    const uint64_t mask = tab.size() - 1;
    uint64_t h = t.key | 1ull;
    int probes = t.is_long ? kLongProbes : kBaseProbes;
    for (int i = 0; i < probes; ++i) {
        h ^= tab[h & mask];
        h *= 0x9E3779B97F4A7C15ull;
        h ^= h >> 29;
    }
    return h;
}

struct Result {
    double makespan_ms = 0.0;
    double throughput_mops = 0.0;
    double p50_us = 0.0, p99_us = 0.0, p999_us = 0.0;
    uint64_t checksum = 0;
    uint64_t processed = 0;
    uint64_t steals = 0;
};

double pct(std::vector<uint64_t>& v, double q) {
    if (v.empty()) return 0.0;
    std::size_t i = static_cast<std::size_t>(q * (v.size() - 1));
    return static_cast<double>(v[i]) / 1000.0;   // ns -> us
}

Result summarize(const std::vector<uint64_t>& latency, uint64_t t_end_ns,
                 uint64_t checksum, uint64_t processed, uint64_t steals) {
    Result r;
    r.makespan_ms = static_cast<double>(t_end_ns) / 1e6;
    r.throughput_mops = static_cast<double>(processed) /
                        (static_cast<double>(t_end_ns) / 1e9) / 1e6;
    std::vector<uint64_t> v = latency;
    std::sort(v.begin(), v.end());
    r.p50_us = pct(v, 0.50);
    r.p99_us = pct(v, 0.99);
    r.p999_us = pct(v, 0.999);
    r.checksum = checksum;
    r.processed = processed;
    r.steals = steals;
    return r;
}

struct TaskSet {
    std::vector<Task> tasks;
    std::vector<std::vector<uint32_t>> by_owner;
};

TaskSet build_tasks(std::size_t n, int threads, const std::string& workload,
                    uint64_t seed = 20261104) {
    TaskSet ts;
    ts.tasks.resize(n);
    ts.by_owner.resize(threads);
    std::mt19937_64 rng(seed);
    std::vector<double> weights(kShards);
    for (int i = 0; i < kShards; ++i)
        weights[i] = 1.0 / std::pow(static_cast<double>(i + 1), 1.1);
    std::discrete_distribution<int> zipf(weights.begin(), weights.end());
    std::uniform_int_distribution<int> uni(0, kShards - 1);
    std::uniform_real_distribution<double> u01(0.0, 1.0);
    std::uniform_int_distribution<uint64_t> keys;
    for (std::size_t i = 0; i < n; ++i) {
        Task t{};
        t.key = keys(rng);
        t.id = static_cast<uint32_t>(i);
        t.shard = (workload == "skew") ? zipf(rng) : uni(rng);
        t.owner = t.shard % threads;
        t.is_long = (u01(rng) < kLongFrac) ? 1 : 0;
        ts.tasks[i] = t;
        ts.by_owner[t.owner].push_back(static_cast<uint32_t>(i));
    }
    return ts;
}

std::vector<std::vector<uint64_t>> make_tables() {
    std::vector<std::vector<uint64_t>> tables(kShards);
    std::mt19937_64 rng(7);
    for (auto& t : tables) {
        t.resize(1ull << kTableBits);
        for (auto& x : t) x = rng();
    }
    return tables;
}

// 所有线程在 go 标志处同步起跑
struct StartGate {
    std::atomic<int> ready{0};
    std::atomic<bool> go{false};
};

void wait_start(StartGate& gate) {
    gate.ready.fetch_add(1, std::memory_order_acq_rel);
    while (!gate.go.load(std::memory_order_acquire)) std::this_thread::yield();
}

Result run_central(const TaskSet& ts, int threads,
                   const std::vector<std::vector<uint64_t>>& tables) {
    const std::size_t n = ts.tasks.size();
    std::vector<uint64_t> latency(n, 0);
    std::atomic<std::size_t> cursor{0};
    std::atomic<uint64_t> checksum{0};
    std::atomic<uint64_t> done{0};
    StartGate gate;
    auto t0 = std::make_shared<Clock::time_point>();

    std::vector<std::thread> pool;
    for (int w = 0; w < threads; ++w) {
        pool.emplace_back([&, w] {
            wait_start(gate);
            (void)w;
            constexpr std::size_t kBatch = 8;
            for (;;) {
                std::size_t begin = cursor.fetch_add(kBatch, std::memory_order_relaxed);
                if (begin >= n) break;
                std::size_t end = std::min(begin + kBatch, n);
                uint64_t sum = 0;
                for (std::size_t i = begin; i < end; ++i) {
                    sum += run_task(ts.tasks[i], tables);
                    latency[i] = static_cast<uint64_t>(
                        std::chrono::duration_cast<std::chrono::nanoseconds>(
                            Clock::now() - *t0).count());
                    done.fetch_add(1, std::memory_order_relaxed);
                }
                checksum.fetch_add(sum, std::memory_order_relaxed);
            }
        });
    }
    while (gate.ready.load() < threads) std::this_thread::yield();
    *t0 = Clock::now();
    gate.go.store(true, std::memory_order_release);
    for (auto& th : pool) th.join();
    uint64_t t_end = 0;
    for (auto x : latency) t_end = std::max(t_end, x);
    return summarize(latency, t_end, checksum.load(), done.load(), 0);
}

Result run_local(const TaskSet& ts, int threads,
                 const std::vector<std::vector<uint64_t>>& tables) {
    const std::size_t n = ts.tasks.size();
    std::vector<uint64_t> latency(n, 0);
    std::atomic<uint64_t> checksum{0};
    StartGate gate;
    auto t0 = std::make_shared<Clock::time_point>();

    std::vector<std::thread> pool;
    for (int w = 0; w < threads; ++w) {
        pool.emplace_back([&, w] {
            wait_start(gate);
            uint64_t sum = 0;
            for (uint32_t idx : ts.by_owner[w]) {
                sum += run_task(ts.tasks[idx], tables);
                latency[idx] = static_cast<uint64_t>(
                    std::chrono::duration_cast<std::chrono::nanoseconds>(
                        Clock::now() - *t0).count());
            }
            checksum.fetch_add(sum, std::memory_order_relaxed);
        });
    }
    while (gate.ready.load() < threads) std::this_thread::yield();
    *t0 = Clock::now();
    gate.go.store(true, std::memory_order_release);
    for (auto& th : pool) th.join();
    uint64_t t_end = 0;
    for (auto x : latency) t_end = std::max(t_end, x);
    return summarize(latency, t_end, checksum.load(), n, 0);
}

Result run_ws(const TaskSet& ts, int threads,
              const std::vector<std::vector<uint64_t>>& tables) {
    const std::size_t n = ts.tasks.size();
    std::vector<uint64_t> latency(n, 0);
    std::vector<std::unique_ptr<ChaseLevDeque<uint32_t>>> deques(threads);
    for (auto& d : deques) d = std::make_unique<ChaseLevDeque<uint32_t>>(1024);
    std::atomic<uint64_t> checksum{0};
    std::atomic<uint64_t> remaining{n};
    std::atomic<uint64_t> steals{0};
    StartGate gate;

    // 预填充阶段：每个属主把自己的任务压入自己的双端队列（不计入计时）
    std::atomic<int> prefilled{0};
    std::vector<std::thread> prefetch;
    for (int w = 0; w < threads; ++w) {
        prefetch.emplace_back([&, w] {
            for (uint32_t idx : ts.by_owner[w]) deques[w]->push(idx);
            prefilled.fetch_add(1, std::memory_order_release);
        });
    }
    for (auto& th : prefetch) th.join();

    auto t0 = std::make_shared<Clock::time_point>();
    std::vector<std::thread> pool;
    for (int w = 0; w < threads; ++w) {
        pool.emplace_back([&, w] {
            std::mt19937 rng(static_cast<uint32_t>(w * 7919 + 13));
            wait_start(gate);
            uint64_t sum = 0;
            while (remaining.load(std::memory_order_relaxed) > 0) {
                uint32_t id = 0;
                bool got = false;
                if (deques[w]->pop(id)) {
                    got = true;
                } else {
                    for (int probe = 0; probe < threads * 2 && !got; ++probe) {
                        int v = static_cast<int>(rng() % threads);
                        if (v != w && deques[v]->steal(id)) {
                            got = true;
                            steals.fetch_add(1, std::memory_order_relaxed);
                        }
                    }
                }
                if (!got) {
                    if (remaining.load(std::memory_order_relaxed) == 0) break;
                    std::this_thread::yield();
                    continue;
                }
                const Task& t = ts.tasks[id];
                sum += run_task(t, tables);
                latency[t.id] = static_cast<uint64_t>(
                    std::chrono::duration_cast<std::chrono::nanoseconds>(
                        Clock::now() - *t0).count());
                remaining.fetch_sub(1, std::memory_order_relaxed);
            }
            checksum.fetch_add(sum, std::memory_order_relaxed);
        });
    }
    while (gate.ready.load() < threads) std::this_thread::yield();
    *t0 = Clock::now();
    gate.go.store(true, std::memory_order_release);
    for (auto& th : pool) th.join();
    uint64_t t_end = 0;
    for (auto x : latency) t_end = std::max(t_end, x);
    return summarize(latency, t_end, checksum.load(), n, steals.load());
}

void selftest() {
    ChaseLevDeque<int> q(4);
    constexpr int kItems = 200000;
    std::atomic<int> consumed{0};
    std::atomic<int> duplicates{0};
    std::vector<std::atomic<int>> seen(kItems);
    for (auto& s : seen) s.store(0, std::memory_order_relaxed);
    auto consume = [&](int v) {
        if (v < 0 || v >= kItems) {
            std::printf("SELFTEST FAILED: out-of-range item %d\n", v);
            std::exit(1);
        }
        if (seen[v].fetch_add(1, std::memory_order_relaxed) != 0)
            duplicates.fetch_add(1, std::memory_order_relaxed);
        consumed.fetch_add(1, std::memory_order_relaxed);
    };

    std::vector<std::thread> thieves;
    std::atomic<bool> stop{false};
    for (int i = 0; i < 4; ++i) {
        thieves.emplace_back([&] {
            int v;
            while (!stop.load(std::memory_order_relaxed)) {
                if (q.steal(v)) consume(v);
            }
        });
    }
    for (int i = 0; i < kItems; ++i) {
        q.push(i);
        if (i % 1000 == 0) {
            int v;
            if (q.pop(v)) consume(v);
        }
    }
    while (consumed.load(std::memory_order_relaxed) < kItems) {
        int v;
        if (q.pop(v)) consume(v);
        else std::this_thread::yield();
    }
    stop.store(true, std::memory_order_relaxed);
    for (auto& t : thieves) t.join();

    int missing = 0;
    for (int i = 0; i < kItems; ++i)
        if (seen[i].load(std::memory_order_relaxed) == 0) ++missing;
    if (missing != 0 || duplicates.load() != 0 ||
        consumed.load() != kItems) {
        std::printf("SELFTEST FAILED: consumed=%d expected=%d missing=%d duplicates=%d\n",
                    consumed.load(), kItems, missing, duplicates.load());
        std::exit(1);
    }
    std::printf("SELFTEST OK: %d items, missing=0 duplicates=0\n", kItems);
}

}  // namespace

int main(int argc, char** argv) {
    std::size_t n = 2000000;
    int threads = static_cast<int>(std::thread::hardware_concurrency());
    if (threads <= 0) threads = 8;
    std::string workload = "skew";
    bool run_selftest = false;
    int positional = 0;
    for (int i = 1; i < argc; ++i) {
        if (std::strcmp(argv[i], "--selftest") == 0) run_selftest = true;
        else if (std::strcmp(argv[i], "--uniform") == 0) workload = "uniform";
        else if (std::strcmp(argv[i], "--skew") == 0) workload = "skew";
        else if (argv[i][0] != '-') {
            if (positional == 0) n = std::strtoull(argv[i], nullptr, 10);
            else if (positional == 1) threads = std::atoi(argv[i]);
            else if (positional == 2) workload = argv[i];
            ++positional;
        }
    }
    if (run_selftest) { selftest(); return 0; }
    constexpr int kMaxThreads = 64;
    if (threads <= 0 || threads > kMaxThreads) threads = 20;
    std::printf("tasks=%zu threads=%d workload=%s\n", n, threads, workload.c_str());

    TaskSet ts = build_tasks(n, threads, workload);
    auto tables = make_tables();

    Result a = run_central(ts, threads, tables);
    Result b = run_local(ts, threads, tables);
    Result c = run_ws(ts, threads, tables);

    std::printf("%-10s %12s %10s %10s %10s %10s %12s\n",
                "policy", "makespan_ms", "Mop/s", "P50_us", "P99_us", "P99.9_us", "checksum");
    auto pr = [](const char* name, const Result& r) {
        std::printf("%-10s %12.1f %10.3f %10.1f %10.1f %10.1f %12llu\n",
                    name, r.makespan_ms, r.throughput_mops,
                    r.p50_us, r.p99_us, r.p999_us,
                    static_cast<unsigned long long>(r.checksum));
    };
    pr("fifo", a);
    pr("local", b);
    pr("ws", c);
    if (a.checksum != b.checksum || b.checksum != c.checksum) {
        std::printf("CHECKSUM MISMATCH!\n");
        return 1;
    }
    std::printf("checksum OK\n");
    return 0;
}
