"""Testler için ortak fixture'lar.

Bütün testler simülatör ve sahte güç kaynaklarıyla çalışır; donanım ya da elle
giriş gerekmez.
"""
from __future__ import annotations

import dataclasses
from pathlib import Path

import numpy as np
import pytest

from merkezleme.guc_kaynagi import KaynakGrubu, KomutGunlugu
from merkezleme.harmonikler import HarmonikKonvansiyonu
from merkezleme.is_akisi import IsAkisi
from merkezleme.kayit import Calistirma
from merkezleme.modlar import ModBazi
from merkezleme.olcum_kaynagi import SimulatorGirisi
from merkezleme.simulator import Simulator
from merkezleme.yapilandirma import Yapilandirma, yapilandirma_yukle

PROJE_KOKU = Path(__file__).resolve().parent.parent
YAPILANDIRMA_YOLU = PROJE_KOKU / "yapilandirma.yaml"


@pytest.fixture(scope="session")
def kfg() -> Yapilandirma:
    return yapilandirma_yukle(YAPILANDIRMA_YOLU)


@pytest.fixture(scope="session")
def qt_uygulama():
    """Bütün arayüz testlerinin paylaştığı QApplication.

    Session kapsamında tutulur: QApplication nesnesine referans kalmazsa
    çöplenip yok edilir ve sonrasında QWidget oluşturmak Qt'yi abort ettirir.
    PyQt5 kurulu değilse ilgili testler atlanır.
    """
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PyQt5", reason="PyQt5 kurulu değil")
    from PyQt5.QtWidgets import QApplication

    uygulama = QApplication.instance() or QApplication([])
    yield uygulama
    uygulama.setStyleSheet("")


@pytest.fixture
def konvansiyon(kfg: Yapilandirma) -> HarmonikKonvansiyonu:
    return HarmonikKonvansiyonu(kfg.harmonikler)


@pytest.fixture
def mod_bazi(kfg: Yapilandirma) -> ModBazi:
    return ModBazi(kfg.modlar, kfg.miknatis)


@pytest.fixture
def simulator_uret(kfg: Yapilandirma):
    """İstenen ofset/roll/arka plan ile simülatör üreten fabrika."""

    def uret(
        ofset_m: complex | None = None,
        roll_rad: float | None = None,
        arka_plan_T: complex | None = None,
        tohum: int = 1,
        **simulator_ayarlari,
    ) -> Simulator:
        """Simülatör üretir.

        `ofset_m`, `roll_rad` ve `arka_plan_T` verilmezse yapılandırmadaki
        değerler korunur (None). Açıkça 0 vermek "temiz durum" demektir.
        """
        ayar = (
            dataclasses.replace(kfg.simulator, **simulator_ayarlari)
            if simulator_ayarlari
            else kfg.simulator
        )
        sim = Simulator(ayar, kfg.miknatis, kfg.harmonikler, tohum=tohum)
        if ofset_m is not None:
            sim.ofset_m = ofset_m
        if roll_rad is not None:
            sim.roll_rad = roll_rad
        if arka_plan_T is not None:
            sim.arka_plan_T = arka_plan_T
        return sim

    return uret


@pytest.fixture
def temiz_simulator(simulator_uret):
    """Gürültüsüz, ofsetsiz, rollsüz, arka plansız simülatör (analitik kontroller için)."""
    return simulator_uret(
        ofset_m=0j, roll_rad=0.0, arka_plan_T=0j, harmonik_gurultu_bagil=0.0
    )


@pytest.fixture
def kaynak_grubu_uret(kfg: Yapilandirma):
    """Sahte (kuru çalışma) kaynak grubu üreten fabrika; beklemeler atlanır."""

    def uret(guvenlik=None) -> KaynakGrubu:
        return KaynakGrubu.olustur(
            kfg.guc_kaynaklari,
            guvenlik or kfg.guvenlik,
            canli=False,
            gunluk=KomutGunlugu(),
            bekle=lambda s: None,
        )

    return uret


@pytest.fixture
def akis_uret(kfg, konvansiyon, mod_bazi, kaynak_grubu_uret, tmp_path):
    """Simülatöre bağlı, tam kurulmuş bir IsAkisi üreten fabrika."""

    def uret(simulator: Simulator) -> tuple[IsAkisi, SimulatorGirisi, Calistirma]:
        kaynak = SimulatorGirisi(simulator)
        calistirma = Calistirma(kfg, kok=tmp_path)
        akis = IsAkisi(kfg, kaynak_grubu_uret(), kaynak, calistirma, konvansiyon, mod_bazi)
        return akis, kaynak, calistirma

    return uret


def kalibrasyonu_yurut(akis: IsAkisi, kaynak: SimulatorGirisi, max_adim: int = 200) -> None:
    """Kalibrasyon fazını otomatik tamamlar (düzeltme fazı başlar)."""
    from merkezleme.is_akisi import Bekleme, Faz

    akis.basla()
    for _ in range(max_adim):
        if akis.faz is not Faz.KALIBRASYON:
            return
        if akis.bekleme in (Bekleme.ARKA_PLAN_GIRISI, Bekleme.OLCUM_GIRISI):
            akis.olcum_gonder(kaynak.olcum_al(akis.mevcut_istek))
        else:  # pragma: no cover
            raise AssertionError(f"beklenmeyen bekleme: {akis.bekleme}")
    raise AssertionError("kalibrasyon tamamlanmadı")


def y_olc(
    simulator: Simulator,
    konvansiyon: HarmonikKonvansiyonu,
    akimlar: np.ndarray,
    gradyen_hedefi: float,
    arka_plan_cikar: bool = True,
):
    """Arka plan sırasını uygulayarak tek bir y ölçümü yapar."""
    arka_plan = simulator.olc(np.zeros(4)) if arka_plan_cikar else None
    olcum = simulator.olc(akimlar)
    net = konvansiyon.arka_plan_cikar(olcum, arka_plan)
    return konvansiyon.kontrol_vektoru(net, gradyen_hedefi)
