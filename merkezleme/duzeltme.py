"""Düzeltme adımı: pseudo-inverse çözümü, güvenlik sınırları, yakınsama.

    dI = alpha * pinv(R) * (y_hedef - y)

`pinv` Moore-Penrose pseudo-inverse'tir, yani minimum normlu çözümü verir.
Tikhonov regülarizasyonu EKLENMEZ: R 3x4 ve rank 3 olduğu için hedef zaten
tam olarak erişilebilir; regülarizasyon yalnızca yolu yavaşlatır, varış
noktasını değiştirmez.

Sıfır uzayı ve monopol
-----------------------
R'nin sıfır uzayı tam olarak M (monopol) yönüdür: işaretli akımda üniform bir
değişim, racetrack bobinlerde net akım üretmediği için dipole de gradyene de
katkısızdır. `pinv` minimum normlu çözümü seçtiği için bu yönde bileşen
üretmez; buna ek olarak her adımdan sonra (I - I_nominal) farkının monopol
bileşeni açıkça atılır, böylece ölçüm gürültüsü sıfır uzayında birikmez.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from .harmonikler import KontrolVektoru
from .modlar import MOD_SIRASI, ModBazi
from .yapilandirma import BOBIN_SAYISI, DuzeltmeYapilandirmasi, GuvenlikYapilandirmasi

# Hedef her zaman sifirdir: merkez sifir, gradyen nominal (g = 0).
Y_HEDEF = np.zeros(3, dtype=float)


@dataclass(frozen=True)
class GuvenlikDegerlendirmesi:
    guvenli: bool
    ihlaller: tuple[str, ...] = ()

    def metin(self) -> str:
        if self.guvenli:
            return "Güvenlik sınırları tamam."
        return "GÜVENLİK SINIRI AŞILDI:\n" + "\n".join(f"  - {i}" for i in self.ihlaller)


@dataclass(frozen=True)
class DuzeltmeOnerisi:
    """Uygulanmadan önce kullanıcıya gösterilecek düzeltme önerisi."""

    mevcut_akimlar_A: np.ndarray
    yeni_akimlar_A: np.ndarray
    olculen_y: KontrolVektoru
    beklenen_y: KontrolVektoru
    mod_genlikleri: dict[str, float]
    monopol_cikarilan: float
    guvenlik: GuvenlikDegerlendirmesi

    @property
    def delta_akimlar_A(self) -> np.ndarray:
        return self.yeni_akimlar_A - self.mevcut_akimlar_A

    @property
    def beklenen_merkez_degisimi_m(self) -> float:
        return math.hypot(
            self.beklenen_y.x_c - self.olculen_y.x_c, self.beklenen_y.y_c - self.olculen_y.y_c
        )

    def asimetriler(self, nominal_akim_A: float) -> np.ndarray:
        """Yeni akımların nominale göre bağıl asimetrisi."""
        return (self.yeni_akimlar_A - nominal_akim_A) / nominal_akim_A

    def ozet_metni(self, nominal_akim_A: float) -> str:
        asimetri = self.asimetriler(nominal_akim_A)
        satirlar = ["Bobin   ayar (A)    yeni (A)     fark (mA)   nominale göre"]
        for i in range(BOBIN_SAYISI):
            satirlar.append(
                f"  I{i + 1}   {self.mevcut_akimlar_A[i]:8.4f}   {self.yeni_akimlar_A[i]:8.4f}   "
                f"{self.delta_akimlar_A[i] * 1e3:+9.2f}   {asimetri[i] * 100:+7.3f} %"
            )
        satirlar.append("")
        satirlar.append(
            "Mod genlikleri: "
            + "  ".join(f"{m}={self.mod_genlikleri.get(m, 0.0) * 100:+.4f}%" for m in MOD_SIRASI)
        )
        satirlar.append(f"Ölçülen:  {self.olculen_y}")
        satirlar.append(f"Beklenen: {self.beklenen_y}")
        satirlar.append(
            f"Beklenen merkez değişimi: {self.beklenen_merkez_degisimi_m * 1e6:.2f} um"
        )
        if abs(self.monopol_cikarilan) > 0:
            satirlar.append(f"Atılan monopol bileşeni: {self.monopol_cikarilan * 100:+.5f} %")
        satirlar.append(self.guvenlik.metin())
        return "\n".join(satirlar)


def _guvenligi_degerlendir(
    mevcut_akimlar_A: np.ndarray,
    yeni_akimlar_A: np.ndarray,
    nominal_akim_A: float,
    guvenlik: GuvenlikYapilandirmasi,
) -> GuvenlikDegerlendirmesi:
    ihlaller: list[str] = []

    asim = yeni_akimlar_A > guvenlik.bobin_basi_max_akim_A
    for i in np.flatnonzero(asim):
        ihlaller.append(
            f"I{i + 1} = {yeni_akimlar_A[i]:.3f} A, bobin başı max "
            f"{guvenlik.bobin_basi_max_akim_A:.3f} A değerini aşıyor"
        )
    for i in np.flatnonzero(yeni_akimlar_A < 0):
        ihlaller.append(f"I{i + 1} = {yeni_akimlar_A[i]:.3f} A negatif olamaz")

    adim = np.abs(yeni_akimlar_A - mevcut_akimlar_A) / nominal_akim_A
    for i in np.flatnonzero(adim > guvenlik.adim_basi_max_bagil_degisim):
        ihlaller.append(
            f"I{i + 1} adım başı bağıl değişim {adim[i] * 100:.3f} %, sınır "
            f"{guvenlik.adim_basi_max_bagil_degisim * 100:.3f} %"
        )

    asimetri = np.abs(yeni_akimlar_A - nominal_akim_A) / nominal_akim_A
    for i in np.flatnonzero(asimetri > guvenlik.nominale_gore_max_asimetri):
        ihlaller.append(
            f"I{i + 1} nominale göre asimetri {asimetri[i] * 100:.3f} %, sınır "
            f"{guvenlik.nominale_gore_max_asimetri * 100:.3f} %"
        )

    return GuvenlikDegerlendirmesi(guvenli=not ihlaller, ihlaller=tuple(ihlaller))


def duzeltme_hesapla(
    R: np.ndarray,
    olculen_y: KontrolVektoru,
    mevcut_akimlar_A: np.ndarray,
    mod_bazi: ModBazi,
    ayar: DuzeltmeYapilandirmasi,
    guvenlik: GuvenlikYapilandirmasi,
) -> DuzeltmeOnerisi:
    """Bir düzeltme adımı önerir; akımları UYGULAMAZ."""
    R = np.asarray(R, dtype=float)
    mevcut_akimlar_A = np.asarray(mevcut_akimlar_A, dtype=float)
    if R.shape != (3, BOBIN_SAYISI):
        raise ValueError(f"R 3x{BOBIN_SAYISI} olmalıdır, {R.shape} verildi")

    hata = Y_HEDEF - olculen_y.dizi()
    delta_bagil = ayar.alpha * (np.linalg.pinv(R) @ hata)

    mevcut_bagil = mod_bazi.bagil_sapma(mevcut_akimlar_A)
    yeni_bagil = mevcut_bagil + delta_bagil

    monopol_cikarilan = 0.0
    if ayar.monopol_cikar:
        monopol_cikarilan = mod_bazi.monopol_bileseni(yeni_bagil)
        yeni_bagil = mod_bazi.monopol_cikar(yeni_bagil)

    yeni_akimlar = mod_bazi.akimlar(yeni_bagil)
    uygulanan_delta = yeni_bagil - mevcut_bagil
    beklenen = olculen_y.dizi() + R @ uygulanan_delta

    return DuzeltmeOnerisi(
        mevcut_akimlar_A=mevcut_akimlar_A,
        yeni_akimlar_A=yeni_akimlar,
        olculen_y=olculen_y,
        beklenen_y=KontrolVektoru(*(float(v) for v in beklenen)),
        mod_genlikleri=mod_bazi.mod_genlikleri(yeni_bagil),
        monopol_cikarilan=float(monopol_cikarilan),
        guvenlik=_guvenligi_degerlendir(
            mevcut_akimlar_A, yeni_akimlar, mod_bazi.miknatis.nominal_akim_A, guvenlik
        ),
    )


# ---------------------------------------------------------------------------
# Yakınsama
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class YakinsamaDurumu:
    yakinsadi: bool
    merkez_tamam: bool
    g_tamam: bool
    olculen_y: KontrolVektoru

    def metin(self, ayar: DuzeltmeYapilandirmasi) -> str:
        merkez = "TAMAM" if self.merkez_tamam else "devam"
        gradyen = "TAMAM" if self.g_tamam else "devam"
        return (
            f"|x_c| = {abs(self.olculen_y.x_c) * 1e6:.2f} um, "
            f"|y_c| = {abs(self.olculen_y.y_c) * 1e6:.2f} um "
            f"(tolerans {ayar.merkez_toleransi_um:.2f} um) -> {merkez}; "
            f"|g| = {abs(self.olculen_y.g):.5f} (tolerans {ayar.g_toleransi:.5f}) -> {gradyen}"
        )


def yakinsama_durumu(olculen_y: KontrolVektoru, ayar: DuzeltmeYapilandirmasi) -> YakinsamaDurumu:
    """|x_c|, |y_c| ve |g| kendi toleranslarının altında mı?"""
    merkez_tamam = (
        abs(olculen_y.x_c) < ayar.merkez_toleransi_m and abs(olculen_y.y_c) < ayar.merkez_toleransi_m
    )
    g_tamam = abs(olculen_y.g) < ayar.g_toleransi
    return YakinsamaDurumu(
        yakinsadi=merkez_tamam and g_tamam,
        merkez_tamam=merkez_tamam,
        g_tamam=g_tamam,
        olculen_y=olculen_y,
    )


# ---------------------------------------------------------------------------
# Tekrarlanabilirlik
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class TekrarlanabilirlikSonucu:
    """Sabit akımlarda N tekrar ölçümün saçılımı."""

    n: int
    x_c_sigma_m: float
    y_c_sigma_m: float
    g_sigma: float
    merkez_sigma_m: float
    tolerans_yeterli_mi: bool
    uyarilar: tuple[str, ...] = field(default=())

    def ozet_metni(self) -> str:
        satirlar = [
            f"Tekrarlanabilirlik ({self.n} ölçüm):",
            f"  sigma(x_c) = {self.x_c_sigma_m * 1e6:.3f} um",
            f"  sigma(y_c) = {self.y_c_sigma_m * 1e6:.3f} um",
            f"  sigma(g)   = {self.g_sigma:.6f}",
        ]
        satirlar.extend(f"  UYARI: {u}" for u in self.uyarilar)
        return "\n".join(satirlar)


def tekrarlanabilirligi_degerlendir(
    olcumler: list[KontrolVektoru], ayar: DuzeltmeYapilandirmasi
) -> TekrarlanabilirlikSonucu:
    """Sabit akımlardaki tekrar ölçümlerden saçılımı ve tolerans yeterliliğini bulur.

    Tolerans, ölçülen tekrarlanabilirliğin `tolerans_tekrarlanabilirlik_carpani`
    katından küçük olmamalıdır; küçükse uyarır.
    """
    if len(olcumler) < 2:
        raise ValueError("Tekrarlanabilirlik için en az iki ölçüm gerekir")
    diziler = np.array([y.dizi() for y in olcumler], dtype=float)
    x_sigma, y_sigma, g_sigma = (float(s) for s in diziler.std(axis=0, ddof=1))
    merkez_sigma = math.hypot(x_sigma, y_sigma)

    uyarilar: list[str] = []
    carpan = ayar.tolerans_tekrarlanabilirlik_carpani
    gereken_merkez_um = carpan * merkez_sigma * 1e6
    if ayar.merkez_toleransi_um < gereken_merkez_um:
        uyarilar.append(
            f"Merkez toleransı {ayar.merkez_toleransi_um:.2f} um çok sıkı; ölçülen "
            f"tekrarlanabilirlik {merkez_sigma * 1e6:.2f} um için en az "
            f"{gereken_merkez_um:.2f} um olmalıdır"
        )
    gereken_g = carpan * g_sigma
    if ayar.g_toleransi < gereken_g:
        uyarilar.append(
            f"g toleransı {ayar.g_toleransi:.5f} çok sıkı; ölçülen saçılım "
            f"{g_sigma:.5f} için en az {gereken_g:.5f} olmalıdır"
        )

    return TekrarlanabilirlikSonucu(
        n=len(olcumler),
        x_c_sigma_m=x_sigma,
        y_c_sigma_m=y_sigma,
        g_sigma=g_sigma,
        merkez_sigma_m=merkez_sigma,
        tolerans_yeterli_mi=not uyarilar,
        uyarilar=tuple(uyarilar),
    )


# ---------------------------------------------------------------------------
# Yazım hatası doğrulaması (kalibrasyon varken)
# ---------------------------------------------------------------------------
def beklenen_y(
    R: np.ndarray, referans_y: KontrolVektoru, bagil_akim_degisimi: np.ndarray
) -> KontrolVektoru:
    """Kalibrasyondan beklenen y: y_beklenen = y_referans + R * dx."""
    tahmin = referans_y.dizi() + np.asarray(R, dtype=float) @ np.asarray(
        bagil_akim_degisimi, dtype=float
    )
    return KontrolVektoru(*(float(v) for v in tahmin))
