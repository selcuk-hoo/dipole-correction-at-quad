"""Guc kaynagi kontrolu (ITECH IT-M3233, sabit akim kipi).

`eski/guc_kaynagi_orijinal.py` dosyasindaki sinif temel alinmistir; kullanilan
SCPI komut kumesi AYNIDIR ve genisletilmemistir:

    *CLS, *IDN?, SYST:REM, VOLT, CURR, SYST:ERR?, OUTP ON/OFF,
    MEAS:VOLT?, MEAS:CURR?

Eklenenler
----------
* `olcumleri_oku()` float dondurur, ayristirma hatalarini yakalar.
* Her yazma isleminden sonra `SYST:ERR?` kontrol edilir; hata varsa islem
  durdurulur ve kaydedilir.
* Sabit akim kipinde `VOLT` bir uyum (compliance) sinirdir; yapilandirmadan
  okunur ve akim ayarindan ONCE yazilir.
* Akimlar asla tek adimda degistirilmez: yazilimda rampa (A/s). Rampa sonunda
  `MEAS:CURR?` ile hedefe tolerans icinde oturdugu dogrulanir, ardindan
  yapilandirilabilir bir bekleme uygulanir.
* Bobin endüktif oldugu icin (~6.5 mH, 10 A) akim sifir degilken `OUTP OFF`
  KULLANILMAZ; once rampa ile sifira inilir.
* Dort kaynak `KaynakGrubu` ile birlikte yonetilir: es zamanli adimlarla
  rampalama, hepsini okuma, acil durumda hepsini rampa ile sifirlama.
* Varsayilan kip KURU CALISMA: komutlar kaydedilir ama gonderilmez. Gercek
  donanim icin acik bir `--canli` bayragi gerekir.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Callable, Protocol

import numpy as np

from .yapilandirma import BOBIN_SAYISI, GucKaynaklariYapilandirmasi, GuvenlikYapilandirmasi


# `cikis_kapat` icin varsayilan "akim sifir sayilir" esigi. Gercekte
# `KaynakGrubu.guvenli_kapat`, yapilandirmadaki akim_tolerans_A degerini gecer;
# bu sabit yalnizca dogrudan cagrilar icin bir taban saglar.
SIFIR_AKIM_TOLERANSI_A = 0.02


def _sifir_akim_dogrula(adres: str, olculen_akim_A: float, tolerans_A: float) -> None:
    """Akim sifir sayilacak kadar kucuk mu? Degilse GuvenlikHatasi yukseltir."""
    if abs(olculen_akim_A) > tolerans_A:
        raise GuvenlikHatasi(
            f"{adres}: akim {olculen_akim_A:.3f} A iken OUTP OFF kullanilamaz "
            f"(esik {tolerans_A:.3f} A); once rampa ile sifira inilmelidir"
        )


class GucKaynagiHatasi(RuntimeError):
    """Guc kaynagi iletisimi ya da cihaz hatasi."""


class GuvenlikHatasi(RuntimeError):
    """Guvenlik siniri asildi; islem uygulanmadi."""


@dataclass
class KomutKaydi:
    """Tek bir SCPI islemi (kuru calismada da kaydedilir)."""

    zaman: float
    adres: str
    komut: str
    yanit: str | None = None
    gonderildi: bool = True

    def satir(self) -> str:
        yon = "->" if self.gonderildi else "(kuru)"
        yanit = f"  <= {self.yanit!r}" if self.yanit is not None else ""
        return f"{self.zaman:.3f}\t{self.adres}\t{yon} {self.komut}{yanit}"


@dataclass
class KomutGunlugu:
    """SCPI komut gunlugu. kayit.py bunu duz metin olarak diske yazar."""

    kayitlar: list[KomutKaydi] = field(default_factory=list)

    def ekle(self, kayit: KomutKaydi) -> None:
        self.kayitlar.append(kayit)

    def satirlar(self) -> list[str]:
        return [k.satir() for k in self.kayitlar]


class GucKaynagiArayuzu(Protocol):
    """Gercek ve sahte kaynaklarin ortak arayuzu."""

    adres: str

    def baslat(self, uyum_gerilimi_V: float) -> str: ...
    def akim_yaz(self, akim_A: float) -> None: ...
    def olcumleri_oku(self) -> tuple[float, float]: ...
    def cikis_ac(self) -> None: ...
    def cikis_kapat(self, olculen_akim_A: float, tolerans_A: float = ...) -> None: ...
    def kapat(self) -> None: ...


class _TemelKaynak:
    """Gercek ve sahte kaynagin paylastigi gunluk/ayristirma mantigi."""

    def __init__(self, adres: str, gunluk: KomutGunlugu | None = None) -> None:
        self.adres = adres
        self.gunluk = gunluk if gunluk is not None else KomutGunlugu()

    def _kaydet(self, komut: str, yanit: str | None = None, gonderildi: bool = True) -> None:
        self.gunluk.ekle(
            KomutKaydi(
                zaman=time.time(), adres=self.adres, komut=komut, yanit=yanit, gonderildi=gonderildi
            )
        )

    @staticmethod
    def _float_ayristir(metin: str, ne: str) -> float:
        """Cihaz yanitini float'a cevirir; basarisiz olursa aciklayici hata verir."""
        try:
            return float(str(metin).strip().split(",")[0])
        except (TypeError, ValueError) as hata:
            raise GucKaynagiHatasi(f"{ne} yaniti sayiya cevrilemedi: {metin!r}") from hata

    @staticmethod
    def _hata_yaniti_sorunlu_mu(yanit: str) -> tuple[bool, str]:
        """`SYST:ERR?` yanitini yorumlar. (sorunlu_mu, aciklama)"""
        metin = str(yanit).strip()
        if not metin:
            return False, ""
        ilk = metin.split(",")[0].strip()
        try:
            kod = int(float(ilk))
        except ValueError:
            # Yorumlanamayan yanit: hata saymayiz ama gunlukte durur.
            return False, metin
        return kod != 0, metin


