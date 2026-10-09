"""Ölçüm analizinin BAĞIMSIZ bir fizik modeline karşı sınanması.

Buradaki model `merkezleme_koprusu`'nun formüllerini (K_n, çok kutup serisi)
kullanmaz: alan, merkezleme simülatörünün iletkenlerinden doğrudan
B_y + i·B_x = μ0/2π · Σ I_j / (z - z_j) ile; akı, bobin kesiti boyunca alanın
Gauss-Legendre integraliyle; gerilim, akının zamana göre türeviyle bulunur.
Enkoder firmware'deki gibi modellenir: stator ~1 ms'de bir okur, değer
gecikmeyle rotora ulaşır, her ADC örneği son gelen değeri taşır (merdiven).
ADC örneği ayrıca filtre gecikmesi kadar eskidir.

Gerçek değerler simülatörün kendi harmonikleri ve gerçek manyetik merkezidir.
"""
from __future__ import annotations

import math

import numpy as np
import pytest

from mgf import merkezleme_koprusu as mk

SPS = 7200.0
ADC_GECIKMESI_S = 2.8e-4  # örnek, açıya göre bu kadar eski
ENKODER_ILETIMI_S = 1.0e-4  # okunan açı rotora bu kadar geç ulaşır
NET_GECIKME_S = ADC_GECIKMESI_S - ENKODER_ILETIMI_S


class BagimsizModel:
    def __init__(self) -> None:
        from merkezleme.simulator import MU0_2PI, Simulator
        from merkezleme.yapilandirma import yapilandirma_yukle

        kfg = yapilandirma_yukle(mk.REPO_KOKU / "yapilandirma.yaml")
        self.sim = Simulator(kfg.simulator, kfg.miknatis, kfg.harmonikler)
        self.sim.ofset_m = complex(150e-6, -80e-6)
        self.akimlar = np.array([9.5, 9.45, 9.55, 9.5])
        polarite = np.array(kfg.miknatis.nominal_polarite, float)
        iletkenler = self.sim.iletkenler()
        self.z0 = np.array([i.konum for i in iletkenler])
        self.akim = np.array([self.akimlar[i.bobin] * polarite[i.bobin] * i.sarim for i in iletkenler])
        self.mu0_2pi = MU0_2PI
        self.gx, self.gw = np.polynomial.legendre.leggauss(24)
        self.gercek = [self.sim.harmonik_ham_T(self.akimlar, n) for n in range(1, 7)]
        self.merkez = self.sim.gercek_merkez_m(self.akimlar)
        self.r_ref = mk.parametreleri_yukle().r_ref_m

    def _alan(self, z):
        z = np.asarray(z)[..., None]
        return self.mu0_2pi * np.sum(self.akim / (z - self.z0), axis=-1)

    def _aki_birim(self, z1, z2, dipol_T=None):
        """Birim uzunluk başına akı, z1 -> z2 kesiti boyunca ∫(B_y dx - B_x dy)."""
        dz = z2 - z1
        if dipol_T is not None:  # düzgün düşey alan (referans mıknatıs)
            return dipol_T * dz.real
        s, w = (self.gx + 1) / 2, self.gw / 2
        f = self._alan(z1[..., None] + s * dz[..., None])
        return np.sum(w * (f.real * dz.real[..., None] - f.imag * dz.imag[..., None]), axis=-1)

    def veri(self, bobin, f_hz=23.0, sure_s=2.0, dalga_derece=0.0, tohum=0,
             titresim_s=0.0, atla=0.0, kayip=0, gurultu_V=0.0, dipol_T=None):
        """(enkoder açısı °, bobin gerilimi V) — firmware'in gönderdiği gibi."""
        rng = np.random.default_rng(tohum)
        w = 2 * math.pi * f_hz
        d = math.radians(dalga_derece)

        def teta(t):  # tur başına 1 ve 2 periyotlu hız dalgalanması
            th = w * t + 0.4
            return th + d * np.sin(th + 0.3) + 0.5 * d * np.sin(2 * th + 1.1)

        z1, z2 = bobin.iletken_konumlari()
        nl = bobin.sarim_sayisi * bobin.uzunluk_m

        def aki(t):
            e = np.exp(1j * teta(t))
            return nl * self._aki_birim(z1 * e, z2 * e, dipol_T)

        t = np.arange(int(sure_s * SPS)) / SPS
        ta, h = t - ADC_GECIKMESI_S, 1e-7
        v = -(aki(ta + h) - aki(ta - h)) / (2 * h)
        if gurultu_V:
            v = v + rng.normal(0.0, gurultu_V, len(v))
        okuma = (np.arange(-2, int(t[-1] / 1e-3) + 4) + 0.31) * 1e-3 * (1 + 40e-6)
        okuma = okuma[rng.random(len(okuma)) >= atla]
        okuma = np.sort(okuma + rng.normal(0.0, titresim_s, len(okuma)) if titresim_s else okuma)
        k = np.searchsorted(okuma + ENKODER_ILETIMI_S, t, side="right") - 1
        aci = (np.degrees(teta(okuma[k])) % 360).astype(np.float32)
        v = v.astype(np.float32)
        if kayip:
            sil = rng.choice(np.arange(1000, len(t) - 1000), kayip, replace=False)
            aci, v = np.delete(aci, sil), np.delete(v, sil)
        return aci, v


