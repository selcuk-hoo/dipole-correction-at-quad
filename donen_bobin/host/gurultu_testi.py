"""Gürültü testi: merkez gürültüsü dönme hızına ve güç kaynağı akımlarına bağlı mı?

    cd donen_bobin/host && python gurultu_testi.py [--hizlar 8 11 13 8] [--n 8] [--pencere 3]

    python gurultu_testi.py --hizlar 2 4 6 8 10 --oturma 120   # hız taraması

Akımları verilen değerlere (varsayılan: 6 Kasım 7 A merkezlemesinin sonu) rampa
ile getirir; her hızda düz bobinle N ölçüm alır. Her ölçüm süresince ayrı bir
iş parçacığı dört güç kaynağının MEAS:CURR? değerini okur. Ölçülen merkez
dalgalanması, akım sapmalarından kalibrasyon matrisiyle beklenen dalgalanmayla
karşılaştırılır:

  * gürültü hızla değişiyor, akımlarla ilişkisiz -> mekanik (şaft sarsıntısı)
    ya da elektriksel
  * gürültü akım sapmalarını izliyor            -> güç kaynağı akım gürültüsü

Sonunda akımlar rampa ile sıfırlanır, çıkışlar kapanır, motor durur (hata ve
Ctrl+C dahil). Sonuçlar oturum klasörüne: gurultu_testi.csv ve ham veriler.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import threading
from datetime import datetime

import numpy as np

from kanal_testi import KOK, KanalTesti, KanalTestiHatasi  # noqa: F401  (KOK: sys.path)
from mgf.merkezleme_koprusu import parametreleri_yukle
from mgf.olcum_dongusu import Durum, OlcumDongusu

SON_AKIMLAR_7A = (8.2564, 6.4030, 5.9677, 7.8211)
KALIBRASYON_7A = KOK / "calistirmalar" / "2026-11-06_125537" / "kalibrasyon.json"


class AkimOkuyucu:
    """Ölçüm süresince dört kaynağın MEAS:CURR?'ını arka planda okur."""

    def __init__(self, kaynaklar) -> None:
        self.kaynaklar = kaynaklar
        self._dur = threading.Event()
        self.okumalar: list[list[float]] = []
        self._is: threading.Thread | None = None

    def _dongu(self) -> None:
        while not self._dur.is_set():
            satir = []
            for k in self.kaynaklar:
                _, akim = k.olcumleri_oku() if not hasattr(k, "_sorgula") else (None, float(k._sorgula("MEAS:CURR?")))
                satir.append(float(akim))
            self.okumalar.append(satir)

    def __enter__(self) -> "AkimOkuyucu":
        self.okumalar = []
        self._dur.clear()
        self._is = threading.Thread(target=self._dongu, daemon=True)
        self._is.start()
        return self

    def __exit__(self, *_) -> None:
        self._dur.set()
        if self._is is not None:
            self._is.join(timeout=10)

    def ortalama(self) -> np.ndarray:
        return np.mean(self.okumalar, axis=0) if self.okumalar else np.full(4, np.nan)


