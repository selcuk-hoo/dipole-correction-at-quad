import numpy as np
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
from vispy import scene

PLOT_RADIUS = 48.0

class RadarPlotWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Header Layout
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(5, 2, 5, 2)
        
        title_label = QLabel("Polar Plot (Radar)")
        title_label.setStyleSheet("font-weight: bold; color: #61afef;")
        header_layout.addWidget(title_label)
        
        self.lbl_scale = QLabel("Range: Auto")
        self.lbl_scale.setStyleSheet("color: #abb2bf; font-size: 9pt; font-family: Segoe UI;")
        header_layout.addWidget(self.lbl_scale)
        
        self.btn_autoscale = QPushButton("Auto Scale")
        self.btn_autoscale.setCheckable(True)
        self.btn_autoscale.setChecked(True)
        self.btn_autoscale.setFixedWidth(80)
        self.btn_autoscale.setStyleSheet("""
            QPushButton { background-color: #3b4048; border: 1px solid #5c6370; border-radius: 3px; padding: 2px; font-size: 8pt; color: white; }
            QPushButton:hover { background-color: #4b5263; }
            QPushButton:checked { background-color: #61afef; color: black; font-weight: bold; }
        """)
        
        self.btn_clear = QPushButton("Clear")
        self.btn_clear.setFixedWidth(50)
        self.btn_clear.setStyleSheet("""
            QPushButton { background-color: #3b4048; border: 1px solid #5c6370; border-radius: 3px; padding: 2px; font-size: 8pt; color: white; }
            QPushButton:hover { background-color: #e06c75; color: black; font-weight: bold; }
        """)
        
        self.btn_screenshot = QPushButton("📸")
        self.btn_screenshot.setFixedWidth(30)
        self.btn_screenshot.setStyleSheet("""
            QPushButton { background-color: #3b4048; border: 1px solid #5c6370; border-radius: 3px; padding: 2px; font-size: 8pt; color: white; }
            QPushButton:hover { background-color: #61afef; color: black; font-weight: bold; }
        """)
        self.btn_screenshot.clicked.connect(self.take_screenshot)
        
        header_layout.addStretch()
        header_layout.addWidget(self.btn_autoscale)
        header_layout.addWidget(self.btn_clear)
        header_layout.addWidget(self.btn_screenshot)
        
        layout.addLayout(header_layout)
        
        self.canvas = scene.SceneCanvas(keys='interactive', show=False, bgcolor='#282c34')
        self.canvas.native.setMinimumHeight(150)
        layout.addWidget(self.canvas.native)
        
        self.view = self.canvas.central_widget.add_view()
        self.view.camera = 'panzoom'
        self.view.camera.aspect = 1.0
        self.view.camera.rect = (-55, -55, 110, 110)
        
        self._init_radar_grid()

    def _init_radar_grid(self):
        grid_color = (1.0, 1.0, 1.0, 0.15)
        theta = np.linspace(0, 2 * np.pi, 200)
        for r in [12, 24, 36, 48]:
            pos = np.column_stack((r * np.cos(theta), r * np.sin(theta)))
            scene.visuals.Line(pos=pos, color=grid_color, parent=self.view.scene)
        for deg in range(0, 360, 30):
            rad = np.radians(deg)
            pos = np.array([[0, 0], [48 * np.cos(rad), 48 * np.sin(rad)]])
            scene.visuals.Line(pos=pos, color=grid_color, parent=self.view.scene)
            
        self.scatter_pos = scene.visuals.Markers(parent=self.view.scene)
        self.scatter_neg = scene.visuals.Markers(parent=self.view.scene)
        self.sweep_line = scene.visuals.Line(parent=self.view.scene,
                                              color='#98c379', width=2.0)
            
        # Quadrupole reference lines at 45, 135, 225, 315 degrees
        quad_color = (0.82, 0.60, 0.40, 0.5)  # Warm orange (#d19a66) with alpha
        for deg in [45, 135, 225, 315]:
            rad = np.radians(deg)
            pos = np.array([[0, 0], [48 * np.cos(rad), 48 * np.sin(rad)]])
            scene.visuals.Line(pos=pos, color=quad_color, parent=self.view.scene, width=1.5)

    def update_data(self, polar_bins, current_angle_deg, mode_voltage, gain=1.0, vref=2.5):
        theta = np.deg2rad(np.arange(360))

        # Auto-scale: use the actual peak value so the plot always fills the ring.
        # Fall back to the physical full-scale (VREF/gain) when no signal is present.
        if mode_voltage:
            full_scale = vref / max(gain, 1.0)
        else:
            full_scale = 2147483647.0

        if self.btn_autoscale.isChecked():
            peak = np.max(np.abs(polar_bins))
            max_val = max(peak, full_scale * 0.01)  # never divide by zero; show grid even with no signal
            self.lbl_scale.setText(f"Range: Max {max_val:.4f} V" if mode_voltage else f"Range: Max {int(max_val)}")
        else:
            max_val = full_scale
            self.lbl_scale.setText(f"Range: Full Scale ({max_val:.4f} V)" if mode_voltage else f"Range: Full Scale")

        radii = (np.abs(polar_bins) / max_val) * PLOT_RADIUS
        x_pol = radii * np.cos(theta)
        y_pol = radii * np.sin(theta)

        mask = polar_bins >= 0
        if np.any(mask):
            self.scatter_pos.set_data(
                np.column_stack((x_pol[mask], y_pol[mask])),
                edge_color=None, face_color='#e06c75', size=5)
        else:
            self.scatter_pos.set_data(np.zeros((0, 2)))

        if np.any(~mask):
            self.scatter_neg.set_data(
                np.column_stack((x_pol[~mask], y_pol[~mask])),
                edge_color=None, face_color='#61afef', size=5)
        else:
            self.scatter_neg.set_data(np.zeros((0, 2)))

        ang = np.deg2rad(current_angle_deg)
        self.sweep_line.set_data(
            pos=np.array([[0, 0], [PLOT_RADIUS * np.cos(ang), PLOT_RADIUS * np.sin(ang)]]))

    def take_screenshot(self):
        import os
        from datetime import datetime
        os.makedirs(os.path.join("outputs", "screenshots"), exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = os.path.join("outputs", "screenshots", f"polar_plot_{ts}.png")
        pixmap = self.canvas.native.grab()
        pixmap.save(filepath)
