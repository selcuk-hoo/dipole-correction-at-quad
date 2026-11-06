"""Kanal testi: dört ADC kanalının hangisi düz (kuadrupolü gören) bobin?

    ./merkezle kanal_testi            (depo kökünden; önerilen yol)
    cd donen_bobin/host && python kanal_testi.py [--akim 9.5] [--tekrar 3] [--pencere 4]

Pencere açmadan dönen bobini başlatır (8 Hz) ve üç akım durumunda dört kanalın
hepsinde ölçer: akım 0 (arka plan), dört bobin EŞİT `--akim` A, yeniden 0
(sürüklenme kontrolü). Eşit akımda doğru bir kuadrupol neredeyse saf
kuadrupol verir; düz bobin kanalında G ≈ 0.1 T/m × akım/10 A görünmelidir.
Akımlar merkezleme'nin sürücüsüyle rampa ile değiştirilir; her hata ve
Ctrl+C'de rampa ile sıfıra inilir, çıkışlar kapatılır, motor durdurulur.

Sonuçlar dönen bobin oturum klasörüne (kayitlar/<tarih_saat>/) gider: her
ölçümün ham verisi, olcumler.csv, gunluk.txt ve özet kanal_testi.csv.
"""
from __future__ import annotations

import argparse
import csv
import math
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

import numpy as np

KOK = Path(__file__).resolve().parents[2]
if str(KOK) not in sys.path:
    sys.path.insert(0, str(KOK))  # merkezleme paketi (güç kaynakları)

from mgf.merkezleme_koprusu import OlcumSonucu, Parametreler, parametreleri_yukle  # noqa: E402
from mgf.olcum_dongusu import KANAL_GECIS_S, Durum, OlcumDongusu  # noqa: E402

BEKLENEN_G_10A_T_m = 0.1  # kullanıcı: 10 A'da kabaca 0.1 T/m
TICK_S = 0.05


class KanalTestiHatasi(RuntimeError):
    pass


@dataclass
class Sonuclar:
    """(durum etiketi, kanal) -> ölçümler"""

    olcumler: dict[tuple[str, str], list[OlcumSonucu]] = field(default_factory=dict)

    def ekle(self, durum: str, kanal: str, s: OlcumSonucu) -> None:
        self.olcumler.setdefault((durum, kanal), []).append(s)

    def ortalama(self, durum: str, kanal: str) -> np.ndarray:
        return np.mean([s.harmonikler for s in self.olcumler[(durum, kanal)]], axis=0)

    def sacilim(self, durum: str, kanal: str) -> np.ndarray:
        c = np.array([s.harmonikler for s in self.olcumler[(durum, kanal)]])
        return np.abs(c - c.mean(axis=0)).max(axis=0) if len(c) > 1 else np.zeros(c.shape[1])


