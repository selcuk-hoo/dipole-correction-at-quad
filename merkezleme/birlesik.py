"""Tek pencere: dönen bobin ölçümü ve merkezleme, iki sekme.

    ./merkezle            (gerçek donanım; depo kökünden)
    ./merkezle kuru       (güç kaynaklarına komut gitmez)
    python -m merkezleme.birlesik [--canli] [--yapilandirma Y] [--parametreler P]

"Dönen bobin" sekmesi açılınca Pico'ya bağlanır; motoru kullanıcı o sekmedeki
"Başlat" ile çalıştırır (açılışta motor dönmez).
"Merkezleme" sekmesinde önce nominal akım ve merkez toleransı seçilir,
"Merkezlemeyi başlat" ile akış kurulur. İki sekme, ayrı programlarken olduğu
gibi kilit dosyası üzerinden konuşur (`DosyaGirisi`); bekleme olay döngüsünü
işlettiği için dönen bobin sekmesi bu sırada ölçmeye devam eder. Akış bitince
"Yeni çalıştırma" akımları sıfırlayıp ayar paneline döner. Pencere kapanınca
akımlar rampa ile sıfıra iner, çıkışlar kapanır, motor durur.
"""
from __future__ import annotations

import argparse
import dataclasses
import os
import signal
import sys
from datetime import datetime
from pathlib import Path
from typing import Callable

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .ana import _kaynak_grubu_kur, kipi_uygula
from .arayuz import MerkezlemePencere, qt_bekle
from .guc_kaynagi import KomutGunlugu
from .harmonikler import HarmonikKonvansiyonu
from .is_akisi import IsAkisi
from .kayit import Calistirma
from .modlar import ModBazi
from .olcum_kaynagi import DosyaGirisi
from .yapilandirma import Yapilandirma, yapilandirma_yukle

KOK = Path(__file__).resolve().parents[1]
HOST = KOK / "donen_bobin" / "host"


def ayarlari_uygula(kfg: Yapilandirma, nominal_akim_A: float, merkez_toleransi_um: float) -> Yapilandirma:
    """Arayüzde seçilen nominal akımı ve toleransı yapılandırmaya yazar."""
    return dataclasses.replace(
        kfg,
        miknatis=dataclasses.replace(kfg.miknatis, nominal_akim_A=float(nominal_akim_A)),
        duzeltme=dataclasses.replace(kfg.duzeltme, merkez_toleransi_um=float(merkez_toleransi_um)),
    )


