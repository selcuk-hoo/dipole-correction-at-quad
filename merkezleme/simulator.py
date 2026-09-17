"""Miknatisin 2 boyutlu cizgi akimi simulatoru.

Donanimda kullanmadan once butun akisi (kalibrasyon + duzeltme + arayuz)
donanimsiz ve elle girissiz sinamak icindir.

Model
-----
Her bobin bir racetrack olarak modellenir: kutup ekseni etrafinda theta +/- alpha
acilarinda, a yaricapinda IKI iletken demeti. Racetrack kapali bir ilmek oldugu
icin iki demet ZIT yonlu akim tasir (biri gidis, biri donus).

z_0 konumundaki bir cizgi akimi I icin (akim +z yonunde):

    B_y + i*B_x = mu0 * I / (2*pi*(z - z_0))

|z| < |z_0| bolgesinde multipol acilimi:

    C_n = -mu0 * I * r_ref^(n-1) / (2*pi * z_0^n)

Butun iletkenler toplanir. Miknatis ofseti d ve roll acisi rho, iletken
konumlarina uygulanir:  z_j -> z_j * exp(i*rho) + d. Boylece mekanik ofset,
olcumde dogal olarak feed-down dipolu olarak gorunur.

Onemli sonuc (analitik): kosegen yerlesimde (45/135/225/315) ve nominal
alternatif polaritede, racetrack cifti yuzunden ortaya cikan ek i carpani
sayesinde nominal desen NORMAL kuadrupol verir; H modu x_c'yi, V modu y_c'yi
hareket ettirir ve

    R_eff = a * sqrt(2) / (4 * cos(alpha))

olur (a = 100 mm, alpha = 30 derece icin 40.8 mm). M modu (isaretli akimda
uniform) racetrack bobinlerde net akim uretmedigi icin hem dipole hem gradyene
tam olarak katkisizdir.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from .harmonikler import HarmonikOlcumu
from .yapilandirma import (
    BOBIN_SAYISI,
    HarmoniklerYapilandirmasi,
    MiknatisYapilandirmasi,
    SimulatorYapilandirmasi,
)

MU0_2PI = 2.0e-7  # mu0 / (2*pi)  [T*m/A]

# Girilen/raporlanan birimin Tesla'dan cevrim katsayisi
_TESLADAN_KATSAYI: dict[str, float] = {"T": 1.0, "mT": 1e3}


@dataclass(frozen=True)
class Iletken:
    """Tek bir iletken demeti."""

    konum: complex  # metre (olcum cercevesi merkezine gore)
    sarim: float  # isaretli sarim sayisi (gidis +, donus -)
    bobin: int  # 0..3


class Simulator:
    """Dort bobinli air-core kuadrupolun 2D modeli.

    `ofset_m`, `roll_rad` ve `arka_plan_T` calisma aninda degistirilebilir;
    testler rastgele ofsetler vermek icin bunlari kullanir.
    """

    def __init__(
        self,
        ayar: SimulatorYapilandirmasi,
        miknatis: MiknatisYapilandirmasi,
        harmonikler_ayari: HarmoniklerYapilandirmasi,
        tohum: int | None = None,
    ) -> None:
        self.ayar = ayar
        self.miknatis = miknatis
        self.harmonikler_ayari = harmonikler_ayari
        self.rng = np.random.default_rng(ayar.tohum if tohum is None else tohum)

        # Calisma aninda degistirilebilen fiziksel durum
        self.ofset_m: complex = complex(
            ayar.miknatis_ofseti_mm[0] * 1e-3, ayar.miknatis_ofseti_mm[1] * 1e-3
        )
        self.roll_rad: float = ayar.roll_mrad * 1e-3
        # Uniform arka plan: C_1 uzerine binen B_y + i*B_x
        self.arka_plan_T: complex = complex(ayar.arka_plan_T[0], ayar.arka_plan_T[1])

    # ------------------------------------------------------------------
    # Geometri
    # ------------------------------------------------------------------
    def iletkenler(self) -> list[Iletken]:
        """Roll ve ofset uygulanmis iletken demetleri (bobin basina iki tane)."""
        alpha = self.ayar.demet_yari_acisi_rad
        donus = complex(math.cos(self.roll_rad), math.sin(self.roll_rad))
        sonuc: list[Iletken] = []
        for i in range(BOBIN_SAYISI):
            aci = self.miknatis.bobin_acilari_rad[i] + self.ayar.yerlesim_hatasi_acisal_mrad[i] * 1e-3
            yaricap = self.ayar.bobin_yaricapi_m + self.ayar.yerlesim_hatasi_radyal_mm[i] * 1e-3
            sarim = self.ayar.sarim_sayisi * (1.0 + self.ayar.sarim_hatasi_bagil[i])
            for isaret, demet_acisi in ((+1.0, aci + alpha), (-1.0, aci - alpha)):
                konum = yaricap * complex(math.cos(demet_acisi), math.sin(demet_acisi))
                sonuc.append(
                    Iletken(konum=konum * donus + self.ofset_m, sarim=isaret * sarim, bobin=i)
                )
        return sonuc

    # ------------------------------------------------------------------
    # Alan harmonikleri
    # ------------------------------------------------------------------
    def harmonik_ham_T(self, akimlar: np.ndarray, n: int) -> complex:
        """C_n (Tesla), gurultu/arka plan/cerceve donusu UYGULANMADAN.

        Isaretli akim kullanilir: fiziksel genlik x nominal polarite.
        """
        akimlar = np.asarray(akimlar, dtype=float)
        if akimlar.shape != (BOBIN_SAYISI,):
            raise ValueError(f"{BOBIN_SAYISI} elemanli akim vektoru bekleniyor")
        polarite = np.array(self.miknatis.nominal_polarite, dtype=float)
        r_ref = self.harmonikler_ayari.r_ref_m

        toplam = 0j
        for iletken in self.iletkenler():
            akim = akimlar[iletken.bobin] * polarite[iletken.bobin] * iletken.sarim
            toplam += akim / iletken.konum**n
        return -MU0_2PI * r_ref ** (n - 1) * toplam

    def gradyen_T_m(self, akimlar: np.ndarray) -> float:
        """Gercek gradyen G = B_2 / r_ref (Tesla/m), gurultusuz."""
        c2 = self.harmonik_ham_T(akimlar, 2)
        return c2.real / self.harmonikler_ayari.r_ref_m

    def gercek_merkez_m(self, akimlar: np.ndarray) -> complex:
        """Gurultusuz, arka plansiz gercek manyetik merkez (metre).

        Testlerde "olculen merkez" ile karsilastirma referansi olarak kullanilir.
        """
        c1 = self.harmonik_ham_T(akimlar, 1)
        c2 = self.harmonik_ham_T(akimlar, 2)
        return -self.harmonikler_ayari.r_ref_m * c1 / c2

    # ------------------------------------------------------------------
    # Olcum (elle girisle ayni bicimde)
    # ------------------------------------------------------------------
    def olc(
        self, akimlar: np.ndarray, zaman: float = 0.0, gurultu: bool = True
    ) -> HarmonikOlcumu:
        """Rotating coil olcumunu taklit eder.

        Donen `HarmonikOlcumu`, elle girisle birebir ayni yapidadir: yapilandirilan
        birimde C_n bilesenleri (T, mT ya da normalize units) ve "units" biciminde
        gereken mutlak gradyen.
        """
        n_listesi = self.harmonikler_ayari.tum_harmonikler
        ham: dict[int, complex] = {n: self.harmonik_ham_T(akimlar, n) for n in n_listesi}

        # Uniform arka plan yalnizca dipole biner (zamanla yavas surukleniyor).
        ham[1] = ham[1] + self.arka_plan_T * (1.0 + self.ayar.arka_plan_surukleme_T_s * zaman)

        # Olcum gurultusu ve yavas suruklenme.
        # Olcek SABITTIR: nominal ana harmonik |C_2| = G_nominal * r_ref.
        # Anlik |C_2| kullanilmaz; cunku arka plan olcumunde akimlar sifir
        # oldugundan |C_2| ~ 0 olur ve gurultu olcegi anlamsizlasir (gercek
        # olcum zincirinin gurultusu de calisma noktasindan bagimsizdir).
        olcek = self.miknatis.nominal_gradyen_T_m * self.harmonikler_ayari.r_ref_m
        if gurultu and self.ayar.harmonik_gurultu_bagil > 0:
            sigma = self.ayar.harmonik_gurultu_bagil * olcek
            for n in n_listesi:
                ham[n] = ham[n] + complex(*self.rng.normal(0.0, sigma, size=2))
        if self.ayar.harmonik_surukleme_bagil_s and zaman:
            surukleme = self.ayar.harmonik_surukleme_bagil_s * zaman * olcek
            for n in n_listesi:
                ham[n] = ham[n] + complex(surukleme, surukleme)

        # Olcum cercevesinin faz referansi (C_n -> C_n * exp(i*n*aci))
        cerceve = math.radians(self.ayar.olcum_cercevesi_acisi_derece)
        if cerceve:
            for n in n_listesi:
                ham[n] = ham[n] * complex(math.cos(n * cerceve), math.sin(n * cerceve))

        gradyen = ham[2].real / self.harmonikler_ayari.r_ref_m
        bilesenler = self._birime_cevir(ham)
        return HarmonikOlcumu(
            bilesenler=bilesenler,
            zaman=zaman,
            mutlak_gradyen_T_m=gradyen,
            ham_giris={"kaynak": "simulator"},
        )

    def _birime_cevir(self, ham_T: dict[int, complex]) -> dict[int, complex]:
        """Tesla cinsinden harmonikleri yapilandirilan birime cevirir."""
        birim = self.harmonikler_ayari.birim
        if birim in _TESLADAN_KATSAYI:
            katsayi = _TESLADAN_KATSAYI[birim]
            return {n: c * katsayi for n, c in ham_T.items()}

        # "units": b_n = B_n / B_(referans) * 1e4  (normalize, mutlak olcek yok)
        referans = ham_T.get(self.harmonikler_ayari.units_referans_n)
        nominal_olcek = self.miknatis.nominal_gradyen_T_m * self.harmonikler_ayari.r_ref_m
        if referans is None or abs(referans) < 1e-6 * nominal_olcek:
            raise ValueError(
                'Birim "units" iken normalizasyon referansi '
                f"(C_{self.harmonikler_ayari.units_referans_n}) sifira cok yakin. "
                "Akimlar sifirken (arka plan olcumu) normalize harmonik tanimsizdir; "
                "arka plan cikarma kullanilacaksa birim T ya da mT olmalidir."
            )
        return {n: c / referans.real * 1e4 for n, c in ham_T.items()}
