"""Mod bazı ve simülatör fiziğinin analitik kontrolleri.

Simülatörün çıktısı, elle türetilmiş analitik sonuçlarla karşılaştırılır:

    R_eff = a * sqrt(2) / (4 * cos(alpha))

Bu, kullanıcının verdiği sayılarla da tutarlıdır: a = 100 mm, alpha = 30 derece
için R_eff = 40.8 mm (beklenen ~40 mm) ve d = 100 um için dI/I = %0.245
(beklenen ~%0.25).
"""
from __future__ import annotations

import numpy as np
import pytest

from merkezleme.modlar import MOD_SIRASI, ModBazi


# ---------------------------------------------------------------------------
# Mod bazı
# ---------------------------------------------------------------------------
def test_mod_matrisi_ortogonal(mod_bazi: ModBazi):
    V = mod_bazi.mod_matrisi
    assert np.allclose(V.T @ V, 4 * np.eye(4))


def test_isaretli_akim_desenleri(mod_bazi: ModBazi):
    """Genlik bazındaki modlar, işaretli akımda beklenen desenleri vermeli."""
    nominal_isaretli = mod_bazi.isaretli_akimlar(mod_bazi.nominal_akimlar)
    beklenen = {
        "Q": [1, -1, 1, -1],  # nominal kuadrupol deseni
        "H": [1, 1, -1, -1],  # yatay dipol
        "V": [1, -1, -1, 1],  # düşey dipol
        "M": [1, 1, 1, 1],  # üniform -> monopol
    }
    for mod, desen in beklenen.items():
        sapma = mod_bazi.isaretli_akimlar(mod_bazi.mod_akimlari(mod, 0.005)) - nominal_isaretli
        assert np.allclose(np.sign(sapma), desen), (mod, sapma)
    # M modu işaretli akımda gerçekten üniform
    sapma_m = mod_bazi.isaretli_akimlar(mod_bazi.mod_akimlari("M", 0.005)) - nominal_isaretli
    assert np.allclose(sapma_m, sapma_m[0])


def test_mod_genlikleri_gidis_donus(mod_bazi: ModBazi):
    x = 0.003 * mod_bazi.mod_vektoru("H") - 0.001 * mod_bazi.mod_vektoru("V")
    genlikler = mod_bazi.mod_genlikleri(x)
    assert genlikler["H"] == pytest.approx(0.003)
    assert genlikler["V"] == pytest.approx(-0.001)
    assert genlikler["Q"] == pytest.approx(0.0)
    assert genlikler["M"] == pytest.approx(0.0)


def test_monopol_cikarma(mod_bazi: ModBazi):
    x = 0.002 * mod_bazi.mod_vektoru("M") + 0.001 * mod_bazi.mod_vektoru("H")
    temiz = mod_bazi.monopol_cikar(x)
    assert abs(mod_bazi.monopol_bileseni(temiz)) < 1e-15
    # H bileşeni korunmalı
    assert mod_bazi.mod_genlikleri(temiz)["H"] == pytest.approx(0.001)


def test_R_kurulumu_ve_sifir_uzayi(mod_bazi: ModBazi):
    S = {
        "H": np.array([-0.0408, 0.0, 0.0]),
        "V": np.array([0.0, -0.0408, 0.0]),
        "Q": np.array([0.0, 0.0, 1.0]),
    }
    R = mod_bazi.response_matrisi(S)
    assert R.shape == (3, 4)
    # M yönü R'nin sıfır uzayında
    assert np.allclose(R @ mod_bazi.mod_vektoru("M"), 0)
    # pinv çözümü monopol bileşeni üretmez
    dI = np.linalg.pinv(R) @ np.array([100e-6, -50e-6, 1e-3])
    assert abs(mod_bazi.monopol_bileseni(dI)) < 1e-15
    # geri okuma
    geri = mod_bazi.mod_egimlerine_ayir(R)
    for mod, egim in S.items():
        assert np.allclose(geri[mod], egim)
    assert np.allclose(geri["M"], 0)


# ---------------------------------------------------------------------------
# Simülatör fiziği
# ---------------------------------------------------------------------------
def test_nominal_desen_normal_kuadrupol_uretir(temiz_simulator, mod_bazi):
    """Köşegen yerleşim + racetrack çifti -> nominal desen NORMAL kuadrupol."""
    c2 = temiz_simulator.harmonik_ham_T(mod_bazi.nominal_akimlar, 2)
    c1 = temiz_simulator.harmonik_ham_T(mod_bazi.nominal_akimlar, 1)
    assert abs(c2.imag) < 1e-12 * abs(c2.real), "C_2 saf normal değil"
    assert abs(c1) < 1e-15, "ofsetsiz durumda dipol olmamalı"


def test_H_modu_x_c_yi_V_modu_y_c_yi_hareket_ettirir(temiz_simulator, mod_bazi, konvansiyon):
    z_H = konvansiyon.merkez(temiz_simulator.olc(mod_bazi.mod_akimlari("H", 0.005), gurultu=False))
    z_V = konvansiyon.merkez(temiz_simulator.olc(mod_bazi.mod_akimlari("V", 0.005), gurultu=False))
    assert abs(z_H.imag) < 1e-9 * abs(z_H.real), "H modu y_c yi de oynatıyor"
    assert abs(z_V.real) < 1e-9 * abs(z_V.imag), "V modu x_c yi de oynatıyor"


