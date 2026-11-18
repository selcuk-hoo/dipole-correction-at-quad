"""İş akışı testleri: adım sırası, arka plan politikası, durum dosyası, rutinler."""
from __future__ import annotations

import csv
import dataclasses
import json
import math

import numpy as np
import pytest

from merkezleme.duzeltme import yakinsama_durumu
from merkezleme.is_akisi import Bekleme, Faz, IsAkisi, IsAkisiHatasi, otomatik_yurut
from merkezleme.kayit import Calistirma
from merkezleme.olcum_kaynagi import SimulatorGirisi

from .conftest import kalibrasyonu_yurut, y_olc


# ---------------------------------------------------------------------------
# Adım sırası
# ---------------------------------------------------------------------------
def test_adim_sirasi_sifir_arka_plan_hedef_olcum(kfg, simulator_uret, akis_uret, mod_bazi):
    """Önce akımlar sıfıra iner ve arka plan istenir; sonra hedefe rampalanıp ölçüm istenir."""
    sim = simulator_uret(ofset_m=complex(150e-6, -100e-6), tohum=51)
    akis, kaynak, _ = akis_uret(sim)
    akis.basla()

    assert akis.bekleme is Bekleme.ARKA_PLAN_GIRISI
    assert np.allclose(akis.mevcut_akimlar_A, 0), "arka plan ölçümü akımlar sıfırdayken alınır"
    assert "ARKA PLAN" in akis.sonraki_eylem_metni()

    akis.olcum_gonder(kaynak.olcum_al(akis.mevcut_istek))
    assert akis.bekleme is Bekleme.OLCUM_GIRISI
    assert np.allclose(akis.mevcut_akimlar_A, mod_bazi.nominal_akimlar)
    # Ölçülen akımlar da gösterilir
    assert np.allclose(akis.olculen_akimlar_A, mod_bazi.nominal_akimlar, atol=0.02)

    akis.olcum_gonder(kaynak.olcum_al(akis.mevcut_istek))
    assert akis.son_y is not None
    assert akis.gradyen_hedefi_T_m is not None, "ilk ölçüm G_hedef'i belirlemeli"


def test_tam_akis_tamamlanir(kfg, simulator_uret, akis_uret):
    sim = simulator_uret(ofset_m=complex(260e-6, 150e-6), tohum=52)
    akis, kaynak, _ = akis_uret(sim)
    akis.basla()
    otomatik_yurut(akis, kaynak)

    assert akis.faz is Faz.TAMAMLANDI, akis.durdurma_nedeni
    assert akis.iterasyon <= 3
    # Ölçüt şartnamedeki gibi bileşen bazında: |x_c| ve |y_c| ayrı ayrı tolerans altında
    assert yakinsama_durumu(akis.son_y, kfg.duzeltme).yakinsadi, akis.son_y
    assert abs(akis.son_y.g) < kfg.duzeltme.g_toleransi
    assert akis.baslangic_y.merkez_normu_m > akis.son_y.merkez_normu_m


# ---------------------------------------------------------------------------
# Arka plan çıkarma
# ---------------------------------------------------------------------------
def test_arka_plan_cikarilmazsa_sonuc_arka_plan_kadar_kayar(
    kfg, konvansiyon, mod_bazi, simulator_uret
):
    """Arka plan çıkarılmadan merkez, arka planın getirdiği kadar kayar."""
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
    assert cikarmali.merkez_normu_m < 1e-12, "çıkarma sonrası merkez sıfırlanmalı"


