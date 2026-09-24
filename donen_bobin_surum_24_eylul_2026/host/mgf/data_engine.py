import os
import struct
import numpy as np
import threading
import queue
import time
from . import protocol
from .session import save_session

class DataEngine:
    def __init__(self, max_points=1000000):
        self.max_points = max_points
        self.lock = threading.Lock()
        
        # Ring buffers for fast plotting
        self.adc_data = np.zeros(max_points, dtype=np.float32)
        self.enc_data = np.zeros(max_points, dtype=np.float32)
        self.step_data = np.zeros(max_points, dtype=np.float32)
        self.enc_pulses_data = np.zeros(max_points, dtype=np.float32)
        self.head = 0
        self.tail = 0
        self.count = 0
        
        # State from status/hello
        self.rotor_online = False
        self.motor_speed = 0.0
        self.encoder_ppr = 14400
        self.total_samples_received = 0
        # Seed with initial configuration matching firmware defaults
        self.current_adc_config = (5, 12, 0, 3, 0, 0, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0x0B, 0x0B, 1)
        self.adc_config_sync_pending = False
        
        # Sweepline pos
        self.current_angle_deg = 0.0
        self.current_data_mode = 1 # 1 = Voltage, 0 = RAW
        self.live_rate_sps = 2400.0  # Updated when ADC rate changes
        
        # Polar plot binning (360 degrees)
        self.polar_bins = np.zeros(360, dtype=np.float32)
        self.polar_counts = np.zeros(360, dtype=np.int32)
        self.polar_averaging = False
        
        # Recording (CSV + .mgf session)
        self.recording = False
        self.record_file = None
        self.csv_writer = None
        self.recording_adc = np.zeros(0, dtype=np.float32)
        self.recording_enc = np.zeros(0, dtype=np.float32)
        self.recording_step = np.zeros(0, dtype=np.float32)
        self.recording_enc_pulses = np.zeros(0, dtype=np.float32)
        self._recording_capacity = 10_000_000  # Max ~10M samples per recording
        self._recording_count = 0
        
        # Replay Mode State
        self.replay_mode = False
        self.replay_adc = None
        self.replay_enc = None
        self.replay_idx = 0
        self.replay_rate_sps = 2400.0
        
        # Coil alignment phase offset (degrees)
        self.phase_offset_deg = 0.0
        
        # Min/Max tracking (None indicates uninitialized)
        self.min_voltage = None
        self.max_voltage = None
        self.min_raw = None
        self.max_raw = None
        self.last_raw = 0
        self.last_voltage = 0.0
        self.current_vref = 2.5
        self.adc_status_state = 'ok'
        self.last_adc_error = None
        self.pending_adc_config = None
        
    # ADS1263 gain table (matches ads1263_types.h ADS1263_GAIN_VALUES)
    _GAIN_TABLE = [1.0, 2.0, 4.0, 8.0, 16.0, 32.0]
    
    def _raw_to_voltage(self, raw: int) -> float:
        """Convert raw 32-bit ADC code to voltage using current ADC config.
        Formula: voltage = raw * vref / (gain * 2^31)
        Matches ADS1263 driver's toVoltage() / updateLSBValue().
        """
        if self.current_adc_config is None:
            return float(raw)  # Fallback: no config yet
        gain_idx = self.current_adc_config[0]   # index 0 = gain
        pga_bypass = self.current_adc_config[2]  # index 2 = pga_bypass
        if pga_bypass or gain_idx >= len(self._GAIN_TABLE):
            gain = 1.0
        else:
            gain = self._GAIN_TABLE[gain_idx]
        lsb = self.current_vref / (gain * 2147483648.0)
        return raw * lsb
        
    def reset_min_max(self):
        with self.lock:
            self.min_voltage = None
            self.max_voltage = None
            self.min_raw = None
            self.max_raw = None
            
    def clear_active_buffers(self):
        """Reset circular buffers and polar bins."""
        with self.lock:
            self.head = 0
            self.tail = 0
            self.count = 0
            self.total_samples_received = 0
            self.adc_data.fill(0.0)
            self.enc_data.fill(0.0)
            self.step_data.fill(0.0)
            self.enc_pulses_data.fill(0.0)
            self.polar_bins.fill(0.0)
            self.polar_counts.fill(0)
            self.current_angle_deg = 0.0
            
    def resize_buffers(self, new_max_points):
        """Dynamically resize circular buffers to a new maximum size, preserving existing data."""
        with self.lock:
            if new_max_points == self.max_points:
                return
            new_adc = np.zeros(new_max_points, dtype=np.float32)
            new_enc = np.zeros(new_max_points, dtype=np.float32)
            new_step = np.zeros(new_max_points, dtype=np.float32)
            new_enc_pulses = np.zeros(new_max_points, dtype=np.float32)
            
            if self.count > 0:
                n = min(self.count, new_max_points)
                start = (self.head - n) % self.max_points
                if start < self.head:
                    adc = self.adc_data[start:self.head]
                    enc = self.enc_data[start:self.head]
                    step = self.step_data[start:self.head]
                    enc_pulses = self.enc_pulses_data[start:self.head]
                else:
                    adc = np.concatenate((self.adc_data[start:], self.adc_data[:self.head]))
                    enc = np.concatenate((self.enc_data[start:], self.enc_data[:self.head]))
                    step = np.concatenate((self.step_data[start:], self.step_data[:self.head]))
                    enc_pulses = np.concatenate((self.enc_pulses_data[start:], self.enc_pulses_data[:self.head]))
                
                new_adc[:n] = adc
                new_enc[:n] = enc
                new_step[:n] = step
                new_enc_pulses[:n] = enc_pulses
                
                self.head = n
                self.tail = 0
                self.count = n
            else:
                self.head = 0
                self.tail = 0
                self.count = 0
                
            self.adc_data = new_adc
            self.enc_data = new_enc
            self.step_data = new_step
            self.enc_pulses_data = new_enc_pulses
            self.max_points = new_max_points
        
    def start_recording(self):
        import csv
        from datetime import datetime
        with self.lock:
            if not self.recording:
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                filepath = os.path.join("outputs", f"radar_data_{ts}.csv")
                self.record_file = open(filepath, 'w', newline='')
                self.csv_writer = csv.writer(self.record_file)
                self.csv_writer.writerow(['EncoderDeg', 'Value', 'Status', 'DataType'])
                self.recording_adc = np.zeros(self._recording_capacity, dtype=np.float32)
                self.recording_enc = np.zeros(self._recording_capacity, dtype=np.float32)
                self.recording_step = np.zeros(self._recording_capacity, dtype=np.float32)
                self.recording_enc_pulses = np.zeros(self._recording_capacity, dtype=np.float32)
                self._recording_count = 0
                self.recording = True
                
    def stop_recording(self, filepath=None):
        """Stop recording and save session data to .mgf file."""
        with self.lock:
            if self.recording:
                self.recording = False
                if self.record_file:
                    self.record_file.close()
                    self.record_file = None
                
                # Save as .mgf if we have collected data
                if self._recording_count > 0:
                    adc_arr = self.recording_adc[:self._recording_count].copy()
                    enc_arr = self.recording_enc[:self._recording_count].copy()
                    step_arr = self.recording_step[:self._recording_count].copy()
                    enc_pulses_arr = self.recording_enc_pulses[:self._recording_count].copy()
                    
                    if not filepath:
                        from datetime import datetime
                        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                        filepath = os.path.join("sessions", f"radar_session_{ts}.mgf")
                    elif not os.path.isabs(filepath) and not filepath.startswith("sessions"):
                        filepath = os.path.join("sessions", filepath)
                        
                    save_session(
                        filepath,
                        adc_arr,
                        enc_arr,
                        rate_sps=self.live_rate_sps,
                        motor_speed_hz=self.motor_speed,
                        data_mode=self.current_data_mode,
                        step_data=step_arr,
                        enc_pulses_data=enc_pulses_arr
                    )
                self.recording_adc = np.zeros(0, dtype=np.float32)
                self.recording_enc = np.zeros(0, dtype=np.float32)
                self.recording_step = np.zeros(0, dtype=np.float32)
                self.recording_enc_pulses = np.zeros(0, dtype=np.float32)
                self._recording_count = 0

    def add_fused_sample(self, adc_val, enc_val, step_val, status, data_type, flags=0):
        # Convert encoder to degrees
        deg = (enc_val % self.encoder_ppr) / self.encoder_ppr * 360.0
        # Apply alignment phase offset
        deg = (deg - self.phase_offset_deg) % 360.0
        
        # Parse data — wire always carries raw 32-bit ADC codes.
        # Convert to voltage locally if data_mode == 1 (voltage display).
        if data_type == 1:
            val = self._raw_to_voltage(adc_val)
        else:
            val = float(adc_val)
            
        with self.lock:
            self.current_data_mode = data_type
            
            # Min/Max tracking
            if data_type == 1:
                self.last_voltage = val
                if self.min_voltage is None or val < self.min_voltage: self.min_voltage = val
                if self.max_voltage is None or val > self.max_voltage: self.max_voltage = val
            else:
                self.last_raw = adc_val
                if self.min_raw is None or adc_val < self.min_raw: self.min_raw = adc_val
                if self.max_raw is None or adc_val > self.max_raw: self.max_raw = adc_val

            self.adc_data[self.head] = val
            self.enc_data[self.head] = deg
            self.step_data[self.head] = float(step_val)
            self.enc_pulses_data[self.head] = float(enc_val)
            self.current_angle_deg = deg
            
            self.total_samples_received += 1

            # Update polar bins
            bin_idx = int(deg) % 360
            if self.polar_averaging:
                count = self.polar_counts[bin_idx]
                if count == 0:
                    self.polar_bins[bin_idx] = val
                    self.polar_counts[bin_idx] = 1
                else:
                    self.polar_bins[bin_idx] = (self.polar_bins[bin_idx] * count + val) / (count + 1)
                    self.polar_counts[bin_idx] = min(count + 1, 1000)
            else:
                self.polar_bins[bin_idx] = val
                self.polar_counts[bin_idx] = 1
            
            if self.recording:
                if self._recording_count < len(self.recording_adc):
                    self.recording_adc[self._recording_count] = val
                    self.recording_enc[self._recording_count] = deg
                    self.recording_step[self._recording_count] = float(step_val)
                    self.recording_enc_pulses[self._recording_count] = float(enc_val)
                    self._recording_count += 1
                if self.csv_writer:
                    self.csv_writer.writerow([deg, val, status, data_type])
            
            self.head = (self.head + 1) % self.max_points
            if self.count < self.max_points:
                self.count += 1
            else:
                self.tail = (self.tail + 1) % self.max_points

    def process_queue(self, rx_queue: queue.Queue, log_cb=None):
        if self.replay_mode:
            # In replay mode, do not process live packets
            return
            
        try:
            while True:
                pkt_type, payload = rx_queue.get_nowait()
                
                if pkt_type == protocol.TCP_TYPE_FUSED_SAMPLE:
                    adc_val, enc_val, step_val, adc_status, data_type, flags = protocol.STRUCT_FUSED_SAMPLE.unpack(payload)
                    self.add_fused_sample(adc_val, enc_val, step_val, adc_status, data_type, flags)
                    
                elif pkt_type == protocol.TCP_TYPE_ENC_UPDATE:
                    timestamp, enc_val = protocol.STRUCT_ENC_UPDATE.unpack(payload)
                    raw_deg = (enc_val % self.encoder_ppr) / self.encoder_ppr * 360.0
                    self.current_angle_deg = (raw_deg - self.phase_offset_deg) % 360.0
                    
                elif pkt_type == protocol.TCP_TYPE_STATUS:
                    up, spd, enc, ppr, r_on, r_err, ro_err, q_depth = protocol.STRUCT_STATUS.unpack(payload)
                    self.motor_speed = spd
                    self.encoder_ppr = ppr
                    self.rotor_online = (r_on != 0)
                    
                elif pkt_type == protocol.TCP_TYPE_HELLO_ACK:
                    parts = protocol.STRUCT_HELLO_ACK.unpack(payload)
                    self.encoder_ppr = parts[2]
                    self.motor_speed = parts[3]
                    self.current_adc_config = parts[4:]
                    self.adc_status_state = 'ok'
                    self.pending_adc_config = None
                    self.adc_config_sync_pending = True
                    
                    ref_pos = self.current_adc_config[10]
                    ref_neg = self.current_adc_config[11]
                    if ref_pos == 0 and ref_neg == 0:
                        self.current_vref = 2.5
                    elif ref_pos == 4 and ref_neg == 4:
                        self.current_vref = 5.0
                    else:
                        self.current_vref = 2.5
                    
                elif pkt_type == protocol.TCP_TYPE_ADC_CONFIG:
                    config = protocol.STRUCT_ADC_CONFIG.unpack(payload)
                    if self.adc_status_state == 'verifying':
                        self.pending_adc_config = config
                    else:
                        self.current_adc_config = config
                        self.pending_adc_config = None
                        self.adc_config_sync_pending = True
                    self.adc_status_state = 'ok'
                    # Update live_rate_sps from config byte index 1 (rate index)
                    # Map rate index to SPS values matching RATE_MAP in control_panel
                    _RATE_IDX_TO_SPS = [
                        2.5, 5.0, 10.0, 16.6, 20.0, 50.0, 60.0, 100.0,
                        400.0, 1200.0, 2400.0, 4800.0, 7200.0, 14400.0, 19200.0, 38400.0
                    ]
                    rate_idx = config[1]
                    if 0 <= rate_idx < len(_RATE_IDX_TO_SPS):
                        self.live_rate_sps = _RATE_IDX_TO_SPS[rate_idx]
                        
                    ref_pos = config[10]
                    ref_neg = config[11]
                    if ref_pos == 0 and ref_neg == 0:
                        self.current_vref = 2.5
                    elif ref_pos == 4 and ref_neg == 4:
                        self.current_vref = 5.0
                    else:
                        self.current_vref = 2.5
                        
                elif pkt_type == protocol.TCP_TYPE_ACK:
                    cmd, status = protocol.STRUCT_ACK.unpack(payload)
                    if status != 0:
                        self.adc_status_state = 'error'
                        self.pending_adc_config = None
                        status_names = {
                            1: "General Error",
                            2: "Invalid Command",
                            3: "Invalid Parameter",
                            4: "Timeout",
                            5: "Busy"
                        }
                        err_name = status_names.get(status, f"Code {status}")
                        self.last_adc_error = f"Cmd 0x{cmd:02X} failed: {err_name}"
                        if log_cb:
                            log_cb(f"ADC Error: Command 0x{cmd:02X} failed with status: {err_name}")
                    else:
                        if self.adc_status_state == 'verifying':
                            self.adc_status_state = 'ok'
                            if self.pending_adc_config is not None:
                                self.current_adc_config = self.pending_adc_config
                                self.pending_adc_config = None
                                self.adc_config_sync_pending = True
        except queue.Empty:
            pass

    def get_latest_data(self, num_points):
        with self.lock:
            if self.count == 0:
                return np.array([]), np.array([])
                
            n = min(num_points, self.count)
            start = (self.head - n) % self.max_points
            
            if start < self.head:
                adc = self.adc_data[start:self.head]
                enc = self.enc_data[start:self.head]
            else:
                adc = np.concatenate((self.adc_data[start:], self.adc_data[:self.head]))
                enc = np.concatenate((self.enc_data[start:], self.enc_data[:self.head]))
                
            return enc, adc

    def get_latest_pulses(self, num_points):
        with self.lock:
            if self.count == 0:
                return np.array([]), np.array([])
                
            n = min(num_points, self.count)
            start = (self.head - n) % self.max_points
            
            if start < self.head:
                enc_pulses = self.enc_pulses_data[start:self.head]
                step_pulses = self.step_data[start:self.head]
            else:
                enc_pulses = np.concatenate((self.enc_pulses_data[start:], self.enc_pulses_data[:self.head]))
                step_pulses = np.concatenate((self.step_data[start:], self.step_data[:self.head]))
                
            return enc_pulses, step_pulses
            
    def get_polar_data(self):
        with self.lock:
            return self.polar_bins.copy()

    # ==========================================
    # REPLAY MODE METHODS
    # ==========================================
    def load_for_replay(self, adc, enc, rate_sps, motor_speed_hz, data_mode, step=None, enc_pulses=None):
        with self.lock:
            self.replay_adc = adc
            self.replay_enc = enc
            self.replay_step = step if step is not None else np.zeros_like(adc)
            self.replay_enc_pulses = enc_pulses if enc_pulses is not None else np.zeros_like(adc)
            self.replay_rate_sps = rate_sps
            self.motor_speed = motor_speed_hz
            self.current_data_mode = data_mode
            self.replay_idx = 0
            self.replay_mode = True
            self.phase_offset_deg = 0.0
            
        self.clear_active_buffers()
        self.reset_min_max()
        
    def stop_replay(self):
        with self.lock:
            self.replay_mode = False
            self.replay_adc = None
            self.replay_enc = None
            self.replay_step = None
            self.replay_enc_pulses = None
            self.replay_idx = 0
        self.clear_active_buffers()
        self.reset_min_max()
        
    def seek_replay(self, idx):
        """Scrub to a specific sample index in replay mode (vectorized)."""
        with self.lock:
            if self.replay_adc is None:
                return
            idx = max(0, min(idx, len(self.replay_adc)))
            self.replay_idx = idx
            
        self.clear_active_buffers()
        self.reset_min_max()
        
        # Populate history buffer using vectorized numpy ops
        start_idx = max(0, idx - self.max_points)
        n = idx - start_idx
        if n <= 0:
            return
            
        adc_slice = self.replay_adc[start_idx:idx]
        enc_slice = self.replay_enc[start_idx:idx]
        step_slice = self.replay_step[start_idx:idx]
        enc_pulses_slice = self.replay_enc_pulses[start_idx:idx]
        
        with self.lock:
            # Fill ring buffer directly
            if n <= self.max_points:
                self.adc_data[:n] = adc_slice
                self.enc_data[:n] = enc_slice
                self.step_data[:n] = step_slice
                self.enc_pulses_data[:n] = enc_pulses_slice
                self.head = n % self.max_points
                self.tail = 0
                self.count = n
            else:
                # More data than buffer can hold — take last max_points
                self.adc_data[:] = adc_slice[-self.max_points:]
                self.enc_data[:] = enc_slice[-self.max_points:]
                self.step_data[:] = step_slice[-self.max_points:]
                self.enc_pulses_data[:] = enc_pulses_slice[-self.max_points:]
                self.head = 0
                self.tail = 0
                self.count = self.max_points
            
            # Update angle
            self.current_angle_deg = float(enc_slice[-1])
            
            # Min/Max tracking
            if self.current_data_mode == 1:
                self.last_voltage = float(adc_slice[-1])
                self.min_voltage = float(np.min(adc_slice))
                self.max_voltage = float(np.max(adc_slice))
            else:
                self.last_raw = int(adc_slice[-1])
                self.min_raw = int(np.min(adc_slice))
                self.max_raw = int(np.max(adc_slice))
            
            # Rebuild polar bins (vectorized)
            bin_indices = enc_slice.astype(np.int32) % 360
            # Last-write-wins for each bin (matches original behavior)
            self.polar_bins[bin_indices] = adc_slice
            self.polar_counts[bin_indices] = 1

    def step_replay(self, count):
        """Step forward by 'count' samples."""
        with self.lock:
            if self.replay_adc is None:
                return 0
            
            total_samples = len(self.replay_adc)
            if self.replay_idx >= total_samples:
                return 0
                
            end_idx = min(self.replay_idx + count, total_samples)
            actual_count = end_idx - self.replay_idx
            
            for i in range(self.replay_idx, end_idx):
                val = self.replay_adc[i]
                deg = self.replay_enc[i]
                step_val = self.replay_step[i]
                enc_pulse_val = self.replay_enc_pulses[i]
                
                self.adc_data[self.head] = val
                self.enc_data[self.head] = deg
                self.step_data[self.head] = step_val
                self.enc_pulses_data[self.head] = enc_pulse_val
                self.current_angle_deg = deg
                
                if self.current_data_mode == 1:
                    self.last_voltage = val
                    if self.min_voltage is None or val < self.min_voltage: self.min_voltage = val
                    if self.max_voltage is None or val > self.max_voltage: self.max_voltage = val
                else:
                    self.last_raw = int(val)
                    if self.min_raw is None or val < self.min_raw: self.min_raw = int(val)
                    if self.max_raw is None or val > self.max_raw: self.max_raw = int(val)
                    
                bin_idx = int(deg) % 360
                self.polar_bins[bin_idx] = val
                self.polar_counts[bin_idx] = 1
                
                self.head = (self.head + 1) % self.max_points
                if self.count < self.max_points:
                    self.count += 1
                else:
                    self.tail = (self.tail + 1) % self.max_points
                    
            self.replay_idx = end_idx
            return actual_count
