"""
Macro System Widget for MGF Radar V2.
Allows scripting of motor speed changes, channel toggles, alignment scans,
and data acquisition loops.
"""
import time
import os
import json
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QGroupBox, QLabel, 
    QComboBox, QPushButton, QProgressBar, QTextEdit, 
    QFileDialog, QScrollArea, QSplitter, QInputDialog, QFrame
)
from PySide6.QtCore import QTimer, Slot, Qt

from .control_panel import CollapsibleSection

from .. import protocol

# Pre-defined built-in macro templates
PRESETS = {
    "Select a Preset...": "",
    
    "Full 4-Channel Coil Alignment": (
        "# Preset: Full 4-Channel Coil Alignment\n"
        "# Automatically rotates motor, switches through the 4 input channels,\n"
        "# performs alignment scans, and saves results in slot 1-4 on the Coil Alignment page.\n\n"
        "CLEAR_ALL_SLOTS\n"
        "SET_SERVO on\n"
        "SET_MOTOR_SPEED 25.0\n"
        "WAIT_SPEED 25.0 0.5\n"
        "WAIT 2.0\n\n"
        "# Capture Slot 1 (Morgan A)\n"
        "SET_CHANNEL AIN0-AIN1\n"
        "WAIT 1.5\n"
        "ALIGNMENT_SCAN\n"
        "CAPTURE_SLOT 1\n\n"
        "# Capture Slot 2 (Regular A)\n"
        "SET_CHANNEL AIN2-AIN3\n"
        "WAIT 1.5\n"
        "ALIGNMENT_SCAN\n"
        "CAPTURE_SLOT 2\n\n"
        "# Capture Slot 3 (Morgan B)\n"
        "SET_CHANNEL AIN4-AIN5\n"
        "WAIT 1.5\n"
        "ALIGNMENT_SCAN\n"
        "CAPTURE_SLOT 3\n\n"
        "# Capture Slot 4 (Regular B)\n"
        "SET_CHANNEL AIN6-AIN7\n"
        "WAIT 1.5\n"
        "ALIGNMENT_SCAN\n"
        "CAPTURE_SLOT 4\n\n"
        "# Ramp down motor\n"
        "SET_MOTOR_SPEED 0.0\n"
        "SET_SERVO off\n"
        "WAIT 1.0\n"
        "APPLY_OFFSET\n"
    ),
    
    "Speed Sweep & Recording": (
        "# Preset: Speed Sweep & Recording\n"
        "# Sweeps the motor from 10 to 25 Hz in increments,\n"
        "# recording 5 seconds of session data at each speed step.\n\n"
        "SET_CHANNEL AIN0-AIN1\n"
        "SET_GAIN 1x\n"
        "SET_RATE 2400 SPS\n"
        "SET_SERVO on\n\n"
        "# Step 1: 10 Hz\n"
        "SET_MOTOR_SPEED 10.0\n"
        "WAIT_SPEED 10.0 0.5\n"
        "WAIT 2.0\n"
        "START_RECORDING\n"
        "WAIT 5.0\n"
        "STOP_RECORDING\n\n"
        "# Step 2: 20 Hz\n"
        "SET_MOTOR_SPEED 20.0\n"
        "WAIT_SPEED 20.0 0.5\n"
        "WAIT 2.0\n"
        "START_RECORDING\n"
        "WAIT 5.0\n"
        "STOP_RECORDING\n\n"
        "# Step 3: 25 Hz\n"
        "SET_MOTOR_SPEED 25.0\n"
        "WAIT_SPEED 25.0 0.5\n"
        "WAIT 2.0\n"
        "START_RECORDING\n"
        "WAIT 5.0\n"
        "STOP_RECORDING\n\n"
        "# Safe motor stop\n"
        "SET_MOTOR_SPEED 0.0\n"
        "SET_SERVO off\n"
    ),
    
    "Device Self-Calibration Sequence": (
        "# Preset: Device Self-Calibration Sequence\n"
        "# Resets internal ADC calibration and runs offset calibration.\n\n"
        "RESET_CALIBRATION\n"
        "WAIT 1.5\n"
        "CALIBRATE_SELF_OFFSET\n"
        "WAIT 3.0\n"
        "CALIBRATE_SYS_OFFSET\n"
        "WAIT 3.0\n"
        "RESUME_STREAM\n"
    ),
    
    "Full 4-Channel FFT Capture": (
        "# Preset: Full 4-Channel FFT Capture\n"
        "# Automatically rotates motor, switches through the 4 input channels,\n"
        "# waits for FFT calculation, and saves results in slot 1-4 on the FFT / Order Analysis page.\n\n"
        "FFT_CLEAR_ALL_SLOTS\n"
        "SET_SERVO on\n"
        "SET_MOTOR_SPEED 25.0\n"
        "WAIT_SPEED 25.0 0.5\n"
        "WAIT 2.0\n\n"
        "# Capture Slot 1 (Morgan A)\n"
        "SET_CHANNEL AIN0-AIN1\n"
        "WAIT 2.5\n"
        "FFT_CAPTURE_SLOT 1\n\n"
        "# Capture Slot 2 (Regular A)\n"
        "SET_CHANNEL AIN2-AIN3\n"
        "WAIT 2.5\n"
        "FFT_CAPTURE_SLOT 2\n\n"
        "# Capture Slot 3 (Morgan B)\n"
        "SET_CHANNEL AIN4-AIN5\n"
        "WAIT 2.5\n"
        "FFT_CAPTURE_SLOT 3\n\n"
        "# Capture Slot 4 (Regular B)\n"
        "SET_CHANNEL AIN6-AIN7\n"
        "WAIT 2.5\n"
        "FFT_CAPTURE_SLOT 4\n\n"
        "# Ramp down motor\n"
        "SET_MOTOR_SPEED 0.0\n"
        "SET_SERVO off\n"
    )
}