def test_arka_plan_cikarma_akiste_de_calisir(kfg, konvansiyon, mod_bazi, simulator_uret, akis_uret):
    """Tam akışta, büyük bir arka planla bile doğru merkeze yakınsanmalı."""
    sim = simulator_uret(
        ofset_m=complex(120e-6, 80e-6), arka_plan_T=complex(3e-6, -2e-6), tohum=53
    )
    akis, kaynak, _ = akis_uret(sim)
    akis.basla()
    otomatik_yurut(akis, kaynak)

    assert akis.faz is Faz.TAMAMLANDI
    # Gerçek (arka plansız) merkez de toleransın altına inmeli
    gercek = sim.gercek_merkez_m(akis.mevcut_akimlar_A)
    assert abs(gercek) * 1e6 < 2 * kfg.duzeltme.merkez_toleransi_um, gercek


def test_arka_plan_her_n_noktada_politikasi(kfg, simulator_uret, akis_uret, tmp_path):
    """arka_plan_her_n_noktada = 3 ise arka plan sayısı belirgin azalmalı."""
    from merkezleme.kalibrasyon import plan_olustur

    her = dataclasses.replace(kfg.kalibrasyon, arka_plan_her_n_noktada=1)
    seyrek = dataclasses.replace(kfg.kalibrasyon, arka_plan_her_n_noktada=3)
    assert plan_olustur(seyrek).arka_plan_sayisi < plan_olustur(her).arka_plan_sayisi


def test_arka_plan_atlanirsa_son_gecerli_kullanilir_ve_kaydedilir(
    kfg, simulator_uret, akis_uret
):
    sim = simulator_uret(ofset_m=complex(90e-6, 0), tohum=54)
    akis, kaynak, calistirma = akis_uret(sim)
    # her noktada arka plan (yapilandirma.yaml'daki değerden bağımsız)
    akis.kfg = dataclasses.replace(
        kfg, kalibrasyon=dataclasses.replace(kfg.kalibrasyon, arka_plan_her_n_noktada=1))
    akis.basla()
    akis.olcum_gonder(kaynak.olcum_al(akis.mevcut_istek))  # ilk arka plan
    ilk_arka_plan = akis.son_arka_plan
    akis.olcum_gonder(kaynak.olcum_al(akis.mevcut_istek))  # ilk ölçüm

    assert akis.bekleme is Bekleme.ARKA_PLAN_GIRISI
    akis.arka_plani_atla()
    assert akis.bekleme is Bekleme.OLCUM_GIRISI
    assert akis.atlanan_arka_plan_sayisi == 1
    assert akis.son_arka_plan is ilk_arka_plan, "son geçerli arka plan kullanılmalı"
    assert any("atlandı" in n for n in akis.notlar)

    # CSV'de arka_plan_taze = 0 olarak kaydedilmis olmali
    with calistirma.olcumler_csv.open(encoding="utf-8") as f:
        satirlar = list(csv.DictReader(f))
    atlanan = [s for s in satirlar if s["not"].startswith("Arka plan adımı atlandı")]
    assert atlanan and atlanan[0]["arka_plan_taze"] == "0"


def test_ilk_arka_plan_atlanamaz(kfg, simulator_uret, akis_uret):
    sim = simulator_uret(tohum=55)
    akis, _, _ = akis_uret(sim)
    akis.basla()
    with pytest.raises(IsAkisiHatasi, match="geçerli bir arka plan"):
        akis.arka_plani_atla()


# ---------------------------------------------------------------------------
# Nokta tekrarı, duraklatma, durdurma
# ---------------------------------------------------------------------------
def test_noktayi_tekrarla_arka_plani_yeniden_ister(kfg, simulator_uret, akis_uret):
    sim = simulator_uret(tohum=56)
    akis, kaynak, _ = akis_uret(sim)
    akis.basla()
    akis.olcum_gonder(kaynak.olcum_al(akis.mevcut_istek))
    assert akis.bekleme is Bekleme.OLCUM_GIRISI
    akis.noktayi_tekrarla()
    assert akis.bekleme is Bekleme.ARKA_PLAN_GIRISI
    assert any("tekrarlandı" in n for n in akis.notlar)


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
    """Çözüm toplam asimetri sınırını aşıyorsa uygulanmaz; akış durur ve neden kaydedilir.
    (Adım başı sınırı durdurmaz, adımı küçültür: bkz. test_duzeltme.)"""
    dar_guvenlik = dataclasses.replace(kfg.guvenlik, nominale_gore_max_asimetri=0.001)
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
    # Güvenlik değerlendirmesi iş akışının kendi yapılandırmasından gelir.
    akis.kfg = dataclasses.replace(kfg, guvenlik=dar_guvenlik)

    akis.basla()
    otomatik_yurut(akis, kaynak, max_adim=200)

    assert akis.faz is Faz.DURDURULDU
    assert "Güvenlik sınırı" in (akis.durdurma_nedeni or "")
    assert "A'da kaldı" in (akis.durdurma_nedeni or "")
    assert akis.iterasyon == 0, "hiçbir düzeltme uygulanmamış olmalı"


