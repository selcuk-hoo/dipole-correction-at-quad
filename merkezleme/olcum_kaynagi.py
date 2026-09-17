"""Olcum kaynagi: elle girisi soyutlayan katman.

Arayuz (`ElleGiris`) ile simulator (`SimulatorGirisi`) ayni protokolu uygular;
boylece butun akis donanimsiz ve elle girissiz sinanabilir, "deneme kipinde" de
alanlar simulatorden otomatik doldurulur.

Alan donusumleri de burada: arayuzun metin kutulari ile `HarmonikOlcumu`
arasindaki cevrim tek yerde toplanmistir (konvansiyonlarin kendisi
`harmonikler.py` icindedir).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, Sequence

import numpy as np

from .harmonikler import HarmonikKonvansiyonu, HarmonikOlcumu
from .simulator import Simulator


@dataclass(frozen=True)
class OlcumIstegi:
    """Programin kullanicidan (ya da simulatorden) bekledigi olcum."""

    tur: str  # "arka_plan" | "olcum"
    etiket: str
    akimlar_A: np.ndarray
    adim_no: int
    toplam_adim: int
    mod: str = ""
    epsilon: float | None = None

    @property
    def metin(self) -> str:
        if self.tur == "arka_plan":
            return "ARKA PLAN OLCUMUNU ALIN VE GIRIN (akimlar sifirda)"
        return "OLCUMU ALIN VE GIRIN"


class OlcumKaynagi(Protocol):
    """Harmonik olcumu saglayan soyut kaynak."""

    def olcum_al(self, istek: OlcumIstegi) -> HarmonikOlcumu: ...


# ---------------------------------------------------------------------------
# Alan <-> olcum donusumu
# ---------------------------------------------------------------------------
def _alan_adlari(n: int, bicim: str) -> tuple[str, str]:
    if bicim == "genlik_faz":
        return f"C{n}_genlik", f"C{n}_faz"
    return f"B{n}", f"A{n}"


@dataclass
class AlanGirisi:
    """Arayuzdeki metin kutularinin ham icerigi."""

    alanlar: dict[str, str] = field(default_factory=dict)
    mutlak_gradyen_T_m: str = ""

    def doldurulmus_mu(self, n: int, bicim: str) -> bool:
        birinci, ikinci = _alan_adlari(n, bicim)
        return bool(self.alanlar.get(birinci, "").strip()) and bool(
            self.alanlar.get(ikinci, "").strip()
        )


class AlanHatasi(ValueError):
    """Metin kutusu icerigi gecersiz."""


def sayi_ayristir(metin: str, alan_adi: str) -> float:
    """Metin kutusundan sayi okur. Ondalik ayraci olarak virgul de kabul edilir."""
    ham = str(metin).strip().replace(",", ".")
    if not ham:
        raise AlanHatasi(f"{alan_adi} bos")
    try:
        return float(ham)
    except ValueError as hata:
        raise AlanHatasi(f"{alan_adi} sayi degil: {metin!r}") from hata


def alanlardan_olcum(
    giris: AlanGirisi,
    konvansiyon: HarmonikKonvansiyonu,
    bicim: str,
    zorunlu: Sequence[int] = (1, 2),
    opsiyonel: Sequence[int] = (3, 4),
    zaman: float = 0.0,
) -> HarmonikOlcumu:
    """Metin kutularindan `HarmonikOlcumu` uretir.

    `bicim`: "genlik_faz" -> (|C_n|, faz);  "normal_skew" -> (B_n, A_n)
    """
    bilesenler: dict[int, complex] = {}
    for n in zorunlu:
        birinci, ikinci = _alan_adlari(n, bicim)
        a = sayi_ayristir(giris.alanlar.get(birinci, ""), birinci)
        b = sayi_ayristir(giris.alanlar.get(ikinci, ""), ikinci)
        bilesenler[n] = (
            konvansiyon.genlik_fazdan(a, b, n)
            if bicim == "genlik_faz"
            else konvansiyon.normal_skewden(a, b)
        )
    for n in opsiyonel:
        if not giris.doldurulmus_mu(n, bicim):
            continue
        birinci, ikinci = _alan_adlari(n, bicim)
        a = sayi_ayristir(giris.alanlar.get(birinci, ""), birinci)
        b = sayi_ayristir(giris.alanlar.get(ikinci, ""), ikinci)
        bilesenler[n] = (
            konvansiyon.genlik_fazdan(a, b, n)
            if bicim == "genlik_faz"
            else konvansiyon.normal_skewden(a, b)
        )

    mutlak_gradyen: float | None = None
    if giris.mutlak_gradyen_T_m.strip():
        mutlak_gradyen = sayi_ayristir(giris.mutlak_gradyen_T_m, "mutlak gradyen (T/m)")

    return HarmonikOlcumu(
        bilesenler=bilesenler,
        zaman=zaman,
        mutlak_gradyen_T_m=mutlak_gradyen,
        ham_giris={"bicim": bicim, **{k: v for k, v in giris.alanlar.items() if v.strip()}},
    )


def olcumden_alanlar(
    olcum: HarmonikOlcumu, konvansiyon: HarmonikKonvansiyonu, bicim: str
) -> AlanGirisi:
    """`HarmonikOlcumu` -> metin kutusu icerikleri (elle girisle ayni bicimde).

    Deneme kipinde simulator ciktisini arayuze doldurmak ve bicimler arasi
    gecis yapmak icin kullanilir.
    """
    alanlar: dict[str, str] = {}
    for n, c_n in sorted(olcum.bilesenler.items()):
        birinci, ikinci = _alan_adlari(n, bicim)
        if bicim == "genlik_faz":
            genlik, faz = konvansiyon.genlik_faza(c_n, n)
            alanlar[birinci] = f"{genlik:.6g}"
            alanlar[ikinci] = f"{faz:.4f}"
        else:
            b_n, a_n = konvansiyon.normal_skewe(c_n)
            alanlar[birinci] = f"{b_n:.6g}"
            alanlar[ikinci] = f"{a_n:.6g}"
    return AlanGirisi(
        alanlar=alanlar,
        mutlak_gradyen_T_m=(
            "" if olcum.mutlak_gradyen_T_m is None else f"{olcum.mutlak_gradyen_T_m:.6g}"
        ),
    )


# ---------------------------------------------------------------------------
# Kaynaklar
# ---------------------------------------------------------------------------
class SimulatorGirisi:
    """Olcumleri simulatorden alan kaynak (testler ve deneme kipi)."""

    def __init__(self, simulator: Simulator) -> None:
        self.simulator = simulator
        self.zaman = 0.0
        self.olcum_sayisi = 0

    def olcum_al(self, istek: OlcumIstegi) -> HarmonikOlcumu:
        self.olcum_sayisi += 1
        # Her olcum arasinda gecen sure; suruklenme terimleri icin.
        self.zaman += 1.0
        return self.simulator.olc(np.asarray(istek.akimlar_A, dtype=float), zaman=self.zaman)


class ElleGiris:
    """Arayuzun doldurdugu kaynak.

    Arayuz `olcumu_yerlestir()` ile sirada bekleyen olcumu koyar; is akisi
    `olcum_al()` ile onu tuketir. Olcum hazir degilse `OlcumHazirDegil`
    yukseltilir - arayuz olay tabanli calistigi icin bu normaldir.
    """

    def __init__(self) -> None:
        self._bekleyen: HarmonikOlcumu | None = None

    def olcumu_yerlestir(self, olcum: HarmonikOlcumu) -> None:
        self._bekleyen = olcum

    def olcum_al(self, istek: OlcumIstegi) -> HarmonikOlcumu:
        if self._bekleyen is None:
            raise OlcumHazirDegil(f"{istek.etiket} icin elle giris bekleniyor")
        olcum, self._bekleyen = self._bekleyen, None
        return olcum


class OlcumHazirDegil(RuntimeError):
    """Elle giris henuz yapilmadi."""
