"""
Magnetic Analysis Widget for MGF Radar V2.
Calculates Cartesian field components Bx and By from rotating coil measurements
and visualizes the field vector on a guide-circle compass plot.
"""
import numpy as np
import pyqtgraph as pg
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QGroupBox, QLabel, 
    QComboBox, QPushButton, QGridLayout, QLineEdit, QSplitter,
    QScrollArea, QFrame, QCheckBox
)
from PySide6.QtCore import QTimer, Slot, Qt

from .control_panel import CollapsibleSection

class MagneticAnalysisWidget(QWidget):
    def __init__(self, engine, parent=None):
        super().__init__(parent)
        self.engine = engine
        
        self.calculated_offset = 0.0
        self.fitted_amp = 0.0
        self.Bx = 0.0
        self.By = 0.0
        self.B_mag = 0.0
        
        # Active scan data for capture
        self.active_speed = 0.0
        self.active_v_amp = 0.0
        self.active_phi_rad = 0.0
        self.active_raw_enc = np.array([])
        self.active_adc_centered = np.array([])
        
        self.slots = {
            1: {"name": "Slot 1", "color": "#e06c75", "data": None},
            2: {"name": "Slot 2", "color": "#e5c07b", "data": None},
            3: {"name": "Slot 3", "color": "#98c379", "data": None},
            4: {"name": "Slot 4", "color": "#61afef", "data": None},
        }
        
        self.setStyleSheet("""
            QGroupBox { border: 1px solid #5c6370; border-radius: 5px; margin-top: 12px; padding-top: 15px; font-weight: bold; }
            QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top left; top: 0px; left: 10px; color: #61afef; background-color: #282c34; padding: 0 5px; }
            QLabel { font-weight: normal; }
            QLineEdit { background-color: #3b4048; border: 1px solid #5c6370; padding: 5px; color: white; border-radius: 3px; font-family: Consolas; }
            QComboBox { background-color: #3b4048; border: 1px solid #5c6370; padding: 5px; color: white; border-radius: 3px; }
            QPushButton { background-color: #616a6b; border: none; padding: 8px; border-radius: 4px; color: white; }
            QPushButton:hover { background-color: #7f8c8d; }
            QPushButton#ScanBtn { background-color: #61afef; color: black; font-weight: bold; padding: 10px; }
            QPushButton#ScanBtn:hover { background-color: #8cc3f2; }
            QLabel#ValueLbl { font-family: 'Consolas', monospace; font-size: 10pt; color: #abb2bf; }
            QLabel#ResultLbl { font-family: 'Consolas', monospace; font-size: 11pt; font-weight: bold; color: #98c379; }
        """)
        
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(5, 5, 5, 5)
        
        self.splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(self.splitter)
        
        # ---- LEFT PANEL SCROLL AREA ----
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setMinimumWidth(250)
        
        # ---- LEFT PANEL: CONTROLS & NUMERICS ----
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(5, 5, 5, 5)
        
        # Guide
        grp_guide = QGroupBox()
        lay_guide = QVBoxLayout(grp_guide)
        lbl_guide = QLabel(
            "1. Enter your rotating coil turns and loop dimensions.\n"
            "2. Spin the motor at a constant speed (Hz).\n"
            "3. Click 'Start Magnetic Scan' to capture signal metrics.\n"
            "4. The system fits the dipole component to calculate the physical field vectors Bx and By."
        )
        lbl_guide.setWordWrap(True)
        lay_guide.addWidget(lbl_guide)
        self.sect_guide = CollapsibleSection("Guide", grp_guide)
        left_layout.addWidget(self.sect_guide)
        
        # Coil Geometry Settings
        grp_geom = QGroupBox()
        lay_geom = QGridLayout(grp_geom)
        
        lay_geom.addWidget(QLabel("Turns (N):"), 0, 0)
        self.txt_turns = QLineEdit("100")
        self.txt_turns.textChanged.connect(self.update_area)
        lay_geom.addWidget(self.txt_turns, 0, 1)
        
        lay_geom.addWidget(QLabel("Loop Length (mm):"), 1, 0)
        self.txt_length = QLineEdit("50")
        self.txt_length.textChanged.connect(self.update_area)
        lay_geom.addWidget(self.txt_length, 1, 1)
        
        lay_geom.addWidget(QLabel("Loop Width (mm):"), 2, 0)
        self.txt_width = QLineEdit("20")
        self.txt_width.textChanged.connect(self.update_area)
        lay_geom.addWidget(self.txt_width, 2, 1)
        
        lay_geom.addWidget(QLabel("Coil Area (A):"), 3, 0)
        self.lbl_area = QLabel("0.001000 m²")
        self.lbl_area.setStyleSheet("font-family: Consolas; font-weight: bold; color: #e5c07b;")
        lay_geom.addWidget(self.lbl_area, 3, 1)
        
        self.sect_geom = CollapsibleSection("Coil Parameters", grp_geom)
        self.sect_geom.content.setVisible(True)
        self.sect_geom.update_header()
        left_layout.addWidget(self.sect_geom)
        
        # Measurement Config
        grp_settings = QGroupBox()
        lay_set = QGridLayout(grp_settings)
        lay_set.addWidget(QLabel("Method:"), 0, 0)
        self.cb_method = QComboBox()
        self.cb_method.addItems(["1X Harmonic (Dipole Phase)", "Peak Voltage"])
        lay_set.addWidget(self.cb_method, 0, 1)
        
        lay_set.addWidget(QLabel("Scan Duration (s):"), 1, 0)
        self.txt_scan_duration = QLineEdit("2.0")
        lay_set.addWidget(self.txt_scan_duration, 1, 1)
        
        self.sect_settings = CollapsibleSection("Measurement Config", grp_settings)
        self.sect_settings.content.setVisible(True)
        self.sect_settings.update_header()
        left_layout.addWidget(self.sect_settings)
        
        # Start Scan Button
        self.btn_scan = QPushButton("START MAGNETIC SCAN")
        self.btn_scan.setObjectName("ScanBtn")
        self.btn_scan.clicked.connect(self.start_scan)
        left_layout.addWidget(self.btn_scan)
        
        # Signal Metrics Results
        grp_sig_out = QGroupBox()
        lay_sig_out = QGridLayout(grp_sig_out)
        
        lay_sig_out.addWidget(QLabel("Motor Speed (f):"), 0, 0)
        self.lbl_speed = QLabel("— Hz")
        self.lbl_speed.setObjectName("ValueLbl")
        lay_sig_out.addWidget(self.lbl_speed, 0, 1)
        
        lay_sig_out.addWidget(QLabel("Fitted Amplitude (V0):"), 1, 0)
        self.lbl_fit_amp = QLabel("— V")
        self.lbl_fit_amp.setObjectName("ValueLbl")
        lay_sig_out.addWidget(self.lbl_fit_amp, 1, 1)
        
        lay_sig_out.addWidget(QLabel("Fitted Phase (phi):"), 2, 0)
        self.lbl_fit_phase = QLabel("— °")
        self.lbl_fit_phase.setObjectName("ValueLbl")
        lay_sig_out.addWidget(self.lbl_fit_phase, 2, 1)
        
        self.lbl_active_offset = QLabel(f"Active Offset: {self.engine.phase_offset_deg:.2f}°")
        self.lbl_active_offset.setStyleSheet("font-weight: bold; font-size: 9pt; color: #abb2bf;")
        lay_sig_out.addWidget(self.lbl_active_offset, 3, 0, 1, 2)
        
        self.sect_sig_out = CollapsibleSection("Signal Metrics", grp_sig_out)
        self.sect_sig_out.content.setVisible(True)
        self.sect_sig_out.update_header()
        left_layout.addWidget(self.sect_sig_out)
        
        # Calculated Field Strengths
        grp_field = QGroupBox()
        lay_field = QGridLayout(grp_field)
        
        lay_field.addWidget(QLabel("Normal Component By:"), 0, 0)
        self.lbl_by = QLabel("—")
        self.lbl_by.setObjectName("ResultLbl")
        lay_field.addWidget(self.lbl_by, 0, 1)
        
        lay_field.addWidget(QLabel("Skew Component Bx:"), 1, 0)
        self.lbl_bx = QLabel("—")
        self.lbl_bx.setObjectName("ResultLbl")
        lay_field.addWidget(self.lbl_bx, 1, 1)
        
        lay_field.addWidget(QLabel("Total Field |B|:"), 2, 0)
        self.lbl_bmag = QLabel("—")
        self.lbl_bmag.setObjectName("ResultLbl")
        self.lbl_bmag.setStyleSheet("font-family: 'Consolas', monospace; font-size: 11pt; font-weight: bold; color: #61afef;")
        lay_field.addWidget(self.lbl_bmag, 2, 1)
        
        self.sect_field = CollapsibleSection("Calculated Field Vectors", grp_field)
        self.sect_field.content.setVisible(True)
        self.sect_field.update_header()
        left_layout.addWidget(self.sect_field)
        
        # Captured slots manager
        grp_slots = QGroupBox()
        lay_slots = QVBoxLayout(grp_slots)
        
        self.slot_widgets = {}
        for idx in [1, 2, 3, 4]:
            slot_row = QWidget()
            row_lay = QHBoxLayout(slot_row)
            row_lay.setContentsMargins(0, 2, 0, 2)
            
            # Checkbox to toggle visibility
            cb_visible = QCheckBox()
            cb_visible.setChecked(True)
            cb_visible.stateChanged.connect(self.replot_slots)
            row_lay.addWidget(cb_visible)
            
            # Slot Name Label
            slot_name = self.slots[idx]["name"]
            lbl_name = QLabel(f"<b>{slot_name}</b>")
            lbl_name.setFixedWidth(50)
            row_lay.addWidget(lbl_name)
            
            # Capture Button
            btn_cap = QPushButton("Capture")
            btn_cap.setFixedWidth(50)
            btn_cap.setStyleSheet("background-color: #3b4048; font-size: 8pt; padding: 4px; color: white;")
            btn_cap.clicked.connect(lambda _, s_idx=idx: self.capture_to_slot(s_idx))
            row_lay.addWidget(btn_cap)
            
            # Clear Button
            btn_clr = QPushButton("Clear")
            btn_clr.setFixedWidth(40)
            btn_clr.setStyleSheet("background-color: #3b4048; font-size: 8pt; padding: 4px; color: white;")
            btn_clr.clicked.connect(lambda _, s_idx=idx: self.clear_slot(s_idx))
            row_lay.addWidget(btn_clr)
            
            # Status Label
            lbl_status = QLabel("Empty")
            lbl_status.setStyleSheet("color: #abb2bf; font-size: 8pt;")
            row_lay.addWidget(lbl_status)
            
            lay_slots.addWidget(slot_row)
            self.slot_widgets[idx] = {
                "checkbox": cb_visible,
                "status_lbl": lbl_status,
                "cap_btn": btn_cap,
                "clr_btn": btn_clr
            }
        
        btn_clear_all = QPushButton("Clear All Slots")
        btn_clear_all.setStyleSheet("background-color: #e06c75; color: black; font-weight: bold; margin-top: 5px; padding: 4px;")
        btn_clear_all.clicked.connect(self.clear_all_slots)
        lay_slots.addWidget(btn_clear_all)
        self.sect_slots = CollapsibleSection("Captured Magnetic Slots", grp_slots)
        self.sect_slots.content.setVisible(True)
        self.sect_slots.update_header()
        left_layout.addWidget(self.sect_slots)

        # Selected Vector Details
        grp_details = QGroupBox()
        lay_details = QGridLayout(grp_details)
        
        lay_details.addWidget(QLabel("Source:"), 0, 0)
        self.cb_details_source = QComboBox()
        self.cb_details_source.addItems(["Active Scan", "Slot 1", "Slot 2", "Slot 3", "Slot 4"])
        self.cb_details_source.currentTextChanged.connect(self.display_selected_details)
        lay_details.addWidget(self.cb_details_source, 0, 1)
        
        lay_details.addWidget(QLabel("By (Normal):"), 1, 0)
        self.lbl_det_by = QLabel("—")
        self.lbl_det_by.setStyleSheet("font-family: Consolas; font-weight: bold; color: #abb2bf;")
        lay_details.addWidget(self.lbl_det_by, 1, 1)
        
        lay_details.addWidget(QLabel("Bx (Skew):"), 2, 0)
        self.lbl_det_bx = QLabel("—")
        self.lbl_det_bx.setStyleSheet("font-family: Consolas; font-weight: bold; color: #abb2bf;")
        lay_details.addWidget(self.lbl_det_bx, 2, 1)
        
        lay_details.addWidget(QLabel("Total |B|:"), 3, 0)
        self.lbl_det_bmag = QLabel("—")
        self.lbl_det_bmag.setStyleSheet("font-family: Consolas; font-weight: bold; color: #61afef;")
        lay_details.addWidget(self.lbl_det_bmag, 3, 1)
        
        lay_details.addWidget(QLabel("Field Angle:"), 4, 0)
        self.lbl_det_angle = QLabel("—")
        self.lbl_det_angle.setStyleSheet("font-family: Consolas; font-weight: bold; color: #e5c07b;")
        lay_details.addWidget(self.lbl_det_angle, 4, 1)
        
        lay_details.addWidget(QLabel("Fit Amp (V0):"), 5, 0)
        self.lbl_det_amp = QLabel("—")
        self.lbl_det_amp.setStyleSheet("font-family: Consolas; color: #abb2bf;")
        lay_details.addWidget(self.lbl_det_amp, 5, 1)
        
        lay_details.addWidget(QLabel("Speed (f):"), 6, 0)
        self.lbl_det_speed = QLabel("—")
        self.lbl_det_speed.setStyleSheet("font-family: Consolas; color: #abb2bf;")
        lay_details.addWidget(self.lbl_det_speed, 6, 1)
        
        self.sect_details = CollapsibleSection("Selected Vector Details", grp_details)
        self.sect_details.content.setVisible(True)
        self.sect_details.update_header()
        left_layout.addWidget(self.sect_details)
        
        left_layout.addStretch()
        scroll.setWidget(left_panel)
        self.splitter.addWidget(scroll)
        
        # ---- RIGHT PANEL: SPLIT GRAPH VIEW ----
        right_splitter = QSplitter(Qt.Vertical)
        
        # 1. Signal Plot Container
        container_signal = QWidget()
        lay_sig_cont = QVBoxLayout(container_signal)
        lay_sig_cont.setContentsMargins(0, 0, 0, 0)
        lay_sig_cont.setSpacing(2)
        
        header_sig = QHBoxLayout()
        header_sig.setContentsMargins(5, 2, 5, 2)
        lbl_sig_title = QLabel("Coil Signal vs. Encoder Angle")
        lbl_sig_title.setStyleSheet("font-weight: bold; color: #abb2bf;")
        header_sig.addWidget(lbl_sig_title)
        header_sig.addStretch()
        
        btn_sig_shot = QPushButton("📸")
        btn_sig_shot.setFixedWidth(30)
        btn_sig_shot.setStyleSheet("""
            QPushButton { background-color: #3b4048; border: 1px solid #5c6370; border-radius: 3px; padding: 2px; font-size: 8pt; color: white; }
            QPushButton:hover { background-color: #61afef; color: black; font-weight: bold; }
        """)
        btn_sig_shot.clicked.connect(self.take_signal_screenshot)
        header_sig.addWidget(btn_sig_shot)
        lay_sig_cont.addLayout(header_sig)

        self.plot_signal = pg.PlotWidget()
        self.plot_signal.setLabel('bottom', 'Encoder Angle (deg)')
        self.plot_signal.setLabel('left', 'Signal Voltage (V)')
        self.plot_signal.showGrid(x=True, y=True, alpha=0.3)
        self.plot_signal.setXRange(0, 360)
        
        self.raw_scatter = self.plot_signal.plot(pen=None, symbol='o', symbolSize=3.5, symbolBrush='#abb2bf')
        self.fit_curve = self.plot_signal.plot(pen=pg.mkPen('#98c379', width=2))
        
        # Quadrupole reference vertical lines
        for x_pos in [45, 135, 225, 315]:
            line = pg.InfiniteLine(pos=x_pos, angle=90, pen=pg.mkPen('#d19a66', width=1, style=Qt.DashLine))
            self.plot_signal.addItem(line)
        
        self.slot_signal_plots = {}
        for idx in [1, 2, 3, 4]:
            color = self.slots[idx]["color"]
            raw_p = self.plot_signal.plot(pen=None, symbol='o', symbolSize=3.5, symbolBrush=color)
            fit_p = self.plot_signal.plot(pen=pg.mkPen(color, width=2))
            self.slot_signal_plots[idx] = {"raw": raw_p, "fit": fit_p}
            
        lay_sig_cont.addWidget(self.plot_signal)
        right_splitter.addWidget(container_signal)
        
        # 2. Vector Compass Plot Container
        container_compass = QWidget()
        lay_comp_cont = QVBoxLayout(container_compass)
        lay_comp_cont.setContentsMargins(0, 0, 0, 0)
        lay_comp_cont.setSpacing(2)
        
        header_comp = QHBoxLayout()
        header_comp.setContentsMargins(5, 2, 5, 2)
        lbl_comp_title = QLabel("Magnetic Field Vector Compass (Bx, By)")
        lbl_comp_title.setStyleSheet("font-weight: bold; color: #abb2bf;")
        header_comp.addWidget(lbl_comp_title)
        header_comp.addStretch()
        
        btn_comp_shot = QPushButton("📸")
        btn_comp_shot.setFixedWidth(30)
        btn_comp_shot.setStyleSheet("""
            QPushButton { background-color: #3b4048; border: 1px solid #5c6370; border-radius: 3px; padding: 2px; font-size: 8pt; color: white; }
            QPushButton:hover { background-color: #61afef; color: black; font-weight: bold; }
        """)
        btn_comp_shot.clicked.connect(self.take_compass_screenshot)
        header_comp.addWidget(btn_comp_shot)
        lay_comp_cont.addLayout(header_comp)

        self.plot_compass = pg.PlotWidget()
        self.plot_compass.setLabel('bottom', 'Skew Field Bx (mT)')
        self.plot_compass.setLabel('left', 'Normal Field By (mT)')
        self.plot_compass.showGrid(x=True, y=True, alpha=0.3)
        self.plot_compass.setAspectLocked(True)
        
        # Concentric circle guides
        self.guide_circles = []
        for _ in range(4):
            circle = self.plot_compass.plot(pen=pg.mkPen('#4b5263', style=Qt.DashLine, width=1))
            self.guide_circles.append(circle)
            
        # Origin axis lines
        self.plot_compass.plot([0, 0], [-1000, 1000], pen=pg.mkPen('#3b4048', width=1))
        self.plot_compass.plot([-1000, 1000], [0, 0], pen=pg.mkPen('#3b4048', width=1))
        
        # Field Vector shaft and tip
        self.vector_line = self.plot_compass.plot([0, 0], [0, 0], pen=pg.mkPen('#61afef', width=3))
        self.vector_tip = self.plot_compass.plot([0], [0], pen=None, symbol='o', symbolSize=8, symbolBrush='#61afef')
        
        self.slot_compass_plots = {}
        for idx in [1, 2, 3, 4]:
            color = self.slots[idx]["color"]
            v_line = self.plot_compass.plot([0, 0], [0, 0], pen=pg.mkPen(color, width=2))
            v_tip = self.plot_compass.plot([0], [0], pen=None, symbol='o', symbolSize=6, symbolBrush=color)
            self.slot_compass_plots[idx] = {"line": v_line, "tip": v_tip}
        
        lay_comp_cont.addWidget(self.plot_compass)
        right_splitter.addWidget(container_compass)
        right_splitter.setSizes([450, 450])
        self.splitter.addWidget(right_splitter)
        self.splitter.setSizes([400, 800])
        
        # Scan single shot timer
        self.scan_timer = QTimer(self)
        self.scan_timer.setSingleShot(True)
        self.scan_timer.timeout.connect(self.finish_scan)
        
    def update_area(self):
        try:
            L = float(self.txt_length.text())
            W = float(self.txt_width.text())
            area = L * W * 1e-6
            self.lbl_area.setText(f"{area:.6f} m²")
        except ValueError:
            self.lbl_area.setText("Invalid inputs")
            
    def get_scan_duration(self):
        try:
            return float(self.txt_scan_duration.text())
        except ValueError:
            return 2.0

    def start_scan(self):
        duration_s = self.get_scan_duration()
        self.btn_scan.setText(f"SCANNING ({duration_s:.1f}s)...")
        self.btn_scan.setEnabled(False)
        self.lbl_speed.setText("Scanning...")
        self.lbl_fit_amp.setText("Scanning...")
        self.lbl_fit_phase.setText("Scanning...")
        self.scan_timer.start(int(duration_s * 1000))
        
    def finish_scan(self):
        self.btn_scan.setText("START MAGNETIC SCAN")
        self.btn_scan.setEnabled(True)
        
        duration_s = self.get_scan_duration()
        sps = getattr(self.engine, 'live_rate_sps', 2400.0)
        num_points = int(duration_s * sps * 1.05)
        num_points = max(100, num_points)
        
        enc, adc = self.engine.get_latest_data(num_points)
        if len(adc) < 100:
            self.lbl_speed.setText("Insufficient data")
            return
            
        # Retrieve actual parameters
        try:
            N = float(self.txt_turns.text())
            L = float(self.txt_length.text())
            W = float(self.txt_width.text())
        except ValueError:
            self.lbl_speed.setText("Error: Parameter inputs must be numeric")
            return
            
        area = L * W * 1e-6
        motor_speed = max(0.01, abs(self.engine.motor_speed))
        self.lbl_speed.setText(f"{motor_speed:.2f} Hz")
        
        # Standardize angle: subtract active offset to get raw coordinates
        raw_enc = (enc + self.engine.phase_offset_deg) % 360.0
        
        dc = np.mean(adc)
        rads = np.radians(raw_enc)
        y_centered = adc - dc
        
        method = self.cb_method.currentText()
        if "1X Harmonic" in method:
            # Fourier integration of first harmonic
            a1 = np.sum(y_centered * np.cos(rads))
            b1 = np.sum(y_centered * np.sin(rads))
            phi_rad = np.arctan2(b1, a1)
            self.calculated_offset = np.degrees(phi_rad) % 360.0
            self.fitted_amp = 2.0 * np.sqrt(a1**2 + b1**2) / len(adc)
        else:
            max_idx = np.argmax(adc)
            self.calculated_offset = raw_enc[max_idx]
            self.fitted_amp = np.max(adc) - dc
            phi_rad = np.radians(self.calculated_offset)
            
        # If signal is RAW counts, convert to Volts using hardware gain and VREF
        v_amp = self.fitted_amp
        if self.engine.current_data_mode == 0:  # RAW mode
            vref = getattr(self.engine, 'current_vref', 2.5)
            gain = getattr(self.engine, 'current_gain', 1.0)
            v_amp = self.fitted_amp * (vref / (gain * 2147483647.0))
            
        self.lbl_fit_amp.setText(f"{v_amp:.6f} V")
        self.lbl_fit_phase.setText(f"{self.calculated_offset:.2f}°")
        
        # Plot raw centered signals and fitted waveform
        self.raw_scatter.setData(raw_enc, adc - dc)
        fit_x = np.linspace(0, 360, 360)
        fit_x_rad = np.radians(fit_x)
        # Reconstruct voltage wave fitted centered around 0
        fit_y = self.fitted_amp * np.cos(fit_x_rad - phi_rad)
        self.fit_curve.setData(fit_x, fit_y)
        
        # Calculate Bx and By (T)
        omega = 2.0 * np.pi * motor_speed
        
        # Bx = (v_amp * sin(phi)) / (N * A * omega)
        # By = - (v_amp * cos(phi)) / (N * A * omega)
        # B_mag = v_amp / (N * A * omega)
        self.Bx = (v_amp * np.sin(phi_rad)) / (N * area * omega)
        self.By = - (v_amp * np.cos(phi_rad)) / (N * area * omega)
        self.B_mag = np.sqrt(self.Bx**2 + self.By**2)
        
        # Format outputs in mT for labels
        self.lbl_bx.setText(f"{self.Bx * 1e3:+.4f} mT\n({self.Bx * 1e6:+.1f} µT)")
        self.lbl_by.setText(f"{self.By * 1e3:+.4f} mT\n({self.By * 1e6:+.1f} µT)")
        self.lbl_bmag.setText(f"{self.B_mag * 1e3:.4f} mT\n({self.B_mag * 1e6:.1f} µT)\n[{self.B_mag:.6f} T]")
        
        # Update compass plot (in mT)
        Bx_mT = self.Bx * 1e3
        By_mT = self.By * 1e3
        Bmag_mT = self.B_mag * 1e3
        
        self.vector_line.setData([0, Bx_mT], [0, By_mT])
        self.vector_tip.setData([Bx_mT], [By_mT])
        
        # Rescale compass guides based on total field magnitude
        limit = max(0.01, Bmag_mT * 1.3)
        self.plot_compass.setXRange(-limit, limit)
        self.plot_compass.setYRange(-limit, limit)
        
        theta_guide = np.linspace(0, 2*np.pi, 100)
        for idx_g, frac in enumerate([0.25, 0.5, 0.75, 1.0]):
            r = limit * frac
            cx = r * np.cos(theta_guide)
            cy = r * np.sin(theta_guide)
            self.guide_circles[idx_g].setData(cx, cy)
            
        # Also store these active variables for capture:
        self.active_speed = motor_speed
        self.active_v_amp = v_amp
        self.active_phi_rad = phi_rad
        self.active_raw_enc = raw_enc
        self.active_adc_centered = adc - dc
        
        # Refresh details view if selected
        self.display_selected_details(self.cb_details_source.currentText())

    def replot_slots(self):
        for idx in [1, 2, 3, 4]:
            slot = self.slots[idx]
            visible = self.slot_widgets[idx]["checkbox"].isChecked()
            
            if visible and slot["data"] is not None:
                d = slot["data"]
                # Plot signal
                self.slot_signal_plots[idx]["raw"].setData(d["raw_enc"], d["adc_centered"])
                self.slot_signal_plots[idx]["fit"].setData(d["fit_x"], d["fit_y"])
                # Plot compass vector
                Bx_mT = d["Bx"] * 1e3
                By_mT = d["By"] * 1e3
                self.slot_compass_plots[idx]["line"].setData([0, Bx_mT], [0, By_mT])
                self.slot_compass_plots[idx]["tip"].setData([Bx_mT], [By_mT])
            else:
                self.slot_signal_plots[idx]["raw"].setData([], [])
                self.slot_signal_plots[idx]["fit"].setData([], [])
                self.slot_compass_plots[idx]["line"].setData([0, 0], [0, 0])
                self.slot_compass_plots[idx]["tip"].setData([], [])

    def capture_to_slot(self, slot_idx):
        if not hasattr(self, 'Bx') or self.B_mag == 0.0:
            return
            
        fit_x = np.linspace(0, 360, 360)
        fit_x_rad = np.radians(fit_x)
        # Reconstruct fit curve
        fit_y = self.fitted_amp * np.cos(fit_x_rad - self.active_phi_rad)
        
        self.slots[slot_idx]["data"] = {
            "Bx": self.Bx,
            "By": self.By,
            "B_mag": self.B_mag,
            "phi": self.calculated_offset,
            "motor_speed": self.active_speed,
            "fitted_amp": self.active_v_amp,
            "raw_enc": self.active_raw_enc,
            "adc_centered": self.active_adc_centered,
            "fit_x": fit_x,
            "fit_y": fit_y,
        }
        
        Bmag_mT = self.B_mag * 1e3
        self.slot_widgets[slot_idx]["status_lbl"].setText(f"{Bmag_mT:.2f} mT @ {self.active_speed:.1f}Hz")
        self.slot_widgets[slot_idx]["status_lbl"].setStyleSheet(f"color: {self.slots[slot_idx]['color']}; font-weight: bold;")
        
        self.replot_slots()
        
        # If currently selecting this slot in Details, refresh it
        if self.cb_details_source.currentText() == f"Slot {slot_idx}":
            self.display_selected_details(f"Slot {slot_idx}")

    def clear_slot(self, slot_idx):
        self.slots[slot_idx]["data"] = None
        self.slot_widgets[slot_idx]["status_lbl"].setText("Empty")
        self.slot_widgets[slot_idx]["status_lbl"].setStyleSheet("color: #abb2bf; font-weight: normal;")
        
        self.replot_slots()
        
        # If currently selecting this slot in Details, refresh it
        if self.cb_details_source.currentText() == f"Slot {slot_idx}":
            self.display_selected_details(f"Slot {slot_idx}")

    def clear_all_slots(self):
        for idx in [1, 2, 3, 4]:
            self.clear_slot(idx)

    def display_selected_details(self, source_text):
        if source_text == "Active Scan":
            if not hasattr(self, 'Bx') or self.B_mag == 0.0:
                self.lbl_det_by.setText("—")
                self.lbl_det_bx.setText("—")
                self.lbl_det_bmag.setText("—")
                self.lbl_det_angle.setText("—")
                self.lbl_det_amp.setText("—")
                self.lbl_det_speed.setText("—")
            else:
                angle_deg = np.degrees(np.arctan2(self.By, self.Bx)) % 360.0
                self.lbl_det_by.setText(f"{self.By * 1e3:+.4f} mT")
                self.lbl_det_bx.setText(f"{self.Bx * 1e3:+.4f} mT")
                self.lbl_det_bmag.setText(f"{self.B_mag * 1e3:.4f} mT")
                self.lbl_det_angle.setText(f"{angle_deg:.2f}°")
                self.lbl_det_amp.setText(f"{self.active_v_amp:.6f} V")
                self.lbl_det_speed.setText(f"{self.active_speed:.2f} Hz")
        else:
            try:
                slot_idx = int(source_text.split()[-1])
                slot = self.slots[slot_idx]
            except (ValueError, IndexError):
                return
                
            if slot["data"] is None:
                self.lbl_det_by.setText("—")
                self.lbl_det_bx.setText("—")
                self.lbl_det_bmag.setText("—")
                self.lbl_det_angle.setText("—")
                self.lbl_det_amp.setText("—")
                self.lbl_det_speed.setText("—")
            else:
                d = slot["data"]
                angle_deg = np.degrees(np.arctan2(d["By"], d["Bx"])) % 360.0
                self.lbl_det_by.setText(f"{d['By'] * 1e3:+.4f} mT")
                self.lbl_det_bx.setText(f"{d['Bx'] * 1e3:+.4f} mT")
                self.lbl_det_bmag.setText(f"{d['B_mag'] * 1e3:.4f} mT")
                self.lbl_det_angle.setText(f"{angle_deg:.2f}°")
                self.lbl_det_amp.setText(f"{d['fitted_amp']:.6f} V")
                self.lbl_det_speed.setText(f"{d['motor_speed']:.2f} Hz")

    def take_signal_screenshot(self):
        import os
        from datetime import datetime
        os.makedirs(os.path.join("outputs", "screenshots"), exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = os.path.join("outputs", "screenshots", f"magnetic_signal_{ts}.png")
        pixmap = self.plot_signal.grab()
        pixmap.save(filepath)

    def take_compass_screenshot(self):
        import os
        from datetime import datetime
        os.makedirs(os.path.join("outputs", "screenshots"), exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = os.path.join("outputs", "screenshots", f"magnetic_vector_{ts}.png")
        pixmap = self.plot_compass.grab()
        pixmap.save(filepath)
