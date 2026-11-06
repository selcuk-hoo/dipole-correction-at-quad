/**
 * @file rotor.cpp
 * @brief ADS1263 Rotor Firmware - Full-Duplex V2 Protocol
 */

#include "hardware/dma.h"
#include "hardware/gpio.h"
#include "hardware/spi.h"
#include "hardware/uart.h"
#include "hardware/watchdog.h"
#include "pico/stdlib.h"
#include <stdio.h>
#include <string.h>

#include "ads1263.h"
#include "mgf_protocol.h"
#include "rs485_dma.h"
#include "rs485_framing.h"
#include "spsc_queue.h"

// ===== TIMING HELPERS =====
static inline uint32_t millis_now(void) {
  return to_ms_since_boot(get_absolute_time());
}

// ===== CONFIGURATION =====
#define RS485_UART uart1
#define RS485_BAUD 8000000
#define RS485_TX_PIN 4
#define RS485_RX_PIN 5
#define RS485_CTRL_PIN 3

#define ADS1263_CS_PIN 17
#define ADS1263_DRDY_PIN 21
#define ADS1263_RST_PIN 20

#ifndef LED_BUILTIN
#define LED_BUILTIN 25
#endif

#define WATCHDOG_TIMEOUT_MS 5000

// ===== GLOBALS =====
ADS1263 ads(ADS1263_CS_PIN, ADS1263_DRDY_PIN, ADS1263_RST_PIN);

// DMA buffers must be aligned for ring buffer!
#define RX_RING_SIZE 1024
__attribute__((aligned(RX_RING_SIZE))) uint8_t rx_dma_buf[RX_RING_SIZE];

mgf::RS485DMA rs485;
mgf::RS485Parser parser(rx_dma_buf, RX_RING_SIZE);

// TX Queue (holds raw bytes ready for DMA)
struct TxItem {
  uint8_t data[32]; // Increased for config report (26 bytes)
  size_t len;
};
mgf::SPSCQueue<TxItem, 256> tx_queue;

volatile uint8_t current_data_mode = MGF_DEFAULT_DATA_MODE;
volatile bool is_calibrating = false;
volatile bool stream_paused = false;

uint16_t error_count = 0;
uint16_t current_error_threshold = 20;
uint32_t sample_count = 0;
uint32_t tx_overflow_count = 0;

static constexpr uint16_t ERROR_THRESHOLDS[16] = {
    20, 20, 20, 20, 20, 25, 25, 30, // 2.5 - 400 SPS
    40, 50, 60, 70, 80, 90, 95, 100 // 1200 - 38400 SPS
};

// --- Encoder Cache (latest value from stator) ---
volatile int32_t enc_curr = 0;
volatile bool encoder_valid = false;
volatile uint32_t encoder_last_update_ms = 0;
volatile bool encoder_stale = true;

// ===== HELPERS =====
void queue_tx(uint8_t type, const void *payload, size_t payload_len) {
  TxItem item;
  item.data[0] = RS485_SYNC_WORD & 0xFF;
  item.data[1] = RS485_SYNC_WORD >> 8;
  item.data[2] = type;
  memcpy(&item.data[3], payload, payload_len);

  item.len = 3 + payload_len; // SYNC + TYPE + PAYLOAD
  if (!tx_queue.push(item)) {
    tx_overflow_count++;
  }
}

void sendACK(uint8_t seq, uint8_t status) {
  AckPacketRS485 ack;
  ack.cmd_seq = seq;
  ack.status = status;
  queue_tx(RS485_TYPE_ACK, &ack.cmd_seq, sizeof(AckPacketRS485) - 3);
}

