/**
 * @file ads1263.cpp
 * @brief ADS1263 32-bit ADC Driver - Implementation
 * @version 3.2.1 - FIXED
 * * @note FIXES APPLIED:
 * - Fixed INTERFACE_STATUS bit position (0x04, not 0x20)
 * - Fixed MODE0 CHOP bit shift (bits [5:4], shift by 4)
 * - Fixed MODE0 RUNMODE bit shift (bit [6], shift by 6)
 * - Added register caching for read-modify-write operations
 * - Fixed ADC2 sign extension for 24-bit data
 * - Fixed GPIO pin limit (0-7, not 0-3)
 * - Fixed static init_step variable
 * - Added CRC/Checksum validation with Correct Data Offset (skipping status byte)
 * - Added proper filter settling time calculation with Sinc4 safety margin
 * - Added check to prevent Pulse Mode when Chop is active
 */

#include "ads1263.h"

ADS1263* ADS1263::_instance = nullptr;

void ADS1263::drdy_isr_handler(uint gpio, uint32_t events) {
    if (_instance && gpio == _instance->_drdy_pin) {
        _instance->_drdy_triggered = true;
    }
}

/* ========================================================================== */
/* CONSTRUCTORS                                                               */
/* ========================================================================== */

ADS1263::ADS1263(uint8_t cs_pin, uint8_t drdy_pin)
    : ADS1263(cs_pin, drdy_pin, 255, 255) {}

ADS1263::ADS1263(uint8_t cs_pin, uint8_t drdy_pin, uint8_t rst_pin)
    : ADS1263(cs_pin, drdy_pin, rst_pin, 255) {}

ADS1263::ADS1263(uint8_t cs_pin, uint8_t drdy_pin, uint8_t rst_pin, uint8_t start_pin)
    : _cs_pin(cs_pin), _drdy_pin(drdy_pin), _rst_pin(rst_pin), _start_pin(start_pin),
      _has_rst_pin(rst_pin != 255), _has_start_pin(start_pin != 255),
      _spi(nullptr), _spi_limiter(ADS1263_TIMING::SPI_SPACING_US),
      _state(ADS1263_STATE_UNINITIALIZED), _substate(ADS1263_SUBSTATE_NONE),
      _queue_head(0), _queue_tail(0), _queue_count(0),
      _gain(ADS1263_GAIN_1), _rate(ADS1263_RATE_20), _filter(ADS1263_FILTER_FIR),
      _vref(ADS1263_VREF_INTERNAL), _lsb_value(0.0f), _pga_bypass(false),
      _adc2_gain(ADS1263_ADC2_GAIN_1), _adc2_ref_mode(ADS1263_ADC2_REF_INTERNAL), _adc2_lsb_value(0.0f),
      _continuous_mode(false), _adc2_enabled(false), _crc_enabled(false),
      _init_step(0), _init_retry_count(0), _single_conv_pending(false),
      _device_id(0), _last_status_byte(0), _last_raw_data(0), _gpio_values(0),
      _drdy_triggered(false)
{
    memset(&_callbacks, 0, sizeof(_callbacks));
    initializeRegisterCache();
    updateLSBValue();
    updateADC2LSBValue();
}

ADS1263::~ADS1263() {
    stopConversion();
}

/* ========================================================================== */
/* REGISTER CACHE INITIALIZATION                                              */
/* ========================================================================== */

void ADS1263::initializeRegisterCache() {
    // Initialize cache to datasheet default values
    _reg_power_cache     = ADS1263_REG_POWER_DEFAULT;      // 0x11
    _reg_interface_cache = ADS1263_REG_INTERFACE_DEFAULT;  // 0x05
    _reg_mode0_cache     = ADS1263_REG_MODE0_DEFAULT;      // 0x00
    _reg_mode1_cache     = ADS1263_REG_MODE1_DEFAULT;      // 0x80 (FIR filter)
    _reg_mode2_cache     = ADS1263_REG_MODE2_DEFAULT;      // 0x04 (Gain=1, DR=20 SPS)
    _reg_inpmux_cache    = ADS1263_REG_INPMUX_DEFAULT;     // 0x01 (AIN0-AIN1)
    _reg_refmux_cache    = ADS1263_REG_REFMUX_DEFAULT;     // 0x00 (Internal ref)
    _reg_gpiocon_cache   = 0x00;  // All analog
    _reg_gpiodir_cache   = 0x00;  // All inputs
    _reg_gpiodat_cache   = 0x00;  // All low
    _reg_idacmag_cache   = 0x00;  // Off
    _reg_idacmux_cache   = 0xBB;  // AINCOM (disconnected)
}

/* ========================================================================== */
/* INITIALIZATION                                                             */
/* ========================================================================== */

ads1263_error_t ADS1263::begin(spi_inst_t *spi, uint32_t spi_speed) {
    if (_state != ADS1263_STATE_UNINITIALIZED) return ADS1263_ERROR_STATE;
    
    // Datasheet specifies max SCLK = 8 MHz
    if (spi_speed > 8000000) spi_speed = 8000000;
    
    _spi = spi;
    _spi_speed = spi_speed;
    
    gpio_init(_cs_pin); gpio_set_dir(_cs_pin, GPIO_OUT); gpio_put(_cs_pin, 1);
    gpio_init(_drdy_pin); 
    gpio_set_dir(_drdy_pin, GPIO_IN);
    
    // Setup hardware interrupt
    _instance = this;
    _drdy_triggered = false;
    gpio_set_irq_enabled_with_callback(_drdy_pin, GPIO_IRQ_EDGE_FALL, true, &ADS1263::drdy_isr_handler);
    if (_has_rst_pin) { gpio_init(_rst_pin); gpio_set_dir(_rst_pin, GPIO_OUT); gpio_put(_rst_pin, 1); }
    if (_has_start_pin) { gpio_init(_start_pin); gpio_set_dir(_start_pin, GPIO_OUT); gpio_put(_start_pin, 0); }
    
    spi_init(_spi, _spi_speed);
    // spi_set_format setup should be done by the user or here
    spi_set_format(_spi, 8, SPI_CPOL_0, SPI_CPHA_1, SPI_MSB_FIRST);
    
    // Reset cache and init state
    initializeRegisterCache();
    _init_step = 0;
    _init_retry_count = 0;
    _device_id = 0;
    _single_conv_pending = false;
    _state = ADS1263_STATE_INIT_START;
    
    return ADS1263_OK;
}

