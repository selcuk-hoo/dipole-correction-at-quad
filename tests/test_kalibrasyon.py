"""Kalibrasyon testleri: plan, fitler, R, tekil degerler, R_eff, JSON."""
from __future__ import annotations

import dataclasses
from itertools import permutations

import numpy as np
import pytest

from merkezleme.is_akisi import Faz
from merkezleme.kalibrasyon import (
    ORTAK_SIFIR,
    KalibrasyonSonucu,
    plan_olustur,
)

from .conftest import kalibrasyonu_yurut


# ---------------------------------------------------------------------------
# Plan
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "nokta_sayisi, arka_plan_her_n, beklenen_nokta, beklenen_giris",
    [(3, 1, 9, 18), (3, 3, 9, 12), (5, 1, 17, 34), (5, 3, 17, 23)],
)
def test_plan_giris_sayisi(kfg, nokta_sayisi, arka_plan_her_n, beklenen_nokta, beklenen_giris):
    """Elle giris sayisi ve tahmini sure onceden bilinebilir olmali."""
    ayar = dataclasses.replace(
        kfg.kalibrasyon, nokta_sayisi=nokta_sayisi, arka_plan_her_n_noktada=arka_plan_her_n
    )
    plan = plan_olustur(ayar)
    assert plan.nokta_sayisi == beklenen_nokta
    assert plan.giris_sayisi == beklenen_giris
    assert plan.tahmini_sure_dk == pytest.approx(
        beklenen_giris * ayar.olcum_basi_tahmini_sure_dk
    )
    assert "elle giris" in plan.ozet_metni()


def test_ortak_sifir_noktasi_paylasilir(kfg):
    """Ortak sifir noktasi yalnizca bir kez olculur."""
    ayar = dataclasses.replace(kfg.kalibrasyon, ortak_sifir_noktasi=True)
    plan = plan_olustur(ayar)
    sifir_noktalari = [n for n in plan.noktalar if n.mod == ORTAK_SIFIR]
    assert len(sifir_noktalari) == 1
    assert plan.noktalar[0].mod == ORTAK_SIFIR, "ortak sifir en basta olmali (G_hedef noktasi)"
    # Paylasilmazsa her mod kendi sifirini olcer -> daha fazla nokta
    paylasmasiz = plan_olustur(dataclasses.replace(ayar, ortak_sifir_noktasi=False))
    assert paylasmasiz.nokta_sayisi > plan.nokta_sayisi


def test_global_epsilon_dizisi_monoton_degil(kfg):
    """Suruklenmeyi egimden ayirmak icin sira monoton olmamali."""
    plan = plan_olustur(kfg.kalibrasyon)
    dizi = [n.epsilon for n in plan.noktalar if n.mod != ORTAK_SIFIR]
    assert dizi != sorted(dizi)
    assert dizi != sorted(dizi, reverse=True)


def test_iki_noktali_modlarda_yon_degisir(kfg):
    """3 nokta + ortak sifir -> mod basina 2 nokta; modlar arasi yon degismeli."""
    plan = plan_olustur(dataclasses.replace(kfg.kalibrasyon, nokta_sayisi=3))
    mod_sirasi: dict[str, list[float]] = {}
    for nokta in plan.noktalar:
        if nokta.mod != ORTAK_SIFIR:
            mod_sirasi.setdefault(nokta.mod, []).append(nokta.epsilon)
    yonler = {mod: degerler[1] > degerler[0] for mod, degerler in mod_sirasi.items()}
    assert len(set(yonler.values())) == 2, yonler


@pytest.mark.parametrize("ortak_sifir", [True, False])
def test_bes_noktali_sira_korelasyonu_en_kucuk(kfg, ortak_sifir):
    """Secilen sira, zaman-epsilon korelasyonunu ulasilabilir minimuma indirmeli."""
    ayar = dataclasses.replace(
        kfg.kalibrasyon, nokta_sayisi=5, ortak_sifir_noktasi=ortak_sifir
    )
    plan = plan_olustur(ayar)
    dizi = [n.epsilon for n in plan.noktalar if n.mod == "H"]

    def korelasyon(sira) -> float:
        t = np.arange(len(sira), dtype=float)
        return abs(float((t - t.mean()) @ np.array(sira, dtype=float)))

    en_kucuk = min(korelasyon(p) for p in permutations(dizi))
    assert korelasyon(dizi) == pytest.approx(en_kucuk, abs=1e-15)
    if not ortak_sifir:
        # Sifir noktasi da dahil oldugunda tam dekorelasyon mumkundur.
        assert en_kucuk == pytest.approx(0.0, abs=1e-15)


