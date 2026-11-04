/**
 * @file ads1263.h
 * @brief ADS1263 32-bit ADC Driver - Main Header
 * @version 3.2.2 - FIXED
 * @date 2024
 * * @note FIXES APPLIED:
 * - Added missing member variables for cache and state
 * - Added missing helper method declarations
 */

#ifndef ADS1263_H
#define ADS1263_H

#include <stddef.h>
#include <stdint.h>
#include <stdbool.h>
#include <string.h>
#include "pico/stdlib.h"
#include "hardware/spi.h"

#include "ads1263_config.h"
#include "ads1263_defs.h"
#include "ads1263_types.h"
#include "ads1263_events.h"
#include "ads1263_state.h"

#define ADS1263_OP_QUEUE_SIZE 32

class ADS1263 {
public:
    ADS1263(uint8_t cs_pin, uint8_t drdy_pin);
    ADS1263(uint8_t cs_pin, uint8_t drdy_pin, uint8_t rst_pin);
    ADS1263(uint8_t cs_pin, uint8_t drdy_pin, uint8_t rst_pin, uint8_t start_pin);
    ~ADS1263();
    
    ads1263_error_t begin(spi_inst_t *spi, uint32_t spi_speed = 2000000);
    ads1263_error_t reset();
    
    void update();
    void flushPendingOperations();
    
    // Hardware Interrupt handler
    static ADS1263* _instance;
    static void drdy_isr_handler(uint gpio, uint32_t events);
    volatile bool _drdy_triggered;
    
    // --- Callbacks ---
    void onInitComplete(ads1263_init_callback_t callback);
    void onDataReady(ads1263_data_callback_t callback);
    void onADC2DataReady(ads1263_adc2_callback_t callback);
    void onError(ads1263_error_callback_t callback);
    void onCalibrationComplete(ads1263_cal_callback_t callback);
    void onAlarm(ads1263_alarm_callback_t callback);
    void onChannelSwitched(ads1263_channel_callback_t callback);
    
    // --- Conversion Control ---
    ads1263_error_t startContinuous();
    ads1263_error_t startSingleConversion();
    ads1263_error_t stopConversion();
    
    // --- ADC1 Config ---
    ads1263_error_t setGain(ads1263_gain_t gain);
    ads1263_error_t setDataRate(ads1263_rate_t rate);
    ads1263_error_t setFilter(ads1263_filter_t filter);
    ads1263_error_t setReference(ads1263_refp_t ref_pos, ads1263_refn_t ref_neg);
    ads1263_error_t setChannel(ads1263_input_t pos, ads1263_input_t neg);
    ads1263_error_t setChopMode(ads1263_chop_mode_t mode);
    ads1263_error_t setPGABypass(bool bypass);
    ads1263_error_t setConversionMode(ads1263_conv_mode_t mode);
    ads1263_error_t setConversionDelay(ads1263_delay_t delay);
    ads1263_error_t setRefReverse(bool reverse);
    ads1263_error_t enableVBias(bool enable);
    ads1263_error_t setInternalRefAlwaysOn(bool always_on);
    
