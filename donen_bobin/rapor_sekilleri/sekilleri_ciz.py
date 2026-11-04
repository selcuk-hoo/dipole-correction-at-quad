"""Rapor şekilleri: donen_bobin/olcumler/ham_*.csv dosyalarından."""
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

KOK = Path("/home/selcuk/projeler/dipole-correction-at-quad/donen_bobin")
sys.path.insert(0, str(KOK / "host"))
from mgf import merkezleme_koprusu as mk  # noqa: E402

O = KOK / "olcumler"
CIKTI = KOK / "rapor_sekilleri"
CIKTI.mkdir(exist_ok=True)
SPS = 7200.0
p = mk.parametreleri_yukle(None)
K1 = p.bobin.sarim_sayisi * p.bobin.uzunluk_m * abs(p.bobin.duyarlilik(1, p.r_ref_m))

MAVI, TURUNCU, CAMGOBEGI = "#2a78d6", "#eb6834", "#1baf7a"
YAZI, YAZI2, IZGARA, ZEMIN = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"
plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 9, "axes.edgecolor": YAZI2,
    "axes.labelcolor": YAZI, "xtick.color": YAZI2, "ytick.color": YAZI2,
    "axes.grid": True, "grid.color": IZGARA, "grid.linewidth": 0.6,
    "axes.spines.top": False, "axes.spines.right": False,
    "figure.facecolor": "white", "axes.facecolor": ZEMIN, "lines.linewidth": 1.4,
    "legend.frameon": False, "savefig.dpi": 200, "savefig.bbox": "tight",
})


def yukle(ad):
    t, a, v = np.loadtxt(O / ad, delimiter=",", comments="#", skiprows=11).T
    return t, a, v


def spektrum(v):
    v = v - v.mean()
    h = np.hanning(len(v))
    return np.fft.rfftfreq(len(v), 1 / SPS), np.abs(np.fft.rfft(v * h)) * 2 / h.sum()


def tepe(v, f0, tol=0.3):
    fr, s = spektrum(v)
    k = np.argmax(np.where(abs(fr - f0) < tol, s, 0))
    return fr[k], s[k]


# 1) Ham gerilim: motor dururken ve 7 Hz'de (üstte mutlak, altta ortalaması çıkarılmış)
fig, (ust, alt) = plt.subplots(2, 1, figsize=(6.4, 4.4), sharex=True, gridspec_kw={"height_ratios": [1, 1.3]})
for ad, renk, etiket in [("ham_2026-11-04_113419.csv", MAVI, "Motor duruyor"),
                         ("ham_2026-11-04_113529.csv", TURUNCU, "Motor 7 Hz'de dönüyor")]:
    t, _, v = yukle(ad)
    m = t >= -0.5
    ust.plot(t[m] + 0.5, v[m] * 1e3, color=renk, lw=0.9, label=etiket)
    alt.plot(t[m] + 0.5, (v[m] - v[m].mean()) * 1e6, color=renk, lw=0.9, label=etiket)
ust.axhline(0, color=YAZI2, lw=0.8, ls="--")
ust.text(0.495, -0.15, "0 V", color=YAZI2, va="top", ha="right", fontsize=8)
ust.set_ylim(-5.2, 0.5)
ust.set_ylabel("Gerilim (mV)")
ust.set_title("Ham ADC gerilimi: yaklaşık −4.59 mV sabit ofset (üst), ofset çıkarılmış hâli (alt)", loc="left", color=YAZI, fontsize=9)
ust.legend(loc="center right")
alt.set_xlim(0, 0.5)
alt.set_xlabel("Zaman (s)")
alt.set_ylabel("Ortalamadan sapma (µV)")
fig.savefig(CIKTI / "1_ham_gerilim.png")
plt.close(fig)

# 2) Spektrum: dururken, 7 Hz, 23 Hz (ilk 8 s)
fig, ax = plt.subplots(figsize=(6.4, 3.0))
t23, _, v23 = yukle("ham_2026-11-04_114836.csv")
for v, renk, etiket in [(yukle("ham_2026-11-04_113419.csv")[2], MAVI, "Motor duruyor"),
                        (yukle("ham_2026-11-04_113529.csv")[2], TURUNCU, "7 Hz"),
                        (v23[t23 < -2], CAMGOBEGI, "23 Hz")]:
    fr, s = spektrum(v)
    m = (fr > 0.5) & (fr < 110)
    ax.semilogy(fr[m], s[m] * 1e6, color=renk, lw=0.9, label=etiket)
