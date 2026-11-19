"""18 Kasım 2026 raporunun sayıları ve şekilleri.

Çalıştırma: python3 raporlar/merkezleme_2026-11-18/analiz.py
Çıktı: sonuclar.json, sekil1_matris.pdf, sekil2_testler.pdf, sekil3_sicrama.pdf
Girdi: calistirmalar/, kayitlar/ (git'te yok; bu bilgisayarda).
"""
import glob
import json
import math
import sys
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

KOK = Path(__file__).resolve().parents[2]
CIKTI = Path(__file__).resolve().parent
sys.path.insert(0, str(KOK))
sys.path.insert(0, str(KOK / "donen_bobin" / "host"))
from merkezleme.kalibrasyon import kayitli_kalibrasyonu_yukle  # noqa: E402
from mgf import merkezleme_koprusu as mk  # noqa: E402

MAVI, TURUNCU, YESIL, GRI = "#2a78d6", "#eb6834", "#1baf7a", "#888888"
SPS = 7200.0
sonuc: dict = {}

# ---------------------------------------------------------------- 1. kalibrasyon matrisleri
KALIBRASYONLAR = ["2026-11-06_152726", "2026-11-06_161730", "2026-11-06_165637", "2026-11-06_182116",
                  "2026-11-11_173406", "2026-11-12_101337", "2026-11-12_120525",
                  "2026-11-17_104609", "2026-11-17_131846"]
satirlar = []
for r in KALIBRASYONLAR:
    d = KOK / "calistirmalar" / r
    kal = kayitli_kalibrasyonu_yukle(d / "kalibrasyon.json")
    nominal = 7.0 if r.endswith("152726") else 9.5
    sutun = kal.R[0] + 1j * kal.R[1]
    psi = kal.kuadrupol_acisi_rad
    dondurulmus = sutun * np.exp(1j * psi)
    isaret = 1 if dondurulmus[0].real >= 0 else -1
    dondurulmus = dondurulmus * isaret
    satirlar.append({
        "calistirma": r, "nominal_A": nominal, "psi_derece": math.degrees(psi),
        "cos2psi": math.cos(2 * psi),
        "ham_aci": [math.degrees(np.angle(x)) for x in sutun],
        "kuadrupol_aci": [math.degrees(np.angle(x)) for x in dondurulmus],
        "um_per_mA": [abs(x) * 1e3 / nominal * 1e-3 * 1e3 / 1e3 for x in dondurulmus],
        "supheli": bool(kal.supheli), "isaret": isaret,
    })
for s in satirlar:  # µm/mA: R (m / bağıl akım) -> 1 mA = 1e-3/nominal bağıl
    pass
for s, r in zip(satirlar, KALIBRASYONLAR):
    kal = kayitli_kalibrasyonu_yukle(KOK / "calistirmalar" / r / "kalibrasyon.json")
    sutun = np.abs(kal.R[0] + 1j * kal.R[1])
    s["um_per_mA"] = [float(x * 1e6 * 1e-3 / s["nominal_A"]) for x in sutun]
sonuc["matrisler"] = satirlar
quad = np.array([s["kuadrupol_aci"] for s in satirlar])
sonuc["kuadrupol_cercevesi_aci_yayilimi_derece"] = [float(np.ptp(quad[:, i])) for i in range(4)]
sonuc["kuadrupol_cercevesi_aci_ortalama"] = [float(x) for x in quad.mean(axis=0)]
# 7 A matrisi hariç boy yayılımı (µm/mA, 9.5 A)
boy = np.array([s["um_per_mA"] for s in satirlar if s["nominal_A"] == 9.5])
sonuc["um_per_mA_9p5A_min_max"] = [float(boy.min()), float(boy.max())]

fig, ax = plt.subplots(1, 2, figsize=(10, 3.8), sharey=True)
x = np.arange(len(satirlar))
for i, (renk, ad) in enumerate(zip((MAVI, TURUNCU, YESIL, GRI), ("I1", "I2", "I3", "I4"))):
    ax[0].plot(x, [s["ham_aci"][i] for s in satirlar], "o-", color=renk, lw=1, label=ad)
    ax[1].plot(x, [s["kuadrupol_aci"][i] for s in satirlar], "o-", color=renk, lw=1, label=ad)