    // --- Getters ---
    // MODE2
    ads1263_gain_t   getGain() const      { return _gain; }
    ads1263_rate_t   getRate() const      { return _rate; }
    bool             getPGABypass() const { return _pga_bypass; }
    // MODE1
    ads1263_filter_t getFilter() const    { return _filter; }
    // MODE0
    ads1263_chop_mode_t getChopMode() const {
        return (ads1263_chop_mode_t)((_reg_mode0_cache & ADS1263_MODE0_CHOP_MASK) >> 4);
    }
    ads1263_conv_mode_t getConversionMode() const {
        return (ads1263_conv_mode_t)((_reg_mode0_cache & ADS1263_MODE0_RUNMODE_MASK) >> 6);
    }
    ads1263_delay_t getConversionDelay() const {
        return (ads1263_delay_t)(_reg_mode0_cache & ADS1263_MODE0_DELAY_MASK);
    }
    bool getRefReverse() const {
        return (_reg_mode0_cache & ADS1263_MODE0_REFREV) != 0;
    }
    // INPMUX
    ads1263_input_t getInputPositive() const {
        return (ads1263_input_t)((_reg_inpmux_cache >> 4) & 0x0F);
    }
    ads1263_input_t getInputNegative() const {
        return (ads1263_input_t)(_reg_inpmux_cache & 0x0F);
    }
    // REFMUX
    ads1263_refp_t getRefPositive() const {
        return (ads1263_refp_t)((_reg_refmux_cache >> 3) & 0x07);
    }
    ads1263_refn_t getRefNegative() const {
        return (ads1263_refn_t)(_reg_refmux_cache & 0x07);
    }
    // POWER
    bool getVBias() const {
        return (_reg_power_cache & ADS1263_POWER_VBIAS) != 0;
    }
    bool getInternalRefAlwaysOn() const {
        return (_reg_power_cache & ADS1263_POWER_INTREF) != 0;
    }
    // Voltage
    ads1263_float_t getVref() const       { return _vref; }
    ads1263_float_t getLSBValue() const    { return _lsb_value; }
    // Register cache access
    uint8_t getMode0Cache() const   { return _reg_mode0_cache; }
    uint8_t getMode1Cache() const   { return _reg_mode1_cache; }
    uint8_t getMode2Cache() const   { return _reg_mode2_cache; }
    uint8_t getInpmuxCache() const  { return _reg_inpmux_cache; }
    uint8_t getRefmuxCache() const  { return _reg_refmux_cache; }
    uint8_t getPowerCache() const   { return _reg_power_cache; }
    uint8_t getIDACMagCache() const { return _reg_idacmag_cache; }
    uint8_t getIDACMuxCache() const { return _reg_idacmux_cache; }
    
    // --- ADC2 Config ---
#if ADS1263_ENABLE_ADC2
    ads1263_error_t setADC2Config(ads1263_adc2_rate_t rate, 
                                  ads1263_adc2_gain_t gain,
                                  ads1263_adc2_ref_t ref);
    ads1263_error_t setADC2Channel(ads1263_input_t pos, ads1263_input_t neg);
    ads1263_error_t startADC2();
    ads1263_error_t stopADC2();
#endif

    // --- Calibration ---
    ads1263_error_t calibrateOffset();
    ads1263_error_t calibrateSystemOffset();
    ads1263_error_t calibrateSystemGain();
    ads1263_error_t writeOffsetCalibration(int32_t offset);
    ads1263_error_t writeFullScaleCalibration(uint32_t fullscale);
    
    // --- Special Features ---
#if ADS1263_ENABLE_TEMP_SENSOR
    ads1263_error_t readInternalTemperature();
#endif
    
#if ADS1263_ENABLE_IDAC
    ads1263_error_t setIDAC(ads1263_idac_magnitude_t idac1_mag,
                            ads1263_idac_magnitude_t idac2_mag,
                            ads1263_input_t idac1_pin,
                            ads1263_input_t idac2_pin);
#endif
    
#if ADS1263_ENABLE_GPIO
    ads1263_error_t gpioPinMode(uint8_t pin, uint8_t mode);
    ads1263_error_t gpioWrite(uint8_t pin, uint8_t value);
    ads1263_error_t gpioReadRequest(uint8_t pin); 
    int getLastGpioState(uint8_t pin);
#endif

    // --- Debug & Utility ---
    void printAllRegisters();
    uint8_t readRegisterDirect(uint8_t reg);

    
    ads1263_float_t toVoltage(int32_t raw_data) const;
    ads1263_float_t toADC2Voltage(int32_t raw_data) const;
    
    ads1263_state_t getState() const { return _state; }
    bool isBusy() const { return _state != ADS1263_STATE_IDLE && _state != ADS1263_STATE_CONVERTING; }
    bool isConverting() const { return _state == ADS1263_STATE_CONVERTING; }
    
    ads1263_status_t parseStatus(uint8_t status_byte) const;
    
private:
    struct Operation {
        pending_op_type_t type;
        uint8_t reg_or_cmd;
        uint8_t data;
        uint32_t timestamp;
    };

    uint8_t _cs_pin, _drdy_pin, _rst_pin, _start_pin;
    bool _has_rst_pin, _has_start_pin;
    