for f, y, yazi in [(7.0, 130, "7 Hz dönme"), (23.1, 400, "23 Hz dönme"), (50, 30, "50 Hz şebeke"),
                   (70.2, 45, "70 Hz = 10×7 Hz"), (100, 12, "100 Hz")]:
    ax.annotate(yazi, (f, y), ha="center", fontsize=7, color=YAZI2)
ax.set_xlim(0, 110)
ax.set_ylim(0.05, 2000)
ax.set_xlabel("Frekans (Hz)")
ax.set_ylabel("Genlik (µV, tepe)")
ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.2), ncol=3)
ax.set_title("Gerilim spektrumu", loc="left", color=YAZI)
fig.savefig(CIKTI / "2_spektrum.png")
plt.close(fig)

# 3) Dönme frekansındaki gerilim ve hız (yalnızca hızın sabit olduğu bölümler)
noktalar = []
for ad, t0, t1, f0 in [("ham_2026-11-04_113529.csv", -1.0, 0.01, 7.0),
                       ("ham_2026-11-04_115612.csv", -10, 0.01, 8.0),
                       ("ham_2026-11-04_120700.csv", -7, 0.01, 13.03),
                       ("ham_2026-11-04_114836.csv", -10, -2, 23.14)]:
    t, _, v = yukle(ad)
    m = (t >= t0) & (t < t1)
    noktalar.append(tepe(v[m], f0))
noktalar = np.array(noktalar)
B_ort = float(np.mean(noktalar[:, 1] / (K1 * 2 * np.pi * noktalar[:, 0])))
fig, ax = plt.subplots(figsize=(4.6, 3.0))
x = np.linspace(0, 25, 50)
ax.plot(x, K1 * 2 * np.pi * x * B_ort * 1e6, color=YAZI2, lw=1, ls="--")
ax.text(15.3, K1 * 2 * np.pi * 15 * B_ort * 1e6 - 20, f"sabit alan\n{B_ort * 1e6:.0f} µT", color=YAZI2, fontsize=8, va="top")
ax.plot(noktalar[:, 0], noktalar[:, 1] * 1e6, "o", color=MAVI, ms=7, mec="white", mew=1.5)
for (f, s), (dx, dy, ha) in zip(noktalar, [(8, -22, "left"), (-8, 6, "right"), (-8, 6, "right"), (-8, 6, "right")]):
    ax.annotate(f"{f:.0f} Hz: {s * 1e6:.0f} µV\n→ {s / (K1 * 2 * np.pi * f) * 1e6:.0f} µT", (f, s * 1e6),
                xytext=(dx, dy), textcoords="offset points", ha=ha, fontsize=7.5, color=YAZI)
ax.set_xlim(0, 25)
ax.set_ylim(0, 280)
ax.set_xlabel("Dönme hızı (Hz)")
ax.set_ylabel("Dönme frekansındaki gerilim (µV)")
ax.set_title("Gerilim hızla orantılı: alan gerçek", loc="left", color=YAZI)
fig.savefig(CIKTI / "3_hiz_gerilim.png")
plt.close(fig)
print("hız-gerilim noktaları:", [(round(f, 2), round(s * 1e6, 1), round(s / (K1 * 2 * np.pi * f) * 1e6, 1)) for f, s in noktalar], "ortalama", round(B_ort * 1e6, 1))


# 4) Enkoder bozulması ve hız
def enkoder(ad):
    t, a, _ = yukle(ad)
    taze = np.flatnonzero(np.diff(a) != 0) + 1
    dn = np.diff(taze)
    da = (np.diff(a[taze]) + 180) % 360 - 180
    f = float(np.median(da / (dn / SPS) / 360))
    bozuk = np.abs(da - f * 360 * dn / SPS) > 15
    f = float(np.sum(da[~bozuk]) / np.sum(dn[~bozuk]) * SPS / 360)  # tutarlı okumalardan ortalama hız
    return f, 100 * bozuk.mean(), 100 * np.mean(dn > 9), t, taze, bozuk


once = [enkoder(a) for a in ["ham_2026-11-04_113529.csv", "ham_2026-11-04_115612.csv", "ham_2026-11-04_115710.csv",
                             "ham_2026-11-04_115741.csv", "ham_2026-11-04_114822.csv"]]