def test_Q_modu_yalnizca_gradyeni_degistirir(temiz_simulator, mod_bazi, konvansiyon):
    eps = 0.005
    olcum = temiz_simulator.olc(mod_bazi.mod_akimlari("Q", eps), gurultu=False)
    gradyen_nominal = temiz_simulator.gradyen_T_m(mod_bazi.nominal_akimlar)
    g = (konvansiyon.gradyen_T_m(olcum) - gradyen_nominal) / gradyen_nominal
    assert g == pytest.approx(eps, rel=1e-9), "dg/deps_Q = 1 olmalı"
    assert abs(konvansiyon.merkez(olcum)) < 1e-12


def test_M_modu_dipole_ve_gradyene_katkisiz(temiz_simulator, mod_bazi, konvansiyon):
    """Monopol modu: racetrack bobinlerde net akım sıfır -> hiçbir etkisi yok."""
    olcum = temiz_simulator.olc(mod_bazi.mod_akimlari("M", 0.005), gurultu=False)
    gradyen_nominal = temiz_simulator.gradyen_T_m(mod_bazi.nominal_akimlar)
    g = (konvansiyon.gradyen_T_m(olcum) - gradyen_nominal) / gradyen_nominal
    assert abs(konvansiyon.merkez(olcum)) < 1e-15
    assert abs(g) < 1e-12


def test_r_eff_analitik_degerle_ortusur(temiz_simulator, mod_bazi, konvansiyon, kfg):
    """Ölçülen R_eff = a*sqrt(2)/(4*cos(alpha)) olmalı."""
    eps = 0.005
    z_H = konvansiyon.merkez(temiz_simulator.olc(mod_bazi.mod_akimlari("H", eps), gurultu=False))
    gradyen_nominal = temiz_simulator.gradyen_T_m(mod_bazi.nominal_akimlar)
    olcum_Q = temiz_simulator.olc(mod_bazi.mod_akimlari("Q", eps), gurultu=False)
    dg_deps = ((konvansiyon.gradyen_T_m(olcum_Q) - gradyen_nominal) / gradyen_nominal) / eps
    r_eff = (z_H.real / eps) / dg_deps
    assert abs(r_eff) == pytest.approx(kfg.simulator.beklenen_r_eff_m, rel=1e-4)
    # Kullanıcının verdiği sayı: ~40 mm
    assert 0.035 < abs(r_eff) < 0.045


@pytest.mark.parametrize(
    "dx_um, dy_um", [(120.0, -45.0), (-500.0, 300.0), (0.0, 500.0), (-350.0, 0.0)]
)
def test_mekanik_ofset_merkez_olarak_okunur(simulator_uret, mod_bazi, konvansiyon, dx_um, dy_um):
    # Yalnızca ofset -> merkez eşleşmesi sınanıyor: roll ve arka plan açıkça sıfır.
    sim = simulator_uret(
        ofset_m=complex(dx_um * 1e-6, dy_um * 1e-6),
        roll_rad=0.0,
        arka_plan_T=0j,
        harmonik_gurultu_bagil=0.0,
    )
    z = konvansiyon.merkez(sim.olc(mod_bazi.nominal_akimlar, gurultu=False))
    assert z.real == pytest.approx(dx_um * 1e-6, abs=1e-9)
    assert z.imag == pytest.approx(dy_um * 1e-6, abs=1e-9)


def test_beklenen_akim_asimetrisi_d_bolu_r_eff(kfg):
    """d = 100 um için dI/I ~ %0.25 (kullanıcının verdiği sayı)."""
    oran = 100e-6 / kfg.simulator.beklenen_r_eff_m
    assert oran == pytest.approx(0.00245, abs=1e-4)


def test_gurultu_seviyesi_tolerans_icin_yeterince_kucuk(simulator_uret, mod_bazi, konvansiyon, kfg):
    """Varsayılan gürültü, 5 um tolerans için tekrarlanabilirlik kontrolünü geçmeli."""
    sim = simulator_uret(ofset_m=complex(100e-6, 0), arka_plan_T=0j, tohum=3)
    hedef = sim.gradyen_T_m(mod_bazi.nominal_akimlar)
    merkezler = [konvansiyon.merkez(sim.olc(mod_bazi.nominal_akimlar)) for _ in range(200)]
    sigma = float(np.std([z.real for z in merkezler]))
    gereken = kfg.duzeltme.tolerans_tekrarlanabilirlik_carpani * sigma
    assert kfg.duzeltme.merkez_toleransi_m > gereken, (sigma, gereken)


def test_yerlesim_hatalari_skew_kuadrupol_uretir(simulator_uret, mod_bazi, konvansiyon):
    """Açısal yerleşim hatası, SQ/G'yi sıfırdan farklı yapar (izleme büyüklüğü)."""
    sim = simulator_uret(
        ofset_m=0j,
        roll_rad=0.0,
        arka_plan_T=0j,
        harmonik_gurultu_bagil=0.0,
        yerlesim_hatasi_acisal_mrad=[5.0, 0.0, 0.0, 0.0],
    )
    izleme = konvansiyon.izleme(sim.olc(mod_bazi.nominal_akimlar, gurultu=False))
    assert izleme.sq_over_g is not None and abs(izleme.sq_over_g) > 1e-6