class KanalTesti:
    def __init__(
        self,
        p: Parametreler,
        dongu: OlcumDongusu,
        grup,
        akim_A: float,
        tekrar: int = 3,
        pencere_s: float = 4.0,
        bekle: Callable[[float], None] = time.sleep,
        saat: Callable[[], float] = time.monotonic,
        yaz: Callable[[str], None] = print,
    ) -> None:
        self.p, self.dongu, self.grup = p, dongu, grup
        self.akim_A, self.tekrar, self.pencere_s = akim_A, tekrar, pencere_s
        self.bekle, self.saat, self.yaz = bekle, saat, yaz
        self.sonuclar = Sonuclar()
        self.kanallar = list(p.kanallar)

    # ------------------------------------------------------------------
    def _tick_bekle(self, kosul: Callable[[], bool], zaman_asimi_s: float, ne: str) -> None:
        bitis = self.saat() + zaman_asimi_s
        while not kosul():
            if self.saat() > bitis:
                raise KanalTestiHatasi(f"{ne}: {zaman_asimi_s:.0f} s içinde olmadı")
            if self.dongu.durum is Durum.HATA:
                raise KanalTestiHatasi(f"{ne} beklenirken dönen bobin hatası: {self.dongu.hata_metni}")
            self.dongu.tick()
            self.bekle(TICK_S)

    def _sure(self, saniye: float) -> None:
        t = self.saat() + saniye
        self._tick_bekle(lambda: self.saat() >= t, saniye + 5, "bekleme")

    def _olc(self) -> OlcumSonucu:
        d = self.dongu
        once = d.son_sonuc_zamani
        d.tek_olcum()
        self._tick_bekle(
            lambda: d._tek_istek is None, self.pencere_s * 3 + 10, "tek ölçüm"
        )
        if d.son_sonuc_zamani is once or d.son_sonuc is None:
            raise KanalTestiHatasi("tek ölçüm hesaplanamadı (günlüğe bakın)")
        return d.son_sonuc

    def _durum_olc(self, etiket: str) -> None:
        for kanal in self.kanallar:
            if not self.dongu.kanal_sec(kanal):
                raise KanalTestiHatasi(f"kanal seçilemedi: {kanal}")
            self._sure(2 * KANAL_GECIS_S)  # eski kanalın örnekleri geçsin
            for _ in range(self.tekrar):
                s = self._olc()
                self.sonuclar.ekle(etiket, kanal, s)
            c = self.sonuclar.ortalama(etiket, kanal)
            self.yaz(f"  {etiket:>8s}  {kanal:40s} |C1| = {abs(c[0]) * 1e6:9.1f} µT   |C2| = {abs(c[1]) * 1e6:9.1f} µT")

    # ------------------------------------------------------------------
    def calistir(self) -> Sonuclar:
        d = self.dongu
        d.otomatik_yaz_ayarla(False)  # kilide yazma; kanal değiştirebilmek için
        d.pencere_ayarla(self.pencere_s)
        self.yaz(f"Motor başlatılıyor ({d.hedef_hiz_hz:g} Hz)...")
        d.baslat()
        self._tick_bekle(lambda: d.durum is Durum.DONUYOR, 60, "motor hızının oturması")

        self.yaz("1/3  akım 0 (arka plan)")
        self._durum_olc("0 A")
        self.yaz(f"2/3  dört bobin {self.akim_A:g} A (rampa)")
        self.grup.rampala(np.full(4, self.akim_A))
        self._durum_olc(f"{self.akim_A:g} A")
        self.yaz("3/3  akım 0 (rampa; sürüklenme kontrolü)")
        self.grup.rampala(np.zeros(4))
        self._durum_olc("0 A son")
        return self.sonuclar

    # ------------------------------------------------------------------
    def rapor(self) -> list[dict[str, object]]:
        r_ref = self.p.r_ref_m
        etiket = f"{self.akim_A:g} A"
        beklenen_G = BEKLENEN_G_10A_T_m * self.akim_A / 10.0
        satirlar = []
        for kanal in self.kanallar:
            arka = 0.5 * (self.sonuclar.ortalama("0 A", kanal) + self.sonuclar.ortalama("0 A son", kanal))
            net = self.sonuclar.ortalama(etiket, kanal) - arka
            kayma = self.sonuclar.ortalama("0 A son", kanal) - self.sonuclar.ortalama("0 A", kanal)
            G = abs(net[1]) / r_ref
            satirlar.append({
                "kanal": kanal,
                "arka_plan_C1_uT": abs(arka[0]) * 1e6,
                "arka_plan_kaymasi_C1_uT": abs(kayma[0]) * 1e6,
                "net_C1_mT": abs(net[0]) * 1e3,
                "net_C2_mT": abs(net[1]) * 1e3,
                "net_C3_mT": abs(net[2]) * 1e3,
                "G_T_m": G,
                "G_beklenene_orani": G / beklenen_G,
                "dipol_kuad_orani": abs(net[0]) / abs(net[1]) if abs(net[1]) > 0 else math.inf,
                "C2_sacilimi_uT": float(self.sonuclar.sacilim(etiket, kanal)[1]) * 1e6,
            })
        return satirlar

    def raporu_yaz(self, satirlar: list[dict[str, object]]) -> Path:
        self.yaz("")
        self.yaz(f"ÖZET (dört bobin {self.akim_A:g} A, arka plan çıkarılmış; beklenen G ≈ "
                 f"{BEKLENEN_G_10A_T_m * self.akim_A / 10:.4f} T/m)")
        self.yaz(f"  {'kanal':40s} {'G (T/m)':>9s} {'G/bekl.':>8s} {'kuad mT':>8s} {'dipol mT':>9s} {'dipol/kuad':>10s} {'ortam µT':>9s}")
        for s in satirlar:
            self.yaz(f"  {s['kanal']:40s} {s['G_T_m']:9.4f} {s['G_beklenene_orani']:8.2f} {s['net_C2_mT']:8.3f} "
                     f"{s['net_C1_mT']:9.3f} {s['dipol_kuad_orani']:10.2f} {s['arka_plan_C1_uT']:9.1f}")
        self.yaz("  (Değerler düz bobin geometrisiyle ölçeklenmiştir; başka tip bir bobinin değerleri yalnızca "
                 "göreli karşılaştırma içindir.)")
        yol = self.dongu.oturum.klasor() / "kanal_testi.csv"
        with open(yol, "w", newline="", encoding="utf-8") as f:
            yazici = csv.DictWriter(f, fieldnames=list(satirlar[0]))
            yazici.writeheader()
            for s in satirlar:
                yazici.writerow({k: (f"{v:.6g}" if isinstance(v, float) else v) for k, v in s.items()})
        self.yaz(f"Kayıtlar: {yol.parent}")
        return yol


