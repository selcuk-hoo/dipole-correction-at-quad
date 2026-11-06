"""Güç kaynağı - bobin eşleştirmesi (merkezleme/eslestirme.py)."""
from __future__ import annotations

import shutil

import pytest

from merkezleme.eslestirme import (
    Okuma,
    adresleri_denetle,
    eslesme_bul,
    pencere_olustur,
    yapilandirmaya_yaz,
)
from merkezleme.yapilandirma import yapilandirma_yukle

from .conftest import YAPILANDIRMA_YOLU


def _okuma(seri: str, ayar: float, cikis: bool = False, olculen: float = 0.0) -> Okuma:
    return Okuma(f"ASRL/dev/serial/by-id/usb-ITECH_IT-M3233_{seri}-if00::INSTR", seri, cikis, ayar, olculen)


def test_ayara_gore_bobin_sirasiyla_eslesir():
    okumalar = [_okuma("A", 3.0), _okuma("B", 1.0), _okuma("C", 4.0), _okuma("D", 2.0)]
    adresler, sorunlar = eslesme_bul(okumalar)
    assert sorunlar == []
    assert adresler == [okumalar[i].adres for i in (1, 3, 0, 2)]


def test_cikis_aciksa_olculen_akim_kullanilir():
    okumalar = [
        _okuma("A", ayar=9.0, cikis=True, olculen=1.02),
        _okuma("B", ayar=9.0, cikis=True, olculen=1.97),
        _okuma("C", 3.0),
        _okuma("D", 4.0),
    ]
    adresler, sorunlar = eslesme_bul(okumalar)
    assert sorunlar == [] and adresler[0] == okumalar[0].adres


@pytest.mark.parametrize(
    "okumalar, beklenen",
    [
        ([_okuma("A", 1.0), _okuma("B", 1.0), _okuma("C", 3.0), _okuma("D", 4.0)], "birden fazla"),
        ([_okuma("A", 1.0), _okuma("B", 2.5), _okuma("C", 3.0), _okuma("D", 4.0)], "yakın değil"),
        ([_okuma("A", 9.0), _okuma("B", 2.0), _okuma("C", 3.0), _okuma("D", 4.0)], "yakın değil"),
        ([_okuma("A", 1.0), _okuma("B", 2.0), _okuma("C", 3.0)], "3 güç kaynağı"),
    ],
)
def test_tutarsiz_eslesme_kaydedilmez(okumalar, beklenen):
    adresler, sorunlar = eslesme_bul(okumalar)
    assert adresler is None and any(beklenen in s for s in sorunlar)


def test_okunamayan_cihaz_bildirilir():
    okumalar = [_okuma("A", 1.0), _okuma("B", 2.0), _okuma("C", 3.0), Okuma("x", "D", hata="timeout")]
    adresler, sorunlar = eslesme_bul(okumalar)
    assert adresler is None and any("D: okunamadı" in s for s in sorunlar)


def test_yapilandirmaya_yazilir_geri_kalan_degismez(tmp_path):
    yol = tmp_path / "yapilandirma.yaml"
    shutil.copy(YAPILANDIRMA_YOLU, yol)
    once = yol.read_text(encoding="utf-8")
    adresler = [f"ASRL/dev/serial/by-id/usb-ITECH_{n}-if00::INSTR" for n in range(1, 5)]
    yapilandirmaya_yaz(yol, adresler)
    kfg = yapilandirma_yukle(yol)
    assert kfg.guc_kaynaklari.visa_adresleri == adresler
    assert kfg.guc_kaynaklari.uyum_gerilimi_V == yapilandirma_yukle(YAPILANDIRMA_YOLU).guc_kaynaklari.uyum_gerilimi_V
    # Yalnızca adres bloğu değişti; ikinci yazım da aynı bloğu değiştirir (tekrar edilebilir)
    sonra = yol.read_text(encoding="utf-8")
    assert len(sonra.splitlines()) == len(once.splitlines())
    yapilandirmaya_yaz(yol, list(reversed(adresler)))
    assert yapilandirma_yukle(yol).guc_kaynaklari.visa_adresleri == list(reversed(adresler))
    assert len(yol.read_text(encoding="utf-8").splitlines()) == len(once.splitlines())
    assert "# bobin 1 (sağ üst)" in yol.read_text(encoding="utf-8")


def test_adres_denetimi(tmp_path, capsys):
    yol = tmp_path / "yapilandirma.yaml"
    shutil.copy(YAPILANDIRMA_YOLU, yol)
    var = tmp_path / "port"
    var.touch()
    yapilandirmaya_yaz(yol, [f"ASRL{var}::INSTR"] * 3 + ["ASRL/dev/yok-boyle-port::INSTR"])
    assert adresleri_denetle(yol) == 1
    assert "/dev/yok-boyle-port" in capsys.readouterr().out
    yapilandirmaya_yaz(yol, [f"ASRL{var}::INSTR"] * 4)
    assert adresleri_denetle(yol) == 0


def test_pencere_eslesince_kaydeder(qt_uygulama, tmp_path):
    yol = tmp_path / "yapilandirma.yaml"
    shutil.copy(YAPILANDIRMA_YOLU, yol)
    okumalar = [_okuma("A", 2.0), _okuma("B", 1.0), _okuma("C", 4.0), _okuma("D", 9.0)]
    pencere = pencere_olustur(yol, lambda: okumalar, "varsayilan")
    pencere.zamanlayici.stop()
    assert not pencere.kaydet_dugmesi.isEnabled() and "D: 9.000 A" in pencere.durum.text()
    assert pencere.tablo.item(1, 4).text() == "1 (sağ üst)"
    okumalar[3] = _okuma("D", 3.0)
    pencere.yenile()
    assert pencere.kaydet_dugmesi.isEnabled()
    pencere.kaydet()
    assert "Kaydedildi" in pencere.durum.text()
    beklenen = [okumalar[i].adres for i in (1, 0, 3, 2)]
    assert yapilandirma_yukle(yol).guc_kaynaklari.visa_adresleri == beklenen
    pencere.close()
