/**
 * @file ads1263_config.h
 * @brief ADS1263 Compile-Time Configuration
 * @version 3.0.0
 * @date 2024
 * 
 * @details User-configurable options for memory, features, and performance.
 *          Modify these settings to customize the library for your application.
 * 
 * @note All settings are compile-time - no runtime overhead
 */

#ifndef ADS1263_CONFIG_H
#define ADS1263_CONFIG_H

/* ========================================================================== */
/*                          MEMORY CONFIGURATION                              */
/* ========================================================================== */

/**
 * @brief Enable double precision for voltage calculations
 * @note RP2350: Double is slower than float (no FPU acceleration)
 * @default 0 (use float)
 */
#define ADS1263_USE_DOUBLE_PRECISION    0

/**
 * @brief Enable internal data buffering
 * @note Useful for burst reading or data logging
 * @default 1 (enabled)
 */
#define ADS1263_ENABLE_BUFFER           1

/**
 * @brief Internal buffer size (number of samples)
 * @note Only used if ADS1263_ENABLE_BUFFER is enabled
 * @default 32 samples
 */
#define ADS1263_BUFFER_SIZE             32

/* ========================================================================== */
/*                         FEATURE CONFIGURATION                              */
/* ========================================================================== */

/**
 * @brief Enable ADC2 support (auxiliary 24-bit ADC)
 * @default 1 (enabled)
 */
#define ADS1263_ENABLE_ADC2             1

/**
 * @brief Enable GPIO functionality (4 GPIO pins)
 * @default 1 (enabled)
 */
#define ADS1263_ENABLE_GPIO             1

/**
 * @brief Enable IDAC functionality (current sources)
 * @default 1 (enabled)
 */
#define ADS1263_ENABLE_IDAC             1

/**
 * @brief Enable TDAC functionality (test DACs)
 * @default 1 (enabled)
 */
#define ADS1263_ENABLE_TDAC             1

/**
 * @brief Enable internal temperature sensor reading
 * @default 1 (enabled)
 */
#define ADS1263_ENABLE_TEMP_SENSOR      1

/**
 * @brief Enable CRC/Checksum validation
 * @default 1 (enabled)
 */
#define ADS1263_ENABLE_CRC              1

/* ========================================================================== */
/*                          API STYLE CONFIGURATION                           */
/* ========================================================================== */

/**
 * @brief Enable fluent interface (method chaining)
 * @note ads.setGain(...).setRate(...).startContinuous()
 * @default 1 (enabled)
 */
#define ADS1263_ENABLE_FLUENT_API       1

/**
 * @brief Enable builder pattern for initialization
 * @default 0 (disabled - optional feature)
 */
#define ADS1263_ENABLE_BUILDER_PATTERN  0

/* ========================================================================== */
/*                      RP2350-SPECIFIC OPTIMIZATIONS                         */
/* ========================================================================== */

/**
 * @brief Enable DMA support for SPI (RP2350 only)
 * @note Requires RP2350/RP2040 platform
 * @default 1 (enabled if platform detected)
 */
#if defined(ARDUINO_ARCH_RP2040) || defined(PICO_BOARD)
    #define ADS1263_ENABLE_DMA          1
#else
    #define ADS1263_ENABLE_DMA          0
#endif

/**
 * @brief Enable dual-core support (RP2350 only)
 * @note Runs state machine on Core 1
 * @default 0 (disabled - advanced feature)
 */
#define ADS1263_ENABLE_DUAL_CORE        0

/**
 * @brief Enable PIO (Programmable I/O) for precise timing
 * @note RP2350-specific feature
 * @default 0 (disabled - advanced feature)
 */
#define ADS1263_ENABLE_PIO              0

/* ========================================================================== */
/*                         TIMING CONFIGURATION                               */
/* ========================================================================== */

/**
 * @namespace ADS1263_TIMING
 * @brief Timing constants from datasheet (SBAS661C)
 * @note All values in microseconds unless specified
 */
