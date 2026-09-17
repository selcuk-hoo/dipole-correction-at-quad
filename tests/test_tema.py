"""Tema testleri: palet tutarliligi, yapilandirma dogrulamasi ve arayuzde uygulama."""
from __future__ import annotations

import dataclasses
import os
import re

import pytest

from merkezleme.tema import FOSFOR_TURUNCU, FOSFOR_YESIL, TEMALAR, VARSAYILAN, tema_al
from merkezleme.yapilandirma import YapilandirmaHatasi, yapilandirma_yukle

RENK_DESENI = re.compile(r"^#[0-9a-fA-F]{6}$")


def test_uc_tema_var():
    assert set(TEMALAR) == {"varsayilan", "fosfor_yesil", "fosfor_turuncu"}
    assert tema_al("fosfor_yesil") is FOSFOR_YESIL
    assert tema_al("fosfor_turuncu") is FOSFOR_TURUNCU


def test_bilinmeyen_tema_aciklayici_hata():
    with pytest.raises(KeyError, match="seçenekler"):
        tema_al("fosfor_mavi")


@pytest.mark.parametrize("tema", [FOSFOR_YESIL, FOSFOR_TURUNCU], ids=["yesil", "turuncu"])
def test_monokrom_paletleri_gecerli_renkler(tema):
    for ad in ("arka_plan", "panel_arka_plan", "on_plan", "parlak", "sonuk", "cok_sonuk"):
        deger = getattr(tema, ad)
        assert RENK_DESENI.match(deger), f"{tema.ad}.{ad} = {deger!r} gecerli renk degil"
    assert tema.monokrom is True
    assert tema.font_yigini, "monokrom temada yazi tipi yigini tanimli olmali"


@pytest.mark.parametrize("tema", [FOSFOR_YESIL, FOSFOR_TURUNCU], ids=["yesil", "turuncu"])
def test_monokrom_stil_sayfasi_temel_ogeleri_kapsar(tema):
    qss = tema.stil_sayfasi()
    for secici in (
        "QWidget",
        "QLabel",
        "QGroupBox",
        "QLineEdit",
        "QPushButton",
        "QComboBox",
        "QPlainTextEdit",
        "QMessageBox",
        "QScrollBar",
    ):
        assert secici in qss, f"{tema.ad}: {secici} stillenmemis"
    # Zemin ve on plan gercekten paletten geliyor
    assert tema.arka_plan in qss and tema.on_plan in qss
    # Ters video: dugme uzerine gelindiginde zemin/on plan yer degistirir
    assert f"background-color: {tema.on_plan}" in qss


def test_varsayilan_tema_stil_sayfasi_bos():
    """Varsayilan tema sistem gorunumunu bozmamali."""
    assert VARSAYILAN.stil_sayfasi() == ""
    assert VARSAYILAN.monokrom is False


@pytest.mark.parametrize("tema", list(TEMALAR.values()), ids=list(TEMALAR))
def test_rol_stilleri_bos_degil(tema):
    """Her tema, arayuzun ihtiyaci olan butun rol stillerini uretmeli."""
    assert tema.kip_stili(canli=True)
    assert tema.kip_stili(canli=False)
    assert tema.deneme_stili()
    assert tema.eylem_stili()
    assert tema.yorum_stili()
    assert tema.sonuc_stili()
    assert tema.sonuk_stili()
    assert tema.zorunlu_stili()
    assert tema.durdur_stili()


@pytest.mark.parametrize("tema", [FOSFOR_YESIL, FOSFOR_TURUNCU], ids=["yesil", "turuncu"])
def test_monokrom_temada_renkli_vurgu_kullanilmaz(tema):
    """Monokrom temada kirmizi/mavi/sari gibi renkler sizmamali."""
    renkli = (tema.tehlike_zemin, tema.vurgu, tema.uyari_zemin, tema.iyi_zemin, tema.deneme_zemin)
    stiller = " ".join(
        [
            tema.stil_sayfasi(),
            tema.kip_stili(True),
            tema.kip_stili(False),
            tema.deneme_stili(),
            tema.eylem_stili(),
            tema.yorum_stili(),
            tema.sonuc_stili(),
            tema.sonuk_stili(),
            tema.zorunlu_stili(),
            tema.durdur_stili(),
        ]
    )
    for renk in renkli:
        assert renk not in stiller, f"{tema.ad} icinde renkli vurgu kullanilmis: {renk}"
    # DURDUR dugmesi ters videoya gecmeli (kirmizi yok)
    assert tema.arka_plan in tema.durdur_stili()
    assert tema.on_plan in tema.durdur_stili()


def test_yapilandirma_temayi_dogrular(tmp_path):
    kaynak = (
        yapilandirma_yukle("yapilandirma.yaml").kaynak_dosya.read_text(encoding="utf-8")
    )
    kotu = tmp_path / "kotu.yaml"
    kotu.write_text(kaynak.replace("tema: varsayilan", "tema: fosfor_mor"), encoding="utf-8")
    with pytest.raises(YapilandirmaHatasi, match="tema"):
        yapilandirma_yukle(kotu)

    iyi = tmp_path / "iyi.yaml"
    iyi.write_text(kaynak.replace("tema: varsayilan", "tema: fosfor_turuncu"), encoding="utf-8")
    assert yapilandirma_yukle(iyi).genel.tema == "fosfor_turuncu"


