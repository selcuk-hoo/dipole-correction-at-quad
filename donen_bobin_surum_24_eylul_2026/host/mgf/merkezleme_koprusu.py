"""Merkezleme programıyla dosya/kilit tabanlı köprü: parametreler, fizik, dosya.

Arayüzden bağımsızdır (yalnızca numpy ve PyYAML). Hem minimal ölçüm penceresi
(`host/merkezleme_olcer.py`) hem de makro sistemindeki MERKEZLEME_OLCUM komutu
bunu kullanır.

Protokol `merkezleme/olcum_kaynagi.py:DosyaGirisi` ile aynıdır: kilit dosyası
YOKSA "ölç", VARSA "veri hazır". Bu taraf veriyi geçici dosyaya yazıp atomik
olarak kilidin adına taşır; kilidi silmek merkezleme'nin işidir.

Fizik
-----
Merkezleme konvansiyonu: B_y + i*B_x = sum_n C_n (z/r_ref)^(n-1). Düz bir
bobinin iki iletkeni dönen çerçevede z1, z2 konumundaysa, bobinden geçen akı

    Phi(theta) = N * L * Re[ sum_n C_n * K_n * exp(i*n*theta) ],
    K_n = (z2^n - z1^n) / (n * r_ref^(n-1))

olur ve ölçülen gerilim V = -dPhi/dt = -omega * dPhi/dtheta. Gerilimin n.
Fourier bileşeni V_n ise

    C_n = i * V_n / (n * omega * N * L * K_n).

K_n bobin geometrisinden hesaplanır; böylece n=1 ile n=2 arasındaki duyarlılık
farkı (bobinin eksene uzaklığından gelen) doğru hesaba katılır ve merkez
z_c = -r_ref * C_1 / C_2 gerçek uzunluk biriminde çıkar. Elektronik kazanç
hatası iki harmoniği aynı oranda etkilediği için merkezi etkilemez.

İletken konumları K_1 = -i * genislik olacak şekilde seçilmiştir; bu, büyük
arayüzdeki magnetic_analysis.py'nin n=1 işaret kuralıyla (Bx, By) birebir aynı
dipolü verir.
"""
from __future__ import annotations

import json
import math
import csv
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import numpy as np
import yaml

_DONEN_BOBIN_KOKU = Path(__file__).resolve().parents[2]
REPO_KOKU = _DONEN_BOBIN_KOKU.parent
VARSAYILAN_PARAMETRE_DOSYASI = _DONEN_BOBIN_KOKU / "merkezleme_olcer.yaml"

# Firmware komut parametreleri (control_panel.py ile aynı tablolar)
KAZANC_INDEKSI = {1: 0, 2: 1, 4: 2, 8: 3, 16: 4, 32: 5}
HIZ_INDEKSI = {
    2.5: 0, 5: 1, 10: 2, 16.6: 3, 20: 4, 50: 5, 60: 6, 100: 7, 400: 8,
    1200: 9, 2400: 10, 4800: 11, 7200: 12, 14400: 13, 19200: 14, 38400: 15,
}
FILTRE_INDEKSI = {"Sinc1": 0, "Sinc2": 1, "Sinc3": 2, "Sinc4": 3, "FIR": 4}

HARMONIK_SAYISI = 6  # uydurulan ve raporlanan en yüksek mertebe


class ParametreHatasi(ValueError):
    pass


# ---------------------------------------------------------------------------
# Parametreler
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class BobinGeometrisi:
    sarim_sayisi: float
    uzunluk_m: float
    genislik_m: float
    eksene_uzaklik_m: float
    tip: str  # "teget" | "radyal"

    def iletken_konumlari(self) -> tuple[complex, complex]:
        """theta=0'da dönen çerçevedeki (z1, z2) iletken konumları (metre)."""
        d, w = self.eksene_uzaklik_m, self.genislik_m
        if self.tip == "teget":
            return complex(d, w / 2), complex(d, -w / 2)
        return complex(0.0, -(d - w / 2)), complex(0.0, -(d + w / 2))

    def duyarlilik(self, n: int, r_ref_m: float) -> complex:
        z1, z2 = self.iletken_konumlari()
        return (z2**n - z1**n) / (n * r_ref_m ** (n - 1))


