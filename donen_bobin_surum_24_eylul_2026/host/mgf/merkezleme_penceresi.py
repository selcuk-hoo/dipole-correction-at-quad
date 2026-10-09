"""Merkezleme ölçümü için tek pencerelik minimal arayüz (PySide6).

Bütün iş `OlcumDongusu`'ndadır; pencere yalnızca düğmeleri ona bağlar ve
50 ms'de bir `tick()` çağırıp durumu gösterir. `mgf.ui` paketine konmadı,
çünkü o paket açılırken büyük arayüzün tüm bağımlılıklarını (vispy,
pyqtgraph) yükler.
"""
from __future__ import annotations

import time
from datetime import datetime

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .merkezleme_koprusu import Parametreler, tutarlilik_uyarilari
from .olcum_dongusu import Durum, OlcumDongusu

TEMALAR = {
    "acik": {
        "ad": "Açık",
        "zemin": "#f5f5f5", "panel": "#ffffff", "yazi": "#202124", "soluk": "#5f6368",
        "kenar": "#c4c7c5", "vurgu": "#1a73e8", "vurgu_yazi": "#ffffff",
        "iyi": "#188038", "uyari": "#b06000", "kotu": "#c5221f", "girdi": "#ffffff",
    },
    "koyu": {
        "ad": "Koyu",
        "zemin": "#202124", "panel": "#2b2c2f", "yazi": "#e8eaed", "soluk": "#9aa0a6",
        "kenar": "#44474a", "vurgu": "#8ab4f8", "vurgu_yazi": "#202124",
        "iyi": "#81c995", "uyari": "#fdd663", "kotu": "#f28b82", "girdi": "#303134",
    },
}

_DURUM_RENGI = {
    Durum.BAGLI_DEGIL: "soluk",
    Durum.HAZIR: "yazi",
    Durum.HIZ_BEKLENIYOR: "uyari",
    Durum.DONUYOR: "yazi",
    Durum.KILIT_BEKLENIYOR: "iyi",
    Durum.VERI_TOPLANIYOR: "vurgu",
    Durum.DURDURULUYOR: "uyari",
    Durum.HATA: "kotu",
}


def _stil(t: dict[str, str]) -> str:
    return f"""
        QWidget {{ background: {t['zemin']}; color: {t['yazi']}; font-size: 10pt; }}
        QGroupBox {{ background: {t['panel']}; border: 1px solid {t['kenar']};
                     border-radius: 6px; margin-top: 14px; padding: 8px; }}
        QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 4px;
                            color: {t['soluk']}; }}
        QLabel {{ background: transparent; }}
        QLineEdit, QComboBox, QDoubleSpinBox, QPlainTextEdit {{
            background: {t['girdi']}; border: 1px solid {t['kenar']};
            border-radius: 4px; padding: 3px; }}
        QPushButton {{ background: {t['panel']}; border: 1px solid {t['kenar']};
                       border-radius: 4px; padding: 6px 12px; }}
        QPushButton:hover {{ border-color: {t['vurgu']}; }}
        QPushButton:disabled {{ color: {t['soluk']}; }}
        QPushButton#birincil {{ background: {t['vurgu']}; color: {t['vurgu_yazi']};
                                border-color: {t['vurgu']}; font-weight: bold; }}
        QPushButton#tehlike {{ color: {t['kotu']}; border-color: {t['kotu']};
                               font-weight: bold; }}
        QLabel#deger {{ font-family: monospace; font-size: 11pt; }}
        QLabel#buyuk {{ font-size: 12pt; font-weight: bold; }}
        QPlainTextEdit {{ font-family: monospace; font-size: 9pt; }}
    """