@pytest.fixture(scope="module")
def model():
    return BagimsizModel()


def bobin(tip="teget"):
    p = mk.parametreleri_yukle()
    return mk.BobinGeometrisi(
        p.bobin.sarim_sayisi, p.bobin.uzunluk_m, p.bobin.genislik_m, p.bobin.eksene_uzaklik_m, tip
    )


def olc(model, b, gecikme_s=0.0, **kw):
    """Referans dipolle faz ofseti bulunup ölçülür (lab akışı)."""
    ref = mk.olcum_hesapla(*model.veri(b, dipol_T=1e-3, **kw), SPS, b, model.r_ref, gecikme_s=gecikme_s)
    ofset = mk.referans_faz_ofseti(ref, 0.0)
    return mk.olcum_hesapla(*model.veri(b, **kw), SPS, b, model.r_ref, ofset, gecikme_s=gecikme_s)


def ust_hata(model, s):
    """n = 3..6 hatası, |C2|'nin 1e-4'ü biriminde."""
    return max(abs(s.harmonikler[n] - model.gercek[n]) for n in range(2, 6)) / abs(model.gercek[1]) * 1e4


@pytest.mark.parametrize("tip", ["teget", "radyal"])
@pytest.mark.parametrize("f_hz", [23.0, -23.0, 10.0])
def test_merkez_ve_harmonikler_gercekci_enkoderle(model, tip, f_hz):
    """Merdivenli, gecikmeli enkoder; iki yön; iki bobin tipi."""
    s = olc(model, bobin(tip), f_hz=f_hz, gecikme_s=NET_GECIKME_S)
    assert abs(s.merkez_m - model.merkez) < 0.2e-6
    assert s.c2 == pytest.approx(model.gercek[1], rel=5e-5)
    assert ust_hata(model, s) < 0.3
    assert s.artik_orani < 1e-3 and s.aci_yontemi == "okuma saati"
    assert s.saat_sicramasi < 0.4 and mk.saglik_sorunlari(s, mk.parametreleri_yukle()) == []
    assert math.copysign(1, s.hiz_hz) == math.copysign(1, f_hz)


def test_hiz_dalgalanmasi_aki_integrasyonuyla_etkisiz(model):
    """Tur içi 2° açı dalgalanması (~%4 hız dalgası): akı uzayında hız hiç
    kullanılmadığı için merkez etkilenmez (gecikme biliniyorsa)."""
    s = olc(model, bobin(), dalga_derece=2.0, gecikme_s=NET_GECIKME_S)
    assert abs(s.merkez_m - model.merkez) < 0.3e-6
    assert ust_hata(model, s) < 0.3