def test_buyuk_ofset_kucuk_adimlarla_yakinsar(
    kfg, konvansiyon, mod_bazi, simulator_uret, kaynak_grubu_uret, tmp_path
):
    """1.4 mm'lik ofset tek adımda %2'yi aşar; adımlar küçültülerek yine yakınsar."""
    sim = simulator_uret(ofset_m=complex(-1400e-6, -120e-6), tohum=61)
    kaynak = SimulatorGirisi(sim)
    k = dataclasses.replace(kfg, duzeltme=dataclasses.replace(kfg.duzeltme, max_iterasyon=10))
    akis = IsAkisi(k, kaynak_grubu_uret(), kaynak, Calistirma(k, kok=tmp_path), konvansiyon, mod_bazi)
    akis.basla()
    otomatik_yurut(akis, kaynak, max_adim=400)
    assert akis.faz is Faz.TAMAMLANDI, akis.durdurma_nedeni
    assert akis.yakinsadi is True and akis.sonraki_eylem_metni() == "TAMAMLANDI"
    assert any("tam adımın" in n for n in akis.notlar)


def test_en_fazla_iterasyonda_tolerans_disi_bitis_ayrilir(
    kfg, konvansiyon, mod_bazi, simulator_uret, kaynak_grubu_uret, tmp_path
):
    """Tolerans dışında, iterasyon sınırında biten akış TAMAMLANDI fazındadır ama
    yakinsadi=False; sonraki eylem metni ve durum dosyası bunu söyler."""
    sim = simulator_uret(ofset_m=complex(-1400e-6, -120e-6), tohum=61)
    kaynak = SimulatorGirisi(sim)
    k = dataclasses.replace(kfg, duzeltme=dataclasses.replace(kfg.duzeltme, max_iterasyon=1))
    cal = Calistirma(k, kok=tmp_path)
    akis = IsAkisi(k, kaynak_grubu_uret(), kaynak, cal, konvansiyon, mod_bazi)
    akis.basla()
    otomatik_yurut(akis, kaynak, max_adim=400)
    assert akis.faz is Faz.TAMAMLANDI and akis.yakinsadi is False
    assert akis.sonraki_eylem_metni().startswith("TOLERANS DIŞINDA BİTTİ")
    akis.durumu_kaydet()
    assert cal.durum_oku()["yakinsadi"] is False


# ---------------------------------------------------------------------------
# Durum dosyası
# ---------------------------------------------------------------------------
def test_durum_dosyasindan_devam(kfg, konvansiyon, mod_bazi, simulator_uret, akis_uret,
                                 kaynak_grubu_uret):
    """Kalibrasyonun ortasında kesilen akış, durum dosyasından devam edebilmeli."""
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

    # Yarım çalıştırma bulunabilmeli
    bulunan = Calistirma.yarim_calistirma_bul(
        calistirma.dizin.parent, kfg.genel.durum_dosyasi_adi
    )
    assert bulunan == calistirma.durum_json

    # Yeni bir süreçmiş gibi devam et
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
    # Geçici dosya kalmamış olmalı
    assert not calistirma.durum_json.with_suffix(".json.tmp").exists()
    with calistirma.durum_json.open(encoding="utf-8") as f:
        json.load(f)  # geçerli JSON


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
    # Polarite ve modülatör rutinleri merkez farkını raporlar
    for ad in ("polarite", "modulator"):
        sonuc = next(r for r in akis.rutin_sonuclari if r.ad == ad)
        assert "fark_buyukluk_um" in sonuc.veriler
    # Tekrarlanabilirlik, doğrulama ölçeklerini besler
    assert akis.merkez_sacilimi_m is not None and akis.merkez_sacilimi_m > 0