for a, b in zip(ax, ("Bobin çerçevesinde (enkoder sıfırı)", "Kuadrupol çerçevesinde (C₂ fazına göre döndürülmüş)")):
    a.set_title(b, fontsize=10)
    a.set_xticks(x)
    a.set_xticklabels([s["calistirma"][5:10] + "\n" + s["calistirma"][11:15] for s in satirlar], fontsize=7)
    a.grid(alpha=0.25)
    a.spines[["top", "right"]].set_visible(False)
ax[0].set_ylabel("bobin sütununun açısı, derece")
ax[0].legend(frameon=False, ncol=4, fontsize=8)
fig.tight_layout()
fig.savefig(CIKTI / "sekil1_matris.pdf")
plt.close(fig)

# ---------------------------------------------------------------- 2. aynı gün tekrarlanabilirlik (akımlar)
def son_akimlar(r):
    d = KOK / "calistirmalar" / r
    return np.array(json.loads((d / "durum.json").read_text())["mevcut_akimlar_A"]), \
        kayitli_kalibrasyonu_yukle(d / "kalibrasyon.json")

ciftler = [("2026-11-06_161730", "2026-11-06_165637"), ("2026-11-12_101337", "2026-11-12_120525"),
           ("2026-11-17_104609", "2026-11-17_131846")]
tekrar = []
for a, b in ciftler:
    Ia, Ra = son_akimlar(a)
    Ib, _ = son_akimlar(b)
    fark_mA = (Ib - Ia) * 1e3
    um = (Ra.R[0] + 1j * Ra.R[1]) @ ((Ib - Ia) / 9.5) * 1e6
    tekrar.append({"a": a, "b": b, "fark_mA": [float(v) for v in fark_mA], "ortak_mA": float(fark_mA.mean()),
                   "merkezde_um": float(abs(um))})
sonuc["ayni_gun_tekrar"] = tekrar

# ---------------------------------------------------------------- 3. 18 Kasım testleri
def merkez_dizisi(r):
    c = pd.read_csv(KOK / "calistirmalar" / r / "olcumler.csv")
    k = c[c.adim_turu.isin(["yon_dogrulama", "duzeltme"])].reset_index(drop=True)
    return k, json.loads((KOK / "calistirmalar" / r / "durum.json").read_text())

t1, d1 = merkez_dizisi("2026-11-18_151730")
t3, d3 = merkez_dizisi("2026-11-18_153713")
for ad, k, d in (("test1", t1, d1), ("test3", t3, d3)):
    sonuc[ad] = {
        "yon": d.get("yon_dogrulama"), "iterasyon": d["iterasyon"], "yakinsadi": d.get("yakinsadi"),
        "son_merkez_um": [float(k.x_c_um.iloc[-1]), float(k.y_c_um.iloc[-1])],
        "olcum_sayisi": int(len(k)),
        "sure_s": float((pd.to_datetime(k.zaman.iloc[-1]) - pd.to_datetime(k.zaman.iloc[0])).total_seconds()),
        "akimlar_A": [float(v) for v in d["mevcut_akimlar_A"]],
    }
tani = json.loads((KOK / "kayitlar" / "tani_testi_2026-11-18_153117.json").read_text())
sonuc["tani"] = {k: v for k, v in tani.items() if k != "csv"}
tcsv = pd.read_csv(KOK / "kayitlar" / "tani_testi_2026-11-18_153117.csv")
m = tcsv[tcsv.x_um.notna()]
sonuc["tani"]["olcum_sayisi"] = int(len(m))
sonuc["tani"]["tum_I0_x_um_ort"] = float(m[m.etiket.str.contains("I0|tekrar|sıfırdan|yukaridan|asagidan")].x_um.mean())

