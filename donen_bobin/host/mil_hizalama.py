"""Mil hizalama: dönerken mekanik gürültüyü canlı izler (akımsız, mıknatıs kapalı).

    cd donen_bobin/host && python mil_hizalama.py [--hiz 8] [--pencere 4]

Şaftın iki ucu tam hizalı değilse yatak yük altında döner: tork tur içinde
dalgalanır, hız 1x ve 2x dönme frekansında oynar. Bu, dönen bobinin harmonik
uydurmasına karışır ve artıkta görünmez; o yüzden asıl gösterge enkoderden
ölçülen HIZ DALGALANMASIDIR (açının doğrusal gidişten 1x / 2x sapması, derece).
11 Kasım: milde ~19.7 Hz'lik bir titreşim bulundu (ivmeölçer de gördü); bobin
sinyalinde kendisi ve dönme frekansıyla yan bantları çıkıyor. Hizalamada en
hassas gösterge bu ("~20 Hz titreşim" ve "yan bantlar", µV).
Diğer göstergeler:
  * artık gürültü: gerilimden dönme harmonikleri çıkarıldıktan sonra kalan (µV);
    dönmeyle eşzamanlı olmayan titreşim ve elektronik gürültü
  * düşük frekans gürültüsü: artığın 0.5-6 Hz bandı (4 Kasım raporu, Bölüm 5)
  * bozuk açı: RS485'te bozulan enkoder okuması / s (kayar halka, titreşim)

Enkoderin kendi eksantrikliği 1x'te sabit bir taban bırakır; hizalamada bakılan
mutlak değer değil, şaft kaydırıldıkça DEĞİŞİMDİR. Her kaydırmadan sonra
"Ayar yaptım"a basın: CSV'ye ve grafiğe işaret düşer. Göstergeler her
--aralik saniyede son --pencere saniyelik kayan pencereden güncellenir; şaftı
yavaşça kaydırırken 1x dalgalanma azalan yöne gidilir (radyo ayarlar gibi).
Dönerken ayarlamak riskliyse önce "Durdur", kaydırın, sonra "Başlat".

Kayıt: kayitlar/<oturum>/mil_hizalama_<saat>.csv. Pencere kapanınca motor durur.
"""
from __future__ import annotations

import argparse
import csv
import math
import sys
import time
from datetime import datetime

import numpy as np

from mgf.merkezleme_koprusu import _sar, bozuk_acilari_ayikla, parametreleri_yukle

RIPIL_HARMONIK = 4        # hız dalgalanmasında bakılan en yüksek mertebe (x dönme frekansı)
GERILIM_HARMONIK = 20     # gerilimden çıkarılan dönme harmonikleri
DUSUK_BANT_HZ = (0.5, 6.0)
# 11 Kasım: milde ~19.7 Hz'lik bir titreşim (ivmeölçerde de görüldü) bobin sinyalinde
# kendisi ve 8/16 Hz'in yan bantları olarak (3.7, 11.7, 27.7 Hz) çıkıyor; şaft
# kaydırılınca 2-4 katına çıktı. Frekansı hizalamayla kayabildiği için aranır.
TITRESIM_ARAMA_HZ = (17.0, 23.0)
TITRESIM_BANT_HZ = 0.5    # tepe ve yan bantlar: frekansın ± bu kadarı
MAKS_HIZ_HZ = 8.0         # 11 Kasım: 10 Hz'de ~1 dk sonra ADC takıldı; inceleme bitene kadar


