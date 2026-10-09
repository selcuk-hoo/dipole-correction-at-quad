"""Uçtan uca kapalı döngü: merkezleme (IsAkisi + DosyaGirisi) <-> kilit dosyası
<-> OlcumDongusu <-> sahte dönen bobin. Alan, merkezleme simülatöründen o anki
güç kaynağı akımlarıyla hesaplanır; bobin gerilimi gerçek geometriyle üretilir."""
from __future__ import annotations

import dataclasses
import threading
import time

import numpy as np
import pytest

from mgf import merkezleme_koprusu as mk
from mgf.olcum_dongusu import OlcumDongusu

from test_merkezleme_olcer import SahteBaglanti, SahteDunya, SahteMotor


def test_kapali_dongu_merkezi_sifirlar(tmp_path):
    from merkezleme.duzeltme import yakinsama_durumu
    from merkezleme.guc_kaynagi import KaynakGrubu
    from merkezleme.harmonikler import HarmonikKonvansiyonu
    from merkezleme.is_akisi import Faz, IsAkisi, otomatik_yurut
    from merkezleme.kayit import Calistirma
    from merkezleme.modlar import ModBazi
    from merkezleme.olcum_kaynagi import DosyaGirisi
    from merkezleme.simulator import Simulator
    from merkezleme.yapilandirma import yapilandirma_yukle

    kfg = yapilandirma_yukle(mk.REPO_KOKU / "yapilandirma.yaml")
    kilit = tmp_path / "veri_kilidi" / ".kilit"
    kfg = dataclasses.replace(
        kfg,
        dosya_girisi=dataclasses.replace(
            kfg.dosya_girisi, kilit_dosyasi=str(kilit), zaman_asimi_s=20.0, yoklama_araligi_s=0.002
        ),
    )
    p = dataclasses.replace(mk.parametreleri_yukle(), kilit_dosyasi=kilit, oturma_suresi_s=0.5)

    sim = Simulator(kfg.simulator, kfg.miknatis, kfg.harmonikler)
    sim.ofset_m = complex(180e-6, -110e-6)
    konvansiyon = HarmonikKonvansiyonu(kfg.harmonikler)
    grup = KaynakGrubu.olustur(kfg.guc_kaynaklari, kfg.guvenlik, canli=False, bekle=lambda s: None)
    akis = IsAkisi(
        kfg, grup, DosyaGirisi(kfg.dosya_girisi, konvansiyon, bekle=time.sleep),
        Calistirma(kfg, kok=tmp_path / "calistirmalar"), konvansiyon, ModBazi(kfg.modlar, kfg.miknatis),
    )

    dunya = SahteDunya(p)
    dongu = OlcumDongusu(p, SahteBaglanti(dunya), SahteMotor(dunya), saat=lambda: dunya.t)
    dongu.baglan()
    dongu.baslat()
    durdur = threading.Event()

    def donen_bobin() -> None:
        while not durdur.is_set():
            akimlar = grup.ayar_akimlari_A.copy()
            dunya.c1 = sim.harmonik_ham_T(akimlar, 1) + sim.arka_plan_T
            dunya.c2 = sim.harmonik_ham_T(akimlar, 2)
            dunya.ilerle(0.05)
            dongu.tick()
            time.sleep(0.0005)

    iplik = threading.Thread(target=donen_bobin, daemon=True)
    iplik.start()
    try:
        akis.basla()
        otomatik_yurut(akis, akis.olcum_kaynagi, max_adim=300)
    finally:
        durdur.set()
        iplik.join(timeout=5.0)

    assert akis.faz is Faz.TAMAMLANDI, akis.durdurma_nedeni
    assert yakinsama_durumu(akis.son_y, kfg.duzeltme).yakinsadi, akis.son_y
    assert abs(sim.gercek_merkez_m(grup.ayar_akimlari_A)) < 5e-6
    assert dongu.olcum_sayisi > 10