def test_m_modu_istege_bagli(kfg):
    ayar = dataclasses.replace(kfg.kalibrasyon, m_modu_kontrolu=False)
    plan = plan_olustur(ayar)
    assert not any(n.mod == "M" for n in plan.noktalar)
    assert plan.nokta_sayisi < plan_olustur(kfg.kalibrasyon).nokta_sayisi


# ---------------------------------------------------------------------------
# Kalibrasyon sonucu
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("nokta_sayisi", [3, 5])
def test_r_eff_simulator_geometrisiyle_tutarli(
    kfg, konvansiyon, mod_bazi, simulator_uret, kaynak_grubu_uret, tmp_path, nokta_sayisi
):
    """3 ve 5 noktali kalibrasyondan cikan R_eff, simulator geometrisiyle uyumlu olmali."""
    import dataclasses as dc

    from merkezleme.is_akisi import IsAkisi
    from merkezleme.kayit import Calistirma
    from merkezleme.olcum_kaynagi import SimulatorGirisi

    yeni_kfg = dc.replace(kfg, kalibrasyon=dc.replace(kfg.kalibrasyon, nokta_sayisi=nokta_sayisi))
    sim = simulator_uret(ofset_m=complex(80e-6, -60e-6), tohum=nokta_sayisi)
    kaynak = SimulatorGirisi(sim)
    akis = IsAkisi(
        yeni_kfg,
        kaynak_grubu_uret(),
        kaynak,
        Calistirma(yeni_kfg, kok=tmp_path),
        konvansiyon,
        mod_bazi,
    )
    kalibrasyonu_yurut(akis, kaynak)

    kal = akis.kalibrasyon
    assert kal is not None
    assert abs(kal.r_eff_m) == pytest.approx(kfg.simulator.beklenen_r_eff_m, rel=0.02)
    assert not kal.supheli, kal.supheli_nedenleri
    assert kal.R.shape == (3, 4)
    assert len(kal.tekil_degerler) == 3
    # M sutunu kucuk olmali (monopol dipol/gradyene katkisiz)
    assert kal.m_sutunu_orani is not None
    assert kal.m_sutunu_orani < kfg.kalibrasyon.m_sutunu_esigi_bagil
    # Olcekli kosul sayisi esigin altinda
    assert kal.kosul_sayisi_olcekli < kfg.kalibrasyon.kosul_sayisi_esigi


def test_fit_artiklari_ve_lineerlik_kaydedilir(kfg, konvansiyon, mod_bazi, simulator_uret, akis_uret):
    sim = simulator_uret(ofset_m=complex(100e-6, 50e-6), tohum=9)
    akis, kaynak, _ = akis_uret(sim)
    kalibrasyonu_yurut(akis, kaynak)
    kal = akis.kalibrasyon
    for mod, fit in kal.fitler.items():
        for ad, bilesen in fit.bilesenler.items():
            assert bilesen.artiklar  # artiklar kaydedilmis
            assert bilesen.artik_rms >= 0
        assert fit.lineer_mi, (mod, fit.sozluk())
    # Beklenen mod-bilesen eslesmesi: H -> x_c, V -> y_c, Q -> g
    assert kal.fitler["H"].bilesenler["x_c"].tepki_veriyor
    assert not kal.fitler["H"].bilesenler["g"].tepki_veriyor
    assert kal.fitler["V"].bilesenler["y_c"].tepki_veriyor
    assert kal.fitler["Q"].bilesenler["g"].tepki_veriyor
    # dg/deps_Q = 1 beklenir. Gurultulu fitte egim belirsizligi
    # ~sigma_g / (delta * sqrt(2)) ~ %0.4 mertebesinde oldugu icin tolerans %2.
    assert kal.fitler["Q"].bilesenler["g"].egim == pytest.approx(1.0, rel=2e-2)


