"""Merkezleme için minimal dönen bobin ölçüm penceresi.

    cd donen_bobin/host
    python merkezleme_olcer.py                      # ../merkezleme_olcer.yaml
    python merkezleme_olcer.py --parametreler P.yaml
    python merkezleme_olcer.py --basla              # açılınca bağlan, motoru başlat

Aynı anda depo kökünde `python -m merkezleme --dosyadan` (ya da
`--otomatik --dosyadan --canli`) çalışırken, ölçümler veri_kilidi/.kilit
üzerinden otomatik alışılır. İkisini birlikte açmanın kısa yolu depo
kökündeki `./merkezle` betiğidir.
"""
import argparse
import signal
import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from mgf.connection import MgfConnection
from mgf.data_engine import DataEngine
from mgf.merkezleme_koprusu import parametreleri_yukle
from mgf.merkezleme_penceresi import MerkezlemePenceresi


def main(argv: list[str] | None = None) -> int:
    ayristirici = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ayristirici.add_argument("--parametreler", default=None, help="parametre YAML dosyası")
    ayristirici.add_argument(
        "--basla", action="store_true", help="açılınca cihaza bağlan ve motoru başlat"
    )
    argumanlar = ayristirici.parse_args(argv)

    p = parametreleri_yukle(argumanlar.parametreler)
    uygulama = QApplication(sys.argv[:1])
    pencere = MerkezlemePenceresi(p, MgfConnection(p.ip, p.port), DataEngine())
    pencere.show()
    if argumanlar.basla:
        QTimer.singleShot(0, pencere.baglan_ve_baslat)
    # merkezle başlatıcısı işi bitince SIGTERM gönderir: pencereyi kapatmak gibi
    # davran (motor yavaşlatılıp durdurulur). İşleyici, pencerenin 50 ms'lik
    # zamanlayıcısı Python'a döndükçe çalışır.
    signal.signal(signal.SIGTERM, lambda *_: pencere.close())
    return uygulama.exec()


if __name__ == "__main__":
    raise SystemExit(main())
