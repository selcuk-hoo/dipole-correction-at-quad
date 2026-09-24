"""Ölçüm kaynağı: elle girişi soyutlayan katman.

Arayüz (`ElleGiris`), simülatör (`SimulatorGirisi`) ve paylaşımlı dosya
(`DosyaGirisi`) aynı protokolü uygular; böylece bütün akış donanımsız ve elle
girişsiz sınanabilir, "deneme kipinde" alanlar simülatörden, dosya kipinde ise
ayrı bir dönen bobin programından otomatik doldurulur.

Alan dönüşümleri de burada: arayüzün metin kutuları ile `HarmonikOlcumu`
arasındaki çevrim tek yerde toplanmıştır (konvansiyonların kendisi
`harmonikler.py` içindedir).
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Protocol, Sequence

import numpy as np

from .harmonikler import HarmonikKonvansiyonu, HarmonikOlcumu
from .simulator import Simulator
from .yapilandirma import DosyaGirisiYapilandirmasi


@dataclass(frozen=True)
class OlcumIstegi:
    """Programın kullanıcıdan (ya da simülatörden) beklediği ölçüm."""

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
            return "ARKA PLAN ÖLÇÜMÜNÜ ALIN VE GİRİN (akımlar sıfırda)"
        return "ÖLÇÜMÜ ALIN VE GİRİN"


class OlcumKaynagi(Protocol):
    """Harmonik ölçümü sağlayan soyut kaynak."""

    def olcum_al(self, istek: OlcumIstegi) -> HarmonikOlcumu: ...


# ---------------------------------------------------------------------------
# Alan <-> ölçüm dönüşümü
# ---------------------------------------------------------------------------
def _alan_adlari(n: int, bicim: str) -> tuple[str, str]:
    if bicim == "genlik_faz":
        return f"C{n}_genlik", f"C{n}_faz"
    return f"B{n}", f"A{n}"


@dataclass
class AlanGirisi:
    """Arayüzdeki metin kutularının ham içeriği."""

    alanlar: dict[str, str] = field(default_factory=dict)
    mutlak_gradyen_T_m: str = ""

    def doldurulmus_mu(self, n: int, bicim: str) -> bool:
        birinci, ikinci = _alan_adlari(n, bicim)
        return bool(self.alanlar.get(birinci, "").strip()) and bool(
            self.alanlar.get(ikinci, "").strip()
        )


class AlanHatasi(ValueError):
    """Metin kutusu içeriği geçersiz."""


def sayi_ayristir(metin: str, alan_adi: str) -> float:
    """Metin kutusundan sayı okur. Ondalık ayracı olarak virgül de kabul edilir."""
    ham = str(metin).strip().replace(",", ".")
    if not ham:
        raise AlanHatasi(f"{alan_adi} boş")
    try:
        return float(ham)
    except ValueError as hata:
        raise AlanHatasi(f"{alan_adi} sayı değil: {metin!r}") from hata


def alanlardan_olcum(
    giris: AlanGirisi,
    konvansiyon: HarmonikKonvansiyonu,
    bicim: str,
    zorunlu: Sequence[int] = (1, 2),
    opsiyonel: Sequence[int] = (3, 4),
    zaman: float = 0.0,
) -> HarmonikOlcumu:
    """Metin kutularından `HarmonikOlcumu` üretir.

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
    """`HarmonikOlcumu` -> metin kutusu içerikleri (elle girişle aynı biçimde).

    Deneme kipinde simülatör çıktısını arayüze doldurmak ve biçimler arası
    geçiş yapmak için kullanılır.
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
    """Ölçümleri simülatörden alan kaynak (testler ve deneme kipi)."""

    def __init__(self, simulator: Simulator) -> None:
        self.simulator = simulator
        self.zaman = 0.0
        self.olcum_sayisi = 0

    def olcum_al(self, istek: OlcumIstegi) -> HarmonikOlcumu:
        self.olcum_sayisi += 1
        # Her ölçüm arasında geçen süre; sürüklenme terimleri için.
        self.zaman += 1.0
        return self.simulator.olc(np.asarray(istek.akimlar_A, dtype=float), zaman=self.zaman)


class ElleGiris:
    """Arayüzün doldurduğu kaynak.

    Arayüz `olcumu_yerlestir()` ile sırada bekleyen ölçümü koyar; iş akışı
    `olcum_al()` ile onu tüketir. Ölçüm hazır değilse `OlcumHazirDegil`
    yükseltilir - arayüz olay tabanlı çalıştığı için bu normaldir.
    """

    def __init__(self) -> None:
        self._bekleyen: HarmonikOlcumu | None = None

    def olcumu_yerlestir(self, olcum: HarmonikOlcumu) -> None:
        self._bekleyen = olcum

    def olcum_al(self, istek: OlcumIstegi) -> HarmonikOlcumu:
        if self._bekleyen is None:
            raise OlcumHazirDegil(f"{istek.etiket} için elle giriş bekleniyor")
        olcum, self._bekleyen = self._bekleyen, None
        return olcum


class OlcumHazirDegil(RuntimeError):
    """Elle giriş henüz yapılmadı."""


class DosyaGirisiHatasi(RuntimeError):
    """Kilit dosyasının içeriği okunamadı ya da geçersiz."""


class DosyaGirisiZamanAsimi(RuntimeError):
    """Dönen bobin programından beklenen sürede veri gelmedi."""


class DosyaGirisi:
    """Paylaşımlı bir kilit dosyası üzerinden, aynı bilgisayarda çalışan ayrı
    bir dönen bobin programıyla otomatik ölçüm alışverişi.

    Protokol (kilit dosyasının VARLIĞI/YOKLUĞU tek sinyaldir, iki taraf da
    aynı bilgisayardaki paylaşımlı bir klasörü kullanır):

    * kilit YOK  -> "ölç" sinyali: sıra dönen bobin programındadır.
    * kilit VAR  -> "veri hazır" sinyali: sıra bu programdadır; dosyanın
      içeriği ölçülen harmonikleri taşır.

    Her `olcum_al()` çağrısı önce eski kilidi (varsa) SİLER - bu, "yeni akım
    hazır, ölç" demektir (`IsAkisi` bu çağrıdan önce akımları zaten rampalayıp
    oturmasını doğrulamış olur). Ardından yeni bir kilit belirene kadar
    yoklar, içeriğini okur ve döner; kilidi HEMEN silmez - silme, akımlar bir
    sonraki nokta için değiştirildikten sonra, bir SONRAKİ `olcum_al()`
    çağrısının başında olur. Böylece dönen bobin programı, kendi ölçtüğü
    akım durumu değişmeden yeniden ölçmeye başlamaz.

    Dönen bobin tarafı kendi verisini önce geçici bir dosyaya yazıp ardından
    ATOMİK olarak kilit dosyasının adına TAŞIMALIDIR (`os.rename`); böylece bu
    program hiçbir zaman yarım yazılmış bir dosya okumaz.

    Dosya içeriği (JSON), dipol ve kuadrupolün normal/skew bileşenleridir:

        {"b0": ..., "a0": ..., "b1": ..., "a1": ...}

    `b`: normal, `a`: skew; `0` = dipol (bu programın n=1'i), `1` = kuadrupol
    (n=2). Değerler, yapılandırmadaki `harmonikler.birim` biriminde kabul
    edilir (elle giriş kutularıyla aynı sözleşme).
    """

    #: dosyadaki 0-tabanlı harmonik indeksi -> bu programın 1-tabanlı n'i.
    _ZORUNLU_INDEKSLER = (0, 1)

    def __init__(
        self,
        ayar: DosyaGirisiYapilandirmasi,
        konvansiyon: HarmonikKonvansiyonu,
        bekle: Callable[[float], None] = time.sleep,
    ) -> None:
        self.ayar = ayar
        self.konvansiyon = konvansiyon
        self.bekle = bekle
        self.kilit_yolu = Path(ayar.kilit_dosyasi)
        self.kilit_yolu.parent.mkdir(parents=True, exist_ok=True)
        self.olcum_sayisi = 0
        self._baslangic = time.time()

    def olcum_al(self, istek: OlcumIstegi) -> HarmonikOlcumu:
        # 1) Önceki turdan kalan kilidi sil: "yeni akım hazır, ölç" sinyali.
        if self.kilit_yolu.exists():
            self.kilit_yolu.unlink()

        # 2) Dönen bobin taze veriyi yazıp kilidi oluşturana kadar yokla.
        gecen_s = 0.0
        while not self.kilit_yolu.exists():
            if gecen_s >= self.ayar.zaman_asimi_s:
                raise DosyaGirisiZamanAsimi(
                    f"{istek.etiket}: {self.ayar.zaman_asimi_s:.0f} s içinde "
                    f"'{self.kilit_yolu}' oluşmadı (dönen bobin programı çalışıyor mu?)"
                )
            self.bekle(self.ayar.yoklama_araligi_s)
            gecen_s += self.ayar.yoklama_araligi_s

        # 3) Oku ve HarmonikOlcumu'na çevir. Kilit BURADA silinmez (bkz. sınıf
        #    docstring'i) - bir sonraki olcum_al() çağrısının başında silinir.
        try:
            with self.kilit_yolu.open(encoding="utf-8") as f:
                ham = json.load(f)
        except json.JSONDecodeError as hata:
            raise DosyaGirisiHatasi(
                f"'{self.kilit_yolu}' geçerli JSON değil: {hata}. Dönen bobin "
                "tarafı veriyi geçici bir dosyaya yazıp ardından ATOMİK olarak "
                "(os.rename) kilit dosyasına taşımalı."
            ) from hata

        bilesenler: dict[int, complex] = {}
        eksik: list[str] = []
        for indeks in self._ZORUNLU_INDEKSLER:
            b_anahtari, a_anahtari = f"b{indeks}", f"a{indeks}"
            if b_anahtari not in ham or a_anahtari not in ham:
                eksik.extend(a for a in (b_anahtari, a_anahtari) if a not in ham)
                continue
            try:
                b = float(ham[b_anahtari])
                a = float(ham[a_anahtari])
            except (TypeError, ValueError) as hata:
                raise DosyaGirisiHatasi(
                    f"'{self.kilit_yolu}' içinde {b_anahtari}/{a_anahtari} sayı değil: {hata}"
                ) from hata
            bilesenler[indeks + 1] = self.konvansiyon.normal_skewden(b, a)
        if eksik:
            raise DosyaGirisiHatasi(f"'{self.kilit_yolu}' içinde eksik alan(lar): {', '.join(eksik)}")

        self.olcum_sayisi += 1
        return HarmonikOlcumu(
            bilesenler=bilesenler,
            zaman=time.time() - self._baslangic,
            ham_giris={"kaynak": "dosya", **{str(k): v for k, v in ham.items()}},
        )
