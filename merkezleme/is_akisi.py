"""Is akisi: adim sirasi, durum makinesi, durum dosyasi ve rutinler.

Her olcum noktasinda sira sabittir:

    1. Program dort akimi rampa ile SIFIRA indirir, oturmasini bekler,
       "Arka plan olcumunu alin ve girin" der.
    2. Kullanici arka plan harmoniklerini girer ve onaylar.
       (Atlarsa son gecerli arka plan kullanilir ve bu durum kaydedilir.)
    3. (Gerekiyorsa) kullanicidan bir eylem istenir: role ile polarite
       degisimi, modulatorun acilip kapatilmasi. Akimlar sifirdayken sorulur.
    4. Program akimlari hedefe rampa ile cikarir, oturmasini bekler, olculen
       akimlari gosterir, "Olcumu alin ve girin" der.
    5. Kullanici harmonikleri girer ve onaylar.
    6. Program arka plani cikarir, y'yi hesaplar, sonucu gosterir ve kaydeder,
       sonraki adima gecer.

Butun olcum noktalari tek bir gorev kuyrugundan gelir; kalibrasyon, duzeltme
ve rutinler (tekrarlanabilirlik, polarite dogrulamasi, modulator
karsilastirmasi) ayni makineyi kullanir.

Arayuz olay tabanli calistigi icin bu sinif BLOKLAMAZ: `olcum_gonder`,
`duzeltmeyi_onayla`, `kullanici_eylemini_onayla` gibi cagrilarla ilerler.
Testler ve deneme kipi ayni cagrilari `otomatik_yurut` ile dongude yapar.
"""
from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Sequence

import numpy as np

from .duzeltme import (
    DuzeltmeOnerisi,
    beklenen_y as beklenen_y_hesapla,
    duzeltme_hesapla,
    tekrarlanabilirligi_degerlendir,
    yakinsama_durumu,
)
from .dogrulama import DogrulamaSonucu, girisi_dogrula
from .guc_kaynagi import GuvenlikHatasi, KaynakGrubu
from .harmonikler import HarmonikKonvansiyonu, HarmonikOlcumu, KontrolVektoru
from .kalibrasyon import (
    ORTAK_SIFIR,
    KalibrasyonNoktasi,
    KalibrasyonSonucu,
    kalibrasyonu_kur,
    mod_fitleri,
    plan_olustur,
)
from .kayit import (
    ADIM_ARKA_PLAN,
    ADIM_DUZELTME,
    ADIM_KALIBRASYON,
    ADIM_MODULATOR,
    ADIM_POLARITE,
    ADIM_TEKRARLANABILIRLIK,
    Calistirma,
    OlcumKaydi,
    OzetVerisi,
    ozet_yaz,
)
from .modlar import ModBazi
from .olcum_kaynagi import OlcumIstegi, OlcumKaynagi
from .yapilandirma import BOBIN_SAYISI, Yapilandirma


class Faz(str, Enum):
    HAZIR = "hazir"
    KALIBRASYON = "kalibrasyon"
    DUZELTME = "duzeltme"
    RUTIN = "rutin"
    TAMAMLANDI = "tamamlandi"
    DURDURULDU = "durduruldu"


class Bekleme(str, Enum):
    YOK = "yok"
    ARKA_PLAN_GIRISI = "arka_plan_girisi"
    OLCUM_GIRISI = "olcum_girisi"
    DUZELTME_ONAYI = "duzeltme_onayi"
    KULLANICI_EYLEMI = "kullanici_eylemi"
    DURAKLATILDI = "duraklatildi"


class IsAkisiHatasi(RuntimeError):
    """Is akisi beklenmeyen bir durumda cagrildi."""


@dataclass
class OlcumGorevi:
    """Kuyrugun tek bir ogesi: bir akim ayarinda bir olcum."""

    tur: str
    etiket: str
    akimlar_A: np.ndarray
    mod: str = ""
    epsilon: float | None = None
    arka_plan_al: bool = True
    kullanici_eylemi: str | None = None
    polarite_isareti: int = 1
    modulator_acik: bool | None = None
    kalibrasyon_noktasi: KalibrasyonNoktasi | None = None
    rutin: str | None = None

    def sozluk(self) -> dict[str, Any]:
        return {
            "tur": self.tur,
            "etiket": self.etiket,
            "akimlar_A": [float(a) for a in self.akimlar_A],
            "mod": self.mod,
            "epsilon": self.epsilon,
            "arka_plan_al": self.arka_plan_al,
            "kullanici_eylemi": self.kullanici_eylemi,
            "polarite_isareti": self.polarite_isareti,
            "modulator_acik": self.modulator_acik,
            "rutin": self.rutin,
            "kalibrasyon_noktasi": (
                None
                if self.kalibrasyon_noktasi is None
                else {
                    "mod": self.kalibrasyon_noktasi.mod,
                    "epsilon": self.kalibrasyon_noktasi.epsilon,
                    "arka_plan_al": self.kalibrasyon_noktasi.arka_plan_al,
                }
            ),
        }

    @classmethod
    def sozlukten(cls, veri: dict[str, Any]) -> "OlcumGorevi":
        nokta_verisi = veri.get("kalibrasyon_noktasi")
        return cls(
            tur=veri["tur"],
            etiket=veri["etiket"],
            akimlar_A=np.array(veri["akimlar_A"], dtype=float),
            mod=veri.get("mod", ""),
            epsilon=veri.get("epsilon"),
            arka_plan_al=bool(veri.get("arka_plan_al", True)),
            kullanici_eylemi=veri.get("kullanici_eylemi"),
            polarite_isareti=int(veri.get("polarite_isareti", 1)),
            modulator_acik=veri.get("modulator_acik"),
            rutin=veri.get("rutin"),
            kalibrasyon_noktasi=(
                None
                if nokta_verisi is None
                else KalibrasyonNoktasi(
                    mod=nokta_verisi["mod"],
                    epsilon=float(nokta_verisi["epsilon"]),
                    arka_plan_al=bool(nokta_verisi["arka_plan_al"]),
                )
            ),
        )


