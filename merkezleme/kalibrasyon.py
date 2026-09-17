"""Kalibrasyon: nokta planı, fitler, 3x4 response matrix, SVD ve R_eff.

Elle giriş yapıldığı için ölçüm sayısı bilinçli olarak küçük tutulur:

* H, V, Q modları zorunlu; M modu isteğe bağlı kontroldür (dipole ve gradyene
  katkısız olması beklenir).
* Mod başına 3 nokta (-D, 0, +D) ya da 5 nokta (-2D .. +2D).
* Sıfır noktası modlar arasında paylaşılabilir (ortak_sifir_noktasi).
* Noktalar, sürüklenmeyi eğimden ayırmak için monoton OLMAYAN sırada alınır;
  ayrıca modlar birbirine geçmeli (round-robin) sıralanır, böylece yavaş bir
  sürüklenme tek bir modun eğimine yüklenmez.

Response matrix
----------------
Mod eğimleri S (3x4, sütunlar Q/H/V/M) ölçülür ve bobin bazına çevrilir:

    R = S * V^T / 4

Satırlar y = [x_c, y_c, g], sütunlar bobin başına BAĞIL akım sapmasıdır.

Koşul sayısı iki biçimde raporlanır:

* Ham koşul sayısı: R'nin tekil değerlerinden. Satırlar farklı birimde
  olduğu için (metre, metre, boyutsuz) bu sayı birim seçiminden etkilenir ve
  tek başına anlamlı değildir.
* Toleransa göre ölçeklenmiş koşul sayısı: her satır kendi toleransına bölünür.
  "Her üç hedefi de kendi toleransına, karşılaştırılabilir akım çabasıyla
  kontrol edebiliyor muyum?" sorusunun cevabıdır. Eşik buna uygulanır.

Not: R 3x4 ve rank 3 olduğu için hedef y HER ZAMAN tam olarak erişilebilir;
bu yüzden satırların birim karışımı (m, m, boyutsuz) çözümü etkilemez. Eski
4x4 [Bx, By, G, SQ] kurulumunda ise SQ satırı sistemi kötü koşullu yapıyor ve
ağırlıklı bir ödünleşmeye zorluyordu.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from itertools import permutations
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np

from .harmonikler import KontrolVektoru
from .modlar import MOD_SIRASI, Y_SATIRLARI, ModBazi
from .yapilandirma import (
    BOBIN_SAYISI,
    DuzeltmeYapilandirmasi,
    KalibrasyonYapilandirmasi,
)

ORTAK_SIFIR = "ortak_sifir"


class KalibrasyonHatasi(ValueError):
    """Kalibrasyon planı ya da fiti geçersiz."""


# ---------------------------------------------------------------------------
# Plan
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class KalibrasyonNoktasi:
    """Tek bir kalibrasyon ölçüm noktası."""

    mod: str  # "Q" | "H" | "V" | "M" | ORTAK_SIFIR
    epsilon: float
    arka_plan_al: bool

    @property
    def etiket(self) -> str:
        if self.mod == ORTAK_SIFIR:
            return "ortak sıfır (nominal akımlar)"
        return f"{self.mod} modu, eps = {self.epsilon:+.4f}"

    def akimlar(self, mod_bazi: ModBazi) -> np.ndarray:
        if self.mod == ORTAK_SIFIR or self.epsilon == 0.0:
            return mod_bazi.nominal_akimlar
        return mod_bazi.mod_akimlari(self.mod, self.epsilon)


@dataclass(frozen=True)
class KalibrasyonPlani:
    noktalar: tuple[KalibrasyonNoktasi, ...]
    olcum_basi_sure_dk: float

    @property
    def nokta_sayisi(self) -> int:
        return len(self.noktalar)

    @property
    def arka_plan_sayisi(self) -> int:
        return sum(1 for n in self.noktalar if n.arka_plan_al)

    @property
    def giris_sayisi(self) -> int:
        """Kullanıcının elle yapacağı toplam harmonik girişi sayısı."""
        return self.nokta_sayisi + self.arka_plan_sayisi

    @property
    def tahmini_sure_dk(self) -> float:
        return self.giris_sayisi * self.olcum_basi_sure_dk

    def ozet_metni(self) -> str:
        return (
            f"{self.nokta_sayisi} ölçüm noktası + {self.arka_plan_sayisi} arka plan "
            f"= {self.giris_sayisi} elle giriş\n"
            f"Tahmini süre: {self.tahmini_sure_dk:.0f} dk "
            f"({self.olcum_basi_sure_dk:.1f} dk/ölçüm)"
        )


def _monoton_olmayan_sira(epsilonlar: Sequence[float]) -> list[float]:
    """Zaman indeksi ile epsilon arasındaki korelasyonu en küçük yapan sıralama.

    Bütün permütasyonlar denenir (en fazla 5 nokta olduğu için ucuzdur). Amaç
    fonksiyonu sum(t_merkezli * eps); sıfıra ne kadar yakınsa, yavaş bir zaman
    sürüklenmesi eğime o kadar az sızar. Eşitlik durumunda ardışık farkların en
    küçüğü en büyük olan (en "zigzag") sıralama seçilir, sonra sözlükbilimsel
    sıralama ile kesin sonuç üretilir.
    """
    degerler = list(epsilonlar)
    if len(degerler) < 3:
        return degerler
    zaman = np.arange(len(degerler), dtype=float)
    zaman_merkezli = zaman - zaman.mean()

    en_iyi: tuple[tuple[float, float, tuple[float, ...]], list[float]] | None = None
    for perm in permutations(degerler):
        dizi = np.array(perm, dtype=float)
        korelasyon = abs(float(zaman_merkezli @ dizi))
        zigzag = -float(np.min(np.abs(np.diff(dizi)))) if len(dizi) > 1 else 0.0
        skor = (round(korelasyon, 12), zigzag, perm)
        if en_iyi is None or skor < en_iyi[0]:
            en_iyi = (skor, list(perm))
    assert en_iyi is not None
    return en_iyi[1]


def plan_olustur(ayar: KalibrasyonYapilandirmasi) -> KalibrasyonPlani:
    """Yapılandırmadan kalibrasyon nokta planını üretir."""
    delta = ayar.delta_bagil
    if ayar.nokta_sayisi == 3:
        tum_epsilonlar = [-delta, 0.0, +delta]
    else:
        tum_epsilonlar = [-2 * delta, -delta, 0.0, +delta, +2 * delta]

    modlar = ayar.olculen_modlar
    mod_epsilonlari: dict[str, list[float]] = {}
    for mod_indeksi, mod in enumerate(modlar):
        epsilonlar = [e for e in tum_epsilonlar if not (ayar.ortak_sifir_noktasi and e == 0.0)]
        if not ayar.monoton_olmayan_sira:
            mod_epsilonlari[mod] = epsilonlar
        elif len(epsilonlar) == 2:
            # İki noktada (ortak sıfırla birlikte 3 nokta) tek bir mod içinde
            # zigzag mümkün değildir; bu yüzden modlar arası yön değiştirilir,
            # böylece global epsilon dizisi monoton kalmaz ve yavaş bir
            # sürüklenme bütün modların eğimine aynı yönde sızmaz.
            mod_epsilonlari[mod] = epsilonlar if mod_indeksi % 2 == 0 else list(reversed(epsilonlar))
        else:
            mod_epsilonlari[mod] = _monoton_olmayan_sira(epsilonlar)

    sirali: list[tuple[str, float]] = []
    if ayar.ortak_sifir_noktasi:
        # Ortak sıfır en başta: aynı zamanda G_hedef'in ölçüldüğü noktadır.
        sirali.append((ORTAK_SIFIR, 0.0))

    # Modları birbirine geçmeli sırala (round-robin).
    en_uzun = max(len(v) for v in mod_epsilonlari.values())
    for i in range(en_uzun):
        for mod in modlar:
            if i < len(mod_epsilonlari[mod]):
                sirali.append((mod, mod_epsilonlari[mod][i]))

    noktalar: list[KalibrasyonNoktasi] = []
    for indeks, (mod, epsilon) in enumerate(sirali):
        arka_plan_al = indeks % ayar.arka_plan_her_n_noktada == 0
        noktalar.append(KalibrasyonNoktasi(mod=mod, epsilon=epsilon, arka_plan_al=arka_plan_al))
    return KalibrasyonPlani(
        noktalar=tuple(noktalar), olcum_basi_sure_dk=ayar.olcum_basi_tahmini_sure_dk
    )


# ---------------------------------------------------------------------------
# Fit
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class BilesenFiti:
    """y'nin tek bir bileşeninin (x_c, y_c ya da g) bir moda karşı fiti."""

    bilesen: str
    egim: float
    kesisim: float
    artiklar: tuple[float, ...]
    artik_rms: float
    r2: float | None  # yalnızca tepki veren bileşenler için anlamlı
    tepki: float  # |egim| * max|eps|
    tepki_veriyor: bool
    lineer_mi: bool | None

    def sozluk(self) -> dict[str, object]:
        return {
            "bilesen": self.bilesen,
            "egim": self.egim,
            "kesisim": self.kesisim,
            "artiklar": list(self.artiklar),
            "artik_rms": self.artik_rms,
            "r2": self.r2,
            "tepki": self.tepki,
            "tepki_veriyor": self.tepki_veriyor,
            "lineer_mi": self.lineer_mi,
        }