def test_yapilandirmada_tema_yoksa_varsayilan(tmp_path):
    """Eski yapilandirma dosyalari (tema anahtari olmayan) da calismali."""
    kaynak = yapilandirma_yukle("yapilandirma.yaml").kaynak_dosya.read_text(encoding="utf-8")
    eski = tmp_path / "eski.yaml"
    eski.write_text(kaynak.replace("  tema: varsayilan\n", ""), encoding="utf-8")
    assert yapilandirma_yukle(eski).genel.tema == "varsayilan"


# ---------------------------------------------------------------------------
# Arayuzde tema
# ---------------------------------------------------------------------------
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PyQt5", reason="PyQt5 kurulu degil")

from PyQt5.QtWidgets import QApplication, QMessageBox  # noqa: E402


@pytest.fixture
def pencere(kfg, simulator_uret, akis_uret, monkeypatch, qt_uygulama):
    from merkezleme.arayuz import MerkezlemePencere

    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Yes))
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: None))
    sim = simulator_uret(ofset_m=complex(150e-6, -90e-6), tohum=91)
    akis, kaynak, _ = akis_uret(sim)
    p = MerkezlemePencere(kfg, akis, deneme_kipi=True)
    yield p
    akis.kaynaklar.acil_sifirla()
    qt_uygulama.setStyleSheet("")  # sonraki testlere sizmasin


def test_tema_secici_uc_secenek_sunar(pencere):
    assert pencere.tema_secici.count() == 3
    adlar = [pencere.tema_secici.itemData(i) for i in range(pencere.tema_secici.count())]
    assert adlar == list(TEMALAR)


def test_tema_degistirince_stil_sayfasi_uygulanir(pencere):
    uygulama = QApplication.instance()
    assert uygulama.styleSheet() == "", "varsayilan temada stil sayfasi bos olmali"

    for ad, beklenen_renk in (
        ("fosfor_yesil", FOSFOR_YESIL.on_plan),
        ("fosfor_turuncu", FOSFOR_TURUNCU.on_plan),
    ):
        indeks = list(TEMALAR).index(ad)
        pencere.tema_secici.setCurrentIndex(indeks)
        assert pencere.tema.ad == ad
        qss = uygulama.styleSheet()
        assert beklenen_renk in qss
        # Rol stilleri de temadan gelmeli
        assert beklenen_renk in pencere.durdur_dugmesi.styleSheet()
        assert pencere.tema.parlak in pencere.eylem_etiketi.styleSheet()

    # Varsayilana donus stil sayfasini temizlemeli
    pencere.tema_secici.setCurrentIndex(list(TEMALAR).index("varsayilan"))
    assert uygulama.styleSheet() == ""


def test_tema_degisimi_akisi_bozmaz(pencere, kfg):
    """Tema degistirmek olcum akisini etkilememeli."""
    from merkezleme.duzeltme import yakinsama_durumu
    from merkezleme.is_akisi import Bekleme, Faz

    pencere.tema_secici.setCurrentIndex(list(TEMALAR).index("fosfor_yesil"))
    for adim in range(400):
        if pencere.akis.bitti_mi() or pencere.akis.bekleme is Bekleme.YOK:
            break
        if adim == 5:  # akisin ortasinda tema degistir
            pencere.tema_secici.setCurrentIndex(list(TEMALAR).index("fosfor_turuncu"))
        pencere._onayla()
    assert pencere.akis.faz is Faz.TAMAMLANDI, pencere.akis.durdurma_nedeni
    assert yakinsama_durumu(pencere.akis.son_y, kfg.duzeltme).yakinsadi


def test_canli_kipte_kip_etiketi_monokromda_ters_video(
    kfg, simulator_uret, akis_uret, monkeypatch, qt_uygulama
):
    """Canli kip monokrom temada da dikkat cekmeli (renk yerine ters video)."""
    from merkezleme.arayuz import MerkezlemePencere

    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Yes))
    canli_kfg = dataclasses.replace(
        kfg, genel=dataclasses.replace(kfg.genel, kip="canli", tema="fosfor_yesil")
    )
    sim = simulator_uret(ofset_m=complex(40e-6, 0), tohum=92)
    akis, _, _ = akis_uret(sim)
    p = MerkezlemePencere(canli_kfg, akis, deneme_kipi=True)
    try:
        stil = p.kip_etiketi.styleSheet()
        assert FOSFOR_YESIL.on_plan in stil and FOSFOR_YESIL.arka_plan in stil
        assert "bold" in stil
    finally:
        akis.kaynaklar.acil_sifirla()
        qt_uygulama.setStyleSheet("")
