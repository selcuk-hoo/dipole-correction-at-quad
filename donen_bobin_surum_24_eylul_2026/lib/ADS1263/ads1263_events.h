/**
 * @file ads1263_events.h
 * @brief ADS1263 Event System
 * @version 3.0.0
 * @date 2024
 * 
 * @details Event-driven callback system for asynchronous operations.
 *          Provides clean API for non-blocking event handling.
 */

#ifndef ADS1263_EVENTS_H
#define ADS1263_EVENTS_H

#include <stdint.h>
#include "ads1263_types.h"

/* ========================================================================== */
/*                          EVENT DATA STRUCTURES                             */
/* ========================================================================== */

/**
 * @brief ADC1 Data Ready Event
 * @note Dispatched when new ADC1 conversion data is available
 */
typedef struct {
    int32_t raw_data;               ///< Raw 32-bit ADC code
    ads1263_float_t voltage;        ///< Converted voltage (V)
    uint8_t status_byte;            ///< Status byte from device
    ads1263_status_t status;        ///< Parsed status flags
    uint32_t timestamp_us;          ///< Timestamp (micros())
    uint8_t crc_byte;               ///< Raw CRC/checksum byte from ADS1263 (for end-to-end validation)
} ads1263_data_event_t;

/**
 * @brief ADC2 Data Ready Event
 * @note Dispatched when new ADC2 conversion data is available
 */
typedef struct {
    int32_t raw_data;               ///< Raw 24-bit ADC code (sign-extended to 32-bit)
    ads1263_float_t voltage;        ///< Converted voltage (V)
    uint8_t status_byte;            ///< Status byte from device
    uint32_t timestamp_us;          ///< Timestamp (micros())
} ads1263_adc2_event_t;

/**
 * @brief Error Event
 * @note Dispatched when an error occurs
 */
typedef struct {
    ads1263_error_t error_code;     ///< Error code
    const char* error_message;      ///< Human-readable error description
    uint8_t state;                  ///< State when error occurred
    uint32_t timestamp_us;          ///< Timestamp (micros())
} ads1263_error_event_t;

/**
 * @brief Calibration Complete Event
 * @note Dispatched when calibration finishes
 */
typedef struct {
    ads1263_cal_type_t cal_type;    ///< Type of calibration performed
    bool success;                   ///< Calibration successful
    ads1263_cal_data_t cal_data;    ///< Calibration data (if available)
    uint32_t duration_us;           ///< Calibration duration
} ads1263_cal_event_t;

/**
 * @brief Initialization Complete Event
 * @note Dispatched when device initialization finishes
 */
typedef struct {
    bool success;                   ///< Initialization successful
    uint8_t device_id;              ///< Device ID register value
    uint32_t duration_us;           ///< Initialization duration
} ads1263_init_event_t;

/**
 * @brief Alarm Event
 * @note Dispatched when hardware alarm is detected
 */
typedef struct {
    uint8_t alarm_flags;            ///< Raw alarm flags from status byte
    bool ref_alarm;                 ///< Reference voltage alarm
    bool pga_low_alarm;             ///< PGA output low alarm
    bool pga_high_alarm;            ///< PGA output high alarm
    bool pga_diff_alarm;            ///< PGA differential alarm
    uint32_t timestamp_us;          ///< Timestamp (micros())
} ads1263_alarm_event_t;

/* ========================================================================== */
/*                          CALLBACK FUNCTION TYPES                           */
/* ========================================================================== */

/**
 * @brief Initialization Complete Callback
 * @param event Pointer to initialization event data
 * 
 * @note Called once after begin() completes successfully or fails
 * @warning Keep callback execution time short (<1ms recommended)
 */
typedef void (*ads1263_init_callback_t)(const ads1263_init_event_t* event);

/**
 * @brief ADC1 Data Ready Callback
 * @param event Pointer to data event
 * 
 * @note Called every time new ADC1 data is available
 * @warning Keep callback execution time short to avoid missing samples
 * @warning Do NOT call blocking functions (delay, Serial.print, etc.)
 */
typedef void (*ads1263_data_callback_t)(const ads1263_data_event_t* event);

/**
 * @brief ADC2 Data Ready Callback
 * @param event Pointer to ADC2 data event
 * 
 * @note Called every time new ADC2 data is available
 * @warning Keep callback execution time short
 */
typedef void (*ads1263_adc2_callback_t)(const ads1263_adc2_event_t* event);

/**
 * @brief Error Callback
 * @param event Pointer to error event
 * 
 * @note Called when any error occurs
 * @note Multiple errors may be reported in sequence
 */
