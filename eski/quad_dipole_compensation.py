"""Dort bagimsiz guc kaynagiyla beslenen bir air-core quadrupolde, mekanik
ofsetten kaynaklanan dipol alanlarin (Bx, By) sadece bobin akimlari
degistirilerek aktif olarak bastirilmasi.

Quadrupole gradyenti bu uygulamada bir kontrol degiskeni olarak
hedeflenmez; onun yerine akim duzeltmelerine eklenen regularization
(lambda*||dI||^2) sayesinde akimlarda gereksiz/buyuk degisiklik
yapilmasi onlenir, dolayisiyla quad gradyenti dolayli olarak korunmus
olur.

Akis:
  Faz 1 (bir kez, sonucu response_matrix.json'a kaydedilir):
    Yari-otomatik kalibrasyon sihirbazi. Uygulama her adimda hangi
    akimlarin uygulanmasi gerektigini gosterir, kullanici guc
    kaynaklarini elle o degerlere ayarlar, rotating coil ile Bx/By
    olcer ve kutulara girer.

  Faz 2 (her calistirmada, kayitli response matrix varsa dogrudan
  buradan baslar):
    Kullanici mevcut Bx/By olcumunu girer -> uygulama regularized
    least squares ile akim duzeltmesini hesaplar -> damping ile
    kismen uygular -> yeni hedef akimlari gosterir -> kullanici guc
    kaynaklarini bu degerlere ayarlayip tekrar olcer.

Tasarim notu - neden G (quadrupole gradyenti) burada hedeflenmiyor:
  R matrisi 2x4 oldugu icin (2 olcum: Bx, By; 4 bilinmeyen: I0..I3)
  sistem underdetermined'dir: ayni Bx,By duzeltmesini veren sonsuz
  sayida ΔI vardir, aralarindaki fark R'nin 2 boyutlu null space'ine
  aittir. Regularized least squares (lambda*||dI||^2) bu sonsuz
  cozum arasindan minimum-norm olani secer, yani "gereksiz" (Bx,By'ye
  hic katkisi olmayan ama quad'i bozabilecek) null-space sapmasini
  sifirlar. Ideal bir 4-bobinli air-core quadrupolde tasarim simetrisi
  geregi "quad modu" (+,-,+,- alternatif isaretli ortak olcekleme)
  ile "dipol modlari" birbirine yaklasik ortogonaldir; mekanik ofset
  bu ortogonalligi hafifce bozdugu icin Bx,By ile quad arasinda kucuk
  bir coupling olusur (bu algoritmanin duzelttigi de budur). Dolayisiyla
  bu duzeltmenin quad'a sizintisi da dogasi geregi kucuktur.

  Kalan kucuk quad sapmasi bilinclii olarak bu algoritmada telafi
  edilmiyor: gercek hizlandirici ortaminda bu duzeltme LOCO (Linear
  Optics from Closed Orbit) gibi bir optik kalibrasyon adimindan ONCE
  uygulanir; LOCO kaynagi ne olursa olsun (mekanik ofset, bu duzeltme,
  sicaklik surklenmesi vb.) entegre gradyent hatalarini orbit response
  matrix uzerinden olcup global quad trim'leriyle telafi eder. Bu
  yuzden G icin bu algoritma dahilinde ayrica bir hedef/kisit tanimlamaya
  gerek yoktur.

  Bu varsayimin gecerliligi calistirma sirasina baglidir: bu uygulama
  LOCO/optik olcumlerden ONCE, commissioning'in erken bir adimi olarak
  calistirilmalidir. LOCO zaten calistirilip makine o hale gore kalibre
  edildikten SONRA bu algoritma tekrar calistirilirsa (orn. yeniden
  hizalama sonrasi), taze quad sapmasi LOCO'suz ortada kalabilir ve
  ayrica telafi edilmesi gerekebilir.
"""
import os
import sys

import numpy as np
from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from PyQt5.QtWidgets import (
    QApplication, QWidget, QLineEdit, QPushButton, QLabel,
    QHBoxLayout, QVBoxLayout, QMessageBox, QStackedWidget, QFrame,
)

from config import CONFIG
from dipole_core import (
    build_calibration_steps, compute_response_matrix,
    solve_regularized_correction, damped_update, ResponseMatrixData,
)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def try_parse_float(text):
    try:
        return float(text)
    except ValueError:
        return None


def currents_to_str(currents):
    return "   ".join(f"I{i}={c:.3f} A" for i, c in enumerate(currents))


