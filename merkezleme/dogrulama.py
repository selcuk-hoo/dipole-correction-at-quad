"""Girilen olcumun dogrulanmasi: mertebe kontrolu ve "olasi yazim hatasi".

Rotating coil baska bir bilgisayarda calistigi icin degerler ekrandan okunup
elle yazilir; bu yuzden tek gercek hata kaynagi YAZIM HATASIDIR. Iki katmanli
dogrulama uygulanir:

1. Mertebe kontrolu: |C_1| ve |C_2| yapilandirilan makul araliklarda mi?
   (C_1 icin alt sinir zorlanmaz; iyi merkezlenmis miknatiste sifira yakin
   olmasi normaldir.)
2. Kalibrasyon varken: olculen y, kalibrasyondan BEKLENEN y'den cok mu sapiyor?
   Beklenen y, referans olcum ve R uzerinden hesaplanir; sapma, olculen
   tekrarlanabilirligin (ya da tolerans olceginin) belirli bir katini gecerse
   uyari verilir ve yeniden onay istenir.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .harmonikler import HarmonikKonvansiyonu, HarmonikOlcumu, KontrolVektoru
from .yapilandirma import DogrulamaYapilandirmasi, DuzeltmeYapilandirmasi


@dataclass(frozen=True)
class DogrulamaSonucu:
    """Girisin dogrulanmasi. `onay_gerekli` ise kullaniciya yeniden sorulur."""

    gecerli: bool
    onay_gerekli: bool
    uyarilar: tuple[str, ...] = field(default=())

    @property
    def temiz(self) -> bool:
        return self.gecerli and not self.onay_gerekli

    def metin(self) -> str:
        if self.temiz:
            return "Giris makul gorunuyor."
        return "\n".join(self.uyarilar)


def mertebe_kontrolu(
    olcum: HarmonikOlcumu, konvansiyon: HarmonikKonvansiyonu, ayar: DogrulamaYapilandirmasi
) -> list[str]:
    """|C_1| ve |C_2| makul aralikta mi?"""
    uyarilar: list[str] = []
    for n, aralik in ((1, ayar.c1_makul_aralik), (2, ayar.c2_makul_aralik)):
        if n not in olcum.bilesenler:
            continue
        c_n = olcum.bilesenler[n]
        if not konvansiyon.mertebe_makul_mu(n, c_n, aralik):
            uyarilar.append(
                f"|C_{n}| = {abs(c_n):.4g} makul araligin ({aralik[0]:.3g} .. {aralik[1]:.3g}) "
                f"disinda; birim ({konvansiyon.ayar.birim}) ya da basamak sayisi yanlis olabilir"
            )
    return uyarilar


def beklenenden_sapma_kontrolu(
    olculen: KontrolVektoru,
    beklenen: KontrolVektoru,
    dogrulama: DogrulamaYapilandirmasi,
    duzeltme: DuzeltmeYapilandirmasi,
    merkez_sacilimi_m: float | None = None,
    g_sacilimi: float | None = None,
) -> list[str]:
    """Olculen y, kalibrasyondan beklenenden cok mu sapiyor?

    Olcek olarak once olculen tekrarlanabilirlik, yoksa tolerans kullanilir.
    """
    uyarilar: list[str] = []
    carpan = dogrulama.yazim_hatasi_sapma_carpani

    merkez_olcegi = merkez_sacilimi_m if merkez_sacilimi_m else duzeltme.merkez_toleransi_m
    g_olcegi = g_sacilimi if g_sacilimi else duzeltme.g_toleransi

    merkez_sapmasi = float(
        np.hypot(olculen.x_c - beklenen.x_c, olculen.y_c - beklenen.y_c)
    )
    if merkez_sapmasi > carpan * merkez_olcegi:
        uyarilar.append(
            f"OLASI YAZIM HATASI: olculen merkez, beklenenden {merkez_sapmasi * 1e6:.1f} um "
            f"sapiyor (esik {carpan * merkez_olcegi * 1e6:.1f} um).\n"
            f"  beklenen: {beklenen}\n  olculen : {olculen}"
        )

    g_sapmasi = abs(olculen.g - beklenen.g)
    if g_sapmasi > carpan * g_olcegi:
        uyarilar.append(
            f"OLASI YAZIM HATASI: olculen g, beklenenden {g_sapmasi:.5f} sapiyor "
            f"(esik {carpan * g_olcegi:.5f}); beklenen g = {beklenen.g:+.5f}, "
            f"olculen g = {olculen.g:+.5f}"
        )
    return uyarilar


def girisi_dogrula(
    olcum: HarmonikOlcumu,
    konvansiyon: HarmonikKonvansiyonu,
    dogrulama: DogrulamaYapilandirmasi,
    duzeltme: DuzeltmeYapilandirmasi,
    olculen_y: KontrolVektoru | None = None,
    beklenen_y: KontrolVektoru | None = None,
    merkez_sacilimi_m: float | None = None,
    g_sacilimi: float | None = None,
) -> DogrulamaSonucu:
    """Iki katmanli dogrulamayi uygular."""
    uyarilar = mertebe_kontrolu(olcum, konvansiyon, dogrulama)
    if olculen_y is not None and beklenen_y is not None:
        uyarilar += beklenenden_sapma_kontrolu(
            olculen_y, beklenen_y, dogrulama, duzeltme, merkez_sacilimi_m, g_sacilimi
        )
    return DogrulamaSonucu(
        gecerli=True, onay_gerekli=bool(uyarilar), uyarilar=tuple(uyarilar)
    )
