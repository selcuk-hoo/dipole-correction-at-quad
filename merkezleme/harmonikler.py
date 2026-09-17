"""Harmonik dönüşümleri ve KONVANSİYONLAR.

Programdaki bütün harmonik/merkez/işaret konvansiyonu seçimleri YALNIZCA bu
modülde ve `yapilandirma.yaml` dosyasındadır. Başka hiçbir modül harmonikleri
kendi başına yorumlamaz.

Konvansiyonlar
---------------
Alan açılımı (n = 1 dipol, n = 2 kuadrupol):

    B_y + i*B_x = SUM_{n>=1} C_n * (z / r_ref)^(n-1),   z = x + i*y
    C_n = B_n + i*A_n            (B: normal, A: skew)

Buradan:
  * z = 0'da  B_y = B_1,  B_x = A_1
  * Normal kuadrupol için  G = B_2 / r_ref

Manyetik merkez (feed-down): kuadrupolün merkezi z_c'de ise alan
C_2*(z - z_c)/r_ref olur, yani görünen dipol C_1 = -C_2*z_c/r_ref. Tersine:

    z_c = -r_ref * C_1 / C_2

`eslenik` bayrağı, ölçüm yazılımı B_x + i*B_y konvansiyonunu kullanıyorsa
gereken eşlenik almayı; `feed_down_isareti` ise işaret belirsizliğini karşılar.

ÖNEMLİ: Hedef tam olarak sıfır olduğu için, tutarlı uygulanan bir işaret ya da
eşlenik hatası kapalı çevrimin yakınsamasını BOZMAZ. Raporlanan merkez
y_rapor = T*y_gercek biçimindeki tersinir bir dönüşümse, kalibrasyon da aynı
dönüşümle ölçüldüğü için R_rapor = T*R_gercek olur ve çözüm y_rapor -> 0'a
sürüklenir; bu da y_gercek -> 0 demektir. Konvansiyon yalnızca raporlanan
merkezin işaretini/yönünü, R_eff'i ve teşhis çıktılarını etkiler.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from .yapilandirma import HarmoniklerYapilandirmasi

# Girilen birimin Tesla'ya çevrim katsayısı ("units" mutlak ölçek taşımaz).
_BIRIM_TESLA_KATSAYISI: dict[str, float] = {"T": 1.0, "mT": 1e-3}


class HarmonikHatasi(ValueError):
    """Harmonik girişi ya da dönüşümü geçersiz."""


@dataclass(frozen=True)
class HarmonikOlcumu:
    """Tek bir ölçüm noktasında girilen harmonikler.

    `bilesenler`: n -> C_n, girilen birimde (T, mT ya da units).
    `mutlak_gradyen_T_m`: yalnızca birim "units" iken gereklidir (normalize
    edilmiş girdi mutlak ölçek taşımadığı için gradyen oradan okunamaz).
    `ham_giris`: kullanıcının gerçekten yazdığı değerler; yalnızca kayıt için.
    """

    bilesenler: dict[int, complex]
    zaman: float = 0.0
    mutlak_gradyen_T_m: float | None = None
    ham_giris: dict[str, Any] = field(default_factory=dict)

    def bilesen(self, n: int) -> complex:
        if n not in self.bilesenler:
            raise HarmonikHatasi(f"C_{n} bileşeni bu ölçümde yok")
        return self.bilesenler[n]

    @property
    def n_listesi(self) -> tuple[int, ...]:
        return tuple(sorted(self.bilesenler))


@dataclass(frozen=True)
class KontrolVektoru:
    """Kontrol edilen büyüklükler: y = [x_c, y_c, g].

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
    """Yalnızca izlenen (hedeflenmeyen) büyüklükler."""

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
    """Yapılandırılmış konvansiyonlarla harmonik dönüşümleri.

    Tüm işaret/eşlenik/faz/birim seçimleri bu sınıfın içinde uygulanır.
    """

    def __init__(self, ayar: HarmoniklerYapilandirmasi) -> None:
        self.ayar = ayar

    # ------------------------------------------------------------------
    # Giriş biçimleri -> C_n
    # ------------------------------------------------------------------
    def genlik_fazdan(self, genlik: float, faz: float, n: int) -> complex:
        """|C_n| ve faz değerinden C_n kurar (girilen birimde)."""
        if genlik < 0:
            raise HarmonikHatasi(f"C_{n} genliği negatif olamaz: {genlik}")
        faz_rad = math.radians(faz) if self.ayar.faz_birimi == "derece" else float(faz)
        carpan = n if self.ayar.faz_n_carpani else 1
        aci = self.ayar.faz_isareti * carpan * faz_rad
        return self._eslenikle(complex(genlik * math.cos(aci), genlik * math.sin(aci)))

    def normal_skewden(self, b_n: float, a_n: float) -> complex:
        """B_n ve A_n değerinden C_n kurar (girilen birimde)."""
        return self._eslenikle(complex(b_n, a_n))

    @staticmethod
    def normal_skewe(c_n: complex) -> tuple[float, float]:
        """C_n -> (B_n, A_n). Arayüzde türetilmiş değerleri göstermek için."""
        return c_n.real, c_n.imag

    def genlik_faza(self, c_n: complex, n: int) -> tuple[float, float]:
        """C_n -> (|C_n|, faz). Biçimler arası geçiş için (genlik_fazdan'ın tersi).

        `faz_n_carpani` açıkken multipol açısı doğası gereği 360/n derece
        modunda tanımlıdır (örneğin n = 2 için -120 ile +60 aynı alanı verir);
        bu fonksiyon ana değer (principal value) temsilcisini döndürür.
        """
        ham = self._eslenikle(c_n)  # eşlenik işlemi kendi tersidir
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
        """Arka planı KOMPLEKS uzayda çıkarır.

        Genlikleri çıkarmak yanlış olur; bu yüzden arka plan da aynı genlik/faz
        (ya da normal/skew) formunda girilip C_n'e çevrilmiş olmalıdır.
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
    # Merkez, gradyen, kontrol vektörü
    # ------------------------------------------------------------------
    def merkez(self, olcum: HarmonikOlcumu) -> complex:
        """Feed-down ile manyetik merkez z_c = x_c + i*y_c (metre).

        Birim taşıyan bir orandır: C_1/C_2 olduğu için girilen birim (T, mT ya
        da normalize units) sonucu etkilemez.
        """
        c1 = olcum.bilesen(1)
        c2 = olcum.bilesen(2)
        if c2 == 0:
            raise HarmonikHatasi("C_2 sıfır; merkez hesaplanamaz (kuadrupol yok mu?)")
        return self.ayar.feed_down_isareti * (-self.ayar.r_ref_m * c1 / c2)

    def gradyen_T_m(self, olcum: HarmonikOlcumu) -> float:
        """Gradyen G (T/m).

        T/mT biriminde C_2'den okunur. "units" biriminde normalize girdi mutlak
        ölçek taşımadığı için ölçümle birlikte girilen mutlak gradyen kullanılır.
        """
        if self.ayar.birim == "units":
            if olcum.mutlak_gradyen_T_m is None:
                if self.ayar.units_mutlak_gradyen_T_m is None:
                    raise HarmonikHatasi(
                        'Birim "units" iken gradyen normalize harmoniklerden okunamaz; '
                        "ölçümle birlikte mutlak gradyen (T/m) girilmelidir"
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
            raise HarmonikHatasi("Gradyen hedefi sıfır olamaz")
        z_c = self.merkez(olcum)
        gradyen = self.gradyen_T_m(olcum)
        return KontrolVektoru(
            x_c=z_c.real,
            y_c=z_c.imag,
            g=(gradyen - gradyen_hedefi_T_m) / gradyen_hedefi_T_m,
        )

    # ------------------------------------------------------------------
    # Yalnızca izleme
    # ------------------------------------------------------------------
    def izleme(self, olcum: HarmonikOlcumu) -> IzlemeBuyuklukleri:
        """SQ/G (roll) ve varsa b3/a3/b4/a4. Hiçbiri hedeflenmez.

        İŞARET NOTU: roll, alan çerçevesinde okunan açıdır. Kaynak köşegen
        dönünce C_2 -> C_2 * exp(-2i*rho) olduğu için, harmoniklerden okunan
        roll mekanik dönüşün TERS işaretiyle çıkar. Yalnızca izleme amaçlı
        olduğu ve büyüklüğü doğru verdiği için olduğu gibi raporlanır.
        """
        c2 = olcum.bilesenler.get(2)
        sq_over_g: float | None = None
        roll_mrad: float | None = None
        if c2 is not None and c2.real != 0:
            sq_over_g = c2.imag / c2.real
            # Skew/normal oranının arctan'i, kuadrupol için 2*roll açısıdır.
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
    # Mertebe kontrolü (yazım hatası yakalamanın ilk katmanı)
    # ------------------------------------------------------------------
    def mertebe_makul_mu(self, n: int, c_n: complex, aralik: tuple[float, float]) -> bool:
        """|C_n| verilen makul aralıkta mı?

        n = 1 için sıfıra çok yakın değer normaldir (iyi merkezlenmiş mıknatıs),
        bu yüzden alt sınır yalnızca n >= 2 için zorlanır.
        """
        buyukluk = abs(c_n)
        alt, ust = aralik
        if buyukluk > ust:
            return False
        if n >= 2 and buyukluk < alt:
            return False
        return True
