import sys
from PySide6.QtWidgets import QApplication

from mgf.connection import MgfConnection
from mgf.data_engine import DataEngine
from mgf.settings import Settings
from mgf.ui.main_window_vispy import MainWindowVispy

def main():
    import os
    for folder in ["backups", "sessions", "outputs", os.path.join("outputs", "screenshots")]:
        os.makedirs(folder, exist_ok=True)
        
    # vispy internal Qt application might need to be created first in some configurations,
    # but since we are using PySide6 explicitly, QApplication handles it.
    app = QApplication(sys.argv)
    
    settings = Settings()
    engine = DataEngine()
    engine.motor_speed = settings.motor_speed  # Seed from saved settings
    conn = MgfConnection(settings.host, settings.port)
    
    window = MainWindowVispy(conn, engine, settings)
    window.show()
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main()