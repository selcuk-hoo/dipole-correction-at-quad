"""Merkezleme ölçüm köprüsü: fizik, durum makinesi (sahte cihazla) ve pencere."""
from __future__ import annotations

import dataclasses
import json
import math
from pathlib import Path

import numpy as np
import pytest

from mgf import protocol
from mgf import merkezleme_koprusu as mk
from mgf.olcum_dongusu import Durum, OlcumDongusu

SPS = 7200.0


@pytest.fixture
def p(tmp_path) -> mk.Parametreler:
    return dataclasses.replace(
        mk.parametreleri_yukle(),
        kilit_dosyasi=tmp_path / "veri_kilidi" / ".kilit",
        kayit_dizini=tmp_path / "olcumler",
    )


def bobin_gerilimi(teta, hiz_hz, c1, c2, bobin, r_ref, ust=None):
    """İleri model: V = -omega * dPhi/dtheta (merkezleme_koprusu docstring'i).
    `ust`: n >= 3 harmonikleri {n: C_n}."""
    w = 2 * math.pi * hiz_hz
    harmonikler = {1: c1, 2: c2, **(ust or {})}
    toplam = sum(
        1j * n * c * bobin.duyarlilik(n, r_ref) * np.exp(1j * n * teta)
        for n, c in harmonikler.items()
    )
    return -w * bobin.sarim_sayisi * bobin.uzunluk_m * np.real(toplam)


# ---------------------------------------------------------------------------
# Fizik
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("tip", ["teget", "radyal"])
def test_merkez_merkezleme_simulatoruyle_ayni(p, tip):
    """Gerçekçi bir alan (merkezleme simülatörü, ofsetli mıknatıs) bobinle
    ölçülünce, hesaplanan merkez simülatörün gerçek merkezine eşit olmalı."""
    from merkezleme.simulator import Simulator
    from merkezleme.yapilandirma import yapilandirma_yukle

    kfg = yapilandirma_yukle(mk.REPO_KOKU / "yapilandirma.yaml")
    sim = Simulator(kfg.simulator, kfg.miknatis, kfg.harmonikler)
    sim.ofset_m = complex(150e-6, -80e-6)
    akimlar = np.full(4, kfg.miknatis.nominal_akim_A)
    c1, c2 = sim.harmonik_ham_T(akimlar, 1), sim.harmonik_ham_T(akimlar, 2)

    bobin = dataclasses.replace(p.bobin, tip=tip)
    t = np.arange(int(2.03 * SPS)) / SPS
    teta = 2 * math.pi * 23.0 * t + 0.7
    v = bobin_gerilimi(teta, 23.0, c1, c2, bobin, p.r_ref_m) + 3e-4
    s = mk.olcum_hesapla(np.degrees(teta) % 360, v, 23.0, bobin, p.r_ref_m)

    assert s.c1 == pytest.approx(c1, rel=1e-6)
    assert s.c2 == pytest.approx(c2, rel=1e-6)
    assert s.merkez_m == pytest.approx(sim.gercek_merkez_m(akimlar), abs=1e-9)
    assert s.gradyen_T_m == pytest.approx(abs(c2) / p.r_ref_m, rel=1e-6)


def test_dipol_buyuk_arayuzun_formuluyle_ayni(p):
    """n=1: magnetic_analysis.py'deki Bx, By formülüyle birebir aynı sonuç."""
    c1 = complex(4e-4, -1.5e-4)  # By + i*Bx
    t = np.arange(int(2.0 * SPS)) / SPS
    teta = 2 * math.pi * 20.0 * t
    v = bobin_gerilimi(teta, 20.0, c1, 0j, p.bobin, p.r_ref_m)
    s = mk.olcum_hesapla(np.degrees(teta) % 360, v, 20.0, p.bobin, p.r_ref_m)

    # magnetic_analysis.py: finish_scan
    y = v - v.mean()
    a1, b1 = np.sum(y * np.cos(teta)), np.sum(y * np.sin(teta))
    phi = np.arctan2(b1, a1)
    v_amp = 2 * np.hypot(a1, b1) / len(v)
    n_a_w = p.bobin.sarim_sayisi * p.bobin.uzunluk_m * p.bobin.genislik_m * 2 * math.pi * 20.0
    bx, by = v_amp * np.sin(phi) / n_a_w, -v_amp * np.cos(phi) / n_a_w

    assert s.c1.real == pytest.approx(by, rel=1e-3)
    assert s.c1.imag == pytest.approx(bx, rel=1e-3)


