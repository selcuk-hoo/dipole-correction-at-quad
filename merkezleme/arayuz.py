"""PyQt5 masaüstü arayüzü.

Ekranda her zaman bulunanlar:
  * mevcut adım / toplam adım ve adım etiketi
  * dört kaynağın AYAR ve ÖLÇÜLEN akımları, nominale göre asimetrileri
  * son hesaplanan merkez (µm) ve g
  * son arka plan değeri ve tazeliği
  * sonraki eylem

Düğmeler: Onayla, Bu noktayı tekrarla, Arka planı atla, Duraklat/Devam,
DURDUR ve akımları sıfırla; ayrıca rutin düğmeleri.

Donanım işlemleri (rampa + oturma beklemesi) bloklayıcı olabildiği için
bekleme, `qt_bekle` ile Qt olay döngüsünü işleterek yapılır; işlem süresince
düğmeler devre dışı kalır. Böylece arayüz donmaz, thread karmaşası da olmaz.

Pencere kapanırsa ya da beklenmeyen bir hata olursa akımlar rampa ile sıfıra
indirilir.

Not: tanımlayıcılar (değişken/fonksiyon adları) ve yapılandırma değerleri
bilinçli olarak ASCII'dir; yalnızca insanın okuduğu metinler tam Türkçedir.
"""
from __future__ import annotations

import time
import traceback
from typing import Any

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .harmonikler import HarmonikOlcumu
from .is_akisi import Bekleme, Faz, IsAkisi
from .olcum_kaynagi import (
    AlanGirisi,
    AlanHatasi,
    DosyaGirisi,
    SimulatorGirisi,
    alanlardan_olcum,
    olcumden_alanlar,
)
from .tema import TEMALAR, Tema, tema_al
from .yapilandirma import BOBIN_SAYISI, Yapilandirma

BICIM_ETIKETLERI = {
    "genlik_faz": "Genlik + faz",
    "normal_skew": "Normal + skew (B_n, A_n)",
}


def qt_bekle(saniye: float) -> None:
    """Qt olay döngüsünü işleterek bekler (arayüz donmasın diye).

    `KaynakGrubu`'na `bekle` olarak verilir; rampa adımları arasındaki
    beklemeler bu fonksiyondan geçer.
    """
    bitis = time.monotonic() + max(0.0, saniye)
    uygulama = QApplication.instance()
    while True:
        kalan = bitis - time.monotonic()
        if kalan <= 0:
            break
        if uygulama is not None:
            uygulama.processEvents()
        time.sleep(min(0.02, kalan))


