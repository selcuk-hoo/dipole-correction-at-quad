"""
Timing and Telemetry Analysis Widget for MGF Radar V2.
Plots stepper motor step count and encoder counts over time.
Provides both cumulative counters and instantaneous rate (ticks/s) plots.
"""
import numpy as np
import pyqtgraph as pg
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QGroupBox, QLabel, 
    QComboBox, QPushButton, QGridLayout, QLineEdit, QSplitter,
    QScrollArea, QFrame
)
from PySide6.QtCore import Qt

from .control_panel import CollapsibleSection

def smooth_pulses(y):
    n_len = len(y)
    if n_len < 2:
        return y.copy() if hasattr(y, 'copy') else y
    
    # Find indices where value changes
    change_indices = np.where(np.diff(y) != 0)[0] + 1
    if len(change_indices) == 0:
        return np.full_like(y, y[0], dtype=np.float64)
    
    # Create output array
    y_smooth = np.zeros_like(y, dtype=np.float64)
    
    # First point is index 0, followed by change points
    x_points = np.concatenate(([0], change_indices))
    y_points = y[x_points]
    
    # Remove duplicate x points
    x_points, unique_idx = np.unique(x_points, return_index=True)
    y_points = y_points[unique_idx]
    
    # Interpolate up to the last change point
    last_change_idx = x_points[-1]
    if last_change_idx > 0:
        y_smooth[:last_change_idx+1] = np.interp(
            np.arange(last_change_idx + 1),
            x_points,
            y_points
        )
    else:
        y_smooth[0] = y[0]
        
    # Extrapolate from the last change point to the end of the array
    if last_change_idx < n_len - 1:
        if len(x_points) >= 2:
            t_b = x_points[-1]
            t_a = x_points[-2]
            val_b = y_points[-1]
            val_a = y_points[-2]
            interval = t_b - t_a
            rate_last = (val_b - val_a) / interval
            max_extra = interval
        else:
            if last_change_idx > 0:
                interval = last_change_idx
                rate_last = (y[last_change_idx] - y[0]) / interval
                max_extra = interval
            else:
                rate_last = 0.0
                max_extra = 0
                
        extra_len = n_len - 1 - last_change_idx
        n_extrapolate = min(extra_len, int(max_extra))
        if n_extrapolate > 0:
            y_smooth[last_change_idx + 1 : last_change_idx + 1 + n_extrapolate] = (
                y[last_change_idx] + rate_last * np.arange(1, n_extrapolate + 1)
            )
        if extra_len > n_extrapolate:
            last_val = y[last_change_idx] + rate_last * n_extrapolate if n_extrapolate > 0 else y[last_change_idx]
            y_smooth[last_change_idx + 1 + n_extrapolate:] = last_val
            
    return y_smooth