ads1263_error_t ADS1263::reset() {
    _state = ADS1263_STATE_INIT_START;
    _queue_head = _queue_tail = _queue_count = 0;
    _init_step = 0;
    _init_retry_count = 0;
    _device_id = 0;
    _single_conv_pending = false;
    initializeRegisterCache();
    return ADS1263_OK;
}

/* ========================================================================== */
/* EVENT LOOP                                                                 */
/* ========================================================================== */

void ADS1263::update() {
    checkHardwareSignals();
    processQueue();
    updateStateMachine();
}

void ADS1263::flushPendingOperations() {
    while (!isQueueEmpty()) {
        while (!_spi_limiter.canAccess()) { sleep_us(1); }
        processQueue();
    }
}

/* ========================================================================== */
/* QUEUE MANAGEMENT                                                           */
/* ========================================================================== */

bool ADS1263::isQueueFull() const { return _queue_count >= ADS1263_OP_QUEUE_SIZE; }
bool ADS1263::isQueueEmpty() const { return _queue_count == 0; }

ads1263_error_t ADS1263::enqueue(pending_op_type_t type, uint8_t reg_or_cmd, uint8_t data) {
    if (isQueueFull()) return ADS1263_ERROR_OVERFLOW;
    
    _op_queue[_queue_tail].type = type;
    _op_queue[_queue_tail].reg_or_cmd = reg_or_cmd;
    _op_queue[_queue_tail].data = data;
    _op_queue[_queue_tail].timestamp = time_us_32();
    
    _queue_tail = (_queue_tail + 1) % ADS1263_OP_QUEUE_SIZE;
    _queue_count++;
    return ADS1263_OK;
}

ADS1263::Operation ADS1263::dequeue() {
    Operation op = _op_queue[_queue_head];
    _queue_head = (_queue_head + 1) % ADS1263_OP_QUEUE_SIZE;
    _queue_count--;
    return op;
}

ADS1263::Operation ADS1263::peekQueue() {
    return _op_queue[_queue_head];
}

/* ========================================================================== */
/* SPI PROCESSING                                                             */
/* ========================================================================== */

void ADS1263::processQueue() {
    if (isQueueEmpty()) return;
    if (!_spi_limiter.canAccess()) return;
    
    Operation op = dequeue();
    
    switch (op.type) {
        case PENDING_OP_COMMAND:
            executeSPICommand(op.reg_or_cmd);
            break;
        case PENDING_OP_REG_WRITE:
            executeSPIRegisterWrite(op.reg_or_cmd, op.data);
            break;
        case PENDING_OP_REG_READ:
            {
                uint8_t val = executeSPIRegisterRead(op.reg_or_cmd);
                if (op.reg_or_cmd == ADS1263_REG_ID) _device_id = val;
                if (op.reg_or_cmd == ADS1263_REG_GPIODAT) _gpio_values = val;
            }
            break;
        case PENDING_OP_DATA_READ:
            executeSPIDataRead();
            break;
        case PENDING_OP_ADC2_READ:
            executeADC2DataRead();
            break;
        default: break;
    }
    
    _spi_limiter.markAccess();
}

/* ========================================================================== */
/* CALLBACK REGISTRATION                                                      */
/* ========================================================================== */

void ADS1263::onInitComplete(ads1263_init_callback_t cb) { _callbacks.init_cb = cb; }
void ADS1263::onDataReady(ads1263_data_callback_t cb) { _callbacks.data_cb = cb; }
void ADS1263::onADC2DataReady(ads1263_adc2_callback_t cb) { _callbacks.adc2_cb = cb; }
void ADS1263::onError(ads1263_error_callback_t cb) { _callbacks.error_cb = cb; }
void ADS1263::onCalibrationComplete(ads1263_cal_callback_t cb) { _callbacks.cal_cb = cb; }
void ADS1263::onAlarm(ads1263_alarm_callback_t cb) { _callbacks.alarm_cb = cb; }
void ADS1263::onChannelSwitched(ads1263_channel_callback_t cb) { _callbacks.channel_cb = cb; }

/* ========================================================================== */
/* CONFIGURATION METHODS - WITH REGISTER CACHING                              */
/* ========================================================================== */

ads1263_error_t ADS1263::setGain(ads1263_gain_t gain) {
    if (gain > ADS1263_GAIN_32) return ADS1263_ERROR_RANGE;
    _gain = gain;
    updateLSBValue();
    
    _reg_mode2_cache = (_reg_mode2_cache & ADS1263_MODE2_BYPASS) | (gain << 4) | _rate;
    return enqueue(PENDING_OP_REG_WRITE, ADS1263_REG_MODE2, _reg_mode2_cache);
}

ads1263_error_t ADS1263::setDataRate(ads1263_rate_t rate) {
    _rate = rate;

    // Auto-fallback filter if incompatible with new rate (Datasheet Section 9.3.8)
    // FIR only valid at ≤20 SPS; Sinc2/3/4 invalid at 14400+ SPS
    bool filter_ok = true;
    if (_filter == ADS1263_FILTER_FIR && rate > ADS1263_RATE_20)
        filter_ok = false;
    if (_filter > ADS1263_FILTER_SINC1 && rate >= ADS1263_RATE_14400)
        filter_ok = false;

    if (!filter_ok) {
        _filter = ADS1263_FILTER_SINC1;
        _reg_mode1_cache = _reg_mode1_cache & ~ADS1263_MODE1_FILTER_MASK; // Sinc1 = 0
        enqueue(PENDING_OP_REG_WRITE, ADS1263_REG_MODE1, _reg_mode1_cache);
    }

    _reg_mode2_cache = (_reg_mode2_cache & (ADS1263_MODE2_BYPASS | ADS1263_MODE2_GAIN_MASK)) | rate;
    return enqueue(PENDING_OP_REG_WRITE, ADS1263_REG_MODE2, _reg_mode2_cache);
}

