"""Harmonik donusumleri ve KONVANSIYONLAR.

Programdaki butun harmonik/merkez/isaret konvansiyonu secimleri YALNIZCA bu
modulde ve `yapilandirma.yaml` dosyasindadir. Baska hicbir modul harmonikleri
kendi basina yorumlamaz.

Konvansiyonlar
--------------
Alan acilimi (n = 1 dipol, n = 2 kuadrupol):

    B_y + i*B_x = SUM_{n>=1} C_n * (z / r_ref)^(n-1),   z = x + i*y
    C_n = B_n + i*A_n            (B: normal, A: skew)

Buradan:
  * z = 0'da  B_y = B_1,  B_x = A_1
  * Normal kuadrupol icin  G = B_2 / r_ref

Manyetik merkez (feed-down): kuadrupolun merkezi z_c'de ise alan
C_2*(z - z_c)/r_ref olur, yani gorunen dipol C_1 = -C_2*z_c/r_ref. Tersine:

    z_c = -r_ref * C_1 / C_2

`eslenik` bayragi, olcum yazilimi B_x + i*B_y konvansiyonunu kullaniyorsa
gereken eslenik almayi; `feed_down_isareti` ise isaret belirsizligini karsilar.

ONEMLI: Hedef tam olarak sifir oldugu icin, tutarli uygulanan bir isaret ya da
eslenik hatasi kapali cevrimin yakinsamasini BOZMAZ. Raporlanan merkez
y_rapor = T*y_gercek bicimindeki tersinir bir donusumse, kalibrasyon da ayni
donusumle olculdugu icin R_rapor = T*R_gercek olur ve cozum y_rapor -> 0'a
suruklenir; bu da y_gercek -> 0 demektir. Konvansiyon yalnizca raporlanan
merkezin isaretini/yonunu, R_eff'i ve teshis ciktilarini etkiler.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from .yapilandirma import HarmoniklerYapilandirmasi

# Girilen birimin Tesla'ya cevrim katsayisi ("units" mutlak olcek tasimaz).
_BIRIM_TESLA_KATSAYISI: dict[str, float] = {"T": 1.0, "mT": 1e-3}


class HarmonikHatasi(ValueError):
    """Harmonik girisi ya da donusumu gecersiz."""


@dataclass(frozen=True)
class HarmonikOlcumu:
    """Tek bir olcum noktasinda girilen harmonikler.

    `bilesenler`: n -> C_n, girilen birimde (T, mT ya da units).
    `mutlak_gradyen_T_m`: yalnizca birim "units" iken gereklidir (normalize
    edilmis girdi mutlak olcek tasimadigi icin gradyen oradan okunamaz).
    `ham_giris`: kullanicinin gerceken yazdigi degerler; yalnizca kayit icin.
    """

    bilesenler: dict[int, complex]
    zaman: float = 0.0
    mutlak_gradyen_T_m: float | None = None
    ham_giris: dict[str, Any] = field(default_factory=dict)

    def bilesen(self, n: int) -> complex:
        if n not in self.bilesenler:
            raise HarmonikHatasi(f"C_{n} bileseni bu olcumde yok")
        return self.bilesenler[n]

    @property
    def n_listesi(self) -> tuple[int, ...]:
        return tuple(sorted(self.bilesenler))


@dataclass(frozen=True)
class KontrolVektoru:
    """Kontrol edilen buyuklukler: y = [x_c, y_c, g].

    x_c, y_c metre cinsindendir; g boyutsuzdur.
    """

    x_c: float
    y_c: float
    g: float

    def dizi(self) -> np.ndarray:
        return np.array([self.x_c, self.y_c, self.g], dtype=float)

    @property
    def merkez_normu_m(self) -> float:
        return math.hypot(self.x_c, self.y_c)

    def __str__(self) -> str:
        return (
            f"x_c = {self.x_c * 1e6:+8.2f} um   "
            f"y_c = {self.y_c * 1e6:+8.2f} um   "
            f"g = {self.g:+.5f}"
        )


@dataclass(frozen=True)
class IzlemeBuyuklukleri:
    """Yalnizca izlenen (hedeflenmeyen) buyuklukler."""

    sq_over_g: float | None
    roll_mrad: float | None
    b3: float | None = None
    a3: float | None = None
    b4: float | None = None
    a4: float | None = None

    def sozluk(self) -> dict[str, float | None]:
        return {
            "sq_over_g": self.sq_over_g,
            "roll_mrad": self.roll_mrad,
            "b3": self.b3,
            "a3": self.a3,
            "b4": self.b4,
            "a4": self.a4,
        }


class HarmonikKonvansiyonu:
    """Yapilandirilmis konvansiyonlarla harmonik donusumleri.

    Tum isaret/eslenik/faz/birim secimleri bu sinifin icinde uygulanir.
    """

    def __init__(self, ayar: HarmoniklerYapilandirmasi) -> None:
        self.ayar = ayar

    # ------------------------------------------------------------------
    # Giris bicimleri -> C_n
    # ------------------------------------------------------------------
    def genlik_fazdan(self, genlik: float, faz: float, n: int) -> complex:
        """|C_n| ve faz degerinden C_n kurar (girilen birimde)."""
        if genlik < 0:
            raise HarmonikHatasi(f"C_{n} genligi negatif olamaz: {genlik}")
        faz_rad = math.radians(faz) if self.ayar.faz_birimi == "derece" else float(faz)
        carpan = n if self.ayar.faz_n_carpani else 1
        aci = self.ayar.faz_isareti * carpan * faz_rad
        return self._eslenikle(complex(genlik * math.cos(aci), genlik * math.sin(aci)))

    def normal_skewden(self, b_n: float, a_n: float) -> complex:
        """B_n ve A_n degerinden C_n kurar (girilen birimde)."""
        return self._eslenikle(complex(b_n, a_n))

    @staticmethod
    def normal_skewe(c_n: complex) -> tuple[float, float]:
        """C_n -> (B_n, A_n). Arayuzde turetilmis degerleri gostermek icin."""
        return c_n.real, c_n.imag

    def genlik_faza(self, c_n: complex, n: int) -> tuple[float, float]:
        """C_n -> (|C_n|, faz). Bicimler arasi gecis icin (genlik_fazdan'in tersi).

        `faz_n_carpani` acikken multipol acisi dogasi geregi 360/n derece
        modunda tanimlidir (ornegin n = 2 icin -120 ile +60 ayni alani verir);
        bu fonksiyon ana deger (principal value) temsilcisini dondurur.
        """
        ham = self._eslenikle(c_n)  # eslenik islemi kendi tersidir
        genlik = abs(ham)
        carpan = n if self.ayar.faz_n_carpani else 1
        aci = math.atan2(ham.imag, ham.real) / (self.ayar.faz_isareti * carpan)
        faz = math.degrees(aci) if self.ayar.faz_birimi == "derece" else aci
        return genlik, faz

    def _eslenikle(self, c_n: complex) -> complex:
        return c_n.conjugate() if self.ayar.eslenik else c_n

    # ------------------------------------------------------------------
    # Arka plan
    # ------------------------------------------------------------------
    def arka_plan_cikar(
        self, olcum: HarmonikOlcumu, arka_plan: HarmonikOlcumu | None
    ) -> HarmonikOlcumu:
        """Arka plani KOMPLEKS uzayda cikarir.

        Genlikleri cikarmak yanlis olur; bu yuzden arka plan da ayni genlik/faz
        (ya da normal/skew) formunda girilip C_n'e cevrilmis olmalidir.
        """
        if arka_plan is None:
            return olcum
        yalniz_dipol = self.ayar.arka_plan_cikarma == "yalniz_dipol"
        net: dict[int, complex] = {}
        for n, c_n in olcum.bilesenler.items():
            if yalniz_dipol and n != 1:
                net[n] = c_n
            else:
                net[n] = c_n - arka_plan.bilesenler.get(n, 0j)
        return HarmonikOlcumu(
            bilesenler=net,
            zaman=olcum.zaman,
            mutlak_gradyen_T_m=olcum.mutlak_gradyen_T_m,
            ham_giris=olcum.ham_giris,
        )

    # ------------------------------------------------------------------
    # Merkez, gradyen, kontrol vektoru
    # ------------------------------------------------------------------
    def merkez(self, olcum: HarmonikOlcumu) -> complex:
        """Feed-down ile manyetik merkez z_c = x_c + i*y_c (metre).

        Birim tasiyan bir orandir: C_1/C_2 oldugu icin girilen birim (T, mT ya
        da normalize units) sonucu etkilemez.
        """
        c1 = olcum.bilesen(1)
        c2 = olcum.bilesen(2)
        if c2 == 0:
            raise HarmonikHatasi("C_2 sifir; merkez hesaplanamaz (kuadrupol yok mu?)")
        return self.ayar.feed_down_isareti * (-self.ayar.r_ref_m * c1 / c2)

    def gradyen_T_m(self, olcum: HarmonikOlcumu) -> float:
        """Gradyen G (T/m).

        T/mT biriminde C_2'den okunur. "units" biriminde normalize girdi mutlak
        olcek tasimadigi icin olcumle birlikte girilen mutlak gradyen kullanilir.
        """
        if self.ayar.birim == "units":
            if olcum.mutlak_gradyen_T_m is None:
                if self.ayar.units_mutlak_gradyen_T_m is None:
                    raise HarmonikHatasi(
                        'Birim "units" iken gradyen normalize harmoniklerden okunamaz; '
                        "olcumle birlikte mutlak gradyen (T/m) girilmelidir"
                    )
                return self.ayar.units_mutlak_gradyen_T_m
            return olcum.mutlak_gradyen_T_m

        katsayi = _BIRIM_TESLA_KATSAYISI[self.ayar.birim]
        c2 = olcum.bilesen(2) * katsayi
        ham = c2.real if self.ayar.gradyen_kaynagi == "normal" else abs(c2)
        return ham / self.ayar.r_ref_m

    def kontrol_vektoru(self, olcum: HarmonikOlcumu, gradyen_hedefi_T_m: float) -> KontrolVektoru:
        """y = [x_c, y_c, g];  g = (G - G_hedef) / G_hedef."""
        if gradyen_hedefi_T_m == 0:
            raise HarmonikHatasi("Gradyen hedefi sifir olamaz")
        z_c = self.merkez(olcum)
        gradyen = self.gradyen_T_m(olcum)
        return KontrolVektoru(
            x_c=z_c.real,
            y_c=z_c.imag,
            g=(gradyen - gradyen_hedefi_T_m) / gradyen_hedefi_T_m,
        )

    # ------------------------------------------------------------------
    # Yalnizca izleme
    # ------------------------------------------------------------------
    def izleme(self, olcum: HarmonikOlcumu) -> IzlemeBuyuklukleri:
        """SQ/G (roll) ve varsa b3/a3/b4/a4. Hicbiri hedeflenmez.

        ISARET NOTU: roll, alan cercevesinde okunan acidir. Kaynak kosegen
        donunce C_2 -> C_2 * exp(-2i*rho) oldugu icin, harmoniklerden okunan
        roll mekanik donusun TERS isaretiyle cikar. Yalnizca izleme amacli
        oldugu ve buyuklugu dogru verdigi icin oldugu gibi raporlanir.
        """
        c2 = olcum.bilesenler.get(2)
        sq_over_g: float | None = None
        roll_mrad: float | None = None
        if c2 is not None and c2.real != 0:
            sq_over_g = c2.imag / c2.real
            # Skew/normal oraninin arctan'i, kuadrupol icin 2*roll acisidir.
            roll_mrad = 0.5 * math.atan2(c2.imag, c2.real) * 1e3

        def bilesen_ciftleri(n: int) -> tuple[float | None, float | None]:
            c_n = olcum.bilesenler.get(n)
            if c_n is None:
                return None, None
            return c_n.real, c_n.imag

        b3, a3 = bilesen_ciftleri(3)
        b4, a4 = bilesen_ciftleri(4)
        return IzlemeBuyuklukleri(
            sq_over_g=sq_over_g, roll_mrad=roll_mrad, b3=b3, a3=a3, b4=b4, a4=a4
        )

    # ------------------------------------------------------------------
    # Mertebe kontrolu (yazim hatasi yakalamanin ilk katmani)
    # ------------------------------------------------------------------
    def mertebe_makul_mu(self, n: int, c_n: complex, aralik: tuple[float, float]) -> bool:
        """|C_n| verilen makul aralikta mi?

        n = 1 icin sifira cok yakin deger normaldir (iyi merkezlenmis miknatis),
        bu yuzden alt sinir yalnizca n >= 2 icin zorlanir.
        """
        buyukluk = abs(c_n)
        alt, ust = aralik
        if buyukluk > ust:
            return False
        if n >= 2 and buyukluk < alt:
            return False
        return True
