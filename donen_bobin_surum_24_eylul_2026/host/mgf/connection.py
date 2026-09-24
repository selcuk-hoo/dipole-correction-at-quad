"""
TCP Client for MGF Radar V2.
Handles discovery (UDP broadcast + mDNS), connection, heartbeat monitoring,
auto-reconnect, and zero-copy TLV packet parsing.
"""

import socket
import threading
import queue
import time
import struct
import logging
from . import protocol

log = logging.getLogger(__name__)


class MgfConnection:
    """Non-blocking TCP client with discovery, heartbeat, and auto-reconnect."""

    # Discovery / reconnect tunables
    DISCOVERY_TIMEOUT_S = 2.0
    CONNECT_TIMEOUT_S = 3.0
    HEARTBEAT_INTERVAL_S = 2.0
    HEARTBEAT_TIMEOUT_S = 6.0
    RECONNECT_DELAY_S = 2.0
    UDP_DISCOVERY_PORT = 5001

    def __init__(self, host: str = "169.254.1.177", port: int = 5000):
        self.host = host
        self.port = port
        self.sock: socket.socket | None = None
        self.connected = False
        self.rx_queue: queue.Queue = queue.Queue(maxsize=50000)
        self._seq = 0

        # Threads
        self._rx_thread: threading.Thread | None = None
        self._hb_thread: threading.Thread | None = None
        self._running = False

        # Auto-reconnect
        self.auto_reconnect = True
        self._reconnect_thread: threading.Thread | None = None
        self._reconnecting = False

        # Heartbeat / quality tracking
        self._last_rx_time = 0.0
        self._last_hb_sent = 0.0
        self._latency_ms = 0.0
        self._packets_received = 0
        self._crc_errors = 0

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    @staticmethod
    def discover_udp(timeout: float = 2.0, port: int = 5001) -> str | None:
        """Broadcast UDP discover and return first responder IP:port string."""
        # 1. Try generic broadcast first
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            s.settimeout(timeout)
            
            try:
                s.sendto(b"DISCOVER_MGF", ("<broadcast>", port))
            except Exception:
                try:
                    s.sendto(b"DISCOVER_MGF", ("255.255.255.255", port))
                except Exception:
                    pass

            try:
                data, addr = s.recvfrom(128)
                resp = data.decode("utf-8", errors="ignore")
                if "MGF_STATOR" in resp:
                    parts = resp.split(":")
                    if len(parts) >= 3:
                        return f"{parts[1]}:{parts[2]}"
                return None
            except socket.timeout:
                pass  # fall through to per-interface scan below
        except Exception as e:
            log.error("UDP discovery error: %s", e)
            return None
        finally:
            s.close()

        # 2. If timeout, try all local interfaces as a fallback for Windows routing issues
        try:
            hostname = socket.gethostname()
            _, _, ips = socket.gethostbyname_ex(hostname)
            for ip in ips:
                try:
                    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                    sock.bind((ip, 0))
                    sock.settimeout(0.5)
                    sock.sendto(b"DISCOVER_MGF", ("255.255.255.255", port))
                    
                    data, addr = sock.recvfrom(128)
                    sock.close()
                    resp = data.decode("utf-8", errors="ignore")
                    if "MGF_STATOR" in resp:
                        parts = resp.split(":")
                        if len(parts) >= 3:
                            return f"{parts[1]}:{parts[2]}"
                except Exception:
                    pass
        except Exception:
            pass
        return None

    @staticmethod
    def discover_mdns(timeout: float = 2.0) -> str | None:
        """Try to resolve mgf-stator.local via DNS."""
        try:
            ip = socket.getaddrinfo(
                "mgf-stator.local", None, socket.AF_INET, socket.SOCK_STREAM,
                0, socket.AI_ADDRCONFIG
            )
            if ip:
                return ip[0][4][0]
        except Exception:
            pass
        return None

    @staticmethod
    def discover_direct(timeout: float = 1.0) -> str | None:
        """Directly attempt to connect to the Stator's default link-local IP."""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(timeout)
            s.connect(("169.254.1.177", 5000))
            s.close()
            return "169.254.1.177:5000"
        except Exception as e:
            log.debug("Direct discovery failed: %s", e)
            return None

    def auto_discover(self) -> bool:
        """Chain: mDNS → UDP broadcast → Direct Link-Local → fall back to stored host."""
        # 1. mDNS
        ip = self.discover_mdns(timeout=1.5)
        if ip:
            self.host = ip
            log.info("Discovered via mDNS: %s", ip)
            return True

        # 2. UDP broadcast
        result = self.discover_udp(timeout=self.DISCOVERY_TIMEOUT_S)
        if result:
            parts = result.split(":")
            self.host = parts[0]
            if len(parts) > 1:
                self.port = int(parts[1])
            log.info("Discovered via UDP: %s:%d", self.host, self.port)
            return True

        # 3. Direct check (for direct Ethernet connections)
        result = self.discover_direct(timeout=1.0)
        if result:
            parts = result.split(":")
            self.host = parts[0]
            if len(parts) > 1:
                self.port = int(parts[1])
            log.info("Discovered via Direct Check: %s:%d", self.host, self.port)
            return True

        # 4. Fall back to configured host
        log.info("Discovery failed, using configured host %s:%d", self.host, self.port)
        return False

    # ------------------------------------------------------------------
    # Connect / Disconnect
    # ------------------------------------------------------------------

    def connect(self) -> bool:
        """Open TCP connection and start RX + heartbeat threads."""
        if self.connected:
            return True

        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.settimeout(self.CONNECT_TIMEOUT_S)
            log.info("Connecting to %s:%d ...", self.host, self.port)
            self.sock.connect((self.host, self.port))
            self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            self.connected = True
            self._running = True
            self._last_rx_time = time.monotonic()
            self._packets_received = 0
            self._crc_errors = 0

            # RX thread
            self._rx_thread = threading.Thread(target=self._rx_loop, daemon=True, name="MgfRX")
            self._rx_thread.start()

            # Heartbeat monitor thread
            self._hb_thread = threading.Thread(target=self._heartbeat_loop, daemon=True, name="MgfHB")
            self._hb_thread.start()

            # Protocol handshake
            self._send_hello()
            log.info("Connected!")
            return True
        except Exception as e:
            log.error("Connection error: %s", e)
            self.connected = False
            if self.auto_reconnect and not self._reconnecting:
                self._start_reconnect()
            return False

    def disconnect(self):
        """Cleanly shut down all threads and the socket."""
        self._running = False
        self.auto_reconnect = False  # Stop reconnect attempts
        if self.sock:
            try:
                self.sock.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass
            try:
                self.sock.close()
            except Exception:
                pass
        self.connected = False

    def _on_connection_lost(self):
        """Called when connection drops unexpectedly."""
        was_connected = self.connected
        self.connected = False
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
        if was_connected and self.auto_reconnect and not self._reconnecting:
            self._start_reconnect()

    # ------------------------------------------------------------------
    # Auto-reconnect
    # ------------------------------------------------------------------

    def _start_reconnect(self):
        """Spawn a background thread that retries connection."""
        if self._reconnecting:
            return
        self._reconnecting = True
        self._reconnect_thread = threading.Thread(
            target=self._reconnect_loop, daemon=True, name="MgfReconnect")
        self._reconnect_thread.start()

    def _reconnect_loop(self):
        """Retry connection with exponential backoff."""
        delay = self.RECONNECT_DELAY_S
        while self.auto_reconnect and not self.connected:
            log.info("Reconnecting in %.1fs ...", delay)
            time.sleep(delay)
            if not self.auto_reconnect:
                break
            self.auto_discover()
            if self.connect():
                break
            delay = min(delay * 1.5, 15.0)
        self._reconnecting = False

    # ------------------------------------------------------------------
    # Heartbeat monitor
    # ------------------------------------------------------------------

    def _heartbeat_loop(self):
        """Periodically send heartbeat and check for RX timeout."""
        while self._running and self.connected:
            time.sleep(self.HEARTBEAT_INTERVAL_S)
            if not self._running:
                break

            # Check for stale connection
            elapsed = time.monotonic() - self._last_rx_time
            if elapsed > self.HEARTBEAT_TIMEOUT_S:
                log.warning("Heartbeat timeout (%.1fs since last RX)", elapsed)
                self._on_connection_lost()
                break

            # Send heartbeat packet
            try:
                ts = int(time.monotonic() * 1000) & 0xFFFFFFFF
                seq = self._seq & 0xFFFF
                payload = struct.pack('<IH', ts, seq)
                self.send_packet(protocol.TCP_TYPE_HEARTBEAT, payload)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # TX
    # ------------------------------------------------------------------

    def _send_hello(self):
        """Send protocol handshake."""
        payload = protocol.STRUCT_HELLO.pack(
            protocol.MGF_PROTOCOL_VERSION,
            0,
            b'MgfPyClient\0\0\0\0\0'
        )
        self.send_packet(protocol.TCP_TYPE_HELLO, payload)

    def send_command(self, cmd: int, param_raw: int | float = 0):
        """Send a command to the stator. Float params are auto-encoded."""
        if isinstance(param_raw, float):
            param_raw = struct.unpack('<I', struct.pack('<f', param_raw))[0]
        payload = protocol.STRUCT_CMD.pack(cmd, param_raw)
        self.send_packet(protocol.TCP_TYPE_CMD, payload)

    def send_packet(self, pkt_type: int, payload: bytes):
        """Build TLV frame with CRC and send."""
        if not self.connected or not self.sock:
            return

        seq = self._seq
        self._seq = (self._seq + 1) & 0xFFFF

        hdr = protocol.STRUCT_TCP_HEADER.pack(
            protocol.MGF_TCP_MAGIC,
            len(payload),
            pkt_type,
            seq
        )

        crc = protocol.calc_crc32(hdr + payload)
        packet = hdr + payload + struct.pack('<I', crc)

        try:
            self.sock.sendall(packet)
        except Exception as e:
            log.error("TX error: %s", e)
            self._on_connection_lost()

    # ------------------------------------------------------------------
    # RX — Zero-copy index-based parser
    # ------------------------------------------------------------------

    def _rx_loop(self):
        """Receive loop with index-based TLV parser (no O(N) buffer deletion)."""
        self.sock.settimeout(1.0)
        buf = bytearray(65536)
        buf_len = 0  # Valid data length in buf

        while self._running:
            try:
                # Read into remaining space
                view = memoryview(buf)[buf_len:]
                if len(view) == 0:
                    # Buffer full — compact or drop
                    buf_len = 0
                    continue
                n = self.sock.recv_into(view, len(view))
                if n == 0:
                    log.info("Server closed connection")
                    break
                buf_len += n
                self._last_rx_time = time.monotonic()

                # Parse all complete TLV packets
                read_pos = 0
                while read_pos < buf_len:
                    remaining = buf_len - read_pos

                    # Need at least TcpHeader (7 bytes)
                    if remaining < 7:
                        break

                    # Check magic
                    magic = buf[read_pos] | (buf[read_pos + 1] << 8)
                    if magic != protocol.MGF_TCP_MAGIC:
                        # Resync: advance 1 byte
                        read_pos += 1
                        continue

                    # Parse header
                    hdr_magic, hdr_len, hdr_type, hdr_seq = protocol.STRUCT_TCP_HEADER.unpack_from(
                        buf, read_pos)

                    total_len = 7 + hdr_len + 4  # header + payload + CRC32
                    if total_len > 256:
                        # Garbage length! Slide window by 1 byte and scan again
                        read_pos += 1
                        continue

                    if remaining < total_len:
                        break  # Wait for more data

                    # Validate CRC
                    packet_data = bytes(buf[read_pos:read_pos + 7 + hdr_len])
                    received_crc = struct.unpack_from('<I', buf, read_pos + 7 + hdr_len)[0]
                    calc_crc = protocol.calc_crc32(packet_data)

                    if calc_crc == received_crc:
                        payload = packet_data[7:]
                        try:
                            self.rx_queue.put_nowait((hdr_type, payload))
                        except queue.Full:
                            pass  # Drop packet if GUI can't keep up
                        self._packets_received += 1
                        read_pos += total_len
                    else:
                        self._crc_errors += 1
                        read_pos += 1  # Slide window by 1 byte to resynchronize

                # Compact: move unprocessed bytes to front
                if read_pos > 0:
                    leftover = buf_len - read_pos
                    if leftover > 0:
                        buf[:leftover] = buf[read_pos:buf_len]
                    buf_len = leftover

            except socket.timeout:
                continue
            except Exception as e:
                if self._running:
                    log.error("RX error: %s", e)
                break

        self._on_connection_lost()

    # ------------------------------------------------------------------
    # Status / quality accessors
    # ------------------------------------------------------------------

    @property
    def latency_ms(self) -> float:
        return self._latency_ms

    @property
    def packets_received(self) -> int:
        return self._packets_received

    @property
    def crc_errors(self) -> int:
        return self._crc_errors

    @property
    def connection_quality(self) -> str:
        """Simple quality string based on recent RX activity."""
        if not self.connected:
            return "Offline"
        elapsed = time.monotonic() - self._last_rx_time
        if elapsed < 0.5:
            return "Excellent"
        elif elapsed < 2.0:
            return "Good"
        elif elapsed < 4.0:
            return "Poor"
        else:
            return "Timeout"