// ===== CONFIG REPORT =====
void send_config_report() {
  TcpAdcConfig cfg;

  // Read actual register values directly from the silicon
  uint8_t mode0 = ads.readRegisterDirect(ADS1263_REG_MODE0);
  uint8_t mode1 = ads.readRegisterDirect(ADS1263_REG_MODE1);
  uint8_t mode2 = ads.readRegisterDirect(ADS1263_REG_MODE2);
  uint8_t inpmux = ads.readRegisterDirect(ADS1263_REG_INPMUX);
  uint8_t refmux = ads.readRegisterDirect(ADS1263_REG_REFMUX);
  uint8_t power = ads.readRegisterDirect(ADS1263_REG_POWER);
  uint8_t idacmag = ads.readRegisterDirect(ADS1263_REG_IDACMAG);
  uint8_t idacmux = ads.readRegisterDirect(ADS1263_REG_IDACMUX);

  // MODE2
  cfg.gain = (mode2 & ADS1263_MODE2_GAIN_MASK) >> 4;
  cfg.rate = mode2 & ADS1263_MODE2_DR_MASK;
  cfg.pga_bypass = (mode2 & ADS1263_MODE2_BYPASS) ? 1 : 0;

  // MODE1
  cfg.filter = (mode1 & ADS1263_MODE1_FILTER_MASK) >> 5;

  // MODE0
  cfg.chop = (mode0 & ADS1263_MODE0_CHOP_MASK) >> 4;
  cfg.conv_mode = (mode0 & ADS1263_MODE0_RUNMODE_MASK) >> 6;
  cfg.conv_delay = mode0 & ADS1263_MODE0_DELAY_MASK;
  cfg.ref_reverse = (mode0 & ADS1263_MODE0_REFREV) ? 1 : 0;

  // INPMUX
  cfg.input_pos = (inpmux >> 4) & 0x0F;
  cfg.input_neg = inpmux & 0x0F;

  // REFMUX
  cfg.ref_pos = (refmux >> 3) & 0x07;
  cfg.ref_neg = refmux & 0x07;

  // POWER
  cfg.vbias = (power & ADS1263_POWER_VBIAS) ? 1 : 0;
  cfg.intref = (power & ADS1263_POWER_INTREF) ? 1 : 0;

  // IDAC
  cfg.idac1_mag = idacmag & 0x0F;
  cfg.idac2_mag = (idacmag >> 4) & 0x0F;
  cfg.idac1_mux = idacmux & 0x0F;
  cfg.idac2_mux = (idacmux >> 4) & 0x0F;

  // Application
  cfg.data_mode = current_data_mode;

  queue_tx(RS485_TYPE_CONFIG, &cfg, sizeof(TcpAdcConfig));
}

// ===== ADS1263 CALLBACKS =====
void onDataReady(const ads1263_data_event_t *event) {
  if (is_calibrating)
    return;
  if (stream_paused)
    return;

  sample_count++;

  FusedSamplePacket pkt;
  pkt.adc_value = event->raw_data; // Always raw (ADS1263 checksum covers these bytes)

  pkt.encoder = enc_curr;
  pkt.adc_status = event->status_byte;
  pkt.data_type = current_data_mode;

  uint8_t flags = 0;
  if (encoder_valid)
    flags |= 0x01;
  if (encoder_stale)
    flags |= 0x02;
  pkt.flags = flags;
  pkt.adc_crc = event->crc_byte; // Pass through ADS1263 checksum

  queue_tx(RS485_TYPE_FUSED, &pkt.adc_value, sizeof(FusedSamplePacket) - 3);
}

