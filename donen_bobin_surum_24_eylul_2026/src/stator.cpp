/**
 * @file stator.cpp
 * @brief MGF Stator - Dual Core (Multicore) Implementation - V2 Protocol
 * @details Fully native Pico SDK implementation (no Arduino framework).
 *
 * Core 0: Ethernet (W5500 via Wiznet ioLibrary), RS485, Protocol V2
 * Core 1: Motor (timer-based stepper), WS2812 LEDs, GPIO
 */

#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "hardware/clocks.h"
#include "hardware/gpio.h"
#include "hardware/pio.h"
#include "hardware/spi.h"
#include "hardware/timer.h"
#include "hardware/uart.h"
#include "hardware/watchdog.h"
#include "pico/multicore.h"
#include "pico/stdlib.h"

// PIO-generated headers (built by CMake pico_generate_pio_header)
#include "quadrature.pio.h"
#include "stepper.pio.h"
#include "ws2812.pio.h"

// Wiznet ioLibrary (raw C driver — needs extern "C" for C++ linkage)
extern "C" {
#include "socket.h"
#include "wizchip_conf.h"
}

// Project headers
#include "crc.h"
#include "dhcp_server.h"
#include "mgf_protocol.h"
#include "rs485_dma.h"
#include "rs485_framing.h"
#include "spsc_queue.h"
#include "w5500_spi.h"

// ===== TIMING HELPER =====
static inline uint32_t millis_now(void) {
  return to_ms_since_boot(get_absolute_time());
}

static inline uint32_t micros_now(void) { return time_us_32(); }

/// ADS1263 Checksum: (sum of data bytes + 0x9B) & 0xFF
/// Matches ADS1263 datasheet Section 9.4.7.3.3.1
static inline uint8_t ads1263_checksum(const uint8_t *data, uint8_t len) {
  uint16_t sum = 0x9B;
  for (uint8_t i = 0; i < len; i++) sum += data[i];
  return (uint8_t)(sum & 0xFF);
}

// ===== CONFIGURATION =====
#define UART_HW uart1

// RS485 PINOUT
#define RS485_TX_PIN 4
#define RS485_RX_PIN 5
#define RS485_CTRL_PIN 3
#define RS485_BAUD 8000000

// LED
#define LED_PIN 13
#define LED_COUNT 8
#define LED_BRIGHT 40

// ===== SHARED STATE (Core 0 -> Core 1) =====
volatile float shared_motor_speed = 0.0f;
volatile float shared_actual_motor_speed = 0.0f;
volatile int32_t stepper_steps = 0;
volatile bool shared_servo_state = false;
volatile bool shared_pulse_clear_req = false;
volatile bool shared_alarm_reset_req = false;
volatile bool shared_ethernet_connected = false;
volatile int32_t shared_encoder_value = 0; // Core 0 writes, Core 1 reads

// LED Vars
uint32_t led_timer = 0;
bool led6_state = false;
uint8_t led_anim_phase = 0;
volatile uint32_t led_flash_timestamps[8] = {0};

// MOTOR & NETWORK
#define MOTOR_STEPS_PER_REV 3600
#define MOTOR_STEP_PIN 8
#define MOTOR_DIR_PIN 9
#define SERVO_PIN 10
#define PULSE_CLEAR_PIN 11
#define ALARM_RESET_PIN 12
#define TCP_PORT 5000
#define UDP_DISCOVERY_PORT 5001

// ENCODER SETTINGS
#define QUADRATURE_A_PIN 7
#define QUADRATURE_B_PIN 6

volatile uint16_t current_enc_ppr = 3600;
volatile uint32_t shared_motor_accel = 36000;

PIO pio_enc = pio0;
uint pio_enc_sm = 0;
uint pio_enc_offset = 0;
volatile int32_t encoder_offset = 0;
volatile uint16_t enc_seq = 0;

// Encoder-derived speed measurement
volatile float encoder_measured_speed_hz = 0.0f;
static int32_t enc_speed_last_pos = 0;
static uint32_t enc_speed_last_time_ms = 0;

// ===== STEPPER ENGINE (PIO-Based, jitter-free) =====
struct StepperState {
  volatile bool enabled;
  volatile bool running;
  volatile int32_t direction;         // +1 or -1
  volatile uint32_t step_interval_us; // microseconds between steps
  volatile uint32_t acceleration;     // steps/s^2
  volatile float current_speed;       // steps/s
  volatile float target_speed;        // steps/s
  volatile uint32_t last_step_us;
  volatile uint32_t last_accel_us;
};
static StepperState stepper = {};

