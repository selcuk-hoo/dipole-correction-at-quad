#ifndef RS485_DMA_H
#define RS485_DMA_H

#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
#include "pico/stdlib.h"
#include "hardware/uart.h"
#include "hardware/dma.h"
#include "hardware/gpio.h"

namespace mgf {

class RS485DMA {
    uart_inst_t* _uart;
    uint _tx_pin;
    uint _rx_pin;
    uint _de_tx_pin;
    uint _de_rx_pin;
    
    int _dma_tx;
    int _dma_rx;
    dma_channel_config _dma_tx_config;
    dma_channel_config _dma_rx_config;
    
    uint8_t* _rx_buf;
    size_t _rx_buf_size;

public:
    RS485DMA() : _uart(nullptr), _dma_tx(-1), _dma_rx(-1), _rx_buf(nullptr), _rx_buf_size(0) {}

    void begin(uart_inst_t* uart, uint baud, uint tx_pin, uint rx_pin, uint de_tx_pin, uint de_rx_pin, uint8_t* rx_buf, size_t rx_buf_size) {
        _uart = uart;
        _tx_pin = tx_pin;
        _rx_pin = rx_pin;
        _de_tx_pin = de_tx_pin;
        _de_rx_pin = de_rx_pin;
        _rx_buf = rx_buf;
        _rx_buf_size = rx_buf_size;

        uart_init(_uart, baud);
        gpio_set_function(_tx_pin, GPIO_FUNC_UART);
        gpio_set_function(_rx_pin, GPIO_FUNC_UART);

        // Turn off UART FIFO for reliable DMA (if needed)
        // uart_set_fifo_enabled(_uart, false); // Optional, usually better left enabled for UART

        // DE pins - permanently enable full duplex
        if (_de_tx_pin != 255) {
            gpio_init(_de_tx_pin);
            gpio_set_dir(_de_tx_pin, GPIO_OUT);
            gpio_put(_de_tx_pin, 1); // TX always enabled
        }
        if (_de_rx_pin != 255) {
            gpio_init(_de_rx_pin);
            gpio_set_dir(_de_rx_pin, GPIO_OUT);
            gpio_put(_de_rx_pin, 0); // RX always enabled (Low enables RE\ on MAX3485)
        }

        // Setup RX DMA ring
        _dma_rx = dma_claim_unused_channel(true);
        _dma_rx_config = dma_channel_get_default_config(_dma_rx);
        channel_config_set_transfer_data_size(&_dma_rx_config, DMA_SIZE_8);
        channel_config_set_read_increment(&_dma_rx_config, false);
        channel_config_set_write_increment(&_dma_rx_config, true);
        
        // Find alignment for ring buffer
        uint ring_bits = 0;
        size_t s = _rx_buf_size;
        while (s > 1) { s >>= 1; ring_bits++; }
        channel_config_set_ring(&_dma_rx_config, true, ring_bits); // Ring on write

        channel_config_set_dreq(&_dma_rx_config, uart_get_index(_uart) ? DREQ_UART1_RX : DREQ_UART0_RX);

        dma_channel_configure(
            _dma_rx,
            &_dma_rx_config,
            _rx_buf,                  // Dest
            &uart_get_hw(_uart)->dr, // Source
            0xFFFFFFFF,              // Infinite
            true                     // Start
        );

        // Setup TX DMA
        _dma_tx = dma_claim_unused_channel(true);
        _dma_tx_config = dma_channel_get_default_config(_dma_tx);
        channel_config_set_transfer_data_size(&_dma_tx_config, DMA_SIZE_8);
        channel_config_set_read_increment(&_dma_tx_config, true);
        channel_config_set_write_increment(&_dma_tx_config, false);
        channel_config_set_dreq(&_dma_tx_config, uart_get_index(_uart) ? DREQ_UART1_TX : DREQ_UART0_TX);
    }

    size_t rx_write_pos() const {
        // Offset from buffer start
        return (size_t)((uint8_t*)dma_channel_hw_addr(_dma_rx)->write_addr - _rx_buf);
    }

    bool is_tx_busy() const {
        if (dma_channel_is_busy(_dma_tx)) return true;
        // Also wait for UART TX FIFO + shift register to fully drain
        return (uart_get_hw(_uart)->fr & UART_UARTFR_BUSY_BITS) != 0;
    }

    bool send(const uint8_t* data, size_t len) {
        if (is_tx_busy()) return false;
        dma_channel_configure(
            _dma_tx,
            &_dma_tx_config,
            &uart_get_hw(_uart)->dr, // Dest
            data,                    // Source
            len,                     // Count
            true                     // Start
        );
        return true;
    }
};

} // namespace mgf

#endif // RS485_DMA_H
