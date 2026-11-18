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
    # Arka plan, son beş arka plan ölçümünün ortalamasıdır (tek ölçüm gürültülü)
    from merkezleme.birlesik import ARKA_PLAN_ORTALAMA_SAYISI
    son = akis.son_arka_planlar[:ARKA_PLAN_ORTALAMA_SAYISI]
    assert len(son) == min(ARKA_PLAN_ORTALAMA_SAYISI, akis.arka_plan_sayisi) >= 2
    assert son[0] is akis.son_arka_plan
    assert sekme.arka_plan()[1] == pytest.approx(sum(o.bilesenler[1] for o in son) / len(son))
    ark = sekme.arka_plan()[1]
    ark2 = sekme.arka_plan().get(2, 0j)  # kuadrupol arka planı da çıkarılır

    izleme.baslat()
    assert izleme.calisiyor and bobin.dongu.otomatik_yaz is False
    assert izleme._akim_isi is not None and izleme._akim_isi.is_alive()  # akımlar arka planda
    import time as _t
    for _ in range(50):
        if all(np.isfinite(izleme._son_akim)):
            break
        _t.sleep(0.05)
    # Aralık içinde üç ölçüm: arka plan + 2.4 mT kuadrupol + 50 / 52 / 48 µT ek dipol
    izleme.aralik.setValue(1)
    for ek in (50e-6, 52e-6, 48e-6):
        bobin.dongu.son_sonuc = SimpleNamespace(
            harmonikler=(ark + ek + 0j, complex(2.4e-3, 0) + ark2, 0j, 0j, 0j, 0j), hiz_hz=8.0, artik_orani=0.01)
        izleme._ornekle()
    assert len(izleme.t) == 0  # aralık dolmadı
    izleme._son_kayit_t -= 2
    izleme._ornekle()
    assert len(izleme.t) == 1
    assert izleme.x[0] == pytest.approx(-0.025 * 50e-6 / 2.4e-3 * 1e6, rel=1e-6)  # ortalama, arka plan çıkarılmış
    satirlar = list(__import__("csv").reader(izleme._csv.open(encoding="utf-8")))
    assert len(satirlar) == 2 and satirlar[0][2] == "n_olcum" and satirlar[1][2] == "3"
    assert float(satirlar[1][5]) == pytest.approx(0.025 * 2e-6 / 2.4e-3 * 1e6, rel=1e-3)  # sx
    assert all(np.isfinite(float(v)) for v in satirlar[1][-4:])  # akımlar iş parçacığından
    # Akım okuma hatası günlüğe yazılır (önce sessizce NaN yazılıyordu); düzelince de
    gunluk: list[str] = []
    bobin.dongu.gunluk = gunluk.append
    with izleme._akim_kilidi:
        izleme._akim_hatasi, izleme._akim_hata_sayisi = "OSError('zaman aşımı')", 1
    izleme._akim_hatasini_bildir()
    izleme._akim_hatasini_bildir()  # aynı hata ikinci kez yazılmaz
    assert len(gunluk) == 1 and "okunamıyor" in gunluk[0] and "zaman aşımı" in gunluk[0]
    with izleme._akim_kilidi:
        izleme._akim_hatasi, izleme._akim_hata_sayisi, izleme._akim_duzeldi = None, 0, 3
    izleme._akim_hatasini_bildir()
    assert len(gunluk) == 2 and "yeniden okunuyor (3" in gunluk[1]
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