class TimingAnalysisWidget(QWidget):
    def __init__(self, engine, parent=None):
        super().__init__(parent)
        self.engine = engine

        self.setStyleSheet("""
            QGroupBox { border: 1px solid #5c6370; border-radius: 5px; margin-top: 12px; padding-top: 15px; font-weight: bold; }
            QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top left; top: 0px; left: 10px; color: #61afef; background-color: #282c34; padding: 0 5px; }
            QLabel { font-weight: normal; }
            QLineEdit, QComboBox { background-color: #3b4048; border: 1px solid #5c6370; padding: 3px; color: white; border-radius: 3px; }
            QPushButton { background-color: #616a6b; border: none; padding: 4px; border-radius: 4px; color: white; min-width: 40px; }
            QPushButton:hover { background-color: #7f8c8d; }
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
        grp_guide = QGroupBox()
        lay_guide = QVBoxLayout(grp_guide)
        lbl_guide = QLabel(
            "1. Navigate here to see real-time stepper & encoder pulses.\n"
            "2. Toggle Y-Axis Mode between Cumulative Counts and Instantaneous Speed.\n"
            "3. Adjust data window size or smoothing window size as needed.\n"
            "4. The stats panel displays current average rates and their ratio."
        )
        lbl_guide.setWordWrap(True)
        lay_guide.addWidget(lbl_guide)
        self.sect_guide = CollapsibleSection("Timing Analysis Guide", grp_guide)
        left_layout.addWidget(self.sect_guide)

        # Settings
        grp_settings = QGroupBox()
        lay_set = QGridLayout(grp_settings)
        
        lay_set.addWidget(QLabel("Y-Axis Mode:"), 0, 0)
        self.cb_y_mode = QComboBox()
        self.cb_y_mode.addItems(["Cumulative Counts", "Instantaneous Speed"])
        self.cb_y_mode.setCurrentText("Instantaneous Speed")
        lay_set.addWidget(self.cb_y_mode, 0, 1)
        
        lay_set.addWidget(QLabel("Window Size:"), 1, 0)
        self.txt_window_size = QLineEdit("20000")
        lay_set.addWidget(self.txt_window_size, 1, 1)
        
        lay_set.addWidget(QLabel("Smoothing Window (s):"), 2, 0)
        self.txt_smoothing = QLineEdit("0.1")
        lay_set.addWidget(self.txt_smoothing, 2, 1)
        
        self.sect_settings = CollapsibleSection("Plot Settings", grp_settings)
        self.sect_settings.content.setVisible(True)
        self.sect_settings.update_header()
        left_layout.addWidget(self.sect_settings)

        # Real-time stats
        grp_stats = QGroupBox()
        lay_stats = QVBoxLayout(grp_stats)
        
        self.lbl_step_rate = QLabel("Step Rate: —")
        self.lbl_step_rate.setStyleSheet("font-weight: bold; font-size: 10pt; color: #98c379;")
        
        self.lbl_enc_rate = QLabel("Encoder Rate: —")
        self.lbl_enc_rate.setStyleSheet("font-weight: bold; font-size: 10pt; color: #e5c07b;")
        
        self.lbl_ratio = QLabel("Step / Encoder Ratio: —")
        self.lbl_ratio.setStyleSheet("font-weight: bold; font-size: 10pt; color: #61afef;")
        
        lay_stats.addWidget(self.lbl_step_rate)
        lay_stats.addWidget(self.lbl_enc_rate)
        lay_stats.addWidget(self.lbl_ratio)
        
        self.sect_stats = CollapsibleSection("Real-Time Telemetry", grp_stats)
        self.sect_stats.content.setVisible(True)
        self.sect_stats.update_header()
        left_layout.addWidget(self.sect_stats)

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
        lbl_title = QLabel("Step & Encoder Pulses / Time Dynamics")
        lbl_title.setStyleSheet("font-weight: bold; color: #abb2bf;")
        header_lay.addWidget(lbl_title)
        header_lay.addStretch()

        btn_shot = QPushButton("📸")
        btn_shot.setFixedWidth(30)
        btn_shot.setStyleSheet("""
            QPushButton { background-color: #3b4048; border: 1px solid #5c6370; border-radius: 3px; padding: 2px; font-size: 8pt; color: white; }
            QPushButton:hover { background-color: #61afef; color: black; font-weight: bold; }
        """)
        btn_shot.clicked.connect(self.take_timing_screenshot)
        header_lay.addWidget(btn_shot)
        graph_lay.addLayout(header_lay)

        self.graph_splitter = QSplitter(Qt.Vertical)

        # Plot 1: Stepper
        self.plot_step = pg.PlotWidget()
        self.plot_step.setLabel('left', 'Stepper Speed (steps/s)')
        self.plot_step.setLabel('bottom', 'Time', units='s')
        self.plot_step.showGrid(x=True, y=True, alpha=0.3)
        self.curve_step = self.plot_step.plot(pen=pg.mkPen('#98c379', width=1.5))
        self.graph_splitter.addWidget(self.plot_step)

        # Plot 2: Encoder
        self.plot_enc = pg.PlotWidget()
        self.plot_enc.setLabel('left', 'Encoder Speed (pulses/s)')
        self.plot_enc.setLabel('bottom', 'Time', units='s')
        self.plot_enc.showGrid(x=True, y=True, alpha=0.3)
        self.curve_enc = self.plot_enc.plot(pen=pg.mkPen('#e5c07b', width=1.5))
        self.graph_splitter.addWidget(self.plot_enc)

        # Plot 3: Step / Encoder Ratio
        self.plot_ratio = pg.PlotWidget()
        self.plot_ratio.setLabel('left', 'Step / Encoder Ratio')
        self.plot_ratio.setLabel('bottom', 'Time', units='s')
        self.plot_ratio.showGrid(x=True, y=True, alpha=0.3)
        self.curve_ratio = self.plot_ratio.plot(pen=pg.mkPen('#61afef', width=1.5))
        self.graph_splitter.addWidget(self.plot_ratio)

        # Link X axes
        self.plot_enc.setXLink(self.plot_step)
        self.plot_ratio.setXLink(self.plot_step)

        graph_lay.addWidget(self.graph_splitter)
        self.splitter.addWidget(graph_container)
        self.splitter.setSizes([280, 940])
        self.graph_splitter.setSizes([300, 300, 300])

    def take_timing_screenshot(self):
        import os
        from datetime import datetime
        os.makedirs(os.path.join("outputs", "screenshots"), exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = os.path.join("outputs", "screenshots", f"timing_plots_{ts}.png")
        pixmap = self.grab()
        pixmap.save(filepath)
        # Try to log on main window status bar
        win = self.window()
        if hasattr(win, 'log'):
            win.log(f"Saved timing screenshot to {os.path.basename(filepath)}")

    def update_data(self):
        try:
            num_points = int(self.txt_window_size.text())
            num_points = max(100, num_points)
        except ValueError:
            num_points = 20000
            
        if num_points > self.engine.max_points:
            self.engine.resize_buffers(num_points)
            
        try:
            smoothing_s = float(self.txt_smoothing.text())
            smoothing_s = max(0.001, min(2.0, smoothing_s))
        except ValueError:
            smoothing_s = 0.1
            
        y_mode = self.cb_y_mode.currentText()
        
        # Fetch latest data
        enc_pulses, step_pulses = self.engine.get_latest_pulses(num_points)
        if len(enc_pulses) < 2:
            self.curve_step.setData([], [])
            self.curve_enc.setData([], [])
            self.curve_ratio.setData([], [])
            self.lbl_step_rate.setText("Step Rate: —")
            self.lbl_enc_rate.setText("Encoder Rate: —")
            self.lbl_ratio.setText("Step / Encoder Ratio: —")
            return
            
        rate = self.engine.live_rate_sps
        if rate <= 0:
            rate = 2400.0
            
        smoothing = int(smoothing_s * rate)
        smoothing = max(1, smoothing)
            
        t = np.arange(len(enc_pulses)) / rate
        
        # Unwrap encoder pulses to make them continuous (prevents sawtooth and wrap-around spikes)
        ppr = self.engine.encoder_ppr
        if ppr > 0:
            diff_enc = np.diff(enc_pulses)
            wrap_correction = np.zeros_like(enc_pulses)
            wrap_correction[1:] = np.round(diff_enc / ppr) * -ppr
            enc_unwrapped = enc_pulses + np.cumsum(wrap_correction)
        else:
            enc_unwrapped = enc_pulses
            
        if y_mode == "Cumulative Counts":
            self.plot_step.setLabel('left', 'Stepper steps (Count)')
            self.plot_enc.setLabel('left', 'Encoder pulses (Count)')
            
            self.curve_step.setData(t, step_pulses)
            self.curve_enc.setData(t, enc_unwrapped)
            
            with np.errstate(divide='ignore', invalid='ignore'):
                ratio_data = np.where(np.abs(enc_unwrapped) > 0.1, step_pulses / enc_unwrapped, 0.0)
            self.curve_ratio.setData(t, ratio_data)
            
            dt = t[-1] - t[0]
            if dt > 0:
                avg_step_rate = (step_pulses[-1] - step_pulses[0]) / dt
                avg_enc_rate = (enc_unwrapped[-1] - enc_unwrapped[0]) / dt
            else:
                avg_step_rate = 0.0
                avg_enc_rate = 0.0
        else:
            self.plot_step.setLabel('left', 'Step Rate (steps/s)')
            self.plot_enc.setLabel('left', 'Encoder Rate (pulses/s)')
            
            # Reconstruction of smooth pulses to remove batching telemetry artifacts
            smooth_step = smooth_pulses(step_pulses)
            smooth_enc = smooth_pulses(enc_unwrapped)
            
            # Differentiation: delta_value * sample_rate
            step_rate = np.diff(smooth_step) * rate
            step_rate = np.insert(step_rate, 0, step_rate[0] if len(step_rate) > 0 else 0)
            
            enc_rate = np.diff(smooth_enc) * rate
            enc_rate = np.insert(enc_rate, 0, enc_rate[0] if len(enc_rate) > 0 else 0)
            
            # Moving average smoothing
            actual_smoothing = min(smoothing, len(step_rate))
            if actual_smoothing > 1:
                kernel = np.ones(actual_smoothing) / actual_smoothing
                step_rate = np.convolve(step_rate, kernel, mode='same')
                enc_rate = np.convolve(enc_rate, kernel, mode='same')
                
            self.curve_step.setData(t, step_rate)
            self.curve_enc.setData(t, enc_rate)
            
            with np.errstate(divide='ignore', invalid='ignore'):
                ratio_data = np.where(np.abs(enc_rate) > 0.1, step_rate / enc_rate, 0.0)
            self.curve_ratio.setData(t, ratio_data)
            
            avg_step_rate = np.mean(step_rate)
            avg_enc_rate = np.mean(enc_rate)
            
        self.lbl_step_rate.setText(f"Step Rate: {avg_step_rate:+.1f} steps/s")
        self.lbl_enc_rate.setText(f"Encoder Rate: {avg_enc_rate:+.1f} pulses/s")
        if abs(avg_enc_rate) > 0.01:
            ratio = avg_step_rate / avg_enc_rate
            self.lbl_ratio.setText(f"Step / Encoder Ratio: {ratio:.4f}")
        else:
            self.lbl_ratio.setText("Step / Encoder Ratio: —")