ads1263_error_t ADS1263::setFilter(ads1263_filter_t filter) {
    // Validate filter↔rate compatibility (Datasheet Section 9.3.8)
    // FIR only valid at ≤20 SPS (rates 0-4)
    if (filter == ADS1263_FILTER_FIR && _rate > ADS1263_RATE_20)
        return ADS1263_ERROR_CONFIG;
    // Sinc2/3/4 invalid at 14400+ SPS (rates 13-15) — hardware ignores FILTER bits
    if (filter > ADS1263_FILTER_SINC1 && _rate >= ADS1263_RATE_14400)
        return ADS1263_ERROR_CONFIG;

    _filter = filter;
    
    _reg_mode1_cache = (_reg_mode1_cache & ~ADS1263_MODE1_FILTER_MASK) | (filter << 5);
    return enqueue(PENDING_OP_REG_WRITE, ADS1263_REG_MODE1, _reg_mode1_cache);
}

ads1263_error_t ADS1263::setReference(ads1263_refp_t ref_pos, ads1263_refn_t ref_neg) {
    if (isConverting()) {
        return ADS1263_ERROR_STATE;
    }
    if (ref_pos == ADS1263_REFP_INTERNAL && ref_neg == ADS1263_REFN_INTERNAL) {
        _vref = ADS1263_VREF_INTERNAL;
    } else if (ref_pos == ADS1263_REFP_AVDD && ref_neg == ADS1263_REFN_AVSS) {
        _vref = 5.0f; // AVDD is 5.0V on this board
    } else {
        _vref = 2.5f; // Fallback for other external refs
    }
    updateLSBValue();
    
    _reg_refmux_cache = (ref_pos << 3) | ref_neg;
    return enqueue(PENDING_OP_REG_WRITE, ADS1263_REG_REFMUX, _reg_refmux_cache);
}

ads1263_error_t ADS1263::setChannel(ads1263_input_t pos, ads1263_input_t neg) {
    if (isConverting()) {
        return ADS1263_ERROR_STATE;
    }
    _reg_inpmux_cache = (pos << 4) | neg;
    ads1263_error_t err = enqueue(PENDING_OP_REG_WRITE, ADS1263_REG_INPMUX, _reg_inpmux_cache);
    
    if (err == ADS1263_OK) {
        _state = ADS1263_STATE_SWITCHING_CHANNEL;
        _state_timer.start(calculateSettlingTime());
    }
    return err;
}

ads1263_error_t ADS1263::setChopMode(ads1263_chop_mode_t mode) {
    if (mode != ADS1263_CHOP_OFF) {
        ads1263_conv_mode_t conv_mode = (ads1263_conv_mode_t)((_reg_mode0_cache & ADS1263_MODE0_RUNMODE_MASK) >> 6);
        if (conv_mode == ADS1263_CONV_PULSE) {
            return ADS1263_ERROR_CONFIG;
        }
    }
    _reg_mode0_cache = (_reg_mode0_cache & ~ADS1263_MODE0_CHOP_MASK) | (mode << 4);
    return enqueue(PENDING_OP_REG_WRITE, ADS1263_REG_MODE0, _reg_mode0_cache);
}

ads1263_error_t ADS1263::setPGABypass(bool bypass) {
    _pga_bypass = bypass;
    
    if (bypass) {
        _reg_mode2_cache |= ADS1263_MODE2_BYPASS;
    } else {
        _reg_mode2_cache &= ~ADS1263_MODE2_BYPASS;
    }
    updateLSBValue();
    return enqueue(PENDING_OP_REG_WRITE, ADS1263_REG_MODE2, _reg_mode2_cache);
}

ads1263_error_t ADS1263::setConversionMode(ads1263_conv_mode_t mode) {
    // FIXED: Conflict Check
    // The datasheet states: "The pulse conversion mode cannot be used in conjunction with chop mode."
    if (mode == ADS1263_CONV_PULSE) {
        uint8_t chop_state = (_reg_mode0_cache & ADS1263_MODE0_CHOP_MASK);
        if (chop_state != 0x00) { // If chop enabled
            return ADS1263_ERROR_CONFIG; // Cannot enable Pulse mode while Chop is on
        }
    }

    _reg_mode0_cache = (_reg_mode0_cache & ~ADS1263_MODE0_RUNMODE_MASK) | (mode << 6);
    return enqueue(PENDING_OP_REG_WRITE, ADS1263_REG_MODE0, _reg_mode0_cache);
}

ads1263_error_t ADS1263::setConversionDelay(ads1263_delay_t delay) {
    _reg_mode0_cache = (_reg_mode0_cache & ~ADS1263_MODE0_DELAY_MASK) | delay;
    return enqueue(PENDING_OP_REG_WRITE, ADS1263_REG_MODE0, _reg_mode0_cache);
}

ads1263_error_t ADS1263::setRefReverse(bool reverse) {
    if (reverse) {
        _reg_mode0_cache |= ADS1263_MODE0_REFREV;
    } else {
        _reg_mode0_cache &= ~ADS1263_MODE0_REFREV;
    }
    return enqueue(PENDING_OP_REG_WRITE, ADS1263_REG_MODE0, _reg_mode0_cache);
}

ads1263_error_t ADS1263::enableVBias(bool enable) {
    if (enable) {
        _reg_power_cache |= ADS1263_POWER_VBIAS;
    } else {
        _reg_power_cache &= ~ADS1263_POWER_VBIAS;
    }
    return enqueue(PENDING_OP_REG_WRITE, ADS1263_REG_POWER, _reg_power_cache);
}