@dataclass(frozen=True)
class Parametreler:
    ip: str
    port: int
    kanallar: dict[str, tuple[int, int]]
    varsayilan_kanal: str
    bobin: BobinGeometrisi
    kazanc: int
    ornekleme_sps: float
    filtre: str
    doyma_uyari_orani: float
    hiz_hz: float
    max_hiz_hz: float
    hiz_toleransi_hz: float
    oturma_suresi_s: float
    durma_zaman_asimi_s: float
    pencere_s: float
    faz_ofseti_derece: float
    r_ref_m: float
    kilit_dosyasi: Path
    kayit_dizini: Path
    merkezleme_yapilandirmasi: Path
    tema: str
    kaynak: Path

    @property
    def tam_olcek_V(self) -> float:
        return 2.5 / self.kazanc


def _repo_yolu(deger: str) -> Path:
    yol = Path(deger)
    return yol if yol.is_absolute() else REPO_KOKU / yol


def parametreleri_yukle(yol: Path | str | None = None) -> Parametreler:
    yol = Path(yol) if yol is not None else VARSAYILAN_PARAMETRE_DOSYASI
    with open(yol, encoding="utf-8") as f:
        v = yaml.safe_load(f)
    try:
        b, a, m, o = v["bobin"], v["adc"], v["motor"], v["olcum"]
        kanallar = {str(ad): (int(p[0]), int(p[1])) for ad, p in b["kanallar"].items()}
        p = Parametreler(
            ip=str(v["baglanti"]["ip"]),
            port=int(v["baglanti"]["port"]),
            kanallar=kanallar,
            varsayilan_kanal=str(b["varsayilan_kanal"]),
            bobin=BobinGeometrisi(
                sarim_sayisi=float(b["sarim_sayisi"]),
                uzunluk_m=float(b["uzunluk_mm"]) * 1e-3,
                genislik_m=float(b["genislik_mm"]) * 1e-3,
                eksene_uzaklik_m=float(b["eksene_uzaklik_mm"]) * 1e-3,
                tip=str(b["tip"]),
            ),
            kazanc=int(a["kazanc"]),
            ornekleme_sps=float(a["ornekleme_sps"]),
            filtre=str(a["filtre"]),
            doyma_uyari_orani=float(a["doyma_uyari_orani"]),
            hiz_hz=float(m["hiz_hz"]),
            max_hiz_hz=float(m["max_hiz_hz"]),
            hiz_toleransi_hz=float(m["hiz_toleransi_hz"]),
            oturma_suresi_s=float(m["oturma_suresi_s"]),
            durma_zaman_asimi_s=float(m["durma_zaman_asimi_s"]),
            pencere_s=float(o["pencere_s"]),
            faz_ofseti_derece=float(o["faz_ofseti_derece"]),
            r_ref_m=float(o["r_ref_mm"]) * 1e-3,
            kilit_dosyasi=_repo_yolu(o["kilit_dosyasi"]),
            kayit_dizini=_repo_yolu(o["kayit_dizini"]),
            merkezleme_yapilandirmasi=_repo_yolu(o["merkezleme_yapilandirmasi"]),
            tema=str(v.get("arayuz", {}).get("tema", "koyu")),
            kaynak=yol,
        )
    except (KeyError, TypeError, ValueError, IndexError) as hata:
        raise ParametreHatasi(f"{yol}: eksik ya da hatalı parametre: {hata!r}") from hata

    if p.varsayilan_kanal not in p.kanallar:
        raise ParametreHatasi(f"varsayilan_kanal '{p.varsayilan_kanal}' kanallar listesinde yok")
    if p.bobin.tip not in ("teget", "radyal"):
        raise ParametreHatasi("bobin.tip 'teget' ya da 'radyal' olmalı")
    if p.kazanc not in KAZANC_INDEKSI:
        raise ParametreHatasi(f"adc.kazanc {sorted(KAZANC_INDEKSI)} değerlerinden biri olmalı")
    if p.ornekleme_sps not in HIZ_INDEKSI:
        raise ParametreHatasi(f"adc.ornekleme_sps desteklenmiyor: {p.ornekleme_sps}")
    if p.filtre not in FILTRE_INDEKSI:
        raise ParametreHatasi(f"adc.filtre {list(FILTRE_INDEKSI)} değerlerinden biri olmalı")
    if not 0 < p.hiz_hz <= p.max_hiz_hz:
        raise ParametreHatasi("motor.hiz_hz 0'dan büyük ve max_hiz_hz'den küçük olmalı")
    if p.tema not in ("acik", "koyu"):
        raise ParametreHatasi("arayuz.tema 'acik' ya da 'koyu' olmalı")
    return p


