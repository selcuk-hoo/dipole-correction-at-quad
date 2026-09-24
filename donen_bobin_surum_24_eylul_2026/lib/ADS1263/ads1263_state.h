/**
 * @file ads1263_state.h
 * @brief ADS1263 State Machine and Timer Management
 * @version 3.1.0
 * @date 2024
 * * @details Non-blocking state machine implementation with precise timing control.
 * Zero delay() calls - all timing via micros() comparison.
 * Updated with substates for Temperature, GPIO, and Debug operations.
 */

#ifndef ADS1263_STATE_H
#define ADS1263_STATE_H

#include <stdint.h>
#include "pico/stdlib.h"

/* ========================================================================== */
/* STATE DEFINITIONS                                 */
/* ========================================================================== */

/**
 * @brief Main State Machine States
 * @note States are designed for non-blocking operation
 */
typedef enum {
    // Initialization States
    ADS1263_STATE_UNINITIALIZED,        ///< Device not initialized
    ADS1263_STATE_INIT_START,           ///< Begin initialization sequence
    ADS1263_STATE_INIT_RESET_PULSE,     ///< Reset pin LOW
    ADS1263_STATE_INIT_RESET_WAIT,      ///< Waiting for oscillator startup
    ADS1263_STATE_INIT_ID_CHECK,        ///< Reading and validating device ID
    ADS1263_STATE_INIT_CONFIG_INTERFACE,///< Configuring INTERFACE register
    ADS1263_STATE_INIT_CONFIG_POWER,    ///< Configuring POWER register
    ADS1263_STATE_INIT_COMPLETE,        ///< Initialization successful
    
    // Idle State
    ADS1263_STATE_IDLE,                 ///< Ready for commands
    
    // Conversion States
    ADS1263_STATE_START_CONVERSION,     ///< Sending START command
    ADS1263_STATE_CONVERTING,           ///< Waiting for DRDY
    ADS1263_STATE_DATA_AVAILABLE,       ///< DRDY detected, data ready
    ADS1263_STATE_READING_DATA,         ///< SPI read in progress
    ADS1263_STATE_READING_DATA_COMPLETE,///< Data read complete, processing
    
    // Channel Switching
    ADS1263_STATE_SWITCHING_CHANNEL,    ///< Channel switch settling
    ADS1263_STATE_CHANNEL_SWITCHED,     ///< Channel switch complete
    
    // Calibration States
    ADS1263_STATE_CAL_START,            ///< Starting calibration
    ADS1263_STATE_CAL_WAIT_DRDY,        ///< Waiting for calibration DRDY
    ADS1263_STATE_CAL_COMPLETE,         ///< Calibration finished
    
    // ADC2 States
    ADS1263_STATE_ADC2_READING,         ///< Reading ADC2 data
    
    // Special Operations States (New)
    ADS1263_STATE_TEMP_READING,         ///< Internal Temperature reading sequence
    ADS1263_STATE_GPIO_READING,         ///< GPIO reading sequence
    ADS1263_STATE_REG_DUMP,             ///< Register dump sequence
    
    // Error States
    ADS1263_STATE_ERROR,                ///< Error occurred
    ADS1263_STATE_ERROR_RECOVERY        ///< Attempting recovery
} ads1263_state_t;

/**
 * @brief Sub-states for Complex Operations
 * @note Used within main states for multi-step operations
 */
typedef enum {
    ADS1263_SUBSTATE_NONE,              ///< No sub-state
    
    // Calibration Sub-states
    ADS1263_SUBSTATE_CAL_OFFSET,        ///< Offset calibration
    ADS1263_SUBSTATE_CAL_GAIN,          ///< Gain calibration
    ADS1263_SUBSTATE_CAL_SYSTEM,        ///< System calibration
    
    // Temperature Reading Sub-states (FIXED & EXPANDED)
    ADS1263_SUBSTATE_TEMP_START,        ///< Begin temp read sequence
    ADS1263_SUBSTATE_TEMP_CONFIG_MUX,   ///< Set MUX to Temp Sensor
    ADS1263_SUBSTATE_TEMP_CONVERT,      ///< Start conversion
    ADS1263_SUBSTATE_TEMP_WAIT,         ///< Wait for DRDY
    ADS1263_SUBSTATE_TEMP_READ,         ///< Read Data
    ADS1263_SUBSTATE_TEMP_RESTORE,      ///< Restore previous config
    
    // Register Dump Sub-states (NEW)
    ADS1263_SUBSTATE_REG_READ_NEXT,     ///< Read next register
    ADS1263_SUBSTATE_REG_READ_WAIT,     ///< Wait for SPI read
    
    // GPIO Read Sub-states (NEW)
    ADS1263_SUBSTATE_GPIO_CMD,          ///< Send GPIO read command
    ADS1263_SUBSTATE_GPIO_RESULT        ///< Process result
} ads1263_substate_t;