def test_bilinmeyen_gecikme_dalgalanmayla_hata_yapar(model):
    """Gecikme 0 sanılırsa hız dalgalanması n = 2'yi n = 1'e karıştırır:
    bu test, gecikme ölçümünün neden gerektiğini belgeler."""
    s = olc(model, bobin(), dalga_derece=2.0, gecikme_s=0.0)
    assert abs(s.merkez_m - model.merkez) > 5e-6


@pytest.mark.parametrize("dipol", [False, True])
def test_cift_yon_gecikmeyi_olcer(model, dipol):
    """İki yönlü ölçüm net gecikmeyi bulur; referans dipolde (C2 = 0) de
    (faz n = 1'den ölçülür)."""
    b = bobin()
    kw = dict(dalga_derece=1.0, dipol_T=1e-3 if dipol else None)
    s = mk.cift_yon_hesapla(
        model.veri(b, f_hz=23.0, **kw), model.veri(b, f_hz=-23.0, tohum=7, **kw), SPS, b, model.r_ref
    )
    assert s.cift_yon
    assert s.gecikme_s == pytest.approx(NET_GECIKME_S, abs=3e-6)


def test_cift_yon_birlesik_olcum_dogru(model):
    b = bobin()
    kw = dict(dalga_derece=2.0)
    ref = mk.cift_yon_hesapla(
        model.veri(b, f_hz=23.0, dipol_T=1e-3, **kw), model.veri(b, f_hz=-23.0, dipol_T=1e-3, **kw),
        SPS, b, model.r_ref,
    )
    ofset = mk.referans_faz_ofseti(ref, 0.0)
    s = mk.cift_yon_hesapla(
        model.veri(b, f_hz=23.0, **kw), model.veri(b, f_hz=-23.0, tohum=3, **kw), SPS, b, model.r_ref, ofset
    )
    assert abs(s.merkez_m - model.merkez) < 0.3e-6
    assert ust_hata(model, s) < 0.3


def test_enkoder_atlama_ve_titresimi(model):
    s = olc(model, bobin(), atla=0.01, titresim_s=5e-6, gecikme_s=NET_GECIKME_S)
    assert abs(s.merkez_m - model.merkez) < 2e-6
    assert s.saat_sicramasi < 0.4  # atlanan okumalar ve titreşim kayıp sanılmaz


@pytest.mark.parametrize("tohum", range(4))
def test_tek_ornek_kaybi_okuma_saatinden_yakalanir(model, tohum):
    """Tek bir kayıp örnek artığı eşiğin altında bırakabilir; ama enkoder
    okumalarının düzenli saatine göre bir örneklik kalıcı kayma yaratır."""
    p = mk.parametreleri_yukle()
    b = bobin()
    s = mk.olcum_hesapla(*model.veri(b, kayip=1, tohum=tohum), SPS, b, model.r_ref)
    assert s.saat_sicramasi > 0.8
    assert any("sıçrama" in m for m in mk.saglik_sorunlari(s, p))


def test_ornek_kaybi_artikla_yakalanir(model):
    """Akı integrali örneklerin zamanda düzgün olduğunu varsayar; kaybolan
    örnekler merkezi bozar ve bunu artık oranı eşiği yakalar."""
    p = mk.parametreleri_yukle()
    saglam = olc(model, bobin(), gecikme_s=NET_GECIKME_S)
    kayipli = olc(model, bobin(), kayip=3, gecikme_s=NET_GECIKME_S)
    assert saglam.artik_orani < p.artik_esigi / 10
    assert kayipli.artik_orani > p.artik_esigi


def test_gurultu_ve_sure(model):
    """1 µV gürültü (ADC 32x tabanının birkaç katı) merkezde µm altı hata."""
    s = olc(model, bobin(), gurultu_V=1e-6, gecikme_s=NET_GECIKME_S)
    assert abs(s.merkez_m - model.merkez) < 1e-6