def test_basilan_dugme_yesile_doner_ve_sonucu_durum_cubuguna_yazilir(qt_uygulama, kfg_tmp, monkeypatch):
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QPlainTextEdit, QPushButton

    class SahteBobin(QMainWindow):
        def __init__(self):
            super().__init__()
            self.gunluk = QPlainTextEdit()
            self.dugme = QPushButton("ADC'yi yeniden ayarla", self)
            self.dugme.resize(200, 30)
            self.dugme.clicked.connect(lambda: self.gunluk.appendPlainText("13:37:20  ADC ayarları yeniden gönderildi."))

    sekme = MerkezlemeSekmesi(kfg_tmp, False, lambda: (False, "bağlı değil"), olcum_kaynagi_uret=_simulator)
    bobin = SahteBobin()
    pencere = BirlesikPencere(bobin, sekme)
    pencere.show()
    QTest.mouseClick(bobin.dugme, Qt.MouseButton.LeftButton, pos=QPoint(10, 10))
    QTest.qWait(50)
    assert bobin.dugme.graphicsEffect() is not None
    mesaj = pencere.statusBar().currentMessage()
    assert "ADC'yi yeniden ayarla" in mesaj and "yeniden gönderildi" in mesaj
    QTest.qWait(pencere.geri_bildirim.SURE_MS + 100)
    assert bobin.dugme.graphicsEffect() is None
    pencere.close()


def test_ortam_alani_akimsiz_izlenir(qt_uygulama, kfg_tmp, tmp_path, monkeypatch):
    """Quad akımları sıfırken dönen bobinin gördüğü dipol zamanla kaydedilir;
    merkezlenmiş akımlar açıkken reddedilir."""
    uyarilar = []
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: uyarilar.append(a[2])))
    pytest.importorskip("pyqtgraph")
    from types import SimpleNamespace

    from merkezleme.birlesik import KararlilikSekmesi

    sekme = MerkezlemeSekmesi(kfg_tmp, False, lambda: (True, "dönüyor"), olcum_kaynagi_uret=_simulator)
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

    izleme.baslat()  # akımlı izleme: merkezleme yok -> reddedilir, akımsızı önerir
    assert not izleme.calisiyor and "Ortam alanını izle" in uyarilar[-1]
    izleme.ortam_degistir()  # merkezleme hiç başlatılmadı: akımlar sıfır sayılır
    assert izleme.calisiyor and izleme.akimsiz and izleme._akim_isi is None
    assert bobin.dongu.otomatik_yaz is False and not izleme.dugme.isEnabled()
    izleme.aralik.setValue(1)
    for b in (34.0, 35.0, 36.0):
        bobin.dongu.son_sonuc = SimpleNamespace(
            harmonikler=(complex(b * 1e-6, 5.5e-6), complex(0.3e-6, 0), 0j, 0j, 0j, 0j), hiz_hz=8.0,
            artik_orani=0.2)
        izleme._ornekle()
    izleme._son_kayit_t -= 2
    izleme._ornekle()
    satirlar = list(__import__("csv").reader(izleme._csv.open(encoding="utf-8")))
    assert izleme._csv.name.startswith("ortam_") and satirlar[0][3:5] == ["B1_uT", "A1_uT"]
    assert float(satirlar[1][3]) == pytest.approx(35.0) and float(satirlar[1][4]) == pytest.approx(5.5)
    assert float(satirlar[1][5]) == pytest.approx(1.0)  # B1 saçılımı
    assert "B1" in izleme.ozet.text() and "µT" in izleme.ozet.text()
    izleme.ortam_degistir()
    assert not izleme.calisiyor and bobin.dongu.otomatik_yaz is True and izleme.dugme.isEnabled()

    sekme.baslat()  # akımlar nominalde açık -> akımsız izleme reddedilir
    izleme.ortam_degistir()
    assert not izleme.calisiyor and "Merkezleme sürüyor" in uyarilar[-1]
    sekme.kapat()


