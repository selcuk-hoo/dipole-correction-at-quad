"""Is akisi testleri: adim sirasi, arka plan politikasi, durum dosyasi, rutinler."""
from __future__ import annotations

import csv
import dataclasses
import json

import numpy as np
import pytest

from merkezleme.duzeltme import yakinsama_durumu
from merkezleme.is_akisi import Bekleme, Faz, IsAkisi, IsAkisiHatasi, otomatik_yurut
from merkezleme.kayit import Calistirma
from merkezleme.olcum_kaynagi import SimulatorGirisi

from .conftest import kalibrasyonu_yurut, y_olc


# ---------------------------------------------------------------------------
# Adim sirasi
# ---------------------------------------------------------------------------
def test_adim_sirasi_sifir_arka_plan_hedef_olcum(kfg, simulator_uret, akis_uret, mod_bazi):
    """Once akimlar sifira iner ve arka plan istenir; sonra hedefe rampalanip olcum istenir."""
    sim = simulator_uret(ofset_m=complex(150e-6, -100e-6), tohum=51)
    akis, kaynak, _ = akis_uret(sim)
    akis.basla()

    assert akis.bekleme is Bekleme.ARKA_PLAN_GIRISI
    assert np.allclose(akis.mevcut_akimlar_A, 0), "arka plan olcumu akimlar sifirdayken alinir"
    assert "ARKA PLAN" in akis.sonraki_eylem_metni()

    akis.olcum_gonder(kaynak.olcum_al(akis.mevcut_istek))
    assert akis.bekleme is Bekleme.OLCUM_GIRISI
    assert np.allclose(akis.mevcut_akimlar_A, mod_bazi.nominal_akimlar)
    # Olculen akimlar da gosterilir
    assert np.allclose(akis.olculen_akimlar_A, mod_bazi.nominal_akimlar, atol=0.02)

    akis.olcum_gonder(kaynak.olcum_al(akis.mevcut_istek))
    assert akis.son_y is not None
    assert akis.gradyen_hedefi_T_m is not None, "ilk olcum G_hedef'i belirlemeli"


def test_tam_akis_tamamlanir(kfg, simulator_uret, akis_uret):
    sim = simulator_uret(ofset_m=complex(260e-6, 150e-6), tohum=52)
    akis, kaynak, _ = akis_uret(sim)
    akis.basla()
    otomatik_yurut(akis, kaynak)

    assert akis.faz is Faz.TAMAMLANDI, akis.durdurma_nedeni
    assert akis.iterasyon <= 3
    # Olcut sartnamedeki gibi bilesen bazinda: |x_c| ve |y_c| ayri ayri tolerans altinda
    assert yakinsama_durumu(akis.son_y, kfg.duzeltme).yakinsadi, akis.son_y
    assert abs(akis.son_y.g) < kfg.duzeltme.g_toleransi
    assert akis.baslangic_y.merkez_normu_m > akis.son_y.merkez_normu_m


# ---------------------------------------------------------------------------
# Arka plan cikarma
# ---------------------------------------------------------------------------
def test_arka_plan_cikarilmazsa_sonuc_arka_plan_kadar_kayar(
    kfg, konvansiyon, mod_bazi, simulator_uret
):
    """Arka plan cikarilmadan merkez, arka planin getirdigi kadar kayar."""
    arka_plan_T = 1e-6 + 0j
    sim = simulator_uret(
        ofset_m=0j, roll_rad=0.0, arka_plan_T=arka_plan_T, harmonik_gurultu_bagil=0.0
    )
    gradyen = sim.gradyen_T_m(mod_bazi.nominal_akimlar)

    cikarmasiz = y_olc(sim, konvansiyon, mod_bazi.nominal_akimlar, gradyen, arka_plan_cikar=False)
    cikarmali = y_olc(sim, konvansiyon, mod_bazi.nominal_akimlar, gradyen, arka_plan_cikar=True)

    # Beklenen kayma: |z| = |C_1^arka_plan| / G
    beklenen_kayma = abs(arka_plan_T) / gradyen
    assert cikarmasiz.merkez_normu_m == pytest.approx(beklenen_kayma, rel=1e-6)
    assert cikarmali.merkez_normu_m < 1e-12, "cikarma sonrasi merkez sifirlanmali"


