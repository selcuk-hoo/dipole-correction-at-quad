"""Arayuz testleri (offscreen Qt).

PyQt5 kurulu degilse atlanir. Modal diyaloglar offscreen kipte bloklayacagi
icin `QMessageBox` yanitlari yamanir; boylece "olasi yazim hatasi" onayi ve
durdurma onayi da sinanabilir.
"""
from __future__ import annotations

import os

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PyQt5", reason="PyQt5 kurulu degil")

from PyQt5.QtWidgets import QApplication, QMessageBox  # noqa: E402

from merkezleme.duzeltme import yakinsama_durumu  # noqa: E402
from merkezleme.is_akisi import Bekleme, Faz  # noqa: E402
from merkezleme.olcum_kaynagi import alanlardan_olcum  # noqa: E402


@pytest.fixture
def uygulama(qt_uygulama):
    """Ortak (session kapsamli) QApplication."""
    return qt_uygulama


@pytest.fixture
def diyalog_yanitlari(monkeypatch):
    """Modal diyaloglari yakalar; `question` her zaman Yes dondurur."""
    kayit = {"question": [], "information": [], "warning": [], "critical": []}

    def yakala(ad, donus=None):
        def islev(*args, **kwargs):
            kayit[ad].append(args[2] if len(args) > 2 else "")
            return donus

        return staticmethod(islev)

    monkeypatch.setattr(QMessageBox, "question", yakala("question", QMessageBox.Yes))
    monkeypatch.setattr(QMessageBox, "information", yakala("information"))
    monkeypatch.setattr(QMessageBox, "warning", yakala("warning"))
    monkeypatch.setattr(QMessageBox, "critical", yakala("critical"))
    return kayit


@pytest.fixture
def pencere_uret(kfg, simulator_uret, akis_uret, uygulama, diyalog_yanitlari):
    from merkezleme.arayuz import MerkezlemePencere

    uretilenler = []

    def uret(ofset=complex(260e-6, 150e-6), tohum=81, deneme_kipi=True):
        sim = simulator_uret(ofset_m=ofset, arka_plan_T=complex(1.1e-6, -0.6e-6), tohum=tohum)
        akis, kaynak, calistirma = akis_uret(sim)
        pencere = MerkezlemePencere(kfg, akis, deneme_kipi=deneme_kipi)
        uretilenler.append(pencere)
        return pencere, akis, kaynak, calistirma, sim

    yield uret
    for pencere in uretilenler:
        pencere.akis.kaynaklar.acil_sifirla()


def akisi_yurut(pencere, akis, max_adim: int = 400) -> None:
    """Arayuz dugmeleriyle akisi sonuna kadar yurutur (deneme kipinde)."""
    for _ in range(max_adim):
        if akis.bitti_mi() or akis.bekleme is Bekleme.YOK:
            return
        pencere._onayla()
    raise AssertionError("akis arayuzden yurutulemedi")


def test_pencere_durum_panelini_gosterir(pencere_uret, kfg):
    pencere, akis, _, _, _ = pencere_uret()
    assert "Adım 1 /" in pencere.adim_etiketi.text()
    assert "ARKA PLAN" in pencere.eylem_etiketi.text()
    # Dort bobinin ayar/olculen/asimetri satiri
    assert len(pencere.akim_etiketleri) == 4
    for ayar, olculen, asimetri in pencere.akim_etiketleri:
        assert ayar.text() and olculen.text() and asimetri.text()
    # Akimlar sifirdayken asimetri "(sifir)" gosterilir
    assert pencere.akim_etiketleri[0][2].text() == "(sıfır)"


def test_deneme_kipinde_alanlar_otomatik_dolar(pencere_uret, kfg):
    pencere, akis, _, _, _ = pencere_uret()
    for n in kfg.harmonikler.zorunlu_harmonikler:
        birinci, ikinci = pencere.alan_kutulari[n]
        assert birinci.text().strip(), f"n={n} genlik alani bos"
        assert ikinci.text().strip(), f"n={n} faz alani bos"
    # Turetilen B_n/A_n gosterimi
    assert "B1" in pencere.turetilen_etiketleri[1].text()


