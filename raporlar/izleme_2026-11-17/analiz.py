"""17 Kasım 2026 izleme kayıtlarının analizi.

Merkez sürüklenmesi, ham dipol, gradyen, bobin direnci (ısınma), arka plan saçılımı
ve güç kaynağı akımları. Raporun bütün sayıları buradan gelir: `sonuclar.json`.
Çalıştırma: python3 raporlar/izleme_2026-11-17/analiz.py
"""
import json
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd
from scipy.optimize import curve_fit

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

KOK = Path(__file__).resolve().parents[2]
K = KOK / "kayitlar/2026-11-17_103703"
CIKTI = Path(__file__).resolve().parent
MAVI, TURUNCU = "#2a78d6", "#eb6834"
ALFA_BAKIR = 0.00393  # 1/K, bakırın direnç sıcaklık katsayısı

IZLEMELER = {
    "izleme1": ("2026-11-17 10:53", "2026-11-17 13:16:45", K / "izleme_105259.csv",
                KOK / "calistirmalar/2026-11-17_104609"),
    "izleme2": ("2026-11-17 13:25", "2026-11-17 16:52", K / "izleme_132526.csv",
                KOK / "calistirmalar/2026-11-17_131846"),
}
BASLIK = {"izleme1": "1. izleme (10:53–13:16, soğuk başladı)",
          "izleme2": "2. izleme (13:25–16:51, sıcak başladı)"}


def ustel(t, a, b, tau):
    return a + b * (1 - np.exp(-t / tau))


o = pd.read_csv(K / "olcumler.csv", parse_dates=["zaman"])
s = o[o.tur == "surekli"].set_index("zaman")
sonuc: dict = {}

