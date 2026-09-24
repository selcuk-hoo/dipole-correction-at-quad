"""Mıknatısın 2 boyutlu çizgi akımı simülatörü.

Donanımda kullanmadan önce bütün akışı (kalibrasyon + düzeltme + arayüz)
donanımsız ve elle girişsiz sınamak içindir.

Model
------
Her bobin bir racetrack olarak modellenir: kutup ekseni etrafında theta +/- alpha
açılarında, a yarıçapında İKİ iletken demeti. Racetrack kapalı bir ilmek olduğu
için iki demet ZIT yönlü akım taşır (biri gidiş, biri dönüş).

z_0 konumundaki bir çizgi akımı I için (akım +z yönünde):

    B_y + i*B_x = mu0 * I / (2*pi*(z - z_0))

|z| < |z_0| bölgesinde multipol açılımı:

    C_n = -mu0 * I * r_ref^(n-1) / (2*pi * z_0^n)

Bütün iletkenler toplanır. Mıknatıs ofseti d ve roll açısı rho, iletken
konumlarına uygulanır:  z_j -> z_j * exp(i*rho) + d. Böylece mekanik ofset,
ölçümde doğal olarak feed-down dipolü olarak görünür.

Önemli sonuç (analitik): köşegen yerleşimde (45/135/225/315) ve nominal
alternatif polaritede, racetrack çifti yüzünden ortaya çıkan ek i çarpanı
sayesinde nominal desen NORMAL kuadrupol verir; H modu x_c'yi, V modu y_c'yi
hareket ettirir ve

    R_eff = a * sqrt(2) / (4 * cos(alpha))

olur (a = 100 mm, alpha = 30 derece için 40.8 mm). M modu (işaretli akımda
üniform) racetrack bobinlerde net akım üretmediği için hem dipole hem gradyene
tam olarak katkısızdır.
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

# Girilen/raporlanan birimin Tesla'dan çevrim katsayısı
_TESLADAN_KATSAYI: dict[str, float] = {"T": 1.0, "mT": 1e3}


@dataclass(frozen=True)
class Iletken:
    """Tek bir iletken demeti."""

    konum: complex  # metre (ölçüm çerçevesi merkezine göre)
    sarim: float  # işaretli sarım sayısı (gidiş +, dönüş -)
    bobin: int  # 0..3


class Simulator:
    """Dört bobinli air-core kuadrupolün 2D modeli.

    `ofset_m`, `roll_rad` ve `arka_plan_T` çalışma anında değiştirilebilir;
    testler rastgele ofsetler vermek için bunları kullanır.
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

        # Çalışma anında değiştirilebilen fiziksel durum
        self.ofset_m: complex = complex(
            ayar.miknatis_ofseti_mm[0] * 1e-3, ayar.miknatis_ofseti_mm[1] * 1e-3
        )
        self.roll_rad: float = ayar.roll_mrad * 1e-3
        # Üniform arka plan: C_1 üzerine binen B_y + i*B_x
        self.arka_plan_T: complex = complex(ayar.arka_plan_T[0], ayar.arka_plan_T[1])

    # ------------------------------------------------------------------
    # Geometri
    # ------------------------------------------------------------------
    def iletkenler(self) -> list[Iletken]:
        """Roll ve ofset uygulanmış iletken demetleri (bobin başına iki tane)."""
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
        """C_n (Tesla), gürültü/arka plan/çerçeve dönüşü UYGULANMADAN.

        İşaretli akım kullanılır: fiziksel genlik x nominal polarite.
        """
        akimlar = np.asarray(akimlar, dtype=float)
        if akimlar.shape != (BOBIN_SAYISI,):
            raise ValueError(f"{BOBIN_SAYISI} elemanlı akım vektörü bekleniyor")
        polarite = np.array(self.miknatis.nominal_polarite, dtype=float)
        r_ref = self.harmonikler_ayari.r_ref_m

        toplam = 0j
        for iletken in self.iletkenler():
            akim = akimlar[iletken.bobin] * polarite[iletken.bobin] * iletken.sarim
            toplam += akim / iletken.konum**n
        return -MU0_2PI * r_ref ** (n - 1) * toplam

    def gradyen_T_m(self, akimlar: np.ndarray) -> float:
        """Gerçek gradyen G = B_2 / r_ref (Tesla/m), gürültüsüz."""
        c2 = self.harmonik_ham_T(akimlar, 2)
        return c2.real / self.harmonikler_ayari.r_ref_m

    def gercek_merkez_m(self, akimlar: np.ndarray) -> complex:
        """Gürültüsüz, arka plansız gerçek manyetik merkez (metre).

        Testlerde "ölçülen merkez" ile karşılaştırma referansı olarak kullanılır.
        """
        c1 = self.harmonik_ham_T(akimlar, 1)
        c2 = self.harmonik_ham_T(akimlar, 2)
        return -self.harmonikler_ayari.r_ref_m * c1 / c2

    def _nominal_olcek_T(self) -> float:
        """Nominal akımda |C_2| (T): gürültü ölçeği ve "units" normalizasyonu
        için referans.

        `nominal_gradyen_T_m` yapılandırma değeri serbest bir parametre değildir;
        burada bütün bobinlere nominal akım uygulanınca geometri modelinden
        çıkan gerçek alandan hesaplanır, elle senkronize edilmesi gerekmez.
        """
        nominal_akimlar = np.full(BOBIN_SAYISI, self.miknatis.nominal_akim_A)
        return abs(self.harmonik_ham_T(nominal_akimlar, 2))

    # ------------------------------------------------------------------
    # Ölçüm (elle girişle aynı biçimde)
    # ------------------------------------------------------------------
    def olc(
        self, akimlar: np.ndarray, zaman: float = 0.0, gurultu: bool = True
    ) -> HarmonikOlcumu:
        """Rotating coil ölçümünü taklit eder.

        Dönen `HarmonikOlcumu`, elle girişle birebir aynı yapıdadır: yapılandırılan
        birimde C_n bileşenleri (T, mT ya da normalize units) ve "units" biçiminde
        gereken mutlak gradyen.
        """
        n_listesi = self.harmonikler_ayari.tum_harmonikler
        ham: dict[int, complex] = {n: self.harmonik_ham_T(akimlar, n) for n in n_listesi}

        # Üniform arka plan yalnızca dipole biner (zamanla yavaş sürükleniyor).
        ham[1] = ham[1] + self.arka_plan_T * (1.0 + self.ayar.arka_plan_surukleme_T_s * zaman)

        # Ölçüm gürültüsü ve yavaş sürüklenme.
        # Ölçek SABİTTİR: nominal ana harmonik |C_2|, nominal akımda hesaplanır.
        # Anlık |C_2| kullanılmaz; çünkü arka plan ölçümünde akımlar sıfır
        # olduğundan |C_2| ~ 0 olur ve gürültü ölçeği anlamsızlaşır (gerçek
        # ölçüm zincirinin gürültüsü de çalışma noktasından bağımsızdır).
        olcek = self._nominal_olcek_T()
        if gurultu and self.ayar.harmonik_gurultu_bagil > 0:
            sigma = self.ayar.harmonik_gurultu_bagil * olcek
            for n in n_listesi:
                ham[n] = ham[n] + complex(*self.rng.normal(0.0, sigma, size=2))
        if self.ayar.harmonik_surukleme_bagil_s and zaman:
            surukleme = self.ayar.harmonik_surukleme_bagil_s * zaman * olcek
            for n in n_listesi:
                ham[n] = ham[n] + complex(surukleme, surukleme)

        # Ölçüm çerçevesinin faz referansı (C_n -> C_n * exp(i*n*aci))
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
        """Tesla cinsinden harmonikleri yapılandırılan birime çevirir."""
        birim = self.harmonikler_ayari.birim
        if birim in _TESLADAN_KATSAYI:
            katsayi = _TESLADAN_KATSAYI[birim]
            return {n: c * katsayi for n, c in ham_T.items()}

        # "units": b_n = B_n / B_(referans) * 1e4  (normalize, mutlak ölçek yok)
        referans = ham_T.get(self.harmonikler_ayari.units_referans_n)
        nominal_olcek = self._nominal_olcek_T()
        if referans is None or abs(referans) < 1e-6 * nominal_olcek:
            raise ValueError(
                'Birim "units" iken normalizasyon referansı '
                f"(C_{self.harmonikler_ayari.units_referans_n}) sıfıra çok yakın. "
                "Akımlar sıfırken (arka plan ölçümü) normalize harmonik tanımsızdır; "
                "arka plan çıkarma kullanılacaksa birim T ya da mT olmalıdır."
            )
        return {n: c / referans.real * 1e4 for n, c in ham_T.items()}
