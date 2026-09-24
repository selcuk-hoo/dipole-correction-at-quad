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
                    "motor_speed": self.motor_speed
                }, f, indent=4)
            log.info("Settings saved to %s", self._filename)
        except Exception as e:
            log.error("Failed to save settings: %s", e)