def test_birim_ve_r_ref_alanlarin_yaninda_gosterilir(pencere_uret, kfg):
    pencere, _, _, _, _ = pencere_uret()
    birinci_baslik, ikinci_baslik = pencere.alan_basliklari[1]
    assert kfg.harmonikler.birim in birinci_baslik.text()
    assert kfg.harmonikler.faz_birimi in ikinci_baslik.text()
    # r_ref grup basliginda
    assert f"{kfg.harmonikler.r_ref_mm:g} mm" in pencere._giris_panelini_kur().title()


def test_bicim_degisiminde_degerler_korunur(pencere_uret, konvansiyon):
    pencere, _, _, _, _ = pencere_uret()
    onceki = pencere._alanlari_oku()
    olcum_once = alanlardan_olcum(onceki, konvansiyon, "genlik_faz")

    pencere.bicim_secici.setCurrentIndex(1)
    assert pencere.bicim == "normal_skew"
    assert "B1" in pencere.alan_basliklari[1][0].text()
    olcum_sonra = alanlardan_olcum(pencere._alanlari_oku(), konvansiyon, "normal_skew")
    for n in (1, 2):
        assert abs(olcum_once.bilesen(n) - olcum_sonra.bilesen(n)) < 1e-5 * abs(
            olcum_once.bilesen(n)
        )

    pencere.bicim_secici.setCurrentIndex(0)
    assert pencere.bicim == "genlik_faz"


def test_yorum_satiri_girisin_fiziksel_karsiligini_gosterir(pencere_uret, kfg):
    """Onaydan once giris, merkez/g olarak canli gosterilmeli."""
    pencere, akis, kaynak, _, _ = pencere_uret()
    assert "ARKA PLAN" in pencere.yorum_etiketi.text()
    pencere._onayla()  # arka plan girildi -> olcum bekleniyor
    assert akis.bekleme is Bekleme.OLCUM_GIRISI
    assert "Bu giriş şu anlama geliyor" in pencere.yorum_etiketi.text()
    assert "x_c" in pencere.yorum_etiketi.text()


def test_gecersiz_giris_uyari_verir(pencere_uret, diyalog_yanitlari):
    pencere, akis, _, _, _ = pencere_uret()
    birinci, _ = pencere.alan_kutulari[1]
    birinci.setText("abc")
    pencere._onayla()
    assert diyalog_yanitlari["warning"], "gecersiz giris uyarisi beklenirdi"
    assert "sayi degil" in diyalog_yanitlari["warning"][-1]


def test_zorunlu_alan_eksikse_yorum_bunu_soyler(pencere_uret):
    pencere, akis, kaynak, _, _ = pencere_uret()
    pencere._onayla()  # arka plan
    birinci, _ = pencere.alan_kutulari[2]
    birinci.clear()
    assert "Zorunlu alanlar bekleniyor" in pencere.yorum_etiketi.text()


def test_bozuk_giris_yazim_hatasi_onayi_ister(pencere_uret, diyalog_yanitlari, kfg):
    """Ondalik kaydirilmis bir giris, modal onay istemeli."""
    pencere, akis, kaynak, _, _ = pencere_uret()
    akisi_yurut(pencere, akis)  # kalibrasyon + duzeltme bitsin, R olsun
    assert akis.kalibrasyon is not None

    # Yeni bir olcum adimi ac (tekrarlanabilirlik rutini) ve bozuk deger gir
    pencere.tekrarlanabilirlik_dugmesi.click()
    while akis.bekleme is Bekleme.ARKA_PLAN_GIRISI:
        pencere._onayla()
    assert akis.bekleme is Bekleme.OLCUM_GIRISI

    birinci, _ = pencere.alan_kutulari[1]
    birinci.setText(str(float(birinci.text()) * 10.0))  # 10 kat buyut
    soru_sayisi = len(diyalog_yanitlari["question"])
    pencere._onayla()
    assert len(diyalog_yanitlari["question"]) > soru_sayisi
    assert "YAZIM HATASI" in diyalog_yanitlari["question"][-1]


def test_tam_akis_arayuzden_yurutulur(pencere_uret, kfg):
    pencere, akis, _, calistirma, _ = pencere_uret()
    akisi_yurut(pencere, akis)
    assert akis.faz is Faz.TAMAMLANDI, akis.durdurma_nedeni
    assert akis.iterasyon <= 3
    # Olcut sartnamedeki gibi bilesen bazinda (|x_c|, |y_c| ayri ayri)
    assert yakinsama_durumu(akis.son_y, kfg.duzeltme).yakinsadi, akis.son_y
    # Panel son sonucu gosteriyor
    assert "x_c" in pencere.sonuc_etiketi.text()
    assert "Son arka plan" in pencere.arka_plan_etiketi.text()
    assert "SQ/G" in pencere.izleme_etiketi.text()