class MerkezlemeSekmesi(QWidget):
    """Ayar paneli -> merkezleme penceresi -> (yeni çalıştırma) -> ayar paneli."""

    def __init__(
        self,
        kfg: Yapilandirma,
        canli: bool,
        bobin_hazir: Callable[[], tuple[bool, str]],
        olcum_kaynagi_uret: Callable[[Yapilandirma, HarmonikKonvansiyonu], object] | None = None,
        donanim_sorunu: str | None = None,
        merkezleme_acilinca: Callable[[], None] | None = None,
    ) -> None:
        super().__init__()
        self.kfg = kipi_uygula(kfg, canli)
        self.canli = canli
        self.bobin_hazir = bobin_hazir
        self.olcum_kaynagi_uret = olcum_kaynagi_uret or (
            lambda k, konv: DosyaGirisi(k.dosya_girisi, konv, bekle=qt_bekle)
        )
        self.donanim_sorunu = donanim_sorunu
        # Merkezleme penceresi temasını uygulama geneline yazar; dönen bobin
        # sekmesininkini geri getirmek için (main bunu verir)
        self.merkezleme_acilinca = merkezleme_acilinca or (lambda: None)
        self.pencere: MerkezlemePencere | None = None

        self.yigin = QStackedWidget()
        self.yigin.addWidget(self._ayar_panelini_kur())
        self.calisma_sayfasi = QWidget()
        cs = QVBoxLayout(self.calisma_sayfasi)
        ust = QHBoxLayout()
        self.calisma_etiketi = QLabel()
        ust.addWidget(self.calisma_etiketi)
        ust.addStretch()
        self.otomatik_calisma = QCheckBox("Otomatik (onay beklemeden)")
        self.otomatik_calisma.setToolTip(
            "Ölçümleri ve düzeltme önerilerini kendiliğinden onaylar. Röle/modülatör gibi\n"
            "kullanıcı eylemleri ve duraklatma yine size bırakılır. İstediğiniz an kapatılabilir.")
        ust.addWidget(self.otomatik_calisma)
        self.yeni_dugmesi = QPushButton("Yeni çalıştırma (akımları sıfırla, ayarlara dön)")
        self.yeni_dugmesi.clicked.connect(self.yeni_calistirma)
        ust.addWidget(self.yeni_dugmesi)
        cs.addLayout(ust)
        self.yigin.addWidget(self.calisma_sayfasi)
        duzen = QVBoxLayout(self)
        duzen.setContentsMargins(0, 0, 0, 0)
        duzen.addWidget(self.yigin)

        self.zamanlayici = QTimer(self)
        self.zamanlayici.timeout.connect(self._durumu_yenile)
        self.zamanlayici.start(500)
        self.otomatik_zamanlayici = QTimer(self)
        self.otomatik_zamanlayici.timeout.connect(self._otomatik_ilerle)
        self.otomatik_zamanlayici.start(300)
        self._durumu_yenile()

    # ------------------------------------------------------------------
    def _ayar_panelini_kur(self) -> QWidget:
        k = self.kfg
        sayfa = QWidget()
        duzen = QVBoxLayout(sayfa)
        self.kip_etiketi = QLabel(
            "Kip: <b>CANLI</b> — güç kaynakları gerçekten sürülür" if self.canli
            else "Kip: <b>KURU</b> — komutlar yalnızca günlüğe yazılır, güç kaynaklarına gitmez"
        )
        self.kip_etiketi.setStyleSheet("color: #c0392b;" if self.canli else "")
        duzen.addWidget(self.kip_etiketi)

        kutu = QGroupBox("Merkezleme ayarları (bu çalıştırma için)")
        form = QFormLayout(kutu)
        self.nominal_kutusu = QDoubleSpinBox()
        self.nominal_kutusu.setRange(0.5, k.guvenlik.bobin_basi_max_akim_A)
        self.nominal_kutusu.setDecimals(2)
        self.nominal_kutusu.setSingleStep(0.5)
        self.nominal_kutusu.setSuffix(" A")
        self.nominal_kutusu.setValue(k.miknatis.nominal_akim_A)
        self.nominal_kutusu.valueChanged.connect(self._durumu_yenile)
        form.addRow("Nominal akım", self.nominal_kutusu)
        self.tolerans_kutusu = QDoubleSpinBox()
        self.tolerans_kutusu.setRange(1.0, 5000.0)
        self.tolerans_kutusu.setDecimals(1)
        self.tolerans_kutusu.setSuffix(" µm")
        self.tolerans_kutusu.setValue(k.duzeltme.merkez_toleransi_um)
        form.addRow("Merkez toleransı", self.tolerans_kutusu)
        self.otomatik_kutusu = QCheckBox("onay beklemeden baştan sona yürü (çalışırken de değiştirilebilir)")
        form.addRow("Otomatik", self.otomatik_kutusu)
        self.sinir_etiketi = QLabel()
        self.sinir_etiketi.setWordWrap(True)
        form.addRow("Sınırlar", self.sinir_etiketi)
        duzen.addWidget(kutu)

        self.bobin_etiketi = QLabel()
        self.bobin_etiketi.setWordWrap(True)
        duzen.addWidget(self.bobin_etiketi)
        self.baslat_dugmesi = QPushButton("Merkezlemeyi başlat")
        self.baslat_dugmesi.clicked.connect(self.baslat)
        duzen.addWidget(self.baslat_dugmesi)
        if self.donanim_sorunu:
            sorun = QLabel(self.donanim_sorunu)
            sorun.setWordWrap(True)
            sorun.setStyleSheet("color: #c0392b;")
            duzen.addWidget(sorun)
        duzen.addStretch()
        return sayfa

    def _otomatik_ilerle(self) -> None:
        if self.pencere is not None and self.otomatik_calisma.isChecked():
            self.pencere.otomatik_adim()

    def _durumu_yenile(self) -> None:
        g = self.kfg.guvenlik
        n = self.nominal_kutusu.value()
        en_fazla = n * (1 + g.nominale_gore_max_asimetri)
        metin = (f"bobin başına en fazla %{g.nominale_gore_max_asimetri * 100:g} asimetri "
                 f"(en fazla {en_fazla:.2f} A), adım başına %{g.adim_basi_max_bagil_degisim * 100:g}, "
                 f"bobin başı sınır {g.bobin_basi_max_akim_A:g} A")
        if en_fazla > g.bobin_basi_max_akim_A:
            metin += " — UYARI: asimetri sınırı bobin başı sınırı aşabilir; o adım reddedilir"
        self.sinir_etiketi.setText(metin)
        hazir, aciklama = self.bobin_hazir()
        self.bobin_etiketi.setText(("Dönen bobin: " if hazir else "Dönen bobin HAZIR DEĞİL: ") + aciklama)
        self.baslat_dugmesi.setEnabled(hazir and not self.donanim_sorunu and self.pencere is None)
        if self.pencere is not None:
            a = self.pencere.akis
            ek = ""
            if self.otomatik_calisma.isChecked() and a.bekleme.name == "KULLANICI_EYLEMI":
                ek = " — KULLANICI EYLEMİ BEKLENİYOR (otomatik geçilmez)"
            self.calisma_etiketi.setText(
                f"Nominal {a.kfg.miknatis.nominal_akim_A:g} A, tolerans {a.kfg.duzeltme.merkez_toleransi_um:g} µm"
                f" — faz: {a.faz.value}{ek}"
            )

    # ------------------------------------------------------------------
    def baslat(self) -> None:
        if self.pencere is not None:
            return
        kfg = ayarlari_uygula(self.kfg, self.nominal_kutusu.value(), self.tolerans_kutusu.value())
        konvansiyon = HarmonikKonvansiyonu(kfg.harmonikler)
        try:
            grup = _kaynak_grubu_kur(kfg, canli=self.canli, gunluk=KomutGunlugu(), bekle=qt_bekle)
        except Exception as hata:  # noqa: BLE001 - kullanıcıya gösterilir
            QMessageBox.critical(self, "Güç kaynakları", f"Güç kaynaklarına bağlanılamadı:\n{hata}")
            return
        calistirma = Calistirma(kfg)
        (calistirma.dizin / "arayuz_ayarlari.txt").write_text(
            f"{datetime.now():%Y-%m-%d %H:%M:%S} birleşik arayüzden başlatıldı\n"
            f"kip: {kfg.genel.kip}\n"
            f"nominal_akim_A: {kfg.miknatis.nominal_akim_A}\n"
            f"merkez_toleransi_um: {kfg.duzeltme.merkez_toleransi_um}\n"
            f"otomatik (başlangıçta): {self.otomatik_kutusu.isChecked()}\n"
            "(yapilandirma.yaml bu iki değer dışında aynen kullanıldı)\n",
            encoding="utf-8",
        )
        akis = IsAkisi(kfg, grup, self.olcum_kaynagi_uret(kfg, konvansiyon), calistirma,
                       konvansiyon, ModBazi(kfg.modlar, kfg.miknatis))
        self.otomatik_calisma.setChecked(self.otomatik_kutusu.isChecked())
        self.yigin.setCurrentWidget(self.calisma_sayfasi)
        # Pencere kurulurken akış başlar ve ilk ölçümü bekler (olay döngüsü işler)
        self.pencere = MerkezlemePencere(kfg, akis, otomatik_kaynak_etiketi="OTOMATİK ÖLÇÜM (dönen bobin sekmesi)")
        self.calisma_sayfasi.layout().addWidget(self.pencere)
        self.merkezleme_acilinca()
        self._durumu_yenile()

    def yeni_calistirma(self) -> None:
        if self.pencere is None:
            return
        a = self.pencere.akis
        soru = ("Akış sürüyor. Durdurup akımları rampa ile sıfıra indireyim mi?" if not a.bitti_mi()
                else "Akımlar rampa ile sıfıra indirilecek, çıkışlar kapanacak. Devam edilsin mi?")
        if QMessageBox.question(self, "Yeni çalıştırma", soru) != QMessageBox.StandardButton.Yes:
            return
        self.kapat()
        self.yigin.setCurrentIndex(0)
        self._durumu_yenile()

    def kapat(self) -> None:
        """Akış varsa durdurur, akımları sıfırlar, özeti yazar (pencerenin closeEvent'i)."""
        if self.pencere is None:
            return
        self.pencere.close()
        self.pencere.setParent(None)
        self.pencere.deleteLater()
        self.pencere = None