@dataclass
class RutinSonucu:
    """Bir rutinin (polarite, modulator, tekrarlanabilirlik) sonucu."""

    ad: str
    metin: str
    veriler: dict[str, Any] = field(default_factory=dict)


class IsAkisi:
    """Kalibrasyon ve duzeltme akisini yuruten durum makinesi."""

    def __init__(
        self,
        yapilandirma: Yapilandirma,
        kaynak_grubu: KaynakGrubu,
        olcum_kaynagi: OlcumKaynagi,
        calistirma: Calistirma,
        konvansiyon: HarmonikKonvansiyonu | None = None,
        mod_bazi: ModBazi | None = None,
    ) -> None:
        self.kfg = yapilandirma
        self.kaynaklar = kaynak_grubu
        self.olcum_kaynagi = olcum_kaynagi
        self.calistirma = calistirma
        self.konvansiyon = konvansiyon or HarmonikKonvansiyonu(yapilandirma.harmonikler)
        self.mod_bazi = mod_bazi or ModBazi(yapilandirma.modlar, yapilandirma.miknatis)

        self.faz = Faz.HAZIR
        self.bekleme = Bekleme.YOK
        self.kuyruk: deque[OlcumGorevi] = deque()
        self.mevcut_gorev: OlcumGorevi | None = None
        self.mevcut_istek: OlcumIstegi | None = None

        self.mevcut_akimlar_A = np.zeros(BOBIN_SAYISI, dtype=float)
        self.olculen_akimlar_A = np.zeros(BOBIN_SAYISI, dtype=float)
        self.olculen_gerilimler_V = np.zeros(BOBIN_SAYISI, dtype=float)

        self.son_arka_plan: HarmonikOlcumu | None = None
        self.arka_plan_taze = False
        self.arka_plan_sayisi = 0
        self.atlanan_arka_plan_sayisi = 0
        self.ilk_arka_plan: HarmonikOlcumu | None = None

        self.gradyen_hedefi_T_m: float | None = None
        self.kalibrasyon: KalibrasyonSonucu | None = None
        self._kalibrasyon_olcumleri: list[tuple[KalibrasyonNoktasi, HarmonikOlcumu]] = []

        self.iterasyon = 0
        self.bekleyen_oneri: DuzeltmeOnerisi | None = None
        self.son_y: KontrolVektoru | None = None
        self.baslangic_y: KontrolVektoru | None = None
        self.son_dogrulama: DogrulamaSonucu | None = None
        self.son_olcum_net: HarmonikOlcumu | None = None

        self._rutin_olcumleri: list[KontrolVektoru] = []
        self._rutin_merkezleri: list[tuple[str, KontrolVektoru]] = []
        self.rutin_sonuclari: list[RutinSonucu] = []
        self.merkez_sacilimi_m: float | None = None
        self.g_sacilimi: float | None = None

        self.adim_no = 0
        self.notlar: list[str] = []
        self.durdurma_nedeni: str | None = None
        self._toplam_gorev_tahmini = 0

    # ==================================================================
    # Baslatma
    # ==================================================================
    def basla(self) -> None:
        """Kaynaklari baslatir, kalibrasyon plani varsa kuyruga koyar."""
        if self.faz is not Faz.HAZIR:
            raise IsAkisiHatasi(f"basla() yalnizca HAZIR fazinda cagrilabilir (faz: {self.faz})")
        self.kaynaklar.baslat()
        if self.kalibrasyon is None:
            self._kalibrasyonu_kuyrukla()
            self.faz = Faz.KALIBRASYON
        else:
            self.faz = Faz.DUZELTME
            self._duzeltme_olcumu_kuyrukla()
        self._sonraki_gorevi_al()

    def kalibrasyonu_yukle(self, sonuc: KalibrasyonSonucu) -> None:
        """Onceki oturumdan kalibrasyon yukler; kalibrasyon fazi atlanir."""
        self.kalibrasyon = sonuc
        self.gradyen_hedefi_T_m = sonuc.gradyen_hedefi_T_m

    def _kalibrasyonu_kuyrukla(self) -> None:
        plan = plan_olustur(self.kfg.kalibrasyon)
        for nokta in plan.noktalar:
            self.kuyruk.append(
                OlcumGorevi(
                    tur=ADIM_KALIBRASYON,
                    etiket=nokta.etiket,
                    akimlar_A=nokta.akimlar(self.mod_bazi),
                    mod=nokta.mod,
                    epsilon=nokta.epsilon,
                    arka_plan_al=nokta.arka_plan_al,
                    modulator_acik=self.kfg.genel.modulator_acik,
                    kalibrasyon_noktasi=nokta,
                )
            )
        self._toplam_gorev_tahmini = len(self.kuyruk) + self.kfg.duzeltme.max_iterasyon
        self.plan = plan

    def _duzeltme_olcumu_kuyrukla(self, akimlar: np.ndarray | None = None) -> None:
        hedef = self.mod_bazi.nominal_akimlar if akimlar is None else np.asarray(akimlar, float)
        arka_plan_al = self.iterasyon % self.kfg.kalibrasyon.arka_plan_her_n_noktada == 0
        self.kuyruk.append(
            OlcumGorevi(
                tur=ADIM_DUZELTME,
                etiket=f"duzeltme iterasyonu {self.iterasyon}",
                akimlar_A=hedef,
                arka_plan_al=arka_plan_al,
                modulator_acik=self.kfg.genel.modulator_acik,
            )
        )

    # ==================================================================
    # Gorev hazirligi (donanim adimlari)
    # ==================================================================
    def _sonraki_gorevi_al(self) -> None:
        if self.bekleme is Bekleme.DURAKLATILDI:
            return
        if not self.kuyruk:
            self.mevcut_gorev = None
            self._fazi_ilerlet()
            return
        self.mevcut_gorev = self.kuyruk.popleft()
        self.adim_no += 1
        self._gorevi_hazirla()

    def _gorevi_hazirla(self) -> None:
        """Mevcut gorev icin donanim adimlarini yapar ve beklemeyi belirler."""
        gorev = self.mevcut_gorev
        if gorev is None:
            return

        # 1) Arka plan gerekiyorsa: akimlari sifira indir ve arka plan iste.
        if gorev.arka_plan_al and not self.arka_plan_taze:
            self.mevcut_akimlar_A = self.kaynaklar.sifira_rampala()
            _, self.olculen_akimlar_A = self.kaynaklar.olcumleri_oku()
            self.mevcut_akimlar_A = np.zeros(BOBIN_SAYISI, dtype=float)
            self.bekleme = Bekleme.ARKA_PLAN_GIRISI
            self.mevcut_istek = OlcumIstegi(
                tur="arka_plan",
                etiket=f"{gorev.etiket} - arka plan",
                akimlar_A=np.zeros(BOBIN_SAYISI, dtype=float),
                adim_no=self.adim_no,
                toplam_adim=self._toplam_gorev_tahmini,
                mod=gorev.mod,
                epsilon=gorev.epsilon,
            )
            return

        # 2) Kullanici eylemi gerekiyorsa (role/modulator): akimlar sifirda sorulur.
        if gorev.kullanici_eylemi:
            if np.any(np.abs(self.mevcut_akimlar_A) > 1e-9):
                self.kaynaklar.sifira_rampala()
                self.mevcut_akimlar_A = np.zeros(BOBIN_SAYISI, dtype=float)
            self.bekleme = Bekleme.KULLANICI_EYLEMI
            self.mevcut_istek = None
            return

        # 3) Hedefe rampala, oturmayi bekle, olculen akimlari goster.
        self.olculen_akimlar_A = self.kaynaklar.rampala(gorev.akimlar_A)
        self.olculen_gerilimler_V, self.olculen_akimlar_A = self.kaynaklar.olcumleri_oku()
        self.mevcut_akimlar_A = np.asarray(gorev.akimlar_A, dtype=float).copy()
        self.bekleme = Bekleme.OLCUM_GIRISI
        self.mevcut_istek = OlcumIstegi(
            tur="olcum",
            etiket=gorev.etiket,
            akimlar_A=self.mevcut_akimlar_A,
            adim_no=self.adim_no,
            toplam_adim=self._toplam_gorev_tahmini,
            mod=gorev.mod,
            epsilon=gorev.epsilon,
        )

    # ==================================================================
    # Kullanici girisleri
    # ==================================================================
    def arka_plani_atla(self) -> None:
        """Arka plan adimini atlar; son gecerli arka plan kullanilir ve kaydedilir."""
        if self.bekleme is not Bekleme.ARKA_PLAN_GIRISI:
            raise IsAkisiHatasi("Arka plan beklenmiyor")
        if self.son_arka_plan is None:
            raise IsAkisiHatasi(
                "Atlanamaz: henuz gecerli bir arka plan olcumu yok (ilk arka plan zorunlu)"
            )
        self.atlanan_arka_plan_sayisi += 1
        self.arka_plan_taze = True
        notu = "Arka plan adimi atlandi; son gecerli arka plan kullanildi"
        self.notlar.append(f"{self.mevcut_gorev.etiket if self.mevcut_gorev else ''}: {notu}")
        self.calistirma.olcum_yaz(
            OlcumKaydi(
                adim_turu=ADIM_ARKA_PLAN,
                adim_no=self.adim_no,
                etiket=self.mevcut_gorev.etiket if self.mevcut_gorev else "",
                arka_plan=self.son_arka_plan,
                arka_plan_taze=False,
                not_metni=notu,
            )
        )
        self._gorevi_hazirla()
        self.durumu_kaydet()

    def kullanici_eylemini_onayla(self) -> None:
        """Role degisimi / modulator gibi bir eylemin yapildigini onaylar."""
        if self.bekleme is not Bekleme.KULLANICI_EYLEMI:
            raise IsAkisiHatasi("Kullanici eylemi beklenmiyor")
        gorev = self.mevcut_gorev
        if gorev is not None:
            self.notlar.append(f"Kullanici eylemi onaylandi: {gorev.kullanici_eylemi}")
            gorev.kullanici_eylemi = None
        self._gorevi_hazirla()
        self.durumu_kaydet()

    def olcum_dogrula(self, olcum: HarmonikOlcumu) -> DogrulamaSonucu:
        """Girisi uygulamadan once dogrular (mertebe + olasi yazim hatasi)."""
        olculen_y: KontrolVektoru | None = None
        beklenen: KontrolVektoru | None = None
        if self.bekleme is Bekleme.OLCUM_GIRISI:
            net = self.konvansiyon.arka_plan_cikar(olcum, self.son_arka_plan)
            try:
                olculen_y = self.konvansiyon.kontrol_vektoru(net, self.gradyen_hedefi())
            except Exception:  # olcum gecersizse mertebe kontrolu yine calisir
                olculen_y = None
            if (
                olculen_y is not None
                and self.kalibrasyon is not None
                and self.son_y is not None
                and self.mevcut_gorev is not None
            ):
                beklenen = beklenen_y_hesapla(
                    self.kalibrasyon.R,
                    self.son_y,
                    self.mod_bazi.bagil_sapma(self.mevcut_akimlar_A)
                    - self.mod_bazi.bagil_sapma(self._onceki_akimlar()),
                )
        sonuc = girisi_dogrula(
            olcum,
            self.konvansiyon,
            self.kfg.dogrulama,
            self.kfg.duzeltme,
            olculen_y=olculen_y,
            beklenen_y=beklenen,
            merkez_sacilimi_m=self.merkez_sacilimi_m,
            g_sacilimi=self.g_sacilimi,
        )
        self.son_dogrulama = sonuc
        return sonuc

    def _onceki_akimlar(self) -> np.ndarray:
        if self.bekleyen_oneri is not None:
            return self.bekleyen_oneri.mevcut_akimlar_A
        return self.mevcut_akimlar_A

    def olcum_gonder(self, olcum: HarmonikOlcumu) -> None:
        """Girilen harmonikleri isler ve akisi ilerletir."""
        if self.bekleme is Bekleme.ARKA_PLAN_GIRISI:
            self._arka_plani_isle(olcum)
            return
        if self.bekleme is Bekleme.OLCUM_GIRISI:
            self._olcumu_isle(olcum)
            return
        raise IsAkisiHatasi(f"Su anda olcum beklenmiyor (bekleme: {self.bekleme})")

    def _arka_plani_isle(self, olcum: HarmonikOlcumu) -> None:
        self.son_arka_plan = olcum
        self.arka_plan_taze = True
        self.arka_plan_sayisi += 1
        if self.ilk_arka_plan is None:
            self.ilk_arka_plan = olcum
        self.calistirma.olcum_yaz(
            OlcumKaydi(
                adim_turu=ADIM_ARKA_PLAN,
                adim_no=self.adim_no,
                etiket=self.mevcut_gorev.etiket if self.mevcut_gorev else "",
                mod=self.mevcut_gorev.mod if self.mevcut_gorev else "",
                ayar_akimlari_A=np.zeros(BOBIN_SAYISI),
                olculen_akimlari_A=self.olculen_akimlar_A,
                ham_olcum=olcum,
                arka_plan_taze=True,
                izleme=self.konvansiyon.izleme(olcum),
                modulator_acik=self.kfg.genel.modulator_acik,
            )
        )
        self._gorevi_hazirla()
        self.durumu_kaydet()

    def _olcumu_isle(self, olcum: HarmonikOlcumu) -> None:
        gorev = self.mevcut_gorev
        if gorev is None:
            raise IsAkisiHatasi("Mevcut gorev yok")

        net = self.konvansiyon.arka_plan_cikar(olcum, self.son_arka_plan)
        self.son_olcum_net = net

        # Kalibrasyonun ilk sifir noktasi ayni zamanda G_hedef'in olculdugu noktadir.
        if (
            self.gradyen_hedefi_T_m is None
            and self.kfg.miknatis.gradyen_hedefi_kaynagi == "ilk_olcum"
            and (gorev.mod == ORTAK_SIFIR or gorev.epsilon in (0.0, None))
        ):
            self.gradyen_hedefi_T_m = self.konvansiyon.gradyen_T_m(net)

        y = self.konvansiyon.kontrol_vektoru(net, self.gradyen_hedefi())
        izleme = self.konvansiyon.izleme(net)
        if self.baslangic_y is None:
            self.baslangic_y = y
            self.baslangic_izleme = izleme
        self.son_y = y
        self.son_izleme = izleme

        self.calistirma.olcum_yaz(
            OlcumKaydi(
                adim_turu=gorev.tur,
                adim_no=self.adim_no,
                etiket=gorev.etiket,
                mod=gorev.mod,
                epsilon=gorev.epsilon,
                ayar_akimlari_A=self.mevcut_akimlar_A,
                olculen_akimlari_A=self.olculen_akimlar_A,
                olculen_gerilimler_V=self.olculen_gerilimler_V,
                ham_olcum=olcum,
                arka_plan=self.son_arka_plan,
                arka_plan_taze=self.arka_plan_taze,
                net_olcum=net,
                y=y,
                izleme=izleme,
                modulator_acik=gorev.modulator_acik,
                polarite_isareti=gorev.polarite_isareti,
                not_metni=(
                    "" if self.son_dogrulama is None or self.son_dogrulama.temiz
                    else "dogrulama uyarisi onaylandi"
                ),
            )
        )

        # Arka plan bir sonraki nokta icin tazeligini yitirir.
        self.arka_plan_taze = False

        if gorev.rutin:
            self._rutin_olcumu_isle(gorev, y)
        elif gorev.tur == ADIM_KALIBRASYON and gorev.kalibrasyon_noktasi is not None:
            self._kalibrasyon_olcumleri.append((gorev.kalibrasyon_noktasi, net))
        elif gorev.tur == ADIM_DUZELTME:
            self._duzeltmeyi_degerlendir(y)
            self.durumu_kaydet()
            return

        self._sonraki_gorevi_al()
        self.durumu_kaydet()

    # ==================================================================
    # Faz gecisleri
    # ==================================================================
    def gradyen_hedefi(self) -> float:
        """Gecerli G_hedef: ilk olcumden gelen deger, yoksa yapilandirmadaki nominal."""
        if self.gradyen_hedefi_T_m is not None:
            return self.gradyen_hedefi_T_m
        return self.kfg.miknatis.nominal_gradyen_T_m

    def _fazi_ilerlet(self) -> None:
        if self.faz is Faz.KALIBRASYON:
            self._kalibrasyonu_tamamla()
            return
        if self.faz is Faz.RUTIN:
            # Rutin bittiginde rutin ONCESI faza donulur. Ana akis zaten
            # tamamlanmissa TAMAMLANDI'da kalinir; yoksa duzeltme surer.
            onceki = getattr(self, "_rutin_oncesi_faz", Faz.TAMAMLANDI)
            if onceki is Faz.DUZELTME and (self.kuyruk or self.bekleyen_oneri is not None):
                self.faz = Faz.DUZELTME
            else:
                self.faz = Faz.TAMAMLANDI
            self.bekleme = Bekleme.YOK
            self.mevcut_istek = None
            return
        self.faz = Faz.TAMAMLANDI
        self.bekleme = Bekleme.YOK
        self.mevcut_istek = None

    def _kalibrasyonu_tamamla(self) -> None:
        hedef = self.gradyen_hedefi()
        y_olcumleri = [
            (nokta, self.konvansiyon.kontrol_vektoru(net, hedef))
            for nokta, net in self._kalibrasyon_olcumleri
        ]
        fitler = mod_fitleri(y_olcumleri, self.kfg.kalibrasyon, self.kfg.duzeltme)
        self.kalibrasyon = kalibrasyonu_kur(
            fitler,
            self.mod_bazi,
            self.kfg.kalibrasyon,
            self.kfg.duzeltme,
            hedef,
            self.kfg.genel.modulator_acik,
        )
        self.calistirma.kalibrasyon_yaz(self.kalibrasyon)
        if self.kalibrasyon.supheli:
            self.notlar.extend(f"Kalibrasyon uyarisi: {n}" for n in self.kalibrasyon.supheli_nedenleri)
        self.faz = Faz.DUZELTME
        self.iterasyon = 0
        self.baslangic_y = None
        self._duzeltme_olcumu_kuyrukla()
        self._sonraki_gorevi_al()

    def _duzeltmeyi_degerlendir(self, y: KontrolVektoru) -> None:
        durum = yakinsama_durumu(y, self.kfg.duzeltme)
        if durum.yakinsadi:
            self.notlar.append(f"Yakinsadi ({self.iterasyon} iterasyon): {durum.metin(self.kfg.duzeltme)}")
            self.faz = Faz.TAMAMLANDI
            self.bekleme = Bekleme.YOK
            self.mevcut_istek = None
            return
        if self.iterasyon >= self.kfg.duzeltme.max_iterasyon:
            self.durdurma_nedeni = (
                f"Maksimum iterasyon sayisina ({self.kfg.duzeltme.max_iterasyon}) ulasildi; "
                f"{durum.metin(self.kfg.duzeltme)}"
            )
            self.notlar.append(self.durdurma_nedeni)
            self.faz = Faz.TAMAMLANDI
            self.bekleme = Bekleme.YOK
            self.mevcut_istek = None
            return
        if self.kalibrasyon is None:
            raise IsAkisiHatasi("Duzeltme icin kalibrasyon gerekir")

        self.bekleyen_oneri = duzeltme_hesapla(
            self.kalibrasyon.R,
            y,
            self.mevcut_akimlar_A,
            self.mod_bazi,
            self.kfg.duzeltme,
            self.kfg.guvenlik,
        )
        self.bekleme = Bekleme.DUZELTME_ONAYI
        self.mevcut_istek = None

    def duzeltmeyi_onayla(self) -> None:
        """Onerilen akimlari uygular ve yeni bir olcum adimi kuyruklar."""
        if self.bekleme is not Bekleme.DUZELTME_ONAYI or self.bekleyen_oneri is None:
            raise IsAkisiHatasi("Onaylanacak bir duzeltme onerisi yok")
        oneri = self.bekleyen_oneri
        if not oneri.guvenlik.guvenli:
            self.durdurma_nedeni = "Guvenlik siniri asildi; duzeltme UYGULANMADI.\n" + "\n".join(
                oneri.guvenlik.ihlaller
            )
            self.notlar.append(self.durdurma_nedeni)
            self.faz = Faz.DURDURULDU
            self.bekleme = Bekleme.YOK
            self.bekleyen_oneri = None
            self.durumu_kaydet()
            return
        self.iterasyon += 1
        self.bekleyen_oneri = None
        self._duzeltme_olcumu_kuyrukla(oneri.yeni_akimlar_A)
        self._sonraki_gorevi_al()
        self.durumu_kaydet()

    def duzeltmeyi_reddet(self, neden: str = "kullanici reddetti") -> None:
        """Oneriyi uygulamadan akisi durdurur."""
        self.durdurma_nedeni = f"Duzeltme uygulanmadi: {neden}"
        self.notlar.append(self.durdurma_nedeni)
        self.bekleyen_oneri = None
        self.faz = Faz.DURDURULDU
        self.bekleme = Bekleme.YOK
        self.durumu_kaydet()

    # ==================================================================
    # Nokta tekrari, duraklatma, durdurma
    # ==================================================================
    def noktayi_tekrarla(self) -> None:
        """Mevcut noktayi bastan alir (arka plan dahil)."""
        if self.mevcut_gorev is None:
            raise IsAkisiHatasi("Tekrarlanacak nokta yok")
        self.notlar.append(f"Nokta tekrarlandi: {self.mevcut_gorev.etiket}")
        if self.mevcut_gorev.tur == ADIM_KALIBRASYON and self._kalibrasyon_olcumleri:
            nokta = self.mevcut_gorev.kalibrasyon_noktasi
            if nokta is not None and self._kalibrasyon_olcumleri[-1][0] is nokta:
                self._kalibrasyon_olcumleri.pop()
        self.arka_plan_taze = False
        self._gorevi_hazirla()
        self.durumu_kaydet()

    def duraklat(self) -> None:
        """Akisi duraklatir; akimlar oldugu gibi korunur."""
        if self.bekleme is Bekleme.DURAKLATILDI:
            return
        self._duraklatma_oncesi = self.bekleme
        self.bekleme = Bekleme.DURAKLATILDI
        self.notlar.append("Akis duraklatildi")
        self.durumu_kaydet()

    def devam_et(self) -> None:
        if self.bekleme is not Bekleme.DURAKLATILDI:
            return
        self.bekleme = getattr(self, "_duraklatma_oncesi", Bekleme.YOK)
        self.notlar.append("Akis devam ettirildi")
        self.durumu_kaydet()

    def durdur(self, neden: str = "kullanici durdurdu") -> None:
        """Akisi durdurur ve akimlari rampa ile sifira indirir."""
        self.durdurma_nedeni = neden
        self.notlar.append(f"DURDURULDU: {neden}")
        self.faz = Faz.DURDURULDU
        self.bekleme = Bekleme.YOK
        self.mevcut_istek = None
        try:
            self.kaynaklar.sifira_rampala()
        except (GuvenlikHatasi, Exception):  # pragma: no cover - acil durum yolu
            self.kaynaklar.acil_sifirla()
        self.mevcut_akimlar_A = np.zeros(BOBIN_SAYISI, dtype=float)
        self.durumu_kaydet()

    # ==================================================================
    # Rutinler
    # ==================================================================
    def tekrarlanabilirlik_rutinini_kuyrukla(self, n: int | None = None) -> None:
        """Sabit akimlarda N tekrar olcum kuyruklar."""
        sayi = n if n is not None else self.kfg.duzeltme.tekrarlanabilirlik_N
        akimlar = self.mevcut_akimlar_A.copy()
        if not np.any(akimlar):
            akimlar = self.mod_bazi.nominal_akimlar
        self._rutin_olcumleri = []
        for i in range(sayi):
            self.kuyruk.append(
                OlcumGorevi(
                    tur=ADIM_TEKRARLANABILIRLIK,
                    etiket=f"tekrarlanabilirlik {i + 1}/{sayi}",
                    akimlar_A=akimlar,
                    arka_plan_al=(i == 0),
                    modulator_acik=self.kfg.genel.modulator_acik,
                    rutin="tekrarlanabilirlik",
                )
            )
        self._rutin_oncesi_faz = self.faz
        self.faz = Faz.RUTIN
        if self.bekleme is Bekleme.YOK:
            self._sonraki_gorevi_al()

    def polarite_rutinini_kuyrukla(self) -> None:
        """Polarite degisimi dogrulamasi: merkez(+) ve merkez(-) karsilastirmasi.

        Ayni akim GENLIKLERI uygulanir; isaret role donanimiyla degistirilir.
        Iki olcumde de arka plan cikarma sirasi uygulanir.
        """
        akimlar = self.mevcut_akimlar_A.copy()
        if not np.any(akimlar):
            akimlar = self.mod_bazi.nominal_akimlar
        self._rutin_merkezleri = []
        self.kuyruk.append(
            OlcumGorevi(
                tur=ADIM_POLARITE,
                etiket="polarite (+): duzeltilmis akimlar",
                akimlar_A=akimlar,
                arka_plan_al=True,
                polarite_isareti=+1,
                modulator_acik=self.kfg.genel.modulator_acik,
                rutin="polarite",
            )
        )
        self.kuyruk.append(
            OlcumGorevi(
                tur=ADIM_POLARITE,
                etiket="polarite (-): ayni genlikler, ters polarite",
                akimlar_A=akimlar,
                arka_plan_al=True,
                kullanici_eylemi=(
                    "Akimlar sifirda. ROLE ile miknatis polaritesini DEGISTIRIN, "
                    "sonra onaylayin."
                ),
                polarite_isareti=-1,
                modulator_acik=self.kfg.genel.modulator_acik,
                rutin="polarite",
            )
        )
        self._rutin_oncesi_faz = self.faz
        self.faz = Faz.RUTIN
        if self.bekleme is Bekleme.YOK:
            self._sonraki_gorevi_al()

    def modulator_rutinini_kuyrukla(self) -> None:
        """Modulator KAPALI ve ACIK durumlarinda duzeltilmis merkezi karsilastirir.

        Program modulatoru kontrol etmez; yalnizca kullanicidan durumu
        degistirmesini ister ve hangi durumda olculdugunu kaydeder.
        """
        akimlar = self.mevcut_akimlar_A.copy()
        if not np.any(akimlar):
            akimlar = self.mod_bazi.nominal_akimlar
        self._rutin_merkezleri = []
        mevcut = self.kfg.genel.modulator_acik
        for indeks, durum in enumerate((mevcut, not mevcut)):
            self.kuyruk.append(
                OlcumGorevi(
                    tur=ADIM_MODULATOR,
                    etiket=f"modulator {'ACIK' if durum else 'KAPALI'}",
                    akimlar_A=akimlar,
                    arka_plan_al=True,
                    kullanici_eylemi=(
                        None
                        if indeks == 0
                        else f"Akimlar sifirda. Modulatoru {'ACIN' if durum else 'KAPATIN'}, "
                        "sonra onaylayin."
                    ),
                    modulator_acik=durum,
                    rutin="modulator",
                )
            )
        self._rutin_oncesi_faz = self.faz
        self.faz = Faz.RUTIN
        if self.bekleme is Bekleme.YOK:
            self._sonraki_gorevi_al()

    def _rutin_olcumu_isle(self, gorev: OlcumGorevi, y: KontrolVektoru) -> None:
        if gorev.rutin == "tekrarlanabilirlik":
            self._rutin_olcumleri.append(y)
            beklenen = sum(1 for g in self.kuyruk if g.rutin == "tekrarlanabilirlik")
            if beklenen == 0:
                sonuc = tekrarlanabilirligi_degerlendir(self._rutin_olcumleri, self.kfg.duzeltme)
                self.merkez_sacilimi_m = sonuc.merkez_sigma_m
                self.g_sacilimi = sonuc.g_sigma
                self.rutin_sonuclari.append(
                    RutinSonucu(
                        ad="tekrarlanabilirlik",
                        metin=sonuc.ozet_metni(),
                        veriler={
                            "n": sonuc.n,
                            "x_c_sigma_um": sonuc.x_c_sigma_m * 1e6,
                            "y_c_sigma_um": sonuc.y_c_sigma_m * 1e6,
                            "g_sigma": sonuc.g_sigma,
                            "tolerans_yeterli_mi": sonuc.tolerans_yeterli_mi,
                        },
                    )
                )
                self.notlar.extend(f"Tekrarlanabilirlik uyarisi: {u}" for u in sonuc.uyarilar)
            return

        etiket = "+" if gorev.polarite_isareti > 0 else "-"
        if gorev.rutin == "modulator":
            etiket = "acik" if gorev.modulator_acik else "kapali"
        self._rutin_merkezleri.append((etiket, y))
        kalan = sum(1 for g in self.kuyruk if g.rutin == gorev.rutin)
        if kalan == 0 and len(self._rutin_merkezleri) >= 2:
            (ad1, y1), (ad2, y2) = self._rutin_merkezleri[0], self._rutin_merkezleri[1]
            dx = (y1.x_c - y2.x_c) * 1e6
            dy = (y1.y_c - y2.y_c) * 1e6
            metin = (
                f"merkez({ad1}) = ({y1.x_c * 1e6:+.2f}, {y1.y_c * 1e6:+.2f}) um\n"
                f"merkez({ad2}) = ({y2.x_c * 1e6:+.2f}, {y2.y_c * 1e6:+.2f}) um\n"
                f"fark = ({dx:+.2f}, {dy:+.2f}) um   |fark| = {math.hypot(dx, dy):.2f} um"
            )
            self.rutin_sonuclari.append(
                RutinSonucu(
                    ad=gorev.rutin or "rutin",
                    metin=metin,
                    veriler={
                        "birinci": ad1,
                        "ikinci": ad2,
                        "fark_x_um": dx,
                        "fark_y_um": dy,
                        "fark_buyukluk_um": math.hypot(dx, dy),
                    },
                )
            )

    # ==================================================================
    # Durum paneli ve durum dosyasi
    # ==================================================================
    def sonraki_eylem_metni(self) -> str:
        if self.bekleme is Bekleme.DURAKLATILDI:
            return "DURAKLATILDI - devam etmek icin Devam'a basin"
        if self.bekleme is Bekleme.ARKA_PLAN_GIRISI:
            return "ARKA PLAN OLCUMUNU ALIN VE GIRIN (akimlar sifirda)"
        if self.bekleme is Bekleme.OLCUM_GIRISI:
            return "OLCUMU ALIN VE GIRIN"
        if self.bekleme is Bekleme.DUZELTME_ONAYI:
            return "ONERILEN AKIMLARI ONAYLAYIN"
        if self.bekleme is Bekleme.KULLANICI_EYLEMI:
            gorev = self.mevcut_gorev
            return gorev.kullanici_eylemi if gorev and gorev.kullanici_eylemi else "Eylem bekleniyor"
        if self.faz is Faz.TAMAMLANDI:
            return "TAMAMLANDI"
        if self.faz is Faz.DURDURULDU:
            return f"DURDURULDU: {self.durdurma_nedeni or ''}"
        return "-"

    def durum_paneli(self) -> dict[str, Any]:
        """Arayuzun surekli gosterdigi bilgiler."""
        return {
            "faz": self.faz.value,
            "bekleme": self.bekleme.value,
            "adim_no": self.adim_no,
            "toplam_adim": self._toplam_gorev_tahmini,
            "etiket": self.mevcut_gorev.etiket if self.mevcut_gorev else "",
            "iterasyon": self.iterasyon,
            "ayar_akimlari_A": [float(a) for a in self.mevcut_akimlar_A],
            "olculen_akimlar_A": [float(a) for a in self.olculen_akimlar_A],
            "son_y": None if self.son_y is None else str(self.son_y),
            "son_merkez_um": None if self.son_y is None else self.son_y.merkez_normu_m * 1e6,
            "son_g": None if self.son_y is None else self.son_y.g,
            "arka_plan_C1": (
                None
                if self.son_arka_plan is None
                else complex(self.son_arka_plan.bilesenler.get(1, 0j)).__repr__()
            ),
            "arka_plan_taze": self.arka_plan_taze,
            "modulator_acik": self.kfg.genel.modulator_acik,
            "kip": self.kfg.genel.kip,
            "sonraki_eylem": self.sonraki_eylem_metni(),
        }

    def _durum_sozlugu(self) -> dict[str, Any]:
        def olcum_sozlugu(olcum: HarmonikOlcumu | None) -> dict[str, Any] | None:
            if olcum is None:
                return None
            return {
                "bilesenler": {str(n): [c.real, c.imag] for n, c in olcum.bilesenler.items()},
                "zaman": olcum.zaman,
                "mutlak_gradyen_T_m": olcum.mutlak_gradyen_T_m,
            }

        return {
            "tamamlandi": self.faz in (Faz.TAMAMLANDI, Faz.DURDURULDU),
            "faz": self.faz.value,
            "bekleme": self.bekleme.value,
            "adim_no": self.adim_no,
            "iterasyon": self.iterasyon,
            "mevcut_akimlar_A": [float(a) for a in self.mevcut_akimlar_A],
            "gradyen_hedefi_T_m": self.gradyen_hedefi_T_m,
            "arka_plan_taze": self.arka_plan_taze,
            "arka_plan_sayisi": self.arka_plan_sayisi,
            "atlanan_arka_plan_sayisi": self.atlanan_arka_plan_sayisi,
            "son_arka_plan": olcum_sozlugu(self.son_arka_plan),
            "mevcut_gorev": None if self.mevcut_gorev is None else self.mevcut_gorev.sozluk(),
            "kuyruk": [g.sozluk() for g in self.kuyruk],
            "kalibrasyon_olcumleri": [
                {
                    "nokta": {"mod": n.mod, "epsilon": n.epsilon, "arka_plan_al": n.arka_plan_al},
                    "olcum": olcum_sozlugu(o),
                }
                for n, o in self._kalibrasyon_olcumleri
            ],
            "kalibrasyon_dosyasi": (
                str(self.calistirma.kalibrasyon_json) if self.kalibrasyon is not None else None
            ),
            "notlar": list(self.notlar),
            "durdurma_nedeni": self.durdurma_nedeni,
        }

    def durumu_kaydet(self) -> None:
        self.calistirma.durum_yaz(self._durum_sozlugu())

    def durumu_uygula(self, durum: dict[str, Any]) -> None:
        """Durum dosyasindan akisi geri yukler (kaldigi yerden devam)."""

        def olcumu_coz(veri: dict[str, Any] | None) -> HarmonikOlcumu | None:
            if veri is None:
                return None
            return HarmonikOlcumu(
                bilesenler={
                    int(n): complex(c[0], c[1]) for n, c in veri["bilesenler"].items()
                },
                zaman=float(veri.get("zaman", 0.0)),
                mutlak_gradyen_T_m=veri.get("mutlak_gradyen_T_m"),
            )

        self.faz = Faz(durum["faz"])
        self.bekleme = Bekleme(durum["bekleme"])
        self.adim_no = int(durum.get("adim_no", 0))
        self.iterasyon = int(durum.get("iterasyon", 0))
        self.mevcut_akimlar_A = np.array(durum.get("mevcut_akimlar_A", [0.0] * BOBIN_SAYISI), float)
        self.gradyen_hedefi_T_m = durum.get("gradyen_hedefi_T_m")
        self.arka_plan_taze = bool(durum.get("arka_plan_taze", False))
        self.arka_plan_sayisi = int(durum.get("arka_plan_sayisi", 0))
        self.atlanan_arka_plan_sayisi = int(durum.get("atlanan_arka_plan_sayisi", 0))
        self.son_arka_plan = olcumu_coz(durum.get("son_arka_plan"))
        self.mevcut_gorev = (
            None if durum.get("mevcut_gorev") is None else OlcumGorevi.sozlukten(durum["mevcut_gorev"])
        )
        self.kuyruk = deque(OlcumGorevi.sozlukten(g) for g in durum.get("kuyruk", []))
        self._kalibrasyon_olcumleri = []
        for oge in durum.get("kalibrasyon_olcumleri", []):
            nokta = KalibrasyonNoktasi(
                mod=oge["nokta"]["mod"],
                epsilon=float(oge["nokta"]["epsilon"]),
                arka_plan_al=bool(oge["nokta"]["arka_plan_al"]),
            )
            olcum = olcumu_coz(oge["olcum"])
            if olcum is not None:
                self._kalibrasyon_olcumleri.append((nokta, olcum))
        self.notlar = list(durum.get("notlar", []))
        self.durdurma_nedeni = durum.get("durdurma_nedeni")
        kalibrasyon_dosyasi = durum.get("kalibrasyon_dosyasi")
        if kalibrasyon_dosyasi:
            try:
                self.kalibrasyon = KalibrasyonSonucu.yukle(kalibrasyon_dosyasi)
            except FileNotFoundError:  # pragma: no cover
                self.kalibrasyon = None
        self._toplam_gorev_tahmini = self.adim_no + len(self.kuyruk)

    def devam_ettir(self) -> None:
        """Durum yuklendikten sonra donanimi hazirlar ve mevcut adimi tekrar kurar."""
        self.kaynaklar.baslat()
        self.arka_plan_taze = False
        if self.mevcut_gorev is not None:
            self.notlar.append(f"Kaldigi yerden devam: {self.mevcut_gorev.etiket}")
            self._gorevi_hazirla()
        else:
            self._sonraki_gorevi_al()
        self.durumu_kaydet()

    # ==================================================================
    # Tamamlama
    # ==================================================================
    def ozeti_yaz(self) -> Any:
        """Calistirma sonu Markdown ozetini ve SCPI gunlugunu yazar."""
        tekrarlanabilirlik_metni = "\n\n".join(
            f"[{r.ad}]\n{r.metin}" for r in self.rutin_sonuclari
        )
        veri = OzetVerisi(
            kip=self.kfg.genel.kip,
            modulator_acik=self.kfg.genel.modulator_acik,
            baslangic_y=self.baslangic_y,
            son_y=self.son_y,
            baslangic_izleme=getattr(self, "baslangic_izleme", None),
            son_izleme=getattr(self, "son_izleme", None),
            son_akimlar_A=[float(a) for a in self.mevcut_akimlar_A],
            nominal_akim_A=self.kfg.miknatis.nominal_akim_A,
            iterasyon_sayisi=self.iterasyon,
            kalibrasyon=self.kalibrasyon,
            tekrarlanabilirlik_metni=tekrarlanabilirlik_metni,
            arka_plan_ilk=self.ilk_arka_plan,
            arka_plan_son=self.son_arka_plan,
            arka_plan_sayisi=self.arka_plan_sayisi,
            atlanan_arka_plan_sayisi=self.atlanan_arka_plan_sayisi,
            notlar=list(self.notlar) + ([self.durdurma_nedeni] if self.durdurma_nedeni else []),
        )
        self.calistirma.scpi_gunlugu_yaz(self.kaynaklar.gunluk)
        return ozet_yaz(self.calistirma, veri)

    def bitti_mi(self) -> bool:
        return self.faz in (Faz.TAMAMLANDI, Faz.DURDURULDU)


