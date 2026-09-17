"""Düzeltme döngüsünün testleri.

Görevde istenen senaryolar burada doğrulanır:
  * <= 3 iterasyonda toleransa yakınsama (rastgele ofsetlerden)
  * g'nin tolerans içinde kalması
  * gereken akım asimetrisinin ~ d / R_eff olması
  * monopol bileşeninin çok sayıda iterasyonda büyümemesi
  * SQ/G'nin pratikte değişmemesi (yalnızca izleniyor)
"""
from __future__ import annotations

import dataclasses

import numpy as np
import pytest

from merkezleme.duzeltme import (
    duzeltme_hesapla,
    tekrarlanabilirligi_degerlendir,
    yakinsama_durumu,
)
from merkezleme.harmonikler import KontrolVektoru

from .conftest import kalibrasyonu_yurut, y_olc


def rastgele_ofset(rng, en_buyuk_m: float = 500e-6) -> complex:
    """Büyüklüğü en_buyuk_m'yi geçmeyen rastgele yönlü ofset."""
    buyukluk = rng.uniform(0, en_buyuk_m)
    aci = rng.uniform(0, 2 * np.pi)
    return complex(buyukluk * np.cos(aci), buyukluk * np.sin(aci))


def duzeltme_dongusu(akis, kaynak, simulator, konvansiyon, mod_bazi, kfg, max_iterasyon=None):
    """Kalibrasyondan sonra düzeltme döngüsünü koşar; geçmişi döndürür."""
    sinir = kfg.duzeltme.max_iterasyon if max_iterasyon is None else max_iterasyon
    hedef = akis.kalibrasyon.gradyen_hedefi_T_m
    akimlar = mod_bazi.nominal_akimlar
    y = y_olc(simulator, konvansiyon, akimlar, hedef)
    gecmis = [(0, akimlar, y, abs(mod_bazi.monopol_bileseni(mod_bazi.bagil_sapma(akimlar))))]

    for iterasyon in range(1, sinir + 1):
        if yakinsama_durumu(y, kfg.duzeltme).yakinsadi:
            break
        oneri = duzeltme_hesapla(
            akis.kalibrasyon.R, y, akimlar, mod_bazi, kfg.duzeltme, kfg.guvenlik
        )
        assert oneri.guvenlik.guvenli, oneri.guvenlik.ihlaller
        akimlar = oneri.yeni_akimlar_A
        y = y_olc(simulator, konvansiyon, akimlar, hedef)
        gecmis.append(
            (iterasyon, akimlar, y, abs(mod_bazi.monopol_bileseni(mod_bazi.bagil_sapma(akimlar))))
        )
    return gecmis


@pytest.mark.parametrize("tohum", [1, 2, 3, 4, 5, 6])
def test_rastgele_ofsetten_uc_iterasyonda_yakinsama(
    kfg, konvansiyon, mod_bazi, simulator_uret, akis_uret, tohum
):
    """+/-500 um'ye kadar rastgele ofsetten <= 3 iterasyonda toleransa inilmeli."""
    rng = np.random.default_rng(tohum)
    ofset = rastgele_ofset(rng)
    sim = simulator_uret(ofset_m=ofset, tohum=tohum)
    akis, kaynak, _ = akis_uret(sim)
    kalibrasyonu_yurut(akis, kaynak)

    gecmis = duzeltme_dongusu(akis, kaynak, sim, konvansiyon, mod_bazi, kfg)
    iterasyon, akimlar, son_y, _ = gecmis[-1]

    assert iterasyon <= 3, f"{iterasyon} iterasyon gerekti"
    durum = yakinsama_durumu(son_y, kfg.duzeltme)
    assert durum.merkez_tamam, f"merkez toleransa inmedi: {son_y}"
    # g tolerans içinde kalmalı
    assert durum.g_tamam, f"g toleransın dışında: {son_y.g}"
    assert durum.yakinsadi