    spi_inst_t *_spi;
    uint32_t _spi_speed;
    RateLimiter _spi_limiter;
    
    ads1263_state_t _state;
    ads1263_substate_t _substate;
    TimerManager _state_timer;
    TimerManager _timeout_timer;
    TimerManager _drdy_poll_timer;
    
    Operation _op_queue[ADS1263_OP_QUEUE_SIZE];
    uint8_t _queue_head;
    uint8_t _queue_tail;
    uint8_t _queue_count;
    
    // ADC1 Cache
    ads1263_gain_t _gain;
    ads1263_rate_t _rate;
    ads1263_filter_t _filter;           // NEW
    ads1263_float_t _vref;
    ads1263_float_t _lsb_value;
    bool _pga_bypass;                   // NEW
    
    // ADC2 Cache
    ads1263_adc2_gain_t _adc2_gain;
    ads1263_adc2_ref_t  _adc2_ref_mode;
    ads1263_float_t     _adc2_lsb_value;
    
    bool _continuous_mode;
    bool _adc2_enabled;
    bool _crc_enabled;                  // NEW
    
    // Register Cache Variables (NEW)
    uint8_t _reg_power_cache;
    uint8_t _reg_interface_cache;
    uint8_t _reg_mode0_cache;
    uint8_t _reg_mode1_cache;
    uint8_t _reg_mode2_cache;
    uint8_t _reg_inpmux_cache;
    uint8_t _reg_refmux_cache;
    uint8_t _reg_gpiocon_cache;
    uint8_t _reg_gpiodir_cache;
    uint8_t _reg_gpiodat_cache;
    uint8_t _reg_idacmag_cache;
    uint8_t _reg_idacmux_cache;
    
    ads1263_config_t _saved_config;
    uint8_t _dump_reg_index;
    uint8_t _init_step;                 // NEW
    uint8_t _init_retry_count;          // NEW: retry counter for startup ID check
    bool _single_conv_pending;          // NEW: deferred single conversion flag
    ads1263_callbacks_t _callbacks;
    
    uint8_t _device_id;
    uint8_t _last_status_byte;
    int32_t _last_raw_data;
    uint8_t _gpio_values;
    
    // --- Private Methods ---
    bool isQueueFull() const;
    bool isQueueEmpty() const;
    ads1263_error_t enqueue(pending_op_type_t type, uint8_t reg_or_cmd = 0, uint8_t data = 0);
    Operation dequeue();
    Operation peekQueue();
    
    void updateStateMachine();
    void handleInitialization();
    void handleConversion();
    void handleCalibration();
    void handleTempReading();
    void handleRegDump();
    void handleGpioReading();
    
    void processQueue();
    void executeSPICommand(uint8_t cmd);
    void executeSPIRegisterWrite(uint8_t reg, uint8_t value);
    uint8_t executeSPIRegisterRead(uint8_t reg);
    void executeSPIDataRead();
    void executeADC2DataRead();
    
    void checkHardwareSignals();
    bool isDRDYLow() const;
    void updateLSBValue();
    void updateADC2LSBValue();
    void initializeRegisterCache();     // NEW
    uint32_t calculateSettlingTime();   // NEW
    
    // CRC/Checksum functions (NEW)
    uint8_t computeChecksum(const uint8_t* data, uint8_t len) const;
    uint8_t computeCRC(const uint8_t* data, uint8_t len) const;
    bool validateDataCRC(const uint8_t* data, uint8_t len, uint8_t received_crc) const;
    
    void dispatchDataReady(int32_t raw, uint8_t status, bool is_temp = false, uint8_t crc_byte = 0);
    void dispatchADC2DataReady(int32_t raw, uint8_t status);
    void dispatchInitComplete(bool success);
    void dispatchError(ads1263_error_t error, const char* msg);
    void dispatchCalibrationComplete(ads1263_cal_type_t type, bool success);
    void dispatchAlarm(uint8_t alarm_flags);
    void dispatchChannelSwitched(ads1263_input_t pos, ads1263_input_t neg);
};

#endif // ADS1263_H