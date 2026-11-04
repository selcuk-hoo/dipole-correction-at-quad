#ifndef DHCP_SERVER_H
#define DHCP_SERVER_H

/**
 * @file dhcp_server.h
 * @brief Minimal DHCP Server for direct-connect Ethernet (Wiznet ioLibrary)
 * @details Assigns IPs from a small pool to hosts connecting directly to the
 *          MGF stator via Ethernet. Uses raw Wiznet socket API, no Arduino deps.
 */

#include <stdint.h>
#include <string.h>
#include "pico/stdlib.h"

#ifdef __cplusplus
extern "C" {
#endif
#include "socket.h"
#ifdef __cplusplus
}
#endif

// DHCP Constants
#define DHCP_SERVER_PORT   67
#define DHCP_CLIENT_PORT   68

#define DHCP_DISCOVER 1
#define DHCP_OFFER    2
#define DHCP_REQUEST  3
#define DHCP_DECLINE  4
#define DHCP_ACK      5
#define DHCP_NAK      6
#define DHCP_RELEASE  7

// DHCP Options
#define DHCP_OPT_SUBNET        1
#define DHCP_OPT_ROUTER        3
#define DHCP_OPT_DNS           6
#define DHCP_OPT_REQUESTED_IP  50
#define DHCP_OPT_LEASE_TIME    51
#define DHCP_OPT_MSG_TYPE      53
#define DHCP_OPT_SERVER_ID     54
#define DHCP_OPT_END           255

#define DHCP_LEASE_TIME 86400  // 24 hours

class DhcpServer {
public:
    DhcpServer() : _running(false), _sock(-1), _nextIP(100) {
        memset(_serverIP, 0, 4);
        memset(_subnet, 0, 4);
    }

    /**
     * @brief Start DHCP server on a Wiznet socket
     * @param sock   Wiznet socket number (0-7) to use for UDP
     * @param serverIP  Our IP address (4 bytes)
     * @param subnetMask  Subnet mask (4 bytes)
     */
    void begin(uint8_t sock, const uint8_t *serverIP, const uint8_t *subnetMask) {
        _sock = sock;
        memcpy(_serverIP, serverIP, 4);
        memcpy(_subnet, subnetMask, 4);

        // Open a UDP socket on port 67
        socket(_sock, Sn_MR_UDP, DHCP_SERVER_PORT, 0);
        _running = true;

        // Pool: x.x.x.100 - x.x.x.200
        memcpy(_poolBase, serverIP, 3);
    }

    void stop() {
        if (_running && _sock >= 0) {
            close(_sock);
        }
        _running = false;
    }

    /**
     * @brief Poll for incoming DHCP requests and respond
     * @details Call this periodically from the main loop
     */
    void poll() {
        if (!_running || _sock < 0) return;

        uint8_t buffer[576];
        uint8_t srcIP[4];
        uint16_t srcPort;

        int32_t len = getSn_RX_RSR(_sock);
        if (len <= 0) return;

        len = recvfrom(_sock, buffer, sizeof(buffer), srcIP, &srcPort);
        if (len < 240) return;  // Min DHCP packet size

        // Check if it's a DHCP request (op=1 is request)
        if (buffer[0] != 1) return;

        // Get transaction ID
        uint32_t xid = ((uint32_t)buffer[4] << 24) | ((uint32_t)buffer[5] << 16) |
                        ((uint32_t)buffer[6] << 8)  | buffer[7];

        // Get client MAC
        uint8_t clientMAC[6];
        memcpy(clientMAC, &buffer[28], 6);

        // Find DHCP message type
        uint8_t msgType = 0;
        uint8_t requestedIP[4] = {0, 0, 0, 0};

        int optIdx = 240;  // Options start after fixed header
        while (optIdx < len && buffer[optIdx] != DHCP_OPT_END) {
            uint8_t opt = buffer[optIdx++];
            if (opt == 0) continue;  // Padding

            uint8_t optLen = buffer[optIdx++];

            if (opt == DHCP_OPT_MSG_TYPE && optLen >= 1) {
                msgType = buffer[optIdx];
            } else if (opt == DHCP_OPT_REQUESTED_IP && optLen >= 4) {
                memcpy(requestedIP, &buffer[optIdx], 4);
            }

            optIdx += optLen;
        }

        if (msgType == DHCP_DISCOVER) {
            uint8_t offerIP[4];
            getNextIP(clientMAC, offerIP);
            sendResponse(buffer, xid, clientMAC, offerIP, DHCP_OFFER);
        }
        else if (msgType == DHCP_REQUEST) {
            uint8_t ackIP[4];
            if (requestedIP[0] == 0) {
                getNextIP(clientMAC, ackIP);
            } else {
                memcpy(ackIP, requestedIP, 4);
            }
            sendResponse(buffer, xid, clientMAC, ackIP, DHCP_ACK);
        }
    }

private:
    int8_t _sock;
    uint8_t _serverIP[4];
    uint8_t _subnet[4];
    uint8_t _poolBase[3];
    bool _running;
    uint8_t _nextIP;