@pytest.mark.parametrize("tohum", [11, 12, 13])
def test_akim_asimetrisi_d_bolu_r_eff(kfg, konvansiyon, mod_bazi, simulator_uret, akis_uret, tohum):
    """Gereken akım asimetrisi ~ d / R_eff olmalı (köşegende en fazla sqrt(2) kat)."""
    rng = np.random.default_rng(tohum)
    ofset = rastgele_ofset(rng, 400e-6)
    sim = simulator_uret(ofset_m=ofset, tohum=tohum)
    akis, kaynak, _ = akis_uret(sim)
    kalibrasyonu_yurut(akis, kaynak)

    gecmis = duzeltme_dongusu(akis, kaynak, sim, konvansiyon, mod_bazi, kfg)
    _, akimlar, _, _ = gecmis[-1]

    nominal = kfg.miknatis.nominal_akim_A
    olculen_asimetri = float(np.max(np.abs(akimlar - nominal)) / nominal)
    beklenen = abs(ofset) / abs(akis.kalibrasyon.r_eff_m)
    # Tek eksende beklenen kadar, köşegende en fazla sqrt(2) katı
    assert beklenen * 0.6 <= olculen_asimetri <= beklenen * np.sqrt(2) * 1.1 + 2e-4, (
        olculen_asimetri,
        beklenen,
    )


def test_monopol_bileseni_cok_iterasyonda_buyumez(
    kfg, konvansiyon, mod_bazi, simulator_uret, akis_uret
):
    """Yakınsadıktan sonra da sürdürülen iterasyonlarda monopol birikmemeli."""
    sim = simulator_uret(ofset_m=complex(300e-6, -200e-6), tohum=21)
    akis, kaynak, _ = akis_uret(sim)
    kalibrasyonu_yurut(akis, kaynak)

    hedef = akis.kalibrasyon.gradyen_hedefi_T_m
    akimlar = mod_bazi.nominal_akimlar
    monopoller = []
    for _ in range(40):  # yakınsama olsa da devam et
        y = y_olc(sim, konvansiyon, akimlar, hedef)
        oneri = duzeltme_hesapla(
            akis.kalibrasyon.R, y, akimlar, mod_bazi, kfg.duzeltme, kfg.guvenlik
        )
        akimlar = oneri.yeni_akimlar_A
        monopoller.append(abs(mod_bazi.monopol_bileseni(mod_bazi.bagil_sapma(akimlar))))

    assert max(monopoller) < 1e-12, f"monopol birikti: {max(monopoller):.3e}"


def test_monopol_cikarma_kapatilinca_bileseni_gorunur(kfg, mod_bazi):
    """monopol_cikar=False iken, dışarıdan gelen monopol bileşeni temizlenmez."""
    R = mod_bazi.response_matrisi(
        {
            "H": np.array([-0.0408, 0.0, 0.0]),
            "V": np.array([0.0, -0.0408, 0.0]),
            "Q": np.array([0.0, 0.0, 1.0]),
        }
    )
    # Başlangıç akımlarında yapay bir monopol bileşeni var
    kirli = mod_bazi.akimlar(0.002 * mod_bazi.mod_vektoru("M"))
    y = KontrolVektoru(x_c=50e-6, y_c=0.0, g=0.0)

    acik = duzeltme_hesapla(
        R, y, kirli, mod_bazi, dataclasses.replace(kfg.duzeltme, monopol_cikar=True), kfg.guvenlik
    )
    kapali = duzeltme_hesapla(
        R, y, kirli, mod_bazi, dataclasses.replace(kfg.duzeltme, monopol_cikar=False), kfg.guvenlik
    )
    assert abs(mod_bazi.monopol_bileseni(mod_bazi.bagil_sapma(acik.yeni_akimlar_A))) < 1e-15
    assert (
        abs(mod_bazi.monopol_bileseni(mod_bazi.bagil_sapma(kapali.yeni_akimlar_A)))
        == pytest.approx(0.002, rel=1e-9)
    )


def test_sq_over_g_pratikte_degismez(kfg, konvansiyon, mod_bazi, simulator_uret, akis_uret):
    """SQ/G hedeflenmez; düzeltme önünde anlamlı bir değişiklik yapmamalı."""
    sim = simulator_uret(ofset_m=complex(350e-6, 250e-6), roll_rad=1e-3, tohum=31)
    akis, kaynak, _ = akis_uret(sim)
    kalibrasyonu_yurut(akis, kaynak)

    hedef = akis.kalibrasyon.gradyen_hedefi_T_m
    once = konvansiyon.izleme(sim.olc(mod_bazi.nominal_akimlar, gurultu=False)).sq_over_g
    gecmis = duzeltme_dongusu(akis, kaynak, sim, konvansiyon, mod_bazi, kfg)
    _, akimlar, _, _ = gecmis[-1]
    sonra = konvansiyon.izleme(sim.olc(akimlar, gurultu=False)).sq_over_g

    assert once is not None and sonra is not None
    # Roll'dan gelen SQ/G ~ -0.002; düzeltmenin etkisi bunun %1'inden küçük olmalı
    assert abs(sonra - once) < 0.01 * abs(once) + 1e-6, (once, sonra)


