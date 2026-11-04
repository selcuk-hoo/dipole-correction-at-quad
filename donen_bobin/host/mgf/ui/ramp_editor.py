"""
Speed Ramp Profile Editor Widget for MGF Radar V2.
Allows users to construct complex motor acceleration/deceleration profiles,
visualize the speed curve, and execute it in real time via timer-driven commands.
"""
import numpy as np
import pyqtgraph as pg
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QPushButton, QLabel, 
    QTableWidget, QTableWidgetItem, QHeaderView, QGroupBox, QSplitter,
    QScrollArea, QFrame
)
from PySide6.QtCore import QTimer, Slot, Qt

from .control_panel import CollapsibleSection

class RampEditorWidget(QWidget):
    def __init__(self, conn, parent=None):
        super().__init__(parent)
        self.conn = conn
        
        self.setStyleSheet("""
            QTableWidget { background-color: #21252b; border: 1px solid #5c6370; color: white; gridline-color: #3b4048; }
            QTableWidget QHeaderView::section { background-color: #282c34; border: 1px solid #5c6370; padding: 4px; color: #61afef; }
            QPushButton { background-color: #616a6b; border: none; padding: 8px; border-radius: 4px; color: white; }
            QPushButton:hover { background-color: #7f8c8d; }
            QPushButton#RunBtn { background-color: #98c379; color: black; font-weight: bold; }
            QPushButton#RunBtn:hover { background-color: #a6d88c; }
            QPushButton#StopBtn { background-color: #e06c75; font-weight: bold; }
            QPushButton#StopBtn:hover { background-color: #e5858b; }
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
        scroll.setMinimumWidth(300)
        
        # ---- LEFT PANEL: SEGMENTS CONFIG & ACTIONS ----
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(5, 5, 5, 5)
        
        grp_table = QGroupBox()
        tbl_lay = QVBoxLayout(grp_table)
        
        self.table = QTableWidget(3, 2)
        self.table.setHorizontalHeaderLabels(["Target Speed (Hz)", "Duration (s)"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        
        # Default profile segments
        default_segments = [(5.0, 5.0), (5.0, 5.0), (0.0, 5.0)]
        for i, (spd, dur) in enumerate(default_segments):
            self.table.setItem(i, 0, QTableWidgetItem(f"{spd:.1f}"))
            self.table.setItem(i, 1, QTableWidgetItem(f"{dur:.1f}"))
            
        self.table.itemChanged.connect(self.update_plot)
        tbl_lay.addWidget(self.table)
        
        h_btns = QHBoxLayout()
        btn_add = QPushButton("Add Segment")
        btn_add.clicked.connect(self.add_segment)
        btn_del = QPushButton("Delete Segment")
        btn_del.clicked.connect(self.delete_segment)
        h_btns.addWidget(btn_add)
        h_btns.addWidget(btn_del)
        tbl_lay.addLayout(h_btns)
        
        self.sect_table = CollapsibleSection("Ramp Profile Segments", grp_table)
        self.sect_table.content.setVisible(True)
        self.sect_table.update_header()
        left_layout.addWidget(self.sect_table)
        
        # Execution controls
        grp_run = QGroupBox()
        run_lay = QVBoxLayout(grp_run)
        
        self.lbl_status = QLabel("Status: Idle")
        self.lbl_status.setStyleSheet("font-weight: bold; font-size: 11pt;")
        self.lbl_current = QLabel("Current Target Speed: 0.0 Hz")
        
        self.btn_run = QPushButton("RUN PROFILE")
        self.btn_run.setObjectName("RunBtn")
        self.btn_run.clicked.connect(self.start_profile)
        
        self.btn_stop = QPushButton("STOP MOTOR")
        self.btn_stop.setObjectName("StopBtn")
        self.btn_stop.clicked.connect(self.stop_profile)
        
        run_lay.addWidget(self.lbl_status)
        run_lay.addWidget(self.lbl_current)
        run_lay.addWidget(self.btn_run)
        run_lay.addWidget(self.btn_stop)
        
        self.sect_run = CollapsibleSection("Execution", grp_run)
        self.sect_run.content.setVisible(True)
        self.sect_run.update_header()
        left_layout.addWidget(self.sect_run)
        left_layout.addStretch()
        scroll.setWidget(left_panel)
        self.splitter.addWidget(scroll)
        
        # ---- RIGHT PANEL: CHART VIEW ----
        self.plot_widget = pg.PlotWidget(title="Speed vs Time Profile")
        self.plot_widget.setLabel('bottom', 'Time (s)')
        self.plot_widget.setLabel('left', 'Speed (Hz)')
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
        self.plot_widget.setYRange(0, 15)
        
        # Curve representing the speed profile
        self.curve = self.plot_widget.plot(pen=pg.mkPen('#61afef', width=2))
        
        # Cursor representing current playback point
        self.cursor = pg.InfiniteLine(pos=0, angle=90, pen=pg.mkPen('#e06c75', width=1.5, style=pg.QtCore.Qt.DashLine))
        self.plot_widget.addItem(self.cursor)
        
        self.splitter.addWidget(self.plot_widget)
        self.splitter.setSizes([380, 800])
        
        # Timer for profile execution
        self.exec_timer = QTimer(self)
        self.exec_timer.setInterval(100)  # Update every 100 ms
        self.exec_timer.timeout.connect(self.step_profile)
        
        # Run state
        self.profile_pts = []
        self.total_time = 0.0
        self.elapsed = 0.0
        
        self.update_plot()
        
    def add_segment(self):
        r = self.table.rowCount()
        self.table.insertRow(r)
        self.table.setItem(r, 0, QTableWidgetItem("5.0"))
        self.table.setItem(r, 1, QTableWidgetItem("5.0"))
        self.update_plot()
        
    def delete_segment(self):
        curr_row = self.table.currentRow()
        if curr_row >= 0:
            self.table.removeRow(curr_row)
            self.update_plot()
            
    def _parse_profile(self):
        """Parse values from table to construct time-speed profile points."""
        pts = [(0.0, 0.0)] # Starting point: (time, speed)
        curr_time = 0.0
        
        for r in range(self.table.rowCount()):
            item_spd = self.table.item(r, 0)
            item_dur = self.table.item(r, 1)
            
            if not item_spd or not item_dur:
                continue
                
            try:
                spd = float(item_spd.text())
                dur = float(item_dur.text())
                if dur < 0: dur = 0.0
                if spd > 25.0:
                    spd = 25.0
                    self.table.blockSignals(True)
                    item_spd.setText("25.0")
                    self.table.blockSignals(False)
                elif spd < -25.0:
                    spd = -25.0
                    self.table.blockSignals(True)
                    item_spd.setText("-25.0")
                    self.table.blockSignals(False)
                curr_time += dur
                pts.append((curr_time, spd))
            except ValueError:
                pass
                
        return pts
        
    def update_plot(self):
        pts = self._parse_profile()
        if len(pts) == 0:
            return
            
        t_arr = [p[0] for p in pts]
        s_arr = [p[1] for p in pts]
        
        self.curve.setData(t_arr, s_arr)
        
        max_t = max(t_arr) if len(t_arr) > 0 else 10.0
        min_s = min(s_arr) if len(s_arr) > 0 else -10.0
        max_s = max(s_arr) if len(s_arr) > 0 else 10.0
        
        self.plot_widget.setXRange(0, max_t * 1.05)
        pad_s = max(1.0, (max_s - min_s) * 0.1)
        self.plot_widget.setYRange(min_s - pad_s, max_s + pad_s)
        
    def start_profile(self):
        if not self.conn.connected:
            self.lbl_status.setText("Status: Not Connected")
            return
            
        self.profile_pts = self._parse_profile()
        if len(self.profile_pts) <= 1:
            return
            
        self.total_time = self.profile_pts[-1][0]
        self.elapsed = 0.0
        self.cursor.setValue(0.0)
        
        self.lbl_status.setText("Status: Running")
        self.btn_run.setEnabled(False)
        
        self.exec_timer.start()
        
    def step_profile(self):
        self.elapsed += 0.1
        self.cursor.setValue(self.elapsed)
        
        if self.elapsed >= self.total_time:
            self.stop_profile()
            self.lbl_status.setText("Status: Finished")
            return
            
        # Interpolate current target speed
        speed = 0.0
        for i in range(len(self.profile_pts) - 1):
            t1, s1 = self.profile_pts[i]
            t2, s2 = self.profile_pts[i+1]
            if t1 <= self.elapsed <= t2:
                fraction = (self.elapsed - t1) / (t2 - t1)
                speed = s1 + fraction * (s2 - s1)
                break
                
        self.lbl_current.setText(f"Current Target Speed: {speed:.2f} Hz")
        
        # Send CMD_SET_MOTOR_SPEED to stator (send_command handles float->u32 encoding)
        from .. import protocol
        self.conn.send_command(protocol.CMD_SET_MOTOR_SPEED, speed)
        
    def stop_profile(self):
        self.exec_timer.stop()
        self.btn_run.setEnabled(True)
        self.lbl_status.setText("Status: Idle")
        self.lbl_current.setText("Current Target Speed: 0.0 Hz")
        
        # Stop motor immediately
        from .. import protocol
        self.conn.send_command(protocol.CMD_SET_MOTOR_SPEED, 0.0)
