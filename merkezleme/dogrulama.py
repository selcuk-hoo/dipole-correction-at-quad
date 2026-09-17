"""Girilen ölçümün doğrulanması: mertebe kontrolü ve "olası yazım hatası".

Rotating coil başka bir bilgisayarda çalıştığı için değerler ekrandan okunup
elle yazılır; bu yüzden tek gerçek hata kaynağı YAZIM HATASIDIR. İki katmanlı
doğrulama uygulanır:

1. Mertebe kontrolü: |C_1| ve |C_2| yapılandırılan makul aralıklarda mı?
   (C_1 için alt sınır zorlanmaz; iyi merkezlenmiş mıknatıste sıfıra yakın
   olması normaldir.)
2. Kalibrasyon varken: ölçülen y, kalibrasyondan BEKLENEN y'den çok mu sapıyor?
   Beklenen y, referans ölçüm ve R üzerinden hesaplanır; sapma, ölçülen
   tekrarlanabilirliğin (ya da tolerans ölçeğinin) belirli bir katını geçerse
   uyarı verilir ve yeniden onay istenir.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .harmonikler import HarmonikKonvansiyonu, HarmonikOlcumu, KontrolVektoru
from .yapilandirma import DogrulamaYapilandirmasi, DuzeltmeYapilandirmasi


@dataclass(frozen=True)
class DogrulamaSonucu:
    """Girişin doğrulanması. `onay_gerekli` ise kullanıcıya yeniden sorulur."""

    gecerli: bool
    onay_gerekli: bool
    uyarilar: tuple[str, ...] = field(default=())

    @property
    def temiz(self) -> bool:
        return self.gecerli and not self.onay_gerekli

    def metin(self) -> str:
        if self.temiz:
            return "Giriş makul görünüyor."
        return "\n".join(self.uyarilar)


def mertebe_kontrolu(
    olcum: HarmonikOlcumu, konvansiyon: HarmonikKonvansiyonu, ayar: DogrulamaYapilandirmasi
) -> list[str]:
    """|C_1| ve |C_2| makul aralıkta mı?"""
    uyarilar: list[str] = []
    for n, aralik in ((1, ayar.c1_makul_aralik), (2, ayar.c2_makul_aralik)):
        if n not in olcum.bilesenler:
            continue
        c_n = olcum.bilesenler[n]
        if not konvansiyon.mertebe_makul_mu(n, c_n, aralik):
            uyarilar.append(
                f"|C_{n}| = {abs(c_n):.4g} makul aralığın ({aralik[0]:.3g} .. {aralik[1]:.3g}) "
                f"dışında; birim ({konvansiyon.ayar.birim}) ya da basamak sayısı yanlış olabilir"
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
    """Ölçülen y, kalibrasyondan beklenenden çok mu sapıyor?

    Ölçek olarak önce ölçülen tekrarlanabilirlik, yoksa tolerans kullanılır.
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
            f"OLASI YAZIM HATASI: ölçülen merkez, beklenenden {merkez_sapmasi * 1e6:.1f} um "
            f"sapıyor (eşik {carpan * merkez_olcegi * 1e6:.1f} um).\n"
            f"  beklenen: {beklenen}\n  ölçülen : {olculen}"
        )

    g_sapmasi = abs(olculen.g - beklenen.g)
    if g_sapmasi > carpan * g_olcegi:
        uyarilar.append(
            f"OLASI YAZIM HATASI: ölçülen g, beklenenden {g_sapmasi:.5f} sapıyor "
            f"(eşik {carpan * g_olcegi:.5f}); beklenen g = {beklenen.g:+.5f}, "
            f"ölçülen g = {olculen.g:+.5f}"
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
    """İki katmanlı doğrulamayı uygular."""
    uyarilar = mertebe_kontrolu(olcum, konvansiyon, dogrulama)
    if olculen_y is not None and beklenen_y is not None:
        uyarilar += beklenenden_sapma_kontrolu(
            olculen_y, beklenen_y, dogrulama, duzeltme, merkez_sacilimi_m, g_sacilimi
        )
    return DogrulamaSonucu(
        gecerli=True, onay_gerekli=bool(uyarilar), uyarilar=tuple(uyarilar)
    )
