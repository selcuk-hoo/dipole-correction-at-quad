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

olur. Ölçülen gerilim V = -dPhi/dt, o anki açısal hızla orantılıdır; hızı
sabit varsaymak tehlikelidir: tur içindeki %1'lik bir hız dalgalanması güçlü
n = 2'yi n = 1 ve n = 3'e karıştırır ve yüzlerce µm sahte merkez kayması
üretir. Bu yüzden gerilim zamana göre integre edilerek akı bulunur
(ADC örnekleri zamanda düzgün aralıklıdır):

    Phi(t) = -integral V dt,

ve Phi, enkoder açısına karşı uydurulur. Phi'nin n. Fourier bileşeni Phi_n ise

    C_n = Phi_n / (N * L * K_n).

Hız hiç kullanılmaz; dönüş yönü ve hız dalgalanması sonucu etkilemez.

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
import dataclasses
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

HARMONIK_SAYISI = 6  # raporlanan en yüksek mertebe
# Uydurmaya alınan en yüksek mertebe. Raporlanmayan üst mertebeler (örneğin
# kuadrupolün izinli n = 10'u) modelde olmazsa pencere kenarından raporlanan
# mertebelere sızar ve artığı şişirir.
UYDURMA_HARMONIK_SAYISI = 15
_PARCA = 50_000  # normal denklemler bu kadar örneklik parçalarla kurulur (bellek)
_SURUKLENME_DERECESI = 3  # akıdaki zaman polinomu: ADC ofsetinin integrali ve sürüklenmesi
_OKUMA_SAATI_SAPMA_SINIRI = 0.45  # örnek; düzgün varış titreşimi ~0.29 (0..1 tekdüze)
_SICRAMA_PENCERESI = 41  # okuma; okuma saati artığının kayan medyanı bu kadar okumada


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
    gecikme_s: float
    artik_esigi: float
    sicrama_esigi: float
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
            gecikme_s=float(o.get("gecikme_ms", 0.0)) * 1e-3,
            artik_esigi=float(o.get("artik_esigi", 5e-3)),
            sicrama_esigi=float(o.get("sicrama_esigi", 0.6)),
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
    if not 0 < p.artik_esigi < 1:
        raise ParametreHatasi("olcum.artik_esigi 0 ile 1 arasında olmalı")
    if abs(p.gecikme_s) > 0.05:
        raise ParametreHatasi("olcum.gecikme_ms mutlak değerce 50 ms'den küçük olmalı")
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
    # Akı uydurmasının artığının rms'i / harmonik içeriğin rms'i. Sağlıklı
    # bir ölçümde gürültü düzeyindedir (~1e-3); büyükse açı, kanal, doyma ya da
    # örnek kaybı gibi bir sorun vardır.
    artik_orani: float = 0.0
    aci_yontemi: str = ""  # açı merdiveninin nasıl giderildiği
    cift_yon: bool = False  # iki zıt yönlü ölçümün birleşimi mi
    # ADC-enkoder zaman gecikmesi: tek yönde analizde kullanılan değer, çift
    # yönde iki yönün farkından ölçülen değer
    gecikme_s: float = 0.0
    # Okuma saati sıçraması (örnek): enkoder okumalarının düzenli saatine göre
    # ADC örnek sayısındaki kalıcı kayma. Kaybolan her örnek ~1 ekler;
    # sağlıklı veride ~0.2. Merdiven yoksa ölçülemez (nan).
    saat_sicramasi: float = math.nan
    # Çizim için: pencerenin (ofsetli) açısı, sürüklenmesi çıkarılmış akı
    # ve uydurmanın Fourier katsayıları [sabit, a_1, b_1, ..., a_M, b_M]
    # (M = UYDURMA_HARMONIK_SAYISI >= raporlanan harmonik sayısı)
    aci_derece: np.ndarray = field(repr=False, default_factory=lambda: np.empty(0))
    aki_Vs: np.ndarray = field(repr=False, default_factory=lambda: np.empty(0))
    fourier: np.ndarray = field(repr=False, default_factory=lambda: np.empty(0))

    @property
    def c1(self) -> complex:
        return self.harmonikler[0]

    @property
    def c2(self) -> complex:
        return self.harmonikler[1]

    def uydurma(self, aci_derece: np.ndarray) -> np.ndarray:
        """Uydurulan akı eğrisi (sürüklenmesiz, V·s), verilen açılarda."""
        teta = np.radians(aci_derece)
        v = np.full_like(teta, self.fourier[0], dtype=float)
        for n in range(1, (len(self.fourier) - 1) // 2 + 1):
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


def _tam_tur(acilmis: np.ndarray) -> tuple[int, int]:
    gidilen = np.abs(acilmis - acilmis[-1])
    tur = int(gidilen[0] // (2 * math.pi))
    if tur < 1:
        return 0, 0
    # gidilen geriye doğru artar; tam tur sınırını geçen son indeks
    return int(np.nonzero(gidilen >= tur * 2 * math.pi)[0][-1]), tur


def tam_tur_penceresi(aci_derece: np.ndarray) -> tuple[int, int]:
    """Son örnekten geriye doğru TAM tur sayısı kadar örneği kapsayan
    pencerenin (başlangıç indeksi, tur sayısı)."""
    return _tam_tur(np.unwrap(np.radians(np.asarray(aci_derece, dtype=np.float64))))


def kubik_enterpolasyon(x: np.ndarray, xp: np.ndarray, yp: np.ndarray) -> np.ndarray:
    """Kübik Hermite enterpolasyonu (egimler merkezi farklardan). Doğrusal
    enterpolasyon, okumalar arası (~1 ms) hız dalgalanmasının eğriliğini
    izleyemez ve merkezde µm düzeyinde hata bırakır; kübik izler."""
    egim = np.gradient(yp, xp)
    j = np.clip(np.searchsorted(xp, x, side="right") - 1, 0, len(xp) - 2)
    h = xp[j + 1] - xp[j]
    s = np.clip((x - xp[j]) / h, 0.0, 1.0)
    s2, s3 = s * s, s * s * s
    return (
        (2 * s3 - 3 * s2 + 1) * yp[j] + (s3 - 2 * s2 + s) * h * egim[j]
        + (-2 * s3 + 3 * s2) * yp[j + 1] + (s3 - s2) * h * egim[j + 1]
    )


def aci_merdivenini_duzelt(acilmis: np.ndarray) -> tuple[np.ndarray, int, int, str, float]:
    """Enkoder açısındaki merdiveni giderir.

    Stator enkoderi ~1 ms'de bir okuyup rotora gönderir; rotor her ADC örneğine
    son aldığı değeri yazar (firmware'de enterpolasyon yok). Birkaç ardışık örnek
    aynı açıyı taşır ve açı 0..1 ms (23 Hz'de 0..8°) eskir; bu n >= 3'ü bozar.

    Her yeni değerin geldiği ilk örnek ("taze nokta") o değerin varış anıdır.
    Okumalar statorun milisaniye saatine bağlı olduğundan düzenlidir: taze
    noktaların indeksine bir doğru uydurmak gerçek okuma anlarını örnek altı
    hassasiyetle verir ("okuma saati"). Okumalar düzenli değilse (uydurmanın
    sapması büyükse) taze noktalar arasında düz enterpolasyon yapılır. Kalan
    sabit gecikme bir açı ofseti gibidir (referansla ya da çift yönlü ölçümle
    giderilir).

    Aynı uydurma örnek kaybını da gösterir: okumalar stator saatine bağlı
    düzenli aralıklarla gelir; aradan bir ADC örneği kaybolursa sonraki bütün
    taze noktalar bir örnek erken görünür. Uydurmanın artığının kayan medyanındaki
    tepe-tepe değişim ("sıçrama") bunu tekil titreşimlerden ayırır.

    Dönen (açı, ilk, son, yöntem, sıçrama): yalnızca ilk..son arasındaki
    örnekler geçerli.
    """
    taze = np.flatnonzero(np.diff(acilmis) != 0) + 1
    if len(taze) < 4:
        return acilmis, 0, len(acilmis), "yok", math.nan
    d = np.diff(taze)
    # Okuma aralığı (örnek): ortalama; atlanan okumalar (2x, 3x aralık)
    # yuvarlanarak sayılır ve ortalama bir kez yeniden hesaplanır. (Medyan
    # kullanılmaz: okuma başına 2.4 örnekte medyan 2 olur ve 3'lük aralıklar
    # iki okuma sayılır.)
    adim = float(np.mean(d))
    sayi = np.maximum(1.0, np.rint(d / adim))
    adim = float(np.sum(d) / np.sum(sayi))
    if adim > 1.5:
        j = np.concatenate(([0.0], np.cumsum(np.maximum(1.0, np.rint(d / adim)))))
        a = np.column_stack([np.ones_like(j), j])
        katsayi, *_ = np.linalg.lstsq(a, taze.astype(float), rcond=None)
        konum = a @ katsayi
        artik = taze - konum
        sicrama = math.nan
        if len(artik) >= 2 * _SICRAMA_PENCERESI:
            kayan = np.lib.stride_tricks.sliding_window_view(artik, _SICRAMA_PENCERESI)
            sicrama = float(np.ptp(np.median(kayan, axis=1)))
        if np.std(artik) <= _OKUMA_SAATI_SAPMA_SINIRI:
            # Taze nokta, varıştan SONRAKİ ilk örnektir (0..1 örnek geç; ortalama
            # yarım örnek): okuma anı için yarım örnek geri gidilir. Kalan iletim
            # gecikmesi sabittir (çift yönlü ölçümle ölçülür).
            konum = konum - 0.5
            ilk, son = int(np.ceil(konum[0])), int(np.floor(konum[-1])) + 1
            duz = kubik_enterpolasyon(np.arange(len(acilmis), dtype=float), konum, acilmis[taze])
            return duz, ilk, son, "okuma saati", sicrama
    else:
        sicrama = math.nan
    duz = kubik_enterpolasyon(np.arange(len(acilmis), dtype=float), taze.astype(float), acilmis[taze])
    return duz, int(taze[0]), int(taze[-1]) + 1, "enterpolasyon", sicrama


def olcum_hesapla(
    aci_derece: np.ndarray,
    gerilim_V: np.ndarray,
    ornekleme_sps: float,
    bobin: BobinGeometrisi,
    r_ref_m: float,
    faz_ofseti_derece: float = 0.0,
    aci_duzelt: bool = True,
    gecikme_s: float = 0.0,
) -> OlcumSonucu:
    """Bobin gerilimi ve enkoder açısından C_1..C_6'yı (Tesla) hesaplar.

    `gerilim_V` zamanda düzgün aralıklı (1/ornekleme_sps) ve örnek kaybı
    olmadan gelmelidir; akı bunun zaman integralidir. `gecikme_s`: gerilimin
    açıya göre ne kadar eski olduğu (ADC filtresi - enkoder iletimi; çift
    yönlü ölçümle bulunur); açı bu kadar geriye kaydırılır."""
    aci = np.asarray(aci_derece, dtype=np.float64)
    v = np.asarray(gerilim_V, dtype=np.float64)
    if len(v) < 100 or len(v) != len(aci):
        raise ValueError("Yetersiz ya da uyumsuz veri")
    dt = 1.0 / ornekleme_sps
    # Akı: yamuk kuralıyla integral (dikdörtgen kuralı yarım örneklik kayma yapar)
    aki = -dt * (np.cumsum(v) - 0.5 * v - 0.5 * v[0])
    acilmis = np.unwrap(np.radians(aci))
    yontem, sicrama = "yok", math.nan
    if aci_duzelt:
        acilmis, ilk, son, yontem, sicrama = aci_merdivenini_duzelt(acilmis)
        acilmis, aki, v = acilmis[ilk:son], aki[ilk:son], v[ilk:son]
    if gecikme_s:
        # Her gerilim örneği, açı örneğinden gecikme_s önceki ana aittir
        kayma = gecikme_s / dt
        sira = np.arange(len(acilmis), dtype=float)
        acilmis = np.interp(sira - kayma, sira, acilmis)
        kenar = int(math.ceil(abs(kayma))) + 1
        acilmis, aki, v = acilmis[kenar:-kenar], aki[kenar:-kenar], v[kenar:-kenar]
    bas, tur = _tam_tur(acilmis)
    if tur < 1:
        raise ValueError("Pencerede tam bir tur bile yok (motor dönüyor mu?)")
    acilmis, aki, v = acilmis[bas:-1], aki[bas:-1], v[bas:-1]
    hiz_hz = (acilmis[-1] - acilmis[0]) / (2 * math.pi) / (len(acilmis) * dt)
    teta = acilmis - math.radians(faz_ofseti_derece)

    # En küçük kareler: sabit + zaman polinomu (ADC ofsetinin integrali ve
    # sürüklenmesi) + 1..M harmonik. Uzun pencerelerde belleği sınırlamak için
    # normal denklemler parça parça kurulur.
    zaman = np.linspace(-1.0, 1.0, len(teta))
    m_pol = _SURUKLENME_DERECESI + 1
    m_sutun = m_pol + 2 * UYDURMA_HARMONIK_SAYISI
    n_dizi = np.arange(1, UYDURMA_HARMONIK_SAYISI + 1)

    def tasarim(dilim: slice) -> np.ndarray:
        t = teta[dilim]
        a = np.empty((len(t), m_sutun))
        a[:, :m_pol] = zaman[dilim, None] ** np.arange(m_pol)
        a[:, m_pol::2] = np.cos(np.outer(t, n_dizi))
        a[:, m_pol + 1::2] = np.sin(np.outer(t, n_dizi))
        return a

    ata, atv = np.zeros((m_sutun, m_sutun)), np.zeros(m_sutun)
    for i in range(0, len(teta), _PARCA):
        a = tasarim(slice(i, i + _PARCA))
        ata += a.T @ a
        atv += a.T @ aki[i:i + _PARCA]
    katsayi = np.linalg.solve(ata, atv)
    artik_kare = harmonik_kare = 0.0
    for i in range(0, len(teta), _PARCA):
        a = tasarim(slice(i, i + _PARCA))
        artik_kare += float(np.sum((aki[i:i + _PARCA] - a @ katsayi) ** 2))
        harmonik_kare += float(np.sum((a[:, m_pol:] @ katsayi[m_pol:]) ** 2))
    artik_orani = math.sqrt(artik_kare / harmonik_kare) if harmonik_kare > 0 else math.inf

    harmonikler = []
    for n in range(1, HARMONIK_SAYISI + 1):
        a_n, b_n = katsayi[m_pol + 2 * (n - 1)], katsayi[m_pol + 2 * (n - 1) + 1]
        # Yamuk kuralı, frekansı f olan bir bileşeni (x/2)·cot(x/2) kadar
        # küçültür (x = 2π·f·dt; 23 Hz'de n = 2 için 1.3e-4, n = 6 için 1.2e-3).
        x = 2 * math.pi * n * abs(hiz_hz) * dt
        aki_n = complex(a_n, -b_n) * (math.tan(x / 2) / (x / 2))
        harmonikler.append(aki_n / (bobin.sarim_sayisi * bobin.uzunluk_m * bobin.duyarlilik(n, r_ref_m)))
    surukleme = np.column_stack([zaman ** p for p in range(m_pol)]) @ katsayi[:m_pol]
    return OlcumSonucu(
        harmonikler=tuple(harmonikler),
        hiz_hz=hiz_hz,
        tur_sayisi=tur,
        ornek_sayisi=len(v),
        tepe_V=float(np.max(np.abs(v))),
        r_ref_m=r_ref_m,
        artik_orani=artik_orani,
        aci_yontemi=yontem,
        gecikme_s=gecikme_s,
        saat_sicramasi=sicrama,
        aci_derece=np.degrees(teta) % 360.0,
        aki_Vs=aki - surukleme,
        fourier=np.concatenate(([0.0], katsayi[m_pol:])),
    )


def cift_yon_birlestir(ileri: OlcumSonucu, geri: OlcumSonucu) -> OlcumSonucu:
    """İki zıt yönlü ölçümü birleştirir; sabit zaman gecikmesini ölçer.

    ADC örneği ile enkoder okuması arasındaki sabit zaman gecikmesi L (ADC
    filtresi, RS485 iletimi) açıyı ω·L kadar kaydırır: C_n bir yönde
    e^{-inψ}, öbür yönde e^{+inψ} ile döner (ψ = |ω|·L). Yöne bağlı sabit bir
    açı farkı (mil burulması, boşluk) da aynı biçimdedir ve ψ'ye katılır.
    ψ, iki yön arasındaki faz farkından bulunur: e^{2inψ}. Fazı en iyi ölçülen
    harmonik kullanılır (akıdaki genliği × n en büyük olan): kuadrupolde n = 2,
    referans dipolde n = 1. Her yön düzeltilip ortalaması alınır.
    """
    if (ileri.hiz_hz > 0) == (geri.hiz_hz > 0):
        raise ValueError("Çift yön için ölçümler zıt yönlü olmalı")
    if ileri.hiz_hz < 0:
        ileri, geri = geri, ileri

    def aki_genligi(s: OlcumSonucu, n: int) -> float:
        return math.hypot(s.fourier[2 * n - 1], s.fourier[2 * n])

    n_faz = max(
        range(1, len(ileri.harmonikler) + 1),
        key=lambda n: n * min(aki_genligi(ileri, n), aki_genligi(geri, n)),
    )
    psi = float(np.angle(geri.harmonikler[n_faz - 1] / ileri.harmonikler[n_faz - 1])) / (2 * n_faz)
    harmonikler = tuple(
        0.5 * (a * np.exp(1j * n * psi) + b * np.exp(-1j * n * psi))
        for n, (a, b) in enumerate(zip(ileri.harmonikler, geri.harmonikler), start=1)
    )
    return dataclasses.replace(
        ileri,
        harmonikler=harmonikler,
        ornek_sayisi=ileri.ornek_sayisi + geri.ornek_sayisi,
        tur_sayisi=ileri.tur_sayisi + geri.tur_sayisi,
        tepe_V=max(ileri.tepe_V, geri.tepe_V),
        artik_orani=max(ileri.artik_orani, geri.artik_orani),
        saat_sicramasi=float(np.fmax(ileri.saat_sicramasi, geri.saat_sicramasi)),
        gecikme_s=psi / (2 * math.pi * abs(ileri.hiz_hz)),
        cift_yon=True,
    )


def cift_yon_hesapla(
    ileri: tuple[np.ndarray, np.ndarray],
    geri: tuple[np.ndarray, np.ndarray],
    ornekleme_sps: float,
    bobin: BobinGeometrisi,
    r_ref_m: float,
    faz_ofseti_derece: float = 0.0,
    gecikme_s: float = 0.0,
) -> OlcumSonucu:
    """İki zıt yönlü ham veriden ((açı, gerilim) çiftleri) birleşik ölçüm.

    Önce verilen gecikmeyle analiz edilir ve kalan gecikme iki yön arasındaki
    faz farkından ölçülür; sonra toplam gecikmeyle analiz tekrarlanır. Sonucun
    `gecikme_s` alanı toplam (ölçülen) gecikmedir."""
    def hesapla(gecikme: float) -> OlcumSonucu:
        return cift_yon_birlestir(*(
            olcum_hesapla(a, v, ornekleme_sps, bobin, r_ref_m, faz_ofseti_derece, gecikme_s=gecikme)
            for a, v in (ileri, geri)
        ))

    # Kalan gecikme birleştirmede ölçülür (faz farkından); ikinci geçişte
    # açı zamanda kaydırılarak uygulanır. Sabit hızda ikisi eşdeğerdir; hız
    # dalgalanırken yalnızca zaman kaydırması doğrudur.
    gecikme_s += hesapla(gecikme_s).gecikme_s
    sonuc = hesapla(gecikme_s)
    return dataclasses.replace(sonuc, gecikme_s=gecikme_s + sonuc.gecikme_s)


def saglik_sorunlari(sonuc: OlcumSonucu, p: "Parametreler") -> list[str]:
    """Ölçümü merkezleme'ye yazmayı engelleyen sorunlar (boşsa sağlıklı)."""
    sorunlar = []
    if not sonuc.artik_orani <= p.artik_esigi:
        sorunlar.append(
            f"uydurma artığı {sonuc.artik_orani:.1e} > eşik {p.artik_esigi:.1e} "
            "(açı, kanal, doyma ya da örnek kaybı?)"
        )
    if sonuc.saat_sicramasi > p.sicrama_esigi:  # nan: ölçülemedi, engellemez
        sorunlar.append(
            f"okuma saati sıçraması {sonuc.saat_sicramasi:.2f} örnek > eşik {p.sicrama_esigi:.2f} "
            "(büyük olasılıkla ADC örneği kaybı)"
        )
    return sorunlar


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
                     "gecikme_ms", "cift_yon", "artik_orani", "saat_sicramasi", "aci_yontemi", "G_T_m", "x_c_um", "y_c_um"]
                    + [f"{ad}{n}_T" for n in range(1, len(sonuc.harmonikler) + 1) for ad in ("b", "a")]
                )
            z = sonuc.merkez_m * 1e6
            yazici.writerow(
                [datetime.now().isoformat(timespec="seconds"), tur, kanal, f"{sonuc.hiz_hz:.4f}",
                 sonuc.tur_sayisi, f"{sonuc.tepe_V * 1e3:.4f}", f"{faz_ofseti_derece:.3f}",
                 f"{sonuc.gecikme_s * 1e3:.4f}", int(sonuc.cift_yon), f"{sonuc.artik_orani:.2e}",
                 f"{sonuc.saat_sicramasi:.3f}", sonuc.aci_yontemi, f"{sonuc.gradyen_T_m:.6g}", f"{z.real:.3f}", f"{z.imag:.3f}"]
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
        ham_aci, adc, engine.live_rate_sps, p.bobin, p.r_ref_m, p.faz_ofseti_derece,
        gecikme_s=p.gecikme_s,
    )
    sorunlar = saglik_sorunlari(sonuc, p)
    if sorunlar:
        raise RuntimeError("Ölçüm yazılmadı: " + "; ".join(sorunlar))
    kilide_yaz(sonuc, p.kilit_dosyasi)
    return sonuc