@dataclass(frozen=True)
class ModFiti:
    mod: str
    epsilonlar: tuple[float, ...]
    bilesenler: dict[str, BilesenFiti]

    @property
    def egim(self) -> np.ndarray:
        """dy/deps (3 elemanlı: x_c, y_c, g)."""
        return np.array([self.bilesenler[ad].egim for ad in Y_SATIRLARI], dtype=float)

    @property
    def lineer_mi(self) -> bool:
        """Tepki veren bütün bileşenler lineer mi?"""
        sonuclar = [
            b.lineer_mi for b in self.bilesenler.values() if b.tepki_veriyor and b.lineer_mi is not None
        ]
        return all(sonuclar) if sonuclar else True

    def sozluk(self) -> dict[str, object]:
        return {
            "mod": self.mod,
            "epsilonlar": list(self.epsilonlar),
            "lineer_mi": self.lineer_mi,
            "bilesenler": {ad: b.sozluk() for ad, b in self.bilesenler.items()},
        }


def _bilesen_fiti(
    bilesen: str,
    epsilonlar: np.ndarray,
    degerler: np.ndarray,
    r2_esigi: float,
    tolerans_olcegi: float,
) -> BilesenFiti:
    """Tek bileşen için doğru fiti ve lineerlik değerlendirmesi.

    R^2 yalnızca gerçekten TEPKİ VEREN bileşenler için hesaplanır: örneğin H
    modunda g bileşeni sabit sıfır civarındadır, oradaki R^2 gürültüden ibaret
    olur ve fiti haksız yere "lineer değil" gösterir.

    "Tepki veriyor" ölçütü iki koşulu birlikte ister:
      1. Tepki, bileşenin TOLERANS ölçeğinden büyük olmalı (fiziksel anlamlılık).
         Yalnızca fit artıklarına bakmak, 3 noktalı bir fitte şans eseri küçük
         çıkan artıklar yüzünden gürültüyü "tepki" sayabilir.
      2. Tepki, artık gürültüsünün belirgin üzerinde olmalı.
    """
    egim, kesisim = np.polyfit(epsilonlar, degerler, 1)
    uydurulan = egim * epsilonlar + kesisim
    artiklar = degerler - uydurulan
    artik_rms = float(np.sqrt(np.mean(artiklar**2)))
    tepki = float(abs(egim) * np.max(np.abs(epsilonlar))) if len(epsilonlar) else 0.0

    tepki_veriyor = tepki > tolerans_olcegi and tepki > 3.0 * artik_rms

    r2: float | None = None
    lineer_mi: bool | None = None
    if len(epsilonlar) >= 3 and tepki_veriyor:
        toplam_kareler = float(np.sum((degerler - np.mean(degerler)) ** 2))
        artik_kareler = float(np.sum(artiklar**2))
        r2 = 1.0 - artik_kareler / toplam_kareler if toplam_kareler > 0 else None
        lineer_mi = None if r2 is None else bool(r2 >= r2_esigi)

    return BilesenFiti(
        bilesen=bilesen,
        egim=float(egim),
        kesisim=float(kesisim),
        artiklar=tuple(float(a) for a in artiklar),
        artik_rms=artik_rms,
        r2=r2,
        tepki=tepki,
        tepki_veriyor=bool(tepki_veriyor),
        lineer_mi=lineer_mi,
    )


