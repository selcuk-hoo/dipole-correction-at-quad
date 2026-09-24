"""
Rotating Coil Alignment Widget for MGF Radar V2.
Calculates the angular offset between the rotating coil and the incremental encoder,
plots raw measurement points vs encoder angle, and overlays the fitted dipole sine wave.
"""
import numpy as np
import pyqtgraph as pg
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QGroupBox, QLabel, 
    QComboBox, QPushButton, QGridLayout, QCheckBox, QSplitter,
    QLineEdit, QScrollArea, QFrame
)
from PySide6.QtCore import QTimer, Slot, Qt

from .control_panel import CollapsibleSection

class CoilAlignmentWidget(QWidget):
    def __init__(self, engine, parent=None):
        super().__init__(parent)
        self.engine = engine
        
        self.slots = {
            1: {"name": "Slot 1: Morgan A", "color": "#e06c75", "data": None, "fit": None},
            2: {"name": "Slot 2: Regular A", "color": "#e5c07b", "data": None, "fit": None},
            3: {"name": "Slot 3: Morgan B", "color": "#98c379", "data": None, "fit": None},
            4: {"name": "Slot 4: Regular B", "color": "#61afef", "data": None, "fit": None},
        }
        self.active_scan_data = None
        self.calculated_offset = 0.0
        self.fitted_amp = 0.0
        
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
            QPushButton#ApplyBtn { background-color: #e5c07b; color: black; font-weight: bold; }
            QPushButton#ApplyBtn:hover { background-color: #f0d59e; }
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
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setMinimumWidth(250)
        
        # ---- LEFT PANEL: CONTROLS & NUMERICS ----
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(5, 5, 5, 5)
        
        # Guidance Note
        grp_guidance = QGroupBox()
        lay_guide = QVBoxLayout(grp_guidance)
        lbl_guide = QLabel(
            "1. Select a channel in the Control Panel and rotate the pipe at a constant speed.\n"
            "2. Click 'Start Alignment Scan' to capture active sensor data.\n"
            "3. Click 'Capture' on a slot below to save the scan to a specific coil.\n"
            "4. Repeat for other coils to overlay and mathematically compare them."
        )
        lbl_guide.setWordWrap(True)
        lay_guide.addWidget(lbl_guide)
        self.sect_guidance = CollapsibleSection("Guide", grp_guidance)
        left_layout.addWidget(self.sect_guidance)
        
        # Settings
        grp_settings = QGroupBox()
        lay_set = QGridLayout(grp_settings)
        lay_set.addWidget(QLabel("Method:"), 0, 0)
        self.cb_method = QComboBox()
        self.cb_method.addItems(["1X Harmonic (Dipole Phase)", "Peak Voltage"])
        lay_set.addWidget(self.cb_method, 0, 1)
        
        lay_set.addWidget(QLabel("Scan Duration (s):"), 1, 0)
        self.txt_scan_duration = QLineEdit("2.0")
        lay_set.addWidget(self.txt_scan_duration, 1, 1)
        
        self.sect_settings = CollapsibleSection("Alignment Settings", grp_settings)
        self.sect_settings.content.setVisible(True)
        self.sect_settings.update_header()
        left_layout.addWidget(self.sect_settings)
        
        # Actions
        self.btn_scan = QPushButton("START ALIGNMENT SCAN")
        self.btn_scan.setObjectName("ScanBtn")
        self.btn_scan.clicked.connect(self.start_scan)
        left_layout.addWidget(self.btn_scan)
        
        # Active Scan outputs
        grp_out = QGroupBox()
        lay_out = QVBoxLayout(grp_out)
        self.lbl_calc_offset = QLabel("Calculated Offset: —")
        self.lbl_calc_offset.setStyleSheet("font-weight: bold; font-size: 11pt; color: #61afef;")
        self.lbl_fit_amp = QLabel("Fit Amplitude: —")
        self.lbl_active_offset = QLabel(f"Active Offset: {self.engine.phase_offset_deg:.2f}°")
        self.lbl_active_offset.setStyleSheet("font-weight: bold; font-size: 9pt; color: #e5c07b;")
        
        lay_out.addWidget(self.lbl_calc_offset)
        lay_out.addWidget(self.lbl_fit_amp)
        lay_out.addWidget(self.lbl_active_offset)
        
        self.btn_apply = QPushButton("Apply Active Offset as Master")
        self.btn_apply.setObjectName("ApplyBtn")
        self.btn_apply.clicked.connect(self.apply_offset)
        self.btn_apply.setEnabled(False)
        self.btn_apply.setToolTip("Sets the main coordinate rotation offset to the current active scan offset.")
        lay_out.addWidget(self.btn_apply)
        self.sect_out = CollapsibleSection("Active Scan Results", grp_out)
        self.sect_out.content.setVisible(True)
        self.sect_out.update_header()
        left_layout.addWidget(self.sect_out)

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
            cb_visible.stateChanged.connect(self.update_plots_visibility)
            row_lay.addWidget(cb_visible)
            
            # Slot Name Label
            slot_name = self.slots[idx]["name"]
            lbl_name = QLabel(f"<b>{slot_name}</b>")
            lbl_name.setFixedWidth(65)
            row_lay.addWidget(lbl_name)
            
            # Capture Button
            btn_cap = QPushButton("Capture")
            btn_cap.setFixedWidth(50)
            btn_cap.setStyleSheet("background-color: #3b4048; font-size: 8pt; padding: 4px; color: white;")
            btn_cap.clicked.connect(lambda _, s_idx=idx: self.capture_to_slot(s_idx))
            row_lay.addWidget(btn_cap)
            
            # Status Label
            lbl_status = QLabel("Empty")
            lbl_status.setStyleSheet("color: #abb2bf; font-size: 8pt;")
            row_lay.addWidget(lbl_status)
            
            lay_slots.addWidget(slot_row)
            self.slot_widgets[idx] = {
                "checkbox": cb_visible,
                "status_lbl": lbl_status,
                "cap_btn": btn_cap
            }
        self.sect_slots = CollapsibleSection("Captured Coil Slots", grp_slots)
        self.sect_slots.content.setVisible(True)
        self.sect_slots.update_header()
        left_layout.addWidget(self.sect_slots)

        # Geometric Verification Report
        grp_verify = QGroupBox()
        lay_verify = QVBoxLayout(grp_verify)
        
        self.lbl_morgan_ortho = QLabel("Morgan Orthogonality (M_B - M_A): —")
        self.lbl_regular_sym = QLabel("Regular Symmetry (S_2 - S_1): —")
        self.lbl_offset_1 = QLabel("Regular Offset 1 (S_1 - M_A): —")
        self.lbl_offset_2 = QLabel("Regular Offset 2 (S_2 - M_B): —")
        self.lbl_verdict = QLabel("Verdict: Waiting for slot data...")
        self.lbl_verdict.setStyleSheet("font-weight: bold; font-size: 11pt; color: #abb2bf;")
        
        self.lbl_morgan_ortho.setStyleSheet("font-size: 9pt;")
        self.lbl_regular_sym.setStyleSheet("font-size: 9pt;")
        self.lbl_offset_1.setStyleSheet("font-size: 9pt;")
        self.lbl_offset_2.setStyleSheet("font-size: 9pt;")
        
        lay_verify.addWidget(self.lbl_morgan_ortho)
        lay_verify.addWidget(self.lbl_regular_sym)
        lay_verify.addWidget(self.lbl_offset_1)
        lay_verify.addWidget(self.lbl_offset_2)
        
        # Reset Slots button
        btn_reset_slots = QPushButton("Clear All Captured Slots")
        btn_reset_slots.setStyleSheet("background-color: #e06c75; color: black; font-weight: bold; margin-top: 5px;")
        btn_reset_slots.clicked.connect(self.clear_all_slots)
        lay_verify.addWidget(btn_reset_slots)
        
        lay_verify.addWidget(self.lbl_verdict)
        self.sect_verify = CollapsibleSection("Geometric Verification Report", grp_verify)
        self.sect_verify.content.setVisible(True)
        self.sect_verify.update_header()
        left_layout.addWidget(self.sect_verify)
        
        left_layout.addStretch()
        scroll.setWidget(left_panel)
        self.splitter.addWidget(scroll)
        
        # ---- RIGHT PANEL: GRAPH VIEW CONTAINER ----
        graph_container = QWidget()
        graph_lay = QVBoxLayout(graph_container)
        graph_lay.setContentsMargins(0, 0, 0, 0)
        graph_lay.setSpacing(2)
        
        header_lay = QHBoxLayout()
        header_lay.setContentsMargins(5, 2, 5, 2)
        lbl_title = QLabel("Coil Signal vs. Encoder Angle")
        lbl_title.setStyleSheet("font-weight: bold; color: #abb2bf;")
        header_lay.addWidget(lbl_title)
        header_lay.addStretch()
        
        btn_shot = QPushButton("📸")
        btn_shot.setFixedWidth(30)
        btn_shot.setStyleSheet("""
            QPushButton { background-color: #3b4048; border: 1px solid #5c6370; border-radius: 3px; padding: 2px; font-size: 8pt; color: white; }
            QPushButton:hover { background-color: #61afef; color: black; font-weight: bold; }
        """)
        btn_shot.clicked.connect(self.take_alignment_screenshot)
        header_lay.addWidget(btn_shot)
        graph_lay.addLayout(header_lay)

        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setLabel('bottom', 'Encoder Angle (deg)')
        self.plot_widget.setLabel('left', 'Signal Amplitude')
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
        self.plot_widget.setXRange(0, 360)
        
        # Active scan curves (temporary, gray dashed fit)
        self.raw_scatter = self.plot_widget.plot(pen=None, symbol='o', symbolSize=3, symbolBrush='#abb2bf')
        self.fit_curve = self.plot_widget.plot(pen=pg.mkPen('#abb2bf', width=2, style=Qt.DashLine))
        
        # Quadrupole reference vertical lines
        for x_pos in [45, 135, 225, 315]:
            line = pg.InfiniteLine(pos=x_pos, angle=90, pen=pg.mkPen('#d19a66', width=1, style=Qt.DashLine))
            self.plot_widget.addItem(line)
        
        # Slot curves (4 slots * 2 curves = 8 plot curves total)
        self.slot_plots = {}
        for idx in [1, 2, 3, 4]:
            color = self.slots[idx]["color"]
            raw_curve = self.plot_widget.plot(pen=None, symbol='o', symbolSize=4, symbolBrush=color)
            fit_curve = self.plot_widget.plot(pen=pg.mkPen(color, width=2.5))
            self.slot_plots[idx] = {
                "raw": raw_curve,
                "fit": fit_curve
            }
        
        graph_lay.addWidget(self.plot_widget)
        self.splitter.addWidget(graph_container)
        self.splitter.setSizes([400, 800])
        
        # Timer for scan accumulation
        self.scan_timer = QTimer(self)
        self.scan_timer.setSingleShot(True)
        self.scan_timer.timeout.connect(self.finish_scan)
        
    def get_scan_duration(self):
        try:
            return float(self.txt_scan_duration.text())
        except ValueError:
            return 2.0

    def start_scan(self):
        duration_s = self.get_scan_duration()
        self.btn_scan.setText(f"SCANNING ({duration_s:.1f}s)...")
        self.btn_scan.setEnabled(False)
        self.btn_apply.setEnabled(False)
        
        # Reset labels
        self.lbl_calc_offset.setText("Calculated Offset: Calculating...")
        self.lbl_fit_amp.setText("Fit Amplitude: —")
        
        # Run scan timer for configured duration
        self.scan_timer.start(int(duration_s * 1000))
        
    def finish_scan(self):
        self.btn_scan.setText("START ALIGNMENT SCAN")
        self.btn_scan.setEnabled(True)
        
        duration_s = self.get_scan_duration()
        sps = getattr(self.engine, 'live_rate_sps', 2400.0)
        num_points = int(duration_s * sps * 1.05)
        num_points = max(100, num_points)
        
        # Fetch dynamic number of points based on scan duration
        enc, adc = self.engine.get_latest_data(num_points)
        if len(adc) < 100:
            self.lbl_calc_offset.setText("Calculated Offset: Insufficient data")
            return
            
        # Standardize: make sure we use raw angles (subtract active offset to get raw coordinates)
        raw_enc = (enc + self.engine.phase_offset_deg) % 360.0
        
        # Math fitting
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
            # Peak value alignment
            max_idx = np.argmax(adc)
            self.calculated_offset = raw_enc[max_idx]
            self.fitted_amp = np.max(adc) - dc
            phi_rad = np.radians(self.calculated_offset)
            
        self.lbl_calc_offset.setText(f"Calculated Offset: {self.calculated_offset:.2f}°")
        self.lbl_fit_amp.setText(f"Fit Amplitude: {self.fitted_amp:.4f}")
        
        # Enable Apply button
        self.btn_apply.setEnabled(True)
        
        # Plot active raw points
        self.raw_scatter.setData(raw_enc, adc)
        
        # Plot active fitted curve (0 to 360 deg)
        fit_x = np.linspace(0, 360, 360)
        fit_x_rad = np.radians(fit_x)
        fit_y = dc + self.fitted_amp * np.cos(fit_x_rad - phi_rad)
        self.fit_curve.setData(fit_x, fit_y)
        
        # Store active scan data for capture
        self.active_scan_data = {
            "enc": raw_enc,
            "adc": adc,
            "phase": self.calculated_offset,
            "amp": self.fitted_amp,
            "dc": dc,
            "phi_rad": phi_rad
        }
        
    def capture_to_slot(self, slot_idx):
        if self.active_scan_data is None:
            return
            
        # Store a copy of the active scan data in the target slot
        self.slots[slot_idx]["data"] = {
            "enc": self.active_scan_data["enc"].copy(),
            "adc": self.active_scan_data["adc"].copy(),
        }
        self.slots[slot_idx]["fit"] = {
            "phase": self.active_scan_data["phase"],
            "amp": self.active_scan_data["amp"],
            "dc": self.active_scan_data["dc"],
            "phi_rad": self.active_scan_data["phi_rad"]
        }
        
        # Update the row status label
        phase = self.slots[slot_idx]["fit"]["phase"]
        amp = self.slots[slot_idx]["fit"]["amp"]
        self.slot_widgets[slot_idx]["status_lbl"].setText(f"Fit: {phase:.2f}° (Amp: {amp:.4f})")
        self.slot_widgets[slot_idx]["status_lbl"].setStyleSheet("color: #98c379; font-weight: bold;")
        
        # Redraw plots and update calculations
        self.replot_slots()
        self.run_geometric_verification()

    def update_plots_visibility(self):
        self.replot_slots()

    def replot_slots(self):
        for idx in [1, 2, 3, 4]:
            slot = self.slots[idx]
            curves = self.slot_plots[idx]
            visible = self.slot_widgets[idx]["checkbox"].isChecked()
            
            if visible and slot["data"] is not None and slot["fit"] is not None:
                # Plot raw points
                curves["raw"].setData(slot["data"]["enc"], slot["data"]["adc"])
                
                # Plot fitted curve (0 to 360 deg)
                fit_x = np.linspace(0, 360, 360)
                fit_x_rad = np.radians(fit_x)
                fit_y = slot["fit"]["dc"] + slot["fit"]["amp"] * np.cos(fit_x_rad - slot["fit"]["phi_rad"])
                curves["fit"].setData(fit_x, fit_y)
            else:
                # Hide curves
                curves["raw"].setData([], [])
                curves["fit"].setData([], [])

    def clear_all_slots(self):
        for idx in [1, 2, 3, 4]:
            self.slots[idx]["data"] = None
            self.slots[idx]["fit"] = None
            self.slot_widgets[idx]["status_lbl"].setText("Empty")
            self.slot_widgets[idx]["status_lbl"].setStyleSheet("color: #abb2bf; font-weight: normal;")
            
        self.replot_slots()
        self.run_geometric_verification()

    def run_geometric_verification(self):
        f1 = self.slots[1]["fit"]
        f2 = self.slots[2]["fit"]
        f3 = self.slots[3]["fit"]
        f4 = self.slots[4]["fit"]
        
        def diff_angle(a, b):
            d = (a - b) % 360.0
            if d > 180.0:
                d -= 360.0
            return d

        errors = []
        
        # 1. Morgan Orthogonality (MB - MA = 90)
        if f1 and f3:
            diff = diff_angle(f3["phase"], f1["phase"])
            err = diff_angle(diff, 90.0)
            errors.append(abs(err))
            self.lbl_morgan_ortho.setText(f"Morgan Orthogonality (M_B - M_A): Diff {diff:.2f}° (Err {err:+.2f}°)")
            if abs(err) < 3.0:
                self.lbl_morgan_ortho.setStyleSheet("color: #98c379;")
            else:
                self.lbl_morgan_ortho.setStyleSheet("color: #e06c75;")
        else:
            self.lbl_morgan_ortho.setText("Morgan Orthogonality (M_B - M_A): —")
            self.lbl_morgan_ortho.setStyleSheet("color: #abb2bf;")
            
        # 2. Regular Symmetry (S2 - S1 = 180)
        if f2 and f4:
            diff = diff_angle(f4["phase"], f2["phase"])
            err = diff_angle(abs(diff), 180.0)
            errors.append(abs(err))
            self.lbl_regular_sym.setText(f"Regular Symmetry (S_2 - S_1): Diff {diff:.2f}° (Err {err:+.2f}°)")
            if abs(err) < 3.0:
                self.lbl_regular_sym.setStyleSheet("color: #98c379;")
            else:
                self.lbl_regular_sym.setStyleSheet("color: #e06c75;")
        else:
            self.lbl_regular_sym.setText("Regular Symmetry (S_2 - S_1): —")
            self.lbl_regular_sym.setStyleSheet("color: #abb2bf;")
            
        # 3. Regular Offset 1 (S1 - MA = 45)
        if f1 and f2:
            diff = diff_angle(f2["phase"], f1["phase"])
            err = diff_angle(diff, 45.0)
            errors.append(abs(err))
            self.lbl_offset_1.setText(f"Regular Offset 1 (S_1 - M_A): Diff {diff:.2f}° (Err {err:+.2f}°)")
            if abs(err) < 3.0:
                self.lbl_offset_1.setStyleSheet("color: #98c379;")
            else:
                self.lbl_offset_1.setStyleSheet("color: #e06c75;")
        else:
            self.lbl_offset_1.setText("Regular Offset 1 (S_1 - M_A): —")
            self.lbl_offset_1.setStyleSheet("color: #abb2bf;")
            
        # 4. Regular Offset 2 (S2 - MB = 135)
        if f3 and f4:
            diff = diff_angle(f4["phase"], f3["phase"])
            err = diff_angle(diff, 135.0)
            errors.append(abs(err))
            self.lbl_offset_2.setText(f"Regular Offset 2 (S_2 - M_B): Diff {diff:.2f}° (Err {err:+.2f}°)")
            if abs(err) < 3.0:
                self.lbl_offset_2.setStyleSheet("color: #98c379;")
            else:
                self.lbl_offset_2.setStyleSheet("color: #e06c75;")
        else:
            self.lbl_offset_2.setText("Regular Offset 2 (S_2 - M_B): —")
            self.lbl_offset_2.setStyleSheet("color: #abb2bf;")
            
        # Overall Verdict
        all_captured = (f1 is not None) and (f2 is not None) and (f3 is not None) and (f4 is not None)
        if all_captured:
            max_err = max(errors)
            if max_err < 3.0:
                self.lbl_verdict.setText(f"Verdict: PASS (Max Err: {max_err:.2f}°)")
                self.lbl_verdict.setStyleSheet("font-weight: bold; font-size: 11pt; color: #98c379;")
            else:
                self.lbl_verdict.setText(f"Verdict: FAIL (Max Err: {max_err:.2f}°)")
                self.lbl_verdict.setStyleSheet("font-weight: bold; font-size: 11pt; color: #e06c75;")
        else:
            captured_count = sum(1 for f in [f1, f2, f3, f4] if f is not None)
            self.lbl_verdict.setText(f"Verdict: Waiting for slot data ({captured_count}/4 captured)")
            self.lbl_verdict.setStyleSheet("font-weight: bold; font-size: 11pt; color: #abb2bf;")
            
    def apply_offset(self):
        self.engine.phase_offset_deg = (315.0 - self.calculated_offset) % 360.0
        self.lbl_active_offset.setText(f"Active Offset: {self.engine.phase_offset_deg:.2f}°")
        self.btn_apply.setEnabled(False)
        
        # Clear active plots to indicate alignment is committed
        self.raw_scatter.setData([], [])
        self.fit_curve.setData([], [])
        self.lbl_calc_offset.setText("Calculated Offset: Committed")
        
    def reset_offset(self):
        self.engine.phase_offset_deg = 0.0
        self.calculated_offset = 0.0
        self.fitted_amp = 0.0
        self.active_scan_data = None
        self.lbl_calc_offset.setText("Calculated Offset: —")
        self.lbl_fit_amp.setText("Fit Amplitude: —")
        self.btn_apply.setEnabled(False)
        self.raw_scatter.setData([], [])
        self.fit_curve.setData([], [])

    def take_alignment_screenshot(self):
        import os
        from datetime import datetime
        os.makedirs(os.path.join("outputs", "screenshots"), exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = os.path.join("outputs", "screenshots", f"coil_alignment_{ts}.png")
        pixmap = self.plot_widget.grab()
        pixmap.save(filepath)
