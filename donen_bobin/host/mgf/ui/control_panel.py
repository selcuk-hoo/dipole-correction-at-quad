import time
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QLineEdit,
    QComboBox, QGridLayout, QTextEdit, QGroupBox, QFrame, QButtonGroup,
    QSlider, QFileDialog, QScrollArea, QApplication, QCheckBox, QSizePolicy
)
from PySide6.QtCore import Qt

from .. import protocol
from .. import session

RATE_MAP = {
    "2.5 SPS": 0, "5 SPS": 1, "10 SPS": 2, "16.6 SPS": 3, "20 SPS": 4, "50 SPS": 5,
    "60 SPS": 6, "100 SPS": 7, "400 SPS": 8, "1200 SPS": 9, "2400 SPS": 10,
    "4800 SPS": 11, "7200 SPS": 12, "14400 SPS": 13, "19200 SPS": 14, "38400 SPS": 15
}
FILTER_MAP = {"Sinc1": 0, "Sinc2": 1, "Sinc3": 2, "Sinc4": 3, "FIR": 4}

class LedIndicator(QFrame):
    """A small custom LED indicator widget."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(14, 14)
        self.color = "#98c379"  # Default to green (All ok)
        self.update_style()

    def set_color(self, color_hex):
        if self.color != color_hex:
            self.color = color_hex
            self.update_style()

    def update_style(self):
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {self.color};
                border: 1px solid #282c34;
                border-radius: 7px;
            }}
        """)


class CollapsibleSection(QWidget):
    """A custom expandable/collapsible section container that stays open until toggled."""
    def __init__(self, title, content_widget, parent=None):
        super().__init__(parent)
        self.content = content_widget
        self.raw_title = title
        
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        
        self.btn_header = QPushButton()
        self.btn_header.setStyleSheet("""
            QPushButton {
                background-color: #21252b;
                color: #61afef;
                font-weight: bold;
                text-align: left;
                padding: 6px;
                border: 1px solid #5c6370;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #3b4048;
            }
        """)
        self.btn_header.clicked.connect(self.toggle)
        layout.addWidget(self.btn_header)
        
        layout.addWidget(self.content)
        self.content.setVisible(False)  # Collapsed/closed by default
        self.update_header()
        
    def toggle(self):
        self.content.setVisible(not self.content.isVisible())
        self.update_header()
        self.updateGeometry()

    def update_header(self):
        prefix = "▼ " if self.content.isVisible() else "▶ "
        self.btn_header.setText(prefix + self.raw_title)

