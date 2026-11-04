"""
Signal Database and Table Analysis Widget for MGF Radar V2.
Loads SQLite databases or CSV tables, extracts 3600 fixed angle points columns,
performs median averaging (verifying a minimum of 100 samples), plots the results,
and supports comparison slots.
"""
import os
import csv
import sqlite3
import numpy as np
import pyqtgraph as pg
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QGroupBox, QLabel, 
    QComboBox, QPushButton, QGridLayout, QCheckBox, QSplitter,
    QScrollArea, QFrame, QFileDialog, QMessageBox, QSizePolicy
)
from PySide6.QtCore import Qt, QTimer

from .control_panel import CollapsibleSection

class SignalAnalysisWidget(QWidget):
    def __init__(self, engine, parent=None):
        super().__init__(parent)
        self.engine = engine
        
        self.slots = {
            1: {"name": "Slot 1", "color": "#e06c75", "angles": None, "medians": None},
            2: {"name": "Slot 2", "color": "#e5c07b", "angles": None, "medians": None},
            3: {"name": "Slot 3", "color": "#98c379", "angles": None, "medians": None},
            4: {"name": "Slot 4", "color": "#61afef", "angles": None, "medians": None},
        }
        
        self.active_angles = None
        self.active_medians = None
        self.current_filepath = None
        
        self.gathering = False
        self.gathered_bins = [[] for _ in range(3600)]
        self.last_total_samples_received = 0
        
        self.gather_timer = QTimer(self)
        self.gather_timer.setInterval(50)  # Every 50 ms
        self.gather_timer.timeout.connect(self.on_gather_tick)
        
        self.setStyleSheet("""
            QGroupBox { border: 1px solid #5c6370; border-radius: 5px; margin-top: 12px; padding-top: 15px; font-weight: bold; }
            QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top left; top: 0px; left: 10px; color: #61afef; background-color: #282c34; padding: 0 5px; }
            QLabel { font-weight: normal; }
            QComboBox { background-color: #3b4048; border: 1px solid #5c6370; padding: 5px; color: white; border-radius: 3px; }
            QPushButton { background-color: #616a6b; border: none; padding: 8px; border-radius: 4px; color: white; }
            QPushButton:hover { background-color: #7f8c8d; }
            QPushButton#LoadBtn { background-color: #61afef; color: black; font-weight: bold; padding: 8px; }
            QPushButton#LoadBtn:hover { background-color: #8cc3f2; }
            QLabel#StatusVal { font-weight: bold; }
        """)
        
        self._build_ui()

    def _build_ui(self):
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
        scroll.setMinimumWidth(280)
        
        # ---- LEFT PANEL: CONTROLS ----
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(5, 5, 5, 5)
        
        # Guide
        grp_guide = QGroupBox()
        lay_guide = QVBoxLayout(grp_guide)
        lbl_guide = QLabel(
            "1. Click 'Load Data File' to open an SQLite database or CSV table.\n"
            "2. If database loaded, select the target table from the dropdown.\n"
            "3. The system extracts 3600 fixed angle points columns (from 0.0 to 359.9°).\n"
            "4. A minimum of 100 rows (samples) is verified, and the median is plotted."
        )
        lbl_guide.setWordWrap(True)
        lay_guide.addWidget(lbl_guide)
        self.sect_guide = CollapsibleSection("Guide", grp_guide)
        left_layout.addWidget(self.sect_guide)
        
        # File and Table Selector
        grp_select = QGroupBox()
        lay_select = QVBoxLayout(grp_select)
        
        self.btn_load = QPushButton("Load Data File")
        self.btn_load.setObjectName("LoadBtn")
        self.btn_load.clicked.connect(self.select_file)
        lay_select.addWidget(self.btn_load)
        
        self.lbl_filename = QLabel("No file loaded")
        self.lbl_filename.setStyleSheet("color: #abb2bf; font-style: italic;")
        self.lbl_filename.setWordWrap(True)
        lay_select.addWidget(self.lbl_filename)
        
        lay_select.addWidget(QLabel("Database Table:"))
        self.cb_tables = QComboBox()
        self.cb_tables.setEnabled(False)
        self.cb_tables.addItem("N/A")
        self.cb_tables.currentTextChanged.connect(self.on_table_changed)
        lay_select.addWidget(self.cb_tables)
        
        # Gathering Controls
        self.btn_gather = QPushButton("Start Sample Gathering")
        self.btn_gather.setStyleSheet("background-color: #98c379; color: black; font-weight: bold; margin-top: 5px;")
        self.btn_gather.clicked.connect(self.toggle_gathering)
        lay_select.addWidget(self.btn_gather)
        
        self.sect_select = CollapsibleSection("Data Source Selection", grp_select)
        self.sect_select.content.setVisible(True)
        self.sect_select.update_header()
        left_layout.addWidget(self.sect_select)
        
        # Analysis Info / Validation
        grp_info = QGroupBox()
        lay_info = QGridLayout(grp_info)
        
        lay_info.addWidget(QLabel("Samples Found:"), 0, 0)
        self.lbl_samples = QLabel("—")
        self.lbl_samples.setObjectName("StatusVal")
        lay_info.addWidget(self.lbl_samples, 0, 1)
        
        lay_info.addWidget(QLabel("Columns Parsed:"), 1, 0)
        self.lbl_columns = QLabel("—")
        self.lbl_columns.setObjectName("StatusVal")
        lay_info.addWidget(self.lbl_columns, 1, 1)
        
        lay_info.addWidget(QLabel("Validation Status:"), 2, 0)
        self.lbl_validation = QLabel("No Data")
        self.lbl_validation.setObjectName("StatusVal")
        self.lbl_validation.setStyleSheet("color: #abb2bf;")
        lay_info.addWidget(self.lbl_validation, 2, 1)
        
        self.sect_info = CollapsibleSection("Analysis Status", grp_info)
        self.sect_info.content.setVisible(True)
        self.sect_info.update_header()
        left_layout.addWidget(self.sect_info)
        
        # Comparison Slots
        grp_slots = QGroupBox()
        lay_slots = QVBoxLayout(grp_slots)
        
        self.slot_widgets = {}
        for idx in [1, 2, 3, 4]:
            slot_row = QWidget()
            row_lay = QHBoxLayout(slot_row)
            row_lay.setContentsMargins(0, 2, 0, 2)
            
            cb_visible = QCheckBox()
            cb_visible.setChecked(True)
            cb_visible.stateChanged.connect(self.replot_slots)
            row_lay.addWidget(cb_visible)
            
            slot_name = self.slots[idx]["name"]
            lbl_name = QLabel(f"<b>{slot_name}</b>")
            lbl_name.setFixedWidth(50)
            row_lay.addWidget(lbl_name)
            
            btn_cap = QPushButton("Capture")
            btn_cap.setFixedWidth(50)
            btn_cap.setStyleSheet("background-color: #3b4048; font-size: 8pt; padding: 4px; color: white;")
            btn_cap.clicked.connect(lambda _, s_idx=idx: self.capture_slot(s_idx))
            row_lay.addWidget(btn_cap)
            
            btn_clr = QPushButton("Clear")
            btn_clr.setFixedWidth(40)
            btn_clr.setStyleSheet("background-color: #3b4048; font-size: 8pt; padding: 4px; color: white;")
            btn_clr.clicked.connect(lambda _, s_idx=idx: self.clear_slot(s_idx))
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
        
        left_layout.addStretch()
        scroll.setWidget(left_panel)
        self.splitter.addWidget(scroll)
        
        # ---- RIGHT PANEL: GRAPH VIEW ----
        graph_container = QWidget()
        graph_lay = QVBoxLayout(graph_container)
        graph_lay.setContentsMargins(0, 0, 0, 0)
        graph_lay.setSpacing(2)
        
        header_lay = QHBoxLayout()
        header_lay.setContentsMargins(5, 2, 5, 2)
        lbl_title = QLabel("Median Signal Curve vs. Angle")
        lbl_title.setStyleSheet("font-weight: bold; color: #abb2bf;")
        header_lay.addWidget(lbl_title)
        header_lay.addStretch()
        
        btn_shot = QPushButton("📸")
        btn_shot.setFixedWidth(30)
        btn_shot.setStyleSheet("""
            QPushButton { background-color: #3b4048; border: 1px solid #5c6370; border-radius: 3px; padding: 2px; font-size: 8pt; color: white; }
            QPushButton:hover { background-color: #61afef; color: black; font-weight: bold; }
        """)
        btn_shot.clicked.connect(self.take_plot_screenshot)
        header_lay.addWidget(btn_shot)
        graph_lay.addLayout(header_lay)
        
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setLabel('bottom', 'Angle (deg)')
        self.plot_widget.setLabel('left', 'Value')
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
        self.plot_widget.setXRange(0, 360)
        
        self.curve_active = self.plot_widget.plot(pen=pg.mkPen('#abb2bf', width=2))
        
        self.slot_curves = {}
        for idx in [1, 2, 3, 4]:
            self.slot_curves[idx] = self.plot_widget.plot(pen=pg.mkPen(self.slots[idx]["color"], width=1.5))
            
        graph_lay.addWidget(self.plot_widget)
        self.splitter.addWidget(graph_container)
        self.splitter.setSizes([320, 900])

    def select_file(self):
        filepath, _ = QFileDialog.getOpenFileName(
            self, "Open Database or Table File", "", "Database/Table Files (*.db *.sqlite *.csv);;SQLite Files (*.db *.sqlite);;CSV Files (*.csv)"
        )
        if not filepath:
            return
            
        self.current_filepath = filepath
        self.lbl_filename.setText(os.path.basename(filepath))
        self.lbl_filename.setStyleSheet("color: #98c379; font-weight: bold;")
        
        # Check if CSV or SQLite
        ext = os.path.splitext(filepath)[1].lower()
        if ext in ['.db', '.sqlite']:
            # Load tables of SQLite database
            self.cb_tables.blockSignals(True)
            self.cb_tables.clear()
            try:
                conn = sqlite3.connect(filepath)
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                tables = [row[0] for row in cursor.fetchall() if not row[0].startswith("sqlite_")]
                conn.close()
                
                if tables:
                    self.cb_tables.addItems(tables)
                    self.cb_tables.setEnabled(True)
                    self.cb_tables.blockSignals(False)
                    self.load_sqlite_table(tables[0])
                else:
                    self.cb_tables.addItem("No Tables")
                    self.cb_tables.setEnabled(False)
                    self.cb_tables.blockSignals(False)
                    QMessageBox.warning(self, "Empty Database", "No user tables found in the database.")
            except Exception as e:
                self.cb_tables.addItem("Error")
                self.cb_tables.setEnabled(False)
                self.cb_tables.blockSignals(False)
                QMessageBox.critical(self, "Database Error", f"Failed to inspect SQLite database: {e}")
        else:
            # CSV file
            self.cb_tables.blockSignals(True)
            self.cb_tables.clear()
            self.cb_tables.addItem("[CSV File]")
            self.cb_tables.setEnabled(False)
            self.cb_tables.blockSignals(False)
            self.load_csv_table()

    def on_table_changed(self, text):
        if not text or text == "N/A" or text == "No Tables" or text == "Error" or text == "[CSV File]":
            return
        self.load_sqlite_table(text)

    def load_sqlite_table(self, table_name):
        if not self.current_filepath:
            return
            
        try:
            conn = sqlite3.connect(self.current_filepath)
            cursor = conn.cursor()
            cursor.execute(f"PRAGMA table_info({table_name})")
            columns = [row[1] for row in cursor.fetchall()]
            
            # Map columns to angles
            angles, col_indices = self._map_columns_to_angles(columns)
            
            # Select columns
            select_cols = ", ".join([f'"{columns[idx]}"' for idx in col_indices])
            cursor.execute(f'SELECT {select_cols} FROM {table_name}')
            rows = cursor.fetchall()
            conn.close()
            
            data_rows = []
            for r in rows:
                try:
                    data_rows.append([float(val) if val is not None else 0.0 for val in r])
                except ValueError:
                    pass # Skip rows with non-numeric data
            
            self._process_and_plot(angles, data_rows)
        except Exception as e:
            QMessageBox.critical(self, "Load Error", f"Failed to load table '{table_name}': {e}")

    def load_csv_table(self):
        if not self.current_filepath:
            return
            
        try:
            with open(self.current_filepath, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                headers = next(reader, None)
                if not headers:
                    raise ValueError("CSV file is empty")
                
                angles, col_indices = self._map_columns_to_angles(headers)
                
                data_rows = []
                for row in reader:
                    if not row:
                        continue
                    try:
                        parsed_row = [float(row[idx]) for idx in col_indices]
                        data_rows.append(parsed_row)
                    except (ValueError, IndexError):
                        pass # Skip invalid rows
            
            self._process_and_plot(angles, data_rows)
        except Exception as e:
            QMessageBox.critical(self, "Load Error", f"Failed to load CSV: {e}")

    def _map_columns_to_angles(self, columns):
        # Scan for numeric values in column names representing angle points (0.0 to 359.9)
        numeric_cols = []
        for idx, col_name in enumerate(columns):
            try:
                val = float(col_name)
                # Cap angles at 360 degrees
                if 0.0 <= val < 360.0:
                    numeric_cols.append((val, idx))
            except ValueError:
                pass
                
        if len(numeric_cols) >= 3600:
            numeric_cols.sort(key=lambda x: x[0])
            angles = [x[0] for x in numeric_cols[:3600]]
            col_indices = [x[1] for x in numeric_cols[:3600]]
        elif len(columns) >= 3600:
            col_indices = list(range(len(columns)))
            if len(columns) == 3601:
                # Skip index column if non-numeric
                try:
                    float(columns[0])
                except ValueError:
                    col_indices = col_indices[1:]
            col_indices = col_indices[:3600]
            angles = [i * 0.1 for i in range(3600)]
        else:
            raise ValueError(f"Table/file must have at least 3600 columns (found {len(columns)})")
            
        return np.array(angles), col_indices

    def _process_and_plot(self, angles, data_rows):
        num_samples = len(data_rows)
        self.lbl_samples.setText(str(num_samples))
        self.lbl_columns.setText(str(len(angles)))
        
        if num_samples == 0:
            self.lbl_validation.setText("Empty Data")
            self.lbl_validation.setStyleSheet("color: #e06c75; font-weight: bold;")
            self.curve_active.setData([], [])
            self.active_angles = None
            self.active_medians = None
            return
            
        # Check minimum 100 samples validation
        if num_samples < 100:
            self.lbl_validation.setText(f"Warning: Low Samples ({num_samples})")
            self.lbl_validation.setStyleSheet("color: #d19a66; font-weight: bold;")
        else:
            self.lbl_validation.setText("Valid (Good)")
            self.lbl_validation.setStyleSheet("color: #98c379; font-weight: bold;")
            
        # Calculate median of each angle point
        data_arr = np.array(data_rows, dtype=np.float32)
        medians = np.median(data_arr, axis=0)
        
        self.active_angles = angles
        self.active_medians = medians
        
        self.curve_active.setData(angles, medians)
        self.replot_slots()

    def capture_slot(self, idx):
        if self.active_angles is None or self.active_medians is None:
            QMessageBox.warning(self, "No Active Data", "Please load a database or table before capturing to slots.")
            return
            
        self.slots[idx]["angles"] = self.active_angles.copy()
        self.slots[idx]["medians"] = self.active_medians.copy()
        
        self.slot_widgets[idx]["status_lbl"].setText("Captured")
        self.slot_widgets[idx]["status_lbl"].setStyleSheet("color: #98c379; font-weight: bold;")
        self.replot_slots()

    def clear_slot(self, idx):
        self.slots[idx]["angles"] = None
        self.slots[idx]["medians"] = None
        
        self.slot_widgets[idx]["status_lbl"].setText("Empty")
        self.slot_widgets[idx]["status_lbl"].setStyleSheet("color: #abb2bf; font-weight: normal;")
        self.replot_slots()

    def clear_all_slots(self):
        for idx in [1, 2, 3, 4]:
            self.clear_slot(idx)

    def replot_slots(self):
        for idx in [1, 2, 3, 4]:
            slot = self.slots[idx]
            visible = self.slot_widgets[idx]["checkbox"].isChecked()
            
            if visible and slot["angles"] is not None:
                self.slot_curves[idx].setData(slot["angles"], slot["medians"])
            else:
                self.slot_curves[idx].setData([], [])

    def take_plot_screenshot(self):
        import os
        from datetime import datetime
        os.makedirs(os.path.join("outputs", "screenshots"), exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = os.path.join("outputs", "screenshots", f"signal_analysis_plot_{ts}.png")
        pixmap = self.plot_widget.grab()
        pixmap.save(filepath)
        
        # Log to main window if possible
        win = self.window()
        if hasattr(win, 'log'):
            win.log(f"Saved signal analysis screenshot to {os.path.basename(filepath)}")

    def toggle_gathering(self):
        if not self.gathering:
            # Start gathering
            self.gathered_bins = [[] for _ in range(3600)]
            self.last_total_samples_received = self.engine.total_samples_received
            self.gathering = True
            self.btn_gather.setText("Stop Sample Gathering")
            self.btn_gather.setStyleSheet("background-color: #e06c75; color: black; font-weight: bold; margin-top: 5px;")
            
            # Disable loading buttons to prevent conflict
            self.btn_load.setEnabled(False)
            self.cb_tables.setEnabled(False)
            
            self.lbl_filename.setText("Gathering live data...")
            self.lbl_filename.setStyleSheet("color: #61afef; font-style: italic;")
            self.lbl_samples.setText("0")
            self.lbl_columns.setText("3600")
            self.lbl_validation.setText("Gathering...")
            self.lbl_validation.setStyleSheet("color: #61afef;")
            
            self.gather_timer.start()
        else:
            # Stop gathering
            self.gathering = False
            self.gather_timer.stop()
            self.btn_gather.setText("Start Sample Gathering")
            self.btn_gather.setStyleSheet("background-color: #98c379; color: black; font-weight: bold; margin-top: 5px;")
            
            self.btn_load.setEnabled(True)
            if self.cb_tables.count() > 1 or (self.cb_tables.count() == 1 and self.cb_tables.itemText(0) != "N/A" and self.cb_tables.itemText(0) != "[CSV File]"):
                self.cb_tables.setEnabled(True)
                
            self.lbl_filename.setText("Live Gathered Data")
            self.lbl_filename.setStyleSheet("color: #98c379; font-weight: bold;")
            
            # Compute results
            angles = np.array([i * 0.1 for i in range(3600)], dtype=np.float32)
            medians = np.zeros(3600, dtype=np.float32)
            counts = []
            
            for i in range(3600):
                bin_vals = self.gathered_bins[i]
                counts.append(len(bin_vals))
                if len(bin_vals) > 0:
                    medians[i] = np.median(bin_vals)
                else:
                    medians[i] = 0.0
                    
            min_samples = min(counts)
            self.lbl_samples.setText(f"Min: {min_samples} (Avg: {sum(counts)/3600.0:.1f})")
            
            if min_samples < 100:
                self.lbl_validation.setText(f"Warning: Low Samples ({min_samples} < 100)")
                self.lbl_validation.setStyleSheet("color: #d19a66; font-weight: bold;")
            else:
                self.lbl_validation.setText("Valid (Good)")
                self.lbl_validation.setStyleSheet("color: #98c379; font-weight: bold;")
                
            self.active_angles = angles
            self.active_medians = medians
            self.curve_active.setData(angles, medians)
            self.replot_slots()

    def on_gather_tick(self):
        total_rec = self.engine.total_samples_received
        diff = total_rec - self.last_total_samples_received
        if diff <= 0:
            return
            
        enc_deg, adc_val = self.engine.get_latest_data(diff)
        self.last_total_samples_received = total_rec
        
        if len(adc_val) == 0:
            return
            
        for deg, val in zip(enc_deg, adc_val):
            bin_idx = int(round(deg * 10)) % 3600
            self.gathered_bins[bin_idx].append(val)
            
        counts = [len(x) for x in self.gathered_bins]
        min_samples = min(counts)
        avg_samples = sum(counts) / 3600.0
        self.lbl_samples.setText(f"Avg: {avg_samples:.1f} (Min: {min_samples})")
