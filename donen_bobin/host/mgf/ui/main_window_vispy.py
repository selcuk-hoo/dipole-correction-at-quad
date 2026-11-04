"""
MGF Radar V2 — Main Window (VisPy + PyQtGraph + PySide6)
Polar plot rendered via VisPy OpenGL for hardware-locked aspect ratio.
Time domain and FFT rendered via PyQtGraph for scientific axis control.
Includes Waterfall, Orbit, Coil Alignment Routine, Speed Ramp Editor, and Session Manager.
"""
import sys
import time
import numpy as np
import pyqtgraph as pg
from PySide6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QTabWidget, QPushButton
from PySide6.QtCore import QTimer, Qt, Slot

from concurrent.futures import ProcessPoolExecutor
from .. import protocol
from ..analysis import Analyzer, run_background_fft
from .. import session


from .alignment import CoilAlignmentWidget
from .magnetic_analysis import MagneticAnalysisWidget
from .signal_analysis import SignalAnalysisWidget
from .fft_page import FftAnalysisWidget
from .source_fft_page import SourceFftAnalysisWidget
from .timing_analysis import TimingAnalysisWidget

from .ramp_editor import RampEditorWidget
from .macro_page import MacroSystemWidget

from .control_panel import ControlPanelWidget
from .status_bar import StatusBarWidget
from .plot_radar import RadarPlotWidget
from .plot_linear import LinearPlotWidget

pg.setConfigOption('background', '#282c34')
pg.setConfigOption('foreground', 'd')
pg.setConfigOptions(antialias=False)

