"""mil_hizalama.pencere_analizi: bilinen hız dalgalanması ve gürültüyle sentetik veri."""
from __future__ import annotations

import math

import numpy as np
import pytest

from mil_hizalama import pencere_analizi

SPS = 7200.0


def veri(f_hz=8.0, sure_s=4.0, ripil=(0.0, 0.0), gurultu_V=0.0, bozuk=0, tohum=0, titresim=0.0, f_t=19.7):
    """Enkoder ~1 ms'de bir okur, her ADC örneği son okumayı taşır (merdiven).
    Açıda 1x ve 2x dalgalanma (derece genlik); gerilimde dipol + kuadrupol."""
    rng = np.random.default_rng(tohum)
    w = 2 * math.pi * f_hz

    def teta(t):
        th = w * t + 0.3
        return th + math.radians(ripil[0]) * np.sin(th + 0.7) + math.radians(ripil[1]) * np.sin(2 * th + 1.9)

    t = np.arange(int(sure_s * SPS)) / SPS
    th = teta(t)
    # titresim: f_t'de bağıl modülasyon (eksen sallanıyor) + aynı frekansta doğrudan bileşen
    mod = 1 + titresim * np.sin(2 * math.pi * f_t * t)
    v = (mod * (40e-6 * np.cos(th) + 2e-3 * np.sin(2 * th + 0.4)) + 2e-6 * titresim / 1e-3
         * np.sin(2 * math.pi * f_t * t + 0.5) - 4.6e-3 + rng.normal(0, gurultu_V, len(t)))
    okuma = (np.arange(int(sure_s / 1e-3) + 2) + 0.31) * 1e-3
    oku = np.degrees(teta(okuma)) % 360
    if bozuk:
        i = rng.choice(np.arange(20, len(okuma) - 20, 7), bozuk, replace=False)
        oku[i] = (oku[i] + rng.uniform(40, 320, bozuk)) % 360
    k = np.searchsorted(okuma, t, side="right") - 1
    aci = np.round(oku[np.clip(k, 0, None)], 1)  # enkoder çözünürlüğü 0.1°
    return aci, v


def test_hiz_dalgalanmasi_olculur():
    s = pencere_analizi(*veri(ripil=(0.5, 0.2)), SPS)
    assert s["hiz_hz"] == pytest.approx(8.0, abs=1e-3)
    assert s["ripil_1x_derece"] == pytest.approx(0.5, abs=0.02)
    assert s["ripil_2x_derece"] == pytest.approx(0.2, abs=0.02)
    assert s["ripil_3x_derece"] < 0.02


def test_dalgalanmasiz_veride_taban_kucuk_ve_gurultu_olculur():
    s = pencere_analizi(*veri(gurultu_V=30e-6), SPS)
    assert s["ripil_1x_derece"] < 0.01 and s["ripil_2x_derece"] < 0.01
    assert s["artik_uV"] == pytest.approx(30.0, rel=0.1)
    assert s["dusuk_frekans_uV"] < 5  # beyaz gürültünün 0.5-6 Hz payı küçük
    assert s["bozuk_aci_s"] == 0


def test_bozuk_acilar_sayilir_ve_dalgalanmayi_bozmaz():
    s = pencere_analizi(*veri(ripil=(0.5, 0.0), bozuk=8), SPS)
    assert s["bozuk_aci_s"] == pytest.approx(8 / 4.0)
    assert s["ripil_1x_derece"] == pytest.approx(0.5, abs=0.02)


def test_motor_dururken_nan():
    aci = np.full(28800, 123.4)
    s = pencere_analizi(aci, np.zeros(28800), SPS)
    assert math.isnan(s["hiz_hz"]) and s["bozuk_aci_s"] == 0


def test_titresim_ve_yan_bantlari_bulunur():
    s0 = pencere_analizi(*veri(gurultu_V=5e-6), SPS)
    s1 = pencere_analizi(*veri(gurultu_V=5e-6, titresim=1e-3), SPS)
    assert s1["titresim_hz"] == pytest.approx(19.7, abs=0.3)
    assert s1["titresim_uV"] == pytest.approx(2.0 / math.sqrt(2), rel=0.2)  # 2 µV genlik -> rms
    assert s1["yan_bant_uV"] == pytest.approx(1.0 / math.sqrt(2), rel=0.2)  # 16 Hz sinyalin |2f - f_t| yan bandı
    assert s1["yan_bant_uV"] > 3 * s0["yan_bant_uV"] and s1["titresim_uV"] > 5 * s0["titresim_uV"]