def mod_fitleri(
    olcumler: Iterable[tuple[KalibrasyonNoktasi, KontrolVektoru]],
    ayar: KalibrasyonYapilandirmasi,
    duzeltme: DuzeltmeYapilandirmasi,
) -> dict[str, ModFiti]:
    """Her mod için y'nin üç bileşeninin doğru fitlerini hesaplar.

    Ortak sıfır noktası, ölçülen bütün modların fitine eps = 0 verisi olarak
    dahil edilir.
    """
    olcum_listesi = list(olcumler)
    ortak: list[KontrolVektoru] = [y for n, y in olcum_listesi if n.mod == ORTAK_SIFIR]

    mod_verileri: dict[str, list[tuple[float, KontrolVektoru]]] = {}
    for nokta, y in olcum_listesi:
        if nokta.mod == ORTAK_SIFIR:
            continue
        mod_verileri.setdefault(nokta.mod, []).append((nokta.epsilon, y))

    if not mod_verileri:
        raise KalibrasyonHatasi("Hiçbir mod için ölçüm yok")

    fitler: dict[str, ModFiti] = {}
    for mod, veriler in mod_verileri.items():
        tum = list(veriler) + [(0.0, y) for y in ortak]
        tum.sort(key=lambda p: p[0])
        epsilonlar = np.array([e for e, _ in tum], dtype=float)
        if len(np.unique(epsilonlar)) < 2:
            raise KalibrasyonHatasi(f"{mod} modu için en az iki farklı epsilon gerekir")
        bilesen_fitleri: dict[str, BilesenFiti] = {}
        for indeks, ad in enumerate(Y_SATIRLARI):
            degerler = np.array([y.dizi()[indeks] for _, y in tum], dtype=float)
            bilesen_fitleri[ad] = _bilesen_fiti(
                ad,
                epsilonlar,
                degerler,
                ayar.lineerlik_r2_esigi,
                _bilesen_olcegi(ad, duzeltme),
            )
        fitler[mod] = ModFiti(
            mod=mod, epsilonlar=tuple(float(e) for e in epsilonlar), bilesenler=bilesen_fitleri
        )
    return fitler