def pencere_analizi(aci_derece: np.ndarray, gerilim_V: np.ndarray, sps: float) -> dict[str, float]:
    """Bir pencerelik ham veriden (her ADC örneği: son enkoder açısı, gerilim)
    mekanik gösterge değerleri. Tam tur gerekmez; birkaç tur yeterli."""
    aci_ham = np.asarray(aci_derece, dtype=np.float64)
    v = np.asarray(gerilim_V, dtype=np.float64)
    aci, bozuk = bozuk_acilari_ayikla(aci_ham)
    sure_s = len(v) / sps
    taze = np.flatnonzero(np.r_[True, np.diff(aci) != 0])
    sonuc = {"hiz_hz": math.nan, "bozuk_aci_s": bozuk / sure_s, "artik_uV": math.nan,
             "dusuk_frekans_uV": math.nan, "ripil_rms_derece": math.nan, "titresim_hz": math.nan,
             "titresim_uV": math.nan, "yan_bant_uV": math.nan}
    sonuc.update({f"ripil_{n}x_derece": math.nan for n in range(1, RIPIL_HARMONIK + 1)})
    if len(taze) < 50:
        return sonuc  # motor duruyor ya da enkoder akmıyor

    # Hız dalgalanması: okuma anlarında açılmış açı; doğrusal + yavaş sürüklenme
    # (t²) çıkarılınca kalan, açının 1..4 harmoniklerine uydurulur
    t = taze / sps
    teta = np.unwrap(np.radians(aci[taze]))
    tm = t - t.mean()
    egim = np.polyfit(tm, teta, 2)
    teta_d = np.polyval(egim, tm)
    hiz = egim[1] / (2 * math.pi)
    sonuc["hiz_hz"] = float(hiz)
    sapma = np.degrees(teta - teta_d)
    sutun = [np.ones_like(tm)]
    for n in range(1, RIPIL_HARMONIK + 1):
        sutun += [np.cos(n * teta_d), np.sin(n * teta_d)]
    a = np.column_stack(sutun)
    k, *_ = np.linalg.lstsq(a, sapma, rcond=None)
    for n in range(1, RIPIL_HARMONIK + 1):
        sonuc[f"ripil_{n}x_derece"] = float(math.hypot(k[2 * n - 1], k[2 * n]))
    sonuc["ripil_rms_derece"] = float(np.std(a[:, 1:] @ k[1:]))

    # Gerilim artığı: her örneğin açısı okumalar arasında doğrusal enterpolasyonla
    sira = np.arange(len(v), dtype=np.float64)
    teta_v = np.interp(sira, taze.astype(np.float64), teta)
    zaman = np.linspace(-1.0, 1.0, len(v))
    sutun = [zaman ** i for i in range(4)]
    for n in range(1, GERILIM_HARMONIK + 1):
        sutun += [np.cos(n * teta_v), np.sin(n * teta_v)]
    a = np.column_stack(sutun)
    k, *_ = np.linalg.lstsq(a, v, rcond=None)
    artik = v - a @ k
    sonuc["artik_uV"] = float(np.std(artik) * 1e6)
    spektrum = np.fft.rfft(artik * np.hanning(len(artik)))
    frekans = np.fft.rfftfreq(len(artik), 1 / sps)
    # Hanning penceresinin güç kaybı (3/8) düzeltilmiş tek taraflı güç (V², rms²)
    guc = np.abs(spektrum) ** 2 * 2 / (len(artik) ** 2 * 3 / 8)

    def bant_rms(f1: float, f2: float) -> float:
        return float(math.sqrt(np.sum(guc[(frekans >= f1) & (frekans <= f2)])) * 1e6)

    sonuc["dusuk_frekans_uV"] = bant_rms(*DUSUK_BANT_HZ)
    arama = np.flatnonzero((frekans >= TITRESIM_ARAMA_HZ[0]) & (frekans <= TITRESIM_ARAMA_HZ[1]))
    if len(arama):
        ft = float(frekans[arama[np.argmax(guc[arama])]])
        fd, b = abs(hiz), TITRESIM_BANT_HZ
        sonuc["titresim_hz"] = ft
        sonuc["titresim_uV"] = bant_rms(ft - b, ft + b)
        yanlar = [abs(fd - ft), fd + ft, abs(2 * fd - ft)]
        sonuc["yan_bant_uV"] = float(math.sqrt(sum(bant_rms(f - b, f + b) ** 2 for f in yanlar)))
    return sonuc


GOSTERGELER = [  # (anahtar, etiket, birim, ondalık); ilk üçü hizalamada asıl bakılanlar
    ("titresim_uV", "~20 Hz titreşim", "µV", 2),
    ("yan_bant_uV", "Titreşim yan bantları", "µV", 2),
    ("artik_uV", "Artık gürültü", "µV", 1),
    ("dusuk_frekans_uV", "0.5–6 Hz gürültü", "µV", 2),
    ("titresim_hz", "Titreşim frekansı", "Hz", 2),
    ("bozuk_aci_s", "Bozuk açı", "/s", 2),
    ("ripil_1x_derece", "Hız dalgalanması 1×", "°", 3),
    ("ripil_2x_derece", "Hız dalgalanması 2×", "°", 3),
    ("hiz_hz", "Ölçülen hız", "Hz", 3),
]


