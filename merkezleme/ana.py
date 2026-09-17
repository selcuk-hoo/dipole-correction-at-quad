"""Komut satırı girişi: `python -m merkezleme`.

    python -m merkezleme                      kuru çalışma, elle giriş (varsayılan)
    python -m merkezleme --canli               GERÇEK DONANIM (açık bayrak gerekir)
    python -m merkezleme --deneme              deneme kipi: alanlar simülatörden dolar
    python -m merkezleme --devam               yarım kalmış son çalıştırmadan devam
    python -m merkezleme --kalibrasyon D.json  kayıtlı kalibrasyonu yükle, faz 1'i atla
    python -m merkezleme --otomatik            arayüzsüz: simülatörle baştan sona koşar

Varsayılan kip KURU ÇALIŞMADIR: SCPI komutları kaydedilir ama cihaza
gönderilmez. Gerçek donanım için `--canli` zorunludur.
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
        "--yapilandirma", default=VARSAYILAN_YAPILANDIRMA, help="YAML yapılandırma dosyası"
    )
    ayristirici.add_argument(
        "--canli",
        action="store_true",
        help="GERÇEK DONANIM: SCPI komutları cihazlara gönderilir (varsayılan kuru çalışma)",
    )
    ayristirici.add_argument(
        "--deneme",
        action="store_true",
        help="Deneme kipi: ölçüm alanları simülatörden otomatik doldurulur",
    )
    ayristirici.add_argument(
        "--devam", action="store_true", help="Yarım kalmış son çalıştırmadan devam et"
    )
    ayristirici.add_argument(
        "--kalibrasyon", default=None, help="Kayıtlı kalibrasyon JSON dosyası (faz 1 atlanır)"
    )
    ayristirici.add_argument(
        "--tema",
        default=None,
        help="Arayüz teması: varsayilan | fosfor_yesil | fosfor_turuncu "
        "(yapılandırmadaki değeri geçersiz kılar)",
    )
    ayristirici.add_argument(
        "--otomatik",
        action="store_true",
        help="Arayüzsüz çalış: ölçümler simülatörden alınır, akış baştan sona koşar",
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

    # Güvenlik: gerçek donanım yalnızca açık bayrakla.
    canli = bool(argumanlar.canli)
    if kfg.genel.kip == "canli" and not canli:
        print(
            "Yapılandırmada kip 'canli' ama --canli bayrağı verilmedi; "
            "kuru çalışmada devam ediliyor.",
            file=sys.stderr,
        )
    if canli and argumanlar.deneme:
        print("--canli ve --deneme birlikte kullanılamaz.", file=sys.stderr)
        return 2
    if canli and argumanlar.otomatik:
        print("--canli ve --otomatik birlikte kullanılamaz.", file=sys.stderr)
        return 2

    if argumanlar.tema:
        from .tema import TEMALAR

        if argumanlar.tema not in TEMALAR:
            print(
                f"Bilinmeyen tema: {argumanlar.tema}; seçenekler: {', '.join(TEMALAR)}",
                file=sys.stderr,
            )
            return 2
        kfg = dataclasses.replace(
            kfg, genel=dataclasses.replace(kfg.genel, tema=argumanlar.tema)
        )

    konvansiyon = HarmonikKonvansiyonu(kfg.harmonikler)
    mod_bazi = ModBazi(kfg.modlar, kfg.miknatis)

    # Ölçüm kaynağı: elle giriş ya da simülatör
    simulatorlu = argumanlar.deneme or argumanlar.otomatik
    if simulatorlu:
        simulator = Simulator(kfg.simulator, kfg.miknatis, kfg.harmonikler)
        olcum_kaynagi: object = SimulatorGirisi(simulator)
    else:
        olcum_kaynagi = ElleGiris()

    gunluk = KomutGunlugu()

    # Arayüzsüz otomatik koşu
    if argumanlar.otomatik:
        grup = _kaynak_grubu_kur(kfg, canli=False, gunluk=gunluk, bekle=lambda s: None)
        calistirma = Calistirma(kfg)
        akis = IsAkisi(kfg, grup, olcum_kaynagi, calistirma, konvansiyon, mod_bazi)  # type: ignore[arg-type]
        if argumanlar.kalibrasyon:
            akis.kalibrasyonu_yukle(KalibrasyonSonucu.yukle(argumanlar.kalibrasyon))
        akis.basla()
        otomatik_yurut(akis, olcum_kaynagi)  # type: ignore[arg-type]
        ozet = akis.ozeti_yaz()
        print(f"Akış tamamlandı: faz={akis.faz.value}, iterasyon={akis.iterasyon}")
        if akis.son_y is not None:
            print(f"Son durum: {akis.son_y}")
        print(f"Çıktı klasörü: {calistirma.dizin}")
        print(f"Özet: {ozet}")
        return 0

    # Arayüzlü koşu
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
            print("Yarım kalmış çalıştırma bulunamadı; yeni çalıştırma başlatılıyor.")
            calistirma = Calistirma(kfg)
        else:
            print(f"Yarım kalmış çalıştırmadan devam ediliyor: {durum_yolu.parent}")
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

    print(f"Çıktı klasörü: {calistirma.dizin}")
    pencere.resize(980, 900)
    pencere.show()
    return int(uygulama.exec_())


def main(argv: list[str] | None = None) -> int:
    argumanlar = arguman_ayristirici().parse_args(argv)
    return calistir(argumanlar)


if __name__ == "__main__":
    raise SystemExit(main())
