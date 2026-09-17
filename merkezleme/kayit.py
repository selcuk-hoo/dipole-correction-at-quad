"""Kayit katmani: tarihli calistirma klasoru, CSV, JSON, SCPI gunlugu, ozet.

Butun ciktilar DUZ METIN dosyalaridir; ikili (binary) bicim kullanilmaz.

    calistirmalar/2026-09-17_143500/
        yapilandirma.yaml     kullanilan yapilandirmanin kopyasi (tekrarlanabilirlik)
        olcumler.csv          her adim: zaman, adim turu, akimlar, harmonikler, y
        kalibrasyon.json      R, tekil degerler, fit parametreleri, R_eff
        scpi_gunlugu.txt      gonderilen (ya da kuru calismada kaydedilen) komutlar
        durum.json            kaldigi yerden devam icin durum dosyasi
        ozet.md               calistirma sonu Markdown ozeti
"""
from __future__ import annotations

import csv
import json
import os
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Sequence

import numpy as np

from .guc_kaynagi import KomutGunlugu
from .harmonikler import HarmonikOlcumu, IzlemeBuyuklukleri, KontrolVektoru
from .kalibrasyon import KalibrasyonSonucu
from .yapilandirma import BOBIN_SAYISI, Yapilandirma

# Adim turleri (CSV'de "adim_turu" kolonu)
ADIM_ARKA_PLAN = "arka_plan"
ADIM_KALIBRASYON = "kalibrasyon"
ADIM_DUZELTME = "duzeltme"
ADIM_TEKRARLANABILIRLIK = "tekrarlanabilirlik"
ADIM_POLARITE = "polarite_dogrulama"
ADIM_MODULATOR = "modulator_karsilastirma"


@dataclass
class OlcumKaydi:
    """CSV'ye yazilacak tek bir olcum satiri."""

    adim_turu: str
    adim_no: int
    etiket: str = ""
    mod: str = ""
    epsilon: float | None = None
    ayar_akimlari_A: Sequence[float] | None = None
    olculen_akimlari_A: Sequence[float] | None = None
    olculen_gerilimler_V: Sequence[float] | None = None
    ham_olcum: HarmonikOlcumu | None = None
    arka_plan: HarmonikOlcumu | None = None
    arka_plan_taze: bool | None = None
    net_olcum: HarmonikOlcumu | None = None
    y: KontrolVektoru | None = None
    izleme: IzlemeBuyuklukleri | None = None
    modulator_acik: bool | None = None
    polarite_isareti: int | None = None
    not_metni: str = ""
    zaman: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))


def _harmonik_kolonlari(onek: str, harmonikler: Iterable[int]) -> list[str]:
    kolonlar: list[str] = []
    for n in harmonikler:
        kolonlar.extend([f"{onek}_B{n}", f"{onek}_A{n}"])
    return kolonlar


def _harmonik_degerleri(
    olcum: HarmonikOlcumu | None, harmonikler: Iterable[int]
) -> list[str]:
    degerler: list[str] = []
    for n in harmonikler:
        if olcum is None or n not in olcum.bilesenler:
            degerler.extend(["", ""])
        else:
            c = olcum.bilesenler[n]
            degerler.extend([f"{c.real:.9g}", f"{c.imag:.9g}"])
    return degerler