static PIO pio_stepper = pio0;
static uint stepper_sm = 0;
static uint stepper_offset = 0;

static void stepper_init(void) {
  gpio_init(MOTOR_DIR_PIN);
  gpio_set_dir(MOTOR_DIR_PIN, GPIO_OUT);
  gpio_put(MOTOR_DIR_PIN, 1);

  stepper.enabled = true;
  stepper.running = false;
  stepper.direction = 1;
  stepper.step_interval_us = 0;
  stepper.acceleration = 3600;
  stepper.current_speed = 0.0f;
  stepper.target_speed = 0.0f;
  stepper.last_step_us = micros_now();
  stepper.last_accel_us = micros_now();

  // Initialize PIO state machine
  stepper_offset = pio_add_program(pio_stepper, &stepper_program);
  stepper_sm = pio_claim_unused_sm(pio_stepper, true);
  stepper_program_init(pio_stepper, stepper_sm, stepper_offset, MOTOR_STEP_PIN);
}

/**
 * @brief Non-blocking stepper update — call from Core 1 loop
 * @details Implements trapezoidal acceleration. Generates step pulses by
 *          toggling the STEP pin at the computed interval.
 */
static void stepper_update(void) {
  if (!stepper.enabled)
    return;

  float target = stepper.target_speed;
  uint32_t now = micros_now();

  // Acceleration ramp (every 1ms)
  uint32_t accel_elapsed = now - stepper.last_accel_us;
  if (accel_elapsed >= 1000) {
    stepper.last_accel_us = now;
    float dt = accel_elapsed / 1000000.0f;
    float accel = (float)stepper.acceleration;

    if (stepper.current_speed < target) {
      stepper.current_speed += accel * dt;
      if (stepper.current_speed > target)
        stepper.current_speed = target;
    } else if (stepper.current_speed > target) {
      stepper.current_speed -= accel * dt;
      if (stepper.current_speed < target)
        stepper.current_speed = target;
    }
  }

  float speed = fabsf(stepper.current_speed);

  if (speed < 1.0f) {
    stepper.running = false;
    stepper.current_speed = 0.0f;
    shared_actual_motor_speed = 0.0f;

    // If stopped, clear the FIFOs and restart state machine
    pio_sm_set_enabled(pio_stepper, stepper_sm, false);
    pio_sm_clear_fifos(pio_stepper, stepper_sm);
    pio_sm_restart(pio_stepper, stepper_sm);
    pio_sm_exec(pio_stepper, stepper_sm, pio_encode_jmp(stepper_offset));
    pio_sm_set_enabled(pio_stepper, stepper_sm, true);
    return;
  }

  stepper.running = true;
  stepper.direction = (stepper.current_speed >= 0) ? 1 : -1;
  gpio_put(MOTOR_DIR_PIN, stepper.direction > 0 ? 1 : 0);

  // Speed in steps/sec. Period in 10 MHz clock cycles = 10000000.0f / speed.
  uint32_t interval_cycles = (uint32_t)(10000000.0f / speed);
  
  // Cap at 100 kHz step rate (100 cycles at 10 MHz)
  if (interval_cycles < 100)
    interval_cycles = 100;

  shared_actual_motor_speed =
      (float)stepper.direction * (10000000.0f / (float)interval_cycles);

  // Calculate PIO delay value (interval_cycles - 24 cycles overhead)
  uint32_t pio_delay = (interval_cycles > 24) ? (interval_cycles - 24) : 0;

  // Feed steps into PIO FIFO when there is empty space
  while (!pio_sm_is_tx_fifo_full(pio_stepper, stepper_sm)) {
    pio_sm_put(pio_stepper, stepper_sm, pio_delay);
    if (stepper.direction > 0) {
      stepper_steps++;
    } else {
      stepper_steps--;
    }
  }
}

// ===== WS2812 LED DRIVER (PIO-based, replaces Adafruit_NeoPixel) =====
static PIO ws2812_pio = pio1;
static uint ws2812_sm = 0;

static uint32_t ws2812_buffer[LED_COUNT] = {0};

static inline uint32_t ws2812_rgb(uint8_t r, uint8_t g, uint8_t b) {
  // WS2812 expects GRB order, shifted left by 8 for autopush
  return ((uint32_t)g << 24) | ((uint32_t)r << 16) | ((uint32_t)b << 8);
}