fig, ax = plt.subplots(1, 2, figsize=(10, 3.6), sharey=True)
for a, k, baslik in ((ax[0], t1, "Test 1: 2 s'lik ölçüm"), (ax[1], t3, "Test 3: 10 s'lik ölçüm")):
    n = np.arange(1, len(k) + 1)
    a.plot(n, np.abs(k.x_c_um).clip(lower=0.05), "o-", color=MAVI, lw=1.2, label="|x_c|")
    a.plot(n, np.abs(k.y_c_um).clip(lower=0.05), "s-", color=TURUNCU, lw=1.2, label="|y_c|")
    a.axhline(5, color=GRI, ls="--", lw=1)
    a.text(len(k) + 0.1, 5.4, "tolerans 5 µm", color=GRI, fontsize=8, ha="right")
    a.set_yscale("log")
    a.set_title(baslik, fontsize=10)
    a.set_xlabel("ölçüm (yön doğrulama ve düzeltme)")
    a.set_xticks(n)
    a.grid(alpha=0.25, which="both")
    a.spines[["top", "right"]].set_visible(False)
ax[0].set_ylabel("merkez, µm (log)")
ax[0].legend(frameon=False)
fig.tight_layout()
fig.savefig(CIKTI / "sekil2_testler.pdf")
plt.close(fig)

# ---------------------------------------------------------------- 4. saat sıçraması: ham veriden
def sicrama(aci):
    a, _ = mk.bozuk_acilari_ayikla(np.asarray(aci, float))
    return mk.aci_merdivenini_duzelt(np.unwrap(np.radians(a)))[4]

def oturum_sicrama(klasor):
    sonuclar = []
    for f in sorted(glob.glob(str(KOK / "kayitlar" / klasor / "ham_*olcum*merkezleme*.csv"))):
        d = pd.read_csv(f, comment="#")
        if len(d) < 8 * SPS:
            continue
        a = d.aci_derece.values
        s2 = [sicrama(a[i:i + int(2 * SPS)]) for i in range(0, len(a) - int(2 * SPS) + 1, int(2 * SPS))]
        sonuclar.append((sicrama(a), float(np.nanmedian(s2))))
    return sonuclar

oturumlar = {"15:37 (test 3)": "2026-11-18_153724", "16:30 (sizin deneme)": "2026-11-18_163044"}
sicr = {}
for ad, kl in oturumlar.items():
    v = np.array(oturum_sicrama(kl))
    sicr[ad] = v
    sonuc.setdefault("sicrama", {})[ad] = {
        "n": int(len(v)), "medyan_10s": float(np.nanmedian(v[:, 0])), "maks_10s": float(np.nanmax(v[:, 0])),
        "ustu_0p6": int((v[:, 0] > 0.6).sum()), "ustu_0p9": int((v[:, 0] > 0.9).sum()),
        "medyan_2s_dilim": float(np.nanmedian(v[:, 1])),
    }
g = (KOK / "kayitlar" / "2026-11-18_163044" / "gunluk.txt").read_text(encoding="utf-8")
sonuc["sicrama"]["16:30 (sizin deneme)"]["gunlukte_ret"] = g.count("Ölçüm reddedildi")
sonuc["sicrama"]["16:30 (sizin deneme)"]["gunlukte_hata"] = g.count("HATA: Üst üste")
# 17 Kasım sürekli ölçüm (2 s pencere)
o = pd.read_csv(KOK / "kayitlar" / "2026-11-17_103703" / "olcumler.csv")
s = o[o.tur == "surekli"].saat_sicramasi
sonuc["sicrama"]["17 Kasım (2 s pencere, 10 427 ölçüm)"] = {
    "n": int(len(s)), "medyan": float(s.median()), "yuzde_ustu_0p6": float((s > 0.6).mean() * 100),
    "yuzde_ustu_0p9": float((s > 0.9).mean() * 100)}

fig, ax = plt.subplots(figsize=(8, 3.4))
for (ad, v), renk in zip(sicr.items(), (MAVI, TURUNCU)):
    ax.plot(np.arange(1, len(v) + 1), v[:, 0], "o", color=renk, ms=5, label=f"{ad}: 10 s'lik pencere")