void onInitComplete(const ads1263_init_event_t *event) {
  if (event->success) {
    // Stop default conversions to ensure the chip accepts configuration
    // register writes
    ads.stopConversion();

    // Apply ALL defaults from protocol header
    // MODE2
    ads.setGain((ads1263_gain_t)MGF_DEFAULT_GAIN);
    ads.setDataRate((ads1263_rate_t)MGF_DEFAULT_RATE);
    ads.setPGABypass(MGF_DEFAULT_PGA_BYPASS);
    // MODE1
    ads.setFilter((ads1263_filter_t)MGF_DEFAULT_FILTER);
    // MODE0
    ads.setChopMode((ads1263_chop_mode_t)MGF_DEFAULT_CHOP);
    ads.setConversionMode((ads1263_conv_mode_t)MGF_DEFAULT_CONV_MODE);
    ads.setConversionDelay((ads1263_delay_t)MGF_DEFAULT_CONV_DELAY);
    ads.setRefReverse(MGF_DEFAULT_REF_REVERSE);
    // INPMUX
    ads.setChannel((ads1263_input_t)MGF_DEFAULT_INPUT_POS,
                   (ads1263_input_t)MGF_DEFAULT_INPUT_NEG);
    // REFMUX
    ads.setReference((ads1263_refp_t)MGF_DEFAULT_REF_POS,
                     (ads1263_refn_t)MGF_DEFAULT_REF_NEG);
    // POWER
    ads.setInternalRefAlwaysOn(MGF_DEFAULT_INTREF);
    ads.enableVBias(MGF_DEFAULT_VBIAS);

    // Application
    current_data_mode = MGF_DEFAULT_DATA_MODE;
    current_error_threshold = ERROR_THRESHOLDS[MGF_DEFAULT_RATE];

    error_count = 0;

    // Broadcast initial config to stator
    send_config_report();

    // Otomatik Offset Kalibrasyonu (Bittiğinde onCalibrationComplete içinde
    // ads.startContinuous() otomatik cagrilir)
    is_calibrating = true;
    ads.calibrateOffset();
  } else {
    error_count += 5;
  }
}

void onCalibrationComplete(const ads1263_cal_event_t *event) {
  is_calibrating = false;

  if (event->cal_type == ADS1263_CAL_SYSTEM_GAIN) {
    // Read register values to check for saturation
    uint8_t fscal0 = ads.readRegisterDirect(ADS1263_REG_FSCAL0);
    uint8_t fscal1 = ads.readRegisterDirect(ADS1263_REG_FSCAL1);
    uint8_t fscal2 = ads.readRegisterDirect(ADS1263_REG_FSCAL2);
    uint32_t fscal = ((uint32_t)fscal2 << 16) | ((uint32_t)fscal1 << 8) | fscal0;

    if (fscal >= 0xFFFFFF) {
      // Saturation detected! Restore default scaling (0x400000)
      ads.writeFullScaleCalibration(0x400000);
      ads.flushPendingOperations();

      // Report calibration failure to host
      sendACK(CMD_CALIBRATE_GAIN, ACK_ERROR);
    }
  }

  ads.startContinuous();
  // Report config after calibration (cal registers may have changed)
  send_config_report();
}

