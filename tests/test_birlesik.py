"""Birleşik pencere (merkezleme/birlesik.py): ayar paneli, başlatma, yeni çalıştırma, kapanış."""
from __future__ import annotations

import dataclasses

import pytest

pytest.importorskip("PySide6", reason="PySide6 kurulu değil")

from PySide6.QtWidgets import QMainWindow, QMessageBox  # noqa: E402

from merkezleme.birlesik import BirlesikPencere, MerkezlemeSekmesi, ayarlari_uygula  # noqa: E402
from merkezleme.olcum_kaynagi import SimulatorGirisi  # noqa: E402
from merkezleme.simulator import Simulator  # noqa: E402


@pytest.fixture
def kfg_tmp(kfg, tmp_path):
    return dataclasses.replace(kfg, genel=dataclasses.replace(kfg.genel, calistirma_kok_dizini=str(tmp_path)))


def _simulator(k, konv):
    return SimulatorGirisi(Simulator(k.simulator, k.miknatis, k.harmonikler))


def test_ayarlar_uygulanir(kfg):
    k = ayarlari_uygula(kfg, 7.0, 12.5)
    assert k.miknatis.nominal_akim_A == 7.0 and k.duzeltme.merkez_toleransi_um == 12.5
    assert kfg.miknatis.nominal_akim_A != 7.0  # özgün değişmez


def test_bobin_hazir_degilse_baslatilmaz(qt_uygulama, kfg_tmp):
    sekme = MerkezlemeSekmesi(kfg_tmp, False, lambda: (False, "bağlı değil"), olcum_kaynagi_uret=_simulator)
    assert not sekme.baslat_dugmesi.isEnabled() and "HAZIR DEĞİL" in sekme.bobin_etiketi.text()
    sekme = MerkezlemeSekmesi(kfg_tmp, True, lambda: (True, "dönüyor"), olcum_kaynagi_uret=_simulator,
                              donanim_sorunu="adres yok")
    assert not sekme.baslat_dugmesi.isEnabled() and "CANLI" in sekme.kip_etiketi.text()


def test_nominal_akimla_baslar_ve_yeniden_ayara_doner(qt_uygulama, kfg_tmp, monkeypatch, tmp_path):
    cagrildi = []
    sekme = MerkezlemeSekmesi(kfg_tmp, False, lambda: (True, "dönüyor"), olcum_kaynagi_uret=_simulator,
                              merkezleme_acilinca=lambda: cagrildi.append(1))
    assert "KURU" in sekme.kip_etiketi.text() and sekme.baslat_dugmesi.isEnabled()
    sekme.nominal_kutusu.setValue(7.0)
    sekme.tolerans_kutusu.setValue(20.0)
    sekme.baslat()
    assert sekme.pencere is not None and cagrildi == [1]
    akis = sekme.pencere.akis
    assert akis.kfg.miknatis.nominal_akim_A == 7.0 and akis.kfg.duzeltme.merkez_toleransi_um == 20.0
    assert akis.kfg.genel.kip == "kuru"
    ayar = list(tmp_path.glob("*/arayuz_ayarlari.txt"))
    assert len(ayar) == 1 and "nominal_akim_A: 7.0" in ayar[0].read_text(encoding="utf-8")
    assert sekme.yigin.currentWidget() is sekme.calisma_sayfasi
    assert not sekme.baslat_dugmesi.isEnabled()  # ikinci akış açılamaz

    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.No))
    sekme.yeni_calistirma()
    assert sekme.pencere is not None  # reddedildi
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))
    sekme.yeni_calistirma()
    assert sekme.pencere is None and sekme.yigin.currentIndex() == 0
    assert akis.bitti_mi()  # durduruldu, akımlar sıfırlandı
    assert all(abs(x) < 1e-9 for x in akis.kaynaklar.ayar_akimlari_A)


def test_pencere_kapaninca_iki_sekme_de_kapanir(qt_uygulama, kfg_tmp):
    kapandi = []

    class SahteBobin(QMainWindow):
        def closeEvent(self, olay):  # noqa: N802
            kapandi.append("bobin")
            olay.accept()

    sekme = MerkezlemeSekmesi(kfg_tmp, False, lambda: (True, "dönüyor"), olcum_kaynagi_uret=_simulator)
    sekme.baslat()
    akis = sekme.pencere.akis
    pencere = BirlesikPencere(SahteBobin(), sekme)
    assert pencere.sekmeler.count() == 2 and pencere.sekmeler.tabText(1) == "Merkezleme"
    pencere.close()
    assert kapandi == ["bobin"] and sekme.pencere is None and akis.bitti_mi()


