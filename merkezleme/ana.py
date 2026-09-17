"""Komut satiri girisi: `python -m merkezleme`.

    python -m merkezleme                      kuru calisma, elle giris (varsayilan)
    python -m merkezleme --canli               GERCEK DONANIM (acik bayrak gerekir)
    python -m merkezleme --deneme              deneme kipi: alanlar simulatorden dolar
    python -m merkezleme --devam               yarim kalmis son calistirmadan devam
    python -m merkezleme --kalibrasyon D.json  kayitli kalibrasyonu yukle, faz 1'i atla
    python -m merkezleme --otomatik            arayuzsuz: simulatorle bastan sona kosar

Varsayilan kip KURU CALISMADIR: SCPI komutlari kaydedilir ama cihaza
gonderilmez. Gercek donanim icin `--canli` zorunludur.
"""
from __future__ import annotations

import argparse
import dataclasses
import sys
from pathlib import Path

from .guc_kaynagi import KaynakGrubu, KomutGunlugu
from .harmonikler import HarmonikKonvansiyonu
from .is_akisi import IsAkisi, otomatik_yurut
from .kalibrasyon import KalibrasyonSonucu
from .kayit import Calistirma
from .modlar import ModBazi
from .olcum_kaynagi import ElleGiris, SimulatorGirisi
from .simulator import Simulator
from .yapilandirma import Yapilandirma, yapilandirma_yukle

VARSAYILAN_YAPILANDIRMA = "yapilandirma.yaml"


def arguman_ayristirici() -> argparse.ArgumentParser:
    ayristirici = argparse.ArgumentParser(
        prog="merkezleme",
        description="pEDM air-core kuadrupol - elektriksel merkezleme",
    )
    ayristirici.add_argument(
        "--yapilandirma", default=VARSAYILAN_YAPILANDIRMA, help="YAML yapilandirma dosyasi"
    )
    ayristirici.add_argument(
        "--canli",
        action="store_true",
        help="GERCEK DONANIM: SCPI komutlari cihazlara gonderilir (varsayilan kuru calisma)",
    )
    ayristirici.add_argument(
        "--deneme",
        action="store_true",
        help="Deneme kipi: olcum alanlari simulatorden otomatik doldurulur",
    )
    ayristirici.add_argument(
        "--devam", action="store_true", help="Yarim kalmis son calistirmadan devam et"
    )
    ayristirici.add_argument(
        "--kalibrasyon", default=None, help="Kayitli kalibrasyon JSON dosyasi (faz 1 atlanir)"
    )
    ayristirici.add_argument(
        "--tema",
        default=None,
        help="Arayuz temasi: varsayilan | fosfor_yesil | fosfor_turuncu "
        "(yapilandirmadaki degeri gecersiz kilar)",
    )
    ayristirici.add_argument(
        "--otomatik",
        action="store_true",
        help="Arayuzsuz calis: olcumler simulatorden alinir, akis bastan sona kosar",
    )
    return ayristirici


def _kaynak_grubu_kur(
    kfg: Yapilandirma, canli: bool, gunluk: KomutGunlugu, bekle: object | None
) -> KaynakGrubu:
    if bekle is None:
        return KaynakGrubu.olustur(kfg.guc_kaynaklari, kfg.guvenlik, canli=canli, gunluk=gunluk)
    return KaynakGrubu.olustur(
        kfg.guc_kaynaklari, kfg.guvenlik, canli=canli, gunluk=gunluk, bekle=bekle  # type: ignore[arg-type]
    )