// ===== RX PACKET PARSER CALLBACK =====
void handle_incoming(uint8_t type, const uint8_t *pkt, size_t len) {
  if (type == RS485_TYPE_ENC_UPDATE) {
    EncUpdatePacket enc_pkt;
    memcpy(&enc_pkt.encoder, &pkt[3], 6); // encoder(4) + seq(2)

    enc_curr = enc_pkt.encoder;
    encoder_valid = true;
    encoder_last_update_ms = millis_now();
    encoder_stale = false;
    error_count = 0; // reset error on healthy rx

  } else if (type == RS485_TYPE_CMD) {
    CmdPacketRS485 cmd;
    memcpy(&cmd.cmd_seq, &pkt[3], 6); // seq(1) + cmd(1) + param(4)

    uint8_t ack_status = ACK_OK;

    if (is_calibrating) {
      ack_status = ACK_ERROR; // Busy
    } else {
      switch (cmd.cmd) {

      // ===== MODE2: Gain (Table 9-40) =====
      case CMD_SET_GAIN:
        if (cmd.param_raw > 5) { // ADS1263_GAIN_32 = 5
          ack_status = ACK_INVALID_PARAM;
        } else {
          ads.stopConversion();
          ads.flushPendingOperations();
          ads.setGain((ads1263_gain_t)cmd.param_raw);
          ads.flushPendingOperations();
          ads.startContinuous();
          send_config_report();
        }
        break;

      // ===== MODE2: Data Rate (Table 9-40) =====
      case CMD_SET_RATE: {
        uint8_t rate_idx = cmd.param_raw & 0x0F;
        if (rate_idx > 15) { // 0–15
          ack_status = ACK_INVALID_PARAM;
        } else {
          ads.stopConversion();
          ads.flushPendingOperations();
          ads.setDataRate((ads1263_rate_t)rate_idx);
          current_error_threshold = ERROR_THRESHOLDS[rate_idx];
          ads.flushPendingOperations();
          ads.startContinuous();
          send_config_report();
        }
        break;
      }

      // ===== MODE1: Filter (Table 9-39) =====
      case CMD_SET_FILTER:
        if (cmd.param_raw > 4) { // ADS1263_FILTER_FIR = 4
          ack_status = ACK_INVALID_PARAM;
        } else {
          ads1263_filter_t filter = (ads1263_filter_t)cmd.param_raw;
          ads1263_rate_t rate = ads.getRate();
          bool valid = true;
          if (filter == ADS1263_FILTER_FIR && rate > ADS1263_RATE_20) {
            valid = false;
          } else if (filter > ADS1263_FILTER_SINC1 &&
                     rate >= ADS1263_RATE_14400) {
            valid = false;
          }

          if (!valid) {
            ack_status = ACK_INVALID_PARAM;
          } else {
            ads.stopConversion();
            ads.flushPendingOperations();
            ads.setFilter(filter);
            ads.flushPendingOperations();
            ads.startContinuous();
            send_config_report();
          }
        }
        break;

      // ===== MODE0: Chop Mode (Table 9-38) =====
      case CMD_SET_CHOP:
        if (cmd.param_raw > 3) { // ADS1263_CHOP_BOTH = 3
          ack_status = ACK_INVALID_PARAM;
        } else {
          ads1263_chop_mode_t chop = (ads1263_chop_mode_t)cmd.param_raw;
          if (chop != ADS1263_CHOP_OFF &&
              ads.getConversionMode() == ADS1263_CONV_PULSE) {
            ack_status = ACK_INVALID_PARAM;
          } else {
            ads.stopConversion();
            ads.flushPendingOperations();
            ads.setChopMode(chop);
            ads.flushPendingOperations();
            ads.startContinuous();
            send_config_report();
          }
        }
        break;

      // ===== MODE2: PGA Bypass (Table 9-40, bit 7) =====
      case CMD_SET_PGA_BYPASS:
        ads.stopConversion();
        ads.flushPendingOperations();
        ads.setPGABypass(cmd.param_raw != 0);
        ads.flushPendingOperations();
        ads.startContinuous();
        send_config_report();
        break;

      // ===== MODE0: Conversion Mode (Table 9-38, bit 6) =====
      case CMD_SET_CONV_MODE:
        if (cmd.param_raw > 1) {
          ack_status = ACK_INVALID_PARAM;
        } else {
          ads1263_conv_mode_t conv_mode = (ads1263_conv_mode_t)cmd.param_raw;
          if (conv_mode == ADS1263_CONV_PULSE &&
              ads.getChopMode() != ADS1263_CHOP_OFF) {
            ack_status = ACK_INVALID_PARAM;
          } else {
            ads.stopConversion();
            ads.flushPendingOperations();
            ads.setConversionMode(conv_mode);
            ads.flushPendingOperations();
            ads.startContinuous();
            send_config_report();
          }
        }
        break;

      // ===== MODE0: Conversion Delay (Table 9-38, bits [3:0]) =====
      case CMD_SET_CONV_DELAY:
        if (cmd.param_raw > 11) { // 0x0B max
          ack_status = ACK_INVALID_PARAM;
        } else {
          ads.stopConversion();
          ads.flushPendingOperations();
          ads.setConversionDelay((ads1263_delay_t)cmd.param_raw);
          ads.flushPendingOperations();
          ads.startContinuous();
          send_config_report();
        }
        break;

      // ===== REFMUX: Reference MUX (Table 9-46) =====
      case CMD_SET_REF_MUX: {
        uint8_t rp = (cmd.param_raw >> 8) & 0xFF;
        uint8_t rn = cmd.param_raw & 0xFF;
        if (rp > 4 || rn > 4) { // Max refp/refn = 4
          ack_status = ACK_INVALID_PARAM;
        } else {
          ads.stopConversion();
          ads.flushPendingOperations();
          ads.setReference((ads1263_refp_t)rp, (ads1263_refn_t)rn);
          ads.flushPendingOperations();
          ads.startContinuous();
          send_config_report();
        }
        break;
      }

      // ===== MODE0: Reference Reverse (Table 9-38, bit 7) =====
      case CMD_SET_REF_REVERSE:
        ads.stopConversion();
        ads.flushPendingOperations();
        ads.setRefReverse(cmd.param_raw != 0);
        ads.flushPendingOperations();
        ads.startContinuous();
        send_config_report();
        break;

      // ===== POWER: VBIAS (Table 9-36, bit 1) =====
      case CMD_SET_VBIAS:
        ads.stopConversion();
        ads.flushPendingOperations();
        ads.enableVBias(cmd.param_raw != 0);
        ads.flushPendingOperations();
        ads.startContinuous();
        send_config_report();
        break;

      // ===== POWER: Internal Ref Always On (Table 9-36, bit 0) =====
      case CMD_SET_INTREF:
        ads.stopConversion();
        ads.flushPendingOperations();
        ads.setInternalRefAlwaysOn(cmd.param_raw != 0);
        ads.flushPendingOperations();
        ads.startContinuous();
        send_config_report();
        break;

      // ===== IDAC: Magnitude & MUX (Table 9-44/45) =====
      case CMD_SET_IDAC: {
        uint8_t idac2_mag = (cmd.param_raw >> 24) & 0xFF;
        uint8_t idac1_mag = (cmd.param_raw >> 16) & 0xFF;
        uint8_t idac2_mux = (cmd.param_raw >> 8) & 0xFF;
        uint8_t idac1_mux = cmd.param_raw & 0xFF;
        if (idac1_mag > 0x0A || idac2_mag > 0x0A || idac1_mux > 0x0F ||
            idac2_mux > 0x0F) {
          ack_status = ACK_INVALID_PARAM;
        } else {
          ads.stopConversion();
          ads.flushPendingOperations();
          ads.setIDAC((ads1263_idac_magnitude_t)idac1_mag,
                      (ads1263_idac_magnitude_t)idac2_mag,
                      (ads1263_input_t)idac1_mux, (ads1263_input_t)idac2_mux);
          ads.flushPendingOperations();
          ads.startContinuous();
          send_config_report();
        }
        break;
      }

      // ===== Application: Data Mode =====
      case CMD_SET_DATA_MODE:
        if (cmd.param_raw > 1) {
          ack_status = ACK_INVALID_PARAM;
        } else {
          current_data_mode = cmd.param_raw;
          send_config_report();
        }
        break;

      // ===== INPMUX: Scan Channels (Table 9-41) =====
      case CMD_SET_SCAN_CHANNELS: {
        uint8_t pos = (cmd.param_raw >> 8) & 0xFF;
        uint8_t neg = cmd.param_raw & 0xFF;
        if (pos > 0x0F || neg > 0x0F) {
          ack_status = ACK_INVALID_PARAM;
        } else {
          ads.stopConversion();
          ads.flushPendingOperations();
          ads.setChannel((ads1263_input_t)pos, (ads1263_input_t)neg);
          ads.flushPendingOperations();
          ads.startContinuous();
          send_config_report();
        }
        break;
      }

      // ===== Calibration: Self-Offset (SFOCAL1) =====
      // Datasheet 9.4.8: Stop conversion, then issue calibration command.
      // SFOCAL1 internally shorts inputs and measures offset.
      // (Bittiğinde onCalibrationComplete içinde ads.startContinuous() cagrilir)
      case CMD_CALIBRATE_OFFSET:
        ads.stopConversion();
        ads.flushPendingOperations();
        is_calibrating = true;
        if (cmd.param_raw == 1) {
          ads.calibrateSystemOffset();
        } else {
          ads.calibrateOffset();
        }
        break;

      // ===== Calibration: System Gain (SYGCAL1) =====
      // Datasheet 9.4.8: Connect full-scale reference to inputs,
      // then issue gain calibration command. DRDY goes low when complete.
      case CMD_CALIBRATE_GAIN:
        ads.stopConversion();
        ads.flushPendingOperations();
        is_calibrating = true;
        ads.calibrateSystemGain();
        break;

      // ===== Calibration: Reset Defaults =====
      case CMD_RESET_CALIBRATION:
        ads.stopConversion();
        ads.flushPendingOperations();
        is_calibrating = false;
        ads.writeOffsetCalibration(0x000000);
        ads.writeFullScaleCalibration(0x400000);
        ads.flushPendingOperations();
        ads.startContinuous();
        send_config_report();
        break;

      // ===== ADC Control =====
      case CMD_START_ADC:
        ads.startContinuous();
        break;
      case CMD_STOP_ADC:
        ads.stopConversion();
        break;

      // ===== Stream Control =====
      case CMD_PAUSE_STREAM:
        stream_paused = true;
        break;
      case CMD_RESUME_STREAM:
        stream_paused = false;
        break;

      // ===== Query: Get Full ADC Config =====
      case CMD_GET_ADC_CONFIG:
        send_config_report();
        break;

      // ===== Stator-side commands (rejected) =====
      case CMD_SET_MOTOR_SPEED:
      case CMD_SET_SERVO:
      case CMD_CLEAR_PULSE:
      case CMD_RESET_ALARM:
      case CMD_SET_ENCODER_PPR:
      case CMD_SPEED_RAMP:
        ack_status = ACK_INVALID_CMD;
        break;

      default:
        ack_status = ACK_INVALID_CMD;
        error_count++;
        break;
      }
    }
    sendACK(cmd.cmd_seq, ack_status);
  }
}

