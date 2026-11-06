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