def test_izleme_bekcisi_olcum_gelmezse_uyarir(qt_uygulama, kfg_tmp, tmp_path):
    """Ölçüm OLCUM_YOK_ESIGI_S boyunca gelmezse günlüğe ve özete bir kez uyarı;
    ölçüm gelince "yeniden geliyor" (17 Kasım: motor durdu, izleme sessizce bitti)."""
    pytest.importorskip("pyqtgraph")
    from types import SimpleNamespace

    from merkezleme.birlesik import OLCUM_YOK_ESIGI_S, KararlilikSekmesi

    sekme = MerkezlemeSekmesi(kfg_tmp, False, lambda: (True, "dönüyor"), olcum_kaynagi_uret=_simulator)
    sekme.otomatik_zamanlayici.stop()
    gunluk: list[str] = []

    class SahteDongu:
        otomatik_yaz = True
        saglik: list = []
        son_sonuc = None
        hata_metni = "Beklenmeyen hata: IndexError('index -1')"
        donuyor = False
        oturum = SimpleNamespace(klasor=lambda: tmp_path)

        def otomatik_yaz_ayarla(self, acik):
            self.otomatik_yaz = acik
            return True

        def gunluk(self, m):
            gunluk.append(m)

    bobin = SimpleNamespace(dongu=SahteDongu(), p=SimpleNamespace(r_ref_m=0.025))
    izleme = KararlilikSekmesi(bobin, sekme)  # type: ignore[arg-type]
    izleme.zamanlayici.stop()
    izleme.ortam_degistir()
    izleme._ornekle()
    assert gunluk == []  # henüz süre dolmadı
    izleme._son_olcum_t -= OLCUM_YOK_ESIGI_S + 1
    izleme._ornekle()
    izleme._ornekle()  # ikinci kez yazılmaz
    assert len(gunluk) == 1 and "yeni ölçüm yok" in gunluk[0] and "IndexError" in gunluk[0]
    assert izleme.ozet.text().startswith("ÖLÇÜM GELMİYOR")
    bobin.dongu.son_sonuc = SimpleNamespace(
        harmonikler=(complex(1e-6, 0), complex(0.3e-6, 0), 0j, 0j, 0j, 0j), hiz_hz=8.0, artik_orani=0.2)
    izleme._ornekle()
    assert len(gunluk) == 2 and "yeniden geliyor" in gunluk[1]
    izleme.ortam_degistir()


def _sonuna_kadar(sekme):
    from PySide6.QtWidgets import QApplication

    sekme.otomatik_calisma.setChecked(True)
    for _ in range(800):
        if sekme.pencere.akis.bitti_mi():
            break
        sekme._otomatik_ilerle(); QApplication.processEvents()


def test_mevcut_akimlarla_yeniden_duzelt(qt_uygulama, kfg_tmp, monkeypatch):
    """Akımlar sıfırlanmadan, aynı kaynak grubu ve kalibrasyonla yeni çalıştırma."""
    import numpy as np

    from merkezleme.is_akisi import Bekleme, Faz

    hizli = dataclasses.replace(
        kfg_tmp,
        guc_kaynaklari=dataclasses.replace(kfg_tmp.guc_kaynaklari, rampa_hizi_A_s=1e4, oturma_suresi_s=0.0,
                                           oturma_kontrol_periyodu_s=0.0),
    )
    sekme = MerkezlemeSekmesi(hizli, False, lambda: (True, "dönüyor"), olcum_kaynagi_uret=_simulator)
    sekme.otomatik_zamanlayici.stop()
    sekme.baslat()
    assert not sekme.yeniden_duzeltilebilir()  # kalibrasyon sürüyor
    _sonuna_kadar(sekme)
    eski = sekme.pencere.akis
    assert eski.faz is Faz.TAMAMLANDI and sekme.yeniden_duzeltilebilir()
    akimlar = np.asarray(eski.kaynaklar.ayar_akimlari_A).copy()
    kancalar = []
    sekme.kapanis_kancalari.append(lambda: kancalar.append(1))

    sekme.yeniden_duzelt(sor=False)
    yeni = sekme.pencere.akis
    assert yeni is not eski and kancalar == [1]  # izleme durduruldu
    assert eski.faz is Faz.TAMAMLANDI  # eski akış durdurulmadı (akımlar sıfırlanmadı)
    assert yeni.kaynaklar is eski.kaynaklar and yeni.kalibrasyon is eski.kalibrasyon
    assert yeni.faz is Faz.DUZELTME and yeni.calistirma.dizin != eski.calistirma.dizin
    # ilk adım: arka plan, ardından eski akımlarla ölçüm (nominal değil)
    assert yeni.bekleme is Bekleme.ARKA_PLAN_GIRISI
    assert np.allclose(yeni.mevcut_gorev.akimlar_A, akimlar)
    assert "önceki çalıştırmadan" in (yeni.calistirma.dizin / "arayuz_ayarlari.txt").read_text(encoding="utf-8")
    _sonuna_kadar(sekme)
    assert yeni.faz is Faz.TAMAMLANDI and yeni.yakinsadi is True
    sekme.kapat()