    // Simple lease table
    struct Lease {
        uint8_t mac[6];
        uint8_t ip;
        uint32_t expires_ms;
    };
    static const int MAX_LEASES = 10;
    Lease _leases[MAX_LEASES] = {};

    void getNextIP(uint8_t *mac, uint8_t *outIP) {
        uint32_t now = to_ms_since_boot(get_absolute_time());

        // Check existing lease
        for (int i = 0; i < MAX_LEASES; i++) {
            if (memcmp(_leases[i].mac, mac, 6) == 0 && _leases[i].ip != 0) {
                memcpy(outIP, _poolBase, 3);
                outIP[3] = _leases[i].ip;
                return;
            }
        }

        // Find free slot and assign new IP
        for (int i = 0; i < MAX_LEASES; i++) {
            if (_leases[i].ip == 0 || now > _leases[i].expires_ms) {
                memcpy(_leases[i].mac, mac, 6);
                _leases[i].ip = _nextIP++;
                if (_nextIP > 200) _nextIP = 100;
                _leases[i].expires_ms = now + (DHCP_LEASE_TIME * 1000);
                memcpy(outIP, _poolBase, 3);
                outIP[3] = _leases[i].ip;
                return;
            }
        }

        // Fallback
        memcpy(outIP, _poolBase, 3);
        outIP[3] = _nextIP++;
    }

    void sendResponse(uint8_t *request, uint32_t xid, uint8_t *clientMAC,
                      uint8_t *offerIP, uint8_t msgType) {
        uint8_t response[300];
        memset(response, 0, sizeof(response));

        // BOOTP header
        response[0] = 2;   // op: reply
        response[1] = 1;   // htype: ethernet
        response[2] = 6;   // hlen: MAC length
        response[3] = 0;   // hops

        // Transaction ID
        response[4] = (xid >> 24) & 0xFF;
        response[5] = (xid >> 16) & 0xFF;
        response[6] = (xid >> 8) & 0xFF;
        response[7] = xid & 0xFF;

        // secs, flags
        response[8] = 0; response[9] = 0;
        response[10] = 0x80; response[11] = 0;  // Broadcast flag

        // yiaddr (your IP)
        memcpy(&response[16], offerIP, 4);

        // siaddr (server IP)
        memcpy(&response[20], _serverIP, 4);

        // chaddr (client MAC)
        memcpy(&response[28], clientMAC, 6);

        // Magic cookie
        response[236] = 99;
        response[237] = 130;
        response[238] = 83;
        response[239] = 99;

        int optIdx = 240;

        // Option 53: DHCP Message Type
        response[optIdx++] = DHCP_OPT_MSG_TYPE;
        response[optIdx++] = 1;
        response[optIdx++] = msgType;

        // Option 54: Server Identifier
        response[optIdx++] = DHCP_OPT_SERVER_ID;
        response[optIdx++] = 4;
        memcpy(&response[optIdx], _serverIP, 4);
        optIdx += 4;

        // Option 51: Lease Time
        response[optIdx++] = DHCP_OPT_LEASE_TIME;
        response[optIdx++] = 4;
        response[optIdx++] = (DHCP_LEASE_TIME >> 24) & 0xFF;
        response[optIdx++] = (DHCP_LEASE_TIME >> 16) & 0xFF;
        response[optIdx++] = (DHCP_LEASE_TIME >> 8) & 0xFF;
        response[optIdx++] = DHCP_LEASE_TIME & 0xFF;

        // Option 1: Subnet Mask
        response[optIdx++] = DHCP_OPT_SUBNET;
        response[optIdx++] = 4;
        memcpy(&response[optIdx], _subnet, 4);
        optIdx += 4;

        // Option 3: Router
        response[optIdx++] = DHCP_OPT_ROUTER;
        response[optIdx++] = 4;
        memcpy(&response[optIdx], _serverIP, 4);
        optIdx += 4;

        // End
        response[optIdx++] = DHCP_OPT_END;

        // Send to broadcast 255.255.255.255:68
        uint8_t bcast[4] = {255, 255, 255, 255};
        sendto(_sock, response, optIdx, bcast, DHCP_CLIENT_PORT);
    }
};

#endif // DHCP_SERVER_H