class MacroSystemWidget(QWidget):
    def __init__(self, engine, parent=None):
        super().__init__(parent)
        self.engine = engine
        
        # State machine variables
        self.steps = []
        self.current_step_idx = 0
        self.is_running = False
        self.wait_time_remaining_ms = 0
        self.waiting_for_speed = False
        self.wait_target_speed = 0.0
        self.wait_speed_tolerance = 0.5
        
        # Custom presets path in the workspace
        self.preset_filepath = "macro_presets.json"
        self.custom_presets = {}
        
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick_execution)
        
        self._build_ui()
        self.load_custom_presets()
        self.update_preset_dropdown()
        
    def _build_ui(self):
        self.setStyleSheet("""
            QGroupBox { border: 1px solid #5c6370; border-radius: 5px; margin-top: 12px; padding-top: 15px; font-weight: bold; }
            QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top left; top: 0px; left: 10px; color: #61afef; background-color: #282c34; padding: 0 5px; }
            QLabel { font-weight: normal; }
            QComboBox { background-color: #3b4048; border: 1px solid #5c6370; padding: 5px; color: white; border-radius: 3px; }
            QPushButton { background-color: #616a6b; border: none; padding: 8px; border-radius: 4px; color: white; font-weight: bold; }
            QPushButton:hover { background-color: #7f8c8d; }
            QPushButton#RunBtn { background-color: #98c379; color: black; }
            QPushButton#RunBtn:hover { background-color: #a6d88c; }
            QPushButton#AbortBtn { background-color: #e06c75; color: black; }
            QPushButton#AbortBtn:hover { background-color: #e5838a; }
            QProgressBar { border: 1px solid #5c6370; border-radius: 4px; text-align: center; color: white; background-color: #21252b; }
            QProgressBar::chunk { background-color: #61afef; }
        """)
        
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(5, 5, 5, 5)
        
        self.main_splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(self.main_splitter)
        
        # ---- LEFT PANEL SCROLL AREA ----
        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setFrameShape(QFrame.NoFrame)
        left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        left_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        left_scroll.setMinimumWidth(250)
        
        # ---- LEFT PANEL: CONTROLS & INFO ----
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(5, 5, 5, 5)
        
        # Guide
        grp_guide = QGroupBox()
        lay_guide = QVBoxLayout(grp_guide)
        lbl_guide = QLabel(
            "Write, load, or select a preset macro script to automate calibration workflows. "
            "Lines starting with '#' are treated as comments. Execution is asynchronous and non-blocking."
        )
        lbl_guide.setWordWrap(True)
        lay_guide.addWidget(lbl_guide)
        self.sect_guide = CollapsibleSection("Macro Scripting Guide", grp_guide)
        left_layout.addWidget(self.sect_guide)
        
        # Presets Panel
        grp_presets = QGroupBox()
        lay_presets = QHBoxLayout(grp_presets)
        self.cb_presets = QComboBox()
        self.cb_presets.currentTextChanged.connect(self.load_preset)
        lay_presets.addWidget(self.cb_presets, 2)
        
        self.btn_save_preset = QPushButton("Save As...")
        self.btn_save_preset.setStyleSheet("background-color: #61afef; color: black; font-weight: bold; padding: 6px;")
        self.btn_save_preset.clicked.connect(self.save_as_preset_dialog)
        self.btn_save_preset.setToolTip("Saves the active editor script as a custom preset.")
        lay_presets.addWidget(self.btn_save_preset, 1)
        
        self.btn_edit_preset = QPushButton("Edit")
        self.btn_edit_preset.setStyleSheet("background-color: #e5c07b; color: black; font-weight: bold; padding: 6px;")
        self.btn_edit_preset.clicked.connect(self.edit_preset_action)
        self.btn_edit_preset.setToolTip("Updates the currently selected custom preset with the editor's content.")
        lay_presets.addWidget(self.btn_edit_preset, 1)
        
        self.btn_delete_preset = QPushButton("Delete")
        self.btn_delete_preset.setStyleSheet("background-color: #e06c75; color: black; font-weight: bold; padding: 6px;")
        self.btn_delete_preset.clicked.connect(self.delete_preset_action)
        self.btn_delete_preset.setToolTip("Deletes the currently selected custom preset.")
        lay_presets.addWidget(self.btn_delete_preset, 1)
        
        self.sect_presets = CollapsibleSection("Presets", grp_presets)
        self.sect_presets.content.setVisible(True)
        self.sect_presets.update_header()
        left_layout.addWidget(self.sect_presets)
        
        # Run Controls
        grp_ctrl = QGroupBox()
        lay_ctrl = QVBoxLayout(grp_ctrl)
        
        h_buttons = QHBoxLayout()
        self.btn_run = QPushButton("RUN MACRO")
        self.btn_run.setObjectName("RunBtn")
        self.btn_run.clicked.connect(self.start_macro)
        
        self.btn_abort = QPushButton("ABORT")
        self.btn_abort.setObjectName("AbortBtn")
        self.btn_abort.clicked.connect(self.abort_macro)
        self.btn_abort.setEnabled(False)
        
        h_buttons.addWidget(self.btn_run)
        h_buttons.addWidget(self.btn_abort)
        lay_ctrl.addLayout(h_buttons)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        lay_ctrl.addWidget(self.progress_bar)
        
        self.lbl_status = QLabel("Status: Idle")
        self.lbl_status.setStyleSheet("font-weight: bold; color: #abb2bf;")
        lay_ctrl.addWidget(self.lbl_status)
        
        self.sect_ctrl = CollapsibleSection("Execution Panel", grp_ctrl)
        self.sect_ctrl.content.setVisible(True)
        self.sect_ctrl.update_header()
        left_layout.addWidget(self.sect_ctrl)
        
        # Save / Load Files
        grp_files = QGroupBox()
        lay_files = QHBoxLayout(grp_files)
        self.btn_load_file = QPushButton("Load Script File...")
        self.btn_load_file.clicked.connect(self.load_script_dialog)
        self.btn_save_file = QPushButton("Save Script File...")
        self.btn_save_file.clicked.connect(self.save_script_dialog)
        lay_files.addWidget(self.btn_load_file)
        lay_files.addWidget(self.btn_save_file)
        
        self.sect_files = CollapsibleSection("Script File Operations", grp_files)
        self.sect_files.content.setVisible(True)
        self.sect_files.update_header()
        left_layout.addWidget(self.sect_files)
        
        # Cheat Sheet
        grp_cheat = QGroupBox()
        lay_cheat = QVBoxLayout(grp_cheat)
        scroll_cheat = QScrollArea()
        scroll_cheat.setWidgetResizable(True)
        scroll_cheat.setStyleSheet("QScrollArea { border: none; background-color: transparent; }")
        
        cheat_text = (
            "<b>Motor & Servo Control:</b><br>"
            "&bull; <code>SET_SERVO &lt;on/off&gt;</code><br>"
            "&bull; <code>SET_MOTOR_SPEED &lt;hz&gt;</code> (float)<br>"
            "<br>"
            "<b>ADC Hardware Configuration:</b><br>"
            "&bull; <code>SET_CHANNEL &lt;name&gt;</code> (e.g. AIN0-AIN1)<br>"
            "&bull; <code>SET_GAIN &lt;1x/2x/4x/8x/16x/32x&gt;</code><br>"
            "&bull; <code>SET_RATE &lt;rate_text&gt;</code> (e.g. 2400 SPS)<br>"
            "<br>"
            "<b>Time & Speed Stabilization:</b><br>"
            "&bull; <code>WAIT &lt;seconds&gt;</code> (float wait delay)<br>"
            "&bull; <code>WAIT_SPEED &lt;target_hz&gt; &lt;tolerance&gt;</code><br>"
            "<br>"
            "<b>Coil Alignment & Calibration:</b><br>"
            "&bull; <code>CLEAR_ALL_SLOTS</code><br>"
            "&bull; <code>ALIGNMENT_SCAN</code> (runs 2s scan)<br>"
            "&bull; <code>CAPTURE_SLOT &lt;1-4&gt;</code><br>"
            "&bull; <code>APPLY_OFFSET</code><br>"
            "&bull; <code>CALIBRATE_SELF_OFFSET</code><br>"
            "&bull; <code>CALIBRATE_SYS_OFFSET</code><br>"
            "&bull; <code>CALIBRATE_SYS_GAIN</code><br>"
            "&bull; <code>RESET_CALIBRATION</code><br>"
            "<br>"
            "<b>FFT / Order Analysis:</b><br>"
            "&bull; <code>FFT_CLEAR_ALL_SLOTS</code><br>"
            "&bull; <code>FFT_CAPTURE_SLOT &lt;1-4&gt;</code><br>"
            "<br>"
            "<b>Recording & Streaming:</b><br>"
            "&bull; <code>START_RECORDING</code><br>"
            "&bull; <code>STOP_RECORDING</code><br>"
            "&bull; <code>PAUSE_STREAM</code> / <code>RESUME_STREAM</code>"
        )
        lbl_cheat = QLabel(cheat_text)
        lbl_cheat.setTextFormat(Qt.RichText)
        lbl_cheat.setWordWrap(True)
        lbl_cheat.setStyleSheet("font-size: 9pt; color: #abb2bf;")
        scroll_cheat.setWidget(lbl_cheat)
        lay_cheat.addWidget(scroll_cheat)
        self.sect_cheat = CollapsibleSection("Command Cheat Sheet", grp_cheat)
        left_layout.addWidget(self.sect_cheat)
        
        left_layout.addStretch()
        left_scroll.setWidget(left_panel)
        self.main_splitter.addWidget(left_scroll)
        
        # ---- RIGHT PANEL: EDITOR & CONSOLE SPLITTER ----
        splitter = QSplitter(Qt.Vertical)
        
        # Text Editor
        self.editor = QTextEdit()
        self.editor.setPlaceholderText("# Write macro instructions here...\n# Press RUN MACRO to execute.")
        self.editor.setStyleSheet("""
            QTextEdit {
                background-color: #21252b;
                border: 1px solid #5c6370;
                border-radius: 4px;
                font-family: Consolas, Monaco, monospace;
                font-size: 10pt;
                color: #abb2bf;
            }
        """)
        splitter.addWidget(self.editor)
        
        # Console Log
        console_widget = QWidget()
        console_lay = QVBoxLayout(console_widget)
        console_lay.setContentsMargins(0, 0, 0, 0)
        
        self.console = QTextEdit()
        self.console.setReadOnly(True)
        self.console.setStyleSheet("""
            QTextEdit {
                background-color: #181a1f;
                border: 1px solid #5c6370;
                border-radius: 4px;
                font-family: Consolas, Monaco, monospace;
                font-size: 9pt;
                color: #abb2bf;
            }
        """)
        console_lay.addWidget(self.console)
        
        # Clear Console Button
        btn_clear_console = QPushButton("Clear Output Console")
        btn_clear_console.setStyleSheet("background-color: #3b4048; font-size: 8pt; padding: 4px;")
        btn_clear_console.clicked.connect(self.console.clear)
        console_lay.addWidget(btn_clear_console)
        
        splitter.addWidget(console_widget)
        splitter.setSizes([450, 250])
        self.main_splitter.addWidget(splitter)
        self.main_splitter.setSizes([420, 800])
        
    def log_to_console(self, category: str, message: str):
        timestamp = time.strftime("%H:%M:%S")
        color = "#abb2bf"
        if category == "INFO":
            color = "#98c379"  # Green
        elif category == "ERROR":
            color = "#e06c75"  # Red
        elif category == "CMD":
            color = "#61afef"  # Cyan
        elif category == "WARN":
            color = "#e5c07b"  # Yellow
            
        html = f'<font color="#5c6370">[{timestamp}]</font> <font color="{color}"><b>{category}:</b> {message}</font>'
        self.console.append(html)
        
    def load_custom_presets(self):
        if os.path.exists(self.preset_filepath):
            try:
                with open(self.preset_filepath, 'r', encoding='utf-8') as f:
                    self.custom_presets = json.load(f)
                self.log_to_console("INFO", f"Loaded {len(self.custom_presets)} custom presets from disk.")
            except Exception as e:
                self.log_to_console("WARN", f"Failed to load custom presets: {e}")
        else:
            self.custom_presets = {}
            
    def update_preset_dropdown(self):
        self.cb_presets.blockSignals(True)
        self.cb_presets.clear()
        self.cb_presets.addItem("Select a Preset...")
        
        # Add built-in presets
        for name in PRESETS:
            if name != "Select a Preset...":
                self.cb_presets.addItem(name)
                
        # Add custom presets
        for name in self.custom_presets:
            self.cb_presets.addItem(name + " (Custom)")
            
        self.cb_presets.blockSignals(False)
        
    def load_preset(self, preset_name):
        if not preset_name or preset_name == "Select a Preset...":
            return
            
        if preset_name.endswith(" (Custom)"):
            real_name = preset_name[:-9]
            script = self.custom_presets.get(real_name, "")
        else:
            script = PRESETS.get(preset_name, "")
            
        if script:
            self.editor.setPlainText(script)
            self.log_to_console("INFO", f"Loaded preset template: '{preset_name}'")
            
    def save_as_preset_dialog(self):
        name, ok = QInputDialog.getText(self, "Save Script as Preset", "Enter preset name:")
        if ok and name.strip():
            name = name.strip()
            if name in PRESETS:
                self.log_to_console("ERROR", f"Cannot overwrite built-in preset '{name}'")
                return
                
            if name in self.custom_presets:
                from PySide6.QtWidgets import QMessageBox
                reply = QMessageBox.question(
                    self,
                    "Confirm Overwrite",
                    f"A custom preset named '{name}' already exists. Do you want to overwrite it?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No
                )
                if reply != QMessageBox.Yes:
                    return

            self.custom_presets[name] = self.editor.toPlainText()
            try:
                with open(self.preset_filepath, 'w', encoding='utf-8') as f:
                    json.dump(self.custom_presets, f, indent=4)
                self.log_to_console("INFO", f"Saved preset '{name}' to custom presets list.")
                self.update_preset_dropdown()
                
                # Automatically select the newly saved preset
                idx = self.cb_presets.findText(name + " (Custom)", Qt.MatchExactly)
                if idx >= 0:
                    self.cb_presets.setCurrentIndex(idx)
            except Exception as e:
                self.log_to_console("ERROR", f"Failed to save custom preset: {e}")
                
    def delete_preset_action(self):
        preset_name = self.cb_presets.currentText()
        if not preset_name or preset_name == "Select a Preset...":
            return
            
        if not preset_name.endswith(" (Custom)"):
            self.log_to_console("ERROR", "Cannot delete built-in presets.")
            return
            
        real_name = preset_name[:-9]
        if real_name in self.custom_presets:
            del self.custom_presets[real_name]
            try:
                with open(self.preset_filepath, 'w', encoding='utf-8') as f:
                    json.dump(self.custom_presets, f, indent=4)
                self.log_to_console("INFO", f"Deleted custom preset '{real_name}'.")
                self.update_preset_dropdown()
            except Exception as e:
                self.log_to_console("ERROR", f"Failed to update custom presets file: {e}")
                
    def edit_preset_action(self):
        preset_name = self.cb_presets.currentText()
        if not preset_name or preset_name == "Select a Preset...":
            self.log_to_console("ERROR", "Please select a custom preset to edit.")
            return
            
        if not preset_name.endswith(" (Custom)"):
            self.log_to_console("ERROR", "Cannot edit built-in presets directly. Please use 'Save As...' to save it as a new custom preset.")
            return
            
        real_name = preset_name[:-9]
        if real_name in self.custom_presets:
            self.custom_presets[real_name] = self.editor.toPlainText()
            try:
                with open(self.preset_filepath, 'w', encoding='utf-8') as f:
                    json.dump(self.custom_presets, f, indent=4)
                self.log_to_console("INFO", f"Successfully updated custom preset '{real_name}'.")
            except Exception as e:
                self.log_to_console("ERROR", f"Failed to save preset edits: {e}")
        else:
            self.log_to_console("ERROR", f"Custom preset '{real_name}' not found.")
                
    def load_script_dialog(self):
        filename, _ = QFileDialog.getOpenFileName(self, "Load Macro Script", "", "Text Files (*.txt);;MGF Macro Files (*.mgfmac);;All Files (*)")
        if filename:
            try:
                with open(filename, 'r', encoding='utf-8') as f:
                    content = f.read()
                self.editor.setPlainText(content)
                self.log_to_console("INFO", f"Successfully loaded macro script from '{os.path.basename(filename)}'")
            except Exception as e:
                self.log_to_console("ERROR", f"Failed to load file: {e}")
                
    def save_script_dialog(self):
        filename, _ = QFileDialog.getSaveFileName(self, "Save Macro Script", "", "Text Files (*.txt);;MGF Macro Files (*.mgfmac);;All Files (*)")
        if filename:
            try:
                content = self.editor.toPlainText()
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write(content)
                self.log_to_console("INFO", f"Successfully saved macro script to '{os.path.basename(filename)}'")
            except Exception as e:
                self.log_to_console("ERROR", f"Failed to save file: {e}")

    def get_parent_ui_widgets(self):
        """Helper to safely fetch main window elements."""
        win = self.window()
        if not hasattr(win, 'control_panel'):
            return None, None, None
        return win.control_panel, getattr(win, 'alignment_widget', None), getattr(win, 'fft_analysis_widget', None)
        
    def parse_script(self) -> bool:
        """Parses the text editor contents. Returns True if syntax is valid."""
        self.steps = []
        raw_text = self.editor.toPlainText()
        lines = raw_text.split('\n')
        
        valid_cmds = {
            "SET_SERVO", "SET_MOTOR_SPEED", "SET_CHANNEL", "SET_GAIN", "SET_RATE",
            "WAIT", "WAIT_SPEED", "CLEAR_ALL_SLOTS", "ALIGNMENT_SCAN", "CAPTURE_SLOT",
            "APPLY_OFFSET", "CALIBRATE_SELF_OFFSET", "CALIBRATE_SYS_OFFSET", 
            "CALIBRATE_SYS_GAIN", "RESET_CALIBRATION", "START_RECORDING", "STOP_RECORDING",
            "PAUSE_STREAM", "RESUME_STREAM", "FFT_CLEAR_ALL_SLOTS", "FFT_CAPTURE_SLOT"
        }
        
        for idx, line in enumerate(lines, 1):
            line = line.strip()
            if not line or line.startswith('#'):
                continue
                
            parts = line.split(maxsplit=2)
            cmd = parts[0].upper()
            args = parts[1:] if len(parts) > 1 else []
            
            if cmd not in valid_cmds:
                self.log_to_console("ERROR", f"Line {idx}: Unknown command '{cmd}'")
                return False
                
            # Basic validation
            if cmd == "SET_SERVO":
                if not args or args[0].lower() not in ["on", "off"]:
                    self.log_to_console("ERROR", f"Line {idx}: SET_SERVO requires 'on' or 'off'")
                    return False
            elif cmd == "SET_MOTOR_SPEED":
                if not args:
                    self.log_to_console("ERROR", f"Line {idx}: SET_MOTOR_SPEED requires a target HZ value")
                    return False
                try:
                    float(args[0])
                except ValueError:
                    self.log_to_console("ERROR", f"Line {idx}: SET_MOTOR_SPEED parameter must be a float")
                    return False
            elif cmd == "SET_GAIN":
                if not args or args[0].lower() not in ["1x", "2x", "4x", "8x", "16x", "32x"]:
                    self.log_to_console("ERROR", f"Line {idx}: SET_GAIN requires one of [1x, 2x, 4x, 8x, 16x, 32x]")
                    return False
            elif cmd == "WAIT":
                if not args:
                    self.log_to_console("ERROR", f"Line {idx}: WAIT requires a duration in seconds")
                    return False
                try:
                    float(args[0])
                except ValueError:
                    self.log_to_console("ERROR", f"Line {idx}: WAIT parameter must be a float")
                    return False
            elif cmd == "WAIT_SPEED":
                if len(line.split()) < 3:
                    self.log_to_console("ERROR", f"Line {idx}: WAIT_SPEED requires both target speed and tolerance values")
                    return False
                try:
                    float(args[0])
                    float(line.split()[2])
                except ValueError:
                    self.log_to_console("ERROR", f"Line {idx}: WAIT_SPEED arguments must be numeric")
                    return False
            elif cmd == "CAPTURE_SLOT":
                if not args or args[0] not in ["1", "2", "3", "4"]:
                    self.log_to_console("ERROR", f"Line {idx}: CAPTURE_SLOT requires slot index 1, 2, 3, or 4")
                    return False
            elif cmd == "FFT_CAPTURE_SLOT":
                if not args or args[0] not in ["1", "2", "3", "4"]:
                    self.log_to_console("ERROR", f"Line {idx}: FFT_CAPTURE_SLOT requires slot index 1, 2, 3, or 4")
                    return False
                    
            self.steps.append({"line_num": idx, "cmd": cmd, "args": args, "raw": line})
            
        return True

    def start_macro(self):
        cp, _, _ = self.get_parent_ui_widgets()
        if not cp:
            self.log_to_console("ERROR", "Parent control panels not found. Macro cannot execute.")
            return
            
        if not cp.conn.connected:
            self.log_to_console("ERROR", "No active hardware connection. Connect first.")
            return
            
        if not self.parse_script():
            self.log_to_console("ERROR", "Script parsing failed. Correct errors before running.")
            return
            
        if not self.steps:
            self.log_to_console("WARN", "Macro script is empty.")
            return
            
        self.is_running = True
        self.current_step_idx = 0
        self.btn_run.setEnabled(False)
        self.btn_abort.setEnabled(True)
        self.editor.setEnabled(False)
        self.cb_presets.setEnabled(False)
        self.btn_load_file.setEnabled(False)
        self.btn_save_preset.setEnabled(False)
        self.btn_edit_preset.setEnabled(False)
        self.btn_delete_preset.setEnabled(False)
        
        self.wait_time_remaining_ms = 0
        self.waiting_for_speed = False
        
        self.log_to_console("INFO", f"Starting macro execution ({len(self.steps)} steps)...")
        self.progress_bar.setValue(0)
        self.timer.start(100)  # Clock tick rate: 100ms
        
    def abort_macro(self):
        if not self.is_running:
            return
            
        self.is_running = False
        self.timer.stop()
        self.log_to_console("WARN", "Macro execution ABORTED by user request.")
        
        # Ramping down motor for safety
        cp, _, _ = self.get_parent_ui_widgets()
        if cp and cp.conn.connected:
            self.log_to_console("INFO", "Safety shutdown: Command motor speed to 0.0 Hz.")
            cp._send(protocol.CMD_SET_MOTOR_SPEED, 0.0)
            
        self.reset_ui_state()
        
    def reset_ui_state(self):
        self.is_running = False
        self.btn_run.setEnabled(True)
        self.btn_abort.setEnabled(False)
        self.editor.setEnabled(True)
        self.cb_presets.setEnabled(True)
        self.btn_load_file.setEnabled(True)
        self.btn_save_preset.setEnabled(True)
        self.btn_edit_preset.setEnabled(True)
        self.btn_delete_preset.setEnabled(True)
        self.lbl_status.setText("Status: Idle")
        self.lbl_status.setStyleSheet("font-weight: bold; color: #abb2bf;")
        
    def tick_execution(self):
        if not self.is_running:
            self.timer.stop()
            return
            
        # 1. Handle WAIT delay
        if self.wait_time_remaining_ms > 0:
            self.wait_time_remaining_ms -= 100
            sec_left = max(0.0, self.wait_time_remaining_ms / 1000.0)
            self.lbl_status.setText(f"Status: Waiting ({sec_left:.1f}s left)")
            return
            
        # 2. Handle WAIT_SPEED delay
        if self.waiting_for_speed:
            diff = abs(self.engine.motor_speed - self.wait_target_speed)
            self.lbl_status.setText(f"Status: Waiting for Speed (Target: {self.wait_target_speed:.1f} Hz, Current: {self.engine.motor_speed:.2f} Hz)")
            if diff <= self.wait_speed_tolerance:
                self.waiting_for_speed = False
                self.log_to_console("INFO", f"Motor speed stabilized at {self.engine.motor_speed:.2f} Hz.")
            else:
                return
                
        # 3. Check macro completion
        if self.current_step_idx >= len(self.steps):
            self.timer.stop()
            self.progress_bar.setValue(100)
            self.log_to_console("INFO", "Macro sequence executed successfully.")
            self.reset_ui_state()
            return
            
        # 4. Execute next command
        step = self.steps[self.current_step_idx]
        self.execute_command(step)
        
        # Advance index and progress
        self.current_step_idx += 1
        percent = int((self.current_step_idx / len(self.steps)) * 100)
        self.progress_bar.setValue(percent)

    def execute_command(self, step):
        cmd = step["cmd"]
        args = step["args"]
        raw = step["raw"]
        
        self.log_to_console("CMD", f"[Line {step['line_num']}] Executing: {raw}")
        self.lbl_status.setText(f"Status: Running step {self.current_step_idx+1}/{len(self.steps)}")
        self.lbl_status.setStyleSheet("font-weight: bold; color: #61afef;")
        
        cp, align, fft_analysis = self.get_parent_ui_widgets()
        if not cp:
            self.log_to_console("ERROR", "UI links broken during execution.")
            self.abort_macro()
            return
            
        # Check connection status mid-macro
        if not cp.conn.connected:
            self.log_to_console("ERROR", "Device disconnected. Aborting macro.")
            self.abort_macro()
            return

        try:
            if cmd == "SET_SERVO":
                target = args[0].lower()
                target_state = (target == "on")
                if cp.servo_state != target_state:
                    cp.toggle_servo()
                    
            elif cmd == "SET_MOTOR_SPEED":
                speed = float(args[0])
                cp.inp_speed.setText(str(speed))
                cp._on_set_motor_speed()
                
            elif cmd == "SET_CHANNEL":
                chan_name = args[0]
                # Find matching channel in combobox
                idx = cp.cb_input.findText(chan_name, Qt.MatchContains)
                if idx >= 0:
                    cp.cb_input.setCurrentIndex(idx)
                else:
                    self.log_to_console("WARN", f"Channel '{chan_name}' not found. Skipping channel change.")
                    
            elif cmd == "SET_GAIN":
                gain_text = args[0].lower()
                idx = cp.cb_gain.findText(gain_text, Qt.MatchContains)
                if idx >= 0:
                    cp.cb_gain.setCurrentIndex(idx)
                else:
                    self.log_to_console("WARN", f"Gain '{gain_text}' not found. Skipping gain change.")
                    
            elif cmd == "SET_RATE":
                rate_text = args[0]
                idx = cp.cb_rate.findText(rate_text, Qt.MatchContains)
                if idx >= 0:
                    cp.cb_rate.setCurrentIndex(idx)
                else:
                    self.log_to_console("WARN", f"Sample rate '{rate_text}' not found. Skipping rate change.")
                    
            elif cmd == "WAIT":
                sec = float(args[0])
                self.wait_time_remaining_ms = int(sec * 1000)
                
            elif cmd == "WAIT_SPEED":
                target = float(args[0])
                # Check for 3rd token since parts splits max 2
                raw_tokens = raw.split()
                tol = float(raw_tokens[2]) if len(raw_tokens) >= 3 else 0.5
                self.waiting_for_speed = True
                self.wait_target_speed = target
                self.wait_speed_tolerance = tol
                
            elif cmd == "CLEAR_ALL_SLOTS":
                if align:
                    align.clear_all_slots()
                else:
                    self.log_to_console("WARN", "Alignment widget not available.")
                    
            elif cmd == "ALIGNMENT_SCAN":
                if align:
                    align.start_scan()
                    # Alignment scans take exactly 2.0s. Wait 2.2s to be safe.
                    self.wait_time_remaining_ms = 2200
                else:
                    self.log_to_console("WARN", "Alignment widget not available.")
                    
            elif cmd == "CAPTURE_SLOT":
                slot_idx = int(args[0])
                if align:
                    align.capture_to_slot(slot_idx)
                else:
                    self.log_to_console("WARN", "Alignment widget not available.")
                    
            elif cmd == "FFT_CLEAR_ALL_SLOTS":
                if fft_analysis:
                    fft_analysis.clear_all_slots()
                else:
                    self.log_to_console("WARN", "FFT Analysis widget not available.")
                    
            elif cmd == "FFT_CAPTURE_SLOT":
                slot_idx = int(args[0])
                if fft_analysis:
                    fft_analysis.capture_slot(slot_idx)
                else:
                    self.log_to_console("WARN", "FFT Analysis widget not available.")
                    
            elif cmd == "APPLY_OFFSET":
                if align:
                    align.apply_offset()
                else:
                    self.log_to_console("WARN", "Alignment widget not available.")
                    
            elif cmd == "START_RECORDING":
                self.engine.start_recording()
                
            elif cmd == "STOP_RECORDING":
                # Check for filename
                raw_tokens = raw.split()
                if len(raw_tokens) > 1:
                    filename = raw_tokens[1]
                    if not filename.endswith('.mgf'):
                        filename += '.mgf'
                    self.engine.stop_recording(filename)
                    self.log_to_console("INFO", f"Recording saved to session: {filename}")
                else:
                    self.engine.stop_recording()
                    self.log_to_console("INFO", "Recording stopped and saved to default session.")
                    
            elif cmd == "CALIBRATE_SELF_OFFSET":
                cp._send(protocol.CMD_CALIBRATE_OFFSET, 0)
                
            elif cmd == "CALIBRATE_SYS_OFFSET":
                cp._send(protocol.CMD_CALIBRATE_OFFSET, 1)
                
            elif cmd == "CALIBRATE_SYS_GAIN":
                cp._send(protocol.CMD_CALIBRATE_GAIN, 0)
                
            elif cmd == "RESET_CALIBRATION":
                cp._send(protocol.CMD_RESET_CALIBRATION, 0)
                
            elif cmd == "PAUSE_STREAM":
                cp._send(protocol.CMD_PAUSE_STREAM, 0)
                
            elif cmd == "RESUME_STREAM":
                cp._send(protocol.CMD_RESUME_STREAM, 0)
                
        except Exception as e:
            self.log_to_console("ERROR", f"Failed to execute command '{cmd}': {e}")
            self.abort_macro()
