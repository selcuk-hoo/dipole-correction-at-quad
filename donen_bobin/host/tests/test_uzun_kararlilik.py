"""uzun_kararlilik: fazların tamamı sahte dönen bobin + merkezleme simülatörüyle.

Alan, o anki güç kaynağı akımlarından simülatörle hesaplanır (test_kapali_dongu
gibi); betiğin saati sahte dünyanın saatidir, böylece dakikalık fazlar saniyelerde
geçer."""
from __future__ import annotations

import dataclasses
import math
import types

import numpy as np
import pytest

import uzun_kararlilik as uk
from mgf import merkezleme_koprusu as mk
from mgf.olcum_dongusu import Durum, OlcumDongusu

from test_merkezleme_olcer import SahteBaglanti, SahteDunya, SahteMotor


@pytest.fixture
def duzenek(tmp_path, monkeypatch):
    from merkezleme.guc_kaynagi import KaynakGrubu
    from merkezleme.simulator import Simulator
    from merkezleme.yapilandirma import yapilandirma_yukle

    kfg = yapilandirma_yukle(mk.REPO_KOKU / "yapilandirma.yaml")
    kilit = tmp_path / "veri_kilidi" / ".kilit"
    kfg = dataclasses.replace(
        kfg,
        genel=dataclasses.replace(kfg.genel, calistirma_kok_dizini=str(tmp_path / "calistirmalar")),
        dosya_girisi=dataclasses.replace(kfg.dosya_girisi, kilit_dosyasi=str(kilit), zaman_asimi_s=60.0,
                                         yoklama_araligi_s=0.002),
        duzeltme=dataclasses.replace(kfg.duzeltme, merkez_toleransi_um=10.0),
    )
    p = dataclasses.replace(mk.parametreleri_yukle(), kilit_dosyasi=kilit, kayit_dizini=tmp_path / "olcumler",
                            oturma_suresi_s=0.5)
    sim = Simulator(kfg.simulator, kfg.miknatis, kfg.harmonikler)
    sim.ofset_m = complex(300e-6, -150e-6)
    grup = KaynakGrubu.olustur(kfg.guc_kaynaklari, kfg.guvenlik, canli=False)
    dunya = SahteDunya(p)
    dongu = OlcumDongusu(p, SahteBaglanti(dunya), SahteMotor(dunya), saat=lambda: dunya.t)

    def ilerle(_s: float = 0.0) -> None:
        akimlar = grup.ayar_akimlari_A.copy()
        dunya.c1 = sim.harmonik_ham_T(akimlar, 1) + sim.arka_plan_T
        dunya.c2 = sim.harmonik_ham_T(akimlar, 2)
        dunya.ilerle(0.05)

    # Betiğin saati sahte dünyanın saati; her uyuma dünyayı 50 ms ilerletir
    monkeypatch.setattr(uk, "time", types.SimpleNamespace(monotonic=lambda: dunya.t, sleep=ilerle))
    monkeypatch.setattr(uk, "HAM_KAYIT_ARALIGI_S", 1e9)
    grup.bekle = lambda s: None
    dongu.baglan()
    dongu.otomatik_yaz_ayarla(False)
    dongu.hiz_ayarla(8.0)
    dongu.baslat()
    for _ in range(2000):  # en fazla 100 s sahte zaman (sonsuz döngü belleği doldurmasın)
        if dongu.durum is Durum.DONUYOR:
            break
        dongu.tick()
        ilerle()
    assert dongu.durum is Durum.DONUYOR, dongu.durum
    grup.baslat()
    return types.SimpleNamespace(kfg=kfg, p=p, sim=sim, grup=grup, dunya=dunya, dongu=dongu, ilerle=ilerle)