class MainWindowVispy(QMainWindow):
    def __init__(self, conn, engine, settings):
        super().__init__()
        self.conn = conn
        self.engine = engine
        self.settings = settings
        self.analyzer = Analyzer()
        self.executor = ProcessPoolExecutor(max_workers=2)
        self._fft_future = None


        self.setWindowTitle("MGF Radar V2 — Order Analysis")
        self.resize(1400, 900)

        # SPS counter state
        self._last_sps_time = time.time()
        self._last_sps_count = 0

        self._build_ui()

        self.timer = QTimer()
        self.timer.timeout.connect(self.update_plots)
        self.timer.start(16)  # ~60 FPS

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(5, 5, 5, 5)

        self.setStyleSheet("""
            QWidget { background-color: #282c34; color: white; font-family: Segoe UI; }
            QGroupBox { border: 1px solid #5c6370; border-radius: 5px;
                        margin-top: 12px; padding-top: 15px; font-weight: bold; }
            QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top left; top: 0px; left: 10px;
                               color: #61afef; background-color: #282c34; padding: 0 5px; }
            QLineEdit, QComboBox { background-color: #3b4048; border: 1px solid #5c6370;
                                   padding: 3px; color: white; border-radius: 3px; min-width: 40px; }
            QPushButton { background-color: #616a6b; border: none; padding: 4px;
                          border-radius: 4px; min-width: 30px; }
            QPushButton:hover { background-color: #7f8c8d; }
            QPushButton:checked { background-color: #61afef; color: black; font-weight: bold; }
            QPushButton:checked:hover { background-color: #72c0ff; }
            QPushButton#ServoBtn.on  { background-color: #98c379; color: black; }
            QPushButton#ServoBtn.off { background-color: #616a6b; }
            QTextEdit { background-color: #21252b; border: none;
                        font-family: Consolas; font-size: 9pt; }
            QLabel#LiveVal { font-family: 'Consolas', monospace;
                             font-size: 24pt; font-weight: bold; color: #98c379; }
            QLabel#LiveEnc { font-family: 'Consolas', monospace;
                             font-size: 16pt; color: #e5c07b; }
            QTabWidget::pane { border: 1px solid #5c6370; background-color: #282c34; }
            QTabBar::tab { background: #21252b; border: 1px solid #5c6370; padding: 8px 12px; min-width: 100px; }
            QTabBar::tab:selected { background: #282c34; border-bottom-color: #282c34; font-weight: bold; color: #61afef; }
            QTabBar::tab:hover { background: #3b4048; }
            QSlider::groove:horizontal { border: 1px solid #5c6370; height: 8px; background: #21252b; border-radius: 4px; }
            QSlider::handle:horizontal { background: #61afef; border: 1px solid #5c6370; width: 18px; margin: -5px 0; border-radius: 9px; }
            QSlider::handle:horizontal:hover { background: #98c379; }
        """)

        splitter = QSplitter(Qt.Horizontal)
        root.addWidget(splitter)

        # ---- LEFT PANEL (Control Panel & Status Bar) ----
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)

        self.control_panel = ControlPanelWidget(self)
        left_layout.addWidget(self.control_panel)

        self.status_bar = StatusBarWidget(self.engine)
        left_layout.addWidget(self.status_bar)

        left_panel.setMinimumWidth(250)
        splitter.addWidget(left_panel)


        # ---- RIGHT PANEL (Tabs) ----
        right_panel = QWidget()
        right_lay = QVBoxLayout(right_panel)
        right_lay.setContentsMargins(0, 0, 0, 0)
        
        self.tabs = QTabWidget()
        
        btn_app_screenshot = QPushButton("📸 Capture Screen")
        btn_app_screenshot.setStyleSheet("""
            QPushButton { background-color: #3b4048; border: 1px solid #5c6370; border-radius: 3px; padding: 4px 8px; font-size: 8.5pt; color: white; min-width: 100px; }
            QPushButton:hover { background-color: #61afef; color: black; font-weight: bold; }
        """)
        btn_app_screenshot.clicked.connect(self.take_application_screenshot)
        self.tabs.setCornerWidget(btn_app_screenshot, Qt.TopRightCorner)
        
        right_lay.addWidget(self.tabs)

        # Tab 1: Dashboard (Splitter: Polar + Time + FFT)
        dashboard_widget = QWidget()
        dash_lay = QVBoxLayout(dashboard_widget)
        dash_lay.setContentsMargins(0, 0, 0, 0)
        
        splitter_p = QSplitter(Qt.Vertical)
        dash_lay.addWidget(splitter_p)

        self.plot_radar = RadarPlotWidget()
        self.plot_radar.btn_clear.clicked.connect(self._clear_polar_graph)
        splitter_p.addWidget(self.plot_radar)

        self.plot_linear = LinearPlotWidget()
        splitter_p.addWidget(self.plot_linear)

        splitter_p.setSizes([450, 450])
        self.tabs.addTab(dashboard_widget, "Dashboard")
        
        # Tab 2: Coil Alignment
        self.alignment_widget = CoilAlignmentWidget(self.engine)
        self.tabs.addTab(self.alignment_widget, "Coil Alignment")
        
        # Tab 3: Magnetic Analysis
        self.magnetic_analysis_widget = MagneticAnalysisWidget(self.engine)
        self.tabs.addTab(self.magnetic_analysis_widget, "Magnetic Analysis")
        
        # Tab 3b: Signal Database Analysis
        self.signal_analysis_widget = SignalAnalysisWidget(self.engine)
        self.tabs.addTab(self.signal_analysis_widget, "Signal Database Analysis")

        
        # Tab 4: Macro System
        self.macro_widget = MacroSystemWidget(self.engine)
        self.tabs.addTab(self.macro_widget, "Macro System")
        
        # Tab 5: FFT / Order Analysis
        self.fft_analysis_widget = FftAnalysisWidget(self.engine)
        self.tabs.addTab(self.fft_analysis_widget, "FFT / Order Analysis")

        # Tab 5b: Signal Source FFT Analysis
        self.source_fft_analysis_widget = SourceFftAnalysisWidget(self.engine)
        self.tabs.addTab(self.source_fft_analysis_widget, "Signal Source FFT")

        # Tab 6: Timing Analysis
        self.timing_analysis_widget = TimingAnalysisWidget(self.engine)
        self.tabs.addTab(self.timing_analysis_widget, "Timing Analysis")
        
        # Tab 7: Ramp Editor
        self.ramp_widget = RampEditorWidget(self.conn)
        self.tabs.addTab(self.ramp_widget, "Ramp Editor")

        splitter.addWidget(right_panel)
        splitter.setSizes([340, 1060])

    def log(self, msg: str):
        self.status_bar.log(msg)

    def closeEvent(self, event):
        if hasattr(self, 'timer') and self.timer.isActive():
            self.timer.stop()
        self.conn.disconnect()
        if hasattr(self, 'executor') and self.executor is not None:
            self.executor.shutdown(wait=False)
            self.executor = None
        event.accept()


    @Slot()
    def update_plots(self):
        # Update active offset label occasionally if it changes outside
        if hasattr(self, 'alignment_widget'):
            self.alignment_widget.lbl_active_offset.setText(f"Active Offset: {self.engine.phase_offset_deg:.2f}°")
        if hasattr(self, 'magnetic_analysis_widget'):
            self.magnetic_analysis_widget.lbl_active_offset.setText(f"Active Offset: {self.engine.phase_offset_deg:.2f}°")


        # 1. Update data buffers
        if self.engine.replay_mode:
            if self.control_panel.replay_playing:
                # 60 FPS update, step index
                dt = 1.0 / 60.0
                step_size = int(self.engine.replay_rate_sps * dt * self.control_panel.replay_speed_mult)
                if step_size < 1:
                    step_size = 1
                actual = self.engine.step_replay(step_size)
                if actual > 0:
                    self.control_panel.replay_slider.blockSignals(True)
                    self.control_panel.replay_slider.setValue(self.engine.replay_idx)
                    self.control_panel.replay_slider.blockSignals(False)
                else:
                    self.control_panel.toggle_replay_play(False)
        else:
            self.engine.process_queue(self.conn.rx_queue, log_cb=self.log)
            if getattr(self.engine, 'adc_config_sync_pending', False):
                self.control_panel.synchronize_ui(self.engine.current_adc_config)
                self.engine.adc_config_sync_pending = False

        # Update ADC status LED and text based on adc_status_state
        state = getattr(self.engine, 'adc_status_state', 'ok')
        if hasattr(self.control_panel, 'led_indicator'):
            if state == 'ok':
                self.control_panel.led_indicator.set_color("#98c379")
                self.control_panel.lbl_status_text.setText("ADC Status: Ok")
                self.control_panel.lbl_status_text.setStyleSheet("font-weight: bold; color: #98c379;")
            elif state == 'verifying':
                self.control_panel.led_indicator.set_color("#d19a66")
                self.control_panel.lbl_status_text.setText("ADC Status: Verifying...")
                self.control_panel.lbl_status_text.setStyleSheet("font-weight: bold; color: #d19a66;")
            elif state == 'error':
                self.control_panel.led_indicator.set_color("#e06c75")
                err_msg = getattr(self.engine, 'last_adc_error', '')
                if err_msg:
                    self.control_panel.lbl_status_text.setText(f"ADC Status: Error ({err_msg})")
                else:
                    self.control_panel.lbl_status_text.setText("ADC Status: Error")
                self.control_panel.lbl_status_text.setStyleSheet("font-weight: bold; color: #e06c75;")

        now = time.time()

        # SPS counter (update every 0.5 s)
        if now - self._last_sps_time >= 0.5:
            if self.engine.total_samples_received < self._last_sps_count:
                self._last_sps_count = 0
                self._last_sps_time = now
            
            dt = now - self._last_sps_time
            sps = (self.engine.total_samples_received - self._last_sps_count) / dt if dt > 0 else 0.0
            self.status_bar.lbl_stats.setText(f"Rate: {sps:.0f} SPS")
            self._last_sps_time = now
            self._last_sps_count = self.engine.total_samples_received

        # Live labels
        mode_voltage = self.control_panel.cb_mode.currentText() == "Voltage (V)"
        if mode_voltage:
            self.status_bar.lbl_live_val.setText(f"{self.engine.last_voltage:+.8f} V")
        else:
            self.status_bar.lbl_live_val.setText(f"{int(self.engine.last_raw)} RAW")
            
        min_v = self.engine.min_voltage if self.engine.min_voltage is not None else 0.0
        max_v = self.engine.max_voltage if self.engine.max_voltage is not None else 0.0
        min_r = self.engine.min_raw if self.engine.min_raw is not None else 0
        max_r = self.engine.max_raw if self.engine.max_raw is not None else 0
            
        self.status_bar.lbl_minmax_v.setText(
            f"Voltage Min: {min_v:+.5f} | Max: {max_v:+.5f}")
        self.status_bar.lbl_peak_peak_v.setText(
            f"Voltage P-P: {max_v - min_v:.5f} V")
        self.status_bar.lbl_minmax_r.setText(
            f"Raw Min: {min_r} | Max: {max_r}")
        self.status_bar.lbl_live_enc.setText(f"Enc: {int(self.engine.current_angle_deg * 10):05d}")

        # Use engine.live_rate_sps as the authoritative sample rate
        rate = self.engine.live_rate_sps
        motor_speed = max(0.01, abs(self.engine.motor_speed))

        # --- Time Domain & Polar Fetch ---
        try:
            window_s = float(self.control_panel.cb_time_window.currentText().replace("s", ""))
        except Exception:
            window_s = 3.0
            
        time_points = max(20000, int(window_s * rate))
        _, adc_time = self.engine.get_latest_data(time_points)
        
        try:
            num_points = int(self.control_panel.txt_point_count.text())
        except Exception:
            num_points = 20000
            
        enc_polar, adc_polar = self.engine.get_latest_data(num_points)

        # --- Time Domain Plot ---
        if len(adc_time) > 0:
            self.plot_linear.update_data(adc_time, rate, window_s)

        # --- Polar Plot ---
        if len(adc_polar) > 0:
            # Calculate polar bins dynamically from the latest num_points
            bins = (enc_polar.astype(np.int32)) % 360
            polar_bins = np.zeros(360, dtype=np.float32)
            
            if getattr(self.engine, 'polar_averaging', False):
                counts = np.bincount(bins, minlength=360)
                sums = np.bincount(bins, weights=adc_polar, minlength=360)
                mask = counts > 0
                polar_bins[mask] = sums[mask] / counts[mask]
            else:
                polar_bins[bins] = adc_polar
        else:
            polar_bins = np.zeros(360, dtype=np.float32)

        current_gain = getattr(self.engine, 'current_gain', 1.0)
        self.plot_radar.update_data(polar_bins, self.engine.current_angle_deg, mode_voltage, current_gain, self.engine.current_vref)

        # --- Dedicated FFT Page (only update when visible to save CPU) ---
        if hasattr(self, 'fft_analysis_widget') and len(adc_time) > 0:
            if self.tabs.currentWidget() is self.fft_analysis_widget:
                self.fft_analysis_widget.update_data(adc_time, rate)

        # --- Signal Source FFT Page (only update when visible to save CPU) ---
        if hasattr(self, 'source_fft_analysis_widget') and len(adc_time) > 0:
            if self.tabs.currentWidget() is self.source_fft_analysis_widget:
                self.source_fft_analysis_widget.update_data(adc_time, rate)

        # --- Timing Analysis Page (only update when visible to save CPU) ---
        if hasattr(self, 'timing_analysis_widget'):
            if self.tabs.currentWidget() is self.timing_analysis_widget:
                self.timing_analysis_widget.update_data()

        # --- Update Control Panel Recording Status ---
        if hasattr(self, 'control_panel'):
            self.control_panel.update_recording_status()



    def _clear_polar_graph(self):
        self.engine.polar_bins.fill(0.0)
        self.engine.polar_counts.fill(0)

    def take_application_screenshot(self):
        import os
        from datetime import datetime
        os.makedirs(os.path.join("outputs", "screenshots"), exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = os.path.join("outputs", "screenshots", f"application_{ts}.png")
        pixmap = self.grab()
        pixmap.save(filepath)
        self.log(f"Saved screen to {os.path.basename(filepath)}")