def tutarlilik_uyarilari(p: Parametreler) -> list[str]:
    """merkezleme yapılandırmasıyla uyuşmazlıklar (uyarı metinleri)."""
    yol = p.merkezleme_yapilandirmasi
    if not yol.exists():
        return [f"merkezleme yapılandırması bulunamadı ({yol}); r_ref/birim kontrol edilemedi"]
    with open(yol, encoding="utf-8") as f:
        h = (yaml.safe_load(f) or {}).get("harmonikler", {})
    uyarilar = []
    r_ref_mm = h.get("r_ref_mm")
    if r_ref_mm is not None and not math.isclose(float(r_ref_mm) * 1e-3, p.r_ref_m, rel_tol=1e-9):
        uyarilar.append(
            f"r_ref uyuşmuyor: burada {p.r_ref_m * 1e3:g} mm, merkezleme'de {r_ref_mm} mm"
        )
    if h.get("birim", "T") != "T":
        uyarilar.append(
            f"merkezleme harmonikler.birim = {h.get('birim')}; bu program Tesla yazar (T olmalı)"
        )
    return uyarilar


# ---------------------------------------------------------------------------
# Fizik
# ---------------------------------------------------------------------------
@dataclass(frozen=True, eq=False)
class OlcumSonucu:
    harmonikler: tuple[complex, ...]  # C_1..C_N (T), merkezleme konvansiyonunda (r_ref'te)
    hiz_hz: float
    tur_sayisi: int
    ornek_sayisi: int
    tepe_V: float
    r_ref_m: float
    # Çizim için: pencerenin (ofsetli) açısı, sürüklenmesi çıkarılmış gerilim
    # ve uydurmanın Fourier katsayıları [sabit, a_1, b_1, ..., a_N, b_N]
    aci_derece: np.ndarray = field(repr=False, default_factory=lambda: np.empty(0))
    gerilim_V: np.ndarray = field(repr=False, default_factory=lambda: np.empty(0))
    fourier: np.ndarray = field(repr=False, default_factory=lambda: np.empty(0))

    @property
    def c1(self) -> complex:
        return self.harmonikler[0]

    @property
    def c2(self) -> complex:
        return self.harmonikler[1]

    def birim(self, n: int) -> complex:
        """C_n / |C_2| * 1e4 ("units"): b_n + i*a_n, ana alana göre."""
        return self.harmonikler[n - 1] / abs(self.c2) * 1e4

    def uydurma(self, aci_derece: np.ndarray) -> np.ndarray:
        """Uydurulan eğri (sürüklenmesiz), verilen açılarda."""
        teta = np.radians(aci_derece)
        v = np.full_like(teta, self.fourier[0], dtype=float)
        for n in range(1, len(self.harmonikler) + 1):
            v += self.fourier[2 * n - 1] * np.cos(n * teta) + self.fourier[2 * n] * np.sin(n * teta)
        return v

    def dosya_verisi(self) -> dict[str, float]:
        return {"b0": self.c1.real, "a0": self.c1.imag, "b1": self.c2.real, "a1": self.c2.imag}

    @property
    def gradyen_T_m(self) -> float:
        return abs(self.c2) / self.r_ref_m

    @property
    def merkez_m(self) -> complex:
        return -self.r_ref_m * self.c1 / self.c2 if self.c2 != 0 else complex("nan")