# ---------------------------------------------------------------------------
# Otomatik yurutme (testler ve deneme kipi)
# ---------------------------------------------------------------------------
def otomatik_yurut(
    akis: IsAkisi,
    kaynak: OlcumKaynagi,
    max_adim: int = 500,
    uyari_onayla: bool = True,
) -> None:
    """Akisi, olcumleri `kaynak`tan alarak sonuna kadar yurutur.

    Elle girisin yerine gecer: arka plan ve olcum isteklerini otomatik
    cevaplar, duzeltme onerilerini onaylar. Dogrulama uyarisi cikarsa
    `uyari_onayla` True ise onaylanir (deneme kipi), False ise akis durur.
    """
    for _ in range(max_adim):
        if akis.bitti_mi():
            return
        if akis.bekleme in (Bekleme.ARKA_PLAN_GIRISI, Bekleme.OLCUM_GIRISI):
            istek = akis.mevcut_istek
            if istek is None:
                raise IsAkisiHatasi("Olcum istegi yok")
            olcum = kaynak.olcum_al(istek)
            sonuc = akis.olcum_dogrula(olcum)
            if sonuc.onay_gerekli and not uyari_onayla:
                akis.durdur(f"Dogrulama uyarisi onaylanmadi: {sonuc.metin()}")
                return
            akis.olcum_gonder(olcum)
        elif akis.bekleme is Bekleme.DUZELTME_ONAYI:
            akis.duzeltmeyi_onayla()
        elif akis.bekleme is Bekleme.KULLANICI_EYLEMI:
            akis.kullanici_eylemini_onayla()
        elif akis.bekleme is Bekleme.DURAKLATILDI:
            akis.devam_et()
        else:
            raise IsAkisiHatasi(
                f"Otomatik yurutme ilerleyemiyor (faz: {akis.faz}, bekleme: {akis.bekleme})"
            )
    raise IsAkisiHatasi(f"Otomatik yurutme {max_adim} adimda bitmedi")