ax.axhline(0.6, color=GRI, ls="--", lw=1)
ax.axhline(0.9, color=YESIL, ls="--", lw=1)
ax.text(0.5, 0.61, "eski eşik 0.6", color=GRI, fontsize=8, va="bottom")
ax.text(0.5, 0.91, "yeni eşik 0.9", color=YESIL, fontsize=8, va="bottom")
ax.set_ylim(0.3, 1.2)
ax.set_xlabel("ölçüm sırası")
ax.set_ylabel("okuma saati sıçraması (örnek)")
ax.legend(frameon=False, fontsize=8, loc="upper right")
ax.grid(alpha=0.25)
ax.spines[["top", "right"]].set_visible(False)
fig.tight_layout()
fig.savefig(CIKTI / "sekil3_sicrama.pdf")
plt.close(fig)

(CIKTI / "sonuclar.json").write_text(json.dumps(sonuc, indent=1, ensure_ascii=False), encoding="utf-8")
print(json.dumps({k: v for k, v in sonuc.items() if k not in ("matrisler",)}, indent=1, ensure_ascii=False)[:3500])

# ---------------------------------------------------------------- LaTeX tablo parçaları (rapor.tex \input eder)
def tex_sayi(v, n=1):
    return f"{v:.{n}f}".replace("-", "$-$")

satir = []
for s in satirlar:
    gun = (s["calistirma"][8:10] + "." + s["calistirma"][5:7] + " "
           + s["calistirma"][11:13] + ":" + s["calistirma"][13:15])
    satir.append(" & ".join([
        gun, f"{s['nominal_A']:g}", tex_sayi(s["psi_derece"]), tex_sayi(s["cos2psi"], 2),
        tex_sayi(s["ham_aci"][0], 0), *[tex_sayi(a, 0) for a in s["kuadrupol_aci"]],
        f"{min(s['um_per_mA']):.2f}--{max(s['um_per_mA']):.2f}", "evet" if s["supheli"] else "hayır"]) + r" \\")
(CIKTI / "tablo_matris.tex").write_text("\n".join(satir) + "\n", encoding="utf-8")

satir = []
for t in sonuc["ayni_gun_tekrar"]:
    gun = t["a"][8:10] + "." + t["a"][5:7]
    saat = f"{t['a'][11:13]}:{t['a'][13:15]} → {t['b'][11:13]}:{t['b'][13:15]}"
    satir.append(" & ".join([
        gun, saat, ", ".join(tex_sayi(v, 1) for v in t["fark_mA"]), tex_sayi(t["ortak_mA"], 1),
        f"{t['merkezde_um']:.0f}"]) + r" \\")
(CIKTI / "tablo_tekrar.tex").write_text("\n".join(satir) + "\n", encoding="utf-8")

sc = sonuc["sicrama"]
satir = [
    r"17 Kasım, sürekli ölçüm (2 s) & " + f"{sc['17 Kasım (2 s pencere, 10 427 ölçüm)']['n']}" + " & "
    + f"{sc['17 Kasım (2 s pencere, 10 427 ölçüm)']['medyan']:.2f} & "
    + f"\\%{sc['17 Kasım (2 s pencere, 10 427 ölçüm)']['yuzde_ustu_0p6']:.1f} & "
    + f"\\%{sc['17 Kasım (2 s pencere, 10 427 ölçüm)']['yuzde_ustu_0p9']:.2f}" + r" \\"]
for ad in ("15:37 (test 3)", "16:30 (sizin deneme)"):
    v = sc[ad]
    satir.append(f"18 Kasım {ad}, 10 s & {v['n']} & {v['medyan_10s']:.2f} & "
                 f"{v['ustu_0p6']} / {v['n']} & {v['ustu_0p9']} / {v['n']}" + r" \\")
(CIKTI / "tablo_sicrama.tex").write_text("\n".join(satir) + "\n", encoding="utf-8")