# ---------------------------------------------------------------------------
# Sonuç
# ---------------------------------------------------------------------------
@dataclass
class KalibrasyonSonucu:
    R: np.ndarray
    fitler: dict[str, ModFiti]
    tekil_degerler: np.ndarray
    kosul_sayisi: float
    kosul_sayisi_olcekli: float
    r_eff_m: float
    m_sutunu_orani: float | None
    supheli: bool
    supheli_nedenleri: list[str]
    gradyen_hedefi_T_m: float
    modulator_acik: bool
    zaman_damgasi: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )

    # ------------------------------------------------------------------
    @property
    def tek_adimda_duzeltilebilir_ofset_m(self) -> float:
        """Adım başı bağıl değişim sınırıyla tek adımda düzeltilebilen en büyük ofset.

        H ve V modları aynı bobinleri paylaştığı için en kötü durum köşegendir:
        bobin başına |eps_H| + |eps_V| = sqrt(2) * |z| / R_eff.
        """
        return abs(self.r_eff_m) / math.sqrt(2.0)

    def ozet_metni(self) -> str:
        satirlar = [
            f"R_eff = {self.r_eff_m * 1e3:+.2f} mm",
            "Tekil değerler: " + ", ".join(f"{s:.4g}" for s in self.tekil_degerler),
            f"Koşul sayısı (ham): {self.kosul_sayisi:.2f}",
            f"Koşul sayısı (toleransa göre ölçekli): {self.kosul_sayisi_olcekli:.2f}",
        ]
        if self.m_sutunu_orani is not None:
            satirlar.append(f"M sütunu / (H,V,Q) oranı: {self.m_sutunu_orani:.4f}")
        satirlar.append(f"G_hedef = {self.gradyen_hedefi_T_m:.6f} T/m")
        satirlar.append(f"Modülatör: {'AÇIK' if self.modulator_acik else 'KAPALI'}")
        if self.supheli:
            satirlar.append("ŞÜPHELİ KALİBRASYON:")
            satirlar.extend(f"  - {neden}" for neden in self.supheli_nedenleri)
        else:
            satirlar.append("Kalibrasyon kontrolleri tamam.")
        return "\n".join(satirlar)

    # ------------------------------------------------------------------
    def sozluk(self) -> dict[str, object]:
        return {
            "zaman_damgasi": self.zaman_damgasi,
            "R": self.R.tolist(),
            "R_satirlari": list(Y_SATIRLARI),
            "R_sutunlari": [f"bobin_{i + 1}_bagil_akim" for i in range(BOBIN_SAYISI)],
            "tekil_degerler": self.tekil_degerler.tolist(),
            "kosul_sayisi": self.kosul_sayisi,
            "kosul_sayisi_olcekli": self.kosul_sayisi_olcekli,
            "r_eff_m": self.r_eff_m,
            "m_sutunu_orani": self.m_sutunu_orani,
            "supheli": self.supheli,
            "supheli_nedenleri": list(self.supheli_nedenleri),
            "gradyen_hedefi_T_m": self.gradyen_hedefi_T_m,
            "modulator_acik": self.modulator_acik,
            "fitler": {mod: fit.sozluk() for mod, fit in self.fitler.items()},
        }

    def kaydet(self, dosya: str | Path) -> Path:
        yol = Path(dosya)
        yol.parent.mkdir(parents=True, exist_ok=True)
        with yol.open("w", encoding="utf-8") as f:
            json.dump(self.sozluk(), f, indent=2, ensure_ascii=False)
        return yol

    @classmethod
    def yukle(cls, dosya: str | Path) -> "KalibrasyonSonucu":
        with Path(dosya).open(encoding="utf-8") as f:
            veri = json.load(f)
        fitler: dict[str, ModFiti] = {}
        for mod, fit_verisi in veri.get("fitler", {}).items():
            bilesenler = {
                ad: BilesenFiti(
                    bilesen=ad,
                    egim=float(b["egim"]),
                    kesisim=float(b["kesisim"]),
                    artiklar=tuple(float(x) for x in b.get("artiklar", ())),
                    artik_rms=float(b.get("artik_rms", 0.0)),
                    r2=None if b.get("r2") is None else float(b["r2"]),
                    tepki=float(b.get("tepki", 0.0)),
                    tepki_veriyor=bool(b.get("tepki_veriyor", False)),
                    lineer_mi=None if b.get("lineer_mi") is None else bool(b["lineer_mi"]),
                )
                for ad, b in fit_verisi.get("bilesenler", {}).items()
            }
            fitler[mod] = ModFiti(
                mod=mod,
                epsilonlar=tuple(float(e) for e in fit_verisi.get("epsilonlar", ())),
                bilesenler=bilesenler,
            )
        return cls(
            R=np.array(veri["R"], dtype=float),
            fitler=fitler,
            tekil_degerler=np.array(veri["tekil_degerler"], dtype=float),
            kosul_sayisi=float(veri["kosul_sayisi"]),
            kosul_sayisi_olcekli=float(veri["kosul_sayisi_olcekli"]),
            r_eff_m=float(veri["r_eff_m"]),
            m_sutunu_orani=None if veri.get("m_sutunu_orani") is None else float(veri["m_sutunu_orani"]),
            supheli=bool(veri["supheli"]),
            supheli_nedenleri=list(veri.get("supheli_nedenleri", [])),
            gradyen_hedefi_T_m=float(veri["gradyen_hedefi_T_m"]),
            modulator_acik=bool(veri.get("modulator_acik", False)),
            zaman_damgasi=str(veri.get("zaman_damgasi", "")),
        )