def test_kalibrasyon_json_gidis_donus(kfg, simulator_uret, akis_uret, tmp_path):
    sim = simulator_uret(ofset_m=complex(60e-6, 20e-6), tohum=4)
    akis, kaynak, calistirma = akis_uret(sim)
    kalibrasyonu_yurut(akis, kaynak)
    assert calistirma.kalibrasyon_json.exists()

    geri = KalibrasyonSonucu.yukle(calistirma.kalibrasyon_json)
    assert np.allclose(geri.R, akis.kalibrasyon.R)
    assert geri.r_eff_m == pytest.approx(akis.kalibrasyon.r_eff_m)
    assert geri.gradyen_hedefi_T_m == pytest.approx(akis.kalibrasyon.gradyen_hedefi_T_m)
    assert set(geri.fitler) == set(akis.kalibrasyon.fitler)


def test_kayitli_kalibrasyon_yuklenince_faz1_atlanir(
    kfg, simulator_uret, akis_uret
):
    """Onceki oturumdan kalibrasyon yuklenirse dogrudan duzeltme fazi baslar."""
    sim = simulator_uret(ofset_m=complex(70e-6, 0), tohum=8)
    akis1, kaynak1, _ = akis_uret(sim)
    kalibrasyonu_yurut(akis1, kaynak1)

    akis2, _, _ = akis_uret(sim)
    akis2.kalibrasyonu_yukle(akis1.kalibrasyon)
    akis2.basla()
    assert akis2.faz is Faz.DUZELTME


def test_kotu_kalibrasyon_supheli_isaretlenir(kfg, mod_bazi):
    """Kosul sayisi buyukse ya da M sutunu kucuk degilse kalibrasyon supheli."""
    from merkezleme.kalibrasyon import BilesenFiti, ModFiti, kalibrasyonu_kur

    def fit_uret(mod: str, egimler: tuple[float, float, float]) -> ModFiti:
        bilesenler = {}
        for ad, egim in zip(("x_c", "y_c", "g"), egimler):
            bilesenler[ad] = BilesenFiti(
                bilesen=ad,
                egim=egim,
                kesisim=0.0,
                artiklar=(0.0, 0.0, 0.0),
                artik_rms=0.0,
                r2=1.0 if egim else None,
                tepki=abs(egim) * 0.005,
                tepki_veriyor=bool(egim),
                lineer_mi=True if egim else None,
            )
        return ModFiti(mod=mod, epsilonlar=(-0.005, 0.0, 0.005), bilesenler=bilesenler)

    # M modu H kadar guclu tepki veriyor -> supheli olmali
    fitler = {
        "H": fit_uret("H", (-0.04, 0.0, 0.0)),
        "V": fit_uret("V", (0.0, -0.04, 0.0)),
        "Q": fit_uret("Q", (0.0, 0.0, 1.0)),
        "M": fit_uret("M", (-0.04, 0.0, 0.0)),
    }
    sonuc = kalibrasyonu_kur(
        fitler, mod_bazi, kfg.kalibrasyon, kfg.duzeltme, 0.1, modulator_acik=False
    )
    assert sonuc.supheli
    assert any("M sutunu" in neden for neden in sonuc.supheli_nedenleri)


def test_mod_bilesen_eslesmesi_ters_ise_uyarir(kfg, mod_bazi):
    """H modu x_c yerine y_c'yi etkiliyorsa konvansiyon/numaralandirma uyarisi verilir."""
    from merkezleme.kalibrasyon import BilesenFiti, ModFiti, kalibrasyonu_kur

    def fit_uret(mod: str, egimler: tuple[float, float, float]) -> ModFiti:
        bilesenler = {
            ad: BilesenFiti(
                bilesen=ad,
                egim=egim,
                kesisim=0.0,
                artiklar=(0.0,),
                artik_rms=0.0,
                r2=1.0 if egim else None,
                tepki=abs(egim) * 0.005,
                tepki_veriyor=bool(egim),
                lineer_mi=True if egim else None,
            )
            for ad, egim in zip(("x_c", "y_c", "g"), egimler)
        }
        return ModFiti(mod=mod, epsilonlar=(-0.005, 0.005), bilesenler=bilesenler)

    fitler = {
        "H": fit_uret("H", (0.0, -0.04, 0.0)),  # ters: y_c'yi etkiliyor
        "V": fit_uret("V", (-0.04, 0.0, 0.0)),
        "Q": fit_uret("Q", (0.0, 0.0, 1.0)),
    }
    sonuc = kalibrasyonu_kur(
        fitler, mod_bazi, kfg.kalibrasyon, kfg.duzeltme, 0.1, modulator_acik=False
    )
    assert sonuc.supheli
    assert any("konvansiyonu ters olabilir" in n for n in sonuc.supheli_nedenleri)
