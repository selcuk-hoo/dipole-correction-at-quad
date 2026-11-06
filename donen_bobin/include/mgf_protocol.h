#ifndef MGF_PROTOCOL_H
#define MGF_PROTOCOL_H

#include <stdint.h>
#include <stddef.h>

#define MGF_PROTOCOL_VERSION  2
#define MGF_TCP_MAGIC         0xA55A

#pragma pack(push, 1)

// ============================================================================
// Default ADC Configuration (Compile-Time)
// ADS1263 Datasheet: SBAS661C
// ============================================================================

// MODE2 — Table 9-40, p.93
#define MGF_DEFAULT_GAIN            5   // ADS1263_GAIN_32 (±78.125mV)
#define MGF_DEFAULT_RATE            12  // ADS1263_RATE_7200 (7200 SPS)
#define MGF_DEFAULT_PGA_BYPASS      0   // PGA enabled

// MODE1 — Table 9-39, p.92
#define MGF_DEFAULT_FILTER          3   // ADS1263_FILTER_SINC4 (best noise rejection)

// MODE0 — Table 9-38, p.91
#define MGF_DEFAULT_CHOP            0   // ADS1263_CHOP_OFF
#define MGF_DEFAULT_CONV_MODE       0   // ADS1263_CONV_CONTINUOUS
#define MGF_DEFAULT_CONV_DELAY      0   // ADS1263_DELAY_NONE
#define MGF_DEFAULT_REF_REVERSE     0   // Normal polarity

// INPMUX — Table 9-41, p.93
#define MGF_DEFAULT_INPUT_POS       0   // AIN0
#define MGF_DEFAULT_INPUT_NEG       1   // AIN1

// REFMUX — Table 9-46, p.98
#define MGF_DEFAULT_REF_POS         0   // Internal 2.5V
#define MGF_DEFAULT_REF_NEG         0   // Internal 2.5V

// POWER — Table 9-36, p.89
#define MGF_DEFAULT_VBIAS           0   // VBIAS disabled
#define MGF_DEFAULT_INTREF          1   // Internal ref always on

// IDACMAG — Table 9-45, p.97
#define MGF_DEFAULT_IDAC1_MAG       0   // Off
#define MGF_DEFAULT_IDAC2_MAG       0   // Off
// IDACMUX — Table 9-44, p.96
#define MGF_DEFAULT_IDAC1_MUX       0x0B // AINCOM (disconnected)
#define MGF_DEFAULT_IDAC2_MUX       0x0B // AINCOM (disconnected)

// Application-Level
#define MGF_DEFAULT_DATA_MODE       1   // 1=VOLTAGE, 0=RAW

// ============================================================================
// RS485 Packet Types (Rotor <-> Stator)
// ============================================================================
#define RS485_SYNC_WORD       0xAA55

enum MgfRS485Type {
    RS485_TYPE_ENC_UPDATE = 0x01,  // Stator -> Rotor: Encoder update
    RS485_TYPE_CMD        = 0x02,  // Stator -> Rotor: Command
    
    RS485_TYPE_FUSED      = 0x10,  // Rotor -> Stator: Fused ADC + Encoder sample
    RS485_TYPE_ACK        = 0x11,  // Rotor -> Stator: Command ACK
    RS485_TYPE_STATUS     = 0x12,  // Rotor -> Stator: Periodic status telemetry
    RS485_TYPE_CONFIG     = 0x13   // Rotor -> Stator: Full ADC config report
};

// Stator -> Rotor: Encoder Update (10kHz stream)
struct EncUpdatePacket {
    uint16_t sync;      // 0xAA55
    uint8_t  type;      // RS485_TYPE_ENC_UPDATE
    int32_t  encoder;
    uint16_t seq;
};

// Stator -> Rotor: Command
struct CmdPacketRS485 {
    uint16_t sync;      // 0xAA55
    uint8_t  type;      // RS485_TYPE_CMD
    uint8_t  cmd_seq;
    uint8_t  cmd;
    uint32_t param_raw;
};

// Rotor -> Stator: Fused ADC + Encoder
struct FusedSamplePacket {
    uint16_t sync;      // 0xAA55
    uint8_t  type;      // RS485_TYPE_FUSED
    int32_t  adc_value;
    int32_t  encoder;
    uint8_t  adc_status;
    uint8_t  data_type; // 0=RAW, 1=Voltage
    uint8_t  flags;     // bit 0 = valid, bit 1 = stale
    uint8_t  adc_crc;   // ADS1263 checksum byte (end-to-end validation)
};

// Rotor -> Stator: Command ACK
struct AckPacketRS485 {
    uint16_t sync;      // 0xAA55
    uint8_t  type;      // RS485_TYPE_ACK
    uint8_t  cmd_seq;
    uint8_t  status;
};