def test_pencere_akimlar_aciksa_kapatmadan_once_sorar(qt_uygulama, kfg_tmp, monkeypatch):
    sorular = []
    yanit = [QMessageBox.StandardButton.No]
    monkeypatch.setattr(QMessageBox, "question",
                        staticmethod(lambda *a, **k: (sorular.append(a[2]), yanit[0])[1]))

    class SahteBobin(QMainWindow):
        pass

    hizli = dataclasses.replace(
        kfg_tmp,
        guc_kaynaklari=dataclasses.replace(kfg_tmp.guc_kaynaklari, rampa_hizi_A_s=1e4, oturma_suresi_s=0.0,
                                           oturma_kontrol_periyodu_s=0.0),
    )
    sekme = MerkezlemeSekmesi(hizli, False, lambda: (True, "dönüyor"), olcum_kaynagi_uret=_simulator)
    sekme.otomatik_zamanlayici.stop()
    sekme.baslat()
    _sonuna_kadar(sekme)  # akımlar merkezlenmiş değerlerde açık
    pencere = BirlesikPencere(SahteBobin(), sekme)
    pencere.show()
    pencere.close()
    assert sorular and "akımları açık" in sorular[-1] and sekme.pencere is not None  # kapanmadı
    yanit[0] = QMessageBox.StandardButton.Yes
    pencere.close()
    assert sekme.pencere is None


def test_kayitli_kalibrasyon_ve_son_akimlarla_baslar(qt_uygulama, kfg_tmp, monkeypatch):
    """Ayarlarda kayıtlı kalibrasyon seçilince kalibrasyon yinelenmez: yön doğrulama
    (iki ölçüm) ardından düzeltme; başlangıç akımları o çalıştırmanın son akımları."""
    import numpy as np

    from merkezleme.is_akisi import Faz

    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))
    hizli = dataclasses.replace(
        kfg_tmp,
        guc_kaynaklari=dataclasses.replace(kfg_tmp.guc_kaynaklari, rampa_hizi_A_s=1e4, oturma_suresi_s=0.0,
                                           oturma_kontrol_periyodu_s=0.0),
    )
    sekme = MerkezlemeSekmesi(hizli, False, lambda: (True, "dönüyor"), olcum_kaynagi_uret=_simulator)
    sekme.otomatik_zamanlayici.stop()
    assert sekme.kalibrasyon_secici.count() == 1  # henüz kayıtlı yok
    sekme.baslat()
    _sonuna_kadar(sekme)
    ilk = sekme.pencere.akis
    son_akimlar = np.asarray(ilk.mevcut_akimlar_A).copy()
    sekme.yeni_calistirma()
    assert sekme.kalibrasyon_secici.count() == 2
    sekme.kalibrasyon_secici.setCurrentIndex(1)
    assert sekme.akimdan_basla.isEnabled() and sekme.akimdan_basla.isChecked()
    assert "yön doğrulama" in sekme.kalibrasyon_bilgi.text()
    sekme.baslat()
    akis = sekme.pencere.akis
    assert akis.faz is Faz.YON_DOGRULAMA and akis.kalibrasyon is not None
    assert np.allclose(akis.mevcut_gorev.akimlar_A, son_akimlar)
    _sonuna_kadar(sekme)
    assert akis.faz is Faz.TAMAMLANDI and akis.yakinsadi is True, akis.notlar
    assert akis.yon_sonucu is not None and abs(akis.yon_sonucu["aci_farki_derece"]) < 5
    assert akis.adim_no < ilk.adim_no  # kalibrasyon yinelenmedi
    sekme.kapat()