class Calistirma:
    """Tek bir calistirmanin cikti klasoru ve dosyalari."""

    def __init__(self, yapilandirma: Yapilandirma, kok: str | Path | None = None) -> None:
        self.yapilandirma = yapilandirma
        kok_dizin = Path(kok) if kok is not None else Path(yapilandirma.genel.calistirma_kok_dizini)
        self.etiket = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        self.dizin = kok_dizin / self.etiket
        self.dizin.mkdir(parents=True, exist_ok=True)

        self.harmonikler = yapilandirma.harmonikler.tum_harmonikler
        self.olcumler_csv = self.dizin / "olcumler.csv"
        self.kalibrasyon_json = self.dizin / yapilandirma.kalibrasyon.dosya_adi
        self.scpi_gunlugu = self.dizin / "scpi_gunlugu.txt"
        self.durum_json = self.dizin / yapilandirma.genel.durum_dosyasi_adi
        self.ozet_md = self.dizin / "ozet.md"
        self._satir_sayisi = 0

        self._yapilandirmayi_kopyala()
        self._csv_basligi_yaz()

    # ------------------------------------------------------------------
    def _yapilandirmayi_kopyala(self) -> None:
        kaynak = self.yapilandirma.kaynak_dosya
        if kaynak is not None and Path(kaynak).exists():
            shutil.copy2(kaynak, self.dizin / "yapilandirma.yaml")

    @property
    def kolonlar(self) -> list[str]:
        kolonlar = [
            "zaman",
            "adim_turu",
            "adim_no",
            "etiket",
            "mod",
            "epsilon",
        ]
        kolonlar += [f"ayar_I{i + 1}_A" for i in range(BOBIN_SAYISI)]
        kolonlar += [f"olculen_I{i + 1}_A" for i in range(BOBIN_SAYISI)]
        kolonlar += [f"olculen_U{i + 1}_V" for i in range(BOBIN_SAYISI)]
        kolonlar += _harmonik_kolonlari("ham", self.harmonikler)
        kolonlar += _harmonik_kolonlari("arka_plan", self.harmonikler)
        kolonlar += _harmonik_kolonlari("net", self.harmonikler)
        kolonlar += [
            "arka_plan_taze",
            "x_c_um",
            "y_c_um",
            "g",
            "sq_over_g",
            "roll_mrad",
            "b3",
            "a3",
            "b4",
            "a4",
            "modulator_acik",
            "polarite_isareti",
            "birim",
            "r_ref_mm",
            "not",
        ]
        return kolonlar

    def _csv_basligi_yaz(self) -> None:
        with self.olcumler_csv.open("w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(self.kolonlar)

    # ------------------------------------------------------------------
    def olcum_yaz(self, kayit: OlcumKaydi) -> None:
        """Bir olcum satirini CSV'ye ekler (her yazmada dosya acilir/kapanir)."""

        def akim_alanlari(degerler: Sequence[float] | None) -> list[str]:
            if degerler is None:
                return [""] * BOBIN_SAYISI
            return [f"{float(v):.4f}" for v in degerler]

        izleme = kayit.izleme
        satir: list[Any] = [
            kayit.zaman,
            kayit.adim_turu,
            kayit.adim_no,
            kayit.etiket,
            kayit.mod,
            "" if kayit.epsilon is None else f"{kayit.epsilon:.6f}",
        ]
        satir += akim_alanlari(kayit.ayar_akimlari_A)
        satir += akim_alanlari(kayit.olculen_akimlari_A)
        satir += akim_alanlari(kayit.olculen_gerilimler_V)
        satir += _harmonik_degerleri(kayit.ham_olcum, self.harmonikler)
        satir += _harmonik_degerleri(kayit.arka_plan, self.harmonikler)
        satir += _harmonik_degerleri(kayit.net_olcum, self.harmonikler)
        satir += [
            "" if kayit.arka_plan_taze is None else int(kayit.arka_plan_taze),
            "" if kayit.y is None else f"{kayit.y.x_c * 1e6:.4f}",
            "" if kayit.y is None else f"{kayit.y.y_c * 1e6:.4f}",
            "" if kayit.y is None else f"{kayit.y.g:.8f}",
            "" if izleme is None or izleme.sq_over_g is None else f"{izleme.sq_over_g:.8f}",
            "" if izleme is None or izleme.roll_mrad is None else f"{izleme.roll_mrad:.5f}",
            "" if izleme is None or izleme.b3 is None else f"{izleme.b3:.9g}",
            "" if izleme is None or izleme.a3 is None else f"{izleme.a3:.9g}",
            "" if izleme is None or izleme.b4 is None else f"{izleme.b4:.9g}",
            "" if izleme is None or izleme.a4 is None else f"{izleme.a4:.9g}",
            "" if kayit.modulator_acik is None else int(kayit.modulator_acik),
            "" if kayit.polarite_isareti is None else kayit.polarite_isareti,
            self.yapilandirma.harmonikler.birim,
            f"{self.yapilandirma.harmonikler.r_ref_mm:g}",
            kayit.not_metni,
        ]
        with self.olcumler_csv.open("a", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(satir)
        self._satir_sayisi += 1

    @property
    def satir_sayisi(self) -> int:
        return self._satir_sayisi

    # ------------------------------------------------------------------
    def kalibrasyon_yaz(self, sonuc: KalibrasyonSonucu) -> Path:
        return sonuc.kaydet(self.kalibrasyon_json)

    def scpi_gunlugu_yaz(self, gunluk: KomutGunlugu) -> Path:
        with self.scpi_gunlugu.open("w", encoding="utf-8") as f:
            f.write("zaman\tadres\tkomut\n")
            for satir in gunluk.satirlar():
                f.write(satir + "\n")
        return self.scpi_gunlugu

    # ------------------------------------------------------------------
    def durum_yaz(self, durum: dict[str, Any]) -> Path:
        """Durum dosyasini ATOMIK yazar (gecici dosya + os.replace).

        Program kapanir ya da cokerse kaldigi yerden devam edebilmek icin
        her adimdan sonra cagrilir; yarim yazilmis dosya olmaz.
        """
        gecici = self.durum_json.with_suffix(".json.tmp")
        with gecici.open("w", encoding="utf-8") as f:
            json.dump(durum, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(gecici, self.durum_json)
        return self.durum_json

    def durum_oku(self) -> dict[str, Any] | None:
        if not self.durum_json.exists():
            return None
        with self.durum_json.open(encoding="utf-8") as f:
            return json.load(f)

    @staticmethod
    def yarim_calistirma_bul(kok: str | Path, durum_dosyasi_adi: str) -> Path | None:
        """En son yarim kalmis calistirmanin durum dosyasini bulur."""
        kok_dizin = Path(kok)
        if not kok_dizin.exists():
            return None
        adaylar = sorted(
            (d for d in kok_dizin.iterdir() if d.is_dir() and (d / durum_dosyasi_adi).exists()),
            key=lambda d: d.name,
            reverse=True,
        )
        for aday in adaylar:
            with (aday / durum_dosyasi_adi).open(encoding="utf-8") as f:
                durum = json.load(f)
            if not durum.get("tamamlandi", False):
                return aday / durum_dosyasi_adi
        return None


# ---------------------------------------------------------------------------
# Markdown ozeti
# ---------------------------------------------------------------------------
@dataclass
class OzetVerisi:
    """Calistirma sonu ozeti icin toplanan bilgiler."""

    kip: str
    modulator_acik: bool
    baslangic_y: KontrolVektoru | None = None
    son_y: KontrolVektoru | None = None
    baslangic_izleme: IzlemeBuyuklukleri | None = None
    son_izleme: IzlemeBuyuklukleri | None = None
    son_akimlar_A: Sequence[float] | None = None
    nominal_akim_A: float = 0.0
    iterasyon_sayisi: int = 0
    kalibrasyon: KalibrasyonSonucu | None = None
    tekrarlanabilirlik_metni: str = ""
    arka_plan_ilk: HarmonikOlcumu | None = None
    arka_plan_son: HarmonikOlcumu | None = None
    arka_plan_sayisi: int = 0
    atlanan_arka_plan_sayisi: int = 0
    notlar: list[str] = field(default_factory=list)


def _merkez_metni(y: KontrolVektoru | None) -> str:
    if y is None:
        return "-"
    return f"x_c = {y.x_c * 1e6:+.2f} um, y_c = {y.y_c * 1e6:+.2f} um, g = {y.g:+.5f}"


def ozet_yaz(calistirma: Calistirma, veri: OzetVerisi) -> Path:
    """Calistirma sonu Markdown ozetini yazar."""
    y_kfg = calistirma.yapilandirma
    satirlar: list[str] = []
    ekle = satirlar.append

    ekle(f"# Elektriksel merkezleme ozeti - {calistirma.etiket}")
    ekle("")
    ekle(f"- Kip: **{veri.kip}**")
    ekle(f"- Modulator: **{'ACIK' if veri.modulator_acik else 'KAPALI'}**")
    ekle(f"- Birim: `{y_kfg.harmonikler.birim}`, r_ref = {y_kfg.harmonikler.r_ref_mm:g} mm")
    ekle(f"- Giris bicimi: `{y_kfg.harmonikler.giris_bicimi}`")
    ekle(f"- Olcum satiri sayisi: {calistirma.satir_sayisi}")
    ekle("")

    ekle("## Merkez")
    ekle("")
    ekle("| | merkez ve gradyen |")
    ekle("|---|---|")
    ekle(f"| Baslangic | {_merkez_metni(veri.baslangic_y)} |")
    ekle(f"| Son | {_merkez_metni(veri.son_y)} |")
    if veri.baslangic_y is not None and veri.son_y is not None:
        ekle(
            f"| Iyilesme | {veri.baslangic_y.merkez_normu_m * 1e6:.2f} um -> "
            f"{veri.son_y.merkez_normu_m * 1e6:.2f} um |"
        )
    ekle(f"| Iterasyon sayisi | {veri.iterasyon_sayisi} |")
    ekle("")

    if veri.son_akimlar_A is not None and veri.nominal_akim_A:
        ekle("## Son akimlar")
        ekle("")
        ekle("| Bobin | akim (A) | nominale gore |")
        ekle("|---|---|---|")
        for i, akim in enumerate(veri.son_akimlar_A):
            asimetri = (akim - veri.nominal_akim_A) / veri.nominal_akim_A * 100
            ekle(f"| I{i + 1} | {akim:.4f} | {asimetri:+.3f} % |")
        ekle("")

    if veri.kalibrasyon is not None:
        kal = veri.kalibrasyon
        ekle("## Kalibrasyon")
        ekle("")
        ekle(f"- R_eff = **{kal.r_eff_m * 1e3:+.2f} mm**")
        ekle("- Tekil degerler: " + ", ".join(f"{s:.4g}" for s in kal.tekil_degerler))
        ekle(f"- Kosul sayisi (ham / toleransa gore olcekli): {kal.kosul_sayisi:.2f} / "
             f"{kal.kosul_sayisi_olcekli:.2f}")
        if kal.m_sutunu_orani is not None:
            ekle(f"- M sutunu orani: {kal.m_sutunu_orani:.4f}")
        ekle(f"- G_hedef = {kal.gradyen_hedefi_T_m:.6f} T/m")
        ekle(
            f"- Tek adimda duzeltilebilir ofset ~ "
            f"{kal.tek_adimda_duzeltilebilir_ofset_m * y_kfg.guvenlik.adim_basi_max_bagil_degisim * 1e6:.0f}"
            " um"
        )
        if kal.supheli:
            ekle("- **SUPHELI KALIBRASYON:**")
            for neden in kal.supheli_nedenleri:
                ekle(f"  - {neden}")
        ekle("")

    ekle("## Yalnizca izlenen buyuklukler")
    ekle("")
    ekle("| Buyukluk | duzeltme oncesi | duzeltme sonrasi |")
    ekle("|---|---|---|")

    def izleme_alani(izleme: IzlemeBuyuklukleri | None, ad: str) -> str:
        if izleme is None:
            return "-"
        deger = getattr(izleme, ad)
        if deger is None:
            return "-"
        return f"{deger:.6g}"

    for ad, baslik in (
        ("sq_over_g", "SQ/G"),
        ("roll_mrad", "roll (mrad)"),
        ("b3", "b3"),
        ("a3", "a3"),
        ("b4", "b4"),
        ("a4", "a4"),
    ):
        ekle(
            f"| {baslik} | {izleme_alani(veri.baslangic_izleme, ad)} | "
            f"{izleme_alani(veri.son_izleme, ad)} |"
        )
    ekle("")

    ekle("## Arka plan")
    ekle("")
    ekle(f"- Alinan arka plan olcumu: {veri.arka_plan_sayisi}")
    if veri.atlanan_arka_plan_sayisi:
        ekle(
            f"- Kullanicinin atladigi arka plan adimi: {veri.atlanan_arka_plan_sayisi} "
            "(son gecerli arka plan kullanildi)"
        )
    for ad, olcum in (("Ilk", veri.arka_plan_ilk), ("Son", veri.arka_plan_son)):
        if olcum is None:
            continue
        c1 = olcum.bilesenler.get(1, 0j)
        ekle(f"- {ad} arka plan C_1: B_1 = {c1.real:.6g}, A_1 = {c1.imag:.6g}")
    if veri.arka_plan_ilk is not None and veri.arka_plan_son is not None:
        fark = veri.arka_plan_son.bilesenler.get(1, 0j) - veri.arka_plan_ilk.bilesenler.get(1, 0j)
        ekle(f"- Arka plan degisimi (C_1): |d| = {abs(fark):.6g}")
    ekle("")

    if veri.tekrarlanabilirlik_metni:
        ekle("## Tekrarlanabilirlik")
        ekle("")
        ekle("```")
        ekle(veri.tekrarlanabilirlik_metni)
        ekle("```")
        ekle("")

    if veri.notlar:
        ekle("## Notlar")
        ekle("")
        for notu in veri.notlar:
            ekle(f"- {notu}")
        ekle("")

    ekle("## Dosyalar")
    ekle("")
    for ad, yol in (
        ("Olcumler (CSV)", calistirma.olcumler_csv),
        ("Kalibrasyon (JSON)", calistirma.kalibrasyon_json),
        ("SCPI gunlugu", calistirma.scpi_gunlugu),
        ("Durum dosyasi", calistirma.durum_json),
        ("Yapilandirma", calistirma.dizin / "yapilandirma.yaml"),
    ):
        if yol.exists():
            ekle(f"- {ad}: `{yol.name}`")

    metin = "\n".join(satirlar) + "\n"
    calistirma.ozet_md.write_text(metin, encoding="utf-8")
    return calistirma.ozet_md