def test_ust_harmonikler_ve_birimler(p):
    c1, c2 = complex(3e-6, 1e-6), complex(2.4e-3, 1e-5)
    ust = {3: complex(2e-6, -1e-6), 4: complex(-1.5e-6, 4e-7), 5: complex(6e-7, 0), 6: complex(0, -8e-7)}
    t = np.arange(int(2.0 * SPS)) / SPS
    teta = 2 * math.pi * 23.0 * t + 1.1
    v = bobin_gerilimi(teta, 23.0, c1, c2, p.bobin, p.r_ref_m, ust) + 5e-4 + 3e-4 * t
    s = mk.olcum_hesapla(np.degrees(teta) % 360, v, 23.0, p.bobin, p.r_ref_m)

    assert len(s.harmonikler) == mk.HARMONIK_SAYISI == 6
    for n, c in ust.items():
        assert s.harmonikler[n - 1] == pytest.approx(c, rel=1e-5), n
    assert s.birim(3) == pytest.approx(ust[3] / abs(c2) * 1e4, rel=1e-5)
    assert abs(s.birim(2)) == pytest.approx(1e4)
    # Uydurma eğrisi, sürüklenmesi çıkarılmış ham veriyi birebir izlemeli
    assert np.max(np.abs(s.uydurma(s.aci_derece) - s.gerilim_V)) < 1e-9


@pytest.mark.parametrize("yon", [1, -1])
def test_tam_tur_penceresi(yon):
    teta = yon * 2 * math.pi * 23.0 * np.arange(int(2.0 * SPS)) / SPS
    bas, tur = mk.tam_tur_penceresi(np.degrees(teta) % 360)
    assert tur == 45
    assert abs(teta[-1] - teta[bas]) == pytest.approx(45 * 2 * math.pi, abs=2 * math.pi * 23 / SPS)


def test_referans_ofseti_dipolu_saf_normal_yapar(p):
    c1 = 3e-4 * np.exp(1j * math.radians(37.0))
    teta = 2 * math.pi * 23.0 * np.arange(int(2.0 * SPS)) / SPS
    v = bobin_gerilimi(teta, 23.0, c1, 0j, p.bobin, p.r_ref_m)
    aci = np.degrees(teta) % 360
    s = mk.olcum_hesapla(aci, v, 23.0, p.bobin, p.r_ref_m)
    ofset = mk.referans_faz_ofseti(s, 0.0)
    s2 = mk.olcum_hesapla(aci, v, 23.0, p.bobin, p.r_ref_m, ofset)
    assert s2.c1.real > 0
    assert abs(s2.c1.imag) < 1e-9 * abs(s2.c1)


def test_parametreler_ve_tutarlilik(p, tmp_path):
    assert p.bobin.sarim_sayisi == 5 and p.bobin.eksene_uzaklik_m == pytest.approx(0.02)
    assert p.kanallar[p.varsayilan_kanal] == (0, 1)
    assert p.kazanc == 32 and p.ornekleme_sps == 7200 and p.filtre == "Sinc4"
    assert mk.tutarlilik_uyarilari(p) == []

    kfg = tmp_path / "y.yaml"
    kfg.write_text("harmonikler:\n  r_ref_mm: 30.0\n  birim: mT\n", encoding="utf-8")
    uyarilar = mk.tutarlilik_uyarilari(dataclasses.replace(p, merkezleme_yapilandirmasi=kfg))
    assert len(uyarilar) == 2