// Rotor -> Stator: Status Telemetry
struct StatusPacketRS485 {
    uint16_t sync;      // 0xAA55
    uint8_t  type;      // RS485_TYPE_STATUS
    uint16_t err_cnt;
    uint32_t sample_cnt;
    uint32_t uptime;
    uint8_t  adc_state;
};


// ============================================================================
// TCP Packet Types (Stator <-> Host)
// ============================================================================

enum MgfTcpType {
    TCP_TYPE_FUSED_SAMPLE   = 0x10,
    TCP_TYPE_ENC_UPDATE     = 0x11,
    TCP_TYPE_STATUS         = 0x12,
    TCP_TYPE_HELLO          = 0x20,
    TCP_TYPE_HELLO_ACK      = 0x21,
    TCP_TYPE_HEARTBEAT      = 0x22,
    TCP_TYPE_CMD            = 0x02,
    TCP_TYPE_ACK            = 0x03,
    TCP_TYPE_ADC_CONFIG     = 0x30   // Stator -> Host: Full ADC config report
};

// TCP TLV Wrapper
struct TcpHeader {
    uint16_t magic;     // 0xA55A
    uint16_t length;    // Payload length
    uint8_t  type;      // MgfTcpType
    uint16_t sequence;  // Rolling sequence counter
};

// Payload for TCP_TYPE_FUSED_SAMPLE
struct TcpFusedSample {
    int32_t  adc_value;
    int32_t  encoder;
    int32_t  stepper_steps;
    uint8_t  adc_status;
    uint8_t  data_type;
    uint8_t  flags;
};

// Payload for TCP_TYPE_ENC_UPDATE
struct TcpEncoderUpdate {
    uint32_t timestamp;
    int32_t  encoder;
};

// Payload for TCP_TYPE_STATUS
struct TcpStatus {
    uint32_t uptime_ms;
    float    motor_speed_hz;
    int32_t  encoder_position;
    uint16_t encoder_ppr;
    uint8_t  rotor_online;
    uint16_t rs485_error_count;
    uint16_t rotor_error_count;
    uint16_t tcp_queue_depth;
};

// Full ADC Config Report — TCP payload (Stator -> Host)
struct TcpAdcConfig {
    // MODE2 — Table 9-40
    uint8_t  gain;           // ads1263_gain_t       (0–5)
    uint8_t  rate;           // ads1263_rate_t        (0–15)
    uint8_t  pga_bypass;     // 0 or 1
    // MODE1 — Table 9-39
    uint8_t  filter;         // ads1263_filter_t      (0–4)
    // MODE0 — Table 9-38
    uint8_t  chop;           // ads1263_chop_mode_t   (0–3)
    uint8_t  conv_mode;      // ads1263_conv_mode_t   (0–1)
    uint8_t  conv_delay;     // ads1263_delay_t       (0–11)
    uint8_t  ref_reverse;    // 0 or 1
    // INPMUX — Table 9-41
    uint8_t  input_pos;      // ads1263_input_t       (0x0–0xF)
    uint8_t  input_neg;      // ads1263_input_t       (0x0–0xF)
    // REFMUX — Table 9-46
    uint8_t  ref_pos;        // ads1263_refp_t        (0–4)
    uint8_t  ref_neg;        // ads1263_refn_t        (0–4)
    // POWER — Table 9-36
    uint8_t  vbias;          // 0 or 1
    uint8_t  intref;         // 0 or 1
    // IDACMAG/MUX — Table 9-44/45
    uint8_t  idac1_mag;      // ads1263_idac_magnitude_t (0x0–0xA)
    uint8_t  idac2_mag;      // ads1263_idac_magnitude_t (0x0–0xA)
    uint8_t  idac1_mux;      // ads1263_input_t (0x0–0xF)
    uint8_t  idac2_mux;      // ads1263_input_t (0x0–0xF)
    // Application-level
    uint8_t  data_mode;      // 0=RAW, 1=VOLTAGE
};

// Full ADC Config Report — RS485 (Rotor -> Stator)
struct AdcConfigPacketRS485 {
    uint16_t sync;           // 0xAA55
    uint8_t  type;           // RS485_TYPE_CONFIG
    TcpAdcConfig config;     // Embedded config payload
};

// Payload for TCP_TYPE_HELLO
struct TcpHello {
    uint8_t  protocol_version;
    uint32_t capabilities;
    char     client_id[16];
};

// Payload for TCP_TYPE_HELLO_ACK
struct TcpHelloAck {
    uint8_t  protocol_version;
    uint32_t capabilities;
    uint16_t encoder_ppr;
    float    motor_speed_hz;
    TcpAdcConfig adc_config;  // Full embedded config
};