static void ws2812_init(void) {
  uint offset = pio_add_program(ws2812_pio, &ws2812_program);
  ws2812_sm = pio_claim_unused_sm(ws2812_pio, true);
  ws2812_program_init(ws2812_pio, ws2812_sm, offset, LED_PIN, 800000, false);
}

static void ws2812_set_pixel(uint idx, uint8_t r, uint8_t g, uint8_t b) {
  if (idx < LED_COUNT) {
    // Apply brightness scaling
    r = (r * LED_BRIGHT) / 255;
    g = (g * LED_BRIGHT) / 255;
    b = (b * LED_BRIGHT) / 255;
    ws2812_buffer[idx] = ws2812_rgb(r, g, b);
  }
}

static void ws2812_show(void) {
  for (uint i = 0; i < LED_COUNT; i++) {
    pio_sm_put_blocking(ws2812_pio, ws2812_sm, ws2812_buffer[i]);
  }
}

// IP Settings (link-local)
static uint8_t mac[6] = {0xDE, 0xAD, 0xBE, 0xEF, 0xFE, 0xED};
static uint8_t myIP[4] = {169, 254, 1, 177};
static uint8_t subnet[4] = {255, 255, 0, 0};
static uint8_t gateway[4] = {169, 254, 1, 1};

// Wiznet socket allocation
#define SOCK_TCP 0
#define SOCK_UDP 1
#define SOCK_DHCPSRV 2

DhcpServer dhcpServer;

bool ethernet_online = false;
bool dhcp_server_active = false;
bool tcp_client_connected = false;
bool rotor_online = false;
uint32_t last_rotor_packet_time = 0;

// Cached ADC config (updated from rotor config reports)
TcpAdcConfig cached_adc_config = {
    MGF_DEFAULT_GAIN,       MGF_DEFAULT_RATE,        MGF_DEFAULT_PGA_BYPASS,
    MGF_DEFAULT_FILTER,     MGF_DEFAULT_CHOP,        MGF_DEFAULT_CONV_MODE,
    MGF_DEFAULT_CONV_DELAY, MGF_DEFAULT_REF_REVERSE, MGF_DEFAULT_INPUT_POS,
    MGF_DEFAULT_INPUT_NEG,  MGF_DEFAULT_REF_POS,     MGF_DEFAULT_REF_NEG,
    MGF_DEFAULT_VBIAS,      MGF_DEFAULT_INTREF,      MGF_DEFAULT_IDAC1_MAG,
    MGF_DEFAULT_IDAC2_MAG,  MGF_DEFAULT_IDAC1_MUX,   MGF_DEFAULT_IDAC2_MUX,
    MGF_DEFAULT_DATA_MODE};

// ===== RS485 & DMA =====
#define RX_RING_SIZE 4096
__attribute__((aligned(RX_RING_SIZE))) uint8_t rs485_rx_buf[RX_RING_SIZE];

mgf::RS485DMA rs485;
mgf::RS485Parser parser(rs485_rx_buf, RX_RING_SIZE);

// TX Queues
struct TxItem {
  uint8_t data[24];
  size_t len;
};
mgf::SPSCQueue<TxItem, 16> enc_tx_queue;
mgf::SPSCQueue<TxItem, 8> cmd_tx_queue;

// (Encoder timer removed — encoder is polled in Core 0 main loop)

// ===== TCP QUEUE =====
struct TcpBufferItem {
  uint8_t data[48]; // Max TLV packet size (HelloAck with config = ~41 bytes)
  size_t len;
};
mgf::SPSCQueue<TcpBufferItem, 2048> tcp_queue;

uint32_t tcp_queue_loss_count = 0;
uint16_t rs485_crc_error_count = 0;
uint16_t tcp_seq = 0;
static uint8_t sequence_to_cmd[256] = {0};

// ===== TCP RX =====
#define TCP_RX_BUF_SIZE 2048
uint8_t tcp_rx_buf[TCP_RX_BUF_SIZE];
uint16_t tcp_rx_head = 0;
uint16_t tcp_rx_tail = 0;

// ===== PIO ENCODER =====
void init_pio_encoder() {
  pio_enc_offset = pio_add_program(pio_enc, &quadratureA_program);
  pio_enc_sm = pio_claim_unused_sm(pio_enc, true);
  gpio_init(QUADRATURE_A_PIN);
  gpio_init(QUADRATURE_B_PIN);
  gpio_set_dir(QUADRATURE_A_PIN, GPIO_IN);
  gpio_set_dir(QUADRATURE_B_PIN, GPIO_IN);
  quadratureA_program_init(pio_enc, pio_enc_sm, pio_enc_offset,
                           QUADRATURE_A_PIN, QUADRATURE_B_PIN);
  pio_sm_set_enabled(pio_enc, pio_enc_sm, true);
}