int main() {
  stdio_init_all();
  gpio_init(LED_BUILTIN);
  gpio_set_dir(LED_BUILTIN, GPIO_OUT);
  watchdog_enable(WATCHDOG_TIMEOUT_MS, 1);

  rs485.begin(RS485_UART, RS485_BAUD, RS485_TX_PIN, RS485_RX_PIN,
              RS485_CTRL_PIN, 255, rx_dma_buf, RX_RING_SIZE);

  ads.onInitComplete(onInitComplete);
  ads.onDataReady(onDataReady);
  ads.onCalibrationComplete(onCalibrationComplete);

  // Set up SPI pins
  spi_init(spi0, 8000000);
  gpio_set_function(16, GPIO_FUNC_SPI); // RX / MISO
  gpio_set_function(18, GPIO_FUNC_SPI); // SCK
  gpio_set_function(19, GPIO_FUNC_SPI); // TX / MOSI

  ads.begin(spi0, 8000000);

  // ===== MAIN LOOP =====
  while (true) {
    watchdog_update();
    uint32_t now_ms = millis_now();

    // LED blink (5 Hz)
    static uint32_t led_timer = 0;
    if (now_ms - led_timer > 100) {
      gpio_put(LED_BUILTIN, !gpio_get(LED_BUILTIN));
      led_timer = now_ms;
    }

    if (error_count >= current_error_threshold)
      watchdog_reboot(0, 0, 0);

    // Check encoder staleness
    if (encoder_valid && (now_ms - encoder_last_update_ms > 500)) {
      encoder_stale = true;
    }

    // Drain TX queue via DMA (burst up to 4 to prevent backpressure)
    for (int tx_burst = 0; tx_burst < 4 && !tx_queue.empty(); tx_burst++) {
      if (rs485.is_tx_busy())
        break;
      TxItem item;
      tx_queue.pop(item);
      rs485.send(item.data, item.len);
    }

    ads.update();

    // Parse RX ring buffer
    parser.parse(rs485.rx_write_pos(), handle_incoming);

    // Periodic status telemetry (every 500ms)
    static uint32_t status_timer = 0;
    if (now_ms - status_timer >= 500) {
      status_timer = now_ms;
      StatusPacketRS485 status;
      status.err_cnt = error_count;
      status.sample_cnt = sample_count;
      status.uptime = now_ms;
      status.adc_state = ads.getState();
      queue_tx(RS485_TYPE_STATUS, &status.err_cnt,
               sizeof(StatusPacketRS485) - 3);
    }
  }
}