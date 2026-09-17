"""Harmonik konvansiyonlari, feed-down merkezi ve arka plan cikarma testleri."""
from __future__ import annotations

import dataclasses
import math

import pytest

from merkezleme.harmonikler import HarmonikHatasi, HarmonikKonvansiyonu, HarmonikOlcumu


def c2_ver(kfg, gradyen_T_m: float = 0.1) -> complex:
    """Verilen gradyeni uretecek (saf normal) C_2."""
    return complex(gradyen_T_m * kfg.harmonikler.r_ref_m, 0.0)


def test_feed_down_bilinen_ofseti_geri_verir(kfg, konvansiyon):
    """z_c = -r_ref*C_1/C_2 bilinen bir ofseti birebir geri vermeli."""
    c2 = c2_ver(kfg)
    d = complex(120e-6, -45e-6)
    c1 = -c2 * d / kfg.harmonikler.r_ref_m
    z = konvansiyon.merkez(HarmonikOlcumu(bilesenler={1: c1, 2: c2}))
    assert z.real == pytest.approx(d.real, abs=1e-15)
    assert z.imag == pytest.approx(d.imag, abs=1e-15)


def test_arka_plan_dipolu_merkez_hatasina_donusur(kfg, konvansiyon):
    """1 uT arka plan dipolu, 0.2 T/m gradyende ~5 um merkez hatasi verir."""
    gradyen = 0.2
    olcum = HarmonikOlcumu(bilesenler={1: 1e-6 + 0j, 2: c2_ver(kfg, gradyen)})
    z = konvansiyon.merkez(olcum)
    assert abs(z) == pytest.approx(5e-6, rel=1e-9)
    assert konvansiyon.gradyen_T_m(olcum) == pytest.approx(gradyen, rel=1e-12)


def test_g_hedefe_gore_bagil_hesaplanir(kfg, konvansiyon):
    olcum = HarmonikOlcumu(bilesenler={1: 0j, 2: c2_ver(kfg, 0.101)})
    y = konvansiyon.kontrol_vektoru(olcum, gradyen_hedefi_T_m=0.1)
    assert y.g == pytest.approx(0.01, rel=1e-9)


def test_arka_plan_kompleks_olarak_cikarilir(kfg, konvansiyon):
    """Arka plan genlikten degil, kompleks olarak cikarilmali."""
    olcum = HarmonikOlcumu(bilesenler={1: 3e-6 + 1e-6j, 2: c2_ver(kfg)})
    arka_plan = HarmonikOlcumu(bilesenler={1: 1e-6 - 0.5e-6j, 2: 0j})
    net = konvansiyon.arka_plan_cikar(olcum, arka_plan)
    assert net.bilesen(1) == pytest.approx(2e-6 + 1.5e-6j)


def test_yalniz_dipol_secenegi_ust_harmonikleri_korur(kfg):
    ayar = dataclasses.replace(kfg.harmonikler, arka_plan_cikarma="yalniz_dipol")
    konvansiyon = HarmonikKonvansiyonu(ayar)
    olcum = HarmonikOlcumu(bilesenler={1: 3e-6 + 0j, 2: 2.5e-3 + 0j})
    arka_plan = HarmonikOlcumu(bilesenler={1: 1e-6 + 0j, 2: 1e-6 + 0j})
    net = konvansiyon.arka_plan_cikar(olcum, arka_plan)
    assert net.bilesen(1) == pytest.approx(2e-6 + 0j)
    assert net.bilesen(2) == pytest.approx(2.5e-3 + 0j)  # n=2 dokunulmadi


@pytest.mark.parametrize("n", [1, 2, 3])
@pytest.mark.parametrize("genlik, faz", [(2.5e-4, 33.0), (1e-6, -120.0)])
def test_genlik_faz_gidis_donus(konvansiyon, kfg, n, genlik, faz):
    """Genlik/faz <-> C_n donusumu, faz 360/n modunda korunmali."""
    c_n = konvansiyon.genlik_fazdan(genlik, faz, n)
    geri_genlik, geri_faz = konvansiyon.genlik_faza(c_n, n)
    assert geri_genlik == pytest.approx(genlik, rel=1e-12)
    periyot = 360.0 / (n if kfg.harmonikler.faz_n_carpani else 1)
    fark = (geri_faz - faz) % periyot
    assert min(fark, periyot - fark) < 1e-9
    assert konvansiyon.genlik_fazdan(geri_genlik, geri_faz, n) == pytest.approx(c_n)


def test_normal_skew_gidis_donus(konvansiyon):
    c_n = konvansiyon.normal_skewden(1.2e-5, -3.4e-6)
    b_n, a_n = konvansiyon.normal_skewe(c_n)
    assert (b_n, a_n) == pytest.approx((1.2e-5, -3.4e-6))