def test_polarite_rutini_role_eylemi_ister(kfg, simulator_uret, akis_uret):
    """Polarite rutini, aynı genliklerle ikinci ölçümden önce röle değişimi ister."""
    sim = simulator_uret(ofset_m=complex(80e-6, 0), tohum=63)
    akis, kaynak, _ = akis_uret(sim)
    akis.basla()
    otomatik_yurut(akis, kaynak)

    akis.polarite_rutinini_kuyrukla()
    eylem_gorulen = False
    for _ in range(60):
        if akis.bekleme is Bekleme.KULLANICI_EYLEMI:
            eylem_gorulen = True
            assert "RÖLE" in akis.sonraki_eylem_metni().upper()
            assert np.allclose(akis.mevcut_akimlar_A, 0), "röle değişimi akımlar sıfırdayken"
            akis.kullanici_eylemini_onayla()
        elif akis.bekleme in (Bekleme.ARKA_PLAN_GIRISI, Bekleme.OLCUM_GIRISI):
            akis.olcum_gonder(kaynak.olcum_al(akis.mevcut_istek))
        else:
            break
    assert eylem_gorulen


# ---------------------------------------------------------------------------
# Çıktılar
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
    assert (calistirma.dizin / "yapilandirma.yaml").exists(), "yapılandırma kopyalanmalı"

    # CSV içeriği
    with calistirma.olcumler_csv.open(encoding="utf-8") as f:
        satirlar = list(csv.DictReader(f))
    assert satirlar
    for kolon in ("zaman", "adim_turu", "ayar_I1_A", "olculen_I1_A", "ham_B1", "ham_A1",
                  "arka_plan_B1", "net_B1", "x_c_um", "y_c_um", "g", "sq_over_g", "birim"):
        assert kolon in satirlar[0], kolon
    turler = {s["adim_turu"] for s in satirlar}
    assert {"arka_plan", "kalibrasyon", "duzeltme", "tekrarlanabilirlik"} <= turler

    # Markdown özeti
    metin = ozet.read_text(encoding="utf-8")
    for baslik in ("## Merkez", "## Son akımlar", "## Kalibrasyon",
                   "## Yalnızca izlenen büyüklükler", "## Arka plan", "## Tekrarlanabilirlik"):
        assert baslik in metin, baslik
    assert "R_eff" in metin and "Tekil değerler" in metin
    assert "a2/b2" in metin and "bobin sıfırına göre" in metin and "b3" in metin


def test_calistirma_klasoru_tarihli(kfg, tmp_path):
    calistirma = Calistirma(kfg, kok=tmp_path)
    assert calistirma.dizin.parent == tmp_path
    # 2026-09-17_123456 biçimi
    assert len(calistirma.etiket) == len("2026-09-17_123456")
    assert calistirma.etiket[4] == "-" and calistirma.etiket[10] == "_"


# ---------------------------------------------------------------------------
# Kayıtlı kalibrasyonu başka oturumda kullanma (yön doğrulama)
# ---------------------------------------------------------------------------
def _kalibre_et(kfg, konvansiyon, mod_bazi, simulator_uret, kaynak_grubu_uret, tmp_path):
    sim = simulator_uret(ofset_m=complex(300e-6, -200e-6), tohum=70)
    kaynak = SimulatorGirisi(sim)
    akis = IsAkisi(kfg, kaynak_grubu_uret(), kaynak, Calistirma(kfg, kok=tmp_path / "ilk"), konvansiyon, mod_bazi)
    akis.basla()
    otomatik_yurut(akis, kaynak, max_adim=400)
    assert akis.kalibrasyon is not None and akis.kalibrasyon.kuadrupol_acisi_rad is not None
    return akis.kalibrasyon