// Payload for TCP_TYPE_HEARTBEAT
struct TcpHeartbeat {
    uint32_t timestamp;
    uint16_t sequence;
};

// Payload for TCP_TYPE_CMD (Host -> Stator)
struct TcpCmd {
    uint8_t  cmd;
    uint32_t param_raw;
};

// Payload for TCP_TYPE_ACK (Stator -> Host)
struct TcpAck {
    uint8_t  cmd;
    uint8_t  status;
};


// ============================================================================
// Command Enums & Macros
// ============================================================================

enum MgfCommand {
    // ADC Config — Basic
    CMD_SET_GAIN           = 0x01,  // param: 0–5 (ads1263_gain_t)
    CMD_SET_RATE           = 0x02,  // param: 0–15 (ads1263_rate_t)
    CMD_SET_FILTER         = 0x03,  // param: 0–4 (ads1263_filter_t)
    CMD_SET_CHOP           = 0x04,  // param: 0–3 (ads1263_chop_mode_t)
    CMD_SET_PGA_BYPASS     = 0x05,  // param: 0 or 1
    
    // ADC Config — Extended (MODE0, REFMUX, POWER, IDAC)
    CMD_SET_CONV_MODE      = 0x06,  // param: 0=continuous, 1=pulse
    CMD_SET_CONV_DELAY     = 0x07,  // param: 0–11 (ads1263_delay_t)
    CMD_SET_REF_MUX        = 0x08,  // param: (ref_pos << 8) | ref_neg
    CMD_SET_REF_REVERSE    = 0x09,  // param: 0 or 1
    CMD_SET_VBIAS          = 0x0A,  // param: 0 or 1
    CMD_SET_INTREF         = 0x0B,  // param: 0 or 1
    CMD_SET_IDAC           = 0x0C,  // param: (mag2<<24)|(mag1<<16)|(mux2<<8)|mux1
    
    // ADC Actions
    CMD_START_ADC          = 0x10,
    CMD_STOP_ADC           = 0x11,
    CMD_CALIBRATE_OFFSET   = 0x12,  // Self-offset cal (SFOCAL1)
    CMD_CALIBRATE_GAIN     = 0x13,  // System gain cal (SYGCAL1)
    CMD_SET_DATA_MODE      = 0x14,  // 0=RAW, 1=VOLTAGE
    CMD_RESET_CALIBRATION  = 0x15,  // Reset calibration registers to defaults
    
    // Motor & Hardware
    CMD_SET_MOTOR_SPEED    = 0x20,  // param = float Hz
    CMD_SET_SERVO          = 0x21,  // param = 0 or 1
    CMD_CLEAR_PULSE        = 0x22,
    CMD_RESET_ALARM        = 0x23,
    CMD_SET_ENCODER_PPR    = 0x24,  // param = PPR
    CMD_SPEED_RAMP         = 0x25,
    CMD_SET_SCAN_CHANNELS  = 0x26,  // param: (pos << 8) | neg
    
    // Stream Control
    CMD_PAUSE_STREAM       = 0x30,
    CMD_RESUME_STREAM      = 0x31,
    
    // Query
    CMD_GET_ADC_CONFIG     = 0x40   // Request full ADC config report
};

enum MgfAckStatus {
    ACK_OK               = 0x00,
    ACK_ERROR            = 0x01,
    ACK_INVALID_CMD      = 0x02,
    ACK_INVALID_PARAM    = 0x03,
    ACK_TIMEOUT          = 0x04,
    ACK_ROTOR_OFFLINE    = 0x05
};

// Command param helper macros
inline float cmd_param_float(uint32_t p) {
    float f;
    memcpy(&f, &p, 4);
    return f;
}
#define CMD_PARAM_FLOAT(p)  cmd_param_float(p)
#define CMD_PARAM_U8(p)     ((uint8_t)(p))
#define CMD_PARAM_U16(p)    ((uint16_t)(p))

#pragma pack(pop)

// Optional compile-time checks for C++ environments
#ifdef __cplusplus
static_assert(sizeof(EncUpdatePacket) == 9, "EncUpdatePacket padding error");
static_assert(sizeof(CmdPacketRS485) == 9, "CmdPacketRS485 padding error");
static_assert(sizeof(FusedSamplePacket) == 15, "FusedSamplePacket padding error");
static_assert(sizeof(AckPacketRS485) == 5, "AckPacketRS485 padding error");
static_assert(sizeof(StatusPacketRS485) == 14, "StatusPacketRS485 padding error");
static_assert(sizeof(TcpAdcConfig) == 19, "TcpAdcConfig padding error");
static_assert(sizeof(AdcConfigPacketRS485) == 22, "AdcConfigPacketRS485 padding error");

static_assert(sizeof(TcpHeader) == 7, "TcpHeader padding error");
#endif

#endif // MGF_PROTOCOL_H
