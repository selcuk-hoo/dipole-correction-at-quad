/**
 * @file ads1263_types.h
 * @brief ADS1263 Type Definitions
 * @version 3.0.0
 * @date 2024
 * 
 * @details Enumerations, structures, and type definitions for ADS1263 driver.
 *          Provides type-safe API and clear documentation.
 */

#ifndef ADS1263_TYPES_H
#define ADS1263_TYPES_H

#include <stdint.h>
#include "ads1263_config.h"

/* ========================================================================== */
/*                          ERROR CODES                                       */
/* ========================================================================== */

/**
 * @brief Error codes returned by ADS1263 functions
 */
typedef enum {
    ADS1263_OK              = 0,    ///< Success
    ADS1263_ERROR_TIMEOUT   = -1,   ///< Operation timed out
    ADS1263_ERROR_CRC       = -2,   ///< CRC/Checksum error
    ADS1263_ERROR_SPI       = -3,   ///< SPI communication error
    ADS1263_ERROR_ID        = -4,   ///< Invalid device ID
    ADS1263_ERROR_RANGE     = -5,   ///< Parameter out of range
    ADS1263_ERROR_CONFIG    = -6,   ///< Invalid configuration
    ADS1263_ERROR_STATE     = -7,   ///< Invalid state for operation
    ADS1263_ERROR_OVERFLOW  = -8,   ///< Buffer overflow
    ADS1263_ERROR_BUSY      = -9,   ///< Device busy
    ADS1263_ERROR_NOT_INIT  = -10,  ///< Device not initialized
    ADS1263_ERROR_INVALID   = -11   ///< Invalid parameter
} ads1263_error_t;

/* ========================================================================== */
/*                          ADC1 CONFIGURATION                                */
/* ========================================================================== */

/**
 * @brief ADC1 Gain Settings (PGA)
 * @note Datasheet Table 38, p.72
 */
typedef enum {
    ADS1263_GAIN_1  = 0,    ///< Gain = 1 (±2.5V with internal ref)
    ADS1263_GAIN_2  = 1,    ///< Gain = 2 (±1.25V)
    ADS1263_GAIN_4  = 2,    ///< Gain = 4 (±625mV)
    ADS1263_GAIN_8  = 3,    ///< Gain = 8 (±312.5mV)
    ADS1263_GAIN_16 = 4,    ///< Gain = 16 (±156.25mV)
    ADS1263_GAIN_32 = 5     ///< Gain = 32 (±78.125mV)
} ads1263_gain_t;

/**
 * @brief ADC1 Data Rates (Samples Per Second)
 * @note Datasheet Table 38, p.72
 */
typedef enum {
    ADS1263_RATE_2_5   = 0,     ///< 2.5 SPS
    ADS1263_RATE_5     = 1,     ///< 5 SPS
    ADS1263_RATE_10    = 2,     ///< 10 SPS
    ADS1263_RATE_16_6  = 3,     ///< 16.6 SPS
    ADS1263_RATE_20    = 4,     ///< 20 SPS
    ADS1263_RATE_50    = 5,     ///< 50 SPS
    ADS1263_RATE_60    = 6,     ///< 60 SPS
    ADS1263_RATE_100   = 7,     ///< 100 SPS
    ADS1263_RATE_400   = 8,     ///< 400 SPS
    ADS1263_RATE_1200  = 9,     ///< 1200 SPS
    ADS1263_RATE_2400  = 10,    ///< 2400 SPS
    ADS1263_RATE_4800  = 11,    ///< 4800 SPS
    ADS1263_RATE_7200  = 12,    ///< 7200 SPS
    ADS1263_RATE_14400 = 13,    ///< 14400 SPS (Sinc1 only)
    ADS1263_RATE_19200 = 14,    ///< 19200 SPS (Sinc1 only)
    ADS1263_RATE_38400 = 15     ///< 38400 SPS (Sinc1 only)
} ads1263_rate_t;

/**
 * @brief Digital Filter Types
 * @note Datasheet Table 37, p.71
 */
