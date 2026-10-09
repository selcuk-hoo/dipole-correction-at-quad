"""Merkezleme ölçümü için tek pencerelik minimal arayüz (PySide6).

Bütün iş `OlcumDongusu`'ndadır; pencere yalnızca düğmeleri ona bağlar ve
50 ms'de bir `tick()` çağırıp durumu gösterir. `mgf.ui` paketine konmadı,
çünkü o paket açılırken büyük arayüzün tüm bağımlılıklarını (vispy,
pyqtgraph) yükler.
"""
from __future__ import annotations

import time
from datetime import datetime

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QKeySequence, QShortcut
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
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .merkezleme_koprusu import HARMONIK_SAYISI, Parametreler, tutarlilik_uyarilari
from .merkezleme_yardim import YardimPenceresi
from .olcum_dongusu import Durum, OlcumDongusu

# Çok kutup grafiğindeki seriler: ad -> (x kayması, çubuk genişliği)
_SERILER = {"b": (-0.2, 0.38), "a": (0.2, 0.38), "genlik": (0.0, 0.6)}
GOSTERIMLER = {"bilesen": "Normal ve skew", "genlik": "Genlik |C_n|"}
# Çok kutup grafiğinin dikey ekseni: (seçenek adı, genliği 1 yapılan mertebe, eksen etiketi)
OLCEKLER = {
    "gercek": ("Gerçek alan (T)", None, "|C_n| (T, r_ref'te)"),
    "n1": ("n = 1'e göre", 1, "|C_n| / |C₁|"),
    "n2": ("n = 2'ye göre", 2, "|C_n| / |C₂|"),
}
_HAM_NOKTA_SAYISI = 4000  # bobin gerilimi grafiğinde gösterilen en fazla örnek

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
        QLineEdit, QComboBox, QDoubleSpinBox, QPlainTextEdit, QTextBrowser {{
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
        QLabel#aciklama {{ color: {t['soluk']}; font-size: 9pt; }}
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
        self.btn_yardim = QPushButton("Yardım")
        self.btn_yardim.setToolTip("Kısa kullanım kılavuzu (F1)")
        self.btn_yardim.clicked.connect(self._yardim)
        satir.addWidget(self.btn_yardim)
        QShortcut(QKeySequence.HelpContents, self, activated=self._yardim)
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
        satir.addWidget(QLabel("Ölçüm süresi:"))
        self.sure = QDoubleSpinBox()
        self.sure.setRange(0.5, round(self.dongu.max_pencere_s))
        self.sure.setDecimals(1)
        self.sure.setSingleStep(1.0)
        self.sure.setSuffix(" s")
        self.sure.setValue(self.p.pencere_s)
        self.sure.setToolTip(
            "Rastgele gürültü 1/√süre ile azalır. Dönmeyle eşzamanlı hatalar ve yavaş\n"
            "sürüklenme azalmaz; merkezleme'nin her adımı da bu kadar uzar."
        )
        self.sure.editingFinished.connect(lambda: self.dongu.pencere_ayarla(self.sure.value()))
        satir.addWidget(self.sure)
        satir.addStretch()
        kok.addLayout(satir)
        self.chk_yaz = QCheckBox("Merkezleme'ye yaz")
        self.chk_yaz.setChecked(True)
        self.chk_yaz.toggled.connect(self._otomatik_yaz)
        self.chk_yaz.setToolTip(
            "Kapalıyken merkezleme'ye yazılmaz; her ölçüm süresinde bir sürekli ölçüm alınır."
        )
        self.chk_csv = QCheckBox("CSV'ye kaydet")
        self.chk_csv.setChecked(True)
        self.chk_csv.toggled.connect(lambda acik: setattr(self.dongu, "csv_kaydet", acik))
        self.chk_csv.setToolTip(f"Her oturum ayrı dosya: {self.p.kayit_dizini}")

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
        satir.addWidget(self.chk_yaz)
        satir.addWidget(self.chk_csv)
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
        g.addWidget(QLabel("Kayıt:"), 3, 0)
        self.lbl_kayit = QLabel("—")
        self.lbl_kayit.setTextInteractionFlags(Qt.TextSelectableByMouse)
        g.addWidget(self.lbl_kayit, 3, 1, 1, 3)
        self.lbl_uyari = QLabel()
        self.lbl_uyari.setWordWrap(True)
        g.addWidget(self.lbl_uyari, 4, 0, 1, 4)
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

        # Sekmeler: çok kutuplar, ham sinyal, günlük
        self.sekmeler = QTabWidget()
        self._grafikleri_kur()
        self.gunluk = QPlainTextEdit()
        self.gunluk.setReadOnly(True)
        self.gunluk.setMaximumBlockCount(500)
        self.sekmeler.addTab(self.gunluk, "Günlük")
        kok.addWidget(self.sekmeler, 1)
        self._cizilen = None
        self.resize(800, 840)

    def _grafikleri_kur(self) -> None:
        sayfa = QWidget()
        dikey = QVBoxLayout(sayfa)
        ust = QHBoxLayout()
        ust.addWidget(QLabel("Göster:"))
        self.gosterim = "bilesen"
        self.cb_gosterim = QComboBox()
        for anahtar, ad in GOSTERIMLER.items():
            self.cb_gosterim.addItem(ad, anahtar)
        self.cb_gosterim.currentIndexChanged.connect(
            lambda i: self._gosterim_sec(self.cb_gosterim.itemData(i))
        )
        ust.addWidget(self.cb_gosterim)
        ust.addSpacing(12)
        ust.addWidget(QLabel("Ölçek:"))
        self.olcek = "gercek"
        self.cb_olcek = QComboBox()
        for anahtar, (ad, _, _) in OLCEKLER.items():
            self.cb_olcek.addItem(ad, anahtar)
        self.cb_olcek.currentIndexChanged.connect(
            lambda i: self._olcek_sec(self.cb_olcek.itemData(i))
        )
        ust.addWidget(self.cb_olcek)
        ust.addStretch()
        btn = QPushButton("Ortalamayı sıfırla")
        btn.clicked.connect(self._ortalamayi_sifirla)
        ust.addWidget(btn)
        dikey.addLayout(ust)
        self.lbl_cok_kutup = QLabel()
        self.lbl_cok_kutup.setTextFormat(Qt.RichText)
        dikey.addWidget(self.lbl_cok_kutup)

        self.grafik_cok = pg.PlotWidget()
        self.grafik_cok.setMenuEnabled(False)
        self.grafik_cok.setMouseEnabled(x=False, y=False)
        # Log eksen: BarGraphItem/ErrorBarItem log kipini kendileri uygulamadığı
        # için bunlara log10 değerler verilir; eksen yalnızca 10^k etiketler.
        self.grafik_cok.setLogMode(x=False, y=True)
        self.grafik_cok.getAxis("left").enableAutoSIPrefix(False)  # "(x0.001)" çarpanı log'da yanıltıcı
        self.grafik_cok.getAxis("bottom").setTicks(
            [[(n, f"{n}") for n in range(1, HARMONIK_SAYISI + 1)]]
        )
        self.grafik_cok.setXRange(0.4, HARMONIK_SAYISI + 0.6, padding=0)
        self.seriler = {ad: self._seri_kur(kayma, genislik) for ad, (kayma, genislik) in _SERILER.items()}
        dikey.addWidget(self.grafik_cok)
        self.sekmeler.addTab(sayfa, "Çok kutuplar")

        sayfa = QWidget()
        dikey = QVBoxLayout(sayfa)
        aciklama = QLabel(
            "Son ölçüm penceresinde ADC'nin kaydettiği bobin gerilimi; penceredeki bütün "
            "turlar enkoder açısına göre üst üste çizilir. Çizgi, uydurulan harmoniklerin "
            "toplamıdır (n = 1..6). Noktalar çizginin üstündeyse ölçüm sağlıklıdır; sistematik "
            "sapma, sıçrama ya da düzleşmiş tepeler (doyma) bir sorun olduğunu gösterir."
        )
        aciklama.setObjectName("aciklama")
        aciklama.setWordWrap(True)
        dikey.addWidget(aciklama)
        self.grafik_ham = pg.PlotWidget()
        self.grafik_ham.setMenuEnabled(False)
        self.grafik_ham.setXRange(0, 360, padding=0.01)
        self.grafik_ham.getAxis("bottom").setTicks([[(a, f"{a}") for a in range(0, 361, 45)]])
        self.ham_noktalar = self.grafik_ham.plot([], [], pen=None, symbol="o", symbolSize=2)
        self.ham_uydurma = self.grafik_ham.plot([], [])
        self.ham_noktalar.setZValue(1)  # sapmalar uydurma eğrisinin üstünde görünsün
        dikey.addWidget(self.grafik_ham)
        self.sekmeler.addTab(sayfa, "Bobin gerilimi")

    def _seri_kur(self, kayma: float, genislik: float) -> dict:
        x = np.arange(1, HARMONIK_SAYISI + 1) + kayma
        sifir = np.zeros(HARMONIK_SAYISI)
        seri = {
            "x": x,
            "cubuk": pg.BarGraphItem(x=x, y0=sifir, y1=sifir, width=genislik),
            "hata": pg.ErrorBarItem(x=x, y=sifir, top=sifir, bottom=sifir, beam=genislik / 4),
            "yazilar": [pg.TextItem(anchor=(0.5, 1.0)) for _ in x],
        }
        for oge in (seri["cubuk"], seri["hata"], *seri["yazilar"]):
            self.grafik_cok.addItem(oge)
        return seri

    def _grafik_temasi(self) -> None:
        t = TEMALAR[self.tema]
        for grafik in (self.grafik_cok, self.grafik_ham):
            grafik.setBackground(t["panel"])
            grafik.showGrid(x=False, y=True, alpha=0.25)
            for kenar in ("left", "bottom"):
                eksen = grafik.getAxis(kenar)
                eksen.setPen(pg.mkPen(t["soluk"]))
                eksen.setTextPen(pg.mkPen(t["yazi"]))
        self.grafik_cok.setLabel("left", OLCEKLER[self.olcek][2], color=t["yazi"])
        self.grafik_cok.setLabel("bottom", "n (1 dipol, 2 kuadrupol, 3 sekstupol, ...)", color=t["yazi"])
        self.grafik_ham.setLabel("left", "Bobin gerilimi (mV)", color=t["yazi"])
        self.grafik_ham.setLabel("bottom", "Açı (°, faz ofsetli)", color=t["yazi"])
        for seri in self.seriler.values():
            seri["hata"].setData(pen=pg.mkPen(t["yazi"], width=1))
            for yazi in seri["yazilar"]:
                yazi.setColor(t["yazi"])
        nokta = pg.mkColor(t["soluk"])
        nokta.setAlpha(90)  # yarı saydam: uydurma çizgisi altından görünsün
        self.ham_noktalar.setSymbolBrush(pg.mkBrush(nokta))
        self.ham_noktalar.setSymbolPen(None)
        self.ham_uydurma.setPen(pg.mkPen(t["vurgu"], width=1.5))

    def _ortalamayi_sifirla(self) -> None:
        self.dongu.gecmisi_sifirla()
        self._grafikleri_ciz()

    def _olcek_sec(self, anahtar: str) -> None:
        self.olcek = anahtar
        self.grafik_cok.setLabel("left", OLCEKLER[anahtar][2], color=self._renk("yazi"))
        self._grafikleri_ciz()

    def _gosterim_sec(self, anahtar: str) -> None:
        self.gosterim = anahtar
        self._grafikleri_ciz()

    @staticmethod
    def _seri_gorunur(seri: dict, gorunur: bool) -> None:
        # Sıfırlamak yetmez: log eksende y0 = y1 = 0, değeri 1 olan bir çizgi çizer
        for oge in (seri["cubuk"], seri["hata"], *seri["yazilar"]):
            oge.setVisible(gorunur)

    def _seri_ciz(self, seri: dict, deger: np.ndarray, sigma: np.ndarray, taban_us: float,
                  renk: str, gercek_alan: bool) -> None:
        """İşaretli değerleri log eksende çizer: yükseklik |değer|, negatifler
        içi boş çubuk, etikette işaretli değer."""
        self._seri_gorunur(seri, True)
        taban = 10.0 ** taban_us
        mutlak = np.abs(deger)
        ust = np.log10(np.maximum(mutlak, taban))
        alt = np.log10(np.maximum(mutlak - sigma, taban))
        tepe = np.log10(np.maximum(mutlak + sigma, taban))
        seri["cubuk"].setOpts(
            y0=np.full_like(ust, taban_us), y1=ust,
            brushes=[pg.mkBrush(renk) if v >= 0 else pg.mkBrush(None) for v in deger],
            pens=[pg.mkPen(renk, width=1.5) for _ in deger],
        )
        seri["hata"].setData(x=seri["x"], y=ust, top=tepe - ust, bottom=ust - alt)
        # Normal/skew'de iki çubuk yan yana: etiketler kısa ve işaretli
        bilesen = self.gosterim == "bilesen"
        isaret, ussel, anlamli = ("+", ".1e", ".2g") if bilesen else ("", ".2e", ".3g")
        for i, yazi in enumerate(seri["yazilar"]):
            v = deger[i]
            if gercek_alan:
                yazi.setText(f"{v:{isaret}{ussel}}")
            else:
                yazi.setText(f"{v:{isaret}.0f}" if abs(v) >= 100 else f"{v:{isaret}{anlamli}}")
            yazi.setPos(seri["x"][i], tepe[i])

    def _grafikleri_ciz(self) -> None:
        d = self.dongu
        t = TEMALAR[self.tema]
        n_olcum, ortalama, sigma = d.harmonik_istatistigi()  # Tesla
        genlik = np.abs(ortalama)
        referans = OLCEKLER[self.olcek][1]
        for seri in self.seriler.values():
            self._seri_gorunur(seri, False)
        if n_olcum == 0:
            self.lbl_cok_kutup.setText("Henüz ölçüm yok")
        elif referans is not None and genlik[referans - 1] <= 0:
            self.lbl_cok_kutup.setText(f"n = {referans} genliği sıfır; bu ölçek kullanılamıyor")
        else:
            bolen = 1.0 if referans is None else genlik[referans - 1]
            if self.gosterim == "bilesen":
                cizilecek = {
                    "b": (ortalama.real / bolen, sigma.real / bolen, t["vurgu"]),
                    "a": (ortalama.imag / bolen, sigma.imag / bolen, t["uyari"]),
                }
                aciklama = (
                    f"<span style='color:{t['vurgu']}'>■</span> b<sub>n</sub> normal &nbsp; "
                    f"<span style='color:{t['uyari']}'>■</span> a<sub>n</sub> skew &nbsp; "
                    "(içi boş çubuk: negatif)"
                )
            else:
                # Genlik σ'sı: normal ve skew saçılımlarının bileşkesi
                cizilecek = {"genlik": (genlik / bolen, np.abs(sigma) / bolen, t["vurgu"])}
                aciklama = "|ortalama C<sub>n</sub>|"
            tum = np.concatenate([np.abs(v) for v, _, _ in cizilecek.values()])
            en_buyuk = float(max(np.abs(v).max() + s.max() for v, s, _ in cizilecek.values()))
            pozitif = tum[tum > 0]
            taban_us = np.floor(np.log10(pozitif.min())) if len(pozitif) else np.log10(en_buyuk) - 3
            taban_us = max(taban_us, np.floor(np.log10(en_buyuk)) - 9)  # en fazla 9 onluk
            for ad, (deger, s, renk) in cizilecek.items():
                self._seri_ciz(self.seriler[ad], deger, s, taban_us, renk, referans is None)
            self.grafik_cok.setYRange(taban_us, np.log10(en_buyuk) + 0.6, padding=0)
            self.lbl_cok_kutup.setText(
                f"Son {n_olcum} ölçümün ortalaması ± σ (tek ölçüm saçılımı) &nbsp;·&nbsp; "
                f"|C<sub>1</sub>| = {genlik[0]:.3e} T, |C<sub>2</sub>| = {genlik[1]:.3e} T"
                f" &nbsp;·&nbsp; {aciklama}"
            )

        s = d.son_sonuc
        if s is None or not len(s.aci_derece):
            self.ham_noktalar.setData([], [])
            self.ham_uydurma.setData([], [])
            return
        adim = max(1, len(s.aci_derece) // _HAM_NOKTA_SAYISI)
        self.ham_noktalar.setData(s.aci_derece[::adim], s.gerilim_V[::adim] * 1e3)
        izgara = np.linspace(0.0, 360.0, 721)
        self.ham_uydurma.setData(izgara, s.uydurma(izgara) * 1e3)

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
        if hasattr(self, "grafik_cok"):
            self._grafik_temasi()
            self._grafikleri_ciz()
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

    def _yardim(self) -> None:
        # Kipsiz: ölçüm sürerken açık kalabilir, zamanlayıcıyı durdurmaz
        if not hasattr(self, "yardim_penceresi"):
            self.yardim_penceresi = YardimPenceresi(self.p, self.dongu.max_pencere_s, self)
        self.yardim_penceresi.show()
        self.yardim_penceresi.raise_()

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
        if d.kayit.yol is not None:
            self.lbl_kayit.setText(f"{d.kayit.yol.name} ({d.kayit.satir_sayisi} satır)")
        else:
            self.lbl_kayit.setText("henüz yok" if d.csv_kaydet else "kapalı")

        s = d.son_sonuc
        if s is not self._cizilen:
            self._cizilen = s
            self._grafikleri_ciz()
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
