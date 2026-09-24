#ifndef SPSC_QUEUE_H
#define SPSC_QUEUE_H

#include <stdint.h>

// Data Memory Barrier for Cortex-M33 (RP2350)
// Ensures all preceding memory accesses complete before subsequent ones begin.
#ifndef __dmb
#define __dmb() __asm volatile ("dmb" ::: "memory")
#endif

namespace mgf {

template<typename T, uint16_t N>
class SPSCQueue {
    T _buf[N];
    volatile uint16_t _head = 0; // Producer writes
    volatile uint16_t _tail = 0; // Consumer writes

public:
    bool push(const T& item) {
        uint16_t next_head = (_head + 1) % N;
        if (next_head == _tail) return false; // Full
        _buf[_head] = item;
        __dmb(); // Ensure data is written before head is published
        _head = next_head;
        return true;
    }

    bool pop(T& item) {
        if (_head == _tail) return false; // Empty
        item = _buf[_tail];
        __dmb(); // Ensure data is read before tail is published
        _tail = (_tail + 1) % N;
        return true;
    }

    uint16_t count() const {
        uint16_t h = _head;
        uint16_t t = _tail;
        if (h >= t) return h - t;
        return N - t + h;
    }

    bool empty() const {
        return _head == _tail;
    }

    bool full() const {
        return ((_head + 1) % N) == _tail;
    }
    
    void clear() {
        _tail = _head;
    }
};

} // namespace mgf

#endif // SPSC_QUEUE_H
