import numpy as np
import pyqtgraph as pg
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
from PySide6.QtCore import Qt

class LinearPlotWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        
        # Header Layout
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(5, 2, 5, 2)
        
        self.title_label = QLabel("Time Domain (3.0s)")
        self.title_label.setStyleSheet("font-weight: bold; color: #abb2bf;")
        header_layout.addWidget(self.title_label)
        
        header_layout.addStretch()
        
        self.btn_screenshot = QPushButton("📸")
        self.btn_screenshot.setFixedWidth(30)
        self.btn_screenshot.setStyleSheet("""
            QPushButton { background-color: #3b4048; border: 1px solid #5c6370; border-radius: 3px; padding: 2px; font-size: 8pt; color: white; }
            QPushButton:hover { background-color: #61afef; color: black; font-weight: bold; }
        """)
        self.btn_screenshot.clicked.connect(self.take_screenshot)
        header_layout.addWidget(self.btn_screenshot)
        
        layout.addLayout(header_layout)
        
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
        self.plot_widget.setLabel('left', 'Voltage (V) / Raw')
        self.plot_widget.setLabel('bottom', 'Time (s)')
        self.plot_widget.setMouseEnabled(x=False, y=True)
        self.curve_linear = self.plot_widget.plot(pen=pg.mkPen('#e5c07b', width=1))
        layout.addWidget(self.plot_widget)

    def update_data(self, adc, rate, window_s=3.0):
        n = min(len(adc), int(window_s * rate))
        if n == 0:
            return
        adc_win = adc[-n:]
        x_lin = np.linspace(0, len(adc_win) / rate, len(adc_win), dtype=np.float32)
        self.curve_linear.setData(x_lin, adc_win)
        self.title_label.setText(f"Time Domain ({window_s}s)")

    def take_screenshot(self):
        import os
        from datetime import datetime
        os.makedirs(os.path.join("outputs", "screenshots"), exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = os.path.join("outputs", "screenshots", f"time_domain_{ts}.png")
        pixmap = self.plot_widget.grab()
        pixmap.save(filepath)