int32_t getRawEncoderCounts() {
  pio_sm_exec_wait_blocking(pio_enc, pio_enc_sm, pio_encode_in(pio_x, 32));
  return (int32_t)pio_sm_get_blocking(pio_enc, pio_enc_sm);
}

int32_t getRealEncoder() {
  int32_t raw_val = getRawEncoderCounts();
  int32_t adjusted_val = (raw_val - encoder_offset) % current_enc_ppr;
  if (adjusted_val < 0)
    adjusted_val += current_enc_ppr;
  return adjusted_val;
}

// (Encoder timer callback removed — push-on-change polling is in Core 0 main
// loop)

// ===== TCP UTILS =====
void push_tcp_packet(uint8_t type, const void *payload, size_t payload_len) {
  if (!shared_ethernet_connected)
    return;

  TcpHeader hdr;
  hdr.magic = MGF_TCP_MAGIC;
  hdr.length = payload_len;
  hdr.type = type;
  hdr.sequence = tcp_seq++;

  TcpBufferItem item;
  item.len = sizeof(hdr) + payload_len + 4;

  memcpy(item.data, &hdr, sizeof(hdr));
  memcpy(item.data + sizeof(hdr), payload, payload_len);

  uint32_t c = crc32(item.data, sizeof(hdr) + payload_len);
  memcpy(item.data + sizeof(hdr) + payload_len, &c, 4);

  if (!tcp_queue.push(item)) {
    tcp_queue_loss_count++;
  }
}

// ===== RS485 PARSER CALLBACK =====
void on_rs485_packet(uint8_t type, const uint8_t *pkt, size_t len) {
  rotor_online = true;
  last_rotor_packet_time = millis_now();
  led_flash_timestamps[2] = millis_now(); // RX Flash

  if (type == RS485_TYPE_FUSED) {
    FusedSamplePacket rs485_fused;
    memcpy(&rs485_fused, pkt, sizeof(FusedSamplePacket));

    // Validate ADS1263 checksum (covers adc_value bytes end-to-end)
    uint8_t computed = ads1263_checksum((const uint8_t *)&rs485_fused.adc_value, 4);
    if (computed != rs485_fused.adc_crc) {
      rs485_crc_error_count++;
      return; // Drop corrupt sample
    }

    TcpFusedSample tcp_payload;
    tcp_payload.adc_value = rs485_fused.adc_value;
    tcp_payload.encoder = rs485_fused.encoder;
    tcp_payload.stepper_steps = stepper_steps;
    tcp_payload.adc_status = rs485_fused.adc_status;
    tcp_payload.data_type = rs485_fused.data_type;
    tcp_payload.flags = rs485_fused.flags;

    push_tcp_packet(TCP_TYPE_FUSED_SAMPLE, &tcp_payload,
                    sizeof(TcpFusedSample));

  } else if (type == RS485_TYPE_ACK) {
    AckPacketRS485 ack;
    memcpy(&ack.cmd_seq, &pkt[3], sizeof(AckPacketRS485) - 3);

    TcpAck tcp_payload;
    tcp_payload.cmd = sequence_to_cmd[ack.cmd_seq];
    tcp_payload.status = ack.status;
    push_tcp_packet(TCP_TYPE_ACK, &tcp_payload, sizeof(TcpAck));

  } else if (type == RS485_TYPE_CONFIG) {
    // Cache config and forward to host
    memcpy(&cached_adc_config, &pkt[3], sizeof(TcpAdcConfig));
    push_tcp_packet(TCP_TYPE_ADC_CONFIG, &cached_adc_config,
                    sizeof(TcpAdcConfig));

  } else if (type == RS485_TYPE_STATUS) {
    // Status updates can be merged into host telemetry
  }
}