def test_arka_plan_cikarma_akiste_de_calisir(kfg, konvansiyon, mod_bazi, simulator_uret, akis_uret):
    """Tam akista, buyuk bir arka planla bile dogru merkeze yakinsanmali."""
    sim = simulator_uret(
        ofset_m=complex(120e-6, 80e-6), arka_plan_T=complex(3e-6, -2e-6), tohum=53
    )
    akis, kaynak, _ = akis_uret(sim)
    akis.basla()
    otomatik_yurut(akis, kaynak)

    assert akis.faz is Faz.TAMAMLANDI
    # Gercek (arka plansiz) merkez de toleransin altina inmeli
    gercek = sim.gercek_merkez_m(akis.mevcut_akimlar_A)
    assert abs(gercek) * 1e6 < 2 * kfg.duzeltme.merkez_toleransi_um, gercek


def test_arka_plan_her_n_noktada_politikasi(kfg, simulator_uret, akis_uret, tmp_path):
    """arka_plan_her_n_noktada = 3 ise arka plan sayisi belirgin azalmali."""
    from merkezleme.kalibrasyon import plan_olustur

    seyrek = dataclasses.replace(kfg.kalibrasyon, arka_plan_her_n_noktada=3)
    assert plan_olustur(seyrek).arka_plan_sayisi < plan_olustur(kfg.kalibrasyon).arka_plan_sayisi


def test_arka_plan_atlanirsa_son_gecerli_kullanilir_ve_kaydedilir(
    kfg, simulator_uret, akis_uret
):
    sim = simulator_uret(ofset_m=complex(90e-6, 0), tohum=54)
    akis, kaynak, calistirma = akis_uret(sim)
    akis.basla()
    akis.olcum_gonder(kaynak.olcum_al(akis.mevcut_istek))  # ilk arka plan
    ilk_arka_plan = akis.son_arka_plan
    akis.olcum_gonder(kaynak.olcum_al(akis.mevcut_istek))  # ilk olcum

    assert akis.bekleme is Bekleme.ARKA_PLAN_GIRISI
    akis.arka_plani_atla()
    assert akis.bekleme is Bekleme.OLCUM_GIRISI
    assert akis.atlanan_arka_plan_sayisi == 1
    assert akis.son_arka_plan is ilk_arka_plan, "son gecerli arka plan kullanilmali"
    assert any("atlandi" in n for n in akis.notlar)

    # CSV'de arka_plan_taze = 0 olarak kaydedilmis olmali
    with calistirma.olcumler_csv.open(encoding="utf-8") as f:
        satirlar = list(csv.DictReader(f))
    atlanan = [s for s in satirlar if s["not"].startswith("Arka plan adimi atlandi")]
    assert atlanan and atlanan[0]["arka_plan_taze"] == "0"


def test_ilk_arka_plan_atlanamaz(kfg, simulator_uret, akis_uret):
    sim = simulator_uret(tohum=55)
    akis, _, _ = akis_uret(sim)
    akis.basla()
    with pytest.raises(IsAkisiHatasi, match="gecerli bir arka plan"):
        akis.arka_plani_atla()


# ---------------------------------------------------------------------------
# Nokta tekrari, duraklatma, durdurma
# ---------------------------------------------------------------------------
def test_noktayi_tekrarla_arka_plani_yeniden_ister(kfg, simulator_uret, akis_uret):
    sim = simulator_uret(tohum=56)
    akis, kaynak, _ = akis_uret(sim)
    akis.basla()
    akis.olcum_gonder(kaynak.olcum_al(akis.mevcut_istek))
    assert akis.bekleme is Bekleme.OLCUM_GIRISI
    akis.noktayi_tekrarla()
    assert akis.bekleme is Bekleme.ARKA_PLAN_GIRISI
    assert any("tekrarlandi" in n for n in akis.notlar)


def test_duraklat_devam(kfg, simulator_uret, akis_uret):
    sim = simulator_uret(tohum=57)
    akis, _, _ = akis_uret(sim)
    akis.basla()
    onceki = akis.bekleme
    akis.duraklat()
    assert akis.bekleme is Bekleme.DURAKLATILDI
    assert "DURAKLATILDI" in akis.sonraki_eylem_metni()
    akis.devam_et()
    assert akis.bekleme is onceki


def test_durdur_akimlari_sifirlar(kfg, simulator_uret, akis_uret):
    sim = simulator_uret(tohum=58)
    akis, kaynak, _ = akis_uret(sim)
    akis.basla()
    akis.olcum_gonder(kaynak.olcum_al(akis.mevcut_istek))
    assert np.any(akis.mevcut_akimlar_A > 0)
    akis.durdur("test")
    assert akis.faz is Faz.DURDURULDU
    assert np.allclose(akis.mevcut_akimlar_A, 0)
    assert np.allclose(akis.kaynaklar.ayar_akimlari_A, 0)


