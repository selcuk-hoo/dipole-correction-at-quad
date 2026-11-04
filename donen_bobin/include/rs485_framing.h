#ifndef RS485_FRAMING_H
#define RS485_FRAMING_H

#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include "mgf_protocol.h"

namespace mgf {

// Helper to get total packet size including sync and type
inline constexpr size_t get_rs485_packet_size(uint8_t type) {
    switch (type) {
        case RS485_TYPE_ENC_UPDATE: return sizeof(EncUpdatePacket);
        case RS485_TYPE_CMD:        return sizeof(CmdPacketRS485);
        case RS485_TYPE_FUSED:      return sizeof(FusedSamplePacket);
        case RS485_TYPE_ACK:        return sizeof(AckPacketRS485);
        case RS485_TYPE_STATUS:     return sizeof(StatusPacketRS485);
        case RS485_TYPE_CONFIG:     return sizeof(AdcConfigPacketRS485);
        default: return 0;
    }
}

// Parser for continuous stream
class RS485Parser {
    uint8_t* _ring_buf;
    size_t   _ring_size;
    size_t   _read_pos;
    
    // Internal parser state
    enum State { WAIT_SYNC_1, WAIT_SYNC_2, READ_TYPE, READ_PAYLOAD };
    State _state;
    uint8_t _type;
    size_t _expected_size;
    uint8_t _pkt_buf[48]; // local buffer to assemble packet (48 for future-proofing)
    size_t _pkt_pos;

public:
    RS485Parser(uint8_t* buf, size_t size) 
        : _ring_buf(buf), _ring_size(size), _read_pos(0), _state(WAIT_SYNC_1), _type(0), _expected_size(0), _pkt_pos(0) {}

    using PacketCallback = void(*)(uint8_t type, const uint8_t* pkt, size_t len);

    void parse(size_t write_pos, PacketCallback cb) {
        while (_read_pos != write_pos) {
            uint8_t b = _ring_buf[_read_pos];
            _read_pos = (_read_pos + 1) % _ring_size;
            
            switch (_state) {
                case WAIT_SYNC_1:
                    if (b == (RS485_SYNC_WORD & 0xFF)) { // 0x55
                        _pkt_buf[0] = b;
                        _state = WAIT_SYNC_2;
                    }
                    break;
                case WAIT_SYNC_2:
                    if (b == (RS485_SYNC_WORD >> 8)) { // 0xAA
                        _pkt_buf[1] = b;
                        _state = READ_TYPE;
                    } else if (b == (RS485_SYNC_WORD & 0xFF)) { // Still 0x55
                        // keep state
                    } else {
                        _state = WAIT_SYNC_1;
                    }
                    break;
                case READ_TYPE:
                    _pkt_buf[2] = b;
                    _type = b;
                    _expected_size = get_rs485_packet_size(_type);
                    if (_expected_size > 0 && _expected_size <= sizeof(_pkt_buf)) {
                        _pkt_pos = 3;
                        _state = READ_PAYLOAD;
                    } else {
                        _state = WAIT_SYNC_1;
                    }
                    break;
                case READ_PAYLOAD:
                    _pkt_buf[_pkt_pos++] = b;
                    if (_pkt_pos == _expected_size) {
                        cb(_type, _pkt_buf, _expected_size);
                        _state = WAIT_SYNC_1;
                    }
                    break;
            }
        }
    }
};

} // namespace mgf

#endif // RS485_FRAMING_H