@pytest.mark.parametrize("roll", [0.0, 0.4, math.pi + 0.3])
def test_kayitli_kalibrasyon_enkoder_sifiri_kaysa_da_kullanilir(
    roll, kfg, konvansiyon, mod_bazi, simulator_uret, kaynak_grubu_uret, tmp_path
):
    """Enkoder sıfırının kayması = bütün düzenin dönmesi (simülatörde roll). Yön
    doğrulama matrisi döndürür, 180° belirsizliğini H adımıyla çözer ve düzeltme
    kalibrasyon yinelenmeden yakınsar."""
    kal = _kalibre_et(kfg, konvansiyon, mod_bazi, simulator_uret, kaynak_grubu_uret, tmp_path)
    sim = simulator_uret(ofset_m=complex(-150e-6, 250e-6), tohum=71)
    sim.roll_rad += roll
    kaynak = SimulatorGirisi(sim)
    akis = IsAkisi(kfg, kaynak_grubu_uret(), kaynak, Calistirma(kfg, kok=tmp_path / "yeni"), konvansiyon, mod_bazi)
    akis.kalibrasyonu_yukle(kal)
    akis.yon_dogrulama_gerekli = True
    akis.basla()
    assert akis.faz is Faz.YON_DOGRULAMA
    otomatik_yurut(akis, kaynak, max_adim=200)
    assert akis.faz is Faz.TAMAMLANDI and akis.yakinsadi is True, akis.notlar
    s = akis.yon_sonucu
    assert s is not None and abs(s["aci_farki_derece"]) < 3 and 0.9 < s["oran"] < 1.1
    fark = (s["dondurme_derece"] - math.degrees(roll) + 180) % 360 - 180
    assert abs(fark) < 1.0
    assert not any(n.startswith("Kalibrasyon uyarisi") for n in akis.notlar[:1])
    assert any("Yön doğrulama" in n for n in akis.notlar)


def test_kayitli_kalibrasyon_uymazsa_durur(
    kfg, konvansiyon, mod_bazi, simulator_uret, kaynak_grubu_uret, tmp_path
):
    kal = _kalibre_et(kfg, konvansiyon, mod_bazi, simulator_uret, kaynak_grubu_uret, tmp_path)
    bozuk = dataclasses.replace(kal, R=kal.R * np.array([[3.0], [3.0], [1.0]]))
    sim = simulator_uret(ofset_m=complex(-150e-6, 250e-6), tohum=72)
    kaynak = SimulatorGirisi(sim)
    akis = IsAkisi(kfg, kaynak_grubu_uret(), kaynak, Calistirma(kfg, kok=tmp_path / "yeni"), konvansiyon, mod_bazi)
    akis.kalibrasyonu_yukle(bozuk)
    akis.yon_dogrulama_gerekli = True
    akis.basla()
    otomatik_yurut(akis, kaynak, max_adim=50)
    assert akis.faz is Faz.DURDURULDU and "uymuyor" in (akis.durdurma_nedeni or "")
    assert akis.iterasyon == 0


