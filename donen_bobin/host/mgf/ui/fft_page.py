"""
Dedicated FFT / Order Analysis Widget for MGF Radar V2.
Allows advanced FFT configuration, automatic peak detection with harmonic labels,
and 4 comparison slots to overlay multiple runs.
"""
import numpy as np
import pyqtgraph as pg
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QGroupBox, QLabel, 
    QComboBox, QPushButton, QGridLayout, QCheckBox, QLineEdit,
    QTableWidget, QTableWidgetItem, QHeaderView, QSplitter,
    QScrollArea, QFrame
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

from ..analysis import Analyzer
from .control_panel import CollapsibleSection

class FftAnalysisWidget(QWidget):
    def __init__(self, engine, parent=None):
        super().__init__(parent)
        self.engine = engine
        self.analyzer = Analyzer()
        self._future = None

        
        self.slots = {
            1: {"name": "Slot 1: Baseline", "color": "#e5c07b", "x": None, "y": None},
            2: {"name": "Slot 2: Run A", "color": "#98c379", "x": None, "y": None},
            3: {"name": "Slot 3: Run B", "color": "#61afef", "x": None, "y": None},
            4: {"name": "Slot 4: Run C", "color": "#c678dd", "x": None, "y": None},
        }
        
        self.peak_text_items = []
        
        self.setStyleSheet("""
            QGroupBox { border: 1px solid #5c6370; border-radius: 5px; margin-top: 12px; padding-top: 15px; font-weight: bold; }
            QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top left; top: 0px; left: 10px; color: #61afef; background-color: #282c34; padding: 0 5px; }
            QLabel { font-weight: normal; }
            QLineEdit, QComboBox { background-color: #3b4048; border: 1px solid #5c6370; padding: 3px; color: white; border-radius: 3px; }
            QCheckBox { color: white; }
            QPushButton { background-color: #616a6b; border: none; padding: 4px; border-radius: 4px; color: white; min-width: 40px; }
            QPushButton:hover { background-color: #7f8c8d; }
            QPushButton#CaptureBtn { background-color: #61afef; color: black; font-weight: bold; padding: 6px; }
            QPushButton#CaptureBtn:hover { background-color: #8cc3f2; }
            QTableWidget { background-color: #21252b; border: 1px solid #5c6370; color: white; gridline-color: #5c6370; }
            QHeaderView::section { background-color: #282c34; color: #61afef; padding: 4px; border: 1px solid #5c6370; }
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
        
        # ---- LEFT PANEL (Controls & Tables) ----
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(5, 5, 5, 5)
        
        # Guide
        grp_guide = QGroupBox()
        lay_guide = QVBoxLayout(grp_guide)
        lbl_guide = QLabel(
            "1. Command target speed in the left motor control panel.\n"
            "2. Tune peak threshold to auto-label peaks.\n"
            "3. Click 'Capture' on any comparison slot to lock the active spectrum.\n"
            "4. Overlay and compare multiple profiles on the graph."
        )
        lbl_guide.setWordWrap(True)
        lay_guide.addWidget(lbl_guide)
        self.sect_guide = CollapsibleSection("Dedicated FFT Guide", grp_guide)
        left_layout.addWidget(self.sect_guide)
        
        # FFT Settings & Peak Detection
        grp_settings = QGroupBox()
        lay_set = QGridLayout(grp_settings)
        
        lay_set.addWidget(QLabel("FFT Window:"), 0, 0)
        self.cb_fft_window = QComboBox()
        self.cb_fft_window.addItems(["Hanning", "Hamming", "Blackman", "Rectangular"])
        lay_set.addWidget(self.cb_fft_window, 0, 1)
        
        lay_set.addWidget(QLabel("Domain:"), 1, 0)
        self.cb_fft_domain = QComboBox()
        self.cb_fft_domain.addItems(["Order", "Frequency"])
        lay_set.addWidget(self.cb_fft_domain, 1, 1)
        
        lay_set.addWidget(QLabel("Max X Limit:"), 2, 0)
        self.txt_fft_max_x = QLineEdit("100")
        lay_set.addWidget(self.txt_fft_max_x, 2, 1)
        
        lay_set.addWidget(QLabel("Y Scale:"), 3, 0)
        self.cb_fft_y_mode = QComboBox()
        self.cb_fft_y_mode.addItems(["Log (dB)", "Linear"])
        self.cb_fft_y_mode.setCurrentText("Log (dB)")
        self.cb_fft_y_mode.currentTextChanged.connect(self.on_y_mode_changed)
        lay_set.addWidget(self.cb_fft_y_mode, 3, 1)
        
        lay_set.addWidget(QLabel("Peak Thresh (dB):"), 4, 0)
        self.txt_threshold_db = QLineEdit("-40.0")
        lay_set.addWidget(self.txt_threshold_db, 4, 1)
        
        lay_set.addWidget(QLabel("Max Peaks:"), 5, 0)
        self.txt_max_peaks = QLineEdit("8")
        lay_set.addWidget(self.txt_max_peaks, 5, 1)
        
        lay_set.addWidget(QLabel("Zero-Pad:"), 6, 0)
        self.cb_zero_pad = QComboBox()
        self.cb_zero_pad.addItems(["1x (Off)", "2x", "4x"])
        lay_set.addWidget(self.cb_zero_pad, 6, 1)
        
        lay_set.addWidget(QLabel("Averaging:"), 7, 0)
        self.cb_averaging = QComboBox()
        self.cb_averaging.addItems(["1 (Off)", "2", "4", "8"])
        lay_set.addWidget(self.cb_averaging, 7, 1)
        
        lay_set.addWidget(QLabel("FFT Samples:"), 8, 0)
        self.txt_fft_samples = QLineEdit("16384")
        lay_set.addWidget(self.txt_fft_samples, 8, 1)
        
        lay_set.addWidget(QLabel("Jitter Tolerance:"), 9, 0)
        self.txt_jitter_tolerance = QLineEdit("0.08")
        lay_set.addWidget(self.txt_jitter_tolerance, 9, 1)
        
        self.chk_div_speed = QCheckBox("Divide X by Measured Speed")
        self.chk_div_speed.setChecked(True)
        lay_set.addWidget(self.chk_div_speed, 10, 0, 1, 2)
        
        self.chk_dc_remove = QCheckBox("Remove DC in Time Plot")
        self.chk_dc_remove.setChecked(False)
        lay_set.addWidget(self.chk_dc_remove, 11, 0, 1, 2)
        
        self.btn_clear_buffer = QPushButton("Clear FFT Sample Buffer")
        self.btn_clear_buffer.setStyleSheet("background-color: #e06c75; color: black; font-weight: bold;")
        self.btn_clear_buffer.clicked.connect(self.clear_sample_buffer)
        lay_set.addWidget(self.btn_clear_buffer, 12, 0, 1, 2)
        
        self.sect_settings = CollapsibleSection("FFT & Peak Settings", grp_settings)
        self.sect_settings.content.setVisible(True)
        self.sect_settings.update_header()
        left_layout.addWidget(self.sect_settings)
        
        # Captured Slots Manager
        grp_slots = QGroupBox()
        lay_slots = QVBoxLayout(grp_slots)
        
        # Live Slot (Toggle active spectrum on/off)
        live_row = QWidget()
        live_lay = QHBoxLayout(live_row)
        live_lay.setContentsMargins(0, 2, 0, 2)
        
        self.chk_live_visible = QCheckBox()
        self.chk_live_visible.setChecked(True)
        self.chk_live_visible.stateChanged.connect(self.toggle_live_visibility)
        live_lay.addWidget(self.chk_live_visible)
        
        lbl_live_name = QLabel("<b>Live FFT</b>")
        lbl_live_name.setFixedWidth(65)
        live_lay.addWidget(lbl_live_name)
        
        self.btn_live_clear = QPushButton("Clear")
        self.btn_live_clear.setFixedWidth(75)
        self.btn_live_clear.setStyleSheet("background-color: #3b4048; font-size: 8pt; padding: 4px; color: white;")
        self.btn_live_clear.clicked.connect(self.clear_active_fft)
        live_lay.addWidget(self.btn_live_clear)
        
        self.lbl_live_status = QLabel("Active")
        self.lbl_live_status.setStyleSheet("color: #98c379; font-weight: bold;")
        live_lay.addWidget(self.lbl_live_status)
        
        lay_slots.addWidget(live_row)
        
        # Comparison Slots (1-4)
        self.slot_widgets = {}
        for idx in [1, 2, 3, 4]:
            slot_name = self.slots[idx]['name']
            slot_row = QWidget()
            row_lay = QHBoxLayout(slot_row)
            row_lay.setContentsMargins(0, 2, 0, 2)
            
            cb_visible = QCheckBox()
            cb_visible.setChecked(True)
            cb_visible.stateChanged.connect(self.replot_slots)
            row_lay.addWidget(cb_visible)
            
            lbl_name = QLabel(f"<b>{slot_name}</b>")
            lbl_name.setFixedWidth(65)
            row_lay.addWidget(lbl_name)
            
            # Capture Button
            btn_cap = QPushButton("Capture")
            btn_cap.setFixedWidth(45)
            btn_cap.setStyleSheet("background-color: #3b4048; font-size: 8pt; padding: 4px; color: white;")
            btn_cap.clicked.connect(lambda _, s_idx=idx: self.capture_slot(s_idx))
            row_lay.addWidget(btn_cap)
            
            # Clear Button
            btn_clr = QPushButton("Clear")
            btn_clr.setFixedWidth(30)
            btn_clr.setStyleSheet("background-color: #3b4048; font-size: 8pt; padding: 4px; color: white;")
            btn_clr.clicked.connect(lambda _, s_idx=idx: self.clear_single_slot(s_idx))
            row_lay.addWidget(btn_clr)
            
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
        btn_clear_all.setStyleSheet("background-color: #e06c75; color: black; font-weight: bold; margin-top: 5px;")
        btn_clear_all.clicked.connect(self.clear_all_slots)
        lay_slots.addWidget(btn_clear_all)
        
        self.sect_slots = CollapsibleSection("Comparison Slots", grp_slots)
        self.sect_slots.content.setVisible(True)
        self.sect_slots.update_header()
        left_layout.addWidget(self.sect_slots)
        
        # Peak Detection Table
        grp_table = QGroupBox()
        lay_table = QVBoxLayout(grp_table)
        
        # Source Selection Row
        src_row = QWidget()
        src_lay = QHBoxLayout(src_row)
        src_lay.setContentsMargins(0, 0, 0, 0)
        src_lay.addWidget(QLabel("Peak Source:"))
        
        self.cb_peak_source = QComboBox()
        self.cb_peak_source.addItems(["Live FFT", "Slot 1: Baseline", "Slot 2: Run A", "Slot 3: Run B", "Slot 4: Run C"])
        self.cb_peak_source.currentTextChanged.connect(self.replot_active)
        src_lay.addWidget(self.cb_peak_source)
        lay_table.addWidget(src_row)
        
        self.table_peaks = QTableWidget(0, 3)
        self.table_peaks.setHorizontalHeaderLabels(["Order/Freq", "Mag", "Label"])
        self.table_peaks.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table_peaks.setMinimumHeight(150)
        lay_table.addWidget(self.table_peaks)
        
        self.sect_table = CollapsibleSection("Detected Peaks List", grp_table)
        self.sect_table.content.setVisible(True)
        self.sect_table.update_header()
        left_layout.addWidget(self.sect_table)
        
        left_layout.addStretch()
        scroll.setWidget(left_panel)
        self.splitter.addWidget(scroll)
        
        # ---- RIGHT PANEL (Graph Container) ----
        graph_container = QWidget()
        graph_lay = QVBoxLayout(graph_container)
        graph_lay.setContentsMargins(0, 0, 0, 0)
        graph_lay.setSpacing(2)
        
        header_lay = QHBoxLayout()
        header_lay.setContentsMargins(5, 2, 5, 2)
        lbl_title = QLabel("FFT Spectrum & Order Analysis")
        lbl_title.setStyleSheet("font-weight: bold; color: #abb2bf;")
        header_lay.addWidget(lbl_title)
        header_lay.addStretch()
        
        btn_shot = QPushButton("📸")
        btn_shot.setFixedWidth(30)
        btn_shot.setStyleSheet("""
            QPushButton { background-color: #3b4048; border: 1px solid #5c6370; border-radius: 3px; padding: 2px; font-size: 8pt; color: white; }
            QPushButton:hover { background-color: #61afef; color: black; font-weight: bold; }
        """)
        btn_shot.clicked.connect(self.take_fft_screenshot)
        header_lay.addWidget(btn_shot)
        graph_lay.addLayout(header_lay)

        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setLabel('left', 'Magnitude')
        self.plot_widget.setLabel('bottom', 'Order')
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
        self.plot_widget.setLogMode(x=False, y=True)
        
        self.curve_active = self.plot_widget.plot(pen=pg.mkPen('#abb2bf', width=1.5))
        self.scatter_peaks = self.plot_widget.plot(pen=None, symbol='t', symbolSize=8, symbolBrush='#e06c75')
        
        self.slot_curves = {}
        for idx in [1, 2, 3, 4]:
            self.slot_curves[idx] = self.plot_widget.plot(pen=pg.mkPen(self.slots[idx]["color"], width=1.5))
            
        graph_lay.addWidget(self.plot_widget)
        self.splitter.addWidget(graph_container)
        self.splitter.setSizes([420, 800])
              # Keep track of active values
        self.active_x = np.array([])
        self.active_y = np.array([])
        self.active_freqs = np.array([])
        self.active_mags = np.array([])
        self.custom_labels = {}
        self.load_custom_labels()
        
        # Connect settings that don't need recomputing FFT to replot instantly
        self.cb_fft_domain.currentTextChanged.connect(self.replot_active)
        self.chk_div_speed.stateChanged.connect(self.replot_active)
        self.txt_fft_max_x.textChanged.connect(self.replot_active)
        self.txt_threshold_db.textChanged.connect(self.replot_active)
        self.txt_max_peaks.textChanged.connect(self.replot_active)
        self.txt_jitter_tolerance.textChanged.connect(self.replot_active)
        
        # Connect settings that change FFT calculation to discard future so it re-runs
        self.cb_fft_window.currentTextChanged.connect(self.force_recompute_fft)
        self.cb_zero_pad.currentTextChanged.connect(self.force_recompute_fft)
        self.cb_averaging.currentTextChanged.connect(self.force_recompute_fft)
        self.txt_fft_samples.textChanged.connect(self.force_recompute_fft)
        
        # Connect table item changed event for editable labels
        self.table_peaks.itemChanged.connect(self.on_table_item_changed)
        
    def on_y_mode_changed(self, text):
        log_mode = (text == "Log (dB)")
        self.plot_widget.setLogMode(x=False, y=log_mode)
        self.replot_active()
        
    def toggle_live_visibility(self):
        visible = self.chk_live_visible.isChecked()
        if visible:
            self.lbl_live_status.setText("Active")
            self.lbl_live_status.setStyleSheet("color: #98c379; font-weight: bold;")
        else:
            self.lbl_live_status.setText("Hidden")
            self.lbl_live_status.setStyleSheet("color: #abb2bf; font-weight: normal;")
            self.curve_active.setData([], [])
            self.scatter_peaks.setData([], [])
            for item in self.peak_text_items:
                self.plot_widget.removeItem(item)
            self.peak_text_items.clear()
            self.table_peaks.setRowCount(0)
            
    def load_custom_labels(self):
        import json
        import os
        if os.path.exists("fft_custom_labels.json"):
            try:
                with open("fft_custom_labels.json", "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.custom_labels = {float(k): v for k, v in data.items()}
            except Exception as e:
                print(f"Failed to load custom labels: {e}")

    def save_custom_labels(self):
        import json
        try:
            with open("fft_custom_labels.json", "w", encoding="utf-8") as f:
                json.dump({str(k): v for k, v in self.custom_labels.items()}, f, indent=4)
        except Exception as e:
            print(f"Failed to save custom labels: {e}")

    def clear_active_fft(self):
        self.active_x = np.array([])
        self.active_y = np.array([])
        self.active_freqs = np.array([])
        self.active_mags = np.array([])
        self.custom_labels.clear()
        self.save_custom_labels()
        
        self.curve_active.setData([], [])
        self.scatter_peaks.setData([], [])
        for item in self.peak_text_items:
            self.plot_widget.removeItem(item)
        self.peak_text_items.clear()
        self.table_peaks.setRowCount(0)

    def clear_sample_buffer(self):
        self.engine.clear_active_buffers()
        self.clear_active_fft()

    def force_recompute_fft(self):
        self._future = None

    def get_jitter_tolerance(self):
        try:
            return float(self.txt_jitter_tolerance.text())
        except ValueError:
            return 0.08

    def get_custom_label(self, order_or_freq):
        # Match nearest custom label within a small tolerance
        tolerance = self.get_jitter_tolerance()
        for key, val in self.custom_labels.items():
            if abs(key - order_or_freq) < tolerance:
                return val
        return None

    def on_table_item_changed(self, item):
        if item.column() == 2: # Label column
            row = item.row()
            self.table_peaks.blockSignals(True)
            try:
                order_item = self.table_peaks.item(row, 0)
                if order_item:
                    try:
                        val = float(order_item.text())
                        new_label = item.text()
                        
                        # Find and update or add new custom label
                        tolerance = self.get_jitter_tolerance()
                        matched_key = None
                        for key in self.custom_labels.keys():
                            if abs(key - val) < tolerance:
                                matched_key = key
                                break
                        
                        if matched_key is not None:
                            self.custom_labels[matched_key] = new_label
                        else:
                            self.custom_labels[val] = new_label
                            
                        self.save_custom_labels()
                            
                        # Update TextItem on plot instantly
                        if 0 <= row < len(self.peak_text_items):
                            self.peak_text_items[row].setText(new_label)
                    except ValueError:
                        pass
            finally:
                self.table_peaks.blockSignals(False)

    def replot_active(self):
        if len(self.active_freqs) == 0:
            return
            
        domain = self.cb_fft_domain.currentText()
        try:
            max_x = float(self.txt_fft_max_x.text())
        except ValueError:
            max_x = 100.0
            
        if domain == "Order":
            if self.chk_div_speed.isChecked():
                self.plot_widget.setLabel('bottom', 'Order (Measured)')
            else:
                self.plot_widget.setLabel('bottom', 'Order (Commanded)')
        else:
            if self.chk_div_speed.isChecked():
                self.plot_widget.setLabel('bottom', 'Frequency (Normalized by Measured Speed)')
            else:
                self.plot_widget.setLabel('bottom', 'Frequency (Hz)')
            
        self.plot_widget.setXRange(0, max_x)
        
        # Determine speed reference
        win = self.window()
        commanded_speed = 10.0
        if hasattr(win, 'settings') and win.settings is not None:
            commanded_speed = max(0.1, abs(win.settings.motor_speed))
            
        if self.chk_div_speed.isChecked():
            motor_speed = max(0.1, abs(self.engine.motor_speed))
        else:
            motor_speed = commanded_speed
            
        self.process_fft_result(self.active_freqs, self.active_mags, motor_speed, max_x)

    def update_data(self, adc, rate):
        # Read parameters
        w_type = self.cb_fft_window.currentText()
        domain = self.cb_fft_domain.currentText()
        try:
            max_x = float(self.txt_fft_max_x.text())
        except ValueError:
            max_x = 100.0
        
        # Read FFT Samples
        try:
            num_samples = int(self.txt_fft_samples.text())
            num_samples = max(256, num_samples)
        except ValueError:
            num_samples = 16384

        if num_samples > self.engine.max_points:
            self.engine.resize_buffers(num_samples)

        # Fetch actual samples from the engine
        _, adc_data = self.engine.get_latest_data(num_samples)
        if len(adc_data) < 128:
            return
            
        # Read new signal processing params
        zp_text = self.cb_zero_pad.currentText()
        zero_pad_factor = int(zp_text[0]) if zp_text[0].isdigit() else 1
        avg_text = self.cb_averaging.currentText()
        try:
            num_averages = int(avg_text.split()[0])
        except (ValueError, IndexError):
            num_averages = 1
            
        # Determine speed reference
        win = self.window()
        commanded_speed = 10.0
        if hasattr(win, 'settings') and win.settings is not None:
            commanded_speed = max(0.1, abs(win.settings.motor_speed))
            
        if self.chk_div_speed.isChecked():
            motor_speed = max(0.1, abs(self.engine.motor_speed))
        else:
            motor_speed = commanded_speed
        
        if hasattr(win, 'executor') and win.executor is not None:
            if self._future is None:
                from ..analysis import run_background_fft
                # Submit task to the main window's shared process pool (force Frequency domain for raw cache)
                self._future = win.executor.submit(
                    run_background_fft,
                    adc_data, rate, motor_speed, w_type, -1, "Frequency",
                    zero_pad_factor, num_averages
                )
            elif self._future.done():
                try:
                    freqs, mag = self._future.result()
                    self.active_freqs = freqs
                    self.active_mags = mag
                    self.replot_active()
                except Exception as e:
                    print(f"Async FFT page error: {e}")
                self._future = None
        else:
            # Synchronous fallback
            freqs, mag = self.analyzer.perform_fft(
                adc_data, rate, motor_speed, window_type=w_type, domain="Frequency",
                zero_pad_factor=zero_pad_factor, num_averages=num_averages
            )
            self.active_freqs = freqs
            self.active_mags = mag
            self.replot_active()

    def process_fft_result(self, freqs, mag, motor_speed, max_x):
        if len(freqs) == 0:
            return
            
        domain = self.cb_fft_domain.currentText()
        if domain == "Frequency":
            if self.chk_div_speed.isChecked():
                x_vals = freqs / motor_speed
            else:
                x_vals = freqs
        else:
            x_vals = freqs / motor_speed
            
        mask = x_vals <= max_x
        self.active_x = x_vals[mask]
        self.active_y = mag[mask]
        
        # Handle live data toggle
        if not self.chk_live_visible.isChecked():
            self.curve_active.setData([], [])
        else:
            self.curve_active.setData(self.active_x, self.active_y)
            
        # Determine the source for peak detection
        src_text = self.cb_peak_source.currentText()
        
        peak_x = np.array([])
        peak_y = np.array([])
        
        if "Live" in src_text:
            if len(self.active_x) > 0:
                peak_x = self.active_x
                peak_y = self.active_y
        else:
            # Parse slot index from name (e.g. "Slot 1: Baseline")
            try:
                slot_idx = int(src_text.split()[1].replace(':', ''))
                slot = self.slots[slot_idx]
                if slot["x"] is not None:
                    peak_x = slot["x"]
                    peak_y = slot["y"]
            except (ValueError, IndexError):
                pass
                
        if len(peak_x) == 0:
            self.scatter_peaks.setData([], [])
            for item in self.peak_text_items:
                self.plot_widget.removeItem(item)
            self.peak_text_items.clear()
            self.table_peaks.setRowCount(0)
            return
            
        # Peak detection parameters
        try:
            thresh = float(self.txt_threshold_db.text())
            max_peaks = int(self.txt_max_peaks.text())
        except ValueError:
            thresh = -40.0
            max_peaks = 8
            
        # Detect peaks on current scaled X-axis
        peaks_motor_speed = 1.0 # Peaks are already scaled on the X-axis we pass
        peaks = self.analyzer.detect_peaks(
            peak_x, peak_y, 
            threshold_db=thresh, max_peaks=max_peaks,
            min_order=0.1, max_order=max_x,
            bearing=None,
            motor_speed_hz=peaks_motor_speed
        )
        
        # Re-assign or assign labels as A-Z defaults unless custom label exists
        for i, p in enumerate(peaks):
            default_letter = chr(ord('A') + (i % 26))
            custom_lbl = self.get_custom_label(p.order)
            p.label = custom_lbl if custom_lbl is not None else default_letter
            
        # Clear old peak text labels from graph
        for item in self.peak_text_items:
            self.plot_widget.removeItem(item)
        self.peak_text_items.clear()
        
        # Populate table and plot items (block signals to avoid self-triggering itemChanged)
        self.table_peaks.blockSignals(True)
        self.table_peaks.setRowCount(len(peaks))
        
        peak_xs = []
        peak_ys = []
        y_log_mode = self.cb_fft_y_mode.currentText() == "Log (dB)"
        
        for i, p in enumerate(peaks):
            # Write to Table
            item_order = QTableWidgetItem(f"{p.order:.3f}")
            item_order.setFlags(item_order.flags() & ~Qt.ItemIsEditable)
            self.table_peaks.setItem(i, 0, item_order)
            
            item_mag = QTableWidgetItem(f"{p.magnitude:.5f}")
            item_mag.setFlags(item_mag.flags() & ~Qt.ItemIsEditable)
            self.table_peaks.setItem(i, 1, item_mag)
            
            item_lbl = QTableWidgetItem(p.label)
            item_lbl.setFlags(item_lbl.flags() | Qt.ItemIsEditable)
            self.table_peaks.setItem(i, 2, item_lbl)
            
            peak_xs.append(p.order)
            peak_ys.append(p.magnitude)
            
            # Draw text labels on the graph
            lbl = p.label if p.label else f"{p.order:.2f}"
            txt_item = pg.TextItem(text=lbl, color='#e06c75', anchor=(0.5, 1.2))
            
            # Position correctly based on Log/Linear scale
            y_pos = np.log10(p.magnitude) if y_log_mode else p.magnitude
            txt_item.setPos(p.order, y_pos)
            self.plot_widget.addItem(txt_item)
            self.peak_text_items.append(txt_item)
            
        self.table_peaks.blockSignals(False)
        self.scatter_peaks.setData(peak_xs, peak_ys)
        
    def capture_slot(self, slot_idx):
        if len(self.active_x) == 0:
            return
            
        self.slots[slot_idx]["x"] = self.active_x.copy()
        self.slots[slot_idx]["y"] = self.active_y.copy()
        
        # Update status text
        max_idx = np.argmax(self.active_y)
        peak_val = self.active_y[max_idx]
        peak_x = self.active_x[max_idx]
        
        self.slot_widgets[slot_idx]["status_lbl"].setText(f"Peak: {peak_val:.4f} @ {peak_x:.2f}")
        self.slot_widgets[slot_idx]["status_lbl"].setStyleSheet(f"color: {self.slots[slot_idx]['color']}; font-weight: bold;")
        
        self.replot_slots()
        self.replot_active()
        
    def replot_slots(self):
        for idx in [1, 2, 3, 4]:
            visible = self.slot_widgets[idx]["checkbox"].isChecked()
            slot = self.slots[idx]
            
            if visible and slot["x"] is not None:
                self.slot_curves[idx].setData(slot["x"], slot["y"])
            else:
                self.slot_curves[idx].setData([], [])
                
    def clear_single_slot(self, slot_idx):
        self.slots[slot_idx]["x"] = None
        self.slots[slot_idx]["y"] = None
        self.slot_widgets[slot_idx]["status_lbl"].setText("Empty")
        self.slot_widgets[slot_idx]["status_lbl"].setStyleSheet("color: #abb2bf; font-weight: normal;")
        
        self.replot_slots()
        self.replot_active()
        
    def clear_all_slots(self):
        for idx in [1, 2, 3, 4]:
            self.slots[idx]["x"] = None
            self.slots[idx]["y"] = None
            self.slot_widgets[idx]["status_lbl"].setText("Empty")
            self.slot_widgets[idx]["status_lbl"].setStyleSheet("color: #abb2bf; font-weight: normal;")
        self.replot_slots()
        self.replot_active()
 
    def take_fft_screenshot(self):
        import os
        from datetime import datetime
        os.makedirs(os.path.join("outputs", "screenshots"), exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = os.path.join("outputs", "screenshots", f"fft_plot_{ts}.png")
        pixmap = self.plot_widget.grab()
        pixmap.save(filepath)