typedef void (*ads1263_error_callback_t)(const ads1263_error_event_t* event);

/**
 * @brief Calibration Complete Callback
 * @param event Pointer to calibration event
 * 
 * @note Called after calibration completes or times out
 */
typedef void (*ads1263_cal_callback_t)(const ads1263_cal_event_t* event);

/**
 * @brief Alarm Callback
 * @param event Pointer to alarm event
 * 
 * @note Called when hardware alarm condition is detected
 * @note Check individual alarm flags to determine cause
 */
typedef void (*ads1263_alarm_callback_t)(const ads1263_alarm_event_t* event);

/**
 * @brief Channel Switch Complete Callback
 * @param channel_pos Positive input channel
 * @param channel_neg Negative input channel
 * 
 * @note Called after channel switch settling time
 * @note Useful for multi-channel scanning applications
 */
typedef void (*ads1263_channel_callback_t)(ads1263_input_t channel_pos, 
                                           ads1263_input_t channel_neg);

/* ========================================================================== */
/*                          CALLBACK REGISTRATION                             */
/* ========================================================================== */

/**
 * @brief Callback Registration Structure
 * @note Internal use - stores all registered callbacks
 */
typedef struct {
    ads1263_init_callback_t init_cb;
    ads1263_data_callback_t data_cb;
    ads1263_adc2_callback_t adc2_cb;
    ads1263_error_callback_t error_cb;
    ads1263_cal_callback_t cal_cb;
    ads1263_alarm_callback_t alarm_cb;
    ads1263_channel_callback_t channel_cb;
} ads1263_callbacks_t;

/* ========================================================================== */
/*                          CALLBACK USAGE EXAMPLES                           */
/* ========================================================================== */

/**
 * @example Basic Data Callback
 * @code
 * void onDataReady(const ads1263_data_event_t* event) {
 *     // Store voltage in global variable for processing in loop()
 *     global_voltage = event->voltage;
 *     global_data_ready = true;
 * }
 * 
 * void setup() {
 *     ads.onDataReady(onDataReady);
 *     ads.begin();
 *     ads.startContinuous();
 * }
 * 
 * void loop() {
 *     ads.update();  // Calls callbacks when events occur
 *     
 *     if (global_data_ready) {
 *         // Process voltage
 *         Serial.println(global_voltage, 6);
 *         global_data_ready = false;
 *     }
 * }
 * @endcode
 */

/**
 * @example Error Handling
 * @code
 * void onError(const ads1263_error_event_t* event) {
 *     Serial.print("ADS1263 Error: ");
 *     Serial.println(event->error_message);
 *     
 *     // Handle specific errors
 *     switch(event->error_code) {
 *         case ADS1263_ERROR_TIMEOUT:
 *             // Reinitialize or retry
 *             break;
 *         case ADS1263_ERROR_CRC:
 *             // Data integrity issue
 *             break;
 *         default:
 *             break;
 *     }
 * }
 * 
 * void setup() {
 *     ads.onError(onError);
 * }
 * @endcode
 */

/**
 * @example Multi-Channel Scanning
 * @code
 * const ads1263_input_t channels[][2] = {
 *     {ADS1263_INPUT_AIN0, ADS1263_INPUT_AIN1},
 *     {ADS1263_INPUT_AIN2, ADS1263_INPUT_AIN3},
 *     {ADS1263_INPUT_AIN4, ADS1263_INPUT_AIN5},
 * };
 * uint8_t current_channel = 0;
 * 
 * void onDataReady(const ads1263_data_event_t* event) {
 *     // Store reading for current channel
 *     channel_readings[current_channel] = event->voltage;
 *     
 *     // Move to next channel
 *     current_channel = (current_channel + 1) % 3;
 *     ads.setChannel(channels[current_channel][0], 
 *                    channels[current_channel][1]);
 *     ads.startSingleConversion();
 * }
 * @endcode
 */

/**
 * @example Calibration Workflow
 * @code
 * void onCalComplete(const ads1263_cal_event_t* event) {
 *     if (event->success) {
 *         Serial.println("Calibration successful");
 *         // Proceed with measurements
 *         ads.startContinuous();
 *     } else {
 *         Serial.println("Calibration failed");
 *         // Retry or error handling
 *     }
 * }
 * 
 * void setup() {
 *     ads.onInitComplete([](const ads1263_init_event_t* e) {
 *         if (e->success) {
 *             // Start calibration after initialization
 *             ads.calibrateOffset();
 *         }
 *     });
 *     ads.onCalibrationComplete(onCalComplete);
 *     ads.begin();
 * }
 * @endcode
 */

#endif // ADS1263_EVENTS_H
