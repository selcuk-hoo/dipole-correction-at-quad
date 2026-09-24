"""DosyaGirisi testleri: kilit protokolü, atomik okuma, zaman aşımı, hata yolları."""
from __future__ import annotations

import json
import threading
import time

import pytest

from merkezleme.olcum_kaynagi import (
    DosyaGirisi,
    DosyaGirisiHatasi,
    DosyaGirisiZamanAsimi,
    OlcumIstegi,
)
from merkezleme.yapilandirma import DosyaGirisiYapilandirmasi

import numpy as np


def _ayar(tmp_path, zaman_asimi_s: float = 1.0, yoklama_araligi_s: float = 0.01):
    return DosyaGirisiYapilandirmasi(
        kilit_dosyasi=str(tmp_path / "veri_kilidi" / ".kilit"),
        zaman_asimi_s=zaman_asimi_s,
        yoklama_araligi_s=yoklama_araligi_s,
    )


def _istek() -> OlcumIstegi:
    return OlcumIstegi(
        tur="olcum",
        etiket="test",
        akimlar_A=np.full(4, 10.0),
        adim_no=1,
        toplam_adim=1,
    )


def _atomik_yaz(yol, veri: dict) -> None:
    """Dönen bobin tarafının yapması gereken: geçici dosya + atomik taşıma."""
    gecici = yol.with_suffix(".tmp")
    gecici.write_text(json.dumps(veri), encoding="utf-8")
    gecici.replace(yol)


def test_kilit_yoksa_veri_gelene_kadar_yoklar(tmp_path, konvansiyon):
    # Gerçek bekle() kullanılır: ayrı iplikteki yazıcının araya girebilmesi için.
    ayar = _ayar(tmp_path)
    kaynak = DosyaGirisi(ayar, konvansiyon, bekle=time.sleep)

    sonuc: dict = {}

    def dinleyici():
        sonuc["olcum"] = kaynak.olcum_al(_istek())

    iplik = threading.Thread(target=dinleyici)
    iplik.start()
    time.sleep(0.05)
    assert "olcum" not in sonuc, "veri gelmeden olcum_al dönmemeli"
    _atomik_yaz(kaynak.kilit_yolu, {"b0": 1e-6, "a0": 2e-7, "b1": 2.5e-3, "a1": -3e-6})
    iplik.join(timeout=2.0)
    assert "olcum" in sonuc
    olcum = sonuc["olcum"]
    assert olcum.bilesen(1) == pytest.approx(1e-6 + 2e-7j)
    assert olcum.bilesen(2) == pytest.approx(2.5e-3 - 3e-6j)


def test_ikinci_cagri_onceki_kilidi_silerek_baslar(tmp_path, konvansiyon):
    """Bir sonraki olcum_al(), akımlar değiştikten sonra "ölç" sinyalini verir."""
    ayar = _ayar(tmp_path)
    kaynak = DosyaGirisi(ayar, konvansiyon, bekle=lambda s: None)
    _bir_kez_yaz_bekle(
        kaynak, lambda: _atomik_yaz(kaynak.kilit_yolu, {"b0": 1e-6, "a0": 0.0, "b1": 2.5e-3, "a1": 0.0})
    )
    kaynak.olcum_al(_istek())
    assert kaynak.kilit_yolu.exists(), "ilk çağrıdan sonra kilit hemen silinmemeli"

    kaynak.bekle = time.sleep
    sonuc: dict = {}
    iplik = threading.Thread(target=lambda: sonuc.update(olcum=kaynak.olcum_al(_istek())))
    iplik.start()
    time.sleep(0.05)
    assert not kaynak.kilit_yolu.exists(), "ikinci çağrı eski kilidi silip 'ölç' demeli"
    _atomik_yaz(kaynak.kilit_yolu, {"b0": 5e-7, "a0": 0.0, "b1": 2.5e-3, "a1": 0.0})
    iplik.join(timeout=2.0)
    assert sonuc["olcum"].bilesen(1) == pytest.approx(5e-7 + 0j)


def test_zaman_asiminda_acikca_hata_verir(tmp_path, konvansiyon):
    ayar = _ayar(tmp_path, zaman_asimi_s=0.05, yoklama_araligi_s=0.01)
    kaynak = DosyaGirisi(ayar, konvansiyon, bekle=lambda s: None)
    with pytest.raises(DosyaGirisiZamanAsimi):
        kaynak.olcum_al(_istek())