sonra = enkoder("ham_2026-11-04_120700.csv")
fig, ax = plt.subplots(figsize=(4.8, 3.0))
ax.plot([o[0] for o in once], [o[1] for o in once], "-o", color=MAVI, ms=7, mec="white", mew=1.5, label="Kablo sabitlenmeden önce")
ax.plot([sonra[0]], [sonra[1]], "s", color=TURUNCU, ms=8, mec="white", mew=1.5, label="Beyaz kablo sabitlendikten sonra")
for o in once[2:]:
    ax.annotate(f"%{o[1]:.1f}", (o[0], o[1]), xytext=(-4, 7), textcoords="offset points", ha="right", fontsize=7.5)
ax.annotate("%0.0 (7 ve 8 Hz)", (7.5, 0), xytext=(0, 9), textcoords="offset points", ha="center", fontsize=7.5)
ax.annotate(f"%{sonra[1]:.2f}", (sonra[0], sonra[1]), xytext=(10, -3), textcoords="offset points", fontsize=7.5)
ax.set_xlim(0, 25)
ax.set_ylim(0, 11)
ax.set_xlabel("Dönme hızı (Hz)")
ax.set_ylabel("Tutarsız enkoder okuması (%)")
ax.legend(loc="upper left")
ax.set_title("Enkoder açısındaki bozulma hızla artıyor", loc="left", color=YAZI)
fig.savefig(CIKTI / "4_enkoder_hiz.png")
plt.close(fig)
print("enkoder:", [(round(o[0], 2), round(o[1], 2), round(o[2], 1)) for o in once], "sonra", (round(sonra[0], 2), round(sonra[1], 2), round(sonra[2], 1)))

# 5) 13 Hz kaydında saniye saniye tutarsız okuma
_, _, _, t, taze, bozuk = sonra
tz = t[taze[1:]]
sayilar = [int(np.sum(bozuk[(tz >= s) & (tz < s + 1)])) for s in range(-10, 0)]
fig, ax = plt.subplots(figsize=(5.2, 2.6))
ax.bar(np.arange(-10, 0) + 0.5, sayilar, width=0.8, color=MAVI)
for s, n in zip(range(-10, 0), sayilar):
    ax.text(s + 0.5, n + 0.3, str(n), ha="center", fontsize=7.5)
ax.axvspan(-10, -8, color=IZGARA, alpha=0.6, lw=0)
ax.text(-9, 13.2, "hız oturuyor", ha="center", fontsize=7.5, color=YAZI2)
ax.set_xlim(-10, 0)
ax.set_ylim(0, 14.5)
ax.set_xlabel("Zaman (s, kaydın sonu 0)")
ax.set_ylabel("Tutarsız okuma (adet/s)")
ax.set_title("13 Hz, kablo sabitlendikten sonra: hatalar kümeler halinde", loc="left", color=YAZI)
fig.savefig(CIKTI / "5_13hz_saniye.png")
plt.close(fig)
print("13 Hz saniye:", sayilar)

# 6) Bobin akısı: 8 Hz, 10 s (açıya karşı) ve uydurma
t, a, v = yukle("ham_2026-11-04_115612.csv")
s = mk.olcum_hesapla(a, v, SPS, p.bobin, p.r_ref_m)
fig, ax = plt.subplots(figsize=(6.0, 2.8))
adim = max(1, len(s.aci_derece) // 6000)
ax.plot(s.aci_derece[::adim], s.aki_Vs[::adim] * 1e6, "o", ms=1.2, color=MAVI, alpha=0.25, mew=0, label="Ölçülen akı (80 tur)")
izgara = np.linspace(0, 360, 721)
ax.plot(izgara, s.uydurma(izgara) * 1e6, color=TURUNCU, lw=1.8, label="Uydurulan harmonikler")
ax.set_xlim(0, 360)
ax.set_xticks(range(0, 361, 45))
ax.set_xlabel("Açı (°)")
ax.set_ylabel("Akı (µV·s)")
ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.2), ncol=2, markerscale=6)
ax.set_title("Bobin akısı, 8 Hz, 10 s (80 tur üst üste)", loc="left", color=YAZI)
fig.savefig(CIKTI / "6_aki_8hz.png")
plt.close(fig)
print("8 Hz akı: artık", round(s.artik_orani, 3), "C:", [round(abs(c) * 1e6, 2) for c in s.harmonikler])