class GucKaynagi(_TemelKaynak):
    """Tek bir ITECH IT-M3233 (pyvisa, `@py` backend, seri port)."""

    def __init__(self, adres: str, gunluk: KomutGunlugu | None = None) -> None:
        super().__init__(adres, gunluk)
        # pyvisa yalnizca canli kipte gerekir; kuru calisma ve testler
        # pyvisa kurulu olmadan da calisir.
        try:
            import pyvisa
        except ImportError as hata:  # pragma: no cover - ortama bagli
            raise GucKaynagiHatasi(
                "pyvisa kurulu degil; canli kip icin 'pip install pyvisa pyvisa-py' gerekir"
            ) from hata
        self._rm = pyvisa.ResourceManager("@py")
        self._cihaz = self._rm.open_resource(adres)
        self._yaz("*CLS")

    # ------------------------------------------------------------------
    # Alt seviye
    # ------------------------------------------------------------------
    def _yaz(self, komut: str, hata_kontrolu: bool = False) -> None:
        self._cihaz.write(komut)
        self._kaydet(komut)
        if hata_kontrolu:
            self.hatalari_kontrol_et(komut)

    def _sorgula(self, komut: str) -> str:
        yanit = self._cihaz.query(komut)
        self._kaydet(komut, yanit=yanit)
        return yanit

    def hatalari_kontrol_et(self, baglam: str = "") -> None:
        """`SYST:ERR?` ile cihaz hatasi var mi diye bakar; varsa yukseltir."""
        yanit = self._sorgula("SYST:ERR?")
        sorunlu, aciklama = self._hata_yaniti_sorunlu_mu(yanit)
        if sorunlu:
            raise GucKaynagiHatasi(
                f"{self.adres}: cihaz hatasi {aciklama!r}"
                + (f" (komut: {baglam})" if baglam else "")
            )

    # ------------------------------------------------------------------
    # Ust seviye
    # ------------------------------------------------------------------
    def baslat(self, uyum_gerilimi_V: float) -> str:
        """Uzaktan kumandaya al, uyum gerilimini yaz, akimi sifirla."""
        kimlik = self._sorgula("*IDN?").strip()
        self._yaz("SYST:REM", hata_kontrolu=True)
        # Sabit akim kipinde VOLT uyum sinirdir ve akimdan ONCE yazilir.
        self._yaz(f"VOLT {uyum_gerilimi_V}", hata_kontrolu=True)
        self._yaz("CURR 0", hata_kontrolu=True)
        return kimlik

    def akim_yaz(self, akim_A: float) -> None:
        self._yaz(f"CURR {akim_A:.4f}", hata_kontrolu=True)

    def olcumleri_oku(self) -> tuple[float, float]:
        """(gerilim_V, akim_A) olarak float dondurur."""
        gerilim = self._float_ayristir(self._sorgula("MEAS:VOLT?"), f"{self.adres} MEAS:VOLT?")
        akim = self._float_ayristir(self._sorgula("MEAS:CURR?"), f"{self.adres} MEAS:CURR?")
        return gerilim, akim

    def cikis_ac(self) -> None:
        self._yaz("OUTP ON", hata_kontrolu=True)

    def cikis_kapat(self, olculen_akim_A: float, tolerans_A: float = SIFIR_AKIM_TOLERANSI_A) -> None:
        """Cikisi kapatir. Akim sifir degilse REDDEDER (endüktif bobin).

        Esik, cihazin kendi olcum gurultusunden buyuk olmalidir; bu yuzden
        yapilandirmadaki `akim_tolerans_A` degeri kullanilir (bkz.
        `KaynakGrubu.guvenli_kapat`).
        """
        _sifir_akim_dogrula(self.adres, olculen_akim_A, tolerans_A)
        self._yaz("OUTP OFF", hata_kontrolu=True)

    def kapat(self) -> None:
        try:
            self._cihaz.close()
        finally:
            self._kaydet("(baglanti kapatildi)")