class ControlPanelWidget(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.mw = main_window
        self.conn = main_window.conn
        self.engine = main_window.engine
        self.settings = main_window.settings
        
        # State
        self.servo_state = False
        self.replay_playing = False
        self.replay_speed_mult = 1.0
        
        # FFT Settings State
        self.fft_size = -1
        self.fft_window = "Hanning"
        self.fft_domain = "Order"
        self.fft_max_x = 100.0
        self.fft_y_log = True

        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Scroll area for left panel widgets
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        
        scroll_content = QWidget()
        scroll_lay = QVBoxLayout(scroll_content)
        scroll_lay.setContentsMargins(0, 0, 0, 0)
        scroll_lay.setSpacing(6)

        # Build Collapsible Sections
        sect_net = self._build_network_section()
        sect_motor = self._build_motor_section()
        sect_adc = self._build_adc_section()
        sect_session = self._build_session_section()
        sect_graphics = self._build_graphics_section()

        scroll_lay.addWidget(CollapsibleSection("Network", sect_net))
        scroll_lay.addWidget(CollapsibleSection("Motor Control", sect_motor))
        scroll_lay.addWidget(CollapsibleSection("ADC Control", sect_adc))
        scroll_lay.addWidget(CollapsibleSection("Session Manager", sect_session))
        scroll_lay.addWidget(CollapsibleSection("Graphic Settings", sect_graphics))
        scroll_lay.addStretch()

        scroll.setWidget(scroll_content)
        layout.addWidget(scroll)

    def log(self, msg):
        if hasattr(self.mw, 'status_bar'):
            self.mw.status_bar.log(msg)
        elif hasattr(self.mw, 'log'):
            self.mw.log(msg)

    def _send(self, cmd, param=0):
        if self.conn.connected:
            adc_cmds = {
                protocol.CMD_SET_GAIN,
                protocol.CMD_SET_RATE,
                protocol.CMD_SET_FILTER,
                protocol.CMD_SET_CHOP,
                protocol.CMD_SET_PGA_BYPASS,
                protocol.CMD_SET_VBIAS,
                protocol.CMD_SET_DATA_MODE,
                protocol.CMD_SET_SCAN_CHANNELS,
                protocol.CMD_CALIBRATE_OFFSET,
                protocol.CMD_CALIBRATE_GAIN,
                protocol.CMD_RESET_CALIBRATION
            }
            if cmd in adc_cmds:
                self.engine.adc_status_state = 'verifying'
            self.conn.send_command(cmd, param)


    def _build_network_section(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        h1 = QHBoxLayout()
        h1.addWidget(QLabel("IP:"))
        self.inp_ip = QLineEdit(self.settings.host)
        h1.addWidget(self.inp_ip)
        h2 = QHBoxLayout()
        h2.addWidget(QLabel("Port:"))
        self.inp_port = QLineEdit(str(self.settings.port))
        h2.addWidget(self.inp_port)
        
        btn_lay = QHBoxLayout()
        self.btn_scan = QPushButton("SCAN")
        self.btn_scan.setStyleSheet("background-color: #d19a66; font-weight: bold; color: black;")
        self.btn_scan.clicked.connect(self.scan_network)
        
        self.btn_conn = QPushButton("CONNECT")
        self.btn_conn.setStyleSheet("background-color: #61afef; font-weight: bold; color: black;")
        self.btn_conn.clicked.connect(self.toggle_connect)
        
        btn_lay.addWidget(self.btn_scan)
        btn_lay.addWidget(self.btn_conn)
        
        lay.addLayout(h1)
        lay.addLayout(h2)
        lay.addLayout(btn_lay)
        return w

    def _build_motor_section(self):
        w = QWidget()
        g = QGridLayout(w)
        self.inp_speed = QLineEdit(str(self.settings.motor_speed))
        btn_set = QPushButton("Set Speed")
        btn_set.clicked.connect(self._on_set_motor_speed)
        btn_stop = QPushButton("Stop")
        btn_stop.setStyleSheet("background-color: #e06c75;")
        btn_stop.clicked.connect(self._on_stop_motor)
        g.addWidget(QLabel("Speed (Hz):"), 0, 0)
        g.addWidget(self.inp_speed, 0, 1)
        g.addWidget(btn_set, 0, 2)
        g.addWidget(btn_stop, 0, 3)

        self.btn_servo = QPushButton("Servo On")
        self.btn_servo.setObjectName("ServoBtn")
        self.btn_servo.clicked.connect(self.toggle_servo)
        btn_pulse = QPushButton("Pulse Clear")
        btn_pulse.setToolTip("Send a 100 ms pulse to external hardware.")
        btn_pulse.clicked.connect(lambda: self._send(protocol.CMD_CLEAR_PULSE))
        btn_alarm = QPushButton("Alarm Reset")
        btn_alarm.clicked.connect(lambda: self._send(protocol.CMD_RESET_ALARM))
        g.addWidget(self.btn_servo, 1, 0, 1, 2)
        g.addWidget(btn_pulse, 1, 2)
        g.addWidget(btn_alarm, 1, 3)
        return w

    def _build_adc_section(self):
        w = QWidget()
        g = QGridLayout(w)

        self.cb_input = QComboBox()
        self.input_options = [
            ("AIN0-AIN1", 0, 1),
            ("AIN2-AIN3", 2, 3),
            ("AIN4-AIN5", 4, 5),
            ("AIN6-AIN7", 6, 7),
            ("AIN8-AIN9", 8, 9),
        ]
        for i in range(10):
            self.input_options.append((f"AIN{i} (SE)", i, 0x0A))
            
        self.cb_input.addItems([opt[0] for opt in self.input_options])
        self.cb_input.currentIndexChanged.connect(
            lambda i: self._send(protocol.CMD_SET_SCAN_CHANNELS, (self.input_options[i][1] << 8) | self.input_options[i][2]))

        self.cb_gain = QComboBox()
        self.cb_gain.addItems(["1x", "2x", "4x", "8x", "16x", "32x"])
        self.cb_gain.currentIndexChanged.connect(self._on_gain_changed)
        self.engine.current_gain = 1.0

        self.cb_rate = QComboBox()
        self.cb_rate.addItems(list(RATE_MAP.keys()))
        if self.settings.rate in RATE_MAP:
            self.cb_rate.setCurrentText(self.settings.rate)
        else:
            self.cb_rate.setCurrentText("2400 SPS")
        self.cb_rate.currentTextChanged.connect(self._on_rate_changed)

        self.cb_filter = QComboBox()
        self.cb_filter.addItems(list(FILTER_MAP.keys()))
        self.cb_filter.setCurrentText("Sinc4")
        self.cb_filter.currentIndexChanged.connect(
            lambda i: self._send(protocol.CMD_SET_FILTER, i))

        self.cb_mode = QComboBox()
        self.cb_mode.addItems(["RAW (int32)", "Voltage (V)"])
        if 0 <= self.settings.data_mode < 2:
            self.cb_mode.setCurrentIndex(self.settings.data_mode)
        else:
            self.cb_mode.setCurrentIndex(1)
        self.cb_mode.currentIndexChanged.connect(self._on_mode_changed)

        # Status row at top
        status_layout = QHBoxLayout()
        status_layout.setContentsMargins(0, 0, 0, 0)
        status_layout.setSpacing(6)
        
        self.led_indicator = LedIndicator()
        self.lbl_status_text = QLabel("ADC Status: Ok")
        self.lbl_status_text.setStyleSheet("font-weight: bold; color: #98c379;")
        
        status_layout.addWidget(self.led_indicator)
        status_layout.addWidget(self.lbl_status_text)
        status_layout.addStretch()
        
        g.addLayout(status_layout, 0, 0, 1, 2)

        g.addWidget(QLabel("Input:"),  1, 0); g.addWidget(self.cb_input,  1, 1)
        g.addWidget(QLabel("Gain:"),   2, 0); g.addWidget(self.cb_gain,   2, 1)
        g.addWidget(QLabel("Rate:"),   3, 0); g.addWidget(self.cb_rate,   3, 1)
        g.addWidget(QLabel("Filter:"), 4, 0); g.addWidget(self.cb_filter, 4, 1)
        g.addWidget(QLabel("Mode:"),   5, 0); g.addWidget(self.cb_mode,   5, 1)

        sep = QFrame(); sep.setFrameShape(QFrame.HLine); sep.setFrameShadow(QFrame.Sunken)
        g.addWidget(sep, 6, 0, 1, 2)

        # PGA and VBIAS switches
        switches = QHBoxLayout()
        self.btn_pga = QPushButton("PGA: ON")
        self.btn_pga.setCheckable(True)
        self.btn_pga.setChecked(True)
        self.btn_pga.clicked.connect(self._toggle_pga)
        switches.addWidget(self.btn_pga)

        self.btn_vbias = QPushButton("VBIAS: OFF")
        self.btn_vbias.setCheckable(True)
        self.btn_vbias.setChecked(False)
        self.btn_vbias.clicked.connect(self._toggle_vbias)
        switches.addWidget(self.btn_vbias)
        
        g.addLayout(switches, 7, 0, 1, 2)

        chop_lay = QVBoxLayout()
        chop_lay.addWidget(QLabel("Chop Mode:"))
        chop_btns = QHBoxLayout()
        self.chop_group = QButtonGroup(self)
        for txt, val in [("Off", 0), ("In", 1), ("IDAC", 2), ("Both", 3)]:
            b = QPushButton(txt); b.setCheckable(True)
            if val == 0: b.setChecked(True)
            self.chop_group.addButton(b, val)
            chop_btns.addWidget(b)
        self.chop_group.idClicked.connect(
            lambda cid: self._send(protocol.CMD_SET_CHOP, cid))
        chop_lay.addLayout(chop_btns)
        g.addLayout(chop_lay, 8, 0, 1, 2)

        cal = QHBoxLayout()
        cal.addWidget(QLabel("Calibration:"))
        b1 = QPushButton("Self Offset")
        b1.clicked.connect(lambda: self._send(protocol.CMD_CALIBRATE_OFFSET, 0))
        b2 = QPushButton("Sys Offset")
        b2.clicked.connect(lambda: self._send(protocol.CMD_CALIBRATE_OFFSET, 1))
        b3 = QPushButton("Sys Gain")
        b3.clicked.connect(self.on_sys_gain_clicked)
        b4 = QPushButton("Reset Cal")
        b4.clicked.connect(self.on_reset_calibration_clicked)
        cal.addWidget(b1); cal.addWidget(b2); cal.addWidget(b3); cal.addWidget(b4)
        g.addLayout(cal, 9, 0, 1, 2)

        return w

    def on_sys_gain_clicked(self):
        from PySide6.QtWidgets import QMessageBox
        reply = QMessageBox.question(
            self, 
            "Confirm System Gain Calibration",
            "System Gain Calibration requires a physical full-scale reference voltage to be applied to the active inputs.\n\n"
            "Are you sure you want to proceed?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self._send(protocol.CMD_CALIBRATE_GAIN, 0)

    def on_reset_calibration_clicked(self):
        from PySide6.QtWidgets import QMessageBox
        reply = QMessageBox.question(
            self, 
            "Confirm Calibration Reset",
            "This will reset the ADC calibration registers to factory defaults (Offset = 0x000000, Full-Scale = 0x400000).\n\n"
            "Are you sure you want to proceed?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self._send(protocol.CMD_RESET_CALIBRATION, 0)

    def _build_session_section(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        
        # Live Recording Group Box
        grp_rec = QGroupBox("Live Recording")
        rec_lay = QVBoxLayout(grp_rec)
        
        btn_row_lay = QHBoxLayout()
        btn_row_lay.setContentsMargins(0, 0, 0, 0)
        
        self.btn_start_rec = QPushButton("Start Rec")
        self.btn_start_rec.setStyleSheet("background-color: #98c379; color: black; font-weight: bold; padding: 5px;")
        self.btn_start_rec.clicked.connect(self.engine.start_recording)
        btn_row_lay.addWidget(self.btn_start_rec)
        
        self.btn_stop_rec = QPushButton("Stop Rec")
        self.btn_stop_rec.setStyleSheet("background-color: #e06c75; color: black; font-weight: bold; padding: 5px;")
        self.btn_stop_rec.clicked.connect(self.stop_recording_dialog)
        btn_row_lay.addWidget(self.btn_stop_rec)
        
        rec_lay.addLayout(btn_row_lay)
        
        self.lbl_rec_status = QLabel("Status: Not Recording")
        self.lbl_rec_status.setStyleSheet("color: #abb2bf; font-style: italic;")
        self.lbl_rec_status.setAlignment(Qt.AlignCenter)
        rec_lay.addWidget(self.lbl_rec_status)
        
        lay.addWidget(grp_rec)
        
        # Save Current Session
        btn_save = QPushButton("Save Current Data")
        btn_save.setStyleSheet("background-color: #61afef; color: black; font-weight: bold;")
        btn_save.clicked.connect(self.save_current_session)
        lay.addWidget(btn_save)
        
        # Load Session
        btn_load = QPushButton("Load Session File")
        btn_load.setStyleSheet("background-color: #d19a66; color: black; font-weight: bold;")
        btn_load.clicked.connect(self.load_session_dialog)
        lay.addWidget(btn_load)
        
        # Replay controls group
        self.replay_group = QGroupBox("Replay controls")
        rep_lay = QVBoxLayout(self.replay_group)
        
        h_ctrls = QHBoxLayout()
        self.btn_replay_play = QPushButton("Play")
        self.btn_replay_play.clicked.connect(lambda: self.toggle_replay_play())

        h_ctrls.addWidget(self.btn_replay_play)
        
        self.cb_replay_mult = QComboBox()
        self.cb_replay_mult.addItems(["0.5x", "1.0x", "2.0x", "5.0x"])
        self.cb_replay_mult.setCurrentText("1.0x")
        self.cb_replay_mult.currentTextChanged.connect(self.change_replay_speed)
        h_ctrls.addWidget(self.cb_replay_mult)
        rep_lay.addLayout(h_ctrls)
        
        self.replay_slider = QSlider(Qt.Horizontal)
        self.replay_slider.valueChanged.connect(self.slider_scrubbed)
        rep_lay.addWidget(self.replay_slider)
        
        btn_live = QPushButton("Return to Live Mode")
        btn_live.setStyleSheet("background-color: #98c379; color: black; font-weight: bold;")
        btn_live.clicked.connect(self.exit_replay_mode)
        rep_lay.addWidget(btn_live)
        
        lay.addWidget(self.replay_group)
        self.replay_group.setEnabled(False) # Disabled by default until loaded
        
        # Annotations text box
        self.txt_annotations = QTextEdit()
        self.txt_annotations.setPlaceholderText("Enter annotations here...")
        self.txt_annotations.setMaximumHeight(80)
        lay.addWidget(QLabel("Session Annotations:"))
        lay.addWidget(self.txt_annotations)
        
        return w

    def _build_graphics_section(self):
        w = QWidget()
        g = QGridLayout(w)
        
        # --- Polar / Time Plot settings ---
        btn_clr = QPushButton("Clear Polar Data")
        btn_clr.clicked.connect(self._on_clear_polar_clicked)
        g.addWidget(btn_clr, 0, 0, 1, 2)
        
        self.cb_time_window = QComboBox()
        self.cb_time_window.addItems(["0.5s", "1.0s", "2.0s", "3.0s"])
        self.cb_time_window.setCurrentText("3.0s")
        g.addWidget(QLabel("Time Window:"), 1, 0)
        g.addWidget(self.cb_time_window, 1, 1)

        # Averaging switch
        self.chk_averaging = QCheckBox("Polar Angle Averaging")
        self.chk_averaging.setChecked(False)
        self.chk_averaging.stateChanged.connect(self._on_averaging_changed)
        g.addWidget(self.chk_averaging, 2, 0, 1, 2)
        
        # Point Count Textbox
        self.txt_point_count = QLineEdit("20000")
        self.txt_point_count.setPlaceholderText("e.g. 20000")
        g.addWidget(QLabel("Data Point Count:"), 3, 0)
        g.addWidget(self.txt_point_count, 3, 1)
        
        return w

    def _on_averaging_changed(self, state):
        self.engine.polar_averaging = self.chk_averaging.isChecked()

    def _on_clear_polar_clicked(self):
        self.engine.polar_bins.fill(0.0)
        self.engine.polar_counts.fill(0)

    # Actions
    def toggle_connect(self):
        if self.conn.connected:
            self.conn.disconnect()
            self.btn_conn.setText("CONNECT")
            self.btn_conn.setStyleSheet("background-color: #61afef; font-weight: bold; color: black;")
            self.inp_ip.setEnabled(True)
            self.btn_scan.setEnabled(True)
            self.log("Disconnected.")
        else:
            self.settings.host = self.inp_ip.text()
            self.settings.port = int(self.inp_port.text())
            self.conn.host = self.settings.host
            self.conn.port = self.settings.port
            self.settings.save()
            if self.conn.connect():
                self.btn_conn.setText("DISCONNECT")
                self.btn_conn.setStyleSheet("background-color: #e06c75; font-weight: bold; color: black;")
                self.inp_ip.setEnabled(False)
                self.btn_scan.setEnabled(False)
                self.log(f"Connected to {self.settings.host}:{self.settings.port}")
                # Push all saved UI settings to firmware so it matches what is shown.
                # Without this the firmware defaults (Gain=32, Rate=7200SPS, Sinc1)
                # stay active even though the UI shows different values.
                self._push_settings_to_firmware()
            else:
                self.log("Connection failed.")

    def _push_settings_to_firmware(self):
        """Send all current UI control values to the firmware after connect."""
        import time
        # Small delay to allow HELLO handshake to complete
        time.sleep(0.05)

        # Gain
        gain_idx = self.cb_gain.currentIndex()
        self._send(protocol.CMD_SET_GAIN, gain_idx)
        pga_on = self.btn_pga.isChecked()
        if not pga_on:
            self.engine.current_gain = 1.0
        else:
            try:
                self.engine.current_gain = float(self.cb_gain.currentText().replace("x", ""))
            except ValueError:
                self.engine.current_gain = 1.0

        # Sample rate
        rate_text = self.cb_rate.currentText()
        if rate_text in RATE_MAP:
            self._send(protocol.CMD_SET_RATE, RATE_MAP[rate_text])
            self.engine.live_rate_sps = float(rate_text.split()[0])

        # Filter
        self._send(protocol.CMD_SET_FILTER, self.cb_filter.currentIndex())

        # Chop mode (use checked button id)
        chop_id = self.chop_group.checkedId()
        if chop_id >= 0:
            self._send(protocol.CMD_SET_CHOP, chop_id)

        # PGA bypass
        pga_on = self.btn_pga.isChecked()
        self._send(protocol.CMD_SET_PGA_BYPASS, 0 if pga_on else 1)

        # VBIAS
        vbias_on = self.btn_vbias.isChecked()
        self._send(protocol.CMD_SET_VBIAS, 1 if vbias_on else 0)

        # Data mode
        self._send(protocol.CMD_SET_DATA_MODE, self.cb_mode.currentIndex())

        # Input channel
        idx = self.cb_input.currentIndex()
        if 0 <= idx < len(self.input_options):
            pos = self.input_options[idx][1]
            neg = self.input_options[idx][2]
            self._send(protocol.CMD_SET_SCAN_CHANNELS, (pos << 8) | neg)

        self.log("Settings pushed to firmware.")

    def scan_network(self):
        if self.conn.connected:
            self.log("Please disconnect before scanning.")
            return
            
        self.log("Scanning for device...")
        QApplication.processEvents()
        
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            success = self.conn.auto_discover()
            if success:
                self.inp_ip.setText(str(self.conn.host))
                self.inp_port.setText(str(self.conn.port))
                self.log(f"Device found at {self.conn.host}:{self.conn.port}")
            else:
                self.log("No device found.")
        finally:
            QApplication.restoreOverrideCursor()

    def _on_set_motor_speed(self):
        try:
            val = float(self.inp_speed.text())
            if val > 25.0:
                self.log("Motor speed capped at max limit: 25.0 Hz")
                val = 25.0
                self.inp_speed.setText("25.0")
            elif val < -25.0:
                self.log("Motor speed capped at min limit: -25.0 Hz")
                val = -25.0
                self.inp_speed.setText("-25.0")
            self.settings.motor_speed = val
            self.settings.save()
            self._send(protocol.CMD_SET_MOTOR_SPEED, val)
        except ValueError:
            self.log("Invalid motor speed value.")

    def _on_stop_motor(self):
        self._send(protocol.CMD_SET_MOTOR_SPEED, 0.0)

    def _on_gain_changed(self, index):
        self._send(protocol.CMD_SET_GAIN, index)
        pga_on = self.btn_pga.isChecked()
        if not pga_on:
            self.engine.current_gain = 1.0
        else:
            try:
                self.engine.current_gain = float(self.cb_gain.currentText().replace("x", ""))
            except ValueError:
                self.engine.current_gain = 1.0

    def _on_rate_changed(self, text):
        if text in RATE_MAP:
            self.settings.rate = text
            self.settings.save()
            self._send(protocol.CMD_SET_RATE, RATE_MAP[text])
            try:
                self.engine.live_rate_sps = float(text.split()[0])
            except (ValueError, IndexError):
                pass

    def _on_mode_changed(self, index):
        self.settings.data_mode = index
        self.settings.save()
        self._send(protocol.CMD_SET_DATA_MODE, index)

    def toggle_servo(self):
        if not self.conn.connected:
            return
        self.servo_state = not self.servo_state
        self._send(protocol.CMD_SET_SERVO, 1 if self.servo_state else 0)
        if self.servo_state:
            self.btn_servo.setText("Servo Off")
            self.btn_servo.setStyleSheet("background-color: #98c379; color: black;")
        else:
            self.btn_servo.setText("Servo On")
            self.btn_servo.setStyleSheet("")
        self.log(f"Servo {'ON' if self.servo_state else 'OFF'}")

    def _toggle_pga(self):
        on = self.btn_pga.isChecked()
        self._send(protocol.CMD_SET_PGA_BYPASS, 0 if on else 1)
        self.btn_pga.setText(f"PGA: {'ON' if on else 'OFF'}")

    def _toggle_vbias(self):
        on = self.btn_vbias.isChecked()
        self._send(protocol.CMD_SET_VBIAS, 1 if on else 0)
        self.btn_vbias.setText(f"VBIAS: {'ON' if on else 'OFF'}")

    def synchronize_ui(self, config):
        """Update UI controls to match the current ADC config from hardware."""
        if not config or len(config) < 19:
            return
            
        gain, rate, pga_bypass, filt, chop, conv_mode, conv_delay, ref_rev, \
        in_pos, in_neg, ref_pos, ref_neg, vbias, intref, \
        idac1_mag, idac2_mag, idac1_mux, idac2_mux, data_mode = config
        
        # Block signals to prevent sending commands back to the hardware
        self.cb_gain.blockSignals(True)
        if 0 <= gain < self.cb_gain.count():
            self.cb_gain.setCurrentIndex(gain)
        self.cb_gain.blockSignals(False)
        # Keep engine gain value in sync for polar plot scaling
        _GAIN_VALUES = [1.0, 2.0, 4.0, 8.0, 16.0, 32.0]
        req_gain = _GAIN_VALUES[gain] if 0 <= gain < len(_GAIN_VALUES) else 1.0
        if pga_bypass != 0:
            self.engine.current_gain = 1.0
        else:
            self.engine.current_gain = req_gain
        
        self.cb_rate.blockSignals(True)
        for text, val in RATE_MAP.items():
            if val == rate:
                self.cb_rate.setCurrentText(text)
                try:
                    self.engine.live_rate_sps = float(text.split()[0])
                except (ValueError, IndexError):
                    pass
                break
        self.cb_rate.blockSignals(False)
        
        self.cb_filter.blockSignals(True)
        if 0 <= filt < self.cb_filter.count():
            self.cb_filter.setCurrentIndex(filt)
        self.cb_filter.blockSignals(False)
        
        self.cb_mode.blockSignals(True)
        if 0 <= data_mode < self.cb_mode.count():
            self.cb_mode.setCurrentIndex(data_mode)
        self.cb_mode.blockSignals(False)
        
        self.btn_pga.blockSignals(True)
        pga_on = (pga_bypass == 0)
        self.btn_pga.setChecked(pga_on)
        self.btn_pga.setText(f"PGA: {'ON' if pga_on else 'OFF'}")
        self.btn_pga.blockSignals(False)

        self.btn_vbias.blockSignals(True)
        vbias_on = (vbias != 0)
        self.btn_vbias.setChecked(vbias_on)
        self.btn_vbias.setText(f"VBIAS: {'ON' if vbias_on else 'OFF'}")
        self.btn_vbias.blockSignals(False)
        
        self.chop_group.blockSignals(True)
        for b in self.chop_group.buttons():
            val = self.chop_group.id(b)
            b.setChecked(val == chop)
        self.chop_group.blockSignals(False)
        
        self.cb_input.blockSignals(True)
        for i, opt in enumerate(self.input_options):
            if opt[1] == in_pos and opt[2] == in_neg:
                self.cb_input.setCurrentIndex(i)
                break
        self.cb_input.blockSignals(False)

        # Update VREF text
        ref_pos_names = {0: "Internal", 1: "AIN0", 2: "AIN2", 3: "AIN4", 4: "AVDD"}
        ref_neg_names = {0: "Internal", 1: "AIN1", 2: "AIN3", 3: "AIN5", 4: "AVSS"}
        pos_str = ref_pos_names.get(ref_pos, f"RefP_{ref_pos}")
        neg_str = ref_neg_names.get(ref_neg, f"RefN_{ref_neg}")
        
        if ref_pos == 0 and ref_neg == 0:
            ref_txt = "Reference: Internal (2.50V)"
        elif ref_pos == 4 and ref_neg == 4:
            ref_txt = "Reference: AVDD/AVSS (5.00V)"
        else:
            ref_txt = f"Reference: {pos_str}/{neg_str} (Ext)"
            
        if hasattr(self.mw, 'status_bar'):
            self.mw.status_bar.lbl_ref_info.setText(ref_txt)

    def stop_recording_dialog(self):
        if not self.engine.recording:
            return
            
        filepath, _ = QFileDialog.getSaveFileName(self, "Save Recorded Session", "", "MGF Session Files (*.mgf)")
        if filepath:
            self.engine.stop_recording(filepath)
            self.log(f"Recording saved to: {filepath}")
        else:
            self.engine.stop_recording()
            self.log("Recording stopped and discarded.")
            
    def save_current_session(self):
        if self.engine.recording:
            self.engine.stop_recording()
            
        filepath, _ = QFileDialog.getSaveFileName(self, "Save Session", "", "MGF Session Files (*.mgf)")
        if filepath:
            enc, adc = self.engine.get_latest_data(self.engine.count)
            if len(adc) == 0:
                self.log("No data in buffer to save.")
                return
                
            rate = self.engine.live_rate_sps
                
            annotations = self.txt_annotations.toPlainText()
            try:
                enc_pulses, step_pulses = self.engine.get_latest_pulses(self.engine.count)
                session.save_session(
                    filepath,
                    adc,
                    enc,
                    rate_sps=rate,
                    motor_speed_hz=self.engine.motor_speed,
                    annotations=annotations,
                    data_mode=self.engine.current_data_mode,
                    step_data=step_pulses,
                    enc_pulses_data=enc_pulses
                )
                self.log(f"Session data saved to: {filepath}")
            except Exception as e:
                self.log(f"Save failed: {e}")

    def load_session_dialog(self):
        filepath, _ = QFileDialog.getOpenFileName(self, "Load Session", "", "MGF Session Files (*.mgf)")
        if filepath:
            try:
                adc, enc, rate_sps, motor_speed_hz, annotations, data_mode, step, enc_pulses = session.load_session(filepath)
                self.log(f"Session loaded: {filepath}")
                self.log(f"Data count: {len(adc)}, Rate: {rate_sps} SPS, Speed: {motor_speed_hz} Hz")
                
                self.txt_annotations.setPlainText(annotations)
                
                # Load into engine
                self.engine.load_for_replay(adc, enc, rate_sps, motor_speed_hz, data_mode, step, enc_pulses)
                
                # Setup slider range
                self.replay_slider.blockSignals(True)
                self.replay_slider.setRange(0, len(adc) - 1)
                self.replay_slider.setValue(0)
                self.replay_slider.blockSignals(False)
                
                # Update UI control locks
                self.replay_group.setEnabled(True)
                self.btn_conn.setEnabled(False)
                self.inp_ip.setEnabled(False)
                self.inp_port.setEnabled(False)
                
                self.cb_mode.blockSignals(True)
                if data_mode == 1:
                    self.cb_mode.setCurrentText("Voltage (V)")
                else:
                    self.cb_mode.setCurrentText("RAW (int32)")
                self.cb_mode.blockSignals(False)
                
                self.replay_playing = False
                self.btn_replay_play.setText("Play")
                self.replay_speed_mult = 1.0
                self.cb_replay_mult.setCurrentText("1.0x")
                
                # Clear widgets
                if hasattr(self.mw, 'waterfall_widget'):
                    self.mw.waterfall_widget.clear()
                
                # Automatically navigate to the main dashboard
                if hasattr(self.mw, 'tabs'):
                    self.mw.tabs.setCurrentIndex(0)
                
            except Exception as e:
                self.log(f"Load failed: {e}")
                
    def toggle_replay_play(self, play=None):
        if not self.engine.replay_mode:
            return
        if play is None:
            self.replay_playing = not self.replay_playing
        else:
            self.replay_playing = play
            
        if self.replay_playing:
            self.btn_replay_play.setText("Pause")
        else:
            self.btn_replay_play.setText("Play")

    def change_replay_speed(self, text):
        try:
            self.replay_speed_mult = float(text.replace("x", ""))
        except ValueError:
            self.replay_speed_mult = 1.0

    def slider_scrubbed(self, value):
        if self.engine.replay_mode:
            self.engine.seek_replay(value)

    def exit_replay_mode(self):
        if self.engine.replay_mode:
            self.engine.stop_replay()
            self.replay_group.setEnabled(False)
            self.btn_conn.setEnabled(True)
            self.inp_ip.setEnabled(True)
            self.inp_port.setEnabled(True)
            self.replay_playing = False
            self.btn_replay_play.setText("Play")
            self.log("Exited replay mode. Returned to live mode.")
            if hasattr(self.mw, 'alignment_widget'):
                self.mw.alignment_widget.lbl_active_offset.setText(f"Active Offset: {self.engine.phase_offset_deg:.2f}°")

    def update_recording_status(self):
        """Update live recording duration and button states."""
        if not hasattr(self, 'lbl_rec_status'):
            return
            
        if self.engine.recording:
            count = self.engine._recording_count
            rate = self.engine.live_rate_sps
            duration = count / rate if rate > 0 else 0.0
            self.lbl_rec_status.setText(f"Recording: {duration:.1f}s ({count:,} samples)")
            self.lbl_rec_status.setStyleSheet("color: #e06c75; font-weight: bold;")
            self.btn_start_rec.setEnabled(False)
            self.btn_stop_rec.setEnabled(True)
        else:
            self.lbl_rec_status.setText("Status: Not Recording")
            self.lbl_rec_status.setStyleSheet("color: #abb2bf; font-style: italic;")
            self.btn_start_rec.setEnabled(True)
            self.btn_stop_rec.setEnabled(False)
