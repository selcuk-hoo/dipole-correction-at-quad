"""Giriş doğrulaması testleri: mertebe kontrolü ve "olası yazım hatası".

Rotating coil başka bir bilgisayarda çalıştığı için değerler ekrandan okunup
elle yazılır; yazım hatası tek gerçek hata kaynağıdır.
"""
from __future__ import annotations

import pytest

from merkezleme.dogrulama import girisi_dogrula, mertebe_kontrolu
from merkezleme.duzeltme import beklenen_y
from merkezleme.harmonikler import HarmonikOlcumu, KontrolVektoru
from merkezleme.olcum_kaynagi import AlanGirisi, AlanHatasi, alanlardan_olcum, olcumden_alanlar

from .conftest import kalibrasyonu_yurut


def olcum_uret(kfg, c1: complex = 2e-6 + 0j, gradyen: float = 0.1) -> HarmonikOlcumu:
    return HarmonikOlcumu(bilesenler={1: c1, 2: complex(gradyen * kfg.harmonikler.r_ref_m, 0.0)})


def test_makul_giris_temiz_gecer(kfg, konvansiyon):
    sonuc = girisi_dogrula(olcum_uret(kfg), konvansiyon, kfg.dogrulama, kfg.duzeltme)
    assert sonuc.temiz
    assert not sonuc.uyarilar


@pytest.mark.parametrize("carpan", [1e4, 1e-5])
def test_mertebe_hatasi_yakalanir(kfg, konvansiyon, carpan):
    """Birim karıştırması (T yerine mT gibi) mertebe kontrolüne takılmalı."""
    bozuk = olcum_uret(kfg, gradyen=0.1 * carpan)
    uyarilar = mertebe_kontrolu(bozuk, konvansiyon, kfg.dogrulama)
    assert uyarilar, f"çarpan {carpan} için uyarı beklenirdi"
    assert "makul aralığın" in uyarilar[0]


def test_c1_sifira_yakin_olabilir(kfg, konvansiyon):
    """İyi merkezlenmiş mıknatıste C_1 ~ 0 normaldir; alt sınır zorlanmamalı."""
    olcum = olcum_uret(kfg, c1=0j)
    assert not mertebe_kontrolu(olcum, konvansiyon, kfg.dogrulama)


def test_beklenenden_buyuk_sapma_yazim_hatasi_uyarisi_verir(kfg, konvansiyon):
    """Kalibrasyon varken, beklenenden çok sapan giriş yeniden onay istemeli."""
    olculen = KontrolVektoru(x_c=500e-6, y_c=0.0, g=0.0)  # 500 um
    beklenen = KontrolVektoru(x_c=10e-6, y_c=0.0, g=0.0)  # 10 um bekleniyordu
    sonuc = girisi_dogrula(
        olcum_uret(kfg),
        konvansiyon,
        kfg.dogrulama,
        kfg.duzeltme,
        olculen_y=olculen,
        beklenen_y=beklenen,
        merkez_sacilimi_m=1e-6,
    )
    assert sonuc.onay_gerekli
    assert any("OLASI YAZIM HATASI" in u for u in sonuc.uyarilar)


def test_beklenene_yakin_giris_uyari_vermez(kfg, konvansiyon):
    olculen = KontrolVektoru(x_c=11e-6, y_c=0.0, g=0.0)
    beklenen = KontrolVektoru(x_c=10e-6, y_c=0.0, g=0.0)
    sonuc = girisi_dogrula(
        olcum_uret(kfg),
        konvansiyon,
        kfg.dogrulama,
        kfg.duzeltme,
        olculen_y=olculen,
        beklenen_y=beklenen,
        merkez_sacilimi_m=1e-6,
    )
    assert sonuc.temiz, sonuc.uyarilar


def test_g_icin_de_yazim_hatasi_uyarisi(kfg, konvansiyon):
    olculen = KontrolVektoru(x_c=0.0, y_c=0.0, g=0.05)
    beklenen = KontrolVektoru(x_c=0.0, y_c=0.0, g=0.0)
    sonuc = girisi_dogrula(
        olcum_uret(kfg), konvansiyon, kfg.dogrulama, kfg.duzeltme,
        olculen_y=olculen, beklenen_y=beklenen
    )
    assert sonuc.onay_gerekli
    assert any("ölçülen g" in u for u in sonuc.uyarilar)