def test_guvenlik_ihlalinde_duzeltme_uygulanmaz(
    kfg, konvansiyon, mod_bazi, simulator_uret, kaynak_grubu_uret, tmp_path
):
    """Cozum adim basi siniri asiyorsa uygulanmaz; akis durur ve neden kaydedilir."""
    dar_guvenlik = dataclasses.replace(kfg.guvenlik, adim_basi_max_bagil_degisim=0.001)
    sim = simulator_uret(ofset_m=complex(400e-6, 0), tohum=59)
    kaynak = SimulatorGirisi(sim)
    akis = IsAkisi(
        kfg,
        kaynak_grubu_uret(guvenlik=dar_guvenlik),
        kaynak,
        Calistirma(kfg, kok=tmp_path),
        konvansiyon,
        mod_bazi,
    )
    # Guvenlik degerlendirmesi is akisinin kendi yapilandirmasindan gelir.
    akis.kfg = dataclasses.replace(kfg, guvenlik=dar_guvenlik)

    akis.basla()
    otomatik_yurut(akis, kaynak, max_adim=200)

    assert akis.faz is Faz.DURDURULDU
    assert "Guvenlik siniri" in (akis.durdurma_nedeni or "")
    assert akis.iterasyon == 0, "hicbir duzeltme uygulanmamis olmali"


# ---------------------------------------------------------------------------
# Durum dosyasi
# ---------------------------------------------------------------------------
def test_durum_dosyasindan_devam(kfg, konvansiyon, mod_bazi, simulator_uret, akis_uret,
                                 kaynak_grubu_uret):
    """Kalibrasyonun ortasinda kesilen akis, durum dosyasindan devam edebilmeli."""
    sim = simulator_uret(ofset_m=complex(200e-6, -140e-6), tohum=60)
    akis, kaynak, calistirma = akis_uret(sim)
    akis.basla()
    for _ in range(7):
        if akis.bekleme in (Bekleme.ARKA_PLAN_GIRISI, Bekleme.OLCUM_GIRISI):
            akis.olcum_gonder(kaynak.olcum_al(akis.mevcut_istek))

    durum = calistirma.durum_oku()
    assert durum is not None and durum["tamamlandi"] is False
    assert durum["faz"] == "kalibrasyon"
    kalan_kuyruk = len(durum["kuyruk"])
    assert kalan_kuyruk > 0

    # Yarim calistirma bulunabilmeli
    bulunan = Calistirma.yarim_calistirma_bul(
        calistirma.dizin.parent, kfg.genel.durum_dosyasi_adi
    )
    assert bulunan == calistirma.durum_json

    # Yeni bir surecmis gibi devam et
    akis2 = IsAkisi(kfg, kaynak_grubu_uret(), kaynak, calistirma, konvansiyon, mod_bazi)
    akis2.durumu_uygula(durum)
    akis2.devam_ettir()
    assert akis2.faz is Faz.KALIBRASYON
    assert len(akis2.kuyruk) == kalan_kuyruk
    otomatik_yurut(akis2, kaynak)
    assert akis2.faz is Faz.TAMAMLANDI
    assert yakinsama_durumu(akis2.son_y, kfg.duzeltme).yakinsadi, akis2.son_y


def test_durum_dosyasi_atomik_yazilir(kfg, simulator_uret, akis_uret):
    sim = simulator_uret(tohum=61)
    akis, kaynak, calistirma = akis_uret(sim)
    akis.basla()
    akis.durumu_kaydet()
    # Gecici dosya kalmamis olmali
    assert not calistirma.durum_json.with_suffix(".json.tmp").exists()
    with calistirma.durum_json.open(encoding="utf-8") as f:
        json.load(f)  # gecerli JSON