typedef enum {
    ADS1263_FILTER_SINC1 = 0,   ///< Sinc1 (fastest settling, lowest rejection)
    ADS1263_FILTER_SINC2 = 1,   ///< Sinc2
    ADS1263_FILTER_SINC3 = 2,   ///< Sinc3 (good balance)
    ADS1263_FILTER_SINC4 = 3,   ///< Sinc4 (best rejection)
    ADS1263_FILTER_FIR   = 4    ///< FIR (valid for ≤20 SPS only)
} ads1263_filter_t;

/**
 * @brief Input Chop Mode
 * @note Datasheet Table 36, p.70
 */
typedef enum {
    ADS1263_CHOP_OFF   = 0,     ///< Chop disabled
    ADS1263_CHOP_INPUT = 1,     ///< Input chop only
    ADS1263_CHOP_IDAC  = 2,     ///< IDAC rotation only
    ADS1263_CHOP_BOTH  = 3      ///< Input chop + IDAC rotation
} ads1263_chop_mode_t;

/**
 * @brief Conversion Mode
 * @note Datasheet Table 36, p.70
 */
typedef enum {
    ADS1263_CONV_CONTINUOUS = 0,    ///< Continuous conversion
    ADS1263_CONV_PULSE      = 1     ///< Pulse conversion (triggered)
} ads1263_conv_mode_t;

/**
 * @brief Conversion Delay
 * @note Datasheet Table 36, p.70
 */
typedef enum {
    ADS1263_DELAY_NONE  = 0,    ///< No delay
    ADS1263_DELAY_8_7US = 1,    ///< 8.7 µs
    ADS1263_DELAY_17US  = 2,    ///< 17 µs
    ADS1263_DELAY_35US  = 3,    ///< 35 µs
    ADS1263_DELAY_69US  = 4,    ///< 69 µs
    ADS1263_DELAY_139US = 5,    ///< 139 µs
    ADS1263_DELAY_278US = 6,    ///< 278 µs
    ADS1263_DELAY_555US = 7     ///< 555 µs
} ads1263_delay_t;

/* ========================================================================== */
/*                          INPUT MULTIPLEXER                                 */
/* ========================================================================== */

/**
 * @brief Input Multiplexer Options
 * @note Datasheet Table 39, p.73
 */
typedef enum {
    ADS1263_INPUT_AIN0          = 0x00, ///< AIN0
    ADS1263_INPUT_AIN1          = 0x01, ///< AIN1
    ADS1263_INPUT_AIN2          = 0x02, ///< AIN2
    ADS1263_INPUT_AIN3          = 0x03, ///< AIN3
    ADS1263_INPUT_AIN4          = 0x04, ///< AIN4
    ADS1263_INPUT_AIN5          = 0x05, ///< AIN5
    ADS1263_INPUT_AIN6          = 0x06, ///< AIN6
    ADS1263_INPUT_AIN7          = 0x07, ///< AIN7
    ADS1263_INPUT_AIN8          = 0x08, ///< AIN8
    ADS1263_INPUT_AIN9          = 0x09, ///< AIN9
    ADS1263_INPUT_AINCOM        = 0x0A, ///< AINCOM
    ADS1263_INPUT_TEMP_P        = 0x0B, ///< Temperature sensor positive
    ADS1263_INPUT_TEMP_N        = 0x0C, ///< Temperature sensor negative
    ADS1263_INPUT_ANALOG_PWR_P  = 0x0D, ///< Analog supply monitor positive
    ADS1263_INPUT_ANALOG_PWR_N  = 0x0E, ///< Analog supply monitor negative
    ADS1263_INPUT_FLOAT         = 0x0F  ///< Floating (disconnected)
} ads1263_input_t;

/* ========================================================================== */
/*                          REFERENCE CONFIGURATION                           */
/* ========================================================================== */

/**
 * @brief Reference Positive Input
 * @note Datasheet Table 45, p.76
 */
typedef enum {
    ADS1263_REFP_INTERNAL   = 0,    ///< Internal 2.5V reference
    ADS1263_REFP_AIN0       = 1,    ///< External AIN0
    ADS1263_REFP_AIN2       = 2,    ///< External AIN2
    ADS1263_REFP_AIN4       = 3,    ///< External AIN4
    ADS1263_REFP_AVDD       = 4     ///< AVDD supply
} ads1263_refp_t;