class DipoleCompensationApp(QWidget):
    def __init__(self):
        super().__init__()

        self.delta_i = float(CONFIG["delta_i_kalibrasyon"])
        self.lam = float(CONFIG["lambda_regularizasyon"])
        self.alpha = float(CONFIG["alpha_damping"])
        self.tolerance = float(CONFIG["tolerance"])
        self.nominal_currents = np.array(CONFIG["nominal_akimlar"], dtype=float)

        rm_path = CONFIG["response_matrix_path"]
        self.response_matrix_path = (
            rm_path if os.path.isabs(rm_path) else os.path.join(SCRIPT_DIR, rm_path)
        )
        log_dir = CONFIG["log_dir"]
        log_dir = log_dir if os.path.isabs(log_dir) else os.path.join(SCRIPT_DIR, log_dir)
        os.makedirs(log_dir, exist_ok=True)
        self.log_path = os.path.join(log_dir, "dipol_duzeltme_logu.txt")
        if not os.path.exists(self.log_path):
            with open(self.log_path, "w") as f:
                f.write("itr\tBx\tBy\terr\tI0\tI1\tI2\tI3\n")

        self.R = None
        self.current_currents = self.nominal_currents.copy()
        self.iterasyon = 0
        self.bx_list = []
        self.by_list = []
        self.err_list = []

        self.calib_steps = build_calibration_steps()
        self.calib_index = 0
        self.calib_measurements = []

        self.init_ui()
        self.try_load_response_matrix(startup=True)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------
    def init_ui(self):
        self.setWindowTitle("Dipol Alan Bastirma (4 Bobin, Response Matrix)")

        self.stack = QStackedWidget()
        self.calib_page = self._build_calibration_page()
        self.correction_page = self._build_correction_page()
        self.stack.addWidget(self.calib_page)
        self.stack.addWidget(self.correction_page)

        layout = QVBoxLayout()
        layout.addWidget(self.stack)
        self.setLayout(layout)

    def _build_calibration_page(self):
        page = QWidget()

        self.calib_instructions = QLabel("")
        self.calib_instructions.setWordWrap(True)

        self.calib_bx_input = QLineEdit()
        self.calib_bx_input.setFixedWidth(80)
        self.calib_by_input = QLineEdit()
        self.calib_by_input.setFixedWidth(80)

        form = QHBoxLayout()
        form.addWidget(QLabel("Bx (mT):"))
        form.addWidget(self.calib_bx_input)
        form.addWidget(QLabel("By (mT):"))
        form.addWidget(self.calib_by_input)

        self.calib_next_button = QPushButton("Ileri")
        self.calib_next_button.clicked.connect(self.calibration_next)

        skip_row = QHBoxLayout()
        self.calib_skip_button = QPushButton("Kayitli Response Matrix'i Kullan")
        self.calib_skip_button.clicked.connect(lambda: self.try_load_response_matrix(startup=False))
        skip_row.addWidget(self.calib_skip_button)

        layout = QVBoxLayout()
        layout.addWidget(QLabel("Faz 1: Response Matrix Kalibrasyonu"))
        layout.addWidget(self.calib_instructions)
        layout.addLayout(form)
        layout.addWidget(self.calib_next_button)
        layout.addWidget(self._hline())
        layout.addLayout(skip_row)
        layout.addStretch(1)
        page.setLayout(layout)
        return page

    def _build_correction_page(self):
        page = QWidget()

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: blue;")

        self.corr_bx_input = QLineEdit()
        self.corr_bx_input.setFixedWidth(80)
        self.corr_by_input = QLineEdit()
        self.corr_by_input.setFixedWidth(80)

        form = QHBoxLayout()
        form.addWidget(QLabel("Olculen Bx (mT):"))
        form.addWidget(self.corr_bx_input)
        form.addWidget(QLabel("Olculen By (mT):"))
        form.addWidget(self.corr_by_input)

        self.corr_button = QPushButton("Duzeltmeyi Hesapla")
        self.corr_button.clicked.connect(self.correction_step)
        self.corr_button.setFixedHeight(60)

        self.currents_label = QLabel("")

        self.recalib_button = QPushButton("Yeniden Kalibre Et")
        self.recalib_button.clicked.connect(self.start_calibration)

        self.figure = Figure(figsize=(5, 3))
        self.canvas = FigureCanvas(self.figure)
        self.ax = self.figure.add_subplot(111)

        layout = QVBoxLayout()
        layout.addWidget(QLabel("Faz 2: Regularized Least Squares Duzeltme Dongusu"))
        layout.addLayout(form)
        layout.addWidget(self.corr_button)
        layout.addWidget(self.status_label)
        layout.addWidget(self.currents_label)
        layout.addWidget(self.canvas)
        layout.addWidget(self.recalib_button)
        page.setLayout(layout)
        return page

    @staticmethod
    def _hline():
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        return line

    # ------------------------------------------------------------------
    # Faz 1: kalibrasyon
    # ------------------------------------------------------------------
    def start_calibration(self):
        self.calib_index = 0
        self.calib_measurements = []
        self.calib_bx_input.clear()
        self.calib_by_input.clear()
        self._show_calibration_step()
        self.stack.setCurrentWidget(self.calib_page)

    def _show_calibration_step(self):
        step = self.calib_steps[self.calib_index]
        target = step.target_currents(self.nominal_currents, self.delta_i)
        self.calib_instructions.setText(
            f"Adim {self.calib_index + 1}/{len(self.calib_steps)}: {step.label}\n"
            f"Guc kaynaklarini su akimlara ayarlayin:\n{currents_to_str(target)}\n"
            f"Ardindan rotating coil ile Bx, By olcup asagiya girin."
        )

    def calibration_next(self):
        bx = try_parse_float(self.calib_bx_input.text())
        by = try_parse_float(self.calib_by_input.text())
        if bx is None or by is None:
            QMessageBox.warning(self, "Hata", "Lutfen gecerli sayilar giriniz.")
            return

        self.calib_measurements.append((bx, by))
        self.calib_bx_input.clear()
        self.calib_by_input.clear()
        self.calib_index += 1

        if self.calib_index < len(self.calib_steps):
            self._show_calibration_step()
            return

        R = compute_response_matrix(self.calib_measurements, self.delta_i)
        data = ResponseMatrixData(
            R=R, nominal_currents=self.nominal_currents, delta_i=self.delta_i
        )
        data.save(self.response_matrix_path)
        self._activate_response_matrix(R)
        QMessageBox.information(
            self, "Kalibrasyon Tamamlandi",
            f"Response matrix hesaplandi ve kaydedildi:\n{self.response_matrix_path}"
        )

    # ------------------------------------------------------------------
    # Faz 2: duzeltme dongusu
    # ------------------------------------------------------------------
    def try_load_response_matrix(self, startup: bool):
        if os.path.exists(self.response_matrix_path):
            data = ResponseMatrixData.load(self.response_matrix_path)
            self._activate_response_matrix(data.R)
            if not np.allclose(data.nominal_currents, self.nominal_currents):
                self.nominal_currents = data.nominal_currents
                self.current_currents = data.nominal_currents.copy()
            return

        if startup:
            self.start_calibration()
        else:
            QMessageBox.warning(
                self, "Bulunamadi",
                f"Kayitli response matrix bulunamadi:\n{self.response_matrix_path}\n"
                "Once kalibrasyonu tamamlayin."
            )

    def _activate_response_matrix(self, R):
        self.R = R
        self.current_currents = self.nominal_currents.copy()
        self.iterasyon = 0
        self.bx_list = []
        self.by_list = []
        self.err_list = []
        self.currents_label.setText(f"Hedef akimlar:\n{currents_to_str(self.current_currents)}")
        self.status_label.setText("Olcum bekleniyor.")
        self.stack.setCurrentWidget(self.correction_page)

    def correction_step(self):
        bx = try_parse_float(self.corr_bx_input.text())
        by = try_parse_float(self.corr_by_input.text())
        if bx is None or by is None:
            QMessageBox.warning(self, "Hata", "Lutfen gecerli sayilar giriniz.")
            return

        error = -np.array([bx, by])  # hedef = [0, 0]
        err_norm = float(np.hypot(bx, by))

        delta_currents = solve_regularized_correction(self.R, error, self.lam)
        self.current_currents = damped_update(self.current_currents, delta_currents, self.alpha)

        self.iterasyon += 1
        self.bx_list.append(bx)
        self.by_list.append(by)
        self.err_list.append(err_norm)

        with open(self.log_path, "a") as f:
            f.write(
                f"{self.iterasyon}\t{bx:.4f}\t{by:.4f}\t{err_norm:.4f}\t"
                + "\t".join(f"{c:.4f}" for c in self.current_currents) + "\n"
            )

        self.currents_label.setText(f"Yeni hedef akimlar:\n{currents_to_str(self.current_currents)}")

        converged = err_norm < self.tolerance
        durum = "YAKINSADI" if converged else "devam ediyor"
        self.status_label.setText(
            f"Iterasyon: {self.iterasyon}   Bx={bx:.4f} mT   By={by:.4f} mT   "
            f"||e||={err_norm:.4f} mT ({durum})"
        )

        self.corr_bx_input.clear()
        self.corr_by_input.clear()

        self._redraw_plot()

        if converged:
            QMessageBox.information(
                self, "Yakinsama",
                f"||[Bx, By]|| = {err_norm:.4f} mT < tolerance ({self.tolerance} mT).\n"
                "Dipol alan basariyla bastirildi."
            )

    def _redraw_plot(self):
        self.ax.clear()
        self.ax.plot(self.bx_list, label="Bx", marker="o")
        self.ax.plot(self.by_list, label="By", marker="o")
        self.ax.plot(self.err_list, label="||e||", linestyle="--")
        self.ax.axhline(0, color="gray", linewidth=0.8)
        self.ax.set_xlabel("Iterasyon")
        self.ax.set_ylabel("Manyetik Alan (mT)")
        self.ax.legend()
        self.ax.grid(True)
        self.figure.tight_layout()
        self.canvas.draw()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    pencere = DipoleCompensationApp()
    pencere.show()
    sys.exit(app.exec_())