def test_parametre_hatasi_aciklayici(tmp_path):
    yol = tmp_path / "p.yaml"
    yol.write_text(
        mk.VARSAYILAN_PARAMETRE_DOSYASI.read_text(encoding="utf-8").replace("kazanc: 32", "kazanc: 3"),
        encoding="utf-8",
    )
    with pytest.raises(mk.ParametreHatasi, match="kazanc"):
        mk.parametreleri_yukle(yol)


# ---------------------------------------------------------------------------
# Sahte cihaz
# ---------------------------------------------------------------------------
class SahteDunya:
    """Motor + bobin + ADC + saat. Alan (c1, c2) testten değiştirilebilir."""

    IVME_HZ_S = 20.0

    def __init__(self, p: mk.Parametreler):
        self.p = p
        self.t = 0.0
        self.c1, self.c2 = complex(2e-6, -1e-6), complex(1.9e-3, 2e-5)
        self.ust: dict[int, complex] = {}  # n >= 3
        self.gurultu_V = 0.0
        self.rng = np.random.default_rng(3)
        self.servo = False
        self.hedef = 0.0
        self.hiz = 0.0
        self.teta = 0.0
        self.kanal = None
        self.komutlar: list[tuple[int, object]] = []
        self.aci: list[float] = []
        self.gerilim: list[float] = []
        self.kesirli = 0.0

    def ilerle(self, dt: float) -> None:
        self.kesirli += dt * SPS
        n = int(self.kesirli)
        self.kesirli -= n
        self.t += dt
        if n == 0:
            return
        hedef = self.hedef if self.servo else 0.0
        fark = hedef - self.hiz
        adimlar = np.minimum(np.arange(1, n + 1) * self.IVME_HZ_S / SPS, abs(fark))
        hizlar = self.hiz + math.copysign(1.0, fark) * adimlar
        tetalar = self.teta + np.cumsum(2 * math.pi * hizlar / SPS)
        w = 2 * math.pi * hizlar
        toplam = sum(
            1j * k * c * self.p.bobin.duyarlilik(k, self.p.r_ref_m) * np.exp(1j * k * tetalar)
            for k, c in {1: self.c1, 2: self.c2, **self.ust}.items()
        )
        v = -w * self.p.bobin.sarim_sayisi * self.p.bobin.uzunluk_m * np.real(toplam)
        if self.gurultu_V:
            v = v + self.rng.normal(0.0, self.gurultu_V, n)
        self.hiz, self.teta = float(hizlar[-1]), float(tetalar[-1])
        self.aci.extend((np.degrees(tetalar) % 360).tolist())
        self.gerilim.extend(v.tolist())


class SahteBaglanti:
    def __init__(self, dunya: SahteDunya):
        self.d = dunya
        self.connected = False
        self.host, self.port, self.auto_reconnect = "", 0, False
        self.rx_queue = None

    def connect(self) -> bool:
        self.connected = True
        return True

    def disconnect(self) -> None:
        self.connected = False

    def send_command(self, cmd, param=0):
        self.d.komutlar.append((cmd, param))
        if cmd == protocol.CMD_SET_SERVO:
            self.d.servo = bool(param)
        elif cmd == protocol.CMD_SET_MOTOR_SPEED:
            assert isinstance(param, float), "hız float gönderilmeli (firmware float bekler)"
            self.d.hedef = param
        elif cmd == protocol.CMD_SET_SCAN_CHANNELS:
            self.d.kanal = (param >> 8, param & 0xFF)