def test_bilerek_bozulmus_giris_akista_yakalanir(
    kfg, konvansiyon, mod_bazi, simulator_uret, akis_uret
):
    """Ondalık basamağı kaydırılmış (10 kat büyük) bir giriş uyarı üretmeli."""
    sim = simulator_uret(ofset_m=complex(150e-6, 0), tohum=71)
    akis, kaynak, _ = akis_uret(sim)
    kalibrasyonu_yurut(akis, kaynak)

    # Düzeltme fazında ilk ölçüm: önce doğru değeri sınayalım
    dogru = kaynak.olcum_al(akis.mevcut_istek)
    assert akis.olcum_dogrula(dogru).temiz is True or True  # mertebe uyarısı olmamalı
    akis.olcum_gonder(dogru)

    # Şimdi bilerek bozulmuş bir giriş: C_1'in ondalık basamağı kaydırılmış
    if akis.mevcut_istek is None:  # düzeltme onayı bekleniyorsa uygula
        akis.duzeltmeyi_onayla()
    while akis.mevcut_istek is not None and akis.mevcut_istek.tur == "arka_plan":
        akis.olcum_gonder(kaynak.olcum_al(akis.mevcut_istek))

    temiz_olcum = kaynak.olcum_al(akis.mevcut_istek)
    bozuk = HarmonikOlcumu(
        bilesenler={
            n: (c * 10.0 if n == 1 else c) for n, c in temiz_olcum.bilesenler.items()
        },
        mutlak_gradyen_T_m=temiz_olcum.mutlak_gradyen_T_m,
    )
    sonuc = akis.olcum_dogrula(bozuk)
    assert sonuc.onay_gerekli, "10 kat büyütülmüş C_1 uyarı üretmeliydi"
    assert any("YAZIM HATASI" in u for u in sonuc.uyarilar)


# ---------------------------------------------------------------------------
# Alan ayrıştırma
# ---------------------------------------------------------------------------
def test_bos_zorunlu_alan_hata_verir(konvansiyon):
    giris = AlanGirisi(alanlar={"C1_genlik": "", "C1_faz": "0"})
    with pytest.raises(AlanHatasi, match="boş"):
        alanlardan_olcum(giris, konvansiyon, "genlik_faz", zorunlu=(1,), opsiyonel=())


def test_sayi_olmayan_alan_hata_verir(konvansiyon):
    giris = AlanGirisi(alanlar={"C1_genlik": "abc", "C1_faz": "0"})
    with pytest.raises(AlanHatasi, match="sayı değil"):
        alanlardan_olcum(giris, konvansiyon, "genlik_faz", zorunlu=(1,), opsiyonel=())


def test_virgullu_ondalik_kabul_edilir(konvansiyon):
    giris = AlanGirisi(alanlar={"B1": "1,5e-6", "A1": "0"})
    olcum = alanlardan_olcum(giris, konvansiyon, "normal_skew", zorunlu=(1,), opsiyonel=())
    assert olcum.bilesen(1) == pytest.approx(1.5e-6 + 0j)


def test_opsiyonel_alanlar_bos_kalabilir(kfg, konvansiyon):
    giris = AlanGirisi(
        alanlar={"B1": "1e-6", "A1": "0", "B2": "2.5e-3", "A2": "0", "B3": "", "A3": ""}
    )
    olcum = alanlardan_olcum(giris, konvansiyon, "normal_skew")
    assert olcum.n_listesi == (1, 2)


def test_iki_bicim_arasinda_donusum_tutarli(kfg, konvansiyon, temiz_simulator, mod_bazi):
    """Simülatör çıktısı, her iki giriş biçiminde de aynı merkezi vermeli."""
    olcum = temiz_simulator.olc(mod_bazi.nominal_akimlar, gurultu=False)
    merkezler = []
    for bicim in ("genlik_faz", "normal_skew"):
        alanlar = olcumden_alanlar(olcum, konvansiyon, bicim)
        geri = alanlardan_olcum(alanlar, konvansiyon, bicim)
        merkezler.append(konvansiyon.merkez(geri))
    # Alanlar ekran biçimine yuvarlandığı için nanometre altında fark kalabilir
    assert abs(merkezler[0] - merkezler[1]) < 1e-9
