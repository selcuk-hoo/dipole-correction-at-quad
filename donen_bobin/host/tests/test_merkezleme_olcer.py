"""Merkezleme ölçüm köprüsü: fizik, durum makinesi (sahte cihazla) ve pencere."""
from __future__ import annotations

import cmath
import dataclasses
import time
import json
import math
from pathlib import Path

import numpy as np
import pytest

from mgf import protocol
from mgf import merkezleme_koprusu as mk
from mgf.olcum_dongusu import AKIS_PENCERESI_S, Durum, OlcumDongusu

SPS = 7200.0


@pytest.fixture
def p(tmp_path) -> mk.Parametreler:
    return dataclasses.replace(
        mk.parametreleri_yukle(),
        hiz_hz=23.0,  # testler bu hız için yazıldı; yapılandırmadaki çalışma hızından bağımsız
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
    s = mk.olcum_hesapla(np.degrees(teta) % 360, v, SPS, bobin, p.r_ref_m)

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
    s = mk.olcum_hesapla(np.degrees(teta) % 360, v, SPS, p.bobin, p.r_ref_m)

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
    s = mk.olcum_hesapla(np.degrees(teta) % 360, v, SPS, p.bobin, p.r_ref_m)

    assert len(s.harmonikler) == mk.HARMONIK_SAYISI == 6
    for n, c in ust.items():
        if n == 4:  # 90°'lik teğet bobin oktupole kör: ölçülemez, sıfır diye raporlanmaz
            assert cmath.isnan(s.harmonikler[n - 1])
            continue
        assert s.harmonikler[n - 1] == pytest.approx(c, rel=1e-5), n
    # Uydurma eğrisi, sürüklenmesi çıkarılmış akıyı birebir izlemeli
    assert np.max(np.abs(s.uydurma(s.aci_derece) - s.aki_Vs)) < 1e-7 * np.max(np.abs(s.aki_Vs))
    assert s.artik_orani < 1e-6


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
    s = mk.olcum_hesapla(aci, v, SPS, p.bobin, p.r_ref_m)
    ofset = mk.referans_faz_ofseti(s, 0.0)
    s2 = mk.olcum_hesapla(aci, v, SPS, p.bobin, p.r_ref_m, ofset)
    assert s2.c1.real > 0
    assert abs(s2.c1.imag) < 1e-9 * abs(s2.c1)


def test_parametreler_ve_tutarlilik(p, tmp_path):
    assert p.bobin.sarim_sayisi == 5 and p.bobin.eksene_uzaklik_m == pytest.approx(0.01414)
    # iletkenler 20 mm yarıçapta, ±45°'de (90°'lik yay)
    assert [abs(z) for z in p.bobin.iletken_konumlari()] == pytest.approx([0.02, 0.02], rel=1e-3)
    assert p.kanallar[p.varsayilan_kanal] == (2, 3)
    assert p.kazanc == 32 and p.ornekleme_sps == 7200 and p.filtre == "Sinc4"
    assert p.gecikme_s == 0.0 and p.artik_esigi == pytest.approx(2e-2) and p.sicrama_esigi == 0.6
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
        self.ofset_V = 0.0  # ADC/giriş ofseti: hızdan bağımsız sabit gerilim
        self.gecikme_s = 0.0  # gerilim örneği açıya göre bu kadar eski
        self.kayip = 0  # get_latest_data'da silinen örnek sayısı
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
        v = v + self.ofset_V
        self.hiz, self.teta = float(hizlar[-1]), float(tetalar[-1])
        self.aci.extend((np.degrees(tetalar + w * self.gecikme_s) % 360).tolist())
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
        aci, v = np.array(self.d.aci[-n:]), np.array(self.d.gerilim[-n:])
        if self.d.kayip:
            sil = np.linspace(len(v) // 4, 3 * len(v) // 4, self.d.kayip).astype(int)
            aci, v = np.delete(aci, sil), np.delete(v, sil)
        return aci, v


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
    assert dunya.kanal == (2, 3)
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
    n_olcum, ortalama, sigma = dongu.harmonik_istatistigi()  # Tesla
    assert n_olcum == 5  # 2 s'lik örtüşmeyen pencereler
    assert ortalama[1] == pytest.approx(dunya.c2, rel=1e-4)
    assert ortalama[2] == pytest.approx(complex(2e-6, -1e-6), rel=0.05)
    assert 0 < sigma[2].real < 0.1 * abs(ortalama[2])  # gürültü var ama küçük
    assert 0 < sigma[2].imag < 0.1 * abs(ortalama[2])
    assert abs(ortalama[4]) < 0.1 * abs(ortalama[2])  # alan yok: yalnızca gürültü tabanı
    assert not p.kilit_dosyasi.exists()

    satirlar = list(csv.reader(dongu.kayit.yol.open(encoding="utf-8")))
    assert satirlar[0][:3] == ["zaman", "tur", "kanal"] and satirlar[0][-1] == "a6_T"
    for sutun in ("gecikme_ms", "cift_yon", "artik_orani", "saat_sicramasi", "aci_yontemi"):
        assert sutun in satirlar[0]
    assert len(satirlar) == 1 + 5 and {s[1] for s in satirlar[1:]} == {"surekli"}
    assert dongu.kayit.yol.name == "olcumler.csv" and dongu.kayit.yol.parent.parent == p.kayit_dizini

    dongu.kanal_sec("Düz bobin B (AIN6-AIN7)")
    assert dongu.harmonik_istatistigi()[0] == 0  # kanal değişince ortalama sıfırlanır


def test_uzun_olcum_suresi_gurultuyu_azaltir(kurulum):
    """Rastgele gürültü 1/√süre ile azalmalı: 8 s, 2 s'ye göre ~2 kat az saçılım."""
    dunya, dongu, _ = kurulum
    dunya.ust = {3: complex(2e-6, -1e-6)}
    dunya.gurultu_V = 2e-5
    dongu.otomatik_yaz = False
    dongu.csv_kaydet = False
    dongu.baglan()
    dongu.baslat()
    calistir(dunya, dongu, 4.5)

    def sacilim(sure: float, adet: int) -> float:
        dongu.pencere_ayarla(sure)
        assert dongu.harmonik_istatistigi()[0] == 0  # süre değişince ortalama sıfırlanır
        calistir(dunya, dongu, sure * adet + 0.2)
        n, _, sigma = dongu.harmonik_istatistigi()
        assert n == adet
        return abs(sigma[2])

    kisa, uzun = sacilim(2.0, 12), sacilim(8.0, 12)
    assert 1.4 < kisa / uzun < 2.8  # beklenen 2


def test_olcum_suresi_sinirlari(kurulum):
    _, dongu, _ = kurulum
    assert dongu.pencere_ayarla(0.01) == 0.5
    assert dongu.pencere_ayarla(1e6) == pytest.approx(dongu.max_pencere_s)
    assert dongu.max_pencere_s == pytest.approx(0.9 * 1_000_000 / SPS)  # DataEngine arabelleği
    assert dongu.gereken_ornek == math.ceil(dongu.max_pencere_s * SPS)


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


def test_faz_ofseti_her_bobin_icin_ayri(kurulum):
    """Dik iki bobin dönen çerçevede 90° farklı durur; birinin referansı
    öbürüne uygulanırsa merkez 90° dönük raporlanır."""
    dunya, dongu, gunluk = kurulum
    dunya.c1, dunya.c2 = 3e-4 * np.exp(1j * math.radians(-120.0)), 0j
    dongu.otomatik_yaz = False
    dongu.baglan()
    dongu.baslat()
    calistir(dunya, dongu, 5.0)
    assert not dongu.referans_alindi
    dongu.tek_olcum(referans=True)
    calistir(dunya, dongu, 2.5)
    birinci = dongu.faz_ofseti_derece
    assert dongu.referans_alindi and birinci != 0.0
    dongu.kanal_sec("Düz bobin B (AIN6-AIN7)")
    assert dongu.faz_ofseti_derece == 0.0 and not dongu.referans_alindi
    assert "referans alınmadı" in gunluk[-1]
    dongu.faz_ofseti_derece = 33.0
    dongu.kanal_sec("Düz bobin A (AIN2-AIN3)")
    assert dongu.faz_ofseti_derece == birinci and dongu.referans_alindi
    dongu.kanal_sec("Düz bobin B (AIN6-AIN7)")
    assert dongu.faz_ofseti_derece == 33.0


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
    assert dunya.hiz == pytest.approx(23.0, abs=0.5)  # firmware motoru durdurmaz
    dongu.conn.connected = True  # otomatik yeniden bağlanma
    calistir(dunya, dongu, 0.1)
    # Hız sıfırlanır ama servo, motor durana kadar açık kalır (normal durdurma gibi)
    assert dunya.hedef == 0.0 and dunya.servo
    assert dongu.durum is Durum.DURDURULUYOR
    calistir(dunya, dongu, 0.6)
    assert dunya.servo and dunya.hiz > 5.0
    calistir(dunya, dongu, 2.0)
    assert not dunya.servo and dunya.hiz == pytest.approx(0.0, abs=0.2)
    assert dongu.durum is Durum.HATA  # kopma hatası kullanıcıya gösterilmeye devam eder


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

    # Artığı yüksek ölçüm yazılmaz (sahte açıda merdiven yok, saat sıçraması
    # ölçülemez; red akışı için eşik sıkılaştırılır)
    p = dataclasses.replace(p, artik_esigi=5e-3, artik_tabani_Vs=0.0)  # yalnızca bağıl eşik
    p.kilit_dosyasi.unlink()
    dunya.kayip = 3
    with pytest.raises(RuntimeError, match="yazılmadı"):
        mk.kuadrupol_olcumu_yaz(motor, p)
    assert not p.kilit_dosyasi.exists()


# ---------------------------------------------------------------------------
# Gecikme (iki yön), çerçeve kilidi, artık eşiği
# ---------------------------------------------------------------------------
def test_gecikme_olcumu_motoru_cevirip_gecikmeyi_bulur(kurulum):
    dunya, dongu, gunluk = kurulum
    dunya.gecikme_s = 3e-4
    dongu.otomatik_yaz = False
    dongu.baglan()
    dongu.baslat()
    calistir(dunya, dongu, 5.0)
    dongu.gecikme_olc()
    assert dongu.gecikme_olculuyor
    calistir(dunya, dongu, 2.2)
    assert dongu._yarim is not None and dunya.hedef == -23.0  # ilk yön alındı, ters çevrildi
    calistir(dunya, dongu, 10.0)
    assert not dongu.gecikme_olculuyor and dongu.yon == -1
    assert dongu.gecikme_s == pytest.approx(3e-4, abs=2e-6)
    assert "ölçüldü" in dongu.gecikme_kaynagi
    assert any("gecikme_ms" in m for m in gunluk)  # kalıcı yapma talimatı
    # Ters yönde de ölçüm doğru
    dongu.tek_olcum()
    calistir(dunya, dongu, 2.5)
    assert dongu.son_sonuc.hiz_hz < 0
    assert dongu.son_sonuc.c2 == pytest.approx(dunya.c2, rel=1e-4)


def test_gecikme_olcumu_referans_ofsetini_tasir(kurulum):
    """Referans gecikme bilinmeden (0) alınmış olsun. Gecikme ölçülünce faz
    ofseti taşınmalı: ters yönde de referans dipol saf normal görünmeli.
    Taşınmasaydı 23 Hz ve 0.3 ms'de 2 x 2.5° hata olurdu."""
    dunya, dongu, _ = kurulum
    dunya.gecikme_s = 3e-4
    dunya.c1, dunya.c2 = 3e-4 * np.exp(1j * math.radians(-120.0)), 0j
    dongu.otomatik_yaz = False
    dongu.baglan()
    dongu.baslat()
    calistir(dunya, dongu, 5.0)
    dongu.tek_olcum(referans=True)
    calistir(dunya, dongu, 2.5)
    dongu.gecikme_olc()
    calistir(dunya, dongu, 14.0)
    assert dongu.yon == -1 and dongu.gecikme_s == pytest.approx(3e-4, abs=2e-6)
    dongu.tek_olcum()
    calistir(dunya, dongu, 2.5)
    c1 = dongu.son_sonuc.c1
    assert c1.real > 0 and abs(c1.imag) < 2e-4 * abs(c1)


@pytest.mark.parametrize("zayif", [False, True])
def test_gecikme_sinyal_yoksa_ya_da_zayifsa_reddedilir(kurulum, zayif):
    """Mıknatıs yokken (yalnızca gürültü) ya da sinyal çok zayıfken ölçülen
    faz anlamsızdır; gecikme uygulanmamalı. Zayıf sinyalde artık eşiği
    gevşetilse bile faz belirsizliği sınırı reddetmeli."""
    dunya, dongu, gunluk = kurulum
    dunya.gecikme_s = 3e-4
    dunya.gurultu_V = 1e-6
    dunya.c1, dunya.c2 = (0j, 1e-6 + 0j) if zayif else (0j, 0j)
    if zayif:
        dongu.p = dataclasses.replace(dongu.p, artik_esigi=0.99, sicrama_esigi=100.0)
    dongu.otomatik_yaz = False
    dongu.baglan()
    dongu.baslat()
    calistir(dunya, dongu, 5.0)
    dongu.gecikme_olc()
    calistir(dunya, dongu, 14.0)
    assert not dongu.gecikme_olculuyor and dongu.yon == -1
    assert dongu.gecikme_s == 0.0 and dongu.gecikme_kaynagi == "parametre dosyası"
    assert any(m.startswith("Gecikme ölçümü kullanılmadı") for m in gunluk)
    if zayif:
        assert any("belirsizlik" in m for m in gunluk)


def test_referans_miknatis_yoksa_faz_ofseti_degismez(kurulum):
    dunya, dongu, gunluk = kurulum
    dunya.c1, dunya.c2 = 0j, 0j
    dunya.gurultu_V = 1e-6
    dongu.otomatik_yaz = False
    dongu.baglan()
    dongu.baslat()
    calistir(dunya, dongu, 5.0)
    dongu.faz_ofseti_derece = 12.5
    dongu.tek_olcum(referans=True)
    calistir(dunya, dongu, 2.5)
    assert dongu.faz_ofseti_derece == 12.5
    assert any(m.startswith("Referans kullanılmadı") for m in gunluk)


def test_gecikme_olcumu_kanal_degisince_iptal(kurulum):
    dunya, dongu, _ = kurulum
    dongu.otomatik_yaz = False
    dongu.baglan()
    dongu.baslat()
    calistir(dunya, dongu, 5.0)
    dongu.gecikme_olc()
    calistir(dunya, dongu, 2.2)
    dongu.kanal_sec("Düz bobin B (AIN6-AIN7)")
    assert not dongu.gecikme_olculuyor and dongu._yarim is None


def test_merkezlemeye_yazarken_cerceve_kilitli(kurulum):
    dunya, dongu, gunluk = kurulum
    dongu.baglan()
    dongu.baslat()
    calistir(dunya, dongu, 6.0)
    assert dongu.cerceve_kilitli
    assert not dongu.kanal_sec("Düz bobin B (AIN6-AIN7)")
    assert dongu.kanal == "Düz bobin A (AIN2-AIN3)" and dunya.kanal == (2, 3)
    assert dongu.hiz_ayarla(10.0) == 23.0 and dunya.hedef == 23.0
    dongu.tek_olcum(referans=True)
    dongu.gecikme_olc()
    assert dongu._tek_istek is None
    assert sum("yapılamaz" in m for m in gunluk) == 4
    # Yazma kapatılınca değiştirilebilir; geri açılınca çerçeve farkı uyarılır
    calistir(dunya, dongu, 3.0)
    assert dongu.olcum_sayisi >= 1
    dongu.otomatik_yaz_ayarla(False)
    assert dongu.kanal_sec("Düz bobin B (AIN6-AIN7)") and dunya.kanal == (6, 7)
    dongu.otomatik_yaz_ayarla(True)
    assert "UYARI: ölçüm çerçevesi" in gunluk[-1]


def test_artigi_yuksek_olcum_merkezlemeye_yazilmaz(kurulum, p):
    dunya, dongu, gunluk = kurulum
    dunya.kayip = 30  # örnek kaybı: akı integrali bozulur
    # sahte açıda saat sıçraması yok; mutlak taban kapalı: yalnızca bağıl eşik sınanır
    dongu.p = dataclasses.replace(dongu.p, artik_esigi=5e-3, artik_tabani_Vs=0.0)
    dongu.baglan()
    dongu.baslat()
    calistir(dunya, dongu, 6.0 + 2.1 * 3)
    assert not p.kilit_dosyasi.exists() and dongu.olcum_sayisi == 0
    assert sum(m.startswith("Ölçüm reddedildi") for m in gunluk) == 3
    assert dongu.durum in (Durum.DURDURULUYOR, Durum.HATA) and "artığı" in dongu.hata_metni
    assert dongu.saglik and "artığı" in dongu.saglik[0]


def test_rs485_hata_sayaci_bildirilir(kurulum):
    dunya, dongu, gunluk = kurulum
    dongu.otomatik_yaz = False
    dongu.baglan()
    dongu.engine.rs485_error_count = 7
    calistir(dunya, dongu, 0.2)
    assert not any("RS485" in m for m in gunluk)  # ilk değer yalnızca kaydedilir
    dongu.engine.rs485_error_count = 9
    calistir(dunya, dongu, 0.1)
    assert any("2 bozuk ADC örneği" in m for m in gunluk)


# ---------------------------------------------------------------------------
# Pencere (ekransız)
# ---------------------------------------------------------------------------
def test_ham_gerilim_motor_dururken_ofseti_gosterir(kurulum):
    dunya, dongu, _ = kurulum
    assert dongu.ham_gerilim(1.0) is None  # bağlı değil
    dongu.baglan()
    dunya.ofset_V, dunya.gurultu_V = 4.88e-3, 2e-6
    komut_sayisi = len(dunya.komutlar)
    assert dongu.ornek_akisi_sps() is None  # henüz süre geçmedi
    calistir(dunya, dongu, 1.5)
    assert dongu.durum is Durum.HAZIR and dunya.hiz == 0.0
    v, o = dongu.ham_gerilim(1.0)
    assert len(v) == o.ornek_sayisi == int(SPS) and o.sure_s == pytest.approx(1.0)
    assert o.ortalama_V == pytest.approx(4.88e-3, abs=1e-7)
    assert o.std_V == pytest.approx(2e-6, rel=0.1)
    assert o.en_kucuk_V < o.ortalama_V < o.en_buyuk_V == pytest.approx(o.tepe_V)
    assert dongu.ornek_akisi_sps() == pytest.approx(SPS, rel=0.05)
    assert len(dunya.komutlar) == komut_sayisi  # okuma cihaza komut göndermez
    # Akış durursa örnek/s sıfıra iner (tampondaki eski veri yine döner)
    for _ in range(int(AKIS_PENCERESI_S / 0.05) + 2):
        dunya.t += 0.05
        dongu.ornek_akisi_sps()
    assert dongu.ornek_akisi_sps() == 0.0
    assert dongu.ham_gerilim(1.0) is not None


def test_ham_veri_kaydedilir(kurulum, p):
    dunya, dongu, gunluk = kurulum
    assert dongu.ham_kaydet(1.0) is None  # bağlı değil
    dongu.baglan()
    dunya.ofset_V = 4.88e-3
    dongu.baslat()
    calistir(dunya, dongu, 3.0)
    yol = dongu.ham_kaydet(0.5)
    assert yol is not None and yol.parent.parent == p.kayit_dizini and yol.name.startswith("ham_")
    assert yol.stem.endswith("_elle")
    basliklar = [s for s in yol.read_text(encoding="utf-8").splitlines() if s.startswith("#")]
    assert any("kanal: " + dongu.kanal in s for s in basliklar)
    assert any(s.startswith("# ozet:") and "ortalama_V=" in s for s in basliklar)
    veri = np.loadtxt(yol, delimiter=",", comments="#", skiprows=len(basliklar) + 1)
    assert veri.shape == (int(0.5 * SPS), 3)
    assert veri[-1, 0] == 0.0 and veri[0, 0] == pytest.approx(-0.5, abs=1e-3)
    np.testing.assert_allclose(veri[:, 2], np.array(dunya.gerilim[-len(veri):]), rtol=1e-8, atol=1e-15)
    np.testing.assert_allclose(veri[:, 1], np.array(dunya.aci[-len(veri):]), atol=1e-5)
    assert "Ham veri kaydedildi" in gunluk[-1]


def test_pencere_duman(kurulum, p, monkeypatch):
    pytest.importorskip("PySide6")
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import Qt
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
    # Grafikler doldu (log10 değerler)
    from mgf.merkezleme_penceresi import GOSTERIMLER, OLCEKLER

    assert pencere.cb_olcek.count() == len(OLCEKLER) == 3
    assert pencere.olcek == "gercek" and pencere.gosterim == "bilesen"
    b, a = pencere.seriler["b"], pencere.seriler["a"]
    # Normal ve skew ayrı çubuklar; yükseklik |değer|
    assert b["cubuk"].opts["y1"][1] == pytest.approx(np.log10(dunya.c2.real), abs=1e-3)
    assert a["cubuk"].opts["y1"][1] == pytest.approx(np.log10(dunya.c2.imag), abs=0.01)
    assert b["cubuk"].opts["y1"][2] == pytest.approx(np.log10(2e-6), abs=0.05)
    # a1 = -1e-6 negatif: içi boş çubuk, işaretli etiket
    assert a["cubuk"].opts["brushes"][0].style() == Qt.NoBrush
    assert b["cubuk"].opts["brushes"][0].style() != Qt.NoBrush
    assert a["yazilar"][0].textItem.toPlainText().startswith("-1.0e-06")
    assert b["yazilar"][0].textItem.toPlainText().startswith("+2.0e-06")

    # Genlik gösterimi ve üç ölçek
    pencere.cb_gosterim.setCurrentIndex(list(GOSTERIMLER).index("genlik"))
    g = pencere.seriler["genlik"]
    assert not b["cubuk"].isVisible() and not a["hata"].isVisible()  # normal/skew gizli
    assert g["cubuk"].isVisible()
    assert g["cubuk"].opts["y1"][1] == pytest.approx(np.log10(abs(dunya.c2)), abs=1e-3)
    pencere.cb_olcek.setCurrentIndex(list(OLCEKLER).index("n2"))
    assert g["cubuk"].opts["y1"][1] == pytest.approx(0.0, abs=1e-9)
    assert g["yazilar"][1].textItem.toPlainText() == "1"
    assert pencere.grafik_cok.getAxis("left").labelText == "|C_n| / |C₂|"
    pencere.cb_olcek.setCurrentIndex(list(OLCEKLER).index("n1"))
    assert g["cubuk"].opts["y1"][0] == pytest.approx(0.0, abs=1e-9)
    assert g["cubuk"].opts["y1"][1] == pytest.approx(
        np.log10(abs(dunya.c2) / abs(dunya.c1)), abs=0.01
    )
    assert pencere.sekmeler.tabText(1) == "Bobin akısı"
    assert "ms" in pencere.lbl_gecikme.text() and "/" in pencere.lbl_artik.text()
    assert "eşik" in pencere.lbl_artik.toolTip()
    # Merkezleme'ye yazarken çerçeve denetimleri kilitli
    assert not pencere.cb_kanal.isEnabled() and not pencere.btn_ref.isEnabled()
    assert not pencere.btn_gecikme.isEnabled()
    # Yardım: parametrelerden doldurulmuş metin, kipsiz pencere
    pencere.btn_yardim.click()
    yardim = pencere.yardim_penceresi.metin.toPlainText()
    assert pencere.yardim_penceresi.isVisible()
    assert f"En fazla {p.max_hiz_hz:g} Hz" in yardim and "merkezleme_olcer.yaml" in yardim
    pencere.yardim_penceresi.close()
    x, y = pencere.ham_noktalar.getData()
    assert len(x) > 1000 and len(pencere.ham_uydurma.getData()[0]) == 721
    assert "ölçüm)" in pencere.lbl_kayit.text()
    pencere.chk_yaz.setChecked(False)
    for _ in range(100):
        dunya.ilerle(0.05)
        pencere._tick()
    assert pencere.dongu.durum is Durum.DONUYOR
    assert pencere.cb_kanal.isEnabled() and pencere.btn_gecikme.isEnabled()
    x, y = pencere.ham_noktalar.getData()
    assert np.max(np.abs(y)) == pytest.approx(np.max(np.abs(pencere.dongu.son_sonuc.aki_Vs)) * 1e6, rel=0.05)
    # Ham gerilim sekmesi: günlükten önce; açıkken canlı değerleri gösterir
    assert [pencere.sekmeler.tabText(i) for i in range(pencere.sekmeler.count())][-2:] == [
        "Ham gerilim", "Günlük"
    ]
    dunya.ofset_V = 4.88e-3
    pencere.sekmeler.setCurrentWidget(pencere.sayfa_gerilim)
    for _ in range(40):
        dunya.ilerle(0.05)
        pencere._tick()
    assert "örnek/s" in pencere.lbl_akis.text()
    tx, ty = pencere.gerilim_egrisi.getData()
    assert tx[-1] == 0.0 and tx[0] == pytest.approx(-1.0, abs=1e-3)
    assert float(np.mean(ty)) == pytest.approx(4.88, abs=0.1)  # mV; ofset + bobin sinyali
    assert pencere.lbl_ham_ort.text().endswith(" mV")
    # Kaydet: kırmızı nokta ve dosya adı, süre dolunca soluk "Son kayıt"
    pencere.btn_ham_kaydet.click()
    assert "●" in pencere.lbl_ham_kayit.text() and "ham_" in pencere.lbl_ham_kayit.text()
    pencere._kayit_isareti_zamanlayici.timeout.emit()
    assert "●" not in pencere.lbl_ham_kayit.text() and "Son kayıt: ham_" in pencere.lbl_ham_kayit.text()
    pencere.chk_dondur.setChecked(True)
    eski = pencere.lbl_ham_ort.text()
    dunya.ofset_V = 0.0
    for _ in range(40):
        dunya.ilerle(0.05)
        pencere._tick()
    assert pencere.lbl_ham_ort.text() == eski
    # Kapanışta gerçek saatle beklenir; sahte motor yavaşlamasa da zaman
    # aşımından sonra servo kapatılmalı.
    import time as _time

    pencere.dongu.saat = _time.monotonic
    pencere.close()
    assert not dunya.servo
    uygulama.processEvents()


def test_pencere_baglan_ve_baslat_ilk_olcumu_yazar(kurulum, p, monkeypatch):
    # merkezle başlatıcısının yolu: --basla -> bağlan + başlat; ilk sağlıklı
    # ölçüm kilide yazılınca başlatıcı merkezleme'yi açar
    pytest.importorskip("PySide6")
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    from mgf.merkezleme_penceresi import MerkezlemePenceresi

    uygulama = QApplication.instance() or QApplication([])
    dunya, _, _ = kurulum
    p = dataclasses.replace(p, durma_zaman_asimi_s=0.3)
    pencere = MerkezlemePenceresi(p, SahteBaglanti(dunya), SahteMotor(dunya))
    pencere.dongu.saat = lambda: dunya.t
    pencere.zamanlayici.stop()
    assert not p.kilit_dosyasi.exists()
    pencere.baglan_ve_baslat()
    assert pencere.dongu.donuyor
    for _ in range(200):
        dunya.ilerle(0.05)
        pencere._tick()
        if p.kilit_dosyasi.exists():
            break
    assert p.kilit_dosyasi.exists()
    pencere.baglan_ve_baslat()  # zaten dönüyorsa bir şey yapmaz
    assert pencere.dongu.donuyor
    pencere.dongu.saat = time.monotonic  # kapatırken motor durdurma beklemesi gerçek saatle
    pencere.close()
    assert pencere.dongu.durum is Durum.BAGLI_DEGIL
    uygulama.processEvents()


def test_pencere_baglanamazsa_baslatmaz(kurulum, p, monkeypatch):
    pytest.importorskip("PySide6")
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    from mgf.merkezleme_penceresi import MerkezlemePenceresi

    QApplication.instance() or QApplication([])
    dunya, _, _ = kurulum
    baglanti = SahteBaglanti(dunya)
    baglanti.connect = lambda: False
    pencere = MerkezlemePenceresi(p, baglanti, SahteMotor(dunya))
    pencere.zamanlayici.stop()
    pencere.baglan_ve_baslat()
    assert pencere.dongu.durum is Durum.BAGLI_DEGIL and dunya.hiz == 0.0
    pencere.close()


# ---------------------------------------------------------------------------
# Oturum klasörü: otomatik kayıtlar
# ---------------------------------------------------------------------------
def _ham_oku(yol):
    satirlar = yol.read_text(encoding="utf-8").splitlines()
    basliklar = [s for s in satirlar if s.startswith("#")]
    return basliklar, len(satirlar) - len(basliklar) - 1  # sütun adı satırı hariç


def test_kayit_yoksa_oturum_klasoru_olusmaz(kurulum, p):
    dunya, dongu, _ = kurulum
    dongu.baglan()
    calistir(dunya, dongu, 1.0)
    assert dongu.oturum.dizin is None and not p.kayit_dizini.exists()


def test_hiz_oturunca_ham_veri_otomatik_kaydedilir(kurulum, p):
    dunya, dongu, gunluk = kurulum
    dongu.otomatik_yaz_ayarla(False)
    dongu.baglan()
    dongu.baslat()
    calistir(dunya, dongu, 6.0)  # hızlanma + oturma bekleyişi; 10 s henüz dolmadı
    assert any("Hız oturdu" in m for m in gunluk)
    assert not list(p.kayit_dizini.glob("*/ham_*_hiz_oturdu.csv"))
    calistir(dunya, dongu, 10.0)
    dosyalar = list(p.kayit_dizini.glob("*/ham_*_hiz_oturdu.csv"))
    assert len(dosyalar) == 1  # bir kez; hız oturmuş kaldıkça tekrar yazılmaz
    basliklar, n = _ham_oku(dosyalar[0])
    assert n == int(p.hiz_oturunca_kayit_s * SPS)
    assert "# etiket: hiz_oturdu" in basliklar
    # Sürekli ölçümlerin ham verisi yazılmaz (yalnızca sonuçları olcumler.csv'de)
    klasor = dosyalar[0].parent
    assert {y.name for y in klasor.glob("ham_*")} == {dosyalar[0].name}
    assert (klasor / "olcumler.csv").exists()
    # Günlük dosyası oturum başından beri tutulur (klasör sonradan oluşsa da)
    metin = (klasor / "gunluk.txt").read_text(encoding="utf-8")
    assert "Bağlandı" in metin and "Hız oturdu" in metin and "Ham veri kaydedildi" in metin


def test_merkezleme_olcumunun_ham_verisi_kaydedilir(kurulum, p):
    dunya, dongu, _ = kurulum
    p_kayitsiz = dataclasses.replace(p, hiz_oturunca_kayit_s=0.0)
    dongu.p = p_kayitsiz
    dongu.baglan()
    dongu.baslat()
    for _ in range(400):
        dunya.ilerle(0.05)
        dongu.tick()
        if p.kilit_dosyasi.exists():
            break
    assert dongu.olcum_sayisi == 1
    dosyalar = list(p.kayit_dizini.glob("*/ham_*"))
    assert [y.name.split("_", 2)[2] for y in dosyalar] == ["olcum001_merkezleme.csv"]
    basliklar, n = _ham_oku(dosyalar[0])
    assert n == dongu.gereken_ornek and "# olcumler_csv_satiri: 1" in basliklar


def test_zayif_alanda_mutlak_artik_kucukse_olcum_kabul_edilir(p):
    """Akım sıfırken (arka plan) yalnızca ortam alanı var: bağıl artık büyür,
    mutlak artık küçük kalır. 6 Kasım ölçümü: ~170 µT, oran ~0.1, ~0.1 µV·s."""
    t = np.arange(int(2.0 * SPS)) / SPS
    teta = 2 * math.pi * 8.0 * t
    rng = np.random.default_rng(1)
    c1 = complex(-1.4e-4, 1.0e-4)  # ~170 µT ortam dipolü, kuadrupol yok
    v = bobin_gerilimi(teta, 8.0, c1, 0j, p.bobin, p.r_ref_m) + rng.normal(0, 3e-5, len(t))
    s = mk.olcum_hesapla(np.degrees(teta) % 360, v, SPS, p.bobin, p.r_ref_m, 0.0)
    assert s.artik_orani > p.artik_esigi  # bağıl ölçüt tek başına reddederdi
    assert s.artik_rms_Vs < p.artik_tabani_Vs
    assert mk.saglik_sorunlari(s, p) == []
    assert mk.saglik_sorunlari(s, dataclasses.replace(p, artik_tabani_Vs=0.0))  # taban yoksa reddedilir
    # Mutlak artık da büyükse (ör. ölçüm sırasında değişen alan) reddedilir
    assert mk.saglik_sorunlari(s, dataclasses.replace(p, artik_tabani_Vs=0.5 * s.artik_rms_Vs))


# ---------------------------------------------------------------------------
# Kanal testi (kanal_testi.py): hangi kanal kuadrupolü görüyor?
# ---------------------------------------------------------------------------
def test_kanal_testi_duz_bobini_ayirt_eder(kurulum, p):
    from kanal_testi import KanalTesti
    from merkezleme.guc_kaynagi import KaynakGrubu, KomutGunlugu
    from merkezleme.yapilandirma import yapilandirma_yukle

    dunya, dongu, _ = kurulum
    kfg = yapilandirma_yukle(Path(__file__).resolve().parents[3] / "yapilandirma.yaml")
    grup = KaynakGrubu.olustur(kfg.guc_kaynaklari, kfg.guvenlik, canli=False,
                               gunluk=KomutGunlugu(), bekle=lambda s: None)
    duz = (2, 3)  # bu sahte dünyada kuadrupolü gören kanal

    def bekle(dt):  # alan akıma ve kanala bağlı: düz kanal kuadrupolü görür, öbürleri görmez
        I = float(np.mean(grup.ayar_akimlari_A))
        olcek = I / 9.5
        if dunya.kanal == duz:
            dunya.c1, dunya.c2 = complex(45e-6, 0) + 0.2e-3 * olcek, complex(2.4e-3, 0) * olcek
        else:
            dunya.c1, dunya.c2 = complex(90e-6, 0) + 1.9e-3 * olcek, complex(0.2e-3, 0) * olcek
        dunya.ilerle(dt)

    dongu.baglan()
    satirlar_yazilan: list[str] = []
    test = KanalTesti(p, dongu, grup, akim_A=9.5, tekrar=2, pencere_s=2.0,
                      bekle=bekle, saat=lambda: dunya.t, yaz=satirlar_yazilan.append)
    grup.baslat()
    sonuclar = test.calistir()
    assert len(sonuclar.olcumler) == 3 * len(p.kanallar)
    assert all(len(v) == 2 for v in sonuclar.olcumler.values())
    rapor = {s["kanal"]: s for s in test.rapor()}
    duz_ad = next(ad for ad, k in p.kanallar.items() if k == duz)
    assert rapor[duz_ad]["G_beklenene_orani"] == pytest.approx(0.096 / 0.095, rel=0.02)
    assert rapor[duz_ad]["arka_plan_C1_uT"] == pytest.approx(45.0, rel=0.02)
    for ad, s in rapor.items():
        if ad != duz_ad:
            assert s["G_beklenene_orani"] < 0.1 and s["dipol_kuad_orani"] > 5
    yol = test.raporu_yaz(test.rapor())
    assert yol.exists() and yol.parent.parent == p.kayit_dizini
    assert any("ÖZET" in m for m in satirlar_yazilan)
    # Her ölçümün ham verisi kaydedildi (tek ölçüm)
    assert len(list(yol.parent.glob("ham_*_tek.csv"))) == 3 * len(p.kanallar) * 2
    # Akımlar sonunda sıfırda; güvenli kapatma çıkışları kapatır
    assert np.all(grup.ayar_akimlari_A == 0)
    grup.guvenli_kapat()
    assert all(not k.cikis_acik for k in grup.kaynaklar)


def test_gurultu_testi_sahte_cihazla(kurulum, p):
    from gurultu_testi import GurultuTesti
    from merkezleme.guc_kaynagi import KaynakGrubu, KomutGunlugu
    from merkezleme.yapilandirma import yapilandirma_yukle

    dunya, dongu, _ = kurulum
    kfg = yapilandirma_yukle(Path(__file__).resolve().parents[3] / "yapilandirma_7A.yaml")
    grup = KaynakGrubu.olustur(kfg.guc_kaynaklari, kfg.guvenlik, canli=False,
                               gunluk=KomutGunlugu(), bekle=lambda s: None)
    dunya.gurultu_V = 2e-6
    dongu.baglan()
    R = np.array([[-0.0167, 0.0116, 0.017, -0.0121], [-0.0108, -0.0185, 0.012, 0.0175], [0.21, 0.23, 0.29, 0.26]])
    yazilan: list[str] = []
    test = GurultuTesti(p, dongu, grup, akim_A=7.0, pencere_s=2.0, hizlar=(8, 11, 8), n=3, R=R,
                        bekle=dunya.ilerle, saat=lambda: dunya.t, yaz=yazilan.append)
    grup.baslat()
    satirlar = test.calistir()
    assert len(satirlar) == 3 * 3 and {s["hiz_hz"] for s in satirlar} == {8, 11}
    assert all(s["akim_okuma_sayisi"] >= 1 for s in satirlar)
    ozet = test.rapor()
    assert len(ozet) == 3 and all(np.isfinite(o["sigma_x_um"]) for o in ozet)
    klasor = test.raporu_yaz(ozet)
    assert (klasor / "gurultu_testi.csv").exists() and (klasor / "gurultu_testi_ozet.csv").exists()
    assert np.all(grup.ayar_akimlari_A == 0)


def test_pencere_baglan_motoru_baslatmaz(kurulum, p, monkeypatch):
    # Birleşik pencere açılışta yalnızca bağlanır; motor kullanıcı "Başlat" deyince
    pytest.importorskip("PySide6")
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    from mgf.merkezleme_penceresi import MerkezlemePenceresi

    QApplication.instance() or QApplication([])
    dunya, _, _ = kurulum
    pencere = MerkezlemePenceresi(p, SahteBaglanti(dunya), SahteMotor(dunya))
    pencere.zamanlayici.stop()
    pencere.baglan()
    for _ in range(40):
        dunya.ilerle(0.05)
        pencere._tick()
    assert pencere.dongu.durum is Durum.HAZIR and not pencere.dongu.donuyor and dunya.hiz == 0.0
    assert not dunya.servo
    pencere.close()


def test_alan_grafiginden_arka_plan_cikarilir(kurulum, p, monkeypatch):
    pytest.importorskip("PySide6")
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    from mgf.merkezleme_penceresi import MerkezlemePenceresi

    QApplication.instance() or QApplication([])
    dunya, _, _ = kurulum
    dunya.c1 = complex(40e-6, 0)
    pencere = MerkezlemePenceresi(p, SahteBaglanti(dunya), SahteMotor(dunya))
    pencere.zamanlayici.stop()
    pencere.dongu.saat = lambda: dunya.t
    pencere.dongu.otomatik_yaz_ayarla(False)  # sürekli ölçüm
    pencere.baglan_ve_baslat()
    for _ in range(240):
        dunya.ilerle(0.05)
        pencere._tick()
    assert pencere.dongu.gecmis
    pencere.chk_arka_cikar.setChecked(True)
    assert "ARKA PLAN ÇIKARILMIŞ" not in pencere.lbl_cok_kutup.text()  # kaynak yok: değişmez
    pencere.arka_plan_kaynagi = lambda: {1: complex(40e-6, 0)}
    pencere._grafikleri_ciz()
    metin = pencere.lbl_cok_kutup.text()
    assert "ARKA PLAN ÇIKARILMIŞ" in metin and "|C<sub>1</sub>| = " in metin
    c1 = float(metin.split("|C<sub>1</sub>| = ")[1].split(" T")[0])
    assert c1 < 1e-6  # 40 µT'lik alan çıkarıldı
    pencere.dongu.saat = time.monotonic  # kapanışta gerçek saat
    pencere.close()


def test_olcum_durumu_degisince_uyarir_ve_adc_yeniden_ayarlanir(kurulum):
    # 6 Kasım 17:40: osiloskop kapanınca dipol saçılımı ve artık birden büyüdü
    dunya, dongu, gunluk = kurulum
    dongu.otomatik_yaz_ayarla(False)
    dongu.baglan()
    dongu.baslat()
    dunya.gurultu_V = 2e-6
    calistir(dunya, dongu, 6.0 + 2.0 * 32)  # ~30 sağlıklı sürekli ölçüm
    assert dongu.durum_uyarisi == ""
    dunya.gurultu_V = 4e-4  # bozulma
    calistir(dunya, dongu, 2.0 * 12)
    assert dongu.durum_uyarisi.startswith("ÖLÇÜM DURUMU DEĞİŞTİ")
    assert any("ADC'yi yeniden ayarla" in m for m in gunluk)
    komut_sayisi = len(dunya.komutlar)
    assert dongu.adc_yeniden_ayarla()
    yeni = [k for k, _ in dunya.komutlar[komut_sayisi:]]
    assert protocol.CMD_SET_GAIN in yeni and protocol.CMD_SET_SCAN_CHANNELS in yeni
    assert dongu.durum_uyarisi == "" and not dongu.gecmis and dongu.donuyor


def test_adc_yeniden_ayarla_bagli_degilken(kurulum):
    _, dongu, gunluk = kurulum
    assert not dongu.adc_yeniden_ayarla() and "bağlı değil" in gunluk[-1]
