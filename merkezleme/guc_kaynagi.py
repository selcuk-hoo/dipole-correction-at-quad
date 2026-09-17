"""Güç kaynağı kontrolü (ITECH IT-M3233, sabit akım kipi).

`eski/guc_kaynagi_orijinal.py` dosyasındaki sınıf temel alınmıştır; kullanılan
SCPI komut kümesi AYNIDIR ve genişletilmemiştir:

    *CLS, *IDN?, SYST:REM, VOLT, CURR, SYST:ERR?, OUTP ON/OFF,
    MEAS:VOLT?, MEAS:CURR?

Eklenenler
-----------
* `olcumleri_oku()` float döndürür, ayrıştırma hatalarını yakalar.
* Her yazma işleminden sonra `SYST:ERR?` kontrol edilir; hata varsa işlem
  durdurulur ve kaydedilir.
* Sabit akım kipinde `VOLT` bir uyum (compliance) sınırdır; yapılandırmadan
  okunur ve akım ayarından ÖNCE yazılır.
* Akımlar asla tek adımda değiştirilmez: yazılımda rampa (A/s). Rampa sonunda
  `MEAS:CURR?` ile hedefe tolerans içinde oturduğu doğrulanır, ardından
  yapılandırılabilir bir bekleme uygulanır.
* Bobin endüktif olduğu için (~6.5 mH, 10 A) akım sıfır değilken `OUTP OFF`
  KULLANILMAZ; önce rampa ile sıfıra inilir.
* Dört kaynak `KaynakGrubu` ile birlikte yönetilir: eş zamanlı adımlarla
  rampalama, hepsini okuma, acil durumda hepsini rampa ile sıfırlama.
* Varsayılan kip KURU ÇALIŞMA: komutlar kaydedilir ama gönderilmez. Gerçek
  donanım için açık bir `--canli` bayrağı gerekir.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Callable, Protocol

import numpy as np

from .yapilandirma import BOBIN_SAYISI, GucKaynaklariYapilandirmasi, GuvenlikYapilandirmasi


# `cikis_kapat` için varsayılan "akım sıfır sayılır" eşiği. Gerçekte
# `KaynakGrubu.guvenli_kapat`, yapılandırmadaki akim_tolerans_A değerini geçer;
# bu sabit yalnızca doğrudan çağrılar için bir taban sağlar.
SIFIR_AKIM_TOLERANSI_A = 0.02


def _sifir_akim_dogrula(adres: str, olculen_akim_A: float, tolerans_A: float) -> None:
    """Akım sıfır sayılacak kadar küçük mü? Değilse GuvenlikHatasi yükseltir."""
    if abs(olculen_akim_A) > tolerans_A:
        raise GuvenlikHatasi(
            f"{adres}: akım {olculen_akim_A:.3f} A iken OUTP OFF kullanılamaz "
            f"(eşik {tolerans_A:.3f} A); önce rampa ile sıfıra inilmelidir"
        )


class GucKaynagiHatasi(RuntimeError):
    """Güç kaynağı iletişimi ya da cihaz hatası."""


class GuvenlikHatasi(RuntimeError):
    """Güvenlik sınırı aşıldı; işlem uygulanmadı."""


@dataclass
class KomutKaydi:
    """Tek bir SCPI işlemi (kuru çalışmada da kaydedilir)."""

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
    """SCPI komut günlüğü. kayit.py bunu düz metin olarak diske yazar."""

    kayitlar: list[KomutKaydi] = field(default_factory=list)

    def ekle(self, kayit: KomutKaydi) -> None:
        self.kayitlar.append(kayit)

    def satirlar(self) -> list[str]:
        return [k.satir() for k in self.kayitlar]


class GucKaynagiArayuzu(Protocol):
    """Gerçek ve sahte kaynakların ortak arayüzü."""

    adres: str

    def baslat(self, uyum_gerilimi_V: float) -> str: ...
    def akim_yaz(self, akim_A: float) -> None: ...
    def olcumleri_oku(self) -> tuple[float, float]: ...
    def cikis_ac(self) -> None: ...
    def cikis_kapat(self, olculen_akim_A: float, tolerans_A: float = ...) -> None: ...
    def kapat(self) -> None: ...


class _TemelKaynak:
    """Gerçek ve sahte kaynağın paylaştığı günlük/ayrıştırma mantığı."""

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
        """Cihaz yanıtını float'a çevirir; başarısız olursa açıklayıcı hata verir."""
        try:
            return float(str(metin).strip().split(",")[0])
        except (TypeError, ValueError) as hata:
            raise GucKaynagiHatasi(f"{ne} yanıtı sayıya çevrilemedi: {metin!r}") from hata

    @staticmethod
    def _hata_yaniti_sorunlu_mu(yanit: str) -> tuple[bool, str]:
        """`SYST:ERR?` yanıtını yorumlar. (sorunlu_mu, açıklama)"""
        metin = str(yanit).strip()
        if not metin:
            return False, ""
        ilk = metin.split(",")[0].strip()
        try:
            kod = int(float(ilk))
        except ValueError:
            # Yorumlanamayan yanıt: hata saymayız ama günlükte durur.
            return False, metin
        return kod != 0, metin