# ---------------------------------------------------------------------------
# Rutinler
# ---------------------------------------------------------------------------
def test_rutinler_calisir_ve_raporlanir(kfg, simulator_uret, akis_uret):
    sim = simulator_uret(ofset_m=complex(120e-6, 60e-6), roll_rad=1e-3, tohum=62)
    akis, kaynak, _ = akis_uret(sim)
    akis.basla()
    otomatik_yurut(akis, kaynak)

    akis.tekrarlanabilirlik_rutinini_kuyrukla()
    otomatik_yurut(akis, kaynak)
    akis.polarite_rutinini_kuyrukla()
    otomatik_yurut(akis, kaynak)
    akis.modulator_rutinini_kuyrukla()
    otomatik_yurut(akis, kaynak)

    adlar = {r.ad for r in akis.rutin_sonuclari}
    assert adlar == {"tekrarlanabilirlik", "polarite", "modulator"}
    for rutin in akis.rutin_sonuclari:
        assert rutin.metin.strip()
    # Polarite ve modulator rutinleri merkez farkini raporlar
    for ad in ("polarite", "modulator"):
        sonuc = next(r for r in akis.rutin_sonuclari if r.ad == ad)
        assert "fark_buyukluk_um" in sonuc.veriler
    # Tekrarlanabilirlik, dogrulama olceklerini besler
    assert akis.merkez_sacilimi_m is not None and akis.merkez_sacilimi_m > 0


def test_polarite_rutini_role_eylemi_ister(kfg, simulator_uret, akis_uret):
    """Polarite rutini, ayni genliklerle ikinci olcumden once role degisimi ister."""
    sim = simulator_uret(ofset_m=complex(80e-6, 0), tohum=63)
    akis, kaynak, _ = akis_uret(sim)
    akis.basla()
    otomatik_yurut(akis, kaynak)

    akis.polarite_rutinini_kuyrukla()
    eylem_gorulen = False
    for _ in range(60):
        if akis.bekleme is Bekleme.KULLANICI_EYLEMI:
            eylem_gorulen = True
            assert "ROLE" in akis.sonraki_eylem_metni().upper()
            assert np.allclose(akis.mevcut_akimlar_A, 0), "role degisimi akimlar sifirdayken"
            akis.kullanici_eylemini_onayla()
        elif akis.bekleme in (Bekleme.ARKA_PLAN_GIRISI, Bekleme.OLCUM_GIRISI):
            akis.olcum_gonder(kaynak.olcum_al(akis.mevcut_istek))
        else:
            break
    assert eylem_gorulen


# ---------------------------------------------------------------------------
# Ciktilar
# ---------------------------------------------------------------------------
def test_ciktilar_duz_metin_ve_eksiksiz(kfg, simulator_uret, akis_uret):
    sim = simulator_uret(ofset_m=complex(180e-6, -90e-6), tohum=64)
    akis, kaynak, calistirma = akis_uret(sim)
    akis.basla()
    otomatik_yurut(akis, kaynak)
    akis.tekrarlanabilirlik_rutinini_kuyrukla()
    otomatik_yurut(akis, kaynak)
    ozet = akis.ozeti_yaz()

    # Dosyalar
    assert calistirma.olcumler_csv.exists()
    assert calistirma.kalibrasyon_json.exists()
    assert calistirma.scpi_gunlugu.exists()
    assert calistirma.durum_json.exists()
    assert ozet.exists()
    assert (calistirma.dizin / "yapilandirma.yaml").exists(), "yapilandirma kopyalanmali"

    # CSV icerigi
    with calistirma.olcumler_csv.open(encoding="utf-8") as f:
        satirlar = list(csv.DictReader(f))
    assert satirlar
    for kolon in ("zaman", "adim_turu", "ayar_I1_A", "olculen_I1_A", "ham_B1", "ham_A1",
                  "arka_plan_B1", "net_B1", "x_c_um", "y_c_um", "g", "sq_over_g", "birim"):
        assert kolon in satirlar[0], kolon
    turler = {s["adim_turu"] for s in satirlar}
    assert {"arka_plan", "kalibrasyon", "duzeltme", "tekrarlanabilirlik"} <= turler

    # Markdown ozeti
    metin = ozet.read_text(encoding="utf-8")
    for baslik in ("## Merkez", "## Son akimlar", "## Kalibrasyon",
                   "## Yalnizca izlenen buyuklukler", "## Arka plan", "## Tekrarlanabilirlik"):
        assert baslik in metin, baslik
    assert "R_eff" in metin and "Tekil degerler" in metin
    assert "SQ/G" in metin and "b3" in metin


def test_calistirma_klasoru_tarihli(kfg, tmp_path):
    calistirma = Calistirma(kfg, kok=tmp_path)
    assert calistirma.dizin.parent == tmp_path
    # 2026-09-17_123456 bicimi
    assert len(calistirma.etiket) == len("2026-09-17_123456")
    assert calistirma.etiket[4] == "-" and calistirma.etiket[10] == "_"
