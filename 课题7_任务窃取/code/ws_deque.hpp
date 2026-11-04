// ws_deque.hpp —— Chase-Lev 工作窃取双端队列（C++17 参考实现）
//
// 语义：
//   * 所有者线程调用 push() / pop()，只在“底部”操作，LIFO；
//   * 任意窃取者线程调用 steal()，只在“顶部”操作，FIFO，CAS 竞争；
//   * 所有者是唯一写 bottom 的线程，窃取者只写 top。
//
// 说明：本实现采用 Lé 等人 (2013) 的简化内存序（seq_cst fence），
// 以正确性优先、便于教学；生产实现可进一步放宽屏障。
// 队列按 2 的幂扩容，旧数组保留到析构，避免窃取者访问已释放内存。

#pragma once

#include <atomic>
#include <cstddef>
#include <memory>
#include <utility>
#include <vector>

template <class T>
class ChaseLevDeque {
public:
    explicit ChaseLevDeque(std::size_t initial_capacity = 1024) {
        std::size_t cap = 2;
        while (cap < initial_capacity) cap <<= 1;
        arrays_.push_back(std::make_unique<Array>(cap));
        array_.store(arrays_.back().get(), std::memory_order_relaxed);
    }

    ChaseLevDeque(const ChaseLevDeque&) = delete;
    ChaseLevDeque& operator=(const ChaseLevDeque&) = delete;
    ~ChaseLevDeque() = default;

    // 仅所有者线程调用
    void push(T value) {
        std::size_t b = bottom_.load(std::memory_order_relaxed);
        std::size_t t = top_.load(std::memory_order_acquire);
        Array* a = array_.load(std::memory_order_relaxed);
        if (b - t > a->cap - 1) {           // 满
            a = grow(a, b, t);
        }
        a->at(b).store(std::move(value), std::memory_order_relaxed);
        std::atomic_thread_fence(std::memory_order_release);
        bottom_.store(b + 1, std::memory_order_relaxed);
    }

    // 仅所有者线程调用；返回 false 表示队列为空
    bool pop(T& out) {
        std::size_t b = bottom_.load(std::memory_order_relaxed);
        std::size_t t = top_.load(std::memory_order_relaxed);
        if (b <= t) return false;           // 空（或正被窃取者取走最后一个）
        --b;
        Array* a = array_.load(std::memory_order_relaxed);
        bottom_.store(b, std::memory_order_relaxed);
        std::atomic_thread_fence(std::memory_order_seq_cst);
        t = top_.load(std::memory_order_relaxed);
        if (t <= b) {
            out = a->at(b).load(std::memory_order_relaxed);
            if (t == b) {                   // 只剩一个，与窃取者竞争
                if (!top_.compare_exchange_strong(t, t + 1,
                                                  std::memory_order_seq_cst,
                                                  std::memory_order_relaxed)) {
                    bottom_.store(b + 1, std::memory_order_relaxed);
                    return false;
                }
                bottom_.store(b + 1, std::memory_order_relaxed);
            }
            return true;
        }
        bottom_.store(b + 1, std::memory_order_relaxed);
        return false;
    }

    // 任意线程调用；返回 false 表示队列为空或竞争失败
    bool steal(T& out) {
        std::size_t t = top_.load(std::memory_order_acquire);
        std::atomic_thread_fence(std::memory_order_seq_cst);
        std::size_t b = bottom_.load(std::memory_order_acquire);
        if (t >= b) return false;
        Array* a = array_.load(std::memory_order_acquire);
        out = a->at(t).load(std::memory_order_relaxed);
        if (!top_.compare_exchange_strong(t, t + 1,
                                          std::memory_order_seq_cst,
                                          std::memory_order_relaxed)) {
            return false;
        }
        return true;
    }

    // 近似长度，仅用于阈值判断与统计
    std::size_t size() const {
        std::size_t b = bottom_.load(std::memory_order_relaxed);
        std::size_t t = top_.load(std::memory_order_relaxed);
        return b > t ? b - t : 0;
    }

private:
    struct Array {
        std::size_t cap;
        std::unique_ptr<std::atomic<T>[]> buf;
        explicit Array(std::size_t c)
            : cap(c), buf(std::make_unique<std::atomic<T>[]>(c)) {}
        std::atomic<T>& at(std::size_t i) { return buf[i & (cap - 1)]; }
        const std::atomic<T>& at(std::size_t i) const { return buf[i & (cap - 1)]; }
    };

    Array* grow(Array* old, std::size_t b, std::size_t t) {
        auto na = std::make_unique<Array>(old->cap * 2);
        for (std::size_t i = t; i < b; ++i) {
            na->at(i).store(old->at(i).load(std::memory_order_relaxed),
                            std::memory_order_relaxed);
        }
        Array* raw = na.get();
        arrays_.push_back(std::move(na));   // 旧数组保留，避免悬垂访问
        array_.store(raw, std::memory_order_release);
        return raw;
    }

    std::atomic<std::size_t> top_{0};
    std::atomic<std::size_t> bottom_{0};
    std::atomic<Array*> array_{nullptr};
    std::vector<std::unique_ptr<Array>> arrays_;   // 仅所有者线程修改
};