namespace ADS1263_TIMING {
    // SPI Timing (Table 6, p.8)
    constexpr uint32_t SPI_SPACING_US           = 1;     // t_CSDC: CS high between commands
    constexpr uint32_t SPI_CS_SETUP_NS          = 10;     // t_CSSC: CS setup before SCLK
    constexpr uint32_t SPI_CS_HOLD_NS           = 10;     // t_SCCS: CS hold after SCLK
    
    // Reset Timing (Figure 78, p.75)
    constexpr uint32_t RESET_PULSE_US           = 5;      // t_RST: Reset pulse width (min 4 CLK)
    constexpr uint32_t RESET_RECOVERY_US        = 50000;  // t_STARTUP: Oscillator startup (typ 20ms -> 50ms)
    
    // Conversion Timing
    constexpr uint32_t CHANNEL_SWITCH_US        = 1;      // t_switch: Analog switch (typ 200ns, max 400ns)
    constexpr uint32_t COMMAND_EXECUTION_US     = 2;      // Command processing overhead
    
    // Timeout Values
    constexpr uint32_t CONVERSION_TIMEOUT_US    = 2000000; // 2 seconds (conservative)
    constexpr uint32_t CALIBRATION_TIMEOUT_US   = 5000000; // 5 seconds (per datasheet)
    constexpr uint32_t DRDY_POLL_INTERVAL_US    = 10;     // DRDY check interval
    constexpr uint32_t INIT_TIMEOUT_US          = 100000;  // 100ms initialization timeout
}

/* ========================================================================== */
/*                         DEBUG CONFIGURATION                                */
/* ========================================================================== */

/**
 * @brief Enable debug output via Serial
 * @default 0 (disabled in production)
 */
#define ADS1263_DEBUG                   0

/**
 * @brief Enable verbose state machine logging
 * @default 0 (disabled)
 */
#define ADS1263_DEBUG_STATE_MACHINE     0

/**
 * @brief Enable SPI transaction logging
 * @default 0 (disabled)
 */
#define ADS1263_DEBUG_SPI               0

/* ========================================================================== */
/*                         VALIDATION MACROS                                  */
/* ========================================================================== */

// Sanity checks
#if ADS1263_BUFFER_SIZE < 1
    #error "ADS1263_BUFFER_SIZE must be at least 1"
#endif

#if ADS1263_BUFFER_SIZE > 256
    #warning "ADS1263_BUFFER_SIZE > 256 may use excessive RAM"
#endif

#if ADS1263_ENABLE_DUAL_CORE && !defined(ARDUINO_ARCH_RP2040)
    #error "ADS1263_ENABLE_DUAL_CORE requires RP2040/RP2350 platform"
#endif

/* ========================================================================== */
/*                         CONDITIONAL INCLUDES                               */
/* ========================================================================== */

#if ADS1263_ENABLE_DMA
    // DMA headers will be included in implementation
#endif

#if ADS1263_ENABLE_DUAL_CORE
    #include <FreeRTOS.h>
    #include <task.h>
#endif

/* ========================================================================== */
/*                         HELPER MACROS                                      */
/* ========================================================================== */

#if ADS1263_DEBUG
    #define ADS1263_DEBUG_PRINT(...)    Serial.print(__VA_ARGS__)
    #define ADS1263_DEBUG_PRINTLN(...)  Serial.println(__VA_ARGS__)
#else
    #define ADS1263_DEBUG_PRINT(...)    
    #define ADS1263_DEBUG_PRINTLN(...)  
#endif

#if ADS1263_DEBUG_STATE_MACHINE
    #define ADS1263_DEBUG_STATE(state)  \
        Serial.print("State: "); Serial.println(state)
#else
    #define ADS1263_DEBUG_STATE(state)
#endif

/* ========================================================================== */
/*                         TYPE SELECTION                                     */
/* ========================================================================== */

#if ADS1263_USE_DOUBLE_PRECISION
    typedef double ads1263_float_t;
#else
    typedef float ads1263_float_t;
#endif

#endif // ADS1263_CONFIG_H
