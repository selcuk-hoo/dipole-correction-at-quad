"""Birleşik arayüzü ekransız ve otomatik süren donanım testi.

    python3 -m merkezleme.arayuz_testi --kalibrasyon son --akimlardan --izleme-dk 10 --bekci

Arayüzün kendi kodunu kullanır (MerkezlemeSekmesi, KararlilikSekmesi, dönen bobin
penceresi); düğmelere basan bir kullanıcı gibi davranır, soru pencerelerine "Evet"
der ve hepsini günlüğe yazar. Sıra:
  1. Pico'ya bağlan, motoru `--hiz` Hz'de başlat, hız oturana kadar bekle.
  2. Merkezleme: `--kalibrasyon yeni` ya da kayıtlı bir çalıştırma (`son` = en
     yenisi, ya da klasör adı); `--akimlardan` ile o çalıştırmanın son akımlarından.
     Otomatik kipte sonuna kadar.
  3. `--izleme-dk` dakika kararlılık izleme (0: atla).
  4. `--bekci`: izleme sürerken motoru durdur, bekçinin uyarısını (ve Telegram'ı) bekle.
  5. Akımları rampa ile sıfırla, çıkışları kapat, motoru durdur, bağlantıyı kes.
Herhangi bir hata, SIGTERM ya da zaman aşımında 5. adım yapılır.
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
HOST = KOK / "donen_bobin" / "host"


def main(argv: list[str] | None = None) -> int:
    a = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    a.add_argument("--kalibrasyon", default="son", help="'yeni', 'son' ya da çalıştırma klasörü adı")
    a.add_argument("--akimlardan", action="store_true", help="kayıtlı çalıştırmanın son akımlarından başla")
    a.add_argument("--izleme-dk", type=float, default=10.0)
    a.add_argument("--bekci", action="store_true", help="izlemede motoru durdurup bekçiyi sına")
    a.add_argument("--hiz", type=float, default=8.0)
    a.add_argument("--olcum-suresi", type=float, default=None,
                   help="dönen bobinin her ölçümde kullandığı veri süresi (s); verilmezse parametre dosyası")
    a.add_argument("--zaman-asimi-dk", type=float, default=40.0)
    g = a.parse_args(argv)

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.chdir(KOK)
    sys.path.insert(0, str(HOST))
    from PySide6.QtWidgets import QApplication, QMessageBox

    from mgf.connection import MgfConnection
    from mgf.data_engine import DataEngine
    from mgf.merkezleme_koprusu import parametreleri_yukle
    from mgf.merkezleme_penceresi import MerkezlemePenceresi
    from mgf.olcum_dongusu import Durum

    from .arayuz import qt_bekle
    from .birlesik import BirlesikPencere, MerkezlemeSekmesi, bobin_durumu, telegram_bildir
    from .yapilandirma import yapilandirma_yukle

    gunluk_yolu = KOK / "kayitlar" / f"arayuz_testi_{datetime.now():%Y-%m-%d_%H%M%S}.log"
    gunluk_yolu.parent.mkdir(exist_ok=True)

    def yaz(m: str) -> None:
        satir = f"{datetime.now():%H:%M:%S}  {m}"
        print(satir, flush=True)
        with gunluk_yolu.open("a", encoding="utf-8") as f:
            f.write(satir + "\n")

    # Soru pencereleri ekransız çalışmada bloklar: yanıtla ve günlüğe yaz
    def soru(*args, **_):
        yaz(f"[soru, Evet denildi] {args[1] if len(args) > 1 else ''}: {str(args[2] if len(args) > 2 else '')[:300]}")
        return QMessageBox.StandardButton.Yes

    def bilgi(tur):
        return lambda *args, **_: yaz(f"[{tur}] {args[1] if len(args) > 1 else ''}: "
                                      f"{str(args[2] if len(args) > 2 else '')[:500]}")
    QMessageBox.question = staticmethod(soru)
    QMessageBox.information = staticmethod(bilgi("bilgi"))
    QMessageBox.warning = staticmethod(bilgi("UYARI"))
    QMessageBox.critical = staticmethod(bilgi("HATA"))

    kfg = yapilandirma_yukle(KOK / "yapilandirma.yaml")
    p = parametreleri_yukle(None)
    uygulama = QApplication(sys.argv[:1])
    bobin = MerkezlemePenceresi(p, MgfConnection(p.ip, p.port), DataEngine())
    sekme = MerkezlemeSekmesi(kfg, True, lambda: bobin_durumu(bobin.dongu),
                              merkezleme_acilinca=lambda: bobin._temayi_uygula(bobin.tema))
    pencere = BirlesikPencere(bobin, sekme)
    pencere.onaysiz_kapat = True
    pencere.show()
    baslangic = time.monotonic()
    iptal = {"neden": None}
    signal.signal(signal.SIGTERM, lambda *_: iptal.update(neden="SIGTERM"))

    def bekle_kosul(kosul, en_fazla_s: float, ad: str) -> bool:
        bitis = time.monotonic() + en_fazla_s
        while time.monotonic() < bitis:
            if iptal["neden"]:
                raise RuntimeError(f"iptal: {iptal['neden']}")
            if time.monotonic() - baslangic > g.zaman_asimi_dk * 60:
                raise RuntimeError("genel zaman aşımı")
            if kosul():
                return True
            qt_bekle(0.2)
        yaz(f"ZAMAN AŞIMI: {ad} ({en_fazla_s:.0f} s)")
        return False

    sonuc: dict = {"gunluk": str(gunluk_yolu)}
    try:
        # 1. Bağlan ve motoru başlat
        yaz("Pico'ya bağlanılıyor...")
        bobin.baglan()
        if not bekle_kosul(lambda: bobin.dongu.durum is not Durum.BAGLI_DEGIL, 20, "bağlantı"):
            raise RuntimeError("Pico'ya bağlanılamadı")
        bobin.hiz.setValue(g.hiz)
        if g.olcum_suresi:
            bobin.sure.setValue(g.olcum_suresi)
            bobin.dongu.pencere_ayarla(g.olcum_suresi)
            yaz(f"Ölçüm süresi: {g.olcum_suresi:g} s")
        bobin._baslat()
        yaz(f"Motor başlatıldı ({g.hiz:g} Hz); dönen bobin hazır olana kadar bekleniyor...")
        if not bekle_kosul(lambda: bobin_durumu(bobin.dongu)[0], 120, "dönen bobin hazır"):
            raise RuntimeError("dönen bobin hazır olmadı: " + bobin_durumu(bobin.dongu)[1])
        yaz("Dönen bobin: " + bobin_durumu(bobin.dongu)[1])

        # 2. Merkezleme
        if g.kalibrasyon != "yeni":
            hedef = None
            for i, k in enumerate(sekme.kayitlilar):
                if g.kalibrasyon == "son" or k.dosya.parent.name == g.kalibrasyon:
                    hedef = i
                    break
            if hedef is None:
                raise RuntimeError(f"kayıtlı kalibrasyon bulunamadı: {g.kalibrasyon}")
            sekme.kalibrasyon_secici.setCurrentIndex(hedef + 1)
            sekme.akimdan_basla.setChecked(g.akimlardan and sekme.akimdan_basla.isEnabled())
            yaz(f"Kalibrasyon: {sekme.kayitlilar[hedef].etiket}; son akımlardan: "
                f"{sekme.akimdan_basla.isChecked()}")
        sekme.otomatik_kutusu.setChecked(True)
        sekme.baslat()
        if sekme.pencere is None:
            raise RuntimeError("merkezleme başlatılamadı")
        akis = sekme.pencere.akis
        yaz(f"Merkezleme başladı: {akis.calistirma.dizin}")
        bekle_kosul(akis.bitti_mi, 20 * 60, "merkezleme")
        sonuc.update(faz=akis.faz.value, yakinsadi=akis.yakinsadi, iterasyon=akis.iterasyon,
                     adim=akis.adim_no, calistirma=str(akis.calistirma.dizin),
                     yon_dogrulama=akis.yon_sonucu, durdurma_nedeni=akis.durdurma_nedeni,
                     gradyen_hedefi_T_m=akis.gradyen_hedefi_T_m,
                     akimlar_A=[float(x) for x in akis.mevcut_akimlar_A])
        if akis.son_y is not None:
            sonuc["son_merkez_um"] = [akis.son_y.x_c * 1e6, akis.son_y.y_c * 1e6]
        for n in akis.notlar:
            yaz("not: " + n)
        yaz("Merkezleme sonucu: " + json.dumps(sonuc, ensure_ascii=False, default=str))
        telegram_bildir("Merkezleme testi bitti",
                        f"faz {akis.faz.value}, yakınsadı {akis.yakinsadi}, {akis.iterasyon} iterasyon, "
                        f"{akis.adim_no} adım. Merkez: {sonuc.get('son_merkez_um')}")

        # 3. İzleme
        izleme = pencere.kararlilik
        if g.izleme_dk > 0 and akis.faz.value == "tamamlandi" and izleme is not None:
            izleme.baslat()
            yaz(f"İzleme başladı: {izleme._csv}")
            bekle_kosul(lambda: False, g.izleme_dk * 60, "izleme (beklenen)")
            yaz("İzleme özeti: " + izleme.ozet.text())
            sonuc["izleme_csv"] = str(izleme._csv)
            # 4. Bekçi
            if g.bekci:
                yaz("Bekçi testi: motor durduruluyor, akımlar açık kalıyor...")
                bobin.dongu.durdur()
                bekle_kosul(lambda: izleme._olcum_yok_bildirildi, 120, "bekçi uyarısı")
                sonuc["bekci_uyardi"] = izleme._olcum_yok_bildirildi
                yaz(f"Bekçi uyardı: {izleme._olcum_yok_bildirildi}; özet: {izleme.ozet.text()}")
            izleme.durdur()
    except Exception as hata:  # noqa: BLE001
        sonuc["hata"] = repr(hata)
        yaz("HATA: " + "".join(traceback.format_exception(hata)))
    finally:
        # 5. Güvenli kapanış: akımlar rampa ile sıfır, çıkışlar kapalı, motor durur
        yaz("Kapanış: akımlar sıfırlanıyor, motor durduruluyor...")
        try:
            sekme.kapat()
        except Exception as hata:  # noqa: BLE001
            yaz(f"Kapanışta hata: {hata!r}")
        try:
            if bobin.dongu.donuyor:
                bobin.dongu.durdur()
                qt_bekle(6)
            pencere.close()
        except Exception as hata:  # noqa: BLE001
            yaz(f"Bobin kapanışında hata: {hata!r}")
        yaz("Bitti. Sonuç: " + json.dumps(sonuc, ensure_ascii=False, default=str))
        (gunluk_yolu.with_suffix(".json")).write_text(json.dumps(sonuc, ensure_ascii=False, indent=2,
                                                                  default=str), encoding="utf-8")
        uygulama.quit()
    return 0 if "hata" not in sonuc else 1


if __name__ == "__main__":
    raise SystemExit(main())