class MerkezlemePenceresi(QMainWindow):
    def __init__(self, p: Parametreler, baglanti, motor) -> None:
        super().__init__()
        self.p = p
        self.tema = p.tema
        self.dongu = OlcumDongusu(p, baglanti, motor, gunluk=self._gunluge_yaz)
        self.setWindowTitle("Dönen bobin — merkezleme ölçümü")
        self._kur()
        self._temayi_uygula(self.tema)
        for uyari in tutarlilik_uyarilari(p):
            self._gunluge_yaz("UYARI: " + uyari)
        self._gunluge_yaz(f"Parametreler: {p.kaynak}")

        self.zamanlayici = QTimer(self)
        self.zamanlayici.timeout.connect(self._tick)
        self.zamanlayici.start(50)
        self._yenile()

    # ------------------------------------------------------------------
    def _kur(self) -> None:
        merkez = QWidget()
        self.setCentralWidget(merkez)
        kok = QVBoxLayout(merkez)

        # Bağlantı satırı
        satir = QHBoxLayout()
        satir.addWidget(QLabel("Cihaz IP:"))
        self.ip = QLineEdit(self.p.ip)
        self.ip.setMaximumWidth(150)
        satir.addWidget(self.ip)
        self.btn_baglan = QPushButton("Bağlan")
        self.btn_baglan.clicked.connect(self._baglan_kes)
        satir.addWidget(self.btn_baglan)
        self.lbl_baglanti = QLabel()
        satir.addWidget(self.lbl_baglanti)
        satir.addStretch()
        satir.addWidget(QLabel("Tema:"))
        self.cb_tema = QComboBox()
        for anahtar, t in TEMALAR.items():
            self.cb_tema.addItem(t["ad"], anahtar)
        self.cb_tema.setCurrentIndex(list(TEMALAR).index(self.tema))
        self.cb_tema.currentIndexChanged.connect(
            lambda i: self._temayi_uygula(self.cb_tema.itemData(i))
        )
        satir.addWidget(self.cb_tema)
        kok.addLayout(satir)

        # Ayar satırı
        satir = QHBoxLayout()
        satir.addWidget(QLabel("Bobin:"))
        self.cb_kanal = QComboBox()
        self.cb_kanal.addItems(list(self.p.kanallar))
        self.cb_kanal.setCurrentText(self.p.varsayilan_kanal)
        self.cb_kanal.currentTextChanged.connect(self.dongu.kanal_sec)
        satir.addWidget(self.cb_kanal)
        satir.addSpacing(16)
        satir.addWidget(QLabel("Hız:"))
        self.hiz = QDoubleSpinBox()
        self.hiz.setRange(0.0, self.p.max_hiz_hz)
        self.hiz.setDecimals(1)
        self.hiz.setSingleStep(0.5)
        self.hiz.setSuffix(" Hz")
        self.hiz.setValue(self.p.hiz_hz)
        self.hiz.editingFinished.connect(lambda: self.dongu.hiz_ayarla(self.hiz.value()))
        satir.addWidget(self.hiz)
        satir.addSpacing(16)
        self.chk_yaz = QCheckBox("Merkezleme'ye yaz (otomatik)")
        self.chk_yaz.setChecked(True)
        self.chk_yaz.toggled.connect(self._otomatik_yaz)
        satir.addWidget(self.chk_yaz)
        satir.addStretch()
        kok.addLayout(satir)

        # Düğmeler
        satir = QHBoxLayout()
        self.btn_baslat = QPushButton("Başlat")
        self.btn_baslat.setObjectName("birincil")
        self.btn_baslat.clicked.connect(self._baslat)
        self.btn_durdur = QPushButton("Durdur")
        self.btn_durdur.setObjectName("tehlike")
        self.btn_durdur.clicked.connect(self.dongu.durdur)
        self.btn_tek = QPushButton("Tek ölçüm")
        self.btn_tek.clicked.connect(lambda: self.dongu.tek_olcum())
        self.btn_ref = QPushButton("Referans mıknatısla sıfırla")
        self.btn_ref.setToolTip(
            "Referans dipol mıknatısı takılıyken basın: faz ofseti, onun alanı "
            "saf normal ve pozitif (b0 > 0, a0 = 0) görünecek şekilde ayarlanır."
        )
        self.btn_ref.clicked.connect(lambda: self.dongu.tek_olcum(referans=True))
        for b in (self.btn_baslat, self.btn_durdur, self.btn_tek, self.btn_ref):
            satir.addWidget(b)
        satir.addStretch()
        kok.addLayout(satir)

        # Durum
        kutu = QGroupBox("Durum")
        g = QGridLayout(kutu)
        self.lbl_durum = QLabel()
        self.lbl_durum.setObjectName("buyuk")
        g.addWidget(self.lbl_durum, 0, 0, 1, 4)
        self.lbl_hiz = self._deger_etiketi(g, 1, 0, "Ölçülen hız")
        self.lbl_sayac = self._deger_etiketi(g, 1, 2, "Yazılan ölçüm")
        self.lbl_faz = self._deger_etiketi(g, 2, 0, "Faz ofseti")
        self.lbl_tepe = self._deger_etiketi(g, 2, 2, "Sinyal tepesi")
        self.lbl_uyari = QLabel()
        self.lbl_uyari.setWordWrap(True)
        g.addWidget(self.lbl_uyari, 3, 0, 1, 4)
        kok.addWidget(kutu)

        # Son ölçüm
        kutu = QGroupBox("Son ölçüm")
        g = QGridLayout(kutu)
        self.lbl_b0 = self._deger_etiketi(g, 0, 0, "b0 (dipol, normal)")
        self.lbl_a0 = self._deger_etiketi(g, 0, 2, "a0 (dipol, skew)")
        self.lbl_b1 = self._deger_etiketi(g, 1, 0, "b1 (kuadrupol, normal)")
        self.lbl_a1 = self._deger_etiketi(g, 1, 2, "a1 (kuadrupol, skew)")
        self.lbl_g = self._deger_etiketi(g, 2, 0, "Gradyen |C₂|/r_ref")
        self.lbl_zaman = self._deger_etiketi(g, 2, 2, "Zaman")
        self.lbl_xc = self._deger_etiketi(g, 3, 0, "x_c")
        self.lbl_yc = self._deger_etiketi(g, 3, 2, "y_c")
        kok.addWidget(kutu)

        self.gunluk = QPlainTextEdit()
        self.gunluk.setReadOnly(True)
        self.gunluk.setMaximumBlockCount(500)
        kok.addWidget(self.gunluk, 1)
        self.resize(760, 620)

    @staticmethod
    def _deger_etiketi(g: QGridLayout, satir: int, sutun: int, ad: str) -> QLabel:
        g.addWidget(QLabel(ad + ":"), satir, sutun)
        lbl = QLabel("—")
        lbl.setObjectName("deger")
        lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        g.addWidget(lbl, satir, sutun + 1)
        return lbl

    # ------------------------------------------------------------------
    def _temayi_uygula(self, anahtar: str) -> None:
        self.tema = anahtar
        QApplication.instance().setStyleSheet(_stil(TEMALAR[anahtar]))
        self._yenile()

    def _renk(self, ad: str) -> str:
        return TEMALAR[self.tema][ad]

    def _gunluge_yaz(self, mesaj: str) -> None:
        if hasattr(self, "gunluk"):
            self.gunluk.appendPlainText(f"{datetime.now():%H:%M:%S}  {mesaj}")

    def _baglan_kes(self) -> None:
        if self.dongu.durum is Durum.BAGLI_DEGIL:
            self.dongu.baglan(self.ip.text().strip())
        else:
            self._bekleyerek(self.dongu.kes)
        self._yenile()

    def _baslat(self) -> None:
        self.dongu.hiz_ayarla(self.hiz.value())
        self.dongu.baslat()

    def _otomatik_yaz(self, acik: bool) -> None:
        self.dongu.otomatik_yaz = acik
        self._gunluge_yaz("Merkezleme'ye otomatik yazma " + ("açık." if acik else "kapalı."))

    def _bekleyerek(self, islev) -> None:
        """Bloklayan bir işlemi (motoru güvenle durdurma) arayüzü dondurmadan yap."""
        self.lbl_durum.setText("Motor durduruluyor, lütfen bekleyin...")

        def bekle(saniye: float) -> None:
            bitis = time.monotonic() + saniye
            while time.monotonic() < bitis:
                QApplication.processEvents()
                time.sleep(0.01)

        self.zamanlayici.stop()
        try:
            islev(bekle=bekle)
        finally:
            self.zamanlayici.start(50)

    def _tick(self) -> None:
        try:
            self.dongu.tick()
        except Exception as hata:  # beklenmeyen: güvenli durdur ve göster
            self.dongu.hata_bildir(f"Beklenmeyen hata: {hata!r}")
        self._yenile()

    def _yenile(self) -> None:
        if not hasattr(self, "lbl_durum"):
            return
        d = self.dongu
        bagli = d.durum is not Durum.BAGLI_DEGIL
        self.btn_baglan.setText("Bağlantıyı kes" if bagli else "Bağlan")
        self.ip.setEnabled(not bagli)
        if bagli:
            rotor = "çevrimiçi" if d.engine.rotor_online else "ÇEVRİMDIŞI"
            renk = self._renk("iyi") if d.engine.rotor_online else self._renk("kotu")
            self.lbl_baglanti.setText(f"● Bağlı — rotor {rotor}")
        else:
            renk = self._renk("soluk")
            self.lbl_baglanti.setText("● Bağlı değil")
        self.lbl_baglanti.setStyleSheet(f"color: {renk};")

        self.btn_baslat.setEnabled(d.durum in (Durum.HAZIR, Durum.HATA) and bagli)
        self.btn_durdur.setEnabled(d.donuyor)
        self.btn_tek.setEnabled(d.donuyor)
        self.btn_ref.setEnabled(d.donuyor)

        metin = d.durum.value + (f" — {d.hata_metni}" if d.durum is Durum.HATA else "")
        if d.durum is Durum.VERI_TOPLANIYOR:
            yuzde = min(100, max(0, 100 * d._taze_ornek(d._toplama_baslangici) // d.gereken_ornek))
            metin += f" (%{yuzde})"
        self.lbl_durum.setText(metin)
        self.lbl_durum.setStyleSheet(f"color: {self._renk(_DURUM_RENGI[d.durum])};")

        self.lbl_hiz.setText(f"{d.engine.motor_speed:.2f} Hz" if bagli else "—")
        self.lbl_sayac.setText(str(d.olcum_sayisi))
        self.lbl_faz.setText(f"{d.faz_ofseti_derece:.2f}°")

        s = d.son_sonuc
        if s is None:
            return
        oran = s.tepe_V / self.p.tam_olcek_V
        self.lbl_tepe.setText(f"{s.tepe_V * 1e3:.2f} mV (tam ölçeğin %{100 * oran:.0f})")
        self.lbl_tepe.setStyleSheet(f"color: {self._renk('kotu' if d.doyma_uyarisi else 'yazi')};")
        self.lbl_uyari.setText(
            "ADC doymaya yakın: kazancı düşürün (merkezleme_olcer.yaml → adc.kazanc)."
            if d.doyma_uyarisi else ""
        )
        self.lbl_uyari.setStyleSheet(f"color: {self._renk('kotu')};")
        self.lbl_b0.setText(f"{s.c1.real:+.4e} T")
        self.lbl_a0.setText(f"{s.c1.imag:+.4e} T")
        self.lbl_b1.setText(f"{s.c2.real:+.4e} T")
        self.lbl_a1.setText(f"{s.c2.imag:+.4e} T")
        self.lbl_g.setText(f"{s.gradyen_T_m:.5f} T/m")
        z = s.merkez_m * 1e6
        self.lbl_xc.setText(f"{z.real:+.2f} µm")
        self.lbl_yc.setText(f"{z.imag:+.2f} µm")
        self.lbl_zaman.setText(f"{d.son_sonuc_zamani:%H:%M:%S}")

    def closeEvent(self, event) -> None:
        if self.dongu.durum is not Durum.BAGLI_DEGIL:
            self._bekleyerek(self.dongu.kes)
        self.zamanlayici.stop()
        event.accept()