def _bir_kez_yaz_bekle(kaynak: DosyaGirisi, yazici) -> None:
    """`bekle()` yerine geçer: ilk yoklamada veriyi yazar, tıpkı gerçek dönen
    bobin programının "kilit yok -> ölç ve yaz" davranışını taklit ederek.

    Doğrudan `write_text` ile önceden yazmak işe yaramaz: `olcum_al()`, her
    çağrının BAŞINDA önceki (bu durumda henüz tüketilmemiş) kilidi "eski"
    sayıp siler - bkz. sınıf docstring'i.
    """
    yazildi = False

    def bekle(saniye: float) -> None:
        nonlocal yazildi
        if not yazildi:
            yazici()
            yazildi = True

    kaynak.bekle = bekle


def test_bozuk_json_aciklayici_hata_verir(tmp_path, konvansiyon):
    ayar = _ayar(tmp_path)
    kaynak = DosyaGirisi(ayar, konvansiyon, bekle=lambda s: None)
    _bir_kez_yaz_bekle(kaynak, lambda: kaynak.kilit_yolu.write_text("{bozuk", encoding="utf-8"))
    with pytest.raises(DosyaGirisiHatasi, match="JSON"):
        kaynak.olcum_al(_istek())


def test_eksik_alan_aciklayici_hata_verir(tmp_path, konvansiyon):
    ayar = _ayar(tmp_path)
    kaynak = DosyaGirisi(ayar, konvansiyon, bekle=lambda s: None)
    _bir_kez_yaz_bekle(kaynak, lambda: _atomik_yaz(kaynak.kilit_yolu, {"b0": 1e-6, "a0": 0.0}))
    with pytest.raises(DosyaGirisiHatasi, match="eksik"):
        kaynak.olcum_al(_istek())


def test_sayi_olmayan_deger_aciklayici_hata_verir(tmp_path, konvansiyon):
    ayar = _ayar(tmp_path)
    kaynak = DosyaGirisi(ayar, konvansiyon, bekle=lambda s: None)
    _bir_kez_yaz_bekle(
        kaynak,
        lambda: _atomik_yaz(kaynak.kilit_yolu, {"b0": "abc", "a0": 0.0, "b1": 2.5e-3, "a1": 0.0}),
    )
    with pytest.raises(DosyaGirisiHatasi):
        kaynak.olcum_al(_istek())


# ---------------------------------------------------------------------------
# Uçtan uca: IsAkisi + DosyaGirisi, gerçekçi (fiziği yanıtlayan) bir "dönen
# bobin" iş parçacığıyla.
# ---------------------------------------------------------------------------
def test_dosyadan_tam_akis_yakinsar(kfg, konvansiyon, mod_bazi, simulator_uret, kaynak_grubu_uret, tmp_path):
    """DosyaGirisi üzerinden sürülen tam akış, elle/simülatör kaynağındaki
    gibi toleransa yakınsamalı; kilit protokolü gerçek bir arka iplikle
    (akım -> gerçek Simulator yanıtı -> atomik yazma) sınanır."""
    from merkezleme.is_akisi import Faz, IsAkisi, otomatik_yurut
    from merkezleme.kayit import Calistirma

    sim = simulator_uret(ofset_m=complex(220e-6, -130e-6), tohum=71)
    ayar = _ayar(tmp_path, zaman_asimi_s=5.0, yoklama_araligi_s=0.01)
    kaynak = DosyaGirisi(ayar, konvansiyon, bekle=time.sleep)
    calistirma = Calistirma(kfg, kok=tmp_path / "calistirmalar")
    akis = IsAkisi(kfg, kaynak_grubu_uret(), kaynak, calistirma, konvansiyon, mod_bazi)

    durdur = threading.Event()

    def donen_bobin() -> None:
        """Sürekli çalışır: kilit yoksa mevcut akımı gerçekten ölçüp yazar."""
        while not durdur.is_set():
            if not kaynak.kilit_yolu.exists():
                akimlar = akis.kaynaklar.ayar_akimlari_A.copy()
                olcum = sim.olc(akimlar, gurultu=False)
                b1, a1 = konvansiyon.normal_skewe(olcum.bilesen(1))
                b2, a2 = konvansiyon.normal_skewe(olcum.bilesen(2))
                _atomik_yaz(kaynak.kilit_yolu, {"b0": b1, "a0": a1, "b1": b2, "a1": a2})
            time.sleep(0.005)

    iplik = threading.Thread(target=donen_bobin, daemon=True)
    iplik.start()
    try:
        akis.basla()
        otomatik_yurut(akis, kaynak, max_adim=200)
    finally:
        durdur.set()
        iplik.join(timeout=2.0)

    assert akis.faz is Faz.TAMAMLANDI, akis.durdurma_nedeni
    assert akis.iterasyon <= 3
    from merkezleme.duzeltme import yakinsama_durumu

    assert yakinsama_durumu(akis.son_y, kfg.duzeltme).yakinsadi, akis.son_y