/**
 * @brief Reference Negative Input
 * @note Datasheet Table 45, p.76
 */
typedef enum {
    ADS1263_REFN_INTERNAL   = 0,    ///< Internal 2.5V reference
    ADS1263_REFN_AIN1       = 1,    ///< External AIN1
    ADS1263_REFN_AIN3       = 2,    ///< External AIN3
    ADS1263_REFN_AIN5       = 3,    ///< External AIN5
    ADS1263_REFN_AVSS       = 4     ///< AVSS ground
} ads1263_refn_t;

/* ========================================================================== */
/*                          ADC2 CONFIGURATION                                */
/* ========================================================================== */

/**
 * @brief ADC2 Data Rates
 * @note Datasheet Table 51, p.79
 */
typedef enum {
    ADS1263_ADC2_RATE_10  = 0,  ///< 10 SPS
    ADS1263_ADC2_RATE_100 = 1,  ///< 100 SPS
    ADS1263_ADC2_RATE_400 = 2,  ///< 400 SPS
    ADS1263_ADC2_RATE_800 = 3   ///< 800 SPS
} ads1263_adc2_rate_t;

/**
 * @brief ADC2 Gain Settings
 * @note Datasheet Table 51, p.79
 */
typedef enum {
    ADS1263_ADC2_GAIN_1   = 0,  ///< Gain = 1
    ADS1263_ADC2_GAIN_2   = 1,  ///< Gain = 2
    ADS1263_ADC2_GAIN_4   = 2,  ///< Gain = 4
    ADS1263_ADC2_GAIN_8   = 3,  ///< Gain = 8
    ADS1263_ADC2_GAIN_16  = 4,  ///< Gain = 16
    ADS1263_ADC2_GAIN_32  = 5,  ///< Gain = 32
    ADS1263_ADC2_GAIN_64  = 6,  ///< Gain = 64
    ADS1263_ADC2_GAIN_128 = 7   ///< Gain = 128
} ads1263_adc2_gain_t;

/**
 * @brief ADC2 Reference Selection
 * @note Datasheet Table 51, p.79
 */
typedef enum {
    ADS1263_ADC2_REF_INTERNAL       = 0,    ///< Internal 2.5V
    ADS1263_ADC2_REF_AIN0_AIN1      = 1,    ///< External AIN0/AIN1
    ADS1263_ADC2_REF_AIN2_AIN3      = 2,    ///< External AIN2/AIN3
    ADS1263_ADC2_REF_AIN4_AIN5      = 3,    ///< External AIN4/AIN5
    ADS1263_ADC2_REF_INTERNAL_AVDD  = 4     ///< Internal + AVDD monitor
} ads1263_adc2_ref_t;

/* ========================================================================== */
/*                          IDAC CONFIGURATION                                */
/* ========================================================================== */

/**
 * @brief IDAC Current Magnitude
 * @note Datasheet Table 44, p.75
 */
typedef enum {
    ADS1263_IDAC_OFF        = 0x00, ///< Off
    ADS1263_IDAC_50UA       = 0x01, ///< 50 µA
    ADS1263_IDAC_100UA      = 0x02, ///< 100 µA
    ADS1263_IDAC_250UA      = 0x03, ///< 250 µA
    ADS1263_IDAC_500UA      = 0x04, ///< 500 µA
    ADS1263_IDAC_750UA      = 0x05, ///< 750 µA
    ADS1263_IDAC_1000UA     = 0x06, ///< 1000 µA (1 mA)
    ADS1263_IDAC_1500UA     = 0x07, ///< 1500 µA (1.5 mA)
    ADS1263_IDAC_2000UA     = 0x08, ///< 2000 µA (2 mA)
    ADS1263_IDAC_2500UA     = 0x09, ///< 2500 µA (2.5 mA)
    ADS1263_IDAC_3000UA     = 0x0A  ///< 3000 µA (3 mA)
} ads1263_idac_magnitude_t;