class BirlesikPencere(QMainWindow):
    def __init__(self, bobin_penceresi: QMainWindow, merkezleme: MerkezlemeSekmesi) -> None:
        super().__init__()
        self.setWindowTitle("Dönen bobin + elektriksel merkezleme")
        self.bobin = bobin_penceresi
        self.merkezleme = merkezleme
        self.bobin.setWindowFlags(Qt.WindowType.Widget)
        self.sekmeler = QTabWidget()
        self.sekmeler.addTab(self.bobin, "Dönen bobin")
        self.sekmeler.addTab(self.merkezleme, "Merkezleme")
        self.setCentralWidget(self.sekmeler)

    def closeEvent(self, olay) -> None:  # noqa: N802 - Qt adı
        try:
            self.merkezleme.kapat()   # akımlar sıfıra, çıkışlar kapalı, özet
        finally:
            self.bobin.close()        # motor durdurulur, bağlantı kesilir
        olay.accept()


def bobin_durumu(dongu) -> tuple[bool, str]:
    from mgf.olcum_dongusu import Durum

    if not dongu.otomatik_yaz:
        return False, "'Merkezleme'ye yaz' kapalı; açın."
    if dongu.durum in (Durum.KILIT_BEKLENIYOR, Durum.VERI_TOPLANIYOR):
        return True, f"dönüyor ({dongu.engine.motor_speed:.2f} Hz), kanal {dongu.kanal}"
    if dongu.durum is Durum.HAZIR:
        return False, "bağlı, motor duruyor; dönen bobin sekmesinde 'Başlat'a basın."
    return False, f"durum: {dongu.durum.value} (bağlanıp motor hızı oturunca hazır olur)"