fig, ax = plt.subplots(3, 2, figsize=(11, 9), sharex="col", sharey="row")
for j, (ad, (bas, son, dosya, calisma)) in enumerate(IZLEMELER.items()):
    r: dict = {}
    iz = pd.read_csv(dosya, parse_dates=["zaman"])
    t_dk = iz.gecen_dk.values
    r["kayit_sayisi"] = len(iz)
    r["sure_dk"] = round(float(t_dk[-1]), 1)
    for c in ["x_c_um", "y_c_um"]:
        y = iz[c].values
        p, kov = np.polyfit(t_dk / 60, y, 1, cov=True)
        k = {"ilk15": y[t_dk < 15].mean(), "son15": y[t_dk > t_dk[-1] - 15].mean(),
             "egim_um_sa": p[0], "egim_hata": np.sqrt(kov[0, 0]),
             "ardisik_gurultu": np.std(np.diff(y), ddof=1) / np.sqrt(2)}
        try:
            pu, ku = curve_fit(ustel, t_dk, y, p0=[y[0], k["son15"] - k["ilk15"], 60], maxfev=20000)
            if 1 < pu[2] < 1000:
                k["ustel_genlik"], k["ustel_tau_dk"] = pu[1], pu[2]
                k["ustel_tau_hata"] = np.sqrt(ku[2, 2])
        except RuntimeError:
            pass
        r[c] = {a: round(float(v), 2) for a, v in k.items()}

    ham = s[bas:son]
    dk = ham.resample("1min").mean(numeric_only=True)
    for c, n in [("b1_T", "B1"), ("a1_T", "A1")]:
        r[f"ham_{n}_ilk15_uT"] = round(float(dk[c].iloc[:15].mean() * 1e6), 2)
        r[f"ham_{n}_son15_uT"] = round(float(dk[c].iloc[-15:].mean() * 1e6), 2)
    g = dk.G_T_m
    g0 = g.iloc[:10].mean()
    r["G_ilk15"] = round(float(g.iloc[:15].mean()), 6)
    r["G_son15"] = round(float(g.iloc[-15:].mean()), 6)
    r["G_tepe_ppm"] = round(float((g.max() / g0 - 1) * 1e6))
    r["G_tepe_dk"] = round(float((g.idxmax() - g.index[0]).total_seconds() / 60))
    r["G_son_ppm"] = round(float((g.iloc[-10:].mean() / g0 - 1) * 1e6))

    # Akımlar: okuma iş parçacığı bir süre sonra hep NaN yazmış
    v = iz[iz.I1_A.notna()]
    akim = v[["I1_A", "I2_A", "I3_A", "I4_A"]]
    r["akim_okuma_son"] = f"{v.zaman.iloc[-1]:%H:%M}"
    r["akim_okuma_dk"] = round(float(v.gecen_dk.iloc[-1]), 1)
    r["akim_fark_mA"] = [round(float(x), 3) for x in (akim.tail(12).mean() - akim.head(12).mean()) * 1e3]
    toplam = akim.sum(axis=1)
    r["akim_toplam_ppm"] = round(float((toplam.tail(12).mean() / toplam.head(12).mean() - 1) * 1e6))
    ga = s[v.zaman.iloc[0]:v.zaman.iloc[-1]].G_T_m
    r["G_ayni_aralik_ppm"] = round(float((ga.tail(30).mean() / ga.head(30).mean() - 1) * 1e6))

    # Merkezleme çalıştırması: bobin direnci (U/I) ve akımsız arka plan saçılımı
    c = pd.read_csv(calisma / "olcumler.csv")
    arka = c[c.adim_turu == "arka_plan"]
    akimli = c[c.adim_turu != "arka_plan"]
    R = (akimli[[f"olculen_U{i}_V" for i in range(1, 5)]].values
         / akimli[[f"olculen_I{i}_A" for i in range(1, 5)]].values)
    r["R_ilk_ohm"] = [round(float(x), 4) for x in R[0]]
    r["R_son_ohm"] = [round(float(x), 4) for x in R[-1]]
    r["R_ort_ilk"] = round(float(R[0].mean()), 4)
    r["R_ort_son"] = round(float(R[-1].mean()), 4)
    r["arka_plan_n"] = len(arka)
    r["arka_plan_ort_uT"] = [round(float(x), 2) for x in arka[["ham_B1", "ham_A1"]].mean() * 1e6]
    r["arka_plan_std_uT"] = [round(float(x), 2) for x in arka[["ham_B1", "ham_A1"]].std() * 1e6]
    r["arka_plan_son_uT"] = [round(float(x), 2) for x in arka[["ham_B1", "ham_A1"]].iloc[-1] * 1e6]
    r["merkezleme_son_um"] = [round(float(x), 1) for x in akimli[["x_c_um", "y_c_um"]].iloc[-1]]
    sonuc[ad] = r

    izd = iz.set_index("zaman")[["x_c_um", "y_c_um"]].resample("1min").mean()
    tizd = (izd.index - iz.zaman.iloc[0]).total_seconds() / 60
    t = (dk.index - dk.index[0]).total_seconds() / 60
    ax[0, j].plot(tizd, izd.x_c_um, color=MAVI, lw=1.5, label="$x_c$")
    ax[0, j].plot(tizd, izd.y_c_um, color=TURUNCU, lw=1.5, label="$y_c$")
    ax[0, j].set_title(BASLIK[ad], fontsize=11)
    ax[1, j].plot(t, (dk.b1_T - dk.b1_T.iloc[:10].mean()) * 1e6, color=MAVI, lw=1.5, label="B1")
    ax[1, j].plot(t, (dk.a1_T - dk.a1_T.iloc[:10].mean()) * 1e6, color=TURUNCU, lw=1.5, label="A1")
    ax[2, j].plot(t, (g / g0 - 1) * 1e6, color=MAVI, lw=1.5)
    ax[2, j].axvline(r["akim_okuma_dk"], color="0.5", lw=1, ls="--")
    ax[2, j].text(r["akim_okuma_dk"] + 2, ax[2, j].get_ylim()[0] if j else -750,
                  "akım okuması\nburada kesildi", fontsize=8, color="0.35", va="bottom")

