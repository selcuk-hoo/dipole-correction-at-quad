"""PyQt5 masaustu arayuzu.

Ekranda her zaman bulunanlar:
  * mevcut adim / toplam adim ve adim etiketi
  * dort kaynagin AYAR ve OLCULEN akimlari, nominale gore asimetrileri
  * son hesaplanan merkez (um) ve g
  * son arka plan degeri ve tazeligi
  * sonraki eylem

Duzenler: Onayla, Bu noktayi tekrarla, Arka plani atla, Duraklat/Devam,
DURDUR ve akimlari sifirla; ayrica rutin dugmeleri.

Donanim islemleri (rampa + oturma beklemesi) bloklayici olabildigi icin
bekleme, `qt_bekle` ile Qt olay dongusunu isleterek yapilir; islem suresince
dugmeler devre disi kalir. Boylece arayuz donmaz, thread karmasasi da olmaz.

Pencere kapanirsa ya da beklenmeyen bir hata olursa akimlar rampa ile sifira
indirilir.
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
    SimulatorGirisi,
    alanlardan_olcum,
    olcumden_alanlar,
)
from .yapilandirma import BOBIN_SAYISI, Yapilandirma

BICIM_ETIKETLERI = {
    "genlik_faz": "Genlik + faz",
    "normal_skew": "Normal + skew (B_n, A_n)",
}


def qt_bekle(saniye: float) -> None:
    """Qt olay dongusunu isleterek bekler (arayuz donmasin diye).

    `KaynakGrubu`'na `bekle` olarak verilir; rampa adimlari arasindaki
    beklemeler bu fonksiyondan gecer.
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
    """Elektriksel merkezleme arayuzu."""

    def __init__(
        self,
        yapilandirma: Yapilandirma,
        akis: IsAkisi,
        deneme_kipi: bool = False,
        devam: bool = False,
    ) -> None:
        """`devam=True` ise akis `basla()` yerine `devam_ettir()` ile kurulur
        (durum dosyasindan geri yuklenmis bir akis icin)."""
        super().__init__()
        self.kfg = yapilandirma
        self.akis = akis
        self.deneme_kipi = deneme_kipi
        self.bicim = yapilandirma.harmonikler.giris_bicimi
        self._mesgul = False

        baslik = "pEDM Kuadrupol - Elektriksel Merkezleme"
        self.setWindowTitle(baslik + (" (devam)" if devam else ""))
        self._arayuzu_kur()
        if devam:
            self.akis.devam_ettir()
        else:
            self.akis.basla()
        self._paneli_yenile()

    # ==================================================================
    # Arayuz kurulumu
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
        kutu.setFrameShape(QFrame.StyledPanel)
        duzen = QHBoxLayout()
        kip = self.kfg.genel.kip.upper()
        self.kip_etiketi = QLabel(f"Kip: {kip}")
        if self.kfg.genel.kip == "canli":
            self.kip_etiketi.setStyleSheet("color: white; background: #b00020; padding: 2px 6px;")
        else:
            self.kip_etiketi.setStyleSheet("color: white; background: #2e7d32; padding: 2px 6px;")
        duzen.addWidget(self.kip_etiketi)
        duzen.addWidget(
            QLabel(f"Modulator: {'ACIK' if self.kfg.genel.modulator_acik else 'KAPALI'}")
        )
        duzen.addWidget(QLabel(f"Calistirma: {self.akis.calistirma.etiket}"))
        if self.deneme_kipi:
            deneme = QLabel("DENEME KIPI (simulator)")
            deneme.setStyleSheet("color: white; background: #1565c0; padding: 2px 6px;")
            duzen.addWidget(deneme)
        duzen.addStretch(1)
        kutu.setLayout(duzen)
        return kutu

    def _adim_panelini_kur(self) -> QWidget:
        kutu = QGroupBox("Adim")
        duzen = QVBoxLayout()
        self.adim_etiketi = QLabel("-")
        kalin = QFont()
        kalin.setBold(True)
        self.adim_etiketi.setFont(kalin)
        self.eylem_etiketi = QLabel("-")
        self.eylem_etiketi.setWordWrap(True)
        self.eylem_etiketi.setStyleSheet("color: #0d47a1; font-size: 13pt;")
        duzen.addWidget(self.adim_etiketi)
        duzen.addWidget(self.eylem_etiketi)
        kutu.setLayout(duzen)
        return kutu

    def _akim_panelini_kur(self) -> QWidget:
        kutu = QGroupBox("Akimlar")
        izgara = QGridLayout()
        for sutun, baslik in enumerate(("Bobin", "ayar (A)", "olculen (A)", "nominale gore")):
            etiket = QLabel(baslik)
            etiket.setStyleSheet("color: gray;")
            izgara.addWidget(etiket, 0, sutun)
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
            f"Harmonik girisi   (r_ref = {harm.r_ref_mm:g} mm, birim: {harm.birim})"
        )
        duzen = QVBoxLayout()

        ust = QHBoxLayout()
        ust.addWidget(QLabel("Giris bicimi:"))
        self.bicim_secici = QComboBox()
        for anahtar, etiket in BICIM_ETIKETLERI.items():
            self.bicim_secici.addItem(etiket, anahtar)
        self.bicim_secici.setCurrentIndex(list(BICIM_ETIKETLERI).index(self.bicim))
        self.bicim_secici.currentIndexChanged.connect(self._bicim_degisti)
        ust.addWidget(self.bicim_secici)
        ust.addStretch(1)
        if self.deneme_kipi:
            self.doldur_dugmesi = QPushButton("Simulatorden doldur")
            self.doldur_dugmesi.clicked.connect(self._simulatorden_doldur)
            ust.addWidget(self.doldur_dugmesi)
        duzen.addLayout(ust)

        izgara = QGridLayout()
        self.alan_kutulari: dict[int, tuple[QLineEdit, QLineEdit]] = {}
        self.alan_basliklari: dict[int, tuple[QLabel, QLabel]] = {}
        self.turetilen_etiketleri: dict[int, QLabel] = {}
        satir = 0
        for n in self.kfg.harmonikler.tum_harmonikler:
            zorunlu = n in self.kfg.harmonikler.zorunlu_harmonikler
            baslik = QLabel(f"n = {n}" + ("  (zorunlu)" if zorunlu else "  (istege bagli)"))
            baslik.setStyleSheet("color: gray;" if not zorunlu else "font-weight: bold;")
            izgara.addWidget(baslik, satir, 0)

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
            turetilen.setStyleSheet("color: #555;")
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

        # Girisin FIZIKSEL KARSILIGI, yazarken canli gosterilir: yanlis yazilan
        # bir rakam, Onayla'ya basmadan once burada gorulur. (Modal onay
        # yalnizca "olasi yazim hatasi" uyarisinda cikar.)
        self.yorum_etiketi = QLabel("")
        self.yorum_etiketi.setWordWrap(True)
        self.yorum_etiketi.setStyleSheet(
            "background: #fff8e1; border: 1px solid #ffca28; padding: 6px; font-size: 12pt;"
        )
        duzen.addWidget(self.yorum_etiketi)

        kutu.setLayout(duzen)
        self._alan_basliklarini_yenile()
        return kutu

    def _sonuc_panelini_kur(self) -> QWidget:
        kutu = QGroupBox("Son sonuc")
        duzen = QVBoxLayout()
        self.sonuc_etiketi = QLabel("-")
        self.sonuc_etiketi.setStyleSheet("font-size: 12pt;")
        self.arka_plan_etiketi = QLabel("-")
        self.izleme_etiketi = QLabel("-")
        self.izleme_etiketi.setStyleSheet("color: #555;")
        self.oneri_metni = QPlainTextEdit()
        self.oneri_metni.setReadOnly(True)
        self.oneri_metni.setMaximumHeight(170)
        self.oneri_metni.setFont(QFont("monospace"))
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
        self.tekrarla_dugmesi = QPushButton("Bu noktayi tekrarla")
        self.tekrarla_dugmesi.clicked.connect(self._noktayi_tekrarla)
        self.arka_plan_atla_dugmesi = QPushButton("Arka plani atla")
        self.arka_plan_atla_dugmesi.clicked.connect(self._arka_plani_atla)
        self.duraklat_dugmesi = QPushButton("Duraklat")
        self.duraklat_dugmesi.clicked.connect(self._duraklat_devam)
        self.durdur_dugmesi = QPushButton("DURDUR ve akimlari sifirla")
        self.durdur_dugmesi.setStyleSheet("color: white; background: #b00020; font-weight: bold;")
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
        self.polarite_dugmesi = QPushButton("Polarite dogrulamasi")
        self.polarite_dugmesi.clicked.connect(
            lambda: self._rutin_calistir(self.akis.polarite_rutinini_kuyrukla)
        )
        self.modulator_dugmesi = QPushButton("Modulator karsilastirmasi")
        self.modulator_dugmesi.clicked.connect(
            lambda: self._rutin_calistir(self.akis.modulator_rutinini_kuyrukla)
        )
        self.ozet_dugmesi = QPushButton("Ozeti yaz")
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
        # Alanlar doluysa bicimi degistirirken degerleri cevir.
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
            # AlanHatasi (bos/sayi degil) ya da HarmonikHatasi (ornegin negatif
            # genlik): ikisi de ValueError turevidir.
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
        """Alanlari doldurur.

        Doldurma sirasinda sinyaller BLOKLANIR: aksi halde yarim doldurulmus
        alanlar (ornegin bicim degisiminde hala eski bicimdeki degerler) yeni
        bicimde yorumlanmaya calisilir ve gecici, anlamsiz hatalar uretir.
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
        """Girilen degerlerin turetilmis B_n/A_n (ya da genlik/faz) karsiligini gosterir."""
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
                etiket.setText("(gecersiz)")
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
        """Girisin fiziksel karsiligini (merkez ve g) canli gosterir."""
        if self.akis.bekleme is Bekleme.ARKA_PLAN_GIRISI:
            self.yorum_etiketi.setText(
                "Bu giris ARKA PLAN olarak kaydedilecek (akimlar sifirda, "
                "olcumlerden kompleks olarak cikarilacak)."
            )
            return
        if self.akis.bekleme is not Bekleme.OLCUM_GIRISI:
            self.yorum_etiketi.setText("")
            return
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
            self.yorum_etiketi.setText(f"Bu giris yorumlanamiyor: {hata}")
            return
        self.yorum_etiketi.setText(f"Bu giris su anlama geliyor:   {y}")

    # ==================================================================
    # Panel yenileme
    # ==================================================================
    def _paneli_yenile(self) -> None:
        panel = self.akis.durum_paneli()
        self.adim_etiketi.setText(
            f"Adim {panel['adim_no']} / {panel['toplam_adim']}"
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
                asimetri_e.setText("(sifir)")
            else:
                asimetri_e.setText(f"{(ayar - nominal) / nominal * 100:+.3f} %")

        if self.akis.son_y is not None:
            self.sonuc_etiketi.setText(str(self.akis.son_y))
        if self.akis.son_arka_plan is not None:
            c1 = self.akis.son_arka_plan.bilesenler.get(1, 0j)
            tazelik = "bu adimda taze" if panel["arka_plan_taze"] else "onceki adimdan"
            self.arka_plan_etiketi.setText(
                f"Son arka plan: B_1 = {c1.real:.4g}, A_1 = {c1.imag:.4g} "
                f"({self.kfg.harmonikler.birim}) - {tazelik}"
            )
        izleme = getattr(self.akis, "son_izleme", None)
        if izleme is not None:
            parcalar = []
            if izleme.sq_over_g is not None:
                parcalar.append(f"SQ/G = {izleme.sq_over_g:+.5f}")
            if izleme.roll_mrad is not None:
                parcalar.append(f"roll = {izleme.roll_mrad:+.3f} mrad")
            for ad in ("b3", "a3", "b4", "a4"):
                deger = getattr(izleme, ad)
                if deger is not None:
                    parcalar.append(f"{ad} = {deger:.4g}")
            self.izleme_etiketi.setText("Izleme:  " + "   ".join(parcalar))

        if self.akis.bekleyen_oneri is not None:
            self.oneri_metni.setPlainText(self.akis.bekleyen_oneri.ozet_metni(nominal))
        elif self.akis.rutin_sonuclari:
            son = self.akis.rutin_sonuclari[-1]
            self.oneri_metni.setPlainText(f"[{son.ad}]\n{son.metin}")
        elif self.akis.kalibrasyon is not None and self.akis.faz is not Faz.KALIBRASYON:
            self.oneri_metni.setPlainText(self.akis.kalibrasyon.ozet_metni())

        self._dugmeleri_guncelle()
        if self.deneme_kipi and self.akis.bekleme in (
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
            self.onayla_dugmesi.setText("Onerilen akimlari UYGULA")
        elif bekleme is Bekleme.KULLANICI_EYLEMI:
            self.onayla_dugmesi.setText("Eylemi yaptim, devam")
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
        """Donanim islemi iceren bir eylemi mesgul bayragiyla calistirir."""
        if self._mesgul:
            return
        self._mesgul = True
        self._dugmeleri_guncelle()
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            islev(*args)
        except Exception as hata:  # pragma: no cover - arayuz hata yolu
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
            QMessageBox.warning(self, "Gecersiz giris", str(hata))
            return

        dogrulama = self.akis.olcum_dogrula(olcum)
        if dogrulama.onay_gerekli:
            yanit = QMessageBox.question(
                self,
                "Olasi yazim hatasi",
                dogrulama.metin() + "\n\nGirdiginiz deger dogru mu?",
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
            "Akis durdurulacak ve dort akim rampa ile sifira indirilecek. Emin misiniz?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if yanit != QMessageBox.Yes:
            return
        self._mesgul_calistir(self.akis.durdur, "kullanici durdurdu")

    def _rutin_calistir(self, kuyruklayici: Any) -> None:
        self._mesgul_calistir(kuyruklayici)

    def _ozeti_yaz(self) -> None:
        try:
            yol = self.akis.ozeti_yaz()
        except Exception as hata:  # pragma: no cover
            self._hatayi_isle(hata)
            return
        QMessageBox.information(self, "Ozet yazildi", f"Ozet dosyasi:\n{yol}")

    def _simulatorden_doldur(self) -> None:
        """Deneme kipinde alanlari simulator ciktisiyla doldurur."""
        kaynak = self.akis.olcum_kaynagi
        istek = self.akis.mevcut_istek
        if not isinstance(kaynak, SimulatorGirisi) or istek is None:
            return
        olcum = kaynak.olcum_al(istek)
        self._alanlari_doldur(olcumden_alanlar(olcum, self.akis.konvansiyon, self.bicim))

    # ==================================================================
    # Guvenlik: hata ve kapanis
    # ==================================================================
    def _hatayi_isle(self, hata: BaseException) -> None:
        """Beklenmeyen hatada akimlari rampa ile sifira indirir ve bildirir."""
        izleme = "".join(traceback.format_exception_only(type(hata), hata)).strip()
        try:
            self.akis.kaynaklar.acil_sifirla()
        finally:
            QMessageBox.critical(
                self,
                "Hata",
                f"Beklenmeyen hata olustu; akimlar rampa ile sifira indirildi.\n\n{izleme}",
            )

    def closeEvent(self, olay: Any) -> None:  # noqa: N802 (Qt adlandirmasi)
        """Pencere kapanirsa akimlari guvenli bicimde sifira indirir."""
        try:
            if not self.akis.bitti_mi():
                self.akis.durdur("pencere kapatildi")
            self.akis.kaynaklar.guvenli_kapat()
            self.akis.ozeti_yaz()
        except Exception:  # pragma: no cover - kapanis yolu
            try:
                self.akis.kaynaklar.acil_sifirla()
            except Exception:
                pass
        olay.accept()