ads1263_error_t ADS1263::setInternalRefAlwaysOn(bool always_on) {
    if (always_on) {
        _reg_power_cache |= ADS1263_POWER_INTREF;
    } else {
        _reg_power_cache &= ~ADS1263_POWER_INTREF;
    }
    return enqueue(PENDING_OP_REG_WRITE, ADS1263_REG_POWER, _reg_power_cache);
}

/* ========================================================================== */
/* CONVERSION CONTROL                                                         */
/* ========================================================================== */

ads1263_error_t ADS1263::startContinuous() {
    _continuous_mode = true;
    if (_state == ADS1263_STATE_SWITCHING_CHANNEL) {
        return ADS1263_OK;
    }
    _state = ADS1263_STATE_START_CONVERSION;
    return enqueue(PENDING_OP_COMMAND, ADS1263_CMD_START1);
}

ads1263_error_t ADS1263::startSingleConversion() {
    _continuous_mode = false;
    if (_state == ADS1263_STATE_SWITCHING_CHANNEL) {
        _single_conv_pending = true;
        return ADS1263_OK;
    }
    _state = ADS1263_STATE_START_CONVERSION;
    return enqueue(PENDING_OP_COMMAND, ADS1263_CMD_START1);
}

ads1263_error_t ADS1263::stopConversion() {
    _continuous_mode = false;
    _state = ADS1263_STATE_IDLE;
    return enqueue(PENDING_OP_COMMAND, ADS1263_CMD_STOP1);
}

/* ========================================================================== */
/* ADC2 & SPECIAL FEATURES                                                    */
/* ========================================================================== */

#if ADS1263_ENABLE_ADC2
ads1263_error_t ADS1263::setADC2Config(ads1263_adc2_rate_t rate, ads1263_adc2_gain_t gain, ads1263_adc2_ref_t ref) {
    _adc2_gain = gain;
    _adc2_ref_mode = ref;
    updateADC2LSBValue();
    uint8_t cfg = (rate << 6) | (ref << 3) | gain;
    return enqueue(PENDING_OP_REG_WRITE, ADS1263_REG_ADC2CFG, cfg);
}

ads1263_error_t ADS1263::setADC2Channel(ads1263_input_t pos, ads1263_input_t neg) {
    if (isConverting() || _adc2_enabled) {
        return ADS1263_ERROR_STATE;
    }
    return enqueue(PENDING_OP_REG_WRITE, ADS1263_REG_ADC2MUX, (pos << 4) | neg);
}

ads1263_error_t ADS1263::startADC2() {
    _adc2_enabled = true;
    return enqueue(PENDING_OP_COMMAND, ADS1263_CMD_START2);
}

ads1263_error_t ADS1263::stopADC2() {
    _adc2_enabled = false;
    return enqueue(PENDING_OP_COMMAND, ADS1263_CMD_STOP2);
}
#endif

#if ADS1263_ENABLE_TEMP_SENSOR
ads1263_error_t ADS1263::readInternalTemperature() {
    if (isBusy()) return ADS1263_ERROR_BUSY;
    _substate = ADS1263_SUBSTATE_TEMP_START;
    _state = ADS1263_STATE_TEMP_READING;
    return ADS1263_OK;
}
#endif

#if ADS1263_ENABLE_IDAC
ads1263_error_t ADS1263::setIDAC(ads1263_idac_magnitude_t idac1_mag,
                                 ads1263_idac_magnitude_t idac2_mag,
                                 ads1263_input_t idac1_pin,
                                 ads1263_input_t idac2_pin)
{
    if (isConverting()) {
        return ADS1263_ERROR_STATE;
    }
    _reg_idacmag_cache = (idac2_mag << 4) | idac1_mag;
    ads1263_error_t err = enqueue(PENDING_OP_REG_WRITE, ADS1263_REG_IDACMAG, _reg_idacmag_cache);
    if (err != ADS1263_OK) return err;
    
    _reg_idacmux_cache = (idac2_pin << 4) | idac1_pin;
    return enqueue(PENDING_OP_REG_WRITE, ADS1263_REG_IDACMUX, _reg_idacmux_cache);
}
#endif

#if ADS1263_ENABLE_GPIO
ads1263_error_t ADS1263::gpioPinMode(uint8_t pin, uint8_t mode) {
    if (pin > 7) return ADS1263_ERROR_RANGE;
    
    uint8_t mask = 1 << pin;
    
    _reg_gpiocon_cache |= mask;  // Enable this pin as GPIO
    enqueue(PENDING_OP_REG_WRITE, ADS1263_REG_GPIOCON, _reg_gpiocon_cache);
    
    if (mode == GPIO_OUT) {
        _reg_gpiodir_cache |= mask;
    } else {
        _reg_gpiodir_cache &= ~mask;
    }
    return enqueue(PENDING_OP_REG_WRITE, ADS1263_REG_GPIODIR, _reg_gpiodir_cache);
}

ads1263_error_t ADS1263::gpioWrite(uint8_t pin, uint8_t value) {
    if (pin > 7) return ADS1263_ERROR_RANGE;
    
    uint8_t mask = 1 << pin;
    
    if (value) {
        _reg_gpiodat_cache |= mask;
    } else {
        _reg_gpiodat_cache &= ~mask;
    }
    return enqueue(PENDING_OP_REG_WRITE, ADS1263_REG_GPIODAT, _reg_gpiodat_cache);
}

ads1263_error_t ADS1263::gpioReadRequest(uint8_t pin) {
    if (pin > 7) return ADS1263_ERROR_RANGE;
    return enqueue(PENDING_OP_REG_READ, ADS1263_REG_GPIODAT);
}

int ADS1263::getLastGpioState(uint8_t pin) {
    if (pin > 7) return -1;
    return (_gpio_values >> pin) & 0x01;
}
#endif

/* ========================================================================== */
/* CALIBRATION                                                                */
/* ========================================================================== */