# ---------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    ayristirici = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ayristirici.add_argument("--akim", type=float, default=9.5, help="dört bobine eşit akım (A)")
    ayristirici.add_argument("--tekrar", type=int, default=3, help="kanal ve durum başına ölçüm")
    ayristirici.add_argument("--pencere", type=float, default=4.0, help="ölçüm süresi (s)")
    ayristirici.add_argument("--parametreler", default=None)
    ayristirici.add_argument("--yapilandirma", default=str(KOK / "yapilandirma.yaml"))
    a = ayristirici.parse_args(argv)

    from merkezleme.guc_kaynagi import KaynakGrubu, KomutGunlugu
    from merkezleme.yapilandirma import yapilandirma_yukle
    from mgf.connection import MgfConnection
    from mgf.data_engine import DataEngine

    p = parametreleri_yukle(a.parametreler)
    kfg = yapilandirma_yukle(a.yapilandirma)
    if not 0 < a.akim <= kfg.guvenlik.bobin_basi_max_akim_A:
        print(f"--akim 0 ile {kfg.guvenlik.bobin_basi_max_akim_A} A arasında olmalı", file=sys.stderr)
        return 2

    def gunluk(m: str) -> None:
        print(f"{datetime.now():%H:%M:%S}  {m}")

    dongu = OlcumDongusu(p, MgfConnection(p.ip, p.port), DataEngine(), gunluk=gunluk)
    if not dongu.baglan():
        print("Pico'ya bağlanılamadı.", file=sys.stderr)
        return 1
    scpi = KomutGunlugu()
    grup = KaynakGrubu.olustur(kfg.guc_kaynaklari, kfg.guvenlik, canli=True, gunluk=scpi)
    test = KanalTesti(p, dongu, grup, a.akim, a.tekrar, a.pencere)
    kod = 0
    try:
        grup.baslat()
        test.calistir()
        test.raporu_yaz(test.rapor())
    except (Exception, KeyboardInterrupt) as hata:
        print(f"\nHATA: {hata!r}; akımlar rampa ile sıfıra indiriliyor.", file=sys.stderr)
        kod = 1
    finally:
        try:
            grup.guvenli_kapat()
        except Exception as hata:  # noqa: BLE001
            print(f"Güvenli kapatma başarısız ({hata!r}); acil sıfırlama.", file=sys.stderr)
            grup.acil_sifirla()
        dongu.kes()
        try:
            (dongu.oturum.klasor() / "scpi_gunlugu.txt").write_text(
                "\n".join(scpi.satirlar()) + "\n", encoding="utf-8")
        except OSError:
            pass
    return kod


if __name__ == "__main__":
    raise SystemExit(main())
