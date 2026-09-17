import pyvisa

class GucKaynagi:
    def __init__(self, visa_address):
        self.rm = pyvisa.ResourceManager("@py")
        self.power_supply = self.rm.open_resource(visa_address)
        self.power_supply.write("*CLS")  # Clears the past errors, etc from the buffer
    
    def get_identity(self):
        """Cihazın kimliğini sorgular."""
        return self.power_supply.query("*IDN?")
    
    def set_remote(self):
        """Cihazı remote moda alır."""
        self.power_supply.write("SYST:REM")
    
    def set_voltage_current(self, voltage, current):
        """Güç kaynağının voltaj ve akımını ayarlar."""
        self.power_supply.write(f"VOLT {voltage}")    # Set voltage
        self.power_supply.write(f"CURR {current}")    # Set current
    
    def check_for_errors(self):
        """Cihaza ait hata mesajlarını kontrol eder."""
        return self.power_supply.query("SYST:ERR?")
    
    def turn_on_output(self):
        """Çıkışı açar."""
        self.power_supply.write("OUTP ON")
    
    def turn_off_output(self):
        """Çıkışı kapatır."""
        self.power_supply.write("OUTP OFF")
    
    def read_measurements(self):
        """Cihazdan voltaj ve akım ölçümleri alır."""
        voltage = self.power_supply.query("MEAS:VOLT?")
        current = self.power_supply.query("MEAS:CURR?")
        return voltage, current
    
    def close_connection(self):
        """Bağlantıyı kapatır."""
        self.power_supply.close()