class SahteMotor:
    def __init__(self, dunya: SahteDunya):
        self.d = dunya
        self.rotor_online = True
        self.current_data_mode = 1
        self.phase_offset_deg = 0.0
        self.live_rate_sps = 2400.0
        self.current_gain = 1.0

    @property
    def motor_speed(self) -> float:
        return self.d.hiz

    @property
    def total_samples_received(self) -> int:
        return len(self.d.gerilim)

    def process_queue(self, rx_queue, log_cb=None):
        pass

    def get_latest_data(self, n):
        return np.array(self.d.aci[-n:]), np.array(self.d.gerilim[-n:])


@pytest.fixture
def kurulum(p):
    dunya = SahteDunya(p)
    gunluk: list[str] = []
    dongu = OlcumDongusu(
        p, SahteBaglanti(dunya), SahteMotor(dunya), gunluk=gunluk.append, saat=lambda: dunya.t
    )
    return dunya, dongu, gunluk


def calistir(dunya, dongu, saniye: float, her_adimda=None):
    for _ in range(int(saniye / 0.05)):
        dunya.ilerle(0.05)
        dongu.tick()
        if her_adimda:
            her_adimda()


# ---------------------------------------------------------------------------
# Durum makinesi
# ---------------------------------------------------------------------------
def test_baglaninca_adc_ayarlari_gonderilir(kurulum):
    dunya, dongu, _ = kurulum
    assert dongu.baglan()
    komutlar = dict(dunya.komutlar)
    assert komutlar[protocol.CMD_SET_GAIN] == 5  # 32x
    assert komutlar[protocol.CMD_SET_RATE] == 12  # 7200 SPS
    assert komutlar[protocol.CMD_SET_FILTER] == 3  # Sinc4
    assert komutlar[protocol.CMD_SET_PGA_BYPASS] == 0
    assert komutlar[protocol.CMD_SET_DATA_MODE] == 1  # Voltage
    assert dunya.kanal == (0, 1)
    assert dongu.durum is Durum.HAZIR


def test_hiz_ust_siniri(kurulum):
    _, dongu, _ = kurulum
    assert dongu.hiz_ayarla(30.0) == 23.0


def test_tam_dongu_yalnizca_kilit_silindikten_sonraki_veriyi_kullanir(kurulum, p):
    dunya, dongu, _ = kurulum
    dongu.baglan()
    dongu.baslat()
    calistir(dunya, dongu, 6.0)  # hızlanma + oturma
    assert dongu.durum in (Durum.VERI_TOPLANIYOR, Durum.KILIT_BEKLENIYOR)
    calistir(dunya, dongu, 3.0)
    assert p.kilit_dosyasi.exists() and dongu.olcum_sayisi == 1
    ilk = json.loads(p.kilit_dosyasi.read_text())
    assert ilk["b1"] == pytest.approx(dunya.c2.real, rel=1e-4)

    # Kilit dururken ölçüm yazılmaz
    calistir(dunya, dongu, 3.0)
    assert dongu.olcum_sayisi == 1 and dongu.durum is Durum.KILIT_BEKLENIYOR

    # merkezleme akımları değiştirir (alan değişir), sonra kilidi siler
    dunya.c1 = complex(-5e-6, 3e-6)
    p.kilit_dosyasi.unlink()
    calistir(dunya, dongu, 3.0)
    ikinci = json.loads(p.kilit_dosyasi.read_text())
    assert dongu.olcum_sayisi == 2
    assert ikinci["b0"] == pytest.approx(-5e-6, rel=1e-3)
    assert ikinci["a0"] == pytest.approx(3e-6, rel=1e-3)


def test_otomatik_yazma_kapaliyken_dosyaya_dokunulmaz(kurulum, p):
    dunya, dongu, _ = kurulum
    dongu.otomatik_yaz = False
    dongu.baglan()
    dongu.baslat()
    calistir(dunya, dongu, 10.0)
    assert dongu.durum is Durum.DONUYOR
    assert not p.kilit_dosyasi.exists()
    dongu.tek_olcum()
    calistir(dunya, dongu, 2.5)
    assert dongu.son_sonuc is not None and not p.kilit_dosyasi.exists()


