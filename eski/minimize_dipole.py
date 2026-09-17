import sys
import os
import numpy as np
from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from PyQt5.QtWidgets import (
    QApplication, QWidget, QLineEdit, QPushButton, QLabel,
    QHBoxLayout, QVBoxLayout, QMessageBox
)
from config import CONFIG  # config.py dosyasından verileri al

def try_parse_float(text):
    try:
        return float(text)
    except ValueError:
        return None

class MagneticFieldCalculator(QWidget):
    def __init__(self):
        super().__init__()
        self.init_ui()
        
        # windows için
        print(os.getcwd())
        self.log_path = os.path.join(os.path.expanduser("~"), "Desktop", "şenol-tez", "gradient descent", "iterasyon_logu.txt")

        # Dosya yoksa başlık yaz
        if not os.path.exists(self.log_path):
            print("dosya bulunamadı, oluşturuluyor.")
            with open(self.log_path, "w") as f:
                f.write("itr \t Bx1\t Bx2\t I0\t I1\t I2\t I3\n")
       
        self.iterasyon = 0
        self.learning_rate_dipol = float(CONFIG['learning_rate_dipol'])
        self.learning_rate_quadrupol = float(CONFIG['learning_rate_quadrupol'])
        self.bx1_target = float(CONFIG['bx1_target'])
        self.bx2_target = float(CONFIG['bx2_target'])
        self.nominal_akim = float(CONFIG['nominal_akim'])
        self.yeni_akimlar = np.array([self.nominal_akim, self.nominal_akim, self.nominal_akim, self.nominal_akim]) 

    def init_ui(self):
        self.setWindowTitle("Mıknatıs Akım Optimizasyonu")

        # bx1 alanı ve etiketi
        self.bx1_input = QLineEdit()
        self.bx1_input.setFixedWidth(50)  # LineEdit genişliğini ayarla
        bx1_label = QLabel("Üst noktadaki alan\nbx1 (mT)")
        bx1_label.setStyleSheet("color: gray;")

        # bx2 alanı ve etiketi
        self.bx2_input = QLineEdit()
        self.bx2_input.setFixedWidth(50)  # LineEdit genişliğini ayarla
        bx2_label = QLabel("Alt noktadaki alan\nbx2 (mT)")
        bx2_label.setStyleSheet("color: gray;")

        bx_layout = QVBoxLayout()
        bx_layout.addWidget(bx1_label)
        bx_layout.addWidget(self.bx1_input)
        bx_layout.addWidget(bx2_label)
        bx_layout.addWidget(self.bx2_input)

        # Hesapla butonu ve bx1, bx2 kutuları yan yana
        input_layout = QHBoxLayout()
        input_layout.addLayout(bx_layout)
        
        self.calc_button = QPushButton("Yeni Akımları Hesapla")
        self.calc_button.clicked.connect(self.hesapla)
        self.calc_button.setFixedWidth(200)  # Butonun genişliğini ayarla
        self.calc_button.setFixedHeight(100)  # Butonun genişliğini ayarla
        input_layout.addWidget(self.calc_button)
       
        # Sonuç etiketi
        self.result_label = QLabel("")
#        self.result_label.setStyleSheet("font-weight: bold;")
        self.result_label.setStyleSheet("color: blue;")

        # Yatay layout
        self.main_layout = QVBoxLayout()  # Initialize main_layout first
        input_layout.addWidget(self.result_label)  # ← Bu satır sonucu sağa koyar

        # Akım bilgileri: I0, I1, I2, I3
        nominal_akim = CONFIG.get('nominal_akim')
        self.akim_labels = []
        for i in range(4):
            label = QLabel(f"I{i}: {nominal_akim:.3f} A")
            self.akim_labels.append(label)

        # Akım etiketlerini yan yana yerleştir
        akim_layout = QHBoxLayout()
        for label in self.akim_labels:
            akim_layout.addWidget(label)

        # Grafik bileşeni
        self.figure = Figure(figsize=(5, 3))
        self.canvas = FigureCanvas(self.figure)
        self.ax = self.figure.add_subplot(111)
        self.bx1_list = []
        self.bx2_list = []

        # Ana düzen
        self.main_layout.addLayout(input_layout)
        self.main_layout.addWidget(self.calc_button)
        self.main_layout.addWidget(self.result_label)
        for label in self.akim_labels:
            self.main_layout.addWidget(label)

        self.main_layout.addWidget(self.canvas)
        self.setLayout(self.main_layout)

    def compute_Bx(self):
        bx1 = try_parse_float(self.bx1_input.text())
        bx2 = try_parse_float(self.bx2_input.text())

        if bx1 is None or bx2 is None:
            raise ValueError("Geçersiz sayı girdisi")

        Bx1 = (bx1 + bx2) / 2  # dipol
        Bx2 = (bx1 - bx2) / 2  # kuadrupol

        self.result_label.setText(f"\nBx1 = {Bx1:.3f}\n Bx2 = {Bx2:.3f} \n")
        print (f"\nBx1 = {Bx1:.3f}\n Bx2 = {Bx2:.3f} \n")
        return Bx1, Bx2

    def hesapla(self):
        try:
            Bx1, Bx2 = self.compute_Bx()

            akim_sapmalari = np.zeros(4)
            D1 = Bx1 - self.bx1_target
            D2 = Bx2 - self.bx2_target

            print ("D1, D2:", D1, ", ", D2)

            akim_sapmalari[0] -= self.learning_rate_dipol * D1
            akim_sapmalari -= self.learning_rate_quadrupol * D2 * np.ones(4)

#            yeni_akimlar = self.nominal_akim + akim_sapmalari
            self.yeni_akimlar += akim_sapmalari
            for i, label in enumerate(self.akim_labels):
                label.setText(f"I{i} (A): {self.yeni_akimlar[i]:32f}")

            self.iterasyon += 1
            self.result_label.setText(f"İterasyon: {self.iterasyon}\n\nBx1 = {Bx1:.3f} mT\nBx2 = {Bx2:.3f} mT")

            # Dosyaya veriyi yaz (her seferinde aç-kapa)
            with open(self.log_path, "a") as f:
                f.write(f"{self.iterasyon}\t{Bx1:.3f}\t{Bx2:.3f}\t{self.yeni_akimlar[0]:.3f}\t{self.yeni_akimlar[1]:.3f}\t{self.yeni_akimlar[2]:.3f}\t{self.yeni_akimlar[3]:.3f}\n")

            self.bx1_list.append(Bx1)
            self.bx2_list.append(Bx2)

            self.ax.clear()
            self.ax.plot(self.bx1_list, label='Bx1')
            self.ax.plot(self.bx2_list, label='Bx2')
            self.ax.set_xlabel("İterasyon")
            self.ax.set_ylabel("Manyetik Alan (mT)")
            self.ax.legend()
            
            max_ticks = 6
            tick_step = max(1, self.iterasyon // (max_ticks - 1))
            xticks = list(range(0, self.iterasyon + 1, tick_step))
            self.ax.set_xticks(xticks)
            
            self.ax.grid(True)
            self.figure.tight_layout()
            self.canvas.draw()

        except ValueError:
            QMessageBox.warning(self, "Hata", "Lütfen geçerli sayılar giriniz.")
            return  # İterasyona geçmeden çık

if __name__ == "__main__":
    app = QApplication(sys.argv)
    pencere = MagneticFieldCalculator()
    pencere.show()
    sys.exit(app.exec_())