def test_guvenlik_sinirlari_asilinca_uygulanmaz(kfg, mod_bazi):
    """Çözüm adım başı ya da toplam asimetri sınırını aşıyorsa güvenli değil."""
    R = mod_bazi.response_matrisi(
        {
            "H": np.array([-0.0408, 0.0, 0.0]),
            "V": np.array([0.0, -0.0408, 0.0]),
            "Q": np.array([0.0, 0.0, 1.0]),
        }
    )
    # 2 mm'lik ofset: gereken asimetri ~%5, adım başı sınır %2
    y = KontrolVektoru(x_c=2000e-6, y_c=0.0, g=0.0)
    oneri = duzeltme_hesapla(R, y, mod_bazi.nominal_akimlar, mod_bazi, kfg.duzeltme, kfg.guvenlik)
    assert not oneri.guvenlik.guvenli
    assert any("adım başı" in i for i in oneri.guvenlik.ihlaller)


def test_maks_akim_siniri_kontrol_edilir(kfg, mod_bazi):
    R = mod_bazi.response_matrisi({"Q": np.array([0.0, 0.0, 1.0])})
    # Çok büyük bir gradyen hatası -> Q modunda büyük akım artışı
    y = KontrolVektoru(x_c=0.0, y_c=0.0, g=-0.5)
    guvenlik = dataclasses.replace(kfg.guvenlik, adim_basi_max_bagil_degisim=1.0,
                                   nominale_gore_max_asimetri=1.0)
    oneri = duzeltme_hesapla(R, y, mod_bazi.nominal_akimlar, mod_bazi, kfg.duzeltme, guvenlik)
    assert not oneri.guvenlik.guvenli
    assert any("max" in i for i in oneri.guvenlik.ihlaller)


def test_oneri_ozeti_beklenen_degisimi_gosterir(kfg, mod_bazi):
    R = mod_bazi.response_matrisi(
        {
            "H": np.array([-0.0408, 0.0, 0.0]),
            "V": np.array([0.0, -0.0408, 0.0]),
            "Q": np.array([0.0, 0.0, 1.0]),
        }
    )
    y = KontrolVektoru(x_c=100e-6, y_c=-50e-6, g=1e-4)
    oneri = duzeltme_hesapla(R, y, mod_bazi.nominal_akimlar, mod_bazi, kfg.duzeltme, kfg.guvenlik)
    metin = oneri.ozet_metni(kfg.miknatis.nominal_akim_A)
    assert "Beklenen merkez değişimi" in metin
    assert "Mod genlikleri" in metin
    # alpha = 0.9 -> beklenen y, ölçülenin %10'una inmeli
    assert oneri.beklenen_y.x_c == pytest.approx(y.x_c * (1 - kfg.duzeltme.alpha), rel=1e-6)


def test_tekrarlanabilirlik_ve_tolerans_uyarisi(kfg, konvansiyon, mod_bazi, simulator_uret):
    """Tolerans, ölçülen tekrarlanabilirliğin katından küçükse uyarılmalı."""
    sim = simulator_uret(ofset_m=complex(100e-6, 0), tohum=41)
    hedef = sim.gradyen_T_m(mod_bazi.nominal_akimlar)
    olcumler = [
        y_olc(sim, konvansiyon, mod_bazi.nominal_akimlar, hedef)
        for _ in range(kfg.duzeltme.tekrarlanabilirlik_N)
    ]
    sonuc = tekrarlanabilirligi_degerlendir(olcumler, kfg.duzeltme)
    assert sonuc.n == kfg.duzeltme.tekrarlanabilirlik_N
    assert sonuc.merkez_sigma_m > 0
    assert sonuc.tolerans_yeterli_mi, sonuc.uyarilar

    siki = dataclasses.replace(kfg.duzeltme, merkez_toleransi_um=0.01)
    sonuc_siki = tekrarlanabilirligi_degerlendir(olcumler, siki)
    assert not sonuc_siki.tolerans_yeterli_mi
    assert any("çok sıkı" in u for u in sonuc_siki.uyarilar)


def test_tek_olcumle_tekrarlanabilirlik_hesaplanmaz(kfg):
    with pytest.raises(ValueError):
        tekrarlanabilirligi_degerlendir([KontrolVektoru(0.0, 0.0, 0.0)], kfg.duzeltme)