def test_otomatik_kip_onaysiz_sonuna_kadar_yurur(qt_uygulama, kfg_tmp):
    from PySide6.QtWidgets import QApplication

    from merkezleme.is_akisi import Faz

    hizli = dataclasses.replace(
        kfg_tmp,
        guc_kaynaklari=dataclasses.replace(kfg_tmp.guc_kaynaklari, rampa_hizi_A_s=1e4, oturma_suresi_s=0.0,
                                           oturma_kontrol_periyodu_s=0.0),
    )
    sekme = MerkezlemeSekmesi(hizli, False, lambda: (True, "dönüyor"), olcum_kaynagi_uret=_simulator)
    sekme.otomatik_kutusu.setChecked(True)
    sekme.otomatik_zamanlayici.stop()  # testte adımları elle sür
    sekme.baslat()
    assert sekme.otomatik_calisma.isChecked()
    akis = sekme.pencere.akis
    for _ in range(500):
        if akis.bitti_mi():
            break
        sekme._otomatik_ilerle()
        QApplication.processEvents()
    assert akis.faz is Faz.TAMAMLANDI, akis.notlar
    assert any("Yakınsadı" in n for n in akis.notlar)
    # Otomatik kapatılınca adım atılmaz
    sekme.otomatik_calisma.setChecked(False)
    assert sekme.pencere.otomatik_adim() is False  # akış bitti
    sekme.kapat()


def test_kararlilik_izleme_kaydeder_ve_arka_plani_cikarir(qt_uygulama, kfg_tmp, tmp_path, monkeypatch):
    uyarilar = []
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: uyarilar.append(a[2])))
    pytest.importorskip("pyqtgraph")
    from types import SimpleNamespace

    import numpy as np
    from PySide6.QtWidgets import QApplication

    from merkezleme.birlesik import KararlilikSekmesi
    from merkezleme.harmonikler import HarmonikOlcumu

    hizli = dataclasses.replace(
        kfg_tmp,
        guc_kaynaklari=dataclasses.replace(kfg_tmp.guc_kaynaklari, rampa_hizi_A_s=1e4, oturma_suresi_s=0.0,
                                           oturma_kontrol_periyodu_s=0.0),
    )
    sekme = MerkezlemeSekmesi(hizli, False, lambda: (True, "dönüyor"), olcum_kaynagi_uret=_simulator)
    sekme.otomatik_zamanlayici.stop()

    class SahteDongu:
        otomatik_yaz = True
        saglik: list = []
        son_sonuc = None
        oturum = SimpleNamespace(klasor=lambda: tmp_path)

        def otomatik_yaz_ayarla(self, acik):
            self.otomatik_yaz = acik
            return True

    bobin = SimpleNamespace(dongu=SahteDongu(), p=SimpleNamespace(r_ref_m=0.025))
    izleme = KararlilikSekmesi(bobin, sekme)  # type: ignore[arg-type]
    izleme.zamanlayici.stop()

    izleme.baslat()  # akış yok -> reddedilir
    assert not izleme.calisiyor and uyarilar and "TAMAMLANMALI" in uyarilar[0]
    sekme.baslat()
    akis = sekme.pencere.akis
    sekme.otomatik_kutusu.setChecked(True); sekme.otomatik_calisma.setChecked(True)
    for _ in range(500):
        if akis.bitti_mi():
            break
        sekme._otomatik_ilerle(); QApplication.processEvents()
    assert akis.faz.value == "tamamlandi" and sekme.arka_plan() is not None
    ark = sekme.arka_plan()[1]
    ark2 = sekme.arka_plan().get(2, 0j)  # kuadrupol arka planı da çıkarılır

    izleme.baslat()
    assert izleme.calisiyor and bobin.dongu.otomatik_yaz is False
    # Arka plan + 2.4 mT kuadrupol + 50 µT'lik ek dipol (ofset)
    bobin.dongu.son_sonuc = SimpleNamespace(
        harmonikler=(ark + 50e-6 + 0j, complex(2.4e-3, 0) + ark2, 0j, 0j, 0j, 0j), hiz_hz=8.0, artik_orani=0.01)
    izleme.aralik.setValue(1)
    izleme._ornekle()
    assert len(izleme.t) == 1
    assert izleme.x[0] == pytest.approx(-0.025 * 50e-6 / 2.4e-3 * 1e6, rel=1e-6)  # arka plan çıkarıldı
    satirlar = list(__import__("csv").reader(izleme._csv.open(encoding="utf-8")))
    assert len(satirlar) == 2 and satirlar[0][2] == "x_c_um"
    izleme.durdur()
    assert bobin.dongu.otomatik_yaz is True
    sekme.kapat()


def test_adim_etiketi_bitince_net(qt_uygulama, kfg_tmp):
    hizli = dataclasses.replace(
        kfg_tmp,
        guc_kaynaklari=dataclasses.replace(kfg_tmp.guc_kaynaklari, rampa_hizi_A_s=1e4, oturma_suresi_s=0.0,
                                           oturma_kontrol_periyodu_s=0.0),
    )
    from PySide6.QtWidgets import QApplication

    sekme = MerkezlemeSekmesi(hizli, False, lambda: (True, "dönüyor"), olcum_kaynagi_uret=_simulator)
    sekme.otomatik_zamanlayici.stop()
    sekme.baslat()
    e = sekme.pencere.adim_etiketi
    assert e.text().startswith("Kalibrasyon: nokta")
    sekme.otomatik_calisma.setChecked(True)
    for _ in range(500):
        if sekme.pencere.akis.bitti_mi():
            break
        sekme._otomatik_ilerle(); QApplication.processEvents()
    assert e.text().startswith("TAMAMLANDI") and "düzeltme iterasyonu" in e.text()
    sekme.kapat()