def _olcekli_kosul_sayisi(R: np.ndarray, duzeltme: DuzeltmeYapilandirmasi) -> float:
    """Satırları kendi toleransına bölerek koşul sayısı hesaplar."""
    olcekler = np.array(
        [
            1.0 / duzeltme.merkez_toleransi_m,
            1.0 / duzeltme.merkez_toleransi_m,
            1.0 / duzeltme.g_toleransi,
        ],
        dtype=float,
    )
    tekil = np.linalg.svd(olcekler[:, None] * R, compute_uv=False)
    if tekil[-1] <= 0:
        return math.inf
    return float(tekil[0] / tekil[-1])


def _m_sutunu_orani(fitler: dict[str, ModFiti]) -> float | None:
    """M modunun tepkisini, ilgili modların tepkisine göre boyutsuz olarak ölçer.

    Her bileşen kendi "sahibi" modla karşılaştırılır (x_c <-> H, y_c <-> V,
    g <-> Q); böylece farklı birimler birbirine karıştırılmaz.
    """
    if "M" not in fitler:
        return None
    esler = {"x_c": "H", "y_c": "V", "g": "Q"}
    oranlar: list[float] = []
    m_egim = fitler["M"].egim
    for indeks, bilesen in enumerate(Y_SATIRLARI):
        sahip = esler[bilesen]
        if sahip not in fitler:
            continue
        sahip_egim = abs(fitler[sahip].egim[indeks])
        if sahip_egim > 0:
            oranlar.append(abs(m_egim[indeks]) / sahip_egim)
    return max(oranlar) if oranlar else None