def test_kuadrupol_acisi_kalibrasyon_dosyasinda_ve_csvden(tmp_path):
    import csv as _csv

    from merkezleme.kalibrasyon import KalibrasyonSonucu, csvden_kuadrupol_acisi, kayitli_kalibrasyonu_yukle

    psi = math.radians(31.6)
    c2 = 2.5e-3 * complex(math.cos(2 * psi), math.sin(2 * psi))
    with (tmp_path / "olcumler.csv").open("w", newline="", encoding="utf-8") as f:
        w = _csv.writer(f)
        w.writerow(["adim_turu", "epsilon", "net_B2", "net_A2"])
        w.writerow(["arka_plan", "", "1e-7", "1e-7"])
        w.writerow(["kalibrasyon", "0.000000", c2.real, c2.imag])
        w.writerow(["kalibrasyon", "0.005000", 0.0, 1.0])  # epsilon != 0: alınmaz
    assert csvden_kuadrupol_acisi(tmp_path) == pytest.approx(psi)
    kal = KalibrasyonSonucu(
        R=np.array([[0.0, 1.0, 0.0, -1.0], [1.0, 0.0, -1.0, 0.0], [0.3, 0.3, 0.3, 0.3]]) * 0.02,
        fitler={}, tekil_degerler=np.ones(3), kosul_sayisi=1.0, kosul_sayisi_olcekli=1.0, r_eff_m=0.03,
        m_sutunu_orani=None, supheli=False, supheli_nedenleri=[], gradyen_hedefi_T_m=0.1, modulator_acik=False)
    kal.kaydet(tmp_path / "kalibrasyon.json")  # açı yok (18 Kasım öncesi gibi)
    yuklu = kayitli_kalibrasyonu_yukle(tmp_path / "kalibrasyon.json")
    assert yuklu.kuadrupol_acisi_rad == pytest.approx(psi)
    # döndürme: sütunlar e^(iφ) ile döner, g satırı değişmez, açı φ kadar azalır
    d = yuklu.dondurulmus(0.5, -1.0)
    s0, s1 = yuklu.R[0] + 1j * yuklu.R[1], d.R[0] + 1j * d.R[1]
    assert np.allclose(s1, -s0 * complex(math.cos(0.5), math.sin(0.5)))
    assert np.allclose(d.R[2], yuklu.R[2]) and d.kuadrupol_acisi_rad == pytest.approx(psi - 0.5)
    yuklu.kaydet(tmp_path / "k2.json")
    assert KalibrasyonSonucu.yukle(tmp_path / "k2.json").kuadrupol_acisi_rad == pytest.approx(psi)


def test_beklenenden_sapma_onceki_olcumun_akimlarina_gore(
    kfg, konvansiyon, mod_bazi, simulator_uret, kaynak_grubu_uret, tmp_path
):
    """Öngörü, son ölçümün akımlarından bu ölçümün akımlarına olan değişimle yapılır.
    18 Kasım'a kadar değişim sıfır çıkıyordu: büyük her düzeltme adımı "beklenenden
    sapma" uyarısı veriyordu. Kusursuz modelde (simülatör) büyük adımlarda uyarı olmamalı."""
    sim = simulator_uret(ofset_m=complex(-600e-6, 400e-6), tohum=63)
    kaynak = SimulatorGirisi(sim)
    k = dataclasses.replace(kfg, duzeltme=dataclasses.replace(kfg.duzeltme, max_iterasyon=10))
    akis = IsAkisi(k, kaynak_grubu_uret(), kaynak, Calistirma(k, kok=tmp_path), konvansiyon, mod_bazi)
    akis.basla()
    sapma, duzeltme_olcumu = [], 0
    for _ in range(400):
        if akis.bitti_mi():
            break
        if akis.bekleme is Bekleme.DUZELTME_ONAYI:
            akis.duzeltmeyi_onayla()
            continue
        olcum = kaynak.olcum_al(akis.mevcut_istek)
        if akis.faz is Faz.DUZELTME and akis.bekleme is Bekleme.OLCUM_GIRISI:
            duzeltme_olcumu += 1
            sapma += [u for u in akis.olcum_dogrula(olcum).uyarilar if "BEKLENENDEN" in u]
        akis.olcum_gonder(olcum)
    assert akis.faz is Faz.TAMAMLANDI and duzeltme_olcumu >= 2
    assert not sapma, sapma