def test_surekli_olcum_csv_ve_istatistik(kurulum, p):
    import csv

    dunya, dongu, _ = kurulum
    dunya.ust = {3: complex(2e-6, -1e-6)}
    dunya.gurultu_V = 2e-6
    dongu.otomatik_yaz = False
    dongu.baglan()
    dongu.baslat()
    calistir(dunya, dongu, 4.5)  # hızlanma (~1.2 s) + oturma (3 s)
    assert dongu.durum is Durum.DONUYOR
    calistir(dunya, dongu, 10.1)
    n_olcum, genlik, sigma = dongu.genlik_istatistigi()
    assert n_olcum == 5  # 2 s'lik örtüşmeyen pencereler
    assert genlik[1] == pytest.approx(1e4)  # ana alan
    assert genlik[2] == pytest.approx(abs(complex(2e-6, -1e-6)) / abs(dunya.c2) * 1e4, rel=0.05)
    assert 0 < sigma[2] < 0.1 * genlik[2]  # gürültü var ama küçük
    assert genlik[4] < 0.1 * genlik[2]  # alan yok: yalnızca gürültü tabanı
    assert not p.kilit_dosyasi.exists()

    satirlar = list(csv.reader(dongu.kayit.yol.open(encoding="utf-8")))
    assert satirlar[0][:3] == ["zaman", "tur", "kanal"] and satirlar[0][-1] == "a6_T"
    assert len(satirlar) == 1 + 5 and {s[1] for s in satirlar[1:]} == {"surekli"}
    assert dongu.kayit.yol.parent == p.kayit_dizini

    dongu.kanal_sec("Düz bobin 2 (AIN4-AIN5)")
    assert dongu.genlik_istatistigi()[0] == 0  # kanal değişince ortalama sıfırlanır


def test_csv_kapaliyken_dosya_yazilmaz(kurulum, p):
    dunya, dongu, _ = kurulum
    dongu.csv_kaydet = False
    dongu.baglan()
    dongu.baslat()
    calistir(dunya, dongu, 9.0)
    assert dongu.olcum_sayisi >= 1 and dongu.kayit.yol is None
    assert not p.kayit_dizini.exists()


def test_referans_dugmesi_faz_ofsetini_ayarlar(kurulum):
    dunya, dongu, _ = kurulum
    dunya.c1, dunya.c2 = 3e-4 * np.exp(1j * math.radians(-120.0)), 0j
    dongu.otomatik_yaz = False
    dongu.baglan()
    dongu.baslat()
    calistir(dunya, dongu, 6.0)
    dongu.tek_olcum(referans=True)
    calistir(dunya, dongu, 2.5)
    dongu.tek_olcum()
    calistir(dunya, dongu, 2.5)
    assert dongu.son_sonuc.c1.real > 0
    assert abs(dongu.son_sonuc.c1.imag) < 1e-3 * abs(dongu.son_sonuc.c1)


def test_durdur_once_hizi_sifirlar_sonra_servoyu_kapatir(kurulum):
    dunya, dongu, _ = kurulum
    dongu.baglan()
    dongu.baslat()
    calistir(dunya, dongu, 3.0)
    dongu.durdur()
    assert (protocol.CMD_SET_MOTOR_SPEED, 0.0) in dunya.komutlar
    assert dunya.servo  # hemen kapatılmaz
    calistir(dunya, dongu, 3.0)
    assert not dunya.servo and dunya.hiz == pytest.approx(0.0, abs=0.2)
    assert dongu.durum is Durum.HAZIR


def test_hata_motoru_guvenle_durdurur(kurulum):
    dunya, dongu, _ = kurulum
    dongu.baglan()
    dongu.baslat()
    dongu.engine.current_data_mode = 0  # RAW: gerilim bilinmez
    calistir(dunya, dongu, 12.0)
    assert dongu.durum is Durum.HATA and "Voltage" in dongu.hata_metni
    assert not dunya.servo and dunya.hedef == 0.0


