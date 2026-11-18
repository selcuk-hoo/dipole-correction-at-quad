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
import csv
import dataclasses
import math
import os
import html
import json
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

import numpy as np

from PySide6.QtCore import QEvent, QObject, Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGraphicsColorizeEffect,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
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
from .kalibrasyon import KalibrasyonSonucu, kayitli_kalibrasyonu_yukle
from .kayit import Calistirma
from .modlar import ModBazi
from .olcum_kaynagi import DosyaGirisi
from .yapilandirma import Yapilandirma, yapilandirma_yukle

KOK = Path(__file__).resolve().parents[1]
HOST = KOK / "donen_bobin" / "host"
ARKA_PLAN_ORTALAMA_SAYISI = 5  # izlemede ortalaması alınan son arka plan ölçümü
OLCUM_YOK_ESIGI_S = 60.0  # izlemede bu kadar yeni ölçüm gelmezse uyarı (+ Telegram)
TELEGRAM_KOMUTU = Path.home() / "bin" / "telegram-mesaj"


def telegram_bildir(baslik: str, ayrinti: str = "") -> None:
    """Kullanıcının telefonuna kısa bir bildirim gönderir (arka planda, beklemeden).

    Komut yoksa, testlerde ya da MERKEZLE_TELEGRAM=0 iken sessizce geçer;
    gönderilemezse ölçüm etkilenmez."""
    if (os.environ.get("MERKEZLE_TELEGRAM") == "0" or "PYTEST_CURRENT_TEST" in os.environ
            or not TELEGRAM_KOMUTU.exists()):
        return
    metin = f"<b>{html.escape(baslik)}</b>"
    if ayrinti:
        metin += f"\n\n{html.escape(ayrinti)}"
    metin += f"\n\n<i>{datetime.now():%H:%M}</i>"
    try:
        subprocess.Popen([str(TELEGRAM_KOMUTU), "-h", metin], stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)
    except OSError:
        pass


@dataclass
class KayitliKalibrasyon:
    """Önceki bir çalıştırmanın kalibrasyonu (yeniden kullanmak için)."""

    dosya: Path
    kalibrasyon: KalibrasyonSonucu
    nominal_A: float | None
    son_akimlar_A: np.ndarray | None  # çalıştırma tamamlandıysa son ayar akımları
    etiket: str


def _calistirma_nominali(dizin: Path) -> float | None:
    ayarlar = dizin / "arayuz_ayarlari.txt"
    if ayarlar.exists():
        for satir in ayarlar.read_text(encoding="utf-8").splitlines():
            if satir.startswith("nominal_akim_A:"):
                try:
                    return float(satir.split(":", 1)[1])
                except ValueError:
                    return None
    try:
        import yaml

        return float(yaml.safe_load((dizin / "yapilandirma.yaml").read_text(encoding="utf-8"))
                     ["miknatis"]["nominal_akim_A"])
    except Exception:  # noqa: BLE001 - bilinmiyorsa None
        return None


def _kuru_calistirma_mi(dizin: Path) -> bool:
    """Komutlar güç kaynaklarına gitmediyse True. SCPI günlüğüne bakılır: 6 Kasım
    öncesi yapılandırma kopyası --canli'yi yansıtmıyordu (kip yanlışlıkla "kuru")."""
    gunluk = dizin / "scpi_gunlugu.txt"
    if gunluk.exists():
        with gunluk.open(encoding="utf-8", errors="replace") as f:
            ilk = [f.readline() for _ in range(5)]
        return any("(kuru)" in s for s in ilk)
    ayarlar = dizin / "arayuz_ayarlari.txt"
    return ayarlar.exists() and "kip: kuru" in ayarlar.read_text(encoding="utf-8")