// ===== COMMAND ROUTING =====
bool handleHostCommand(const uint8_t *buffer, size_t len) {
  if (len < sizeof(TcpHeader) + 4)
    return false;

  TcpHeader *hdr = (TcpHeader *)buffer;
  if (hdr->magic != MGF_TCP_MAGIC)
    return false;

  uint32_t expected_crc = crc32(buffer, sizeof(TcpHeader) + hdr->length);
  uint32_t received_crc;
  memcpy(&received_crc, buffer + sizeof(TcpHeader) + hdr->length, 4);
  if (expected_crc != received_crc)
    return false;

  if (hdr->type == TCP_TYPE_HELLO) {
    TcpHelloAck ack = {0};
    ack.protocol_version = MGF_PROTOCOL_VERSION;
    ack.capabilities = 0;
    ack.encoder_ppr = current_enc_ppr;
    ack.motor_speed_hz = shared_actual_motor_speed / MOTOR_STEPS_PER_REV;
    ack.adc_config = cached_adc_config;
    push_tcp_packet(TCP_TYPE_HELLO_ACK, &ack, sizeof(ack));
    return true;
  }

  if (hdr->type != TCP_TYPE_CMD)
    return true; // Unknown but valid packet with valid CRC

  TcpCmd cmd;
  memcpy(&cmd, buffer + sizeof(TcpHeader), sizeof(TcpCmd));

  // Store sequence number -> command ID mapping
  sequence_to_cmd[hdr->sequence & 0xFF] = cmd.cmd;

  switch (cmd.cmd) {
  case CMD_SET_MOTOR_SPEED:
    shared_motor_speed = CMD_PARAM_FLOAT(cmd.param_raw) * MOTOR_STEPS_PER_REV;
    stepper.target_speed = shared_motor_speed;
    break;
  case CMD_SET_SERVO:
    shared_servo_state = (cmd.param_raw & 0x01);
    break;
  case CMD_CLEAR_PULSE:
    shared_pulse_clear_req = true;
    encoder_offset = getRawEncoderCounts();
    stepper_steps = 0;
    break;
  case CMD_RESET_ALARM:
    shared_alarm_reset_req = true;
    break;
  case CMD_SET_ENCODER_PPR:
    current_enc_ppr = (uint16_t)(cmd.param_raw & 0xFFFF);
    break;
  case CMD_SPEED_RAMP:
    shared_motor_accel = cmd.param_raw;
    stepper.acceleration = cmd.param_raw;
    break;

  default: {
    CmdPacketRS485 rs485_cmd;
    rs485_cmd.sync = RS485_SYNC_WORD;
    rs485_cmd.type = RS485_TYPE_CMD;
    rs485_cmd.cmd_seq = hdr->sequence & 0xFF;
    rs485_cmd.cmd = cmd.cmd;
    rs485_cmd.param_raw = cmd.param_raw;

    TxItem item;
    memcpy(item.data, &rs485_cmd, sizeof(rs485_cmd));
    item.len = sizeof(rs485_cmd);
    cmd_tx_queue.push(item);

    led_flash_timestamps[3] = millis_now(); // TX Flash
    break;
  }
  }
  return true;
}

// ===== NETWORK INIT (Wiznet ioLibrary) =====
void network_init() {
  // Initialize W5500 SPI interface and hardware reset
  w5500_spi_init();

  // Configure W5500 chip memory (2KB per socket, 8 sockets)
  uint8_t tx_memsize[8] = {2, 2, 2, 2, 2, 2, 2, 2};
  uint8_t rx_memsize[8] = {2, 2, 2, 2, 2, 2, 2, 2};
  if (wizchip_init(tx_memsize, rx_memsize) < 0) {
    ethernet_online = false;
    return;
  }

  // Configure network parameters
  wiz_NetInfo netinfo;
  memcpy(netinfo.mac, mac, 6);
  memcpy(netinfo.ip, myIP, 4);
  memcpy(netinfo.sn, subnet, 4);
  memcpy(netinfo.gw, gateway, 4);
  uint8_t dns[4] = {0, 0, 0, 0};
  memcpy(netinfo.dns, dns, 4);
  netinfo.dhcp = NETINFO_STATIC;
  wizchip_setnetinfo(&netinfo);

  // Verify link is up
  if (wizphy_getphylink() != PHY_LINK_ON) {
    // W5500 is physically present but no cable — still mark as online
    // since the chip is responsive. Link may come up later.
  }

  ethernet_online = true;

  // Start DHCP server for direct connections (socket 2)
  dhcpServer.begin(SOCK_DHCPSRV, myIP, subnet);
  dhcp_server_active = true;

  // Open TCP server socket
  socket(SOCK_TCP, Sn_MR_TCP, TCP_PORT, 0);
  listen(SOCK_TCP);

  // Open UDP discovery socket
  socket(SOCK_UDP, Sn_MR_UDP, UDP_DISCOVERY_PORT, 0);
}

