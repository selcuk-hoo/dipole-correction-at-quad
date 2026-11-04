from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGroupBox, QPushButton, QTextEdit
)
from PySide6.QtCore import Qt

from .control_panel import CollapsibleSection

class StatusBarWidget(QWidget):
    def __init__(self, engine):
        super().__init__()
        self.engine = engine
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # Stats Label
        self.lbl_stats = QLabel("Rate: 0 SPS")
        self.lbl_stats.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.lbl_stats)

        # Live Data
        live_grp = QGroupBox("Live Data")
        live_lay = QVBoxLayout(live_grp)
        self.lbl_live_val = QLabel("+0.00000000 V")
        self.lbl_live_val.setObjectName("LiveVal")
        self.lbl_live_val.setAlignment(Qt.AlignCenter)
        
        self.lbl_live_enc = QLabel("Enc: 00000")
        self.lbl_live_enc.setObjectName("LiveEnc")
        self.lbl_live_enc.setAlignment(Qt.AlignCenter)
        
        self.lbl_minmax_v = QLabel("Voltage Min: 0.000 | Max: 0.000")
        self.lbl_peak_peak_v = QLabel("Voltage P-P: 0.00000 V")
        self.lbl_minmax_r = QLabel("Raw Min: 0 | Max: 0")
        self.lbl_ref_info = QLabel("Reference: Internal (2.50V)")
        
        btn_clear = QPushButton("Clear Min-Max")
        btn_clear.clicked.connect(self.engine.reset_min_max)
        
        for w in (self.lbl_live_val, self.lbl_live_enc,
                  self.lbl_minmax_v, self.lbl_peak_peak_v, self.lbl_minmax_r,
                  self.lbl_ref_info, btn_clear):
            live_lay.addWidget(w)
            
        layout.addWidget(live_grp)

        # Log
        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.append("System started.")
        self.log_section = CollapsibleSection("System Logs", self.log_box)
        layout.addWidget(self.log_section)

    def log(self, msg: str):
        self.log_box.append(msg)
