"""Merkezlemedeki açıklanamayan sıçramalar için tanı ölçümü (18 Kasım 2026).

    python3 -m merkezleme.tani_testi --akimlar-calistirma 2026-11-18_151730

18 Kasım testinde düzeltme yinelemeleri arasındaki merkez değişimi, matrisin
öngörüsünden her adımda 13-19 µm saptı; tek ölçüm gürültüsü ~4 µm (iki ölçüm farkı
~6 µm), kalibrasyonun büyük adımlarında tepki doğrusal. Ayırt edilecek adaylar:
  A) akım değiştikten hemen sonra alınan ölçüm daha gürültülü mü?
     -> aynı akımlarda art arda 6 ölçüm (her biri yeni bir kilit turu)
  B) küçük adımlara (~3 mA, H deseni) tepki tekrarlanabilir mi?
     -> I0, I0+d, I0, I0-d, I0 döngüsü, 4 kez
  C) histerezis: aynı noktaya yukarıdan ve aşağıdan gelmek merkezi değiştiriyor mu?
     -> I0+%0.5H -> I0 (2 ölçüm), I0-%0.5H -> I0 (2 ölçüm), 2 kez
  D) sıfırdan geçmek (arka plan adımı gibi) merkezi değiştiriyor mu?
     -> I0 -> 0 (arka plan) -> I0 (2 ölçüm), 2 kez
Sonuçlar `kayitlar/tani_testi_<zaman>.csv` ve özet `.json`. Arayüzü ekransız açar,
motoru başlatır; hata, SIGTERM ya da zaman aşımında akımlar rampa ile sıfırlanır.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import signal
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

import numpy as np

KOK = Path(__file__).resolve().parents[1]
HOST = KOK / "donen_bobin" / "host"


def main(argv: list[str] | None = None) -> int:
    a = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    a.add_argument("--akimlar-calistirma", required=True,
                   help="başlangıç akımları (I0) bu çalıştırmanın son akımlarıdır")
    a.add_argument("--kucuk-adim", type=float, default=0.0003, help="B: bağıl adım (H deseni)")
    a.add_argument("--buyuk-adim", type=float, default=0.005, help="C: bağıl adım (H deseni)")
    a.add_argument("--hiz", type=float, default=8.0)
    a.add_argument("--zaman-asimi-dk", type=float, default=25.0)
    g = a.parse_args(argv)

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.chdir(KOK)
    sys.path.insert(0, str(HOST))
    from PySide6.QtWidgets import QApplication

    from mgf.connection import MgfConnection
    from mgf.data_engine import DataEngine
    from mgf.merkezleme_koprusu import parametreleri_yukle
    from mgf.merkezleme_penceresi import MerkezlemePenceresi
    from mgf.olcum_dongusu import Durum

    from .ana import _kaynak_grubu_kur
    from .arayuz import qt_bekle
    from .birlesik import bobin_durumu, telegram_bildir
    from .guc_kaynagi import KomutGunlugu
    from .harmonikler import HarmonikKonvansiyonu
    from .modlar import ModBazi
    from .olcum_kaynagi import DosyaGirisi, OlcumIstegi
    from .yapilandirma import yapilandirma_yukle

    zaman = f"{datetime.now():%Y-%m-%d_%H%M%S}"
    csv_yolu = KOK / "kayitlar" / f"tani_testi_{zaman}.csv"
    gunluk_yolu = csv_yolu.with_suffix(".log")

    def yaz(m: str) -> None:
        satir = f"{datetime.now():%H:%M:%S}  {m}"
        print(satir, flush=True)
        with gunluk_yolu.open("a", encoding="utf-8") as f:
            f.write(satir + "\n")

    kfg = yapilandirma_yukle(KOK / "yapilandirma.yaml")
    durum = json.loads((KOK / "calistirmalar" / g.akimlar_calistirma / "durum.json").read_text(encoding="utf-8"))
    I0 = np.asarray(durum["mevcut_akimlar_A"], dtype=float)
    mb = ModBazi(kfg.modlar, kfg.miknatis)
    H = mb.mod_vektoru("H")
    x0 = mb.bagil_sapma(I0)
    for e in (g.kucuk_adim, g.buyuk_adim):
        for s in (1, -1):
            x = x0 + s * e * H
            if np.any(np.abs(x) > kfg.guvenlik.nominale_gore_max_asimetri):
                raise SystemExit("adım asimetri sınırını aşıyor")
    konv = HarmonikKonvansiyonu(kfg.harmonikler)

    p = parametreleri_yukle(None)
    uygulama = QApplication(sys.argv[:1])
    bobin = MerkezlemePenceresi(p, MgfConnection(p.ip, p.port), DataEngine())
    bobin.show()
    iptal = {"neden": None}
    signal.signal(signal.SIGTERM, lambda *_: iptal.update(neden="SIGTERM"))
    baslangic = time.monotonic()

    def bekle_kosul(kosul, en_fazla_s: float) -> bool:
        bitis = time.monotonic() + en_fazla_s
        while time.monotonic() < bitis:
            if iptal["neden"] or time.monotonic() - baslangic > g.zaman_asimi_dk * 60:
                raise RuntimeError(f"iptal/zaman aşımı: {iptal['neden']}")
            if kosul():
                return True
            qt_bekle(0.2)
        return False

    grup = None
    satirlar: list[dict] = []
    ozet: dict = {"I0_A": I0.tolist(), "csv": str(csv_yolu)}
    try:
        bobin.baglan()
        if not bekle_kosul(lambda: bobin.dongu.durum is not Durum.BAGLI_DEGIL, 20):
            raise RuntimeError("Pico'ya bağlanılamadı")
        bobin.hiz.setValue(g.hiz)
        bobin._baslat()
        if not bekle_kosul(lambda: bobin_durumu(bobin.dongu)[0], 120):
            raise RuntimeError("dönen bobin hazır olmadı")
        yaz("Dönen bobin: " + bobin_durumu(bobin.dongu)[1])
        Path(kfg.dosya_girisi.kilit_dosyasi).unlink(missing_ok=True)
        grup = _kaynak_grubu_kur(kfg, canli=True, gunluk=KomutGunlugu(), bekle=qt_bekle)
        grup.baslat()
        kaynak = DosyaGirisi(kfg.dosya_girisi, konv, bekle=qt_bekle)
        arka = {"olcum": None}
        sayac = {"n": 0}

        def olc(grup_adi: str, etiket: str, akimlar: np.ndarray) -> None:
            if iptal["neden"] or time.monotonic() - baslangic > g.zaman_asimi_dk * 60:
                raise RuntimeError(f"iptal/zaman aşımı: {iptal['neden']}")
            akimlar = np.asarray(akimlar, dtype=float)
            grup.rampala(akimlar)
            sayac["n"] += 1
            tur = "arka_plan" if not np.any(akimlar > 0) else "olcum"
            m = kaynak.olcum_al(OlcumIstegi(tur=tur, etiket=etiket, akimlar_A=akimlar,
                                            adim_no=sayac["n"], toplam_adim=0))
            satir = {"zaman": datetime.now().isoformat(timespec="seconds"), "grup": grup_adi,
                     "etiket": etiket, **{f"I{i + 1}_A": round(float(v), 5) for i, v in enumerate(akimlar)}}
            if tur == "arka_plan":
                arka["olcum"] = m
                c1 = m.bilesen(1)
                satir.update(B1_uT=c1.real * 1e6, A1_uT=c1.imag * 1e6)
            else:
                net = konv.arka_plan_cikar(m, arka["olcum"])
                z = konv.merkez(net)
                satir.update(x_um=z.real * 1e6, y_um=z.imag * 1e6, C2_mT=abs(net.bilesen(2)) * 1e3)
            satirlar.append(satir)
            yaz(f"{grup_adi} {etiket}: " + ", ".join(f"{k}={v:.2f}" for k, v in satir.items()
                                                    if k in ("x_um", "y_um", "B1_uT", "A1_uT")))

        sifir = np.zeros(4)
        d = mb.akimlar(x0 + g.kucuk_adim * H) - I0
        D = mb.akimlar(x0 + g.buyuk_adim * H) - I0
        olc("hazirlik", "arka plan", sifir)
        for i in range(6):
            olc("A", f"I0 tekrar {i + 1}", I0)
        for k in range(4):
            for ad, I in (("+d", I0 + d), ("I0", I0), ("-d", I0 - d), ("I0", I0)):
                olc("B", f"döngü {k + 1} {ad}", I)
        for k in range(2):
            for yon, I in (("yukaridan", I0 + D), ("asagidan", I0 - D)):
                grup.rampala(I)
                qt_bekle(1.0)
                olc("C", f"{k + 1} {yon} 1", I0)
                olc("C", f"{k + 1} {yon} 2", I0)
        for k in range(2):
            olc("D", f"{k + 1} sıfır (arka plan)", sifir)
            olc("D", f"{k + 1} sıfırdan sonra 1", I0)
            olc("D", f"{k + 1} sıfırdan sonra 2", I0)
    except Exception as hata:  # noqa: BLE001
        ozet["hata"] = repr(hata)
        yaz("HATA: " + "".join(traceback.format_exception(hata)))
    finally:
        yaz("Kapanış: akımlar sıfırlanıyor, çıkışlar kapatılıyor, motor durduruluyor...")
        try:
            if grup is not None:
                grup.guvenli_kapat()
        except Exception as hata:  # noqa: BLE001
            yaz(f"Güç kaynağı kapanışında hata: {hata!r}")
            try:
                grup.acil_sifirla()
            except Exception:  # noqa: BLE001
                pass
        try:
            if bobin.dongu.donuyor:
                bobin.dongu.durdur()
                qt_bekle(6)
            bobin.close()
        except Exception as hata:  # noqa: BLE001
            yaz(f"Bobin kapanışında hata: {hata!r}")
        if satirlar:
            alanlar = {k for s in satirlar for k in s}
            sira = ["zaman", "grup", "etiket", "I1_A", "I2_A", "I3_A", "I4_A", "x_um", "y_um", "C2_mT",
                    "B1_uT", "A1_uT"]
            with csv_yolu.open("w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=[k for k in sira if k in alanlar])
                w.writeheader()
                w.writerows(satirlar)
            ozet.update(_ozetle(satirlar))
        yaz("Özet: " + json.dumps(ozet, ensure_ascii=False))
        csv_yolu.with_suffix(".json").write_text(json.dumps(ozet, ensure_ascii=False, indent=2), encoding="utf-8")
        telegram_bildir("Tanı testi bitti", "; ".join(f"{k}: {v}" for k, v in ozet.items()
                                                      if k.startswith(("A_", "B_", "C_", "D_", "hata"))))
        uygulama.quit()
    return 0 if "hata" not in ozet else 1


def _ozetle(satirlar: list[dict]) -> dict:
    def z(s):
        return complex(s["x_um"], s["y_um"])
    o: dict = {}
    A = [z(s) for s in satirlar if s["grup"] == "A"]
    if len(A) > 1:
        o["A_tekrar_sigma_um"] = [round(float(np.std([v.real for v in A], ddof=1)), 2),
                                  round(float(np.std([v.imag for v in A], ddof=1)), 2)]
    B = [s for s in satirlar if s["grup"] == "B"]
    if B:
        # her döngüde (+d) - (-d) farkının yarısı: küçük adıma tepki; döngüler arası saçılım
        donguler = sorted({s["etiket"].split()[1] for s in B})
        tepkiler = []
        for k in donguler:
            arti = [z(s) for s in B if s["etiket"].split()[1] == k and s["etiket"].endswith("+d")]
            eksi = [z(s) for s in B if s["etiket"].split()[1] == k and s["etiket"].endswith("-d")]
            if arti and eksi:
                tepkiler.append((arti[0] - eksi[0]) / 2)
        if tepkiler:
            ort = np.mean(tepkiler)
            o["B_kucuk_adim_tepkisi_um"] = [round(ort.real, 2), round(ort.imag, 2)]
            o["B_tepki_donguler_arasi_sigma_um"] = round(float(np.std(np.abs(np.array(tepkiler) - ort), ddof=0)), 2)
        sifirlar = [z(s) for s in B if s["etiket"].endswith("I0")]
        if len(sifirlar) > 1:
            o["B_I0_sigma_um"] = [round(float(np.std([v.real for v in sifirlar], ddof=1)), 2),
                                  round(float(np.std([v.imag for v in sifirlar], ddof=1)), 2)]
    C = [s for s in satirlar if s["grup"] == "C"]
    if C:
        yuk = np.mean([z(s) for s in C if "yukaridan" in s["etiket"]])
        asa = np.mean([z(s) for s in C if "asagidan" in s["etiket"]])
        o["C_yukaridan_eksi_asagidan_um"] = [round((yuk - asa).real, 2), round((yuk - asa).imag, 2)]
    Dn = [z(s) for s in satirlar if s["grup"] == "D" and "x_um" in s]
    if Dn and A:
        fark = np.mean(Dn) - np.mean(A)
        o["D_sifirdan_sonra_eksi_A_um"] = [round(fark.real, 2), round(fark.imag, 2)]
    return o


if __name__ == "__main__":
    raise SystemExit(main())