def test_duzeltme_onerisi_panelde_gosterilir(pencere_uret, kfg):
    pencere, akis, _, _, _ = pencere_uret()
    for _ in range(400):
        if akis.bekleme is Bekleme.DUZELTME_ONAYI:
            break
        pencere._onayla()
    else:  # pragma: no cover
        raise AssertionError("duzeltme onayina gelinemedi")

    metin = pencere.oneri_metni.toPlainText()
    assert "Bobin" in metin and "nominale göre" in metin
    assert "Beklenen merkez değişimi" in metin
    assert pencere.onayla_dugmesi.text() == "Önerilen akımları UYGULA"


def test_rutin_dugmeleri_calisir(pencere_uret):
    pencere, akis, _, _, _ = pencere_uret()
    akisi_yurut(pencere, akis)
    for dugme in (
        pencere.tekrarlanabilirlik_dugmesi,
        pencere.polarite_dugmesi,
        pencere.modulator_dugmesi,
    ):
        assert dugme.isEnabled()
        dugme.click()
        akisi_yurut(pencere, akis)
    assert {r.ad for r in akis.rutin_sonuclari} == {
        "tekrarlanabilirlik",
        "polarite",
        "modulator",
    }


def test_duraklat_dugmesi_metni_degisir(pencere_uret):
    pencere, akis, _, _, _ = pencere_uret()
    pencere.duraklat_dugmesi.click()
    assert akis.bekleme is Bekleme.DURAKLATILDI
    assert pencere.duraklat_dugmesi.text() == "Devam"
    pencere.duraklat_dugmesi.click()
    assert akis.bekleme is not Bekleme.DURAKLATILDI


def test_durdur_dugmesi_akimlari_sifirlar(pencere_uret, diyalog_yanitlari):
    pencere, akis, _, _, _ = pencere_uret()
    pencere._onayla()  # arka plan -> akimlar nominalde
    assert np.any(akis.mevcut_akimlar_A > 0)
    pencere.durdur_dugmesi.click()
    assert diyalog_yanitlari["question"], "durdurma onayi sorulmali"
    assert akis.faz is Faz.DURDURULDU
    assert np.allclose(akis.mevcut_akimlar_A, 0)


def test_pencere_kapanisinda_akimlar_sifirlanir_ve_ozet_yazilir(pencere_uret):
    from PyQt5.QtGui import QCloseEvent

    pencere, akis, _, calistirma, _ = pencere_uret()
    pencere._onayla()
    pencere.closeEvent(QCloseEvent())
    assert np.allclose(akis.kaynaklar.ayar_akimlari_A, 0)
    assert not any(getattr(k, "cikis_acik", False) for k in akis.kaynaklar.kaynaklar)
    assert calistirma.ozet_md.exists()


def test_ozet_dugmesi_dosya_yazar(pencere_uret, diyalog_yanitlari, kfg):
    pencere, akis, _, calistirma, _ = pencere_uret()
    akisi_yurut(pencere, akis)
    pencere.ozet_dugmesi.click()
    assert calistirma.ozet_md.exists()
    assert diyalog_yanitlari["information"]


def test_canli_kipte_kip_etiketi_uyarici(kfg, simulator_uret, akis_uret, uygulama,
                                         diyalog_yanitlari):
    """Canli kipte kip etiketi kirmizi gosterilir (kazara canli calismayi onlemek icin)."""
    import dataclasses

    from merkezleme.arayuz import MerkezlemePencere

    canli_kfg = dataclasses.replace(kfg, genel=dataclasses.replace(kfg.genel, kip="canli"))
    sim = simulator_uret(ofset_m=complex(50e-6, 0), tohum=99)
    akis, _, _ = akis_uret(sim)
    pencere = MerkezlemePencere(canli_kfg, akis, deneme_kipi=True)
    assert "CANLI" in pencere.kip_etiketi.text()
    assert "b00020" in pencere.kip_etiketi.styleSheet()
    akis.kaynaklar.acil_sifirla()