def main(argv: list[str] | None = None) -> int:
    a = argparse.ArgumentParser(description="Dönen bobin + merkezleme tek pencere")
    a.add_argument("--canli", action="store_true", help="GERÇEK DONANIM (güç kaynakları sürülür)")
    a.add_argument("--yapilandirma", default=str(KOK / "yapilandirma.yaml"))
    a.add_argument("--parametreler", default=None, help="dönen bobin parametre YAML'ı")
    a.add_argument("--baglanma", action="store_true", help="açılışta Pico'ya bağlanma (deneme için)")
    g = a.parse_args(argv)

    os.chdir(KOK)  # göreli yollar (calistirmalar/, veri_kilidi/) depo köküne göre
    if str(HOST) not in sys.path:
        sys.path.insert(0, str(HOST))
    from mgf.connection import MgfConnection
    from mgf.data_engine import DataEngine
    from mgf.merkezleme_koprusu import parametreleri_yukle
    from mgf.merkezleme_penceresi import MerkezlemePenceresi

    kfg = yapilandirma_yukle(g.yapilandirma)
    p = parametreleri_yukle(g.parametreler)
    sorun = None
    if g.canli:
        from .eslestirme import adresleri_denetle

        if adresleri_denetle(g.yapilandirma) != 0:
            sorun = "Güç kaynağı adresleri bu bilgisayarda yok. Önce: ./merkezle eslestir"
    Path(kfg.dosya_girisi.kilit_dosyasi).unlink(missing_ok=True)  # eski oturumdan kalan veri

    uygulama = QApplication(sys.argv[:1])
    bobin = MerkezlemePenceresi(p, MgfConnection(p.ip, p.port), DataEngine())
    sekme = MerkezlemeSekmesi(kfg, g.canli, lambda: bobin_durumu(bobin.dongu), donanim_sorunu=sorun,
                              merkezleme_acilinca=lambda: bobin._temayi_uygula(bobin.tema))
    pencere = BirlesikPencere(bobin, sekme)
    pencere.resize(1250, 980)
    pencere.show()
    if not g.baglanma:
        QTimer.singleShot(0, bobin.baglan)  # yalnızca bağlan; motor kullanıcı "Başlat" deyince
    signal.signal(signal.SIGTERM, lambda *_: pencere.close())
    return int(uygulama.exec())


if __name__ == "__main__":
    raise SystemExit(main())