def tam_tur_penceresi(aci_derece: np.ndarray) -> tuple[int, int]:
    """Son örnekten geriye doğru TAM tur sayısı kadar örneği kapsayan
    pencerenin (başlangıç indeksi, tur sayısı)."""
    teta = np.unwrap(np.radians(np.asarray(aci_derece, dtype=np.float64)))
    gidilen = np.abs(teta - teta[-1])
    tur = int(gidilen[0] // (2 * math.pi))
    if tur < 1:
        return 0, 0
    # gidilen geriye doğru artar; tam tur sınırını geçen son indeks
    baslangic = int(np.nonzero(gidilen >= tur * 2 * math.pi)[0][-1])
    return baslangic, tur


def olcum_hesapla(
    aci_derece: np.ndarray,
    gerilim_V: np.ndarray,
    hiz_hz: float,
    bobin: BobinGeometrisi,
    r_ref_m: float,
    faz_ofseti_derece: float = 0.0,
) -> OlcumSonucu:
    """Bobin gerilimi ve enkoder açısından C_1..C_6'yı (Tesla) hesaplar."""
    aci = np.asarray(aci_derece, dtype=np.float64)
    v = np.asarray(gerilim_V, dtype=np.float64)
    if len(v) < 100 or len(v) != len(aci):
        raise ValueError("Yetersiz ya da uyumsuz veri")
    if abs(hiz_hz) < 0.1:
        raise ValueError(f"Motor dönmüyor (hız {hiz_hz:.2f} Hz)")
    bas, tur = tam_tur_penceresi(aci)
    if tur < 1:
        raise ValueError("Pencerede tam bir tur bile yok")
    aci, v = aci[bas:-1], v[bas:-1]

    teta = np.radians(aci - faz_ofseti_derece)
    # Düz Fourier toplamı yerine en küçük kareler: n=2, n=1'den ~1000 kat
    # büyük olduğundan pencere sınırındaki tek örneklik kayma bile n=1'e
    # belirgin sızıntı yapar. Uydurmada sızıntı yoktur; sabit ve doğrusal
    # sürüklenme terimleri ile üst harmonikler de modele dahildir.
    surukleme = np.linspace(-1.0, 1.0, len(teta))
    sutunlar = [np.ones_like(teta), surukleme]
    for n in range(1, HARMONIK_SAYISI + 1):
        sutunlar += [np.cos(n * teta), np.sin(n * teta)]
    katsayi, *_ = np.linalg.lstsq(np.column_stack(sutunlar), v, rcond=None)
    omega = 2 * math.pi * abs(hiz_hz)
    harmonikler = []
    for n in range(1, HARMONIK_SAYISI + 1):
        a_n, b_n = katsayi[2 * n], katsayi[2 * n + 1]
        v_n = complex(a_n, -b_n)
        k_n = bobin.duyarlilik(n, r_ref_m)
        harmonikler.append(1j * v_n / (n * omega * bobin.sarim_sayisi * bobin.uzunluk_m * k_n))
    return OlcumSonucu(
        harmonikler=tuple(harmonikler),
        hiz_hz=hiz_hz,
        tur_sayisi=tur,
        ornek_sayisi=len(v),
        tepe_V=float(np.max(np.abs(v))),
        r_ref_m=r_ref_m,
        aci_derece=np.degrees(teta) % 360.0,
        gerilim_V=v - katsayi[1] * surukleme,
        fourier=np.delete(katsayi, 1),
    )


def referans_faz_ofseti(sonuc: OlcumSonucu, mevcut_ofset_derece: float) -> float:
    """Referans dipol mıknatısının alanını saf normal ve pozitif (b0 > 0,
    a0 = 0) gösterecek yeni faz ofseti."""
    return (mevcut_ofset_derece - math.degrees(np.angle(sonuc.c1))) % 360.0


# ---------------------------------------------------------------------------
# Dosya
# ---------------------------------------------------------------------------
def kilide_yaz(sonuc: OlcumSonucu, kilit_yolu: Path) -> None:
    kilit_yolu = Path(kilit_yolu)
    kilit_yolu.parent.mkdir(parents=True, exist_ok=True)
    gecici = kilit_yolu.with_suffix(".tmp")
    gecici.write_text(json.dumps(sonuc.dosya_verisi()), encoding="utf-8")
    gecici.replace(kilit_yolu)


class OlcumKaydi:
    """Oturum başına bir CSV; dosya ilk satırda oluşturulur. Her satır bir
    ölçüm: koşullar ve C_1..C_N'nin normal/skew bileşenleri (Tesla)."""

    def __init__(self, dizin: Path) -> None:
        self.dizin = Path(dizin)
        self.yol: Path | None = None
        self.satir_sayisi = 0

    def ekle(self, sonuc: OlcumSonucu, tur: str, kanal: str, faz_ofseti_derece: float) -> None:
        yeni = self.yol is None
        if yeni:
            self.dizin.mkdir(parents=True, exist_ok=True)
            self.yol = self.dizin / f"olcum_{datetime.now():%Y-%m-%d_%H%M%S}.csv"
        with open(self.yol, "a", newline="", encoding="utf-8") as f:
            yazici = csv.writer(f)
            if yeni:
                yazici.writerow(
                    ["zaman", "tur", "kanal", "hiz_hz", "tur_sayisi", "tepe_mV", "faz_ofseti_derece",
                     "G_T_m", "x_c_um", "y_c_um"]
                    + [f"{ad}{n}_T" for n in range(1, len(sonuc.harmonikler) + 1) for ad in ("b", "a")]
                )
            z = sonuc.merkez_m * 1e6
            yazici.writerow(
                [datetime.now().isoformat(timespec="seconds"), tur, kanal, f"{sonuc.hiz_hz:.4f}",
                 sonuc.tur_sayisi, f"{sonuc.tepe_V * 1e3:.4f}", f"{faz_ofseti_derece:.3f}",
                 f"{sonuc.gradyen_T_m:.6g}", f"{z.real:.3f}", f"{z.imag:.3f}"]
                + [f"{x:.6e}" for c in sonuc.harmonikler for x in (c.real, c.imag)]
            )
        self.satir_sayisi += 1


def kuadrupol_olcumu_yaz(engine, p: Parametreler) -> OlcumSonucu:
    """Büyük arayüzün makro komutu için: o anki kanalın son `pencere_s`
    saniyelik verisinden ölçer ve kilide yazar. Kanal ve motor hızını makro
    betiği önceden ayarlamış olmalıdır."""
    n_ornek = max(100, int(p.pencere_s * engine.live_rate_sps * 1.05))
    enc, adc = engine.get_latest_data(n_ornek)
    if engine.current_data_mode != 1:
        raise RuntimeError("Veri kipi Voltage olmalı (RAW kipte gerilim bilinmiyor)")
    ham_aci = (np.asarray(enc) + engine.phase_offset_deg) % 360.0
    sonuc = olcum_hesapla(
        ham_aci, adc, engine.motor_speed, p.bobin, p.r_ref_m, p.faz_ofseti_derece
    )
    kilide_yaz(sonuc, p.kilit_dosyasi)
    return sonuc