def kalibrasyonu_kur(
    fitler: dict[str, ModFiti],
    mod_bazi: ModBazi,
    ayar: KalibrasyonYapilandirmasi,
    duzeltme: DuzeltmeYapilandirmasi,
    gradyen_hedefi_T_m: float,
    modulator_acik: bool,
) -> KalibrasyonSonucu:
    """Mod fitlerinden R'yi kurar, tanıları hesaplar ve şüpheli olup olmadığına karar verir."""
    egimler = {mod: fit.egim for mod, fit in fitler.items()}
    R = mod_bazi.response_matrisi(egimler)
    tekil = np.linalg.svd(R, compute_uv=False)
    kosul = float(tekil[0] / tekil[-1]) if tekil[-1] > 0 else math.inf
    kosul_olcekli = _olcekli_kosul_sayisi(R, duzeltme)

    # R_eff = (dx_c / deps_H) / (dg / deps_Q)
    if "H" not in fitler or "Q" not in fitler:
        raise KalibrasyonHatasi("R_eff için H ve Q modu fitleri gerekir")
    dxc_deps_H = fitler["H"].bilesenler["x_c"].egim
    dg_deps_Q = fitler["Q"].bilesenler["g"].egim
    if dg_deps_Q == 0:
        raise KalibrasyonHatasi("dg/deps_Q sıfır; Q modu gradyeni değiştirmiyor")
    r_eff = dxc_deps_H / dg_deps_Q

    m_orani = _m_sutunu_orani(fitler)

    nedenler: list[str] = []
    if kosul_olcekli > ayar.kosul_sayisi_esigi:
        nedenler.append(
            f"Ölçekli koşul sayısı {kosul_olcekli:.1f} > eşik {ayar.kosul_sayisi_esigi:.1f}"
        )
    if m_orani is not None and m_orani > ayar.m_sutunu_esigi_bagil:
        nedenler.append(
            f"M sütunu küçük değil (oran {m_orani:.3f} > eşik {ayar.m_sutunu_esigi_bagil:.3f}); "
            "monopol modu dipole/gradyene sızdırıyor olabilir"
        )
    for mod, fit in fitler.items():
        if not fit.lineer_mi:
            bozuk = [
                f"{ad} (R^2 = {b.r2:.4f})"
                for ad, b in fit.bilesenler.items()
                if b.tepki_veriyor and b.lineer_mi is False and b.r2 is not None
            ]
            nedenler.append(f"{mod} modu fiti lineer değil: " + ", ".join(bozuk))
    # Beklenen mod-bileşen eşleşmesi: H -> x_c, V -> y_c, Q -> g
    for mod, beklenen in (("H", "x_c"), ("V", "y_c"), ("Q", "g")):
        if mod not in fitler:
            continue
        fit = fitler[mod]
        tepkiler = {ad: abs(b.egim) for ad, b in fit.bilesenler.items()}
        en_buyuk = max(tepkiler, key=lambda ad: tepkiler[ad] / _bilesen_olcegi(ad, duzeltme))
        if en_buyuk != beklenen:
            nedenler.append(
                f"{mod} modu en çok {en_buyuk} bileşenini etkiliyor ({beklenen} bekleniyordu); "
                "bobin numaralandırması ya da faz/eşlenik konvansiyonu ters olabilir"
            )

    return KalibrasyonSonucu(
        R=R,
        fitler=fitler,
        tekil_degerler=tekil,
        kosul_sayisi=kosul,
        kosul_sayisi_olcekli=kosul_olcekli,
        r_eff_m=r_eff,
        m_sutunu_orani=m_orani,
        supheli=bool(nedenler),
        supheli_nedenleri=nedenler,
        gradyen_hedefi_T_m=gradyen_hedefi_T_m,
        modulator_acik=modulator_acik,
    )


def _bilesen_olcegi(bilesen: str, duzeltme: DuzeltmeYapilandirmasi) -> float:
    """Bileşenin tolerans ölçeği; farklı birimleri karşılaştırmak için."""
    if bilesen == "g":
        return duzeltme.g_toleransi
    return duzeltme.merkez_toleransi_m