class GucKaynagi(_TemelKaynak):
    """Tek bir ITECH IT-M3233 (pyvisa, `@py` backend, seri port)."""

    def __init__(self, adres: str, gunluk: KomutGunlugu | None = None) -> None:
        super().__init__(adres, gunluk)
        # pyvisa yalnızca canlı kipte gerekir; kuru çalışma ve testler
        # pyvisa kurulu olmadan da çalışır.
        try:
            import pyvisa
        except ImportError as hata:  # pragma: no cover - ortama bagli
            raise GucKaynagiHatasi(
                "pyvisa kurulu değil; canlı kip için 'pip install pyvisa pyvisa-py' gerekir"
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
        """`SYST:ERR?` ile cihaz hatası var mı diye bakar; varsa yükseltir."""
        yanit = self._sorgula("SYST:ERR?")
        sorunlu, aciklama = self._hata_yaniti_sorunlu_mu(yanit)
        if sorunlu:
            raise GucKaynagiHatasi(
                f"{self.adres}: cihaz hatası {aciklama!r}"
                + (f" (komut: {baglam})" if baglam else "")
            )

    # ------------------------------------------------------------------
    # Üst seviye
    # ------------------------------------------------------------------
    def baslat(self, uyum_gerilimi_V: float) -> str:
        """Uzaktan kumandaya al, uyum gerilimini yaz, akımı sıfırla."""
        kimlik = self._sorgula("*IDN?").strip()
        self._yaz("SYST:REM", hata_kontrolu=True)
        # Sabit akım kipinde VOLT uyum sınırıdır ve akımdan ÖNCE yazılır.
        self._yaz(f"VOLT {uyum_gerilimi_V}", hata_kontrolu=True)
        self._yaz("CURR 0", hata_kontrolu=True)
        return kimlik

    def akim_yaz(self, akim_A: float) -> None:
        self._yaz(f"CURR {akim_A:.4f}", hata_kontrolu=True)

    def olcumleri_oku(self) -> tuple[float, float]:
        """(gerilim_V, akim_A) olarak float döndürür."""
        gerilim = self._float_ayristir(self._sorgula("MEAS:VOLT?"), f"{self.adres} MEAS:VOLT?")
        akim = self._float_ayristir(self._sorgula("MEAS:CURR?"), f"{self.adres} MEAS:CURR?")
        return gerilim, akim

    def cikis_ac(self) -> None:
        self._yaz("OUTP ON", hata_kontrolu=True)

    def cikis_kapat(self, olculen_akim_A: float, tolerans_A: float = SIFIR_AKIM_TOLERANSI_A) -> None:
        """Çıkışı kapatır. Akım sıfır değilse REDDEDER (endüktif bobin).

        Eşik, cihazın kendi ölçüm gürültüsünden büyük olmalıdır; bu yüzden
        yapılandırmadaki `akim_tolerans_A` değeri kullanılır (bkz.
        `KaynakGrubu.guvenli_kapat`).
        """
        _sifir_akim_dogrula(self.adres, olculen_akim_A, tolerans_A)
        self._yaz("OUTP OFF", hata_kontrolu=True)

    def kapat(self) -> None:
        try:
            self._cihaz.close()
        finally:
            self._kaydet("(bağlantı kapatıldı)")


class SahteGucKaynagi(_TemelKaynak):
    """Kuru çalışma ve testler için sahte kaynak.

    Komutları kaydeder, cihaza hiçbir şey göndermez. Ölçülen akım, ayarlanan
    akımı küçük bir hatayla izler; böylece oturma doğrulaması gerçekçi çalışır.
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
        self._kaydet("(bağlantı kapatıldı)", gonderildi=False)


class KaynakGrubu:
    """Dört kaynağı birlikte yöneten katman.

    * `rampala()`: dört akımı eş zamanlı adımlarla hedefe götürür, oturmayı
      `MEAS:CURR?` ile doğrular, ardından bekleme uygular.
    * `olcumleri_oku()`: dört kanalın gerilim/akım ölçümleri.
    * `acil_sifirla()`: her durumda akımları rampa ile sıfıra indirir.
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
        """Kip'e göre gerçek ya da sahte kaynaklarla grup kurar."""
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
        """Dört kaynağı uzaktan kumandaya alır, uyum gerilimini yazar, çıkışı açar."""
        self.kimlikler = []
        for kaynak in self.kaynaklar:
            self.kimlikler.append(kaynak.baslat(self.ayar.uyum_gerilimi_V))
        for kaynak in self.kaynaklar:
            kaynak.cikis_ac()
        self.ayar_akimlari_A = np.zeros(BOBIN_SAYISI, dtype=float)
        self.baslatildi = True
        return self.kimlikler

    def olcumleri_oku(self) -> tuple[np.ndarray, np.ndarray]:
        """(gerilimler, akımlar) - her biri 4 elemanlı."""
        gerilimler = np.zeros(BOBIN_SAYISI, dtype=float)
        akimlar = np.zeros(BOBIN_SAYISI, dtype=float)
        for i, kaynak in enumerate(self.kaynaklar):
            gerilimler[i], akimlar[i] = kaynak.olcumleri_oku()
        return gerilimler, akimlar

    # ------------------------------------------------------------------
    def _hedefleri_dogrula(self, hedefler: np.ndarray) -> np.ndarray:
        hedefler = np.asarray(hedefler, dtype=float)
        if hedefler.shape != (BOBIN_SAYISI,):
            raise ValueError(f"{BOBIN_SAYISI} elemanlı hedef vektörü bekleniyor")
        if np.any(hedefler < 0):
            raise GuvenlikHatasi(
                f"Negatif akım istendi ({hedefler}); polarite röle donanımıyla değiştirilir, "
                "güç kaynakları yalnızca pozitif akım sürer"
            )
        asim = hedefler > self.guvenlik.bobin_basi_max_akim_A
        if np.any(asim):
            raise GuvenlikHatasi(
                f"Bobin başı max akım {self.guvenlik.bobin_basi_max_akim_A} A aşıldı: {hedefler}"
            )
        return hedefler

    def rampala(self, hedefler: np.ndarray) -> np.ndarray:
        """Dört akımı eş zamanlı adımlarla hedefe götürür.

        Adım sayısı en büyük değişime göre hesaplanır; her kanal aynı adım
        sayısında ilerlediği için dördü aynı anda hedefe varır. Rampa sonunda
        oturma `MEAS:CURR?` ile doğrulanır, ardından `oturma_suresi_s` beklenir.

        Ölçülen akımları döndürür.
        """
        if not self.baslatildi:
            raise GucKaynagiHatasi("Kaynak grubu başlatılmadı (baslat() çağrılmalı)")
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
        """`MEAS:CURR?` ile akımların hedefe tolerans içinde oturduğunu doğrular."""
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
            "Akımlar hedefe oturmadı: hedef="
            + np.array2string(hedefler, precision=3)
            + " ölçülen="
            + np.array2string(son_akimlar, precision=3)
            + f" sapma={np.array2string(sapma, precision=3)} "
            + f"(tolerans {self.ayar.akim_tolerans_A} A)"
        )

    # ------------------------------------------------------------------
    def sifira_rampala(self) -> np.ndarray:
        """Dört akımı rampa ile sıfıra indirir (çıkış kapatılmaz)."""
        return self.rampala(np.zeros(BOBIN_SAYISI, dtype=float))

    def acil_sifirla(self) -> None:
        """Her durumda akımları sıfıra indirmeyi dener; hataları yutar ama kaydeder.

        Beklenmeyen hata, iletişim kopması, pencerenin kapatılması ya da
        kullanıcı kesintisinde çağrılır.
        """
        try:
            self.sifira_rampala()
        except Exception as hata:  # pragma: no cover - acil durum yolu
            self.gunluk.ekle(
                KomutKaydi(
                    zaman=time.time(),
                    adres="(grup)",
                    komut=f"ACİL: sıfıra rampalama başarısız: {hata}",
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
        """Akımları sıfırlar, çıkışları kapatır, bağlantıları kapatır."""
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
                        komut=f"UYARI: çıkış kapatılamadı: {hata}",
                        gonderildi=False,
                    )
                )
        for kaynak in self.kaynaklar:
            kaynak.kapat()
        self.baslatildi = False