class GurultuTesti(KanalTesti):
    def __init__(self, *a, akimlar=SON_AKIMLAR_7A, hizlar=(8, 11, 13, 8), n=8, R=None, nominal_A=7.0,
                 oturma_s: float = 0.0, min_tur: float = 0.0, **k) -> None:
        super().__init__(*a, **k)
        self.akimlar = np.asarray(akimlar, dtype=float)
        self.oturma_s, self.min_tur = oturma_s, min_tur
        self.hizlar, self.n, self.R, self.nominal_A = list(hizlar), n, R, nominal_A
        self.satirlar: list[dict] = []

    def calistir(self):  # type: ignore[override]
        d = self.dongu
        d.otomatik_yaz_ayarla(False)
        d.pencere_ayarla(self.pencere_s)
        d.hiz_ayarla(self.hizlar[0])
        self.yaz(f"Akımlar rampa ile: {self.akimlar} A")
        self.grup.rampala(self.akimlar)
        d.baslat()
        for blok, hz in enumerate(self.hizlar):
            d.hiz_ayarla(hz)
            self._tick_bekle(lambda: d.durum is Durum.DONUYOR, 60, f"{hz} Hz'de hızın oturması")
            # Pencere en az `min_tur` tur (düşük hızda düşük mertebeler sürüklenme
            # polinomundan ayrılabilsin); oturma süresince sürekli ölçümler kaydedilir.
            pencere = max(self.pencere_s, self.min_tur / hz if hz else 0.0)
            d.pencere_ayarla(pencere)
            if self.oturma_s:
                self.yaz(f"Blok {blok + 1}/{len(self.hizlar)}: {hz:g} Hz, {self.oturma_s:g} s oturma")
            self._sure(max(1.0, self.oturma_s))
            self.yaz(f"Blok {blok + 1}/{len(self.hizlar)}: {hz:g} Hz, {self.n} ölçüm ({pencere:.1f} s)")
            for i in range(self.n):
                with AkimOkuyucu(self.grup.kaynaklar) as ok:
                    s = self._olc()
                c = s.harmonikler
                z = -self.p.r_ref_m * c[0] / c[1]
                self.satirlar.append({
                    "blok": blok + 1, "hiz_hz": hz, "olcum": i + 1, "olculen_hiz_hz": s.hiz_hz,
                    "x_c_um": z.real * 1e6, "y_c_um": z.imag * 1e6, "C1_uT": abs(c[0]) * 1e6,
                    "C2_mT": abs(c[1]) * 1e3, "artik_orani": s.artik_orani, "saat_sicramasi": s.saat_sicramasi,
                    **{f"I{j + 1}_A": float(v) for j, v in enumerate(ok.ortalama())},
                    "akim_okuma_sayisi": len(ok.okumalar),
                })
        self.grup.rampala(np.zeros(4))
        return self.satirlar

    def rapor(self):  # type: ignore[override]
        sat = self.satirlar
        satirlar = []
        self.yaz("")
        self.yaz("ÖZET: merkez saçılımı (blok içinde, µm) ve akım sapmalarından beklenen saçılım")
        self.yaz(f"  {'blok':>4s} {'hız':>5s} {'σx':>7s} {'σy':>7s} {'σx_bekl':>8s} {'σy_bekl':>8s} {'kor_x':>6s} {'kor_y':>6s} {'σI maks (mA)':>13s}")
        for blok in sorted({s["blok"] for s in sat}):
            b = [s for s in sat if s["blok"] == blok]
            x = np.array([s["x_c_um"] for s in b]); y = np.array([s["y_c_um"] for s in b])
            I = np.array([[s[f"I{j}_A"] for j in range(1, 5)] for s in b])
            sigI = np.nanstd(I, axis=0, ddof=1) * 1e3
            bx = by = np.full(len(b), np.nan)
            kx = ky = float("nan")
            if self.R is not None and np.all(np.isfinite(I)):
                dz = (I - I.mean(axis=0)) / self.nominal_A @ self.R[:2].T * 1e6  # µm
                bx, by = dz[:, 0], dz[:, 1]
                if np.std(bx) > 0 and np.std(by) > 0:
                    kx = float(np.corrcoef(x, bx)[0, 1]); ky = float(np.corrcoef(y, by)[0, 1])
            r = {"blok": blok, "hiz_hz": b[0]["hiz_hz"], "sigma_x_um": float(np.std(x, ddof=1)),
                 "sigma_y_um": float(np.std(y, ddof=1)), "beklenen_sigma_x_um": float(np.nanstd(bx, ddof=1)),
                 "beklenen_sigma_y_um": float(np.nanstd(by, ddof=1)), "korelasyon_x": kx, "korelasyon_y": ky,
                 "akim_sigma_maks_mA": float(np.nanmax(sigI)), "ort_x_um": float(x.mean()), "ort_y_um": float(y.mean())}
            satirlar.append(r)
            self.yaz(f"  {blok:4d} {r['hiz_hz']:5g} {r['sigma_x_um']:7.1f} {r['sigma_y_um']:7.1f} "
                     f"{r['beklenen_sigma_x_um']:8.1f} {r['beklenen_sigma_y_um']:8.1f} {kx:6.2f} {ky:6.2f} {r['akim_sigma_maks_mA']:13.2f}"
                     f"   (ort x={r['ort_x_um']:+.0f}, y={r['ort_y_um']:+.0f} µm)")
        return satirlar

    def raporu_yaz(self, ozet):  # type: ignore[override]
        klasor = self.dongu.oturum.klasor()
        for ad, veri in (("gurultu_testi.csv", self.satirlar), ("gurultu_testi_ozet.csv", ozet)):
            with open(klasor / ad, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=list(veri[0]))
                w.writeheader()
                w.writerows(veri)
        self.yaz(f"Kayıtlar: {klasor}")
        return klasor


