"""
Protocol V2 Definitions for MGF Radar.
"""

import struct

# Magic and Constants
MGF_TCP_MAGIC = 0xA55A
MGF_PROTOCOL_VERSION = 2

# TCP Packet Types
TCP_TYPE_FUSED_SAMPLE   = 0x10
TCP_TYPE_ENC_UPDATE     = 0x11
TCP_TYPE_STATUS         = 0x12
TCP_TYPE_HELLO          = 0x20
TCP_TYPE_HELLO_ACK      = 0x21
TCP_TYPE_HEARTBEAT      = 0x22
TCP_TYPE_CMD            = 0x02
TCP_TYPE_ACK            = 0x03
TCP_TYPE_ADC_CONFIG     = 0x30

# Commands (Host -> Stator)
CMD_SET_GAIN           = 0x01
CMD_SET_RATE           = 0x02
CMD_SET_FILTER         = 0x03
CMD_SET_CHOP           = 0x04
CMD_SET_PGA_BYPASS     = 0x05
CMD_SET_CONV_MODE      = 0x06
CMD_SET_CONV_DELAY     = 0x07
CMD_SET_REF_MUX        = 0x08
CMD_SET_REF_REVERSE    = 0x09
CMD_SET_VBIAS          = 0x0A
CMD_SET_INTREF         = 0x0B
CMD_SET_IDAC           = 0x0C
CMD_START_ADC          = 0x10
CMD_STOP_ADC           = 0x11
CMD_CALIBRATE_OFFSET   = 0x12
CMD_CALIBRATE_GAIN     = 0x13
CMD_SET_DATA_MODE      = 0x14
CMD_RESET_CALIBRATION  = 0x15
CMD_SET_MOTOR_SPEED    = 0x20
CMD_SET_SERVO          = 0x21
CMD_CLEAR_PULSE        = 0x22
CMD_RESET_ALARM        = 0x23
CMD_SET_ENCODER_PPR    = 0x24
CMD_SPEED_RAMP         = 0x25
CMD_SET_SCAN_CHANNELS  = 0x26
CMD_PAUSE_STREAM       = 0x30
CMD_RESUME_STREAM      = 0x31

# Structs (Packed, Little Endian)
# Header: [MAGIC:u16][LEN:u16][TYPE:u8][SEQ:u16]
STRUCT_TCP_HEADER = struct.Struct('<HHBH')

# TCP_TYPE_FUSED_SAMPLE (15 bytes)
# [adc_value:i32][encoder:i32][stepper_steps:i32][adc_status:u8][data_type:u8][flags:u8]
STRUCT_FUSED_SAMPLE = struct.Struct('<iiiBBB')

# TCP_TYPE_ENC_UPDATE (8 bytes)
# [timestamp:u32][encoder:i32]
STRUCT_ENC_UPDATE = struct.Struct('<Ii')

# TCP_TYPE_STATUS (21 bytes)
# [uptime_ms:u32][motor_speed:f32][encoder:i32][ppr:u16][rotor_online:u8][rs485_err:u16][rotor_err:u16][tcp_queue:u16]
STRUCT_STATUS = struct.Struct('<IfiHBHHH')

# TCP_TYPE_HELLO_ACK (30 bytes)
# [ver:u8][caps:u32][ppr:u16][motor_speed:f32][adc_config:19B]
STRUCT_HELLO_ACK = struct.Struct('<BIHf19B')

# TCP_TYPE_ADC_CONFIG (19 bytes)
STRUCT_ADC_CONFIG = struct.Struct('<19B')

# TCP_TYPE_ACK (2 bytes)
# [cmd:u8][status:u8]
STRUCT_ACK = struct.Struct('<BB')

# TCP_TYPE_CMD (5 bytes)
# [cmd:u8][param_raw:u32]
STRUCT_CMD = struct.Struct('<BI')

# TCP_TYPE_HELLO (21 bytes)
# [ver:u8][caps:u32][client_id:16s]
STRUCT_HELLO = struct.Struct('<BI16s')

def calc_crc32(data: bytes) -> int:
    import zlib
    return zlib.crc32(data) & 0xFFFFFFFF