def test_butun_fazlar_kaydedilir_ve_ayni_akimlara_donulur(duzenek):
    d = duzenek
    mesajlar: list[str] = []
    olcum = uk.UzunOlcum(d.p, d.kfg, d.dongu, d.grup, [60.0, 60.0, 40.0, 60.0, 40.0], 10.0, mesajlar.append)
    d.grup.bekle = olcum.bekle
    olcum.calistir()
    olcum.durdur()

    f = olcum.faz_satirlari
    assert set(f) == set(uk.FAZLAR)
    assert all(len(f[ad]) >= 3 for ad in uk.FAZLAR)
    for ad in ("ortam1", "ortam2", "ortam3"):  # akımsız: net merkez yok, akımlar sıfır
        assert all(math.isnan(s["x_net_um"]) for s in f[ad])
        assert all(abs(s["B2_mT"]) < 1e-3 for s in f[ad])
    for ad in ("akimli1", "akimli2"):  # merkezlenmiş: net merkez toleransın içinde
        x = np.array([s["x_net_um"] for s in f[ad]])
        y = np.array([s["y_net_um"] for s in f[ad]])
        assert np.all(np.isfinite(x)) and abs(x.mean()) < 15 and abs(y.mean()) < 15
    a = olcum.faz_ayarlari  # geri okunan akımlar iş parçacığından gelir, gecikebilir; ayarlar kesin
    assert np.array_equal(a["akimli1"], a["akimli2"]) and np.all(a["akimli1"] > 9.0)  # yeniden optimize yok
    assert all(np.allclose(a[ad], 0) for ad in ("ortam1", "ortam2", "ortam3"))
    assert np.allclose(d.grup.ayar_akimlari_A, 0)  # sonda akımlar sıfır
    satirlar = olcum.csv_yolu.read_text(encoding="utf-8").splitlines()
    assert satirlar[0].split(",") == uk.SUTUNLAR and len(satirlar) == 1 + sum(len(v) for v in f.values())
    assert sum("bitti" in m for m in mesajlar) == 6 and any("merkezleme" in m for m in mesajlar)


def test_adc_takilinca_durur(duzenek):
    d = duzenek
    olcum = uk.UzunOlcum(d.p, d.kfg, d.dongu, d.grup, [60.0] * 5, 10.0, lambda m: None)
    d.dongu._ham_veri = lambda s: (np.zeros(3600), np.full(3600, 0.078125))
    with pytest.raises(uk.OlcumHatasi, match="ADC takıldı"):
        olcum.bekle(2.0)
    olcum.durdur()


def test_kaydi_hesapla_net_merkez():
    arka = (complex(30e-6, 5e-6), 0j)
    o = [types.SimpleNamespace(harmonikler=(arka[0] + complex(b, 0), complex(2.4e-3, 0)), hiz_hz=8.0,
                               artik_orani=0.006, ayiklanan_aci=1) for b in (1e-6, 2e-6, 3e-6)]
    k = uk.kaydi_hesapla(o, arka, 0.025)
    assert k["n_olcum"] == 3 and k["ayiklanan_aci"] == 3
    assert k["x_net_um"] == pytest.approx(-0.025 * 2e-6 / 2.4e-3 * 1e6)
    assert k["sB1_uT"] == pytest.approx(1.0)
    assert math.isnan(uk.kaydi_hesapla(o, None, 0.025)["x_net_um"])


def test_akimlar_verilince_merkezleme_atlanir_ve_sifir_fazlar_atlanir(duzenek):
    d = duzenek
    mesajlar: list[str] = []
    akimlar = np.array([9.53, 9.41, 9.47, 9.60])
    olcum = uk.UzunOlcum(d.p, d.kfg, d.dongu, d.grup, [40.0, 0.0, 0.0, 60.0, 30.0], 10.0, mesajlar.append)
    d.grup.bekle = olcum.bekle
    olcum.calistir(akimlar)
    olcum.durdur()
    assert set(olcum.faz_satirlari) == {"ortam1", "akimli2", "ortam3"}
    assert np.allclose(olcum.faz_ayarlari["akimli2"], akimlar)
    assert all(math.isfinite(s["x_net_um"]) for s in olcum.faz_satirlari["akimli2"])  # arka plan: ortam1
    assert any("merkezleme atlandı" in m for m in mesajlar)
    assert not any("merkezleme</b> başladı" in m for m in mesajlar)
    assert np.allclose(d.grup.ayar_akimlari_A, 0)