class MerkezlemePencere(QWidget):
    """Elektriksel merkezleme arayüzü."""

    def __init__(
        self,
        yapilandirma: Yapilandirma,
        akis: IsAkisi,
        deneme_kipi: bool = False,
        otomatik_kaynak_etiketi: str | None = None,
        devam: bool = False,
    ) -> None:
        """`devam=True` ise akış `basla()` yerine `devam_ettir()` ile kurulur
        (durum dosyasından geri yüklenmiş bir akış için).

        `otomatik_kaynak_etiketi`: `deneme_kipi` DIŞINDA, alanların
        `akis.olcum_kaynagi`'ndan (örn. `DosyaGirisi`) otomatik doldurulmasını
        istiyorsanız üst şeritte gösterilecek etiketi verin (örn.
        "OTOMATİK ÖLÇÜM (dosya)"); yarı otomatik çalışma içindir - onay
        düğmelerine yine kullanıcı basar."""
        super().__init__()
        self.kfg = yapilandirma
        self.akis = akis
        self.deneme_kipi = deneme_kipi
        self.otomatik_kaynak_etiketi = otomatik_kaynak_etiketi
        self._otomatik_doldur = deneme_kipi or otomatik_kaynak_etiketi is not None
        self.bicim = yapilandirma.harmonikler.giris_bicimi
        self.tema: Tema = tema_al(yapilandirma.genel.tema)
        self._mesgul = False

        baslik = "pEDM Kuadrupol - Elektriksel Merkezleme"
        self.setWindowTitle(baslik + (" (devam)" if devam else ""))
        self._arayuzu_kur()
        self._temayi_uygula()
        if devam:
            self.akis.devam_ettir()
        else:
            self.akis.basla()
        self._paneli_yenile()

    # ==================================================================
    # Arayüz kurulumu
    # ==================================================================
    def _arayuzu_kur(self) -> None:
        duzen = QVBoxLayout()
        duzen.addWidget(self._ust_seridi_kur())
        duzen.addWidget(self._adim_panelini_kur())
        duzen.addWidget(self._akim_panelini_kur())
        duzen.addWidget(self._giris_panelini_kur())
        duzen.addWidget(self._sonuc_panelini_kur())
        duzen.addWidget(self._dugmeleri_kur())
        duzen.addWidget(self._rutin_dugmelerini_kur())
        self.setLayout(duzen)

    def _ust_seridi_kur(self) -> QWidget:
        kutu = QFrame()
        kutu.setObjectName("ustSerit")
        kutu.setFrameShape(QFrame.StyledPanel)
        duzen = QHBoxLayout()
        self.kip_etiketi = QLabel(f"Kip: {self.kfg.genel.kip.upper()}")
        duzen.addWidget(self.kip_etiketi)
        duzen.addWidget(
            QLabel(f"Modülatör: {'AÇIK' if self.kfg.genel.modulator_acik else 'KAPALI'}")
        )
        duzen.addWidget(QLabel(f"Çalıştırma: {self.akis.calistirma.etiket}"))
        self.deneme_etiketi = QLabel(
            "DENEME KİPİ (simülatör)" if self.deneme_kipi else (self.otomatik_kaynak_etiketi or "")
        )
        self.deneme_etiketi.setVisible(self._otomatik_doldur)
        duzen.addWidget(self.deneme_etiketi)
        duzen.addStretch(1)
        duzen.addWidget(QLabel("Tema:"))
        self.tema_secici = QComboBox()
        for ad, tema in TEMALAR.items():
            self.tema_secici.addItem(tema.baslik, ad)
        self.tema_secici.setCurrentIndex(list(TEMALAR).index(self.tema.ad))
        # İçeriğe göre boyutlan: tema adları kesilmesin
        self.tema_secici.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self.tema_secici.currentIndexChanged.connect(self._tema_degisti)
        duzen.addWidget(self.tema_secici)
        kutu.setLayout(duzen)
        return kutu

    def _adim_panelini_kur(self) -> QWidget:
        kutu = QGroupBox("Adım")
        duzen = QVBoxLayout()
        self.adim_etiketi = QLabel("-")
        kalin = QFont()
        kalin.setBold(True)
        self.adim_etiketi.setFont(kalin)
        self.eylem_etiketi = QLabel("-")
        self.eylem_etiketi.setWordWrap(True)
        duzen.addWidget(self.adim_etiketi)
        duzen.addWidget(self.eylem_etiketi)
        kutu.setLayout(duzen)
        return kutu

    def _akim_panelini_kur(self) -> QWidget:
        kutu = QGroupBox("Akımlar")
        izgara = QGridLayout()
        self.sutun_basliklari: list[QLabel] = []
        for sutun, baslik in enumerate(("Bobin", "ayar (A)", "ölçülen (A)", "nominale göre")):
            etiket = QLabel(baslik)
            izgara.addWidget(etiket, 0, sutun)
            self.sutun_basliklari.append(etiket)
        self.akim_etiketleri: list[tuple[QLabel, QLabel, QLabel]] = []
        for i in range(BOBIN_SAYISI):
            izgara.addWidget(QLabel(f"I{i + 1}"), i + 1, 0)
            ayar, olculen, asimetri = QLabel("-"), QLabel("-"), QLabel("-")
            for sutun, etiket in enumerate((ayar, olculen, asimetri), start=1):
                etiket.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
                izgara.addWidget(etiket, i + 1, sutun)
            self.akim_etiketleri.append((ayar, olculen, asimetri))
        kutu.setLayout(izgara)
        return kutu

    def _giris_panelini_kur(self) -> QWidget:
        harm = self.kfg.harmonikler
        kutu = QGroupBox(
            f"Harmonik girişi   (r_ref = {harm.r_ref_mm:g} mm, birim: {harm.birim})"
        )
        duzen = QVBoxLayout()

        ust = QHBoxLayout()
        ust.addWidget(QLabel("Giriş biçimi:"))
        self.bicim_secici = QComboBox()
        for anahtar, etiket in BICIM_ETIKETLERI.items():
            self.bicim_secici.addItem(etiket, anahtar)
        self.bicim_secici.setCurrentIndex(list(BICIM_ETIKETLERI).index(self.bicim))
        self.bicim_secici.currentIndexChanged.connect(self._bicim_degisti)
        ust.addWidget(self.bicim_secici)
        ust.addStretch(1)
        if self._otomatik_doldur:
            etiket = "Simülatörden doldur" if self.deneme_kipi else "Kaynaktan doldur"
            self.doldur_dugmesi = QPushButton(etiket)
            self.doldur_dugmesi.clicked.connect(self._simulatorden_doldur)
            ust.addWidget(self.doldur_dugmesi)
        duzen.addLayout(ust)

        izgara = QGridLayout()
        self.alan_kutulari: dict[int, tuple[QLineEdit, QLineEdit]] = {}
        self.satir_basliklari: dict[int, tuple[QLabel, bool]] = {}
        self.alan_basliklari: dict[int, tuple[QLabel, QLabel]] = {}
        self.turetilen_etiketleri: dict[int, QLabel] = {}
        satir = 0
        for n in self.kfg.harmonikler.tum_harmonikler:
            zorunlu = n in self.kfg.harmonikler.zorunlu_harmonikler
            baslik = QLabel(f"n = {n}" + ("  (zorunlu)" if zorunlu else "  (isteğe bağlı)"))
            izgara.addWidget(baslik, satir, 0)
            self.satir_basliklari[n] = (baslik, zorunlu)

            birinci_baslik, ikinci_baslik = QLabel("-"), QLabel("-")
            birinci, ikinci = QLineEdit(), QLineEdit()
            for kutu_alani in (birinci, ikinci):
                kutu_alani.setFixedWidth(120)
                kutu_alani.textChanged.connect(self._turetilenleri_yenile)
            izgara.addWidget(birinci_baslik, satir, 1)
            izgara.addWidget(birinci, satir, 2)
            izgara.addWidget(ikinci_baslik, satir, 3)
            izgara.addWidget(ikinci, satir, 4)
            turetilen = QLabel("")
            izgara.addWidget(turetilen, satir, 5)

            self.alan_kutulari[n] = (birinci, ikinci)
            self.alan_basliklari[n] = (birinci_baslik, ikinci_baslik)
            self.turetilen_etiketleri[n] = turetilen
            satir += 1

        self.mutlak_gradyen_kutusu = QLineEdit()
        self.mutlak_gradyen_kutusu.setFixedWidth(120)
        self.mutlak_gradyen_etiketi = QLabel("Mutlak gradyen (T/m):")
        izgara.addWidget(self.mutlak_gradyen_etiketi, satir, 0, 1, 2)
        izgara.addWidget(self.mutlak_gradyen_kutusu, satir, 2)
        gorunur = self.kfg.harmonikler.birim == "units"
        self.mutlak_gradyen_etiketi.setVisible(gorunur)
        self.mutlak_gradyen_kutusu.setVisible(gorunur)

        duzen.addLayout(izgara)

        # Girişin FİZİKSEL KARŞILIĞI, yazarken canlı gösterilir: yanlış yazılan
        # bir rakam, Onayla'ya basmadan önce burada görülür. (Modal onay
        # yalnızca "olası yazım hatası" uyarısında çıkar.)
        self.yorum_etiketi = QLabel("")
        self.yorum_etiketi.setWordWrap(True)
        duzen.addWidget(self.yorum_etiketi)

        kutu.setLayout(duzen)
        self._alan_basliklarini_yenile()
        return kutu

    # ==================================================================
    # Tema
    # ==================================================================
    def _tema_degisti(self) -> None:
        ad = self.tema_secici.currentData()
        if ad == self.tema.ad:
            return
        self.tema = tema_al(ad)
        self._temayi_uygula()

    def _temayi_uygula(self) -> None:
        """Tema stil sayfasını ve rol bazlı stilleri uygular.

        Stil sayfası UYGULAMA genelinde verilir; böylece QMessageBox gibi ayrı
        üst seviye pencereler de temalı görünür.
        """
        uygulama = QApplication.instance()
        if uygulama is not None:
            uygulama.setStyleSheet(self.tema.stil_sayfasi())

        self.kip_etiketi.setStyleSheet(self.tema.kip_stili(self.kfg.genel.kip == "canli"))
        self.deneme_etiketi.setStyleSheet(self.tema.deneme_stili())
        self.eylem_etiketi.setStyleSheet(self.tema.eylem_stili())
        self.yorum_etiketi.setStyleSheet(self.tema.yorum_stili())
        self.sonuc_etiketi.setStyleSheet(self.tema.sonuc_stili())
        self.izleme_etiketi.setStyleSheet(self.tema.sonuk_stili())
        self.durdur_dugmesi.setStyleSheet(self.tema.durdur_stili())
        for etiket in self.sutun_basliklari:
            etiket.setStyleSheet(self.tema.sonuk_stili())
        for baslik, zorunlu in self.satir_basliklari.values():
            baslik.setStyleSheet(
                self.tema.zorunlu_stili() if zorunlu else self.tema.sonuk_stili()
            )
        for etiket in self.turetilen_etiketleri.values():
            etiket.setStyleSheet(self.tema.sonuk_stili())

    def _sonuc_panelini_kur(self) -> QWidget:
        kutu = QGroupBox("Son sonuç")
        duzen = QVBoxLayout()
        self.sonuc_etiketi = QLabel("-")
        self.arka_plan_etiketi = QLabel("-")
        self.izleme_etiketi = QLabel("-")
        # Onay kararının dayandığı metin buraya yazılır (önerilen akımlar, mod
        # genlikleri, beklenen değişim ve güvenlik satırı). Kullanıcının
        # onaylayacağı şeyi görmek için KAYDIRMAK ZORUNDA KALMAMASI gerekir,
        # bu yüzden 12 satırlık öneri metnini sığdıracak yükseklik verilir.
        self.oneri_metni = QPlainTextEdit()
        self.oneri_metni.setReadOnly(True)
        self.oneri_metni.setMinimumHeight(260)
        self.oneri_metni.setFont(QFont("monospace"))
        self.oneri_metni.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.oneri_metni.setVisible(False)
        duzen.addWidget(self.sonuc_etiketi)
        duzen.addWidget(self.arka_plan_etiketi)
        duzen.addWidget(self.izleme_etiketi)
        duzen.addWidget(self.oneri_metni)
        kutu.setLayout(duzen)
        return kutu

    def _dugmeleri_kur(self) -> QWidget:
        kutu = QWidget()
        duzen = QHBoxLayout()
        self.onayla_dugmesi = QPushButton("Onayla")
        self.onayla_dugmesi.setMinimumHeight(44)
        self.onayla_dugmesi.clicked.connect(self._onayla)
        self.tekrarla_dugmesi = QPushButton("Bu noktayı tekrarla")
        self.tekrarla_dugmesi.clicked.connect(self._noktayi_tekrarla)
        self.arka_plan_atla_dugmesi = QPushButton("Arka planı atla")
        self.arka_plan_atla_dugmesi.clicked.connect(self._arka_plani_atla)
        self.duraklat_dugmesi = QPushButton("Duraklat")
        self.duraklat_dugmesi.clicked.connect(self._duraklat_devam)
        self.durdur_dugmesi = QPushButton("DURDUR ve akımları sıfırla")
        self.durdur_dugmesi.setMinimumHeight(44)
        self.durdur_dugmesi.clicked.connect(self._durdur)
        for dugme in (
            self.onayla_dugmesi,
            self.tekrarla_dugmesi,
            self.arka_plan_atla_dugmesi,
            self.duraklat_dugmesi,
            self.durdur_dugmesi,
        ):
            duzen.addWidget(dugme)
        kutu.setLayout(duzen)
        return kutu

    def _rutin_dugmelerini_kur(self) -> QWidget:
        kutu = QGroupBox("Rutinler")
        duzen = QHBoxLayout()
        self.tekrarlanabilirlik_dugmesi = QPushButton("Tekrarlanabilirlik")
        self.tekrarlanabilirlik_dugmesi.clicked.connect(
            lambda: self._rutin_calistir(self.akis.tekrarlanabilirlik_rutinini_kuyrukla)
        )
        self.polarite_dugmesi = QPushButton("Polarite doğrulaması")
        self.polarite_dugmesi.clicked.connect(
            lambda: self._rutin_calistir(self.akis.polarite_rutinini_kuyrukla)
        )
        self.modulator_dugmesi = QPushButton("Modülatör karşılaştırması")
        self.modulator_dugmesi.clicked.connect(
            lambda: self._rutin_calistir(self.akis.modulator_rutinini_kuyrukla)
        )
        self.ozet_dugmesi = QPushButton("Özeti yaz")
        self.ozet_dugmesi.clicked.connect(self._ozeti_yaz)
        for dugme in (
            self.tekrarlanabilirlik_dugmesi,
            self.polarite_dugmesi,
            self.modulator_dugmesi,
            self.ozet_dugmesi,
        ):
            duzen.addWidget(dugme)
        kutu.setLayout(duzen)
        return kutu

    # ==================================================================
    # Alanlar
    # ==================================================================
    def _alan_basliklarini_yenile(self) -> None:
        for n, (birinci, ikinci) in self.alan_basliklari.items():
            if self.bicim == "genlik_faz":
                birim = self.kfg.harmonikler.birim
                faz_birimi = "derece" if self.kfg.harmonikler.faz_birimi == "derece" else "rad"
                birinci.setText(f"|C{n}| ({birim}):")
                ikinci.setText(f"faz ({faz_birimi}):")
            else:
                birim = self.kfg.harmonikler.birim
                birinci.setText(f"B{n} ({birim}):")
                ikinci.setText(f"A{n} ({birim}):")

    def _bicim_degisti(self) -> None:
        yeni = self.bicim_secici.currentData()
        if yeni == self.bicim:
            return
        # Alanlar doluysa biçimi değiştirirken değerleri çevir.
        mevcut = self._alanlari_oku()
        cevrilebilir = True
        try:
            olcum = alanlardan_olcum(
                mevcut,
                self.akis.konvansiyon,
                self.bicim,
                zorunlu=self.kfg.harmonikler.zorunlu_harmonikler,
                opsiyonel=self.kfg.harmonikler.opsiyonel_harmonikler,
            )
        except ValueError:
            # AlanHatasi (boş/sayı değil) ya da HarmonikHatasi (örneğin negatif
            # genlik): ikisi de ValueError türevidir.
            cevrilebilir = False
        self.bicim = yeni
        self._alan_basliklarini_yenile()
        if cevrilebilir:
            self._alanlari_doldur(olcumden_alanlar(olcum, self.akis.konvansiyon, self.bicim))
        else:
            self._turetilenleri_yenile()

    def _alanlari_oku(self) -> AlanGirisi:
        alanlar: dict[str, str] = {}
        for n, (birinci, ikinci) in self.alan_kutulari.items():
            if self.bicim == "genlik_faz":
                alanlar[f"C{n}_genlik"] = birinci.text()
                alanlar[f"C{n}_faz"] = ikinci.text()
            else:
                alanlar[f"B{n}"] = birinci.text()
                alanlar[f"A{n}"] = ikinci.text()
        return AlanGirisi(alanlar=alanlar, mutlak_gradyen_T_m=self.mutlak_gradyen_kutusu.text())

    def _alanlari_doldur(self, giris: AlanGirisi) -> None:
        """Alanları doldurur.

        Doldurma sırasında sinyaller BLOKLANIR: aksi halde yarım doldurulmuş
        alanlar (örneğin biçim değişiminde hâlâ eski biçimdeki değerler) yeni
        biçimde yorumlanmaya çalışılır ve geçici, anlamsız hatalar üretir.
        """
        kutular = [k for cift in self.alan_kutulari.values() for k in cift]
        kutular.append(self.mutlak_gradyen_kutusu)
        for kutu in kutular:
            kutu.blockSignals(True)
        try:
            for n, (birinci, ikinci) in self.alan_kutulari.items():
                if self.bicim == "genlik_faz":
                    birinci.setText(giris.alanlar.get(f"C{n}_genlik", ""))
                    ikinci.setText(giris.alanlar.get(f"C{n}_faz", ""))
                else:
                    birinci.setText(giris.alanlar.get(f"B{n}", ""))
                    ikinci.setText(giris.alanlar.get(f"A{n}", ""))
            if giris.mutlak_gradyen_T_m:
                self.mutlak_gradyen_kutusu.setText(giris.mutlak_gradyen_T_m)
        finally:
            for kutu in kutular:
                kutu.blockSignals(False)
        self._turetilenleri_yenile()

    def _alanlari_temizle(self) -> None:
        for birinci, ikinci in self.alan_kutulari.values():
            birinci.clear()
            ikinci.clear()
        for etiket in self.turetilen_etiketleri.values():
            etiket.setText("")

    def _turetilenleri_yenile(self) -> None:
        """Girilen değerlerin türetilmiş B_n/A_n (ya da genlik/faz) karşılığını gösterir."""
        giris = self._alanlari_oku()
        for n in self.alan_kutulari:
            etiket = self.turetilen_etiketleri[n]
            if not giris.doldurulmus_mu(n, self.bicim):
                etiket.setText("")
                continue
            try:
                tek_alan = AlanGirisi(alanlar=giris.alanlar)
                olcum = alanlardan_olcum(
                    tek_alan, self.akis.konvansiyon, self.bicim, zorunlu=(n,), opsiyonel=()
                )
            except ValueError:
                etiket.setText("(geçersiz)")
                continue
            c_n = olcum.bilesen(n)
            if self.bicim == "genlik_faz":
                b_n, a_n = self.akis.konvansiyon.normal_skewe(c_n)
                etiket.setText(f"->  B{n} = {b_n:.6g}   A{n} = {a_n:.6g}")
            else:
                genlik, faz = self.akis.konvansiyon.genlik_faza(c_n, n)
                etiket.setText(f"->  |C{n}| = {genlik:.6g}   faz = {faz:.4f}")

        self._yorumu_yenile(giris)

    def _yorumu_yenile(self, giris: AlanGirisi) -> None:
        """Girişin fiziksel karşılığını (merkez ve g) canlı gösterir."""
        if self.akis.bekleme is Bekleme.ARKA_PLAN_GIRISI:
            self.yorum_etiketi.setVisible(True)
            self.yorum_etiketi.setText(
                "Bu giriş ARKA PLAN olarak kaydedilecek (akımlar sıfırda, "
                "ölçümlerden kompleks olarak çıkarılacak)."
            )
            return
        if self.akis.bekleme is not Bekleme.OLCUM_GIRISI:
            self.yorum_etiketi.setText("")
            self.yorum_etiketi.setVisible(False)
            return
        self.yorum_etiketi.setVisible(True)
        eksikler = [
            n for n in self.kfg.harmonikler.zorunlu_harmonikler
            if not giris.doldurulmus_mu(n, self.bicim)
        ]
        if eksikler:
            self.yorum_etiketi.setText(
                "Zorunlu alanlar bekleniyor: " + ", ".join(f"n = {n}" for n in eksikler)
            )
            return
        try:
            olcum = alanlardan_olcum(
                giris,
                self.akis.konvansiyon,
                self.bicim,
                zorunlu=self.kfg.harmonikler.zorunlu_harmonikler,
                opsiyonel=self.kfg.harmonikler.opsiyonel_harmonikler,
            )
            net = self.akis.konvansiyon.arka_plan_cikar(olcum, self.akis.son_arka_plan)
            y = self.akis.konvansiyon.kontrol_vektoru(net, self.akis.gradyen_hedefi())
        except Exception as hata:
            self.yorum_etiketi.setText(f"Bu giriş yorumlanamıyor: {hata}")
            return
        self.yorum_etiketi.setText(f"Bu giriş şu anlama geliyor:   {y}")

    # ==================================================================
    # Panel yenileme
    # ==================================================================
    def _paneli_yenile(self) -> None:
        panel = self.akis.durum_paneli()
        self.adim_etiketi.setText(
            f"Adım {panel['adim_no']} / {panel['toplam_adim']}"
            + (f"  -  {panel['etiket']}" if panel["etiket"] else "")
            + (f"   (faz: {panel['faz']}, iterasyon: {panel['iterasyon']})")
        )
        self.eylem_etiketi.setText("Sonraki eylem: " + panel["sonraki_eylem"])

        nominal = self.kfg.miknatis.nominal_akim_A
        for i, (ayar_e, olculen_e, asimetri_e) in enumerate(self.akim_etiketleri):
            ayar = panel["ayar_akimlari_A"][i]
            olculen = panel["olculen_akimlar_A"][i]
            ayar_e.setText(f"{ayar:.4f}")
            olculen_e.setText(f"{olculen:.4f}")
            if abs(ayar) < 1e-9:
                asimetri_e.setText("(sıfır)")
            else:
                asimetri_e.setText(f"{(ayar - nominal) / nominal * 100:+.3f} %")

        if self.akis.son_y is not None:
            self.sonuc_etiketi.setText(str(self.akis.son_y))
        else:
            self.sonuc_etiketi.setText("Henüz işlenmiş bir ölçüm yok.")
        if self.akis.son_arka_plan is not None:
            c1 = self.akis.son_arka_plan.bilesenler.get(1, 0j)
            tazelik = "bu adımda taze" if panel["arka_plan_taze"] else "önceki adımdan"
            self.arka_plan_etiketi.setText(
                f"Son arka plan: B_1 = {c1.real:.4g}, A_1 = {c1.imag:.4g} "
                f"({self.kfg.harmonikler.birim}) - {tazelik}"
            )
        izleme = getattr(self.akis, "son_izleme", None)
        if izleme is None:
            self.izleme_etiketi.setVisible(False)
        else:
            self.izleme_etiketi.setVisible(True)
            parcalar = []
            if izleme.sq_over_g is not None:
                parcalar.append(f"SQ/G = {izleme.sq_over_g:+.5f}")
            if izleme.roll_mrad is not None:
                parcalar.append(f"roll = {izleme.roll_mrad:+.3f} mrad")
            for ad in ("b3", "a3", "b4", "a4"):
                deger = getattr(izleme, ad)
                if deger is not None:
                    parcalar.append(f"{ad} = {deger:.4g}")
            self.izleme_etiketi.setText("İzleme:  " + "   ".join(parcalar))
        if self.akis.son_arka_plan is None:
            self.arka_plan_etiketi.setText("Henüz arka plan ölçümü girilmedi.")

        if self.akis.bekleyen_oneri is not None:
            self.oneri_metni.setPlainText(self.akis.bekleyen_oneri.ozet_metni(nominal))
        elif self.akis.rutin_sonuclari:
            son = self.akis.rutin_sonuclari[-1]
            self.oneri_metni.setPlainText(f"[{son.ad}]\n{son.metin}")
        elif self.akis.kalibrasyon is not None and self.akis.faz is not Faz.KALIBRASYON:
            self.oneri_metni.setPlainText(self.akis.kalibrasyon.ozet_metni())
        self.oneri_metni.setVisible(bool(self.oneri_metni.toPlainText().strip()))

        self._dugmeleri_guncelle()
        if self._otomatik_doldur and self.akis.bekleme in (
            Bekleme.ARKA_PLAN_GIRISI,
            Bekleme.OLCUM_GIRISI,
        ):
            self._simulatorden_doldur()

    def _dugmeleri_guncelle(self) -> None:
        bekleme = self.akis.bekleme
        bitti = self.akis.bitti_mi()
        olcum_bekleniyor = bekleme in (Bekleme.ARKA_PLAN_GIRISI, Bekleme.OLCUM_GIRISI)
        self.onayla_dugmesi.setEnabled(
            not self._mesgul
            and not bitti
            and bekleme
            in (
                Bekleme.ARKA_PLAN_GIRISI,
                Bekleme.OLCUM_GIRISI,
                Bekleme.DUZELTME_ONAYI,
                Bekleme.KULLANICI_EYLEMI,
            )
        )
        if bekleme is Bekleme.DUZELTME_ONAYI:
            self.onayla_dugmesi.setText("Önerilen akımları UYGULA")
        elif bekleme is Bekleme.KULLANICI_EYLEMI:
            self.onayla_dugmesi.setText("Eylemi yaptım, devam")
        else:
            self.onayla_dugmesi.setText("Onayla")
        self.tekrarla_dugmesi.setEnabled(not self._mesgul and olcum_bekleniyor)
        self.arka_plan_atla_dugmesi.setEnabled(
            not self._mesgul
            and bekleme is Bekleme.ARKA_PLAN_GIRISI
            and self.akis.son_arka_plan is not None
        )
        self.duraklat_dugmesi.setEnabled(not self._mesgul and not bitti)
        self.duraklat_dugmesi.setText(
            "Devam" if bekleme is Bekleme.DURAKLATILDI else "Duraklat"
        )
        self.durdur_dugmesi.setEnabled(not self._mesgul and not bitti)
        for dugme in (
            self.tekrarlanabilirlik_dugmesi,
            self.polarite_dugmesi,
            self.modulator_dugmesi,
        ):
            dugme.setEnabled(not self._mesgul and bekleme is Bekleme.YOK)

    # ==================================================================
    # Eylemler
    # ==================================================================
    def _mesgul_calistir(self, islev: Any, *args: Any) -> None:
        """Donanım işlemi içeren bir eylemi meşgul bayrağıyla çalıştırır."""
        if self._mesgul:
            return
        self._mesgul = True
        self._dugmeleri_guncelle()
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            islev(*args)
        except Exception as hata:  # pragma: no cover - arayüz hata yolu
            self._hatayi_isle(hata)
        finally:
            QApplication.restoreOverrideCursor()
            self._mesgul = False
            self._paneli_yenile()

    def _onayla(self) -> None:
        bekleme = self.akis.bekleme
        if bekleme is Bekleme.DUZELTME_ONAYI:
            self._mesgul_calistir(self.akis.duzeltmeyi_onayla)
            return
        if bekleme is Bekleme.KULLANICI_EYLEMI:
            self._mesgul_calistir(self.akis.kullanici_eylemini_onayla)
            return
        if bekleme not in (Bekleme.ARKA_PLAN_GIRISI, Bekleme.OLCUM_GIRISI):
            return

        try:
            olcum = alanlardan_olcum(
                self._alanlari_oku(),
                self.akis.konvansiyon,
                self.bicim,
                zorunlu=self.kfg.harmonikler.zorunlu_harmonikler,
                opsiyonel=self.kfg.harmonikler.opsiyonel_harmonikler,
            )
        except AlanHatasi as hata:
            QMessageBox.warning(self, "Geçersiz giriş", str(hata))
            return

        dogrulama = self.akis.olcum_dogrula(olcum)
        if dogrulama.onay_gerekli:
            yanit = QMessageBox.question(
                self,
                "Olası yazım hatası",
                dogrulama.metin() + "\n\nGirdiğiniz değer doğru mu?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if yanit != QMessageBox.Yes:
                return

        self._mesgul_calistir(self._olcumu_gonder, olcum)

    def _olcumu_gonder(self, olcum: HarmonikOlcumu) -> None:
        self.akis.olcum_gonder(olcum)
        self._alanlari_temizle()

    def _noktayi_tekrarla(self) -> None:
        self._alanlari_temizle()
        self._mesgul_calistir(self.akis.noktayi_tekrarla)

    def _arka_plani_atla(self) -> None:
        self._mesgul_calistir(self.akis.arka_plani_atla)

    def _duraklat_devam(self) -> None:
        if self.akis.bekleme is Bekleme.DURAKLATILDI:
            self.akis.devam_et()
        else:
            self.akis.duraklat()
        self._paneli_yenile()

    def _durdur(self) -> None:
        yanit = QMessageBox.question(
            self,
            "Durdur",
            "Akış durdurulacak ve dört akım rampa ile sıfıra indirilecek. Emin misiniz?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if yanit != QMessageBox.Yes:
            return
        self._mesgul_calistir(self.akis.durdur, "kullanıcı durdurdu")

    def _rutin_calistir(self, kuyruklayici: Any) -> None:
        self._mesgul_calistir(kuyruklayici)

    def _ozeti_yaz(self) -> None:
        try:
            yol = self.akis.ozeti_yaz()
        except Exception as hata:  # pragma: no cover
            self._hatayi_isle(hata)
            return
        QMessageBox.information(self, "Özet yazıldı", f"Özet dosyası:\n{yol}")

    def _simulatorden_doldur(self) -> None:
        """Alanları otomatik kaynaktan (simülatör ya da `DosyaGirisi`) doldurur.

        Kaynak `DosyaGirisi` ise bu çağrı, veri gelene kadar (yoklama +
        zaman aşımı ile) BLOKE olabilir; bu yüzden yalnızca kullanıcı
        düğmeye bastığında ya da bekleme başladığında çağrılır.
        """
        kaynak = self.akis.olcum_kaynagi
        istek = self.akis.mevcut_istek
        if not isinstance(kaynak, (SimulatorGirisi, DosyaGirisi)) or istek is None:
            return
        try:
            olcum = kaynak.olcum_al(istek)
        except Exception as hata:  # pragma: no cover - dosya kaynağı hata yolu
            self._hatayi_isle(hata)
            return
        self._alanlari_doldur(olcumden_alanlar(olcum, self.akis.konvansiyon, self.bicim))

    # ==================================================================
    # Güvenlik: hata ve kapanış
    # ==================================================================
    def _hatayi_isle(self, hata: BaseException) -> None:
        """Beklenmeyen hatada akımları rampa ile sıfıra indirir ve bildirir."""
        izleme = "".join(traceback.format_exception_only(type(hata), hata)).strip()
        try:
            self.akis.kaynaklar.acil_sifirla()
        finally:
            QMessageBox.critical(
                self,
                "Hata",
                f"Beklenmeyen hata oluştu; akımlar rampa ile sıfıra indirildi.\n\n{izleme}",
            )

    def closeEvent(self, olay: Any) -> None:  # noqa: N802 (Qt adlandırması)
        """Pencere kapanırsa akımları güvenli biçimde sıfıra indirir."""
        try:
            if not self.akis.bitti_mi():
                self.akis.durdur("pencere kapatıldı")
            self.akis.kaynaklar.guvenli_kapat()
            self.akis.ozeti_yaz()
        except Exception:  # pragma: no cover - kapanış yolu
            try:
                self.akis.kaynaklar.acil_sifirla()
            except Exception:
                pass
        olay.accept()