class SahteGucKaynagi(_TemelKaynak):
    """Kuru calisma ve testler icin sahte kaynak.

    Komutlari kaydeder, cihaza hicbir sey gondermez. Olculen akim, ayarlanan
    akimi kucuk bir hatayla izler; boylece oturma dogrulamasi gercekci calisir.
    """

    def __init__(
        self,
        adres: str,
        gunluk: KomutGunlugu | None = None,
        olcum_hatasi_A: float = 0.001,
        rng: np.random.Generator | None = None,
    ) -> None:
        super().__init__(adres, gunluk)
        self.ayar_akimi_A = 0.0
        self.cikis_acik = False
        self.olcum_hatasi_A = olcum_hatasi_A
        self.rng = rng if rng is not None else np.random.default_rng(0)

    def baslat(self, uyum_gerilimi_V: float) -> str:
        for komut in ("*IDN?", "SYST:REM", f"VOLT {uyum_gerilimi_V}", "CURR 0"):
            self._kaydet(komut, gonderildi=False)
        self.ayar_akimi_A = 0.0
        return f"SAHTE,IT-M3233,{self.adres},kuru"

    def akim_yaz(self, akim_A: float) -> None:
        self._kaydet(f"CURR {akim_A:.4f}", gonderildi=False)
        self.ayar_akimi_A = float(akim_A)

    def olcumleri_oku(self) -> tuple[float, float]:
        self._kaydet("MEAS:VOLT?", gonderildi=False)
        self._kaydet("MEAS:CURR?", gonderildi=False)
        if not self.cikis_acik:
            return 0.0, 0.0
        akim = self.ayar_akimi_A + float(self.rng.normal(0.0, self.olcum_hatasi_A))
        gerilim = 0.05 * akim  # bobin direnci ~50 mOhm mertebesinde
        return gerilim, akim

    def cikis_ac(self) -> None:
        self._kaydet("OUTP ON", gonderildi=False)
        self.cikis_acik = True

    def cikis_kapat(self, olculen_akim_A: float, tolerans_A: float = SIFIR_AKIM_TOLERANSI_A) -> None:
        _sifir_akim_dogrula(self.adres, olculen_akim_A, tolerans_A)
        self._kaydet("OUTP OFF", gonderildi=False)
        self.cikis_acik = False

    def kapat(self) -> None:
        self._kaydet("(baglanti kapatildi)", gonderildi=False)