def kayitli_kalibrasyonlari_bul(kok: Path, canli: bool, en_fazla: int = 15) -> list[KayitliKalibrasyon]:
    """`kok` altındaki çalıştırmaların kalibrasyonları, en yeniden eskiye.

    Kuadrupol açısı bilinmeyenler (yeniden kullanılamaz) ve canlı kipte, kuru
    kipte yapılmış çalıştırmalar alınmaz."""
    sonuc: list[KayitliKalibrasyon] = []
    if not kok.is_dir():
        return sonuc
    for dizin in sorted((d for d in kok.iterdir() if d.is_dir()), reverse=True):
        dosya = dizin / "kalibrasyon.json"
        if not dosya.exists():
            continue
        if canli and _kuru_calistirma_mi(dizin):
            continue
        try:
            kal = kayitli_kalibrasyonu_yukle(dosya)
        except Exception:  # noqa: BLE001 - bozuk dosya listelenmez
            continue
        if kal.kuadrupol_acisi_rad is None:
            continue
        son = None
        try:
            durum = json.loads((dizin / "durum.json").read_text(encoding="utf-8"))
            akimlar = np.asarray(durum.get("mevcut_akimlar_A", []), dtype=float)
            if durum.get("faz") == "tamamlandi" and akimlar.size == 4 and np.all(akimlar > 0):
                son = akimlar
        except Exception:  # noqa: BLE001
            pass
        nominal = _calistirma_nominali(dizin)
        etiket = (dizin.name + (f", {nominal:g} A" if nominal else "")
                  + (", ŞÜPHELİ" if kal.supheli else "") + ("" if son is None else ", son akımlar var"))
        sonuc.append(KayitliKalibrasyon(dosya, kal, nominal, son, etiket))
        if len(sonuc) >= en_fazla:
            break
    return sonuc


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
        self.kapanis_kancalari: list[Callable[[], None]] = []  # kapat() önce bunları çağırır

        self.otomatik_calisma = QCheckBox("Otomatik (onay beklemeden)")
        self.otomatik_calisma.setToolTip(
            "Ölçümleri ve düzeltme önerilerini kendiliğinden onaylar. Röle/modülatör gibi\n"
            "kullanıcı eylemleri ve duraklatma yine size bırakılır. Çalışırken de açılıp kapatılabilir.")
        # Eskiden ayar panelinde ayrı bir kutu vardı ve yalnızca başlangıçta eşitleniyordu
        self.otomatik_kutusu = self.otomatik_calisma
        self.yigin = QStackedWidget()
        self.yigin.addWidget(self._ayar_panelini_kur())
        self.calisma_sayfasi = QWidget()
        cs = QVBoxLayout(self.calisma_sayfasi)
        ust = QHBoxLayout()
        self.calisma_etiketi = QLabel()
        ust.addWidget(self.calisma_etiketi)
        ust.addStretch()
        self.yeniden_dugmesi = QPushButton("Mevcut akımlarla yeniden düzelt")
        self.yeniden_dugmesi.setToolTip(
            "Akımları SIFIRLAMADAN, bu çalıştırmanın kalibrasyonuyla düzeltmeyi yeniden başlatır.\n"
            "Mıknatıs sıcak düzeninde kalır (yalnızca arka plan için akımlar kısa süre sıfırlanır).\n"
            "Isınmayla kayan merkezi izleme sırasında düzeltmek için.")
        self.yeniden_dugmesi.clicked.connect(self.yeniden_duzelt)
        ust.addWidget(self.yeniden_dugmesi)
        self.yeni_dugmesi = QPushButton("Yeni çalıştırma (akımları sıfırla, ayarlara dön)")
        self.yeni_dugmesi.clicked.connect(self.yeni_calistirma)
        ust.addWidget(self.yeni_dugmesi)
        cs.addLayout(ust)
        self.yigin.addWidget(self.calisma_sayfasi)
        duzen = QVBoxLayout(self)
        duzen.setContentsMargins(0, 0, 0, 0)
        ust_satir = QHBoxLayout()
        ust_satir.setContentsMargins(8, 4, 8, 0)
        ust_satir.addStretch()
        ust_satir.addWidget(self.otomatik_calisma)
        duzen.addLayout(ust_satir)
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
        self.kalibrasyon_secici = QComboBox()
        self.kalibrasyon_secici.setToolTip(
            "Kayıtlı bir kalibrasyon seçilirse kalibrasyon yinelenmez (~7 dk ve 15 akım değişimi yerine\n"
            "2 ölçümlük yön doğrulama): matris, kuadrupolün bu oturumdaki açısına göre döndürülür,\n"
            "180° belirsizliği küçük bir H adımıyla çözülür. Uymazsa akış durur ve yeni kalibrasyon önerir.")
        self.kalibrasyon_secici.currentIndexChanged.connect(self._kalibrasyon_secildi)
        form.addRow("Kalibrasyon", self.kalibrasyon_secici)
        self.akimdan_basla = QCheckBox("o çalıştırmanın son akımlarından başla (nominal yerine)")
        form.addRow("", self.akimdan_basla)
        self.kalibrasyon_bilgi = QLabel()
        self.kalibrasyon_bilgi.setWordWrap(True)
        form.addRow("", self.kalibrasyon_bilgi)
        self.nominal_kutusu.valueChanged.connect(self._kalibrasyon_secildi)
        self.kayitlilar: list[KayitliKalibrasyon] = []
        self._kalibrasyonlari_yenile()
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

    def _kalibrasyonlari_yenile(self) -> None:
        self.kayitlilar = kayitli_kalibrasyonlari_bul(Path(self.kfg.genel.calistirma_kok_dizini), self.canli)
        self.kalibrasyon_secici.blockSignals(True)
        self.kalibrasyon_secici.clear()
        self.kalibrasyon_secici.addItem("Yeni kalibrasyon kur (~7 dk)", None)
        for i, k in enumerate(self.kayitlilar):
            self.kalibrasyon_secici.addItem("Kayıtlı: " + k.etiket, i)
        self.kalibrasyon_secici.blockSignals(False)
        self._kalibrasyon_secildi()

    def secili_kayitli(self) -> KayitliKalibrasyon | None:
        i = self.kalibrasyon_secici.currentData()
        return None if i is None else self.kayitlilar[i]

    def _kalibrasyon_secildi(self) -> None:
        k = self.secili_kayitli()
        nominal = self.nominal_kutusu.value()
        ayni_nominal = k is not None and k.nominal_A is not None and abs(k.nominal_A - nominal) < 1e-6
        kullanilir = k is not None and k.son_akimlar_A is not None and ayni_nominal
        self.akimdan_basla.setEnabled(kullanilir)
        self.akimdan_basla.setChecked(kullanilir)
        if k is None:
            self.kalibrasyon_bilgi.setText("")
            return
        metin = (f"Kuadrupol açısı (o oturumun bobin sıfırına göre) "
                 f"{math.degrees(k.kalibrasyon.kuadrupol_acisi_rad):+.1f}°. "
                 "Matris bu oturuma 2 ölçümlük yön doğrulamayla uyarlanır.")
        if k.nominal_A is not None and not ayni_nominal:
            metin += f" Kalibrasyon {k.nominal_A:g} A'de kurulmuş (bağıl birimde geçerli); son akımlar kullanılamaz."
        ipucu = ""
        if k.kalibrasyon.supheli:
            n = len(k.kalibrasyon.supheli_nedenleri)
            metin += f" Şüpheli işaretli ({n} neden; ayrıntı için üzerine gelin)."
            ipucu = "\n".join("• " + neden for neden in k.kalibrasyon.supheli_nedenleri)
        self.kalibrasyon_bilgi.setText(metin)
        self.kalibrasyon_bilgi.setToolTip(ipucu)

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
        self.yeniden_dugmesi.setEnabled(self.yeniden_duzeltilebilir())
        if self.pencere is not None:
            a = self.pencere.akis
            ek = ""
            if self.otomatik_calisma.isChecked() and a.bekleme.name == "KULLANICI_EYLEMI":
                ek = " — KULLANICI EYLEMİ BEKLENİYOR (otomatik geçilmez)"
            if a.faz.value == "tamamlandi" and a.yakinsadi is False:
                ek = " — TOLERANS DIŞINDA BİTTİ"
            self.calisma_etiketi.setText(
                f"Nominal {a.kfg.miknatis.nominal_akim_A:g} A, tolerans {a.kfg.duzeltme.merkez_toleransi_um:g} µm"
                f" — faz: {a.faz.value}{ek}"
            )

    # ------------------------------------------------------------------
    def baslat(self) -> None:
        if self.pencere is not None:
            return
        kfg = ayarlari_uygula(self.kfg, self.nominal_kutusu.value(), self.tolerans_kutusu.value())
        kayitli = self.secili_kayitli()
        baslangic = None
        if kayitli is not None and self.akimdan_basla.isEnabled() and self.akimdan_basla.isChecked():
            baslangic = np.asarray(kayitli.son_akimlar_A, dtype=float)
            g = kfg.guvenlik
            asimetri = np.abs(baslangic / kfg.miknatis.nominal_akim_A - 1.0)
            if np.any(asimetri > g.nominale_gore_max_asimetri) or np.any(baslangic > g.bobin_basi_max_akim_A):
                QMessageBox.warning(self, "Başlangıç akımları",
                                    "Kayıtlı son akımlar güvenlik sınırlarının dışında; nominalden başlayın.")
                return
        try:
            grup = _kaynak_grubu_kur(kfg, canli=self.canli, gunluk=KomutGunlugu(), bekle=qt_bekle)
        except Exception as hata:  # noqa: BLE001 - kullanıcıya gösterilir
            QMessageBox.critical(self, "Güç kaynakları", f"Güç kaynaklarına bağlanılamadı:\n{hata}")
            return
        if kayitli is None:
            self._akisi_kur(kfg, grup)
        else:
            self._akisi_kur(kfg, grup, kalibrasyon=kayitli.kalibrasyon, baslangic_akimlari_A=baslangic,
                            onceki=kayitli.dosya.parent, yon_dogrulama=True)

    def _akisi_kur(self, kfg: Yapilandirma, grup, kalibrasyon=None, baslangic_akimlari_A=None,
                   onceki: Path | None = None, yon_dogrulama: bool = False) -> None:
        konvansiyon = HarmonikKonvansiyonu(kfg.harmonikler)
        calistirma = Calistirma(kfg)
        ek = ""
        if onceki is not None:
            ek = ((f"kayıtlı kalibrasyon: {onceki} (yön doğrulamayla bu oturuma uyarlanır)\n"
                   if yon_dogrulama else f"önceki çalıştırmadan yeniden düzeltme: {onceki}\n")
                  + ("başlangıç akımları: nominal\n" if baslangic_akimlari_A is None else
                     f"başlangıç akımları (A): {', '.join(f'{a:.5f}' for a in baslangic_akimlari_A)}\n")
                  + "kalibrasyon yeniden yapılmadı\n")
        (calistirma.dizin / "arayuz_ayarlari.txt").write_text(
            f"{datetime.now():%Y-%m-%d %H:%M:%S} birleşik arayüzden başlatıldı\n"
            f"kip: {kfg.genel.kip}\n"
            f"nominal_akim_A: {kfg.miknatis.nominal_akim_A}\n"
            f"merkez_toleransi_um: {kfg.duzeltme.merkez_toleransi_um}\n"
            f"otomatik (başlangıçta): {self.otomatik_calisma.isChecked()}\n"
            + ek +
            "(yapilandirma.yaml bu iki değer dışında aynen kullanıldı)\n",
            encoding="utf-8",
        )
        akis = IsAkisi(kfg, grup, self.olcum_kaynagi_uret(kfg, konvansiyon), calistirma,
                       konvansiyon, ModBazi(kfg.modlar, kfg.miknatis))
        if kalibrasyon is not None:
            akis.kalibrasyonu_yukle(kalibrasyon)
            calistirma.kalibrasyon_yaz(kalibrasyon)
            akis.baslangic_akimlari_A = baslangic_akimlari_A
            akis.yon_dogrulama_gerekli = yon_dogrulama
        self.yigin.setCurrentWidget(self.calisma_sayfasi)
        # Pencere kurulurken akış başlar ve ilk ölçümü bekler (olay döngüsü işler)
        self.pencere = MerkezlemePencere(kfg, akis, otomatik_kaynak_etiketi="OTOMATİK ÖLÇÜM (dönen bobin sekmesi)",
                                         tema_yonet=False)
        self.calisma_sayfasi.layout().addWidget(self.pencere)
        self.merkezleme_acilinca()
        self._durumu_yenile()

    def yeniden_duzeltilebilir(self) -> bool:
        """Akış tamamlanmış, kalibrasyonu var ve akımlar açıksa."""
        if self.pencere is None:
            return False
        a = self.pencere.akis
        return (a.faz.value == "tamamlandi" and a.kalibrasyon is not None
                and bool(np.any(np.asarray(a.kaynaklar.ayar_akimlari_A) > 0)))

    def yeniden_duzelt(self, sor: bool = True) -> None:
        """Akımları sıfırlamadan, aynı kalibrasyonla yeni bir düzeltme çalıştırması.

        17 Kasım'da yeniden merkezlemek için akımlar sıfırlanıp kalibrasyon baştan
        yapılmıştı; mıknatıs soğudu ve ısıl düzen bozuldu. Burada eski pencere
        kapatılmadan (closeEvent akımları sıfırlardı) sökülür, kaynak grubu ve
        kalibrasyon yeni akışa devredilir."""
        if not self.yeniden_duzeltilebilir():
            return
        eski = self.pencere.akis
        akimlar = np.asarray(eski.kaynaklar.ayar_akimlari_A, dtype=float).copy()
        if sor and QMessageBox.question(
            self, "Mevcut akımlarla yeniden düzelt",
            "Akımlar şu değerlerde açık kalacak:\n  "
            + ", ".join(f"I{i + 1} = {a:.4f} A" for i, a in enumerate(akimlar))
            + "\n\nBu çalıştırmanın kalibrasyonuyla düzeltme yeniden başlatılacak (kalibrasyon "
            "yinelenmez). Yalnızca arka plan ölçümü için akımlar kısa süre sıfıra iner.\n"
            "Kararlılık izlemesi sürüyorsa durdurulur. Devam edilsin mi?",
        ) != QMessageBox.StandardButton.Yes:
            return
        for kanca in self.kapanis_kancalari:  # izlemeyi durdur
            kanca()
        eski.notlar.append("Mevcut akımlarla yeniden düzeltmeye geçildi; akımlar açık bırakıldı.")
        try:
            eski.ozeti_yaz()
        except Exception:  # noqa: BLE001 - özet yazılamasa da devam
            pass
        pencere, self.pencere = self.pencere, None
        pencere.setParent(None)   # close() DEĞİL: closeEvent akımları sıfırlardı
        pencere.deleteLater()
        self._akisi_kur(eski.kfg, eski.kaynaklar, kalibrasyon=eski.kalibrasyon,
                        baslangic_akimlari_A=akimlar, onceki=eski.calistirma.dizin)

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
        self._kalibrasyonlari_yenile()  # biten çalıştırmanın kalibrasyonu da listelensin
        self._durumu_yenile()

    def arka_plan(self) -> dict[int, complex] | None:
        """Quad akımları sıfırken ölçülen alan (n -> C_n, Tesla); yoksa None.

        Son `ARKA_PLAN_ORTALAMA_SAYISI` arka plan ölçümünün ortalamasıdır:
        tek ölçümün saçılımı ~0.8 µT, bu da merkezde ~8 µm demek (17 Kasım).
        Merkezlemede arka plan her noktada alındığı için bunlar son ~2 dakikaya
        aittir. Durumdan devam edilmişse yalnızca son arka plan bilinir.
        Yalnızca birim T iken (dönen bobin Tesla yazar) ve merkezleme akışı
        en az bir arka plan ölçümü aldıysa."""
        if self.pencere is None or self.kfg.harmonikler.birim != "T":
            return None
        akis = self.pencere.akis
        olcumler = akis.son_arka_planlar[:ARKA_PLAN_ORTALAMA_SAYISI]
        if not olcumler:
            olcumler = [akis.son_arka_plan] if akis.son_arka_plan is not None else []
        if not olcumler:
            return None
        nler = set(olcumler[0].bilesenler).intersection(*(o.bilesenler for o in olcumler[1:]))
        return {n: sum(complex(o.bilesenler[n]) for o in olcumler) / len(olcumler) for n in nler}

    def kapat(self) -> None:
        """Akış varsa durdurur, akımları sıfırlar, özeti yazar (pencerenin closeEvent'i)."""
        for kanca in self.kapanis_kancalari:
            kanca()
        if self.pencere is None:
            return
        self.pencere.close()
        self.pencere.setParent(None)
        self.pencere.deleteLater()
        self.pencere = None