def main(argv: list[str] | None = None) -> int:
    a = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    a.add_argument("--hiz", type=float, default=8.0)
    a.add_argument("--pencere", type=float, default=4.0, help="kayan gösterge penceresi (s)")
    a.add_argument("--aralik", type=float, default=1.0, help="göstergelerin güncellenme aralığı (s)")
    a.add_argument("--parametreler", default=None)
    g = a.parse_args(argv)
    if argv is None:  # komut satırından: ölçüm sürerken bilgisayar uyumasın
        from uyku import uykuyu_engelle

        uykuyu_engelle("Mil hizalama ölçümü sürüyor")
    if not 0 < g.hiz <= MAKS_HIZ_HZ:
        print(f"hız 0 ile {MAKS_HIZ_HZ} Hz arasında olmalı", file=sys.stderr)
        return 2

    import pyqtgraph as pg
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import (
        QApplication, QDoubleSpinBox, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QMainWindow,
        QPushButton, QVBoxLayout, QWidget,
    )

    from mgf.connection import MgfConnection
    from mgf.data_engine import DataEngine
    from mgf.olcum_dongusu import Durum, OlcumDongusu

    p = parametreleri_yukle(g.parametreler)
    uygulama = QApplication(sys.argv[:1])
    pencere = QMainWindow()
    pencere.setWindowTitle("Mil hizalama: canlı mekanik gürültü (akımsız)")
    kok = QWidget()
    dikey = QVBoxLayout(kok)
    pencere.setCentralWidget(kok)

    dongu = OlcumDongusu(p, MgfConnection(p.ip, p.port), DataEngine(),
                         gunluk=lambda m: pencere.statusBar().showMessage(f"{datetime.now():%H:%M:%S}  {m}", 20000))

    satir = QHBoxLayout()
    hiz = QDoubleSpinBox()
    hiz.setRange(1.0, MAKS_HIZ_HZ)
    hiz.setDecimals(1)
    hiz.setSuffix(" Hz")
    hiz.setValue(g.hiz)
    btn_baslat, btn_durdur = QPushButton("Başlat"), QPushButton("Durdur")
    not_kutusu = QLineEdit()
    not_kutusu.setPlaceholderText("ayar notu (ör. alt yatak 1/4 tur sağa)")
    btn_isaret = QPushButton("Ayar yaptım")
    for w in (QLabel("Hız:"), hiz, btn_baslat, btn_durdur):
        satir.addWidget(w)
    satir.addSpacing(20)
    satir.addWidget(not_kutusu, 1)
    satir.addWidget(btn_isaret)
    dikey.addLayout(satir)

    izgara = QGridLayout()
    etiketler: dict[str, QLabel] = {}
    for i, (anahtar, ad, birim, _) in enumerate(GOSTERGELER):
        baslik = QLabel(ad)
        deger = QLabel("—")
        deger.setStyleSheet("font-size: 26pt; font-weight: bold;")
        izgara.addWidget(baslik, 2 * (i // 3), i % 3)
        izgara.addWidget(deger, 2 * (i // 3) + 1, i % 3)
        etiketler[anahtar] = deger
    dikey.addLayout(izgara)
    durum_etiketi = QLabel("Bağlanılıyor...")
    dikey.addWidget(durum_etiketi)

    grafikler = pg.GraphicsLayoutWidget()
    dikey.addWidget(grafikler, 1)
    g_titresim = grafikler.addPlot(row=0, col=0, title="~20 Hz titreşim ve yan bantları (µV)")
    g_gurultu = grafikler.addPlot(row=1, col=0, title="Gürültü (µV)")
    g_ripil = grafikler.addPlot(row=2, col=0, title="Hız dalgalanması (°)")
    g_bozuk = grafikler.addPlot(row=3, col=0, title="Bozuk açı (/s)")
    for gr in (g_titresim, g_gurultu, g_ripil, g_bozuk):
        gr.addLegend(offset=(5, 5))
        gr.showGrid(x=True, y=True, alpha=0.3)
        gr.setLabel("bottom", "zaman (dk)")
    egriler = {
        "titresim_uV": g_titresim.plot(pen=pg.mkPen("#c0392b", width=2), name="~20 Hz"),
        "yan_bant_uV": g_titresim.plot(pen=pg.mkPen("#16a085", width=2), name="yan bantlar"),
        "ripil_1x_derece": g_ripil.plot(pen=pg.mkPen("#e67e22", width=2), name="1×"),
        "ripil_2x_derece": g_ripil.plot(pen=pg.mkPen("#3498db", width=2), name="2×"),
        "artik_uV": g_gurultu.plot(pen=pg.mkPen("#e74c3c", width=2), name="artık"),
        "dusuk_frekans_uV": g_gurultu.plot(pen=pg.mkPen("#9b59b6", width=2), name="0.5–6 Hz"),
        "bozuk_aci_s": g_bozuk.plot(pen=pg.mkPen("#2ecc71", width=2), name="bozuk açı"),
    }
    seriler: dict[str, list[float]] = {k: [] for k in ["t_dk", *egriler]}
    t0 = time.monotonic()
    son_analiz = [0.0]
    durum = {"csv": None, "yazici": None, "isaret": ""}

    def csv_ac():
        if durum["csv"] is None:
            yol = dongu.oturum.klasor() / f"mil_hizalama_{datetime.now():%H%M%S}.csv"
            durum["csv"] = open(yol, "w", newline="", encoding="utf-8")
            durum["yazici"] = csv.writer(durum["csv"])
            durum["yazici"].writerow(["zaman", "t_dk", "hedef_hiz_hz", *[k for k, *_ in GOSTERGELER],
                                      "ripil_3x_derece", "ripil_4x_derece", "ripil_rms_derece", "isaret"])
            pencere.statusBar().showMessage(f"Kayıt: {yol}", 20000)

    def isaret_koy():
        metin = not_kutusu.text().strip() or "ayar"
        durum["isaret"] = metin
        t = (time.monotonic() - t0) / 60
        for gr in (g_titresim, g_gurultu, g_ripil, g_bozuk):
            gr.addItem(pg.InfiniteLine(pos=t, angle=90, pen=pg.mkPen("#888", style=pg.QtCore.Qt.DashLine),
                                       label=metin, labelOpts={"position": 0.9, "rotateAxis": (1, 0)}))
        pencere.statusBar().showMessage(f"{datetime.now():%H:%M:%S}  ✓ işaret: {metin}", 20000)
        not_kutusu.clear()

    def analiz():
        veri = dongu._ham_veri(g.pencere)
        if veri is None or len(veri[1]) < g.pencere * p.ornekleme_sps * 0.9:
            return
        s = pencere_analizi(veri[0], veri[1], p.ornekleme_sps)
        if not math.isfinite(s["hiz_hz"]):
            return
        t = (time.monotonic() - t0) / 60
        seriler["t_dk"].append(t)
        for anahtar, egri in egriler.items():
            seriler[anahtar].append(s[anahtar])
            egri.setData(seriler["t_dk"], seriler[anahtar])
        for anahtar, _, birim, ondalik in GOSTERGELER:
            gecmis = seriler.get(anahtar)
            en_iyi = f"  <small>(en iyi {min(gecmis):.{ondalik}f})</small>" if gecmis else ""
            etiketler[anahtar].setText(f"{s[anahtar]:.{ondalik}f} {birim}{en_iyi}")
        csv_ac()
        durum["yazici"].writerow([datetime.now().isoformat(timespec="seconds"), f"{t:.3f}", hiz.value(),
                                  *[f"{s[k]:.5g}" for k, *_ in GOSTERGELER],
                                  f"{s['ripil_3x_derece']:.5g}", f"{s['ripil_4x_derece']:.5g}",
                                  f"{s['ripil_rms_derece']:.5g}", durum["isaret"]])
        durum["csv"].flush()
        durum["isaret"] = ""

    def tik():
        dongu.tick()
        durum_etiketi.setText(f"Durum: {dongu.durum.value}")
        simdi = time.monotonic()
        if dongu.durum is Durum.DONUYOR and simdi - son_analiz[0] >= g.aralik:
            son_analiz[0] = simdi
            analiz()

    def baslat():
        dongu.otomatik_yaz_ayarla(False)
        dongu.hiz_ayarla(hiz.value())
        dongu.baslat()
        son_analiz[0] = time.monotonic() + g.pencere  # hız oturduktan sonra ilk tam pencere

    btn_baslat.clicked.connect(baslat)
    btn_durdur.clicked.connect(dongu.durdur)
    btn_isaret.clicked.connect(isaret_koy)
    not_kutusu.returnPressed.connect(isaret_koy)
    hiz.editingFinished.connect(lambda: dongu.hiz_ayarla(hiz.value()))

    zamanlayici = QTimer()
    zamanlayici.timeout.connect(tik)
    zamanlayici.start(20)

    def kapat(olay):
        zamanlayici.stop()
        try:
            dongu.durdur()
            bitis = time.monotonic() + 8
            while dongu.donuyor and time.monotonic() < bitis:
                dongu.tick()
                time.sleep(0.02)
            dongu.kes()
        finally:
            if durum["csv"] is not None:
                durum["csv"].close()
        olay.accept()

    pencere.closeEvent = kapat
    pencere.resize(1000, 900)
    pencere.show()
    if not dongu.baglan():
        durum_etiketi.setText("Pico'ya bağlanılamadı.")
    return int(uygulama.exec())


if __name__ == "__main__":
    raise SystemExit(main())