/* ========================================================================== */
/*                          CALIBRATION TYPES                                 */
/* ========================================================================== */

/**
 * @brief Calibration Types
 */
typedef enum {
    ADS1263_CAL_SELF_OFFSET  = 0,   ///< Self offset calibration (SFOCAL1)
    ADS1263_CAL_SYSTEM_OFFSET = 1,  ///< System offset calibration (SYOCAL1)
    ADS1263_CAL_SYSTEM_GAIN  = 2    ///< System gain calibration (SYGCAL1)
} ads1263_cal_type_t;

/* ========================================================================== */
/*                          STATUS STRUCTURE                                  */
/* ========================================================================== */

/**
 * @brief Status Byte Parsed Structure
 * @note Datasheet Table 31, p.67
 */
typedef struct {
    bool adc2_new;      ///< ADC2 new data available
    bool adc1_new;      ///< ADC1 new data available
    bool extclk;        ///< External clock detected
    bool ref_alarm;     ///< Reference alarm
    bool pga_low;       ///< PGA output low alarm
    bool pga_high;      ///< PGA output high alarm
    bool pga_diff;      ///< PGA differential alarm
    bool reset;         ///< Reset occurred
} ads1263_status_t;

/* ========================================================================== */
/*                          CALIBRATION DATA                                  */
/* ========================================================================== */

/**
 * @brief Calibration Data Storage
 */
typedef struct {
    int32_t offset;         ///< Offset calibration value (24-bit signed)
    uint32_t fullscale;     ///< Full-scale calibration value (24-bit)
    bool valid;             ///< Calibration data is valid
} ads1263_cal_data_t;

/* ========================================================================== */
/*                          CONFIGURATION STRUCTURE                           */
/* ========================================================================== */

/**
 * @brief Complete ADC1 Configuration
 * @note Used for bulk configuration and state saving
 */
typedef struct {
    ads1263_gain_t gain;                ///< PGA gain
    ads1263_rate_t rate;                ///< Data rate
    ads1263_filter_t filter;            ///< Digital filter
    ads1263_refp_t ref_pos;             ///< Reference positive
    ads1263_refn_t ref_neg;             ///< Reference negative
    ads1263_input_t input_pos;          ///< Input positive
    ads1263_input_t input_neg;          ///< Input negative
    ads1263_chop_mode_t chop;           ///< Chop mode
    ads1263_conv_mode_t conv_mode;      ///< Conversion mode
    ads1263_delay_t delay;              ///< Conversion delay
    bool pga_bypass;                    ///< PGA bypass enable
    bool vbias_enable;                  ///< VBIAS enable
    bool internal_ref_always_on;        ///< Internal reference always on
} ads1263_config_t;

/* ========================================================================== */
/*                          LOOKUP TABLES                                     */
/* ========================================================================== */

/**
 * @brief Gain to Float Conversion Table
 * @note Pre-calculated for fast voltage conversion
 */
static const ads1263_float_t ADS1263_GAIN_VALUES[6] = {
    1.0f, 2.0f, 4.0f, 8.0f, 16.0f, 32.0f
};

/**
 * @brief ADC2 Gain to Float Conversion Table
 */
static const ads1263_float_t ADS1263_ADC2_GAIN_VALUES[8] = {
    1.0f, 2.0f, 4.0f, 8.0f, 16.0f, 32.0f, 64.0f, 128.0f
};

/**
 * @brief Data Rate to Period (microseconds)
 * @note Used for timeout calculations
 */
static const uint32_t ADS1263_RATE_PERIOD_US[16] = {
    400000,  // 2.5 SPS
    200000,  // 5 SPS
    100000,  // 10 SPS
    60000,   // 16.6 SPS
    50000,   // 20 SPS
    20000,   // 50 SPS
    16667,   // 60 SPS
    10000,   // 100 SPS
    2500,    // 400 SPS
    833,     // 1200 SPS
    417,     // 2400 SPS
    208,     // 4800 SPS
    139,     // 7200 SPS
    69,      // 14400 SPS
    52,      // 19200 SPS
    26       // 38400 SPS
};

#endif // ADS1263_TYPES_H