def test_negatif_genlik_reddedilir(konvansiyon):
    with pytest.raises(HarmonikHatasi):
        konvansiyon.genlik_fazdan(-1e-6, 0.0, 1)


def test_units_biciminde_merkez_olcekten_bagimsiz(kfg, konvansiyon):
    """Normalize "units" girdide merkez ayni cikar (C_1/C_2 orani oldugu icin)."""
    c2 = c2_ver(kfg)
    d = complex(120e-6, -45e-6)
    c1 = -c2 * d / kfg.harmonikler.r_ref_m
    mutlak = konvansiyon.merkez(HarmonikOlcumu(bilesenler={1: c1, 2: c2}))

    units = HarmonikKonvansiyonu(dataclasses.replace(kfg.harmonikler, birim="units"))
    olcum_units = HarmonikOlcumu(bilesenler={1: (c1 / c2) * 1e4, 2: 1e4 + 0j})
    assert units.merkez(olcum_units) == pytest.approx(mutlak, abs=1e-15)


def test_units_biciminde_gradyen_mutlak_deger_ister(kfg):
    """Normalize girdi mutlak olcek tasimadigi icin gradyen ayrica girilmeli."""
    units = HarmonikKonvansiyonu(
        dataclasses.replace(kfg.harmonikler, birim="units", units_mutlak_gradyen_T_m=None)
    )
    olcum = HarmonikOlcumu(bilesenler={1: 5.0 + 0j, 2: 1e4 + 0j})
    with pytest.raises(HarmonikHatasi):
        units.gradyen_T_m(olcum)
    olcum_mutlakli = dataclasses.replace(olcum, mutlak_gradyen_T_m=0.1)
    assert units.gradyen_T_m(olcum_mutlakli) == pytest.approx(0.1)


def test_mT_birimi_tesla_ya_cevrilir(kfg):
    """mT biriminde girilen C_2, gradyeni dogru olcekle vermeli."""
    mt = HarmonikKonvansiyonu(dataclasses.replace(kfg.harmonikler, birim="mT"))
    # G = 0.1 T/m  ->  B_2 = 2.5e-3 T = 2.5 mT
    olcum = HarmonikOlcumu(bilesenler={1: 0j, 2: 2.5 + 0j})
    assert mt.gradyen_T_m(olcum) == pytest.approx(0.1, rel=1e-12)


def test_izleme_sq_ve_roll(kfg, konvansiyon):
    c2 = c2_ver(kfg)
    olcum = HarmonikOlcumu(
        bilesenler={1: 0j, 2: complex(c2.real, 0.004 * c2.real), 3: 1e-7 + 2e-7j}
    )
    izleme = konvansiyon.izleme(olcum)
    assert izleme.sq_over_g == pytest.approx(0.004, rel=1e-9)
    assert izleme.roll_mrad == pytest.approx(0.5 * math.atan(0.004) * 1e3, rel=1e-9)
    assert izleme.b3 == pytest.approx(1e-7)
    assert izleme.a3 == pytest.approx(2e-7)
    assert izleme.b4 is None


@pytest.mark.parametrize("eslenik", [False, True])
@pytest.mark.parametrize("isaret", [1, -1])
def test_konvansiyon_bayraklari_tersinir_donusum_uretir(kfg, eslenik, isaret):
    """eslenik / feed_down_isareti bayraklari merkezi yalnizca TERSINIR bir
    donusumle degistirir; bu yuzden kapali cevrimin yakinsamasini bozmazlar."""
    ayar = dataclasses.replace(kfg.harmonikler, eslenik=eslenik, feed_down_isareti=isaret)
    konvansiyon = HarmonikKonvansiyonu(ayar)
    c2 = c2_ver(kfg)
    d = complex(120e-6, -45e-6)
    c1 = -c2 * d / kfg.harmonikler.r_ref_m
    olcum = HarmonikOlcumu(
        bilesenler={
            1: konvansiyon.normal_skewden(c1.real, c1.imag),
            2: konvansiyon.normal_skewden(c2.real, c2.imag),
        }
    )
    z = konvansiyon.merkez(olcum)
    # Buyukluk her zaman korunur; yalnizca isaret/yon degisir.
    assert abs(z) == pytest.approx(abs(d), rel=1e-9)
    assert abs(z.real) == pytest.approx(abs(d.real), rel=1e-9)
    assert abs(z.imag) == pytest.approx(abs(d.imag), rel=1e-9)


def test_c2_sifirken_merkez_hesaplanmaz(konvansiyon):
    with pytest.raises(HarmonikHatasi):
        konvansiyon.merkez(HarmonikOlcumu(bilesenler={1: 1e-6 + 0j, 2: 0j}))
