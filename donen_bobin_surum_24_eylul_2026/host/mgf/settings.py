import json
import os
import logging

log = logging.getLogger(__name__)

class Settings:
    def __init__(self, filename="settings.json"):
        self._filename = filename
        self.host = "169.254.1.177"
        self.port = 5000
        self.data_mode = 1 # Voltage (0 for RAW, 1 for Voltage)
        self.rate = "2400 SPS" # Default rate string
        self.motor_speed = 1.0 # 1 Hz
        # Merkezleme bridge (MERKEZLEME_OLCUM macro command): "Regular" coil
        # geometry, used identically for n=1 and n=2 harmonic conversion, and
        # an approximate n=2-only sensitivity correction (aperture-related;
        # 1.0 = no correction applied). See merkezleme_koprusu.py.
        self.coil_turns = 100.0
        self.coil_length_mm = 50.0
        self.coil_width_mm = 20.0
        self.merkezleme_duyarlilik_n2 = 1.0
        self.merkezleme_kilit_yolu = None  # None -> merkezleme_koprusu default
        self.load()

    def load(self):
        """Load settings from JSON file."""
        if os.path.exists(self._filename):
            try:
                with open(self._filename, "r") as f:
                    data = json.load(f)
                    self.host = data.get("host", self.host)
                    self.port = data.get("port", self.port)
                    self.data_mode = data.get("data_mode", self.data_mode)
                    self.rate = data.get("rate", self.rate)
                    self.motor_speed = data.get("motor_speed", self.motor_speed)
                    self.coil_turns = data.get("coil_turns", self.coil_turns)
                    self.coil_length_mm = data.get("coil_length_mm", self.coil_length_mm)
                    self.coil_width_mm = data.get("coil_width_mm", self.coil_width_mm)
                    self.merkezleme_duyarlilik_n2 = data.get(
                        "merkezleme_duyarlilik_n2", self.merkezleme_duyarlilik_n2
                    )
                    self.merkezleme_kilit_yolu = data.get(
                        "merkezleme_kilit_yolu", self.merkezleme_kilit_yolu
                    )
                log.info("Settings loaded from %s", self._filename)
            except Exception as e:
                log.error("Failed to load settings: %s", e)

    def save(self):
        """Save settings to JSON file."""
        try:
            with open(self._filename, "w") as f:
                json.dump({
                    "host": self.host,
                    "port": self.port,
                    "data_mode": self.data_mode,
                    "rate": self.rate,
                    "motor_speed": self.motor_speed,
                    "coil_turns": self.coil_turns,
                    "coil_length_mm": self.coil_length_mm,
                    "coil_width_mm": self.coil_width_mm,
                    "merkezleme_duyarlilik_n2": self.merkezleme_duyarlilik_n2,
                    "merkezleme_kilit_yolu": self.merkezleme_kilit_yolu
                }, f, indent=4)
            log.info("Settings saved to %s", self._filename)
        except Exception as e:
            log.error("Failed to save settings: %s", e)

