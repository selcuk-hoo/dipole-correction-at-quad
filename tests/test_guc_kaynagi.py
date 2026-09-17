"""Guc kaynagi katmani testleri (sahte kaynaklarla, kuru calisma)."""
from __future__ import annotations

import dataclasses

import numpy as np
import pytest

from merkezleme.guc_kaynagi import (
    GucKaynagiHatasi,
    GuvenlikHatasi,
    KaynakGrubu,
    KomutGunlugu,
    SahteGucKaynagi,
)


@pytest.fixture
def grup(kaynak_grubu_uret) -> KaynakGrubu:
    g = kaynak_grubu_uret()
    g.baslat()
    return g


def komutlar(grup: KaynakGrubu) -> list[str]:
    return [k.komut for k in grup.gunluk.kayitlar]


def test_uyum_gerilimi_akimdan_once_yazilir(grup):
    """Sabit akim kipinde VOLT bir uyum sinirdir; CURR'den once yazilmali."""
    kayitlar = komutlar(grup)
    ilk_volt = next(i for i, k in enumerate(kayitlar) if k.startswith("VOLT"))
    ilk_curr = next(i for i, k in enumerate(kayitlar) if k.startswith("CURR"))
    assert ilk_volt < ilk_curr


def test_kullanilan_komut_kumesi_genisletilmemis(grup):
    """Yalnizca izin verilen SCPI komutlari kullanilmali."""
    grup.rampala(np.full(4, 1.0))
    grup.olcumleri_oku()
    izinli_onekler = (
        "*CLS",
        "*IDN?",
        "SYST:REM",
        "SYST:ERR?",
        "VOLT",
        "CURR",
        "OUTP ON",
        "OUTP OFF",
        "MEAS:VOLT?",
        "MEAS:CURR?",
        "(baglanti kapatildi)",
    )
    for komut in komutlar(grup):
        assert komut.startswith(izinli_onekler), f"izin verilmeyen komut: {komut}"


def test_akim_tek_adimda_degismez(grup, kfg):
    """Rampa: adim sayisi hiz ve adim suresiyle belirlenir, tek adim olamaz."""
    onceki = len(grup.gunluk.kayitlar)
    grup.rampala(np.full(4, 10.0))
    yeni_curr = [
        k for k in grup.gunluk.kayitlar[onceki:] if k.komut.startswith("CURR")
    ]
    adim_sayisi = len(yeni_curr) // 4
    beklenen = int(
        np.ceil(10.0 / (kfg.guc_kaynaklari.rampa_hizi_A_s * kfg.guc_kaynaklari.rampa_adim_suresi_s))
    )
    assert adim_sayisi == beklenen > 1


def test_rampa_dort_kanali_es_zamanli_surer(grup):
    onceki = len(grup.gunluk.kayitlar)
    grup.rampala(np.array([10.05, 9.95, 9.95, 10.05]))
    curr_kayitlari = [k for k in grup.gunluk.kayitlar[onceki:] if k.komut.startswith("CURR")]
    # Her adimda dort ayri adrese yazilmali
    ilk_adim_adresleri = {k.adres for k in curr_kayitlari[:4]}
    assert len(ilk_adim_adresleri) == 4


def test_rampa_sonunda_oturma_dogrulanir(grup):
    olculen = grup.rampala(np.array([10.05, 9.95, 9.95, 10.05]))
    assert np.allclose(olculen, [10.05, 9.95, 9.95, 10.05], atol=0.02)


def test_oturmazsa_hata_verir(kaynak_grubu_uret, kfg):
    """Tolerans saglanamazsa islem durdurulur."""
    grup = KaynakGrubu.olustur(
        dataclasses.replace(kfg.guc_kaynaklari, akim_tolerans_A=1e-12),
        kfg.guvenlik,
        canli=False,
        gunluk=KomutGunlugu(),
        bekle=lambda s: None,
    )
    grup.baslat()
    with pytest.raises(GucKaynagiHatasi, match="oturmadi"):
        grup.rampala(np.full(4, 1.0))


def test_max_akim_asimi_reddedilir(grup, kfg):
    kotu = np.full(4, kfg.guvenlik.bobin_basi_max_akim_A + 0.1)
    with pytest.raises(GuvenlikHatasi, match="max akim"):
        grup.rampala(kotu)


def test_negatif_akim_reddedilir(grup):
    """Polarite role ile degisir; kaynaklar yalnizca pozitif akim surer."""
    with pytest.raises(GuvenlikHatasi, match="Negatif akim"):
        grup.rampala(np.array([-1.0, 10.0, 10.0, 10.0]))


def test_akim_sifir_degilken_cikis_kapatilamaz(grup):
    """Endüktif bobin: akim sifir degilken OUTP OFF yasak."""
    grup.rampala(np.full(4, 5.0))
    with pytest.raises(GuvenlikHatasi, match="OUTP OFF"):
        grup.kaynaklar[0].cikis_kapat(olculen_akim_A=5.0)


def test_guvenli_kapat_once_sifirlar_sonra_cikisi_kapatir(grup):
    grup.rampala(np.full(4, 3.0))
    grup.guvenli_kapat()
    kayitlar = komutlar(grup)
    son_curr = max(i for i, k in enumerate(kayitlar) if k.startswith("CURR"))
    ilk_outp_off = min(i for i, k in enumerate(kayitlar) if k.startswith("OUTP OFF"))
    assert son_curr < ilk_outp_off
    assert kayitlar[son_curr].startswith("CURR 0.0000")


def test_kuru_calismada_hicbir_komut_gonderilmez(grup):
    grup.rampala(np.full(4, 2.0))
    assert all(not k.gonderildi for k in grup.gunluk.kayitlar)


def test_olcumler_float_dondurur():
    sahte = SahteGucKaynagi("TEST::INSTR")
    sahte.cikis_ac()
    gerilim, akim = sahte.olcumleri_oku()
    assert isinstance(gerilim, float) and isinstance(akim, float)


def test_bozuk_yanit_yakalanir():
    with pytest.raises(GucKaynagiHatasi, match="sayiya cevrilemedi"):
        SahteGucKaynagi._float_ayristir("OVERLOAD", "MEAS:CURR?")


@pytest.mark.parametrize(
    "yanit, sorunlu",
    [('0,"No error"', False), ('-113,"Undefined header"', True), ("", False), ("bilinmeyen", False)],
)
def test_syst_err_yorumlama(yanit, sorunlu):
    assert SahteGucKaynagi._hata_yaniti_sorunlu_mu(yanit)[0] is sorunlu


def test_acil_sifirlama_hata_yutar(grup):
    grup.rampala(np.full(4, 4.0))
    grup.acil_sifirla()
    assert np.allclose(grup.ayar_akimlari_A, 0)


def test_baslatilmadan_rampa_reddedilir(kaynak_grubu_uret):
    grup = kaynak_grubu_uret()
    with pytest.raises(GucKaynagiHatasi, match="baslatilmadi"):
        grup.rampala(np.full(4, 1.0))