class KararlilikSekmesi(QWidget):
    """Merkezleme bittikten sonra quad akımları AÇIK tutulur; alanın saatler içindeki
    kararlılığı izlenir. Dönen bobin sürekli ölçüm kipine alınır. Her `aralik`
    saniyede, o aralıktaki BÜTÜN sağlıklı ölçümlerin ortalaması (arka plan çıkarılmış
    merkez, dipol, kuadrupol), ölçüm sayısı ve saçılımı ile dört güç kaynağının
    gerçek akımı `izleme_<saat>.csv`'ye yazılır ve çizilir. Akımları ayrı bir iş
    parçacığı saniyede bir okur; arayüz okumayı beklemez (her MEAS:CURR? ~0.7 s).

    "Ortam alanını izle (akımsız)": quad akımları SIFIRKEN dönen bobinin gördüğü
    dipol (B1, A1) aynı biçimde `ortam_<saat>.csv`'ye yazılır. Akımlı izlemedeki
    "net" merkez, merkezlemede bir kez ölçülen arka planı sabit sayar; ortam alanı
    1 µT oynarsa merkez ~10 µm oynamış görünür. Bu kayıt o payı ayırmak içindir."""

    def __init__(self, bobin: QMainWindow, merkezleme: MerkezlemeSekmesi) -> None:
        super().__init__()
        import pyqtgraph as pg

        self.bobin, self.merkezleme = bobin, merkezleme
        self.calisiyor = False
        self.akimsiz = False  # True: ortam alanı izleniyor (quad akımları sıfır)
        self._onceki_yaz = True
        self._son_sonuc = None
        self._son_kayit_t = 0.0
        self._t0 = 0.0
        self._biriken: list = []
        self._akim_kilidi = threading.Lock()
        self._son_akim: list[float] = [math.nan] * 4
        self._akim_hatasi: str | None = None  # okuma iş parçacığının son hatası
        self._akim_hata_sayisi = 0  # art arda başarısız okuma
        self._akim_duzeldi = 0  # düzelmeden önceki başarısız okuma sayısı (bildirilmedi)
        self._bildirilen_hata_sayisi = 0
        self._son_olcum_t = 0.0
        self._olcum_yok_bildirildi = False
        self._akim_dur = threading.Event()
        self._akim_isi: threading.Thread | None = None
        self.t: list[float] = []
        self.x: list[float] = []
        self.y: list[float] = []
        self.dI: list[list[float]] = [[], [], [], []]
        self._I0: list[float] | None = None
        self._csv: Path | None = None

        duzen = QVBoxLayout(self)
        ust = QHBoxLayout()
        self.dugme = QPushButton("İzlemeyi başlat")
        self.dugme.clicked.connect(self.degistir)
        ust.addWidget(self.dugme)
        self.dugme_ortam = QPushButton("Ortam alanını izle (akımsız)")
        self.dugme_ortam.setToolTip(
            "Quad akımları sıfırken dönen bobinin gördüğü dipolü (B1, A1) zamanla izler:\n"
            "merkezleme başlatılmadan önce ya da 'Yeni çalıştırma'dan sonra kullanılır.")
        self.dugme_ortam.clicked.connect(self.ortam_degistir)
        ust.addWidget(self.dugme_ortam)
        ust.addWidget(QLabel("Kayıt aralığı (bu sürede gelen ölçümlerin ortalaması)"))
        self.aralik = QSpinBox()
        self.aralik.setRange(1, 3600)
        self.aralik.setValue(30)  # 10 s ölçümle aralıkta ~3 ölçüm: saçılım hesaplanabilsin
        self.aralik.setSuffix(" s")
        ust.addWidget(self.aralik)
        ust.addStretch()
        duzen.addLayout(ust)
        self.bilgi = QLabel(
            "İzlemeyi başlat: merkezleme TAMAMLANDI olduktan sonra; akımlar açık kalır, pencereyi kapatana "
            "ya da 'Yeni çalıştırma'ya basana kadar sürer. Arka plan: quad en son sıfırken ölçülen alan. "
            "Ortam alanını izle: quad akımları sıfırken (merkezlemeden önce ya da 'Yeni çalıştırma'dan sonra).")
        self.bilgi.setWordWrap(True)
        duzen.addWidget(self.bilgi)
        self.ozet = QLabel("—")
        self.ozet.setWordWrap(True)
        duzen.addWidget(self.ozet)
        self.grafik_merkez = pg.PlotWidget(title="Merkez (arka plan çıkarılmış, aralık ortalaması)")
        self.grafik_merkez.setLabel("bottom", "süre", units="dk")
        self.grafik_merkez.setLabel("left", "µm")
        self.grafik_merkez.addLegend()
        self.egri_x = self.grafik_merkez.plot(name="x_c")
        self.egri_y = self.grafik_merkez.plot(name="y_c")
        duzen.addWidget(self.grafik_merkez)
        self.grafik_akim = pg.PlotWidget(title="Güç kaynağı akımı: ilk değerden sapma")
        self.grafik_akim.setLabel("bottom", "süre", units="dk")
        self.grafik_akim.setLabel("left", "mA")
        self.grafik_akim.addLegend()
        self.egri_akim = [self.grafik_akim.plot(name=f"I{i + 1}") for i in range(4)]
        self._tema: str | None = None
        self._grafik_temasi()
        duzen.addWidget(self.grafik_akim)

        self.zamanlayici = QTimer(self)
        self.zamanlayici.timeout.connect(self._ornekle)
        self.zamanlayici.start(500)
        merkezleme.kapanis_kancalari.append(self.durdur)

    # ------------------------------------------------------------------
    def degistir(self) -> None:
        if self.calisiyor:
            self.durdur()
        else:
            self.baslat()

    def ortam_degistir(self) -> None:
        if self.calisiyor:
            self.durdur()
        else:
            self.baslat(akimsiz=True)

    def baslat(self, akimsiz: bool = False) -> None:
        akis = self.merkezleme.pencere.akis if self.merkezleme.pencere else None
        if akimsiz:
            if akis is not None and (not akis.bitti_mi()
                                     or np.any(np.abs(akis.kaynaklar.ayar_akimlari_A) > 1e-6)):
                QMessageBox.information(self, "Ortam alanı izleme",
                                        "Merkezleme sürüyor ya da quad akımları açık. Önce 'Yeni çalıştırma' "
                                        "ile akımları sıfırlayın.")
                return
        elif akis is None or akis.faz.value != "tamamlandi":
            QMessageBox.information(self, "Kararlılık izleme",
                                    "Önce merkezleme TAMAMLANMALI (akımlar merkezlenmiş değerlerde açık kalır). "
                                    "Akımlar sıfırken 'Ortam alanını izle (akımsız)'ı kullanın.")
            return
        if not akimsiz and akis.yakinsadi is False and QMessageBox.question(
            self, "Kararlılık izleme",
            "Merkezleme TOLERANS DIŞINDA bitti:\n" + (akis.durdurma_nedeni or "")
            + "\n\nİzleme bu merkezden başlayacak. 'Mevcut akımlarla yeniden düzelt' ile önce "
            "düzeltmeyi yineleyebilirsiniz. Yine de izleme başlatılsın mı?",
        ) != QMessageBox.StandardButton.Yes:
            return
        self.akimsiz = akimsiz
        d = self.bobin.dongu
        self._onceki_yaz = d.otomatik_yaz
        d.otomatik_yaz_ayarla(False)       # sürekli ölçüm: her pencere_s'de bir
        self._t0 = time.monotonic()
        self._son_kayit_t = self._t0
        self._son_sonuc = d.son_sonuc      # mevcut sonuç yeni sayılmasın
        self._son_olcum_t = self._t0
        self._olcum_yok_bildirildi = False
        self._biriken = []
        self.t, self.x, self.y = [], [], []
        self.dI = [[], [], [], []]
        self._I0 = None
        self._son_akim = [math.nan] * 4
        self._akim_hatasi, self._akim_hata_sayisi, self._akim_duzeldi = None, 0, 0
        self._bildirilen_hata_sayisi = 0
        ad = "ortam" if akimsiz else "izleme"
        self._csv = d.oturum.klasor() / f"{ad}_{datetime.now():%H%M%S}.csv"
        with open(self._csv, "w", newline="", encoding="utf-8") as f:
            if akimsiz:
                csv.writer(f).writerow(["zaman", "gecen_dk", "n_olcum", "B1_uT", "A1_uT", "sB1_uT", "sA1_uT",
                                        "C2_uT", "hiz_hz", "artik_orani"])
            else:
                csv.writer(f).writerow(["zaman", "gecen_dk", "n_olcum", "x_c_um", "y_c_um", "sx_um", "sy_um",
                                        "C1_net_uT", "C2_mT", "hiz_hz", "artik_orani", "I1_A", "I2_A", "I3_A",
                                        "I4_A", "B1_net_uT", "A1_net_uT"])
        self.calisiyor = True
        if akimsiz:
            self.grafik_merkez.setTitle("Ortam alanı: B1 (kırmızı), A1 (mavi); quad akımları sıfır")
            self.grafik_merkez.setLabel("left", "µT")
            self.grafik_akim.setVisible(False)
        else:
            self.grafik_merkez.setTitle("Merkez (arka plan çıkarılmış, aralık ortalaması)")
            self.grafik_merkez.setLabel("left", "µm")
            self.grafik_akim.setVisible(True)
            self._akim_dur.clear()
            self._akim_isi = threading.Thread(target=self._akimlari_oku, args=(akis.kaynaklar,), daemon=True)
            self._akim_isi.start()
        (self.dugme_ortam if akimsiz else self.dugme).setText(
            "Ortam izlemeyi durdur" if akimsiz else "İzlemeyi durdur")
        (self.dugme if akimsiz else self.dugme_ortam).setEnabled(False)
        self.ozet.setText(f"İzleniyor... kayıt: {self._csv.name}")

    def durdur(self) -> None:
        if not self.calisiyor:
            return
        self.calisiyor = False
        self._akim_dur.set()
        if self._akim_isi is not None:
            self._akim_isi.join(timeout=5)  # süren okuma bitsin; ardından akımlar sıfırlanabilir
            self._akim_isi = None
        self.bobin.dongu.otomatik_yaz_ayarla(self._onceki_yaz)
        self.dugme.setText("İzlemeyi başlat")
        self.dugme_ortam.setText("Ortam alanını izle (akımsız)")
        self.dugme.setEnabled(True)
        self.dugme_ortam.setEnabled(True)

    def _akimlari_oku(self, kaynaklar) -> None:
        while not self._akim_dur.is_set():
            hata = None
            try:
                akim = [float(a) for a in kaynaklar.akimlari_oku()]
            except Exception as h:  # noqa: BLE001 - okunamazsa NaN yazılır, izleme sürer
                akim, hata = [math.nan] * 4, h
            with self._akim_kilidi:
                self._son_akim = akim
                if hata is not None:
                    self._akim_hatasi = repr(hata)
                    self._akim_hata_sayisi += 1
                elif self._akim_hatasi is not None:  # düzeldi: _ornekle bildirir
                    self._akim_duzeldi += self._akim_hata_sayisi
                    self._akim_hatasi, self._akim_hata_sayisi = None, 0
            self._akim_dur.wait(1.0)

    def _akim_hatasini_bildir(self) -> None:
        """Okuma hatasını günlüğe yazar (ana iş parçacığından): ilk hata, her 60
        hatada bir özet ve düzelince bir satır. 17 Kasım'da okuma iki izlemede de
        13-26 dk sonra kesilmiş, hata sessizce yutulduğu için nedeni bilinmiyordu."""
        with self._akim_kilidi:
            hata, sayi, duzeldi = self._akim_hatasi, self._akim_hata_sayisi, self._akim_duzeldi
            self._akim_duzeldi = 0
        d = self.bobin.dongu
        if duzeldi:
            d.gunluk(f"Güç kaynağı akımları yeniden okunuyor ({duzeldi} okuma başarısızdı).")
            self._bildirilen_hata_sayisi = 0
        if hata is not None and (self._bildirilen_hata_sayisi == 0
                                   or sayi - self._bildirilen_hata_sayisi >= 60):
            d.gunluk(f"UYARI: güç kaynağı akımları okunamıyor ({sayi}. başarısız okuma): {hata}")
            self._bildirilen_hata_sayisi = sayi

    # ------------------------------------------------------------------
    # Dönen bobin sekmesinin teması (yoksa açık tema) ve renk körlüğüne dayanıklı
    # sıralı renkler (mavi, turuncu, yeşil-mavi, sarı; açık/koyu zemine ayrı tonlar)
    RENKLER = {"acik": ("#2a78d6", "#eb6834", "#1baf7a", "#eda100"),
               "koyu": ("#3987e5", "#d95926", "#199e70", "#c98500")}
    ZEMIN = {"acik": ("#ffffff", "#202124", "#5f6368"), "koyu": ("#2b2c2f", "#e8eaed", "#9aa0a6")}

    def _grafik_temasi(self) -> None:
        import pyqtgraph as pg

        tema = getattr(self.bobin, "tema", "acik")
        tema = tema if tema in self.RENKLER else "acik"
        if tema == self._tema:
            return
        self._tema = tema
        zemin, yazi, soluk = self.ZEMIN[tema]
        renk = self.RENKLER[tema]
        for grafik in (self.grafik_merkez, self.grafik_akim):
            grafik.setBackground(zemin)
            grafik.showGrid(x=False, y=True, alpha=0.25)
            for kenar in ("left", "bottom"):
                eksen = grafik.getAxis(kenar)
                eksen.setPen(pg.mkPen(soluk))
                eksen.setTextPen(pg.mkPen(yazi))
            grafik.getPlotItem().titleLabel.setAttr("color", yazi)
        self.egri_x.setPen(pg.mkPen(renk[0], width=2))
        self.egri_y.setPen(pg.mkPen(renk[1], width=2))
        for egri, c in zip(self.egri_akim, renk):
            egri.setPen(pg.mkPen(c, width=2))

    def _ornekle(self) -> None:
        self._grafik_temasi()  # dönen bobin sekmesinde tema değiştiyse
        if not self.calisiyor:
            return
        d = self.bobin.dongu
        s = d.son_sonuc
        simdi = time.monotonic()
        if s is not None and s is not self._son_sonuc:
            self._son_sonuc = s
            self._son_olcum_t = simdi
            if not d.saglik:
                self._biriken.append(s)
        self._bekci(simdi)
        if simdi - self._son_kayit_t < self.aralik.value() - 0.01 or not self._biriken:
            return
        self._son_kayit_t = simdi
        olcumler, self._biriken = self._biriken, []
        dk = (simdi - self._t0) / 60.0
        n = len(olcumler)
        hiz = sum(o.hiz_hz for o in olcumler) / n
        artik = sorted(o.artik_orani for o in olcumler)[n // 2]
        if self.akimsiz:
            b = [o.harmonikler[0].real * 1e6 for o in olcumler]
            a = [o.harmonikler[0].imag * 1e6 for o in olcumler]
            c2 = abs(sum(o.harmonikler[1] for o in olcumler) / n) * 1e6
            sb = float(np.std(b, ddof=1)) if n > 1 else math.nan
            sa = float(np.std(a, ddof=1)) if n > 1 else math.nan
            self.t.append(dk); self.x.append(float(np.mean(b))); self.y.append(float(np.mean(a)))
            with open(self._csv, "a", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow([datetime.now().isoformat(timespec="seconds"), f"{dk:.3f}", n,
                                        f"{self.x[-1]:.3f}", f"{self.y[-1]:.3f}", f"{sb:.3f}", f"{sa:.3f}",
                                        f"{c2:.3f}", f"{hiz:.3f}", f"{artik:.2e}"])
            self._ciz()
            return
        arka = self.merkezleme.arka_plan() or {}
        def net(h):
            c = list(h)
            for n, a in arka.items():
                if 1 <= n <= len(c):
                    c[n - 1] = c[n - 1] - a
            return c
        cler = [net(o.harmonikler) for o in olcumler]
        r = self.bobin.p.r_ref_m
        zler = [(-r * c[0] / c[1]) if abs(c[1]) > 0 else complex(math.nan, math.nan) for c in cler]
        c1 = sum(c[0] for c in cler) / len(cler)
        c2 = sum(c[1] for c in cler) / len(cler)
        z = -r * c1 / c2 if abs(c2) > 0 else complex(math.nan, math.nan)
        sx = (sum((v.real - z.real) ** 2 for v in zler) / (n - 1)) ** 0.5 if n > 1 else math.nan
        sy = (sum((v.imag - z.imag) ** 2 for v in zler) / (n - 1)) ** 0.5 if n > 1 else math.nan
        self._akim_hatasini_bildir()
        with self._akim_kilidi:
            akim = list(self._son_akim)
        if self._I0 is None and all(math.isfinite(a) for a in akim):
            self._I0 = list(akim)
        self.t.append(dk); self.x.append(z.real * 1e6); self.y.append(z.imag * 1e6)
        for i in range(4):
            self.dI[i].append((akim[i] - self._I0[i]) * 1e3 if self._I0 else math.nan)
        with open(self._csv, "a", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow([datetime.now().isoformat(timespec="seconds"), f"{dk:.3f}", n,
                                    f"{z.real * 1e6:.2f}", f"{z.imag * 1e6:.2f}", f"{sx * 1e6:.2f}", f"{sy * 1e6:.2f}",
                                    f"{abs(c1) * 1e6:.2f}", f"{abs(c2) * 1e3:.4f}", f"{hiz:.3f}", f"{artik:.2e}"]
                                   + [f"{a:.5f}" for a in akim] + [f"{c1.real * 1e6:.3f}", f"{c1.imag * 1e6:.3f}"])
        self._ciz()

    def _bekci(self, simdi: float) -> None:
        """Yeni ölçüm gelmiyorsa bir kez uyarır (günlük, kırmızı özet, Telegram).

        17 Kasım 16:51'de bir yazılım hatası motoru durdurdu; akımlar ~70 dk açık
        kaldı, izleme sessizce yazmayı bıraktı ve kimse fark etmedi."""
        d = self.bobin.dongu
        gecen = simdi - self._son_olcum_t
        if gecen > OLCUM_YOK_ESIGI_S and not self._olcum_yok_bildirildi:
            self._olcum_yok_bildirildi = True
            neden = getattr(d, "hata_metni", "") or (
                "motor dönmüyor" if getattr(d, "donuyor", True) is False else "neden bilinmiyor")
            akim = "akımlar sıfır" if self.akimsiz else "quad akımları AÇIK"
            metin = f"{gecen / 60:.0f} dakikadır yeni ölçüm yok ({akim}). Neden: {neden}"
            if hasattr(d, "gunluk"):
                d.gunluk("UYARI: izleme: " + metin)
            self.ozet.setStyleSheet("color: #c0392b; font-weight: bold;")
            self.ozet.setText("ÖLÇÜM GELMİYOR — " + metin)
            telegram_bildir("🔴 Ölçüm durdu", metin)
        elif gecen <= OLCUM_YOK_ESIGI_S and self._olcum_yok_bildirildi:
            self._olcum_yok_bildirildi = False
            if hasattr(d, "gunluk"):
                d.gunluk("İzleme: ölçümler yeniden geliyor.")
            self.ozet.setStyleSheet("")
            telegram_bildir("🟢 Ölçüm yeniden başladı")

    def _ciz(self) -> None:
        self.egri_x.setData(self.t, self.x)
        self.egri_y.setData(self.t, self.y)
        for e, v in zip(self.egri_akim, self.dI):
            e.setData(self.t, v)
        n = len(self.t)
        ad, birim, ond = (("B1", "A1"), "µT", 2) if self.akimsiz else (("x", "y"), "µm", 1)
        metin = (f"{n} kayıt, {self.t[-1]:.1f} dk. Son: {ad[0]} = {self.x[-1]:+.{ond}f} {birim}, "
                 f"{ad[1]} = {self.y[-1]:+.{ond}f} {birim}.")
        if n >= 5:
            ax, ay = np.polyfit(self.t, self.x, 1)[0] * 60, np.polyfit(self.t, self.y, 1)[0] * 60
            metin += (f" Ortalama ± σ: {ad[0]} {np.mean(self.x):+.{ond}f} ± {np.std(self.x, ddof=1):.{ond}f}, "
                      f"{ad[1]} {np.mean(self.y):+.{ond}f} ± {np.std(self.y, ddof=1):.{ond}f} {birim}. "
                      f"Sürüklenme: {ad[0]} {ax:+.{ond}f}, {ad[1]} {ay:+.{ond}f} {birim}/saat.")
        if not self._olcum_yok_bildirildi:
            self.ozet.setText(metin)


class DugmeGeriBildirimi(QObject):
    """Basılan düğmeyi kısa süre yeşile boyar ve durum çubuğuna yazar.

    Temada fare üstündeyken düğme zaten ters renkte; basınca görünür bir değişiklik
    olmuyordu ve "ADC'yi yeniden ayarla" gibi düğmelerin sonucu yalnızca Günlük
    sekmesine düşüyordu (11 Kasım). Uygulama geneline olay süzgeci olarak kurulur,
    sonradan oluşan düğmeleri de kapsar. Basıştan sonraki GUNLUK_S saniye içinde
    dönen bobin günlüğüne düşen satır, düğmenin sonucu olarak durum çubuğuna eklenir."""

    RENK = "#2ecc71"
    SURE_MS = 600
    GUNLUK_S = 2.0
    MESAJ_MS = 15000

    def __init__(self, pencere: QMainWindow) -> None:
        super().__init__(pencere)
        self.pencere = pencere
        self._son: tuple[str, float, str] | None = None  # (düğme metni, monotonic, saat)
        self._sonuc_yazildi = False

    def eventFilter(self, nesne, olay) -> bool:  # noqa: N802 - Qt adı
        # Süzgeç düğmeden ÖNCE çalışır: basış burada kaydedilir ki clicked içinde
        # (eşzamanlı) yazılan günlük satırı bu basışın sonucu sayılabilsin.
        if (olay.type() == QEvent.Type.MouseButtonRelease and isinstance(nesne, QPushButton)
                and nesne.isEnabled() and nesne.isDown()
                and nesne.rect().contains(olay.position().toPoint())
                and nesne.window() is self.pencere):
            self._son = (nesne.text().replace("&", ""), time.monotonic(), f"{datetime.now():%H:%M:%S}")
            self._sonuc_yazildi = False
            QTimer.singleShot(0, lambda d=nesne: self.bildir(d))
        return False

    def bildir(self, dugme: QPushButton) -> None:
        try:
            if dugme.graphicsEffect() is None:
                etki = QGraphicsColorizeEffect(dugme)
                etki.setColor(QColor(self.RENK))
                etki.setStrength(0.9)
                dugme.setGraphicsEffect(etki)
                QTimer.singleShot(self.SURE_MS, lambda: self._etkiyi_kaldir(dugme, etki))
        except RuntimeError:  # düğme bu arada silindi
            return
        if self._son is not None and not self._sonuc_yazildi:
            metin, _, saat = self._son
            self.pencere.statusBar().showMessage(f"{saat}  ✓ '{metin}' basıldı", self.MESAJ_MS)

    @staticmethod
    def _etkiyi_kaldir(dugme: QPushButton, etki) -> None:
        try:
            if dugme.graphicsEffect() is etki:
                dugme.setGraphicsEffect(None)
        except RuntimeError:
            pass

    def gunluk_satiri(self, satir: str) -> None:
        if self._son is None or time.monotonic() - self._son[1] > self.GUNLUK_S:
            return
        metin, _, saat = self._son
        self._sonuc_yazildi = True
        satir = satir.split("  ", 1)[-1]  # başındaki "HH:MM:SS  "
        self.pencere.statusBar().showMessage(f"{saat}  ✓ '{metin}': {satir}", self.MESAJ_MS)


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
        self.kararlilik = None
        if hasattr(self.bobin, "dongu"):
            self.kararlilik = KararlilikSekmesi(self.bobin, self.merkezleme)
            self.sekmeler.addTab(self.kararlilik, "Kararlılık")
            if hasattr(self.bobin, "arka_plan_kaynagi"):
                self.bobin.arka_plan_kaynagi = self.merkezleme.arka_plan
        self.setCentralWidget(self.sekmeler)
        self.geri_bildirim = DugmeGeriBildirimi(self)
        QApplication.instance().installEventFilter(self.geri_bildirim)
        if isinstance(getattr(self.bobin, "gunluk", None), QPlainTextEdit):
            belge = self.bobin.gunluk
            belge.textChanged.connect(
                lambda: self.geri_bildirim.gunluk_satiri(belge.document().lastBlock().text()))
        self.statusBar().showMessage("Basılan düğme yeşile döner; sonucu burada görünür.")
        self.onaysiz_kapat = False  # SIGTERM: soru sorulmadan kapanır

    def _suren_isler(self) -> list[str]:
        isler = []
        p = self.merkezleme.pencere
        if p is not None and np.any(np.asarray(p.akis.kaynaklar.ayar_akimlari_A) > 0):
            isler.append("quad akımları açık (rampa ile sıfıra inecek)")
        if self.kararlilik is not None and self.kararlilik.calisiyor:
            isler.append("kararlılık izlemesi sürüyor (bitecek)")
        if getattr(getattr(self.bobin, "dongu", None), "donuyor", False):
            isler.append("motor dönüyor (durdurulacak)")
        return isler

    def closeEvent(self, olay) -> None:  # noqa: N802 - Qt adı
        # Uzun ölçümde yanlışlıkla kapatmak her şeyi bitirirdi; DURDUR soruyordu, bu sormuyordu.
        isler = [] if self.onaysiz_kapat else self._suren_isler()
        if isler and QMessageBox.question(
            self, "Pencereyi kapat", "Kapatılırsa:\n  • " + "\n  • ".join(isler) + "\n\nKapatılsın mı?",
        ) != QMessageBox.StandardButton.Yes:
            olay.ignore()
            return
        QApplication.instance().removeEventFilter(self.geri_bildirim)
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
    def sigterm(*_) -> None:
        pencere.onaysiz_kapat = True
        pencere.close()

    signal.signal(signal.SIGTERM, sigterm)
    return int(uygulama.exec())


if __name__ == "__main__":
    raise SystemExit(main())