def test_baglanti_kopunca_ve_donunce_guvenli_durum(kurulum):
    dunya, dongu, _ = kurulum
    dongu.baglan()
    dongu.baslat()
    calistir(dunya, dongu, 2.0)
    dongu.conn.connected = False
    calistir(dunya, dongu, 0.5)
    assert dongu.durum is Durum.HATA
    dongu.conn.connected = True  # otomatik yeniden bağlanma
    calistir(dunya, dongu, 0.1)
    assert dongu.durum is Durum.HAZIR
    assert dunya.hedef == 0.0 and not dunya.servo


def test_kes_motoru_durdurup_baglantiyi_kapatir(kurulum):
    dunya, dongu, _ = kurulum
    dongu.baglan()
    dongu.baslat()
    calistir(dunya, dongu, 3.0)

    def bekle(s):
        dunya.ilerle(s)

    dongu.kes(bekle=bekle)
    assert not dunya.servo and dunya.hiz == pytest.approx(0.0, abs=0.2)
    assert dongu.durum is Durum.BAGLI_DEGIL and not dongu.conn.connected


def test_makro_yolu(p):
    dunya = SahteDunya(p)
    motor = SahteMotor(dunya)
    dunya.servo, dunya.hedef = True, 23.0
    dunya.ilerle(4.0)
    motor.live_rate_sps = SPS
    s = mk.kuadrupol_olcumu_yaz(motor, p)
    assert json.loads(p.kilit_dosyasi.read_text()) == s.dosya_verisi()
    assert s.c2 == pytest.approx(dunya.c2, rel=1e-4)


# ---------------------------------------------------------------------------
# Pencere (ekransız)
# ---------------------------------------------------------------------------
def test_pencere_duman(kurulum, p, monkeypatch):
    pytest.importorskip("PySide6")
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    from mgf.merkezleme_penceresi import TEMALAR, MerkezlemePenceresi

    uygulama = QApplication.instance() or QApplication([])
    dunya, _, _ = kurulum
    dunya.ust = {3: complex(2e-6, -1e-6)}
    p = dataclasses.replace(p, durma_zaman_asimi_s=0.3)
    pencere = MerkezlemePenceresi(p, SahteBaglanti(dunya), SahteMotor(dunya))
    pencere.dongu.saat = lambda: dunya.t
    pencere.zamanlayici.stop()
    for i in range(len(TEMALAR)):
        pencere.cb_tema.setCurrentIndex(i)
    pencere._baglan_kes()
    assert pencere.btn_baslat.isEnabled()
    pencere._baslat()
    for _ in range(200):
        dunya.ilerle(0.05)
        pencere._tick()
    assert pencere.dongu.olcum_sayisi >= 1
    assert pencere.lbl_b1.text().endswith(" T")
    # Grafikler doldu (log10 değerler): n=2 ana alan 10⁴, n=3 ~ 10 birim
    ust = pencere.cubuk.opts["y1"]
    assert ust[1] == pytest.approx(4.0) and 0.5 < ust[2] < 2.0
    assert pencere.deger_yazilari[1].textItem.toPlainText() == "10000"
    x, y = pencere.ham_noktalar.getData()
    assert len(x) > 1000 and len(pencere.ham_uydurma.getData()[0]) == 721
    assert "satır" in pencere.lbl_kayit.text()
    pencere.chk_yaz.setChecked(False)
    for _ in range(100):
        dunya.ilerle(0.05)
        pencere._tick()
    assert pencere.dongu.durum is Durum.DONUYOR
    # Kapanışta gerçek saatle beklenir; sahte motor yavaşlamasa da zaman
    # aşımından sonra servo kapatılmalı.
    import time as _time

    pencere.dongu.saat = _time.monotonic
    pencere.close()
    assert not dunya.servo
    uygulama.processEvents()