/* ========================================================================== */
/* PENDING OPERATION TYPES                           */
/* ========================================================================== */

/**
 * @brief Pending Operation Types
 * @note Operations queued for execution after timing requirements met
 */
typedef enum {
    PENDING_OP_NONE,                    ///< No pending operation
    PENDING_OP_COMMAND,                 ///< Send command
    PENDING_OP_REG_WRITE,               ///< Write register
    PENDING_OP_REG_READ,                ///< Read register
    PENDING_OP_DATA_READ,               ///< Read conversion data
    PENDING_OP_ADC2_READ                ///< Read ADC2 data
} pending_op_type_t;

/**
 * @brief Pending Operation Structure
 * @note Stores queued operation details
 */
typedef struct {
    pending_op_type_t type;             ///< Operation type
    uint8_t reg_or_cmd;                 ///< Register address or command
    uint8_t data;                       ///< Data to write (for REG_WRITE)
    uint32_t queued_time_us;            ///< Time operation was queued
} pending_operation_t;

/* ========================================================================== */
/* TIMER MANAGER CLASS                               */
/* ========================================================================== */

/**
 * @brief Non-Blocking Timer Manager
 * @details Provides microsecond-precision timing without blocking
 */
class TimerManager {
private:
    uint32_t _start_time_us;            ///< Start time (micros())
    uint32_t _duration_us;              ///< Duration (microseconds)
    bool _active;                       ///< Timer is running
    
public:
    TimerManager() : _start_time_us(0), _duration_us(0), _active(false) {}
    
    inline void start(uint32_t duration_us) {
        _start_time_us = time_us_32();
        _duration_us = duration_us;
        _active = true;
    }
    
    inline bool isExpired() const {
        if (!_active) return false;
        uint32_t current = time_us_32();
        uint32_t elapsed;
        if (current >= _start_time_us) {
            elapsed = current - _start_time_us;
        } else {
            elapsed = (UINT32_MAX - _start_time_us) + current + 1;
        }
        return elapsed >= _duration_us;
    }
    
    inline void stop() { _active = false; }
    
    inline uint32_t elapsed() const {
        if (!_active) return 0;
        uint32_t current = time_us_32();
        return (current >= _start_time_us) ? (current - _start_time_us) : ((UINT32_MAX - _start_time_us) + current + 1);
    }
    
    inline void restart() { if (_active) _start_time_us = time_us_32(); }
    inline bool isActive() const { return _active; }
};

/* ========================================================================== */
/* RATE LIMITER CLASS                                */
/* ========================================================================== */

class RateLimiter {
private:
    uint32_t _last_access_us;           ///< Last access time
    uint32_t _min_interval_us;          ///< Minimum interval
    
public:
    RateLimiter(uint32_t min_interval_us = 1) 
        : _last_access_us(0), _min_interval_us(min_interval_us) {}
    
    inline bool canAccess() const {
        uint32_t current = time_us_32();
        uint32_t elapsed = (current >= _last_access_us) ? (current - _last_access_us) : ((UINT32_MAX - _last_access_us) + current + 1);
        return elapsed >= _min_interval_us;
    }
    
    inline void markAccess() { _last_access_us = time_us_32(); }
};

/* ========================================================================== */
/* STATE MACHINE HELPERS                             */
/* ========================================================================== */

inline const char* ads1263_state_to_string(ads1263_state_t state) {
    switch(state) {
        case ADS1263_STATE_UNINITIALIZED: return "UNINITIALIZED";
        case ADS1263_STATE_IDLE: return "IDLE";
        case ADS1263_STATE_CONVERTING: return "CONVERTING";
        case ADS1263_STATE_DATA_AVAILABLE: return "DATA_AVAILABLE";
        case ADS1263_STATE_TEMP_READING: return "TEMP_READING";
        case ADS1263_STATE_GPIO_READING: return "GPIO_READING";
        case ADS1263_STATE_REG_DUMP: return "REG_DUMP";
        case ADS1263_STATE_ERROR: return "ERROR";
        default: return "OTHER";
    }
}

#endif // ADS1263_STATE_H