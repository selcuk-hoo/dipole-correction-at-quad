"""Merkezleme için minimal dönen bobin ölçüm penceresi.

    cd donen_bobin_surum_24_eylul_2026/host
    python merkezleme_olcer.py                      # ../merkezleme_olcer.yaml
    python merkezleme_olcer.py --parametreler P.yaml

Aynı anda depo kökünde `python -m merkezleme --dosyadan` (ya da
`--otomatik --dosyadan --canli`) çalışırken, ölçümler veri_kilidi/.kilit
üzerinden otomatik alışılır.
"""
import argparse
import sys

from PySide6.QtWidgets import QApplication

from mgf.connection import MgfConnection
from mgf.data_engine import DataEngine
from mgf.merkezleme_koprusu import parametreleri_yukle
from mgf.merkezleme_penceresi import MerkezlemePenceresi


def main(argv: list[str] | None = None) -> int:
    ayristirici = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ayristirici.add_argument("--parametreler", default=None, help="parametre YAML dosyası")
    argumanlar = ayristirici.parse_args(argv)

    p = parametreleri_yukle(argumanlar.parametreler)
    uygulama = QApplication(sys.argv[:1])
    pencere = MerkezlemePenceresi(p, MgfConnection(p.ip, p.port), DataEngine())
    pencere.show()
    return uygulama.exec()


if __name__ == "__main__":
    raise SystemExit(main())