def main(argv=None) -> int:
    a = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    a.add_argument("--hizlar", type=float, nargs="+", default=[8, 11, 13, 8])
    a.add_argument("--n", type=int, default=8)
    a.add_argument("--pencere", type=float, default=3.0, help="en kısa ölçüm süresi (s)")
    a.add_argument("--min-tur", type=float, default=20.0, help="ölçüm penceresine en az bu kadar tur")
    a.add_argument("--oturma", type=float, default=0.0, help="her hızda ölçümden önce bekleme (s)")
    a.add_argument("--akimlar", type=float, nargs=4, default=list(SON_AKIMLAR_7A))
    a.add_argument("--parametreler", default=str(KOK / "donen_bobin" / "merkezleme_olcer_7A.yaml"))
    a.add_argument("--yapilandirma", default=str(KOK / "yapilandirma_7A.yaml"))
    g = a.parse_args(argv)
    if max(g.hizlar) > 13:
        print("13 Hz üstü: enkoder bozuluyor (CRC'li firmware yüklenmedi).", file=sys.stderr)
        return 2

    from merkezleme.guc_kaynagi import KaynakGrubu, KomutGunlugu
    from merkezleme.yapilandirma import yapilandirma_yukle
    from mgf.connection import MgfConnection
    from mgf.data_engine import DataEngine

    p = parametreleri_yukle(g.parametreler)
    kfg = yapilandirma_yukle(g.yapilandirma)
    if max(g.akimlar) > kfg.guvenlik.bobin_basi_max_akim_A or min(g.akimlar) < 0:
        print("akımlar 0 ile bobin başı sınır arasında olmalı", file=sys.stderr)
        return 2
    R = np.array(json.loads(KALIBRASYON_7A.read_text())["R"]) if KALIBRASYON_7A.exists() else None

    def gunluk(m: str) -> None:
        print(f"{datetime.now():%H:%M:%S}  {m}")

    dongu = OlcumDongusu(p, MgfConnection(p.ip, p.port), DataEngine(), gunluk=gunluk)
    if not dongu.baglan():
        print("Pico'ya bağlanılamadı.", file=sys.stderr)
        return 1
    scpi = KomutGunlugu()
    grup = KaynakGrubu.olustur(kfg.guc_kaynaklari, kfg.guvenlik, canli=True, gunluk=scpi)
    test = GurultuTesti(p, dongu, grup, akim_A=float(np.mean(g.akimlar)), pencere_s=g.pencere,
                        akimlar=g.akimlar, hizlar=g.hizlar, n=g.n, R=R, nominal_A=kfg.miknatis.nominal_akim_A,
                        oturma_s=g.oturma, min_tur=g.min_tur)
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
            (dongu.oturum.klasor() / "scpi_gunlugu.txt").write_text("\n".join(scpi.satirlar()) + "\n", encoding="utf-8")
        except OSError:
            pass
    return kod


if __name__ == "__main__":
    raise SystemExit(main())