def calistir(argumanlar: argparse.Namespace) -> int:
    kfg = yapilandirma_yukle(argumanlar.yapilandirma)

    # Guvenlik: gercek donanim yalnizca acik bayrakla.
    canli = bool(argumanlar.canli)
    if kfg.genel.kip == "canli" and not canli:
        print(
            "Yapilandirmada kip 'canli' ama --canli bayragi verilmedi; "
            "kuru calismada devam ediliyor.",
            file=sys.stderr,
        )
    if canli and argumanlar.deneme:
        print("--canli ve --deneme birlikte kullanilamaz.", file=sys.stderr)
        return 2
    if canli and argumanlar.otomatik:
        print("--canli ve --otomatik birlikte kullanilamaz.", file=sys.stderr)
        return 2

    if argumanlar.tema:
        from .tema import TEMALAR

        if argumanlar.tema not in TEMALAR:
            print(
                f"Bilinmeyen tema: {argumanlar.tema}; secenekler: {', '.join(TEMALAR)}",
                file=sys.stderr,
            )
            return 2
        kfg = dataclasses.replace(
            kfg, genel=dataclasses.replace(kfg.genel, tema=argumanlar.tema)
        )

    konvansiyon = HarmonikKonvansiyonu(kfg.harmonikler)
    mod_bazi = ModBazi(kfg.modlar, kfg.miknatis)

    # Olcum kaynagi: elle giris ya da simulator
    simulatorlu = argumanlar.deneme or argumanlar.otomatik
    if simulatorlu:
        simulator = Simulator(kfg.simulator, kfg.miknatis, kfg.harmonikler)
        olcum_kaynagi: object = SimulatorGirisi(simulator)
    else:
        olcum_kaynagi = ElleGiris()

    gunluk = KomutGunlugu()

    # Arayuzsuz otomatik kosu
    if argumanlar.otomatik:
        grup = _kaynak_grubu_kur(kfg, canli=False, gunluk=gunluk, bekle=lambda s: None)
        calistirma = Calistirma(kfg)
        akis = IsAkisi(kfg, grup, olcum_kaynagi, calistirma, konvansiyon, mod_bazi)  # type: ignore[arg-type]
        if argumanlar.kalibrasyon:
            akis.kalibrasyonu_yukle(KalibrasyonSonucu.yukle(argumanlar.kalibrasyon))
        akis.basla()
        otomatik_yurut(akis, olcum_kaynagi)  # type: ignore[arg-type]
        ozet = akis.ozeti_yaz()
        print(f"Akis tamamlandi: faz={akis.faz.value}, iterasyon={akis.iterasyon}")
        if akis.son_y is not None:
            print(f"Son durum: {akis.son_y}")
        print(f"Cikti klasoru: {calistirma.dizin}")
        print(f"Ozet: {ozet}")
        return 0

    # Arayuzlu kosu
    from PyQt5.QtWidgets import QApplication

    from .arayuz import MerkezlemePencere, qt_bekle

    uygulama = QApplication(sys.argv[:1])
    grup = _kaynak_grubu_kur(kfg, canli=canli, gunluk=gunluk, bekle=qt_bekle)

    devam_durumu = None
    calistirma: Calistirma
    if argumanlar.devam:
        durum_yolu = Calistirma.yarim_calistirma_bul(
            kfg.genel.calistirma_kok_dizini, kfg.genel.durum_dosyasi_adi
        )
        if durum_yolu is None:
            print("Yarim kalmis calistirma bulunamadi; yeni calistirma baslatiliyor.")
            calistirma = Calistirma(kfg)
        else:
            print(f"Yarim kalmis calistirmadan devam ediliyor: {durum_yolu.parent}")
            calistirma = Calistirma(kfg)
            import json

            with durum_yolu.open(encoding="utf-8") as f:
                devam_durumu = json.load(f)
    else:
        calistirma = Calistirma(kfg)

    akis = IsAkisi(kfg, grup, olcum_kaynagi, calistirma, konvansiyon, mod_bazi)  # type: ignore[arg-type]
    if argumanlar.kalibrasyon:
        akis.kalibrasyonu_yukle(KalibrasyonSonucu.yukle(argumanlar.kalibrasyon))

    if devam_durumu is not None:
        akis.durumu_uygula(devam_durumu)
    pencere = MerkezlemePencere(
        kfg,
        akis,
        deneme_kipi=bool(argumanlar.deneme),
        devam=devam_durumu is not None,
    )

    print(f"Cikti klasoru: {calistirma.dizin}")
    pencere.resize(980, 900)
    pencere.show()
    return int(uygulama.exec_())


def main(argv: list[str] | None = None) -> int:
    argumanlar = arguman_ayristirici().parse_args(argv)
    return calistir(argumanlar)


if __name__ == "__main__":
    raise SystemExit(main())