// ===== TCP TX (batch flush to W5500) =====
void process_tcp_tx() {
  if (!ethernet_online || !tcp_client_connected) {
    tcp_queue.clear();
    shared_ethernet_connected = false;
    return;
  }
  shared_ethernet_connected = true;

  const size_t BATCH_SIZE = 1460;
  static uint8_t batch[BATCH_SIZE];
  size_t batch_len = 0;

  // VERY IMPORTANT: Check W5500 free buffer size FIRST to prevent send() from
  // blocking If send() blocks, core0 is frozen, RS485 RX overflows, and the
  // whole system chokes.
  uint16_t free_size = getSn_TX_FSR(SOCK_TCP);
  size_t max_to_send = (free_size < BATCH_SIZE) ? free_size : BATCH_SIZE;

  while (!tcp_queue.empty()) {
    if (batch_len + 48 > max_to_send) // 48 is roughly max item size
      break;

    TcpBufferItem item;
    tcp_queue.pop(item);
    memcpy(batch + batch_len, item.data, item.len);
    batch_len += item.len;
  }

  if (batch_len > 0) {
    send(SOCK_TCP, batch, batch_len);
    led_flash_timestamps[1] = millis_now(); // TX flash
  }
}

// ===== CORE 1 ENTRY POINT =====
void core1_main() {
  // Initialize motor
  stepper_init();
  stepper.acceleration = shared_motor_accel;

  // Initialize GPIO
  gpio_init(SERVO_PIN);
  gpio_set_dir(SERVO_PIN, GPIO_OUT);
  gpio_put(SERVO_PIN, 0);

  gpio_init(PULSE_CLEAR_PIN);
  gpio_set_dir(PULSE_CLEAR_PIN, GPIO_OUT);
  gpio_put(PULSE_CLEAR_PIN, 0);

  gpio_init(ALARM_RESET_PIN);
  gpio_set_dir(ALARM_RESET_PIN, GPIO_OUT);
  gpio_put(ALARM_RESET_PIN, 0);

  // Initialize WS2812 LEDs
  ws2812_init();

  // Core 1 main loop
  while (true) {
    uint32_t now = millis_now();

    // === LED Update (30 Hz) ===
    if (now - led_timer >= 33) {
      led_timer = now;
      led_anim_phase++;

      // LED 0: Ethernet status
      if (ethernet_online) {
        if (dhcp_server_active)
          ws2812_set_pixel(0, 0, 100, 100);
        else
          ws2812_set_pixel(0, 0, 100, 0);
      } else {
        ws2812_set_pixel(0, 100, 0, 0);
      }

      // LED 1: TCP TX flash
      ws2812_set_pixel(1, (now - led_flash_timestamps[1] < 50) ? 0 : 0,
                       (now - led_flash_timestamps[1] < 50) ? 0 : 0,
                       (now - led_flash_timestamps[1] < 50) ? 100 : 0);

      // LED 2: RS485 RX flash
      ws2812_set_pixel(2, (now - led_flash_timestamps[2] < 50) ? 100 : 0,
                       (now - led_flash_timestamps[2] < 50) ? 50 : 0, 0);

      // LED 3: RS485 TX flash
      ws2812_set_pixel(3, (now - led_flash_timestamps[3] < 50) ? 50 : 0, 0,
                       (now - led_flash_timestamps[3] < 50) ? 100 : 0);

      // LED 4: Error flash
      ws2812_set_pixel(4, (now - led_flash_timestamps[4] < 200) ? 100 : 0, 0,
                       0);

      // LED 5: Client connected
      if (shared_ethernet_connected)
        ws2812_set_pixel(5, 0, 50, 50);
      else
        ws2812_set_pixel(5, 20, 20, 0);

      // LED 6: Encoder activity (read shared value — no PIO access from Core 1)
      int32_t enc = shared_encoder_value;
      static int32_t last_enc = 0;
      if (enc != last_enc) {
        led6_state = !led6_state;
        last_enc = enc;
      }
      ws2812_set_pixel(6, led6_state ? 50 : 0, led6_state ? 50 : 0,
                       led6_state ? 50 : 0);

      // LED 7: Breathing animation
      uint8_t b =
          (led_anim_phase < 128) ? led_anim_phase : (255 - led_anim_phase);
      ws2812_set_pixel(7, b / 5, b / 5, b / 5);

      ws2812_show();
    }

    // === Stepper Motor Update ===
    stepper.target_speed = shared_motor_speed;
    stepper.acceleration = shared_motor_accel;
    stepper_update();

    // === Servo ===
    gpio_put(SERVO_PIN, shared_servo_state ? 1 : 0);

    // === Pulse Clear (100ms pulse) ===
    static bool pulse_clear_active = false;
    static uint32_t pulse_clear_start_time = 0;
    static bool pulse_alarm_active = false;
    static uint32_t pulse_alarm_start_time = 0;

    if (shared_pulse_clear_req) {
      gpio_put(PULSE_CLEAR_PIN, 1);
      pulse_clear_start_time = now;
      pulse_clear_active = true;
      shared_pulse_clear_req = false;
    }
    if (shared_alarm_reset_req) {
      gpio_put(ALARM_RESET_PIN, 1);
      pulse_alarm_start_time = now;
      pulse_alarm_active = true;
      shared_alarm_reset_req = false;
    }

    if (pulse_clear_active && (now - pulse_clear_start_time >= 100)) {
      gpio_put(PULSE_CLEAR_PIN, 0);
      pulse_clear_active = false;
    }
    if (pulse_alarm_active && (now - pulse_alarm_start_time >= 100)) {
      gpio_put(ALARM_RESET_PIN, 0);
      pulse_alarm_active = false;
    }

    // Yield to avoid busy-looping — SDK-recommended idle hint
    tight_loop_contents();
  }
}