class KaynakGrubu:
    """Dort kaynagi birlikte yoneten katman.

    * `rampala()`: dort akimi es zamanli adimlarla hedefe goturur, oturmayi
      `MEAS:CURR?` ile dogrular, ardindan bekleme uygular.
    * `olcumleri_oku()`: dort kanalin gerilim/akim olcumleri.
    * `acil_sifirla()`: her durumda akimlari rampa ile sifira indirir.
    """

    def __init__(
        self,
        kaynaklar: list[GucKaynagiArayuzu],
        ayar: GucKaynaklariYapilandirmasi,
        guvenlik: GuvenlikYapilandirmasi,
        gunluk: KomutGunlugu | None = None,
        bekle: Callable[[float], None] = time.sleep,
    ) -> None:
        if len(kaynaklar) != BOBIN_SAYISI:
            raise ValueError(f"{BOBIN_SAYISI} kaynak bekleniyor, {len(kaynaklar)} verildi")
        self.kaynaklar = kaynaklar
        self.ayar = ayar
        self.guvenlik = guvenlik
        self.gunluk = gunluk if gunluk is not None else KomutGunlugu()
        self.bekle = bekle
        self.ayar_akimlari_A = np.zeros(BOBIN_SAYISI, dtype=float)
        self.baslatildi = False
        self.kimlikler: list[str] = []

    # ------------------------------------------------------------------
    @classmethod
    def olustur(
        cls,
        ayar: GucKaynaklariYapilandirmasi,
        guvenlik: GuvenlikYapilandirmasi,
        canli: bool,
        gunluk: KomutGunlugu | None = None,
        bekle: Callable[[float], None] = time.sleep,
    ) -> "KaynakGrubu":
        """Kip'e gore gercek ya da sahte kaynaklarla grup kurar."""
        gunluk = gunluk if gunluk is not None else KomutGunlugu()
        kaynaklar: list[GucKaynagiArayuzu] = []
        for adres in ayar.visa_adresleri:
            if canli:
                kaynaklar.append(GucKaynagi(adres, gunluk=gunluk))
            else:
                kaynaklar.append(SahteGucKaynagi(adres, gunluk=gunluk))
        return cls(kaynaklar, ayar, guvenlik, gunluk=gunluk, bekle=bekle)

    # ------------------------------------------------------------------
    def baslat(self) -> list[str]:
        """Dort kaynagi uzaktan kumandaya alir, uyum gerilimini yazar, cikisi acar."""
        self.kimlikler = []
        for kaynak in self.kaynaklar:
            self.kimlikler.append(kaynak.baslat(self.ayar.uyum_gerilimi_V))
        for kaynak in self.kaynaklar:
            kaynak.cikis_ac()
        self.ayar_akimlari_A = np.zeros(BOBIN_SAYISI, dtype=float)
        self.baslatildi = True
        return self.kimlikler

    def olcumleri_oku(self) -> tuple[np.ndarray, np.ndarray]:
        """(gerilimler, akimlar) - her biri 4 elemanli."""
        gerilimler = np.zeros(BOBIN_SAYISI, dtype=float)
        akimlar = np.zeros(BOBIN_SAYISI, dtype=float)
        for i, kaynak in enumerate(self.kaynaklar):
            gerilimler[i], akimlar[i] = kaynak.olcumleri_oku()
        return gerilimler, akimlar

    # ------------------------------------------------------------------
    def _hedefleri_dogrula(self, hedefler: np.ndarray) -> np.ndarray:
        hedefler = np.asarray(hedefler, dtype=float)
        if hedefler.shape != (BOBIN_SAYISI,):
            raise ValueError(f"{BOBIN_SAYISI} elemanli hedef vektoru bekleniyor")
        if np.any(hedefler < 0):
            raise GuvenlikHatasi(
                f"Negatif akim istendi ({hedefler}); polarite role donanimiyla degistirilir, "
                "guc kaynaklari yalnizca pozitif akim surer"
            )
        asim = hedefler > self.guvenlik.bobin_basi_max_akim_A
        if np.any(asim):
            raise GuvenlikHatasi(
                f"Bobin basi max akim {self.guvenlik.bobin_basi_max_akim_A} A asildi: {hedefler}"
            )
        return hedefler

    def rampala(self, hedefler: np.ndarray) -> np.ndarray:
        """Dort akimi es zamanli adimlarla hedefe goturur.

        Adim sayisi en buyuk degisime gore hesaplanir; her kanal ayni adim
        sayisinda ilerledigi icin dordu ayni anda hedefe varir. Rampa sonunda
        oturma `MEAS:CURR?` ile dogrulanir, ardindan `oturma_suresi_s` beklenir.

        Olculen akimlari dondurur.
        """
        if not self.baslatildi:
            raise GucKaynagiHatasi("Kaynak grubu baslatilmadi (baslat() cagrilmali)")
        hedefler = self._hedefleri_dogrula(hedefler)
        baslangic = self.ayar_akimlari_A.copy()
        en_buyuk_degisim = float(np.max(np.abs(hedefler - baslangic)))

        if en_buyuk_degisim > 0:
            adim_basi_A = self.ayar.rampa_hizi_A_s * self.ayar.rampa_adim_suresi_s
            adim_sayisi = max(1, math.ceil(en_buyuk_degisim / adim_basi_A))
            for adim in range(1, adim_sayisi + 1):
                oran = adim / adim_sayisi
                ara = baslangic + (hedefler - baslangic) * oran
                for i, kaynak in enumerate(self.kaynaklar):
                    kaynak.akim_yaz(float(ara[i]))
                self.ayar_akimlari_A = ara
                self.bekle(self.ayar.rampa_adim_suresi_s)

        self.ayar_akimlari_A = hedefler.copy()
        olculen = self._oturmayi_dogrula(hedefler)
        self.bekle(self.ayar.oturma_suresi_s)
        return olculen

    def _oturmayi_dogrula(self, hedefler: np.ndarray) -> np.ndarray:
        """`MEAS:CURR?` ile akimlarin hedefe tolerans icinde oturdugunu dogrular."""
        son_akimlar = np.zeros(BOBIN_SAYISI, dtype=float)
        for deneme in range(1, self.ayar.oturma_dogrulama_denemesi + 1):
            _, son_akimlar = self.olcumleri_oku()
            sapma = np.abs(son_akimlar - hedefler)
            if np.all(sapma <= self.ayar.akim_tolerans_A):
                return son_akimlar
            if deneme < self.ayar.oturma_dogrulama_denemesi:
                self.bekle(self.ayar.rampa_adim_suresi_s)
        sapma = np.abs(son_akimlar - hedefler)
        raise GucKaynagiHatasi(
            "Akimlar hedefe oturmadi: hedef="
            + np.array2string(hedefler, precision=3)
            + " olculen="
            + np.array2string(son_akimlar, precision=3)
            + f" sapma={np.array2string(sapma, precision=3)} "
            + f"(tolerans {self.ayar.akim_tolerans_A} A)"
        )

    # ------------------------------------------------------------------
    def sifira_rampala(self) -> np.ndarray:
        """Dort akimi rampa ile sifira indirir (cikis kapatilmaz)."""
        return self.rampala(np.zeros(BOBIN_SAYISI, dtype=float))

    def acil_sifirla(self) -> None:
        """Her durumda akimlari sifira indirmeyi dener; hatalari yutar ama kaydeder.

        Beklenmeyen hata, iletisim kopmasi, pencerenin kapatilmasi ya da
        kullanici kesintisinde cagrilir.
        """
        try:
            self.sifira_rampala()
        except Exception as hata:  # pragma: no cover - acil durum yolu
            self.gunluk.ekle(
                KomutKaydi(
                    zaman=time.time(),
                    adres="(grup)",
                    komut=f"ACIL: sifira rampalama basarisiz: {hata}",
                    gonderildi=False,
                )
            )
            # Yine de kanal kanal denenir.
            for kaynak in self.kaynaklar:
                try:
                    kaynak.akim_yaz(0.0)
                except Exception:  # pragma: no cover
                    pass

    def guvenli_kapat(self) -> None:
        """Akimlari sifirlar, cikislari kapatir, baglantilari kapatir."""
        try:
            self.sifira_rampala()
        except Exception:  # pragma: no cover - acil durum yolu
            self.acil_sifirla()
        _, akimlar = self.olcumleri_oku()
        for i, kaynak in enumerate(self.kaynaklar):
            try:
                kaynak.cikis_kapat(float(akimlar[i]), self.ayar.akim_tolerans_A)
            except GuvenlikHatasi as hata:
                self.gunluk.ekle(
                    KomutKaydi(
                        zaman=time.time(),
                        adres=kaynak.adres,
                        komut=f"UYARI: cikis kapatilamadi: {hata}",
                        gonderildi=False,
                    )
                )
        for kaynak in self.kaynaklar:
            kaynak.kapat()
        self.baslatildi = False