ads1263_error_t ADS1263::calibrateOffset() {
    // 1. Stop conversions
    enqueue(PENDING_OP_COMMAND, ADS1263_CMD_STOP1);
    
    // 2. Short inputs internally (INPMUX = 0xBB, AINCOM to both MUXP/MUXN)
    enqueue(PENDING_OP_REG_WRITE, ADS1263_REG_INPMUX, 0xBB);
    
    // 3. Disable IDAC currents (IDACMAG = 0x00)
#if ADS1263_ENABLE_IDAC
    enqueue(PENDING_OP_REG_WRITE, ADS1263_REG_IDACMAG, 0x00);
#endif
    
    // 4. Start offset calibration command
    _state = ADS1263_STATE_CAL_START;
    _substate = ADS1263_SUBSTATE_CAL_OFFSET;
    return enqueue(PENDING_OP_COMMAND, ADS1263_CMD_SFOCAL1);
}

ads1263_error_t ADS1263::calibrateSystemOffset() {
    _state = ADS1263_STATE_CAL_START;
    _substate = ADS1263_SUBSTATE_CAL_SYSTEM;
    return enqueue(PENDING_OP_COMMAND, ADS1263_CMD_SYOCAL1);
}

ads1263_error_t ADS1263::calibrateSystemGain() {
    _state = ADS1263_STATE_CAL_START;
    _substate = ADS1263_SUBSTATE_CAL_GAIN;
    return enqueue(PENDING_OP_COMMAND, ADS1263_CMD_SYGCAL1);
}

ads1263_error_t ADS1263::writeOffsetCalibration(int32_t offset) {
    enqueue(PENDING_OP_REG_WRITE, ADS1263_REG_OFCAL0, offset & 0xFF);
    enqueue(PENDING_OP_REG_WRITE, ADS1263_REG_OFCAL1, (offset >> 8) & 0xFF);
    return enqueue(PENDING_OP_REG_WRITE, ADS1263_REG_OFCAL2, (offset >> 16) & 0xFF);
}

ads1263_error_t ADS1263::writeFullScaleCalibration(uint32_t fullscale) {
    enqueue(PENDING_OP_REG_WRITE, ADS1263_REG_FSCAL0, fullscale & 0xFF);
    enqueue(PENDING_OP_REG_WRITE, ADS1263_REG_FSCAL1, (fullscale >> 8) & 0xFF);
    return enqueue(PENDING_OP_REG_WRITE, ADS1263_REG_FSCAL2, (fullscale >> 16) & 0xFF);
}

void ADS1263::printAllRegisters() {
    if (isBusy()) return;
    _dump_reg_index = 0;
    _substate = ADS1263_SUBSTATE_REG_READ_NEXT;
    _state = ADS1263_STATE_REG_DUMP;
}

/* ========================================================================== */
/* STATE MACHINE LOGIC                                                        */
/* ========================================================================== */

void ADS1263::updateStateMachine() {
    switch (_state) {
        case ADS1263_STATE_INIT_START:
        case ADS1263_STATE_INIT_RESET_PULSE:
        case ADS1263_STATE_INIT_RESET_WAIT:
        case ADS1263_STATE_INIT_ID_CHECK:
        case ADS1263_STATE_INIT_CONFIG_INTERFACE:
        case ADS1263_STATE_INIT_CONFIG_POWER:
            handleInitialization();
            break;
        case ADS1263_STATE_START_CONVERSION:
            _state = ADS1263_STATE_CONVERTING;
            break;
        case ADS1263_STATE_CONVERTING:
            handleConversion();
            break;
        case ADS1263_STATE_TEMP_READING:
            handleTempReading();
            break;
        case ADS1263_STATE_REG_DUMP:
            handleRegDump();
            break;
        case ADS1263_STATE_GPIO_READING:
            handleGpioReading();
            break;
        case ADS1263_STATE_CAL_START:
        case ADS1263_STATE_CAL_WAIT_DRDY:
            handleCalibration();
            break;
        case ADS1263_STATE_SWITCHING_CHANNEL:
            if (_state_timer.isExpired()) {
                if (_continuous_mode) {
                    _state = ADS1263_STATE_START_CONVERSION;
                    enqueue(PENDING_OP_COMMAND, ADS1263_CMD_START1);
                } else if (_single_conv_pending) {
                    _single_conv_pending = false;
                    _state = ADS1263_STATE_START_CONVERSION;
                    enqueue(PENDING_OP_COMMAND, ADS1263_CMD_START1);
                } else {
                    _state = ADS1263_STATE_IDLE;
                }
                uint8_t pos = (_reg_inpmux_cache >> 4) & 0x0F;
                uint8_t neg = _reg_inpmux_cache & 0x0F;
                dispatchChannelSwitched((ads1263_input_t)pos, (ads1263_input_t)neg);
            }
            break;
        default: break;
    }
}

void ADS1263::handleTempReading() {
    switch (_substate) {
        case ADS1263_SUBSTATE_TEMP_START:
            _saved_config.input_pos = (ads1263_input_t)((_reg_inpmux_cache >> 4) & 0x0F);
            _saved_config.input_neg = (ads1263_input_t)(_reg_inpmux_cache & 0x0F);
            _substate = ADS1263_SUBSTATE_TEMP_CONFIG_MUX;
            break;
            
        case ADS1263_SUBSTATE_TEMP_CONFIG_MUX:
            enqueue(PENDING_OP_REG_WRITE, ADS1263_REG_INPMUX, 0xBB);
            _substate = ADS1263_SUBSTATE_TEMP_CONVERT;
            break;
            
        case ADS1263_SUBSTATE_TEMP_CONVERT:
            enqueue(PENDING_OP_COMMAND, ADS1263_CMD_START1);
            _substate = ADS1263_SUBSTATE_TEMP_WAIT;
            _timeout_timer.start(200000);
            break;
            
        case ADS1263_SUBSTATE_TEMP_WAIT:
            if (isDRDYLow()) {
                _substate = ADS1263_SUBSTATE_TEMP_READ;
            } else if (_timeout_timer.isExpired()) {
                dispatchError(ADS1263_ERROR_TIMEOUT, "Temperature read timeout");
                _substate = ADS1263_SUBSTATE_TEMP_RESTORE;
            }
            break;
            
        case ADS1263_SUBSTATE_TEMP_READ:
            enqueue(PENDING_OP_DATA_READ, 0, 0);
            _substate = ADS1263_SUBSTATE_TEMP_RESTORE;
            break;
            
        case ADS1263_SUBSTATE_TEMP_RESTORE:
            _reg_inpmux_cache = (_saved_config.input_pos << 4) | _saved_config.input_neg;
            enqueue(PENDING_OP_REG_WRITE, ADS1263_REG_INPMUX, _reg_inpmux_cache);
            _state = ADS1263_STATE_SWITCHING_CHANNEL;
            _state_timer.start(calculateSettlingTime());
            _substate = ADS1263_SUBSTATE_NONE;
            break;
            
        default:
            _state = ADS1263_STATE_IDLE;
            break;
    }
}

void ADS1263::handleRegDump() {
    if (_substate == ADS1263_SUBSTATE_REG_READ_NEXT) {
        if (_dump_reg_index <= 0x1A) {
            enqueue(PENDING_OP_REG_READ, _dump_reg_index);
            _dump_reg_index++;
        } else {
            _state = ADS1263_STATE_IDLE;
            _substate = ADS1263_SUBSTATE_NONE;
        }
    }
}

void ADS1263::handleGpioReading() {
    enqueue(PENDING_OP_REG_READ, ADS1263_REG_GPIODAT);
    _state = ADS1263_STATE_IDLE;
}

void ADS1263::handleInitialization() {
    if (_queue_count > 0) return;
    
    switch (_init_step) {
        case 0:
            if (_has_rst_pin) {
                gpio_put(_rst_pin, 0);
                sleep_us(10);
                gpio_put(_rst_pin, 1);
            } else {
                enqueue(PENDING_OP_COMMAND, ADS1263_CMD_RESET);
            }
            _state_timer.start(ADS1263_TIMING::RESET_RECOVERY_US);
            _init_step++;
            break;
            
        case 1:
            if (_state_timer.isExpired()) {
                _device_id = 0;
                enqueue(PENDING_OP_REG_READ, ADS1263_REG_ID);
                _init_step++;
            }
            break;
            
        case 2:
            if ((_device_id & ADS1263_ID_DEV_MASK) == ADS1263_ID_ADS1263 ||
                (_device_id & ADS1263_ID_DEV_MASK) == ADS1263_ID_ADS1262) {
                _reg_interface_cache = ADS1263_INTERFACE_STATUS;
                #if ADS1263_ENABLE_CRC
                _reg_interface_cache |= ADS1263_INTERFACE_CRC_CSUM;
                _crc_enabled = true;
                #endif
                enqueue(PENDING_OP_REG_WRITE, ADS1263_REG_INTERFACE, _reg_interface_cache);
                _init_step++;
            } else {
                if (_init_retry_count < 3) {
                    _init_retry_count++;
                    _init_step = 1; // Retry reading ID register
                    _state_timer.start(50000); // 50ms recovery delay before retry
                } else {
                    dispatchError(ADS1263_ERROR_ID, "Device ID validation failed");
                    _state = ADS1263_STATE_ERROR;
                    _init_step = 0;
                }
            }
            break;
            
        case 3:
            _reg_power_cache = ADS1263_POWER_INTREF;
            enqueue(PENDING_OP_REG_WRITE, ADS1263_REG_POWER, _reg_power_cache);
            _state_timer.start(100000);  // 100ms delay for internal reference stabilization
            _init_step++;
            break;
            
        case 4:
            if (_state_timer.isExpired()) {
                _state = ADS1263_STATE_IDLE;
                _init_step = 0;
                dispatchInitComplete(true);
            }
            break;
    }
}

void ADS1263::handleConversion() {
    // Handled by hardware DRDY interrupt check
}

void ADS1263::handleCalibration() {
    switch (_state) {
        case ADS1263_STATE_CAL_START:
            _timeout_timer.start(ADS1263_TIMING::CALIBRATION_TIMEOUT_US);
            _state = ADS1263_STATE_CAL_WAIT_DRDY;
            break;
            
        case ADS1263_STATE_CAL_WAIT_DRDY:
            if (isDRDYLow() || _timeout_timer.isExpired()) {
                bool success = isDRDYLow();
                _state = ADS1263_STATE_SWITCHING_CHANNEL;
                _state_timer.start(calculateSettlingTime());
                // Restore INPMUX from cache
                enqueue(PENDING_OP_REG_WRITE, ADS1263_REG_INPMUX, _reg_inpmux_cache);
                // Restore IDACMAG from cache
#if ADS1263_ENABLE_IDAC
                enqueue(PENDING_OP_REG_WRITE, ADS1263_REG_IDACMAG, _reg_idacmag_cache);
#endif
                dispatchCalibrationComplete((ads1263_cal_type_t)_substate, success);
                _substate = ADS1263_SUBSTATE_NONE;
            }
            break;
            
        default:
            break;
    }
}

void ADS1263::checkHardwareSignals() {
    // Process interrupt flag
    if (_drdy_triggered) {
        _drdy_triggered = false;
        if (_state == ADS1263_STATE_CONVERTING || _state == ADS1263_STATE_START_CONVERSION) {
            enqueue(PENDING_OP_DATA_READ, 0, 0);
        }
    }
}

/* ========================================================================== */
/* SPI LOW LEVEL OPERATIONS                                                   */
/* ========================================================================== */

void ADS1263::executeSPICommand(uint8_t cmd) {
    gpio_put(_cs_pin, 0);
    uint8_t dummy;
    spi_write_read_blocking(_spi, &cmd, &dummy, 1);
    gpio_put(_cs_pin, 1);
}

void ADS1263::executeSPIRegisterWrite(uint8_t reg, uint8_t value) {
    gpio_put(_cs_pin, 0);
    uint8_t tx[3] = { (uint8_t)(ADS1263_CMD_WREG | reg), 0x00, value };
    spi_write_blocking(_spi, tx, 3);
    gpio_put(_cs_pin, 1);
}

uint8_t ADS1263::executeSPIRegisterRead(uint8_t reg) {
    gpio_put(_cs_pin, 0);
    uint8_t tx[3] = { (uint8_t)(ADS1263_CMD_RREG | reg), 0x00, 0x00 };
    uint8_t rx[3];
    spi_write_read_blocking(_spi, tx, rx, 3);
    uint8_t val = rx[2];
    gpio_put(_cs_pin, 1);
    
    return val;
}

void ADS1263::executeSPIDataRead() {
    // Data format: STATUS (if enabled) + 4 bytes Data + CRC (if enabled)
    // We assume STATUS is enabled in init.
    
    uint8_t buf[7];  // Max: STATUS + 4 DATA + CRC
    uint8_t read_len = 5;  // Default: STATUS + 4 DATA
    
    #if ADS1263_ENABLE_CRC
    if (_crc_enabled) read_len = 6;
    #endif
    
    gpio_put(_cs_pin, 0);
    uint8_t cmd = ADS1263_CMD_RDATA1;
    spi_write_blocking(_spi, &cmd, 1);
    spi_read_blocking(_spi, 0x00, buf, read_len);
    gpio_put(_cs_pin, 1);
    
    _last_status_byte = buf[0];
    
    // 32-bit signed data
    _last_raw_data = ((int32_t)buf[1] << 24) | 
                     ((int32_t)buf[2] << 16) | 
                     ((int32_t)buf[3] << 8)  | 
                     buf[4];
    
    // CRC/checksum byte passed through to consumer for end-to-end validation.
    // Validation happens at the stator after RS485 transport, not here.
    uint8_t crc_byte = 0;
    #if ADS1263_ENABLE_CRC
    if (_crc_enabled) crc_byte = buf[5];
    #endif
    
    uint8_t alarms = _last_status_byte & ADS1263_STATUS_ALARM_MASK;
    if (alarms) {
        dispatchAlarm(alarms);
    }
    
    bool is_temp = (_state == ADS1263_STATE_TEMP_READING);
    dispatchDataReady(_last_raw_data, _last_status_byte, is_temp, crc_byte);
    
    if (_adc2_enabled && (_last_status_byte & ADS1263_STATUS_ADC2_NEW)) {
        enqueue(PENDING_OP_ADC2_READ, 0, 0);
    }
}

void ADS1263::executeADC2DataRead() {
    // ADC2 Data format: STATUS + 3 bytes Data + CRC (if enabled)
    
    uint8_t buf[6];
    uint8_t read_len = 4;  // STATUS + 3 DATA
    
    #if ADS1263_ENABLE_CRC
    if (_crc_enabled) read_len = 5;
    #endif
    
    gpio_put(_cs_pin, 0);
    uint8_t cmd = ADS1263_CMD_RDATA2;
    spi_write_blocking(_spi, &cmd, 1);
    spi_read_blocking(_spi, 0x00, buf, read_len);
    gpio_put(_cs_pin, 1);
    
    // ADC2 is 24-bit.
    int32_t raw = ((int32_t)buf[1] << 16) | ((int32_t)buf[2] << 8) | buf[3];
    
    // Sign extend 24-bit to 32-bit
    if (raw & 0x00800000) {
        raw |= 0xFF000000;
    }
    
    #if ADS1263_ENABLE_CRC
    // FIXED: Validate CRC on DATA BYTES ONLY.
    // buf[0] is status, buf[1-3] is data. buf[4] is CRC.
    // Pass pointer starting at buf[1], length 3.
    if (_crc_enabled) {
        uint8_t received_crc = buf[4];
        if (!validateDataCRC(&buf[1], 3, received_crc)) {
            dispatchError(ADS1263_ERROR_CRC, "ADC2 CRC mismatch");
            return;
        }
    }
    #endif
    
    dispatchADC2DataReady(raw, buf[0]);
}

/* ========================================================================== */
/* UTILITY & HELPERS                                                          */
/* ========================================================================== */

void ADS1263::updateLSBValue() {
    ads1263_float_t gain_val;
    if (_pga_bypass) {
        gain_val = 1.0f; // Bypassed PGA means unity gain (1 V/V) on ADC1
    } else {
        gain_val = ADS1263_GAIN_VALUES[_gain];
    }
    _lsb_value = _vref / (gain_val * 2147483648.0f);
}

void ADS1263::updateADC2LSBValue() {
    ads1263_float_t gain_val = ADS1263_ADC2_GAIN_VALUES[_adc2_gain];
    ads1263_float_t vref_val = 2.5f;
    if (_adc2_ref_mode == ADS1263_ADC2_REF_INTERNAL_AVDD) vref_val = 5.0f;
    
    _adc2_lsb_value = vref_val / (gain_val * 8388608.0f);
}

ads1263_float_t ADS1263::toVoltage(int32_t raw) const {
    return (ads1263_float_t)raw * _lsb_value;
}

ads1263_float_t ADS1263::toADC2Voltage(int32_t raw) const {
    return (ads1263_float_t)raw * _adc2_lsb_value;
}

bool ADS1263::isDRDYLow() const {
    return gpio_get(_drdy_pin) == 0;
}

uint32_t ADS1263::calculateSettlingTime() {
    uint32_t period_us = ADS1263_RATE_PERIOD_US[_rate];
    uint32_t settling_cycles;
    
    switch (_filter) {
        case ADS1263_FILTER_SINC1:
            settling_cycles = 1;
            break;
        case ADS1263_FILTER_SINC2:
            settling_cycles = 2;
            break;
        case ADS1263_FILTER_SINC3:
            settling_cycles = 3;
            break;
        case ADS1263_FILTER_SINC4:
            settling_cycles = 4;
            break;
        case ADS1263_FILTER_FIR:
        default:
            settling_cycles = 1;
            break;
    }
    
    // FIXED: Added extra margin for Sinc4 settling time accuracy
    // Datasheet values are slightly higher than pure calculation.
    return (period_us * settling_cycles) + 500;
}

ads1263_status_t ADS1263::parseStatus(uint8_t status_byte) const {
    ads1263_status_t status;
    status.adc2_new  = (status_byte & ADS1263_STATUS_ADC2_NEW) != 0;
    status.adc1_new  = (status_byte & ADS1263_STATUS_ADC1_NEW) != 0;
    status.extclk    = (status_byte & ADS1263_STATUS_EXTCLK) != 0;
    status.ref_alarm = (status_byte & ADS1263_STATUS_REF_ALM) != 0;
    status.pga_low   = (status_byte & ADS1263_STATUS_PGAL_ALM) != 0;
    status.pga_high  = (status_byte & ADS1263_STATUS_PGAH_ALM) != 0;
    status.pga_diff  = (status_byte & ADS1263_STATUS_PGAD_ALM) != 0;
    status.reset     = (status_byte & ADS1263_STATUS_RESET) != 0;
    return status;
}

/* ========================================================================== */
/* CRC/CHECKSUM FUNCTIONS                                                     */
/* ========================================================================== */

uint8_t ADS1263::computeChecksum(const uint8_t* data, uint8_t len) const {
    // Checksum = lower 8 bits of (sum of all data bytes + 0x9B)
    uint16_t sum = 0x9B;  // Start with offset value
    for (uint8_t i = 0; i < len; i++) {
        sum += data[i];
    }
    return (uint8_t)(sum & 0xFF);
}

uint8_t ADS1263::computeCRC(const uint8_t* data, uint8_t len) const {
    // CRC-8-ATM (HEC) polynomial: x^8 + x^2 + x + 1 = 0x07
    uint8_t crc = 0x00;  // Initial value
    for (uint8_t i = 0; i < len; i++) {
        crc ^= data[i];
        for (uint8_t bit = 0; bit < 8; bit++) {
            if (crc & 0x80) {
                crc = (crc << 1) ^ ADS1263_CRC_POLYNOMIAL;
            } else {
                crc <<= 1;
            }
        }
    }
    return crc;
}

bool ADS1263::validateDataCRC(const uint8_t* data, uint8_t len, uint8_t received_crc) const {
    // Check which mode is enabled from interface register cache
    if (_reg_interface_cache & ADS1263_INTERFACE_CRC_CRC) {
        return computeCRC(data, len) == received_crc;
    } else {
        return computeChecksum(data, len) == received_crc;
    }
}

/* ========================================================================== */
/* DISPATCHERS                                                                */
/* ========================================================================== */

void ADS1263::dispatchDataReady(int32_t raw, uint8_t status, bool is_temp, uint8_t crc_byte) {
    if (_callbacks.data_cb) {
        ads1263_data_event_t event;
        event.raw_data = raw;
        event.voltage = is_temp ? 0.0f : toVoltage(raw);
        event.status_byte = status;
        event.status = parseStatus(status);
        event.timestamp_us = time_us_32();
        event.crc_byte = crc_byte;
        _callbacks.data_cb(&event);
    }
}

void ADS1263::dispatchADC2DataReady(int32_t raw, uint8_t status) {
    if (_callbacks.adc2_cb) {
        ads1263_adc2_event_t event;
        event.raw_data = raw;
        event.voltage = toADC2Voltage(raw);
        event.status_byte = status;
        event.timestamp_us = time_us_32();
        _callbacks.adc2_cb(&event);
    }
}

void ADS1263::dispatchInitComplete(bool success) {
    if (_callbacks.init_cb) {
        ads1263_init_event_t e;
        e.success = success;
        e.device_id = _device_id;
        e.duration_us = 0;
        _callbacks.init_cb(&e);
    }
}

void ADS1263::dispatchError(ads1263_error_t error, const char* msg) {
    if (_callbacks.error_cb) {
        ads1263_error_event_t e;
        e.error_code = error;
        e.error_message = msg;
        e.state = _state;
        e.timestamp_us = time_us_32();
        _callbacks.error_cb(&e);
    }
}

void ADS1263::dispatchCalibrationComplete(ads1263_cal_type_t type, bool success) {
    if (_callbacks.cal_cb) {
        ads1263_cal_event_t e;
        e.cal_type = type;
        e.success = success;
        e.duration_us = 0;
        _callbacks.cal_cb(&e);
    }
}

void ADS1263::dispatchAlarm(uint8_t alarm_flags) {
    if (_callbacks.alarm_cb) {
        ads1263_alarm_event_t e;
        e.alarm_flags = alarm_flags;
        e.ref_alarm = (alarm_flags & ADS1263_STATUS_REF_ALM) != 0;
        e.pga_low_alarm = (alarm_flags & ADS1263_STATUS_PGAL_ALM) != 0;
        e.pga_high_alarm = (alarm_flags & ADS1263_STATUS_PGAH_ALM) != 0;
        e.pga_diff_alarm = (alarm_flags & ADS1263_STATUS_PGAD_ALM) != 0;
        e.timestamp_us = time_us_32();
        _callbacks.alarm_cb(&e);
    }
}

void ADS1263::dispatchChannelSwitched(ads1263_input_t pos, ads1263_input_t neg) {
    if (_callbacks.channel_cb) {
        _callbacks.channel_cb(pos, neg);
    }
}

uint8_t ADS1263::readRegisterDirect(uint8_t reg) {
    while (!_spi_limiter.canAccess()) { sleep_us(1); }
    uint8_t val = executeSPIRegisterRead(reg);
    _spi_limiter.markAccess();
    return val;
}