// ===== MAIN (Core 0) =====
int main() {
  stdio_init_all();

  // Initialize RS485 DMA
  rs485.begin(UART_HW, RS485_BAUD, RS485_TX_PIN, RS485_RX_PIN, RS485_CTRL_PIN,
              255, rs485_rx_buf, RX_RING_SIZE);

  // Initialize PIO encoder
  init_pio_encoder();

  // Initialize Ethernet
  network_init();

  // (Encoder timer removed — push-on-change polling is in Core 0 main loop)

  // Enable watchdog
  watchdog_enable(5000, true);

  // Launch Core 1
  multicore_launch_core1(core1_main);

  // ===== CORE 0 MAIN LOOP =====
  while (true) {
    watchdog_update();

    // === Ethernet Management ===
    if (ethernet_online) {
      // DHCP server
      if (dhcp_server_active) {
        dhcpServer.poll();
      }

      // === UDP Discovery ===
      int32_t udp_rx_size = getSn_RX_RSR(SOCK_UDP);
      if (udp_rx_size > 0) {
        char pktBuf[32];
        uint8_t remoteIP[4];
        uint16_t remotePort;
        int32_t rlen = recvfrom(SOCK_UDP, (uint8_t *)pktBuf, sizeof(pktBuf),
                                remoteIP, &remotePort);
        if (rlen > 0 && strncmp(pktBuf, "DISCOVER_MGF", 12) == 0) {
          char res[64];
          snprintf(res, sizeof(res), "MGF_STATOR:%d.%d.%d.%d:%d", myIP[0],
                   myIP[1], myIP[2], myIP[3], TCP_PORT);
          sendto(SOCK_UDP, (uint8_t *)res, strlen(res), remoteIP, remotePort);
        }
      }

      // === TCP Server State Machine ===
      uint8_t sock_status = getSn_SR(SOCK_TCP);

      switch (sock_status) {
      case SOCK_ESTABLISHED:
        if (!tcp_client_connected) {
          tcp_client_connected = true;
          tcp_rx_head = tcp_rx_tail = 0;
          tcp_queue.clear();
        }

        // Read incoming TCP data
        {
          int32_t avail = getSn_RX_RSR(SOCK_TCP);
          if (avail > 0) {
            int to_read = TCP_RX_BUF_SIZE - tcp_rx_head;
            if (avail < to_read)
              to_read = avail;

            int32_t readCount =
                recv(SOCK_TCP, &tcp_rx_buf[tcp_rx_head], to_read);
            if (readCount > 0) {
              tcp_rx_head += readCount;

              while (tcp_rx_head - tcp_rx_tail >= sizeof(TcpHeader)) {
                TcpHeader *hdr = (TcpHeader *)&tcp_rx_buf[tcp_rx_tail];
                if (hdr->magic != MGF_TCP_MAGIC) {
                  tcp_rx_tail++;
                  continue;
                }

                size_t total_len = sizeof(TcpHeader) + hdr->length + 4;
                if (total_len > 256) {
                  tcp_rx_tail++;
                  continue;
                }

                if ((uint16_t)(tcp_rx_head - tcp_rx_tail) >= total_len) {
                  if (handleHostCommand(&tcp_rx_buf[tcp_rx_tail], total_len)) {
                    tcp_rx_tail += total_len;
                  } else {
                    tcp_rx_tail++; // CRC mismatch, slide window
                  }
                } else {
                  break;
                }
              }

              if (tcp_rx_tail > 0 && tcp_rx_head == tcp_rx_tail) {
                tcp_rx_head = tcp_rx_tail = 0;
              } else if (tcp_rx_head >= TCP_RX_BUF_SIZE) {
                memmove(tcp_rx_buf, &tcp_rx_buf[tcp_rx_tail],
                        tcp_rx_head - tcp_rx_tail);
                tcp_rx_head -= tcp_rx_tail;
                tcp_rx_tail = 0;
              }
            }
          }
        }

        process_tcp_tx();
        break;

      case SOCK_CLOSE_WAIT:
        disconnect(SOCK_TCP);
        tcp_client_connected = false;
        shared_ethernet_connected = false;
        break;

      case SOCK_CLOSED:
        tcp_client_connected = false;
        shared_ethernet_connected = false;
        socket(SOCK_TCP, Sn_MR_TCP, TCP_PORT, 0);
        listen(SOCK_TCP);
        break;

      case SOCK_LISTEN:
        // Waiting for connection
        break;

      default:
        break;
      }
    }

    // === RS485 TX ===
    if (!rs485.is_tx_busy()) {
      TxItem tx;
      if (cmd_tx_queue.pop(tx))
        rs485.send(tx.data, tx.len);
      else if (enc_tx_queue.pop(tx))
        rs485.send(tx.data, tx.len);
    }

    // === RS485 RX ===
    parser.parse(rs485.rx_write_pos(), on_rs485_packet);

    // === Encoder: Rate-limited push (max ~1kHz to avoid RS485 flood) ===
    {
      static int32_t last_sent_enc = -1;
      static uint32_t last_enc_send_ms = 0;
      int32_t enc = getRealEncoder();
      shared_encoder_value = enc; // Update shared value for Core 1 LED

      uint32_t enc_now_ms = millis_now();
      if (enc != last_sent_enc && (enc_now_ms - last_enc_send_ms >= 1)) {
        last_sent_enc = enc;
        last_enc_send_ms = enc_now_ms;

        EncUpdatePacket pkt;
        pkt.sync = RS485_SYNC_WORD;
        pkt.type = RS485_TYPE_ENC_UPDATE;
        pkt.encoder = enc;
        pkt.seq = enc_seq++;

        TxItem item;
        memcpy(item.data, &pkt, sizeof(pkt));
        item.len = sizeof(pkt);
        enc_tx_queue.push(item);
      }

      // Measure actual shaft speed from encoder (every 200ms)
      if (enc_now_ms - enc_speed_last_time_ms >= 200) {
        static bool speed_init = false;
        int32_t raw_enc = getRawEncoderCounts();
        if (!speed_init) {
          enc_speed_last_pos = raw_enc;
          speed_init = true;
        }
        int32_t delta = raw_enc - enc_speed_last_pos;

        float dt_s = (enc_now_ms - enc_speed_last_time_ms) / 1000.0f;
        if (dt_s > 0.0f && current_enc_ppr > 0) {
          encoder_measured_speed_hz =
              (float)delta / ((float)current_enc_ppr * dt_s);
        }
        enc_speed_last_pos = raw_enc;
        enc_speed_last_time_ms = enc_now_ms;
      }
    }

    // === Rotor Timeout ===
    if (millis_now() - last_rotor_packet_time > 1000) {
      rotor_online = false;
    }

    // === Periodic Status (1Hz) ===
    static uint32_t last_status_ms = 0;
    if (millis_now() - last_status_ms >= 1000) {
      last_status_ms = millis_now();
      TcpStatus status;
      status.uptime_ms = millis_now();
      status.motor_speed_hz = encoder_measured_speed_hz;
      status.encoder_position = shared_encoder_value;
      status.encoder_ppr = current_enc_ppr;
      status.rotor_online = rotor_online;
      status.rs485_error_count = rs485_crc_error_count;
      status.rotor_error_count = 0;
      status.tcp_queue_depth = tcp_queue.count();
      push_tcp_packet(TCP_TYPE_STATUS, &status, sizeof(TcpStatus));
    }
  }
}