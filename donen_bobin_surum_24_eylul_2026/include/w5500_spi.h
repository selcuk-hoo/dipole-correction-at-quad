#ifndef W5500_SPI_H
#define W5500_SPI_H

/**
 * @file w5500_spi.h
 * @brief W5500 SPI Platform Adapter for Pico SDK
 * @details Provides the SPI callback functions required by the Wiznet ioLibrary_Driver.
 *          Call w5500_spi_init() before using any Wiznet library functions.
 */

#include <stdint.h>
#include "pico/stdlib.h"
#include "hardware/spi.h"
#include "hardware/gpio.h"

// Pin definitions (must match hardware)
#define W5500_SPI_PORT  spi0
#define W5500_SPI_FREQ  33000000  // 33 MHz (W5500 max = 80 MHz)

#define W5500_MISO_PIN  16
#define W5500_CS_PIN    17
#define W5500_SCK_PIN   18
#define W5500_MOSI_PIN  19
#define W5500_RST_PIN   20
#define W5500_INT_PIN   21

// Forward declarations for ioLibrary callbacks
static void w5500_cs_select(void);
static void w5500_cs_deselect(void);
static void w5500_spi_read_burst(uint8_t *buf, uint16_t len);
static void w5500_spi_write_burst(uint8_t *buf, uint16_t len);
static uint8_t w5500_spi_read_byte(void);
static void w5500_spi_write_byte(uint8_t data);

/**
 * @brief Initialize SPI hardware and W5500 chip
 * @details Sets up SPI0 pins, performs hardware reset, and registers
 *          callbacks with the Wiznet ioLibrary.
 */
static inline void w5500_spi_init(void) {
    // Initialize SPI peripheral
    spi_init(W5500_SPI_PORT, W5500_SPI_FREQ);
    
    // Configure SPI pins
    gpio_set_function(W5500_MISO_PIN, GPIO_FUNC_SPI);
    gpio_set_function(W5500_SCK_PIN,  GPIO_FUNC_SPI);
    gpio_set_function(W5500_MOSI_PIN, GPIO_FUNC_SPI);
    
    // CS is manual GPIO (not SPI hardware CS)
    gpio_init(W5500_CS_PIN);
    gpio_set_dir(W5500_CS_PIN, GPIO_OUT);
    gpio_put(W5500_CS_PIN, 1);  // Deselect
    
    // INT pin (active low, directly polled)
    gpio_init(W5500_INT_PIN);
    gpio_set_dir(W5500_INT_PIN, GPIO_IN);
    gpio_pull_up(W5500_INT_PIN);
    
    // Hardware reset sequence
    gpio_init(W5500_RST_PIN);
    gpio_set_dir(W5500_RST_PIN, GPIO_OUT);
    gpio_put(W5500_RST_PIN, 0);
    sleep_ms(100);
    gpio_put(W5500_RST_PIN, 1);
    sleep_ms(500);  // Wait for W5500 PLL lock and internal init
    
    // Register ioLibrary callbacks
    reg_wizchip_cs_cbfunc(w5500_cs_select, w5500_cs_deselect);
    reg_wizchip_spi_cbfunc(w5500_spi_read_byte, w5500_spi_write_byte);
    reg_wizchip_spiburst_cbfunc(w5500_spi_read_burst, w5500_spi_write_burst);
}

// ===== Callback Implementations =====

static void w5500_cs_select(void) {
    gpio_put(W5500_CS_PIN, 0);
}

static void w5500_cs_deselect(void) {
    gpio_put(W5500_CS_PIN, 1);
}

static uint8_t w5500_spi_read_byte(void) {
    uint8_t val = 0;
    spi_read_blocking(W5500_SPI_PORT, 0x00, &val, 1);
    return val;
}

static void w5500_spi_write_byte(uint8_t data) {
    spi_write_blocking(W5500_SPI_PORT, &data, 1);
}

static void w5500_spi_read_burst(uint8_t *buf, uint16_t len) {
    spi_read_blocking(W5500_SPI_PORT, 0x00, buf, len);
}

static void w5500_spi_write_burst(uint8_t *buf, uint16_t len) {
    spi_write_blocking(W5500_SPI_PORT, buf, len);
}

#endif // W5500_SPI_H