R1, R2 = sonuc["izleme1"]["R_ort_ilk"], sonuc["izleme2"]["R_ort_ilk"]
sonuc["isinma_K"] = round((R2 / R1 - 1) / ALFA_BAKIR, 1)
sonuc["direnc_artisi_yuzde"] = round((R2 / R1 - 1) * 100, 1)
arka = np.array([sonuc[a]["arka_plan_ort_uT"] for a in IZLEMELER])
sonuc["arka_plan_fark_uT"] = [round(float(x), 2) for x in arka[1] - arka[0]]
# Merkezin alana duyarlılığı: 1 µT dipol kayması kaç µm? (r_ref = 25 mm)
c2 = abs(complex(s.b2_T.median(), s.a2_T.median()))
sonuc["um_per_uT"] = round(25e-3 / c2, 2)
sonuc["C2_mT"] = round(c2 * 1e3, 3)

# Güç kaynağı okuması (MEAS:CURR?) ile ayar değeri arasındaki fark
def okunan_eksi_ayar(calisma: Path) -> dict:
    c = pd.read_csv(calisma / "olcumler.csv")
    k = c[c.adim_turu != "arka_plan"]
    z = c[c.adim_turu == "arka_plan"]
    d = np.array([(k[f"olculen_I{i}_A"] - k[f"ayar_I{i}_A"]).values * 1e3 for i in range(1, 5)])
    return {"ort_mA": [round(float(x), 2) for x in d.mean(axis=1)],
            "akimsiz_mA": [round(float(z[f"olculen_I{i}_A"].mean() * 1e3), 2) for i in range(1, 5)]}


sonuc["okuma_17kasim"] = {ad: okunan_eksi_ayar(v[3]) for ad, v in IZLEMELER.items()}
# 12 Kasım uzun ölçümü: merkezlenmiş akımlar (CURR'a 4 ondalıkla yazılır) ve 10 s'lik okumalar
AYAR_12 = np.round([9.82836, 9.40981, 9.18835, 9.6069], 4)
u = pd.read_csv(KOK / "kayitlar/2026-11-12_120020/uzun_kararlilik.csv", parse_dates=["zaman"])
u = u[u.faz == "akimli1"]
dI = (u[["I1_A", "I2_A", "I3_A", "I4_A"]] - AYAR_12) * 1e3
saat = (u.zaman - u.zaman.iloc[0]).dt.total_seconds() / 3600
sonuc["okuma_12kasim_akimli1"] = {
    "kayit": len(u),
    "ort_mA": [round(float(x), 2) for x in dI.mean()],
    "ilk10_mA": [round(float(x), 2) for x in dI.head(10).mean()],
    "son10_mA": [round(float(x), 2) for x in dI.tail(10).mean()],
    "egim_mA_sa": [round(float(np.polyfit(saat, dI[c], 1)[0]), 2) for c in dI],
    "en_kucuk_adim_mA": round(float(min(np.diff(np.unique(u[c])).min() for c in ["I1_A", "I2_A", "I3_A", "I4_A"]) * 1e3), 3),
}
# Kalibrasyon: bir bobindeki 1 mA merkezi kaç µm kaydırır (R: m / bağıl akım, nominal 9.5 A)
Rk = np.array(json.loads((IZLEMELER["izleme2"][3] / "kalibrasyon.json").read_text())["R"])
sonuc["um_per_mA"] = [[round(float(x), 2) for x in satir] for satir in Rk[:2] * 1e6 * 1e-3 / 9.5]
sonuc["um_per_mA_en_buyuk"] = round(float(np.abs(Rk[:2]).max() * 1e6 * 1e-3 / 9.5), 2)

for a in ax.flat:
    a.grid(alpha=0.25)
    a.spines[["top", "right"]].set_visible(False)
ax[0, 0].set_ylabel("net merkez, µm")
ax[0, 0].legend(frameon=False)
ax[1, 0].set_ylabel("ham dipol değişimi, µT")
ax[1, 0].legend(frameon=False)
ax[2, 0].set_ylabel("gradyen değişimi, ppm")
for a in ax[2]:
    a.set_xlabel("izleme başından süre, dk")
fig.tight_layout()
fig.savefig(CIKTI / "sekil1_izleme.pdf")
fig.savefig(CIKTI / "izleme_2026-11-17.png", dpi=120)

(CIKTI / "sonuclar.json").write_text(json.dumps(sonuc, indent=2, ensure_ascii=False), encoding="utf-8")
print(json.dumps(sonuc, indent=2, ensure_ascii=False))
