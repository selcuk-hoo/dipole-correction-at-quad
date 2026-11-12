"""12 Kasım 2026 uzun kararlılık ölçümünün analizi: bölümleri birleştirir, şekil ve sayı üretir.

    cd donen_bobin/host && python uzun_kararlilik_analiz.py [--cikti kayitlar/uzun_kararlilik_2026-11-12/rapor]

Girdi: oturum klasörlerindeki uzun_kararlilik.csv'ler (aşağıdaki FAZLAR tablosu). Çıktı:
sonuclar.json (raporda geçen bütün sayılar) ve şekiller (PDF, vektör).

Net merkez iki yolla hesaplanır:
  * önceki: akımlı fazdan hemen önceki akımsız fazın ortalama alanı çıkarılır (ölçüm sırasında
    kullanılan yol)
  * ara değer: akımlı fazı çevreleyen iki akımsız fazın ortalamaları arasında zamana göre
    doğrusal ara değer çıkarılır (ortam alanının faz boyunca kaymasını da düzeltir)
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from datetime import datetime
from pathlib import Path

import numpy as np

KOK = Path(__file__).resolve().parents[2]
K = KOK / "kayitlar"
# (oturum, betikteki faz adı) -> rapordaki ad. 2026-11-12_101134 kısa denemedir, katılmaz.
FAZLAR = [
    ("2026-11-12_103042", "ortam1", "O1"),
    ("2026-11-12_120020", "ortam1", "O2"),
    ("2026-11-12_120020", "akimli1", "A1"),
    ("2026-11-12_120020", "ortam2", "O3"),
    ("2026-11-12_150000", "ortam1", "O4"),
    ("2026-11-12_150645", "ortam1", "O5"),
    ("2026-11-12_150645", "akimli2", "A2"),
    ("2026-11-12_150645", "ortam3", "O6"),
]
# Akımlı faz -> (önceki akımsız, sonraki akımsız)
CEVRE = {"A1": ("O2", "O3"), "A2": ("O5", "O6")}
R_REF_M = 0.025
MAVI, TURUNCU = "#2a78d6", "#eb6834"   # dataviz varsayılan paleti, sıra 1-2 (doğrulandı)
YAZI, IKINCIL, IZGARA, YUZEY = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"


def oku() -> dict[str, dict[str, np.ndarray]]:
    fazlar: dict[str, dict[str, np.ndarray]] = {}
    for oturum, faz, ad in FAZLAR:
        yol = K / oturum / "uzun_kararlilik.csv"
        if not yol.exists():
            continue
        satirlar = [r for r in csv.DictReader(open(yol, encoding="utf-8")) if r["faz"] == faz]
        if not satirlar:
            continue
        d = {k: np.array([float(r[k]) if r[k] not in ("", "nan") else math.nan for r in satirlar])
             for k in ("B1_uT", "A1_uT", "B2_mT", "A2_mT", "x_net_um", "y_net_um", "n_olcum",
                       "I1_A", "I2_A", "I3_A", "I4_A", "artik_orani", "ayiklanan_aci")}
        d["t"] = np.array([datetime.fromisoformat(r["zaman"]).timestamp() for r in satirlar])
        fazlar[ad] = d
    return fazlar


def egim_saat(t_s: np.ndarray, v: np.ndarray) -> tuple[float, float]:
    """Doğrusal eğim (birim/saat) ve 1σ belirsizliği."""
    m = np.isfinite(v)
    if m.sum() < 4:
        return math.nan, math.nan
    p, c = np.polyfit((t_s[m] - t_s[m][0]) / 3600, v[m], 1, cov=True)
    return float(p[0]), float(math.sqrt(c[0, 0]))


def ardisik_sigma(v: np.ndarray) -> float:
    """Ardışık kayıt farklarından gürültü (yavaş kaymadan bağımsız): std(fark)/√2."""
    d = np.diff(v[np.isfinite(v)])
    return float(np.std(d, ddof=1) / math.sqrt(2)) if len(d) > 2 else math.nan


def net_merkez(d, bg1: np.ndarray | complex, bg2: np.ndarray | complex) -> np.ndarray:
    c1 = (d["B1_uT"] + 1j * d["A1_uT"]) * 1e-6
    c2 = (d["B2_mT"] + 1j * d["A2_mT"]) * 1e-3
    return -R_REF_M * (c1 - bg1) / (c2 - bg2) * 1e6  # µm


def ortalama_alan(d, son_s: float | None = None, ilk_s: float | None = None) -> tuple[complex, complex, float]:
    m = np.ones(len(d["t"]), bool)
    if son_s:
        m &= d["t"] >= d["t"][-1] - son_s
    if ilk_s:
        m &= d["t"] <= d["t"][0] + ilk_s
    c1 = complex(np.mean(d["B1_uT"][m]), np.mean(d["A1_uT"][m])) * 1e-6
    c2 = complex(np.mean(d["B2_mT"][m]), np.mean(d["A2_mT"][m])) * 1e-3
    return c1, c2, float(np.mean(d["t"][m]))


def isinma_uydur(t_dk: np.ndarray, v: np.ndarray) -> dict[str, float]:
    """v(t) = a + b (1 - exp(-t/τ)). Uymazsa nan."""
    from scipy.optimize import curve_fit

    m = np.isfinite(v)

    def f(t, a, b, tau):
        return a + b * (1 - np.exp(-t / tau))

    try:
        p, c = curve_fit(f, t_dk[m], v[m], p0=(v[m][:30].mean(), v[m][-60:].mean() - v[m][:30].mean(), 15.0),
                         bounds=([-500, -500, 0.5], [500, 500, 300]), maxfev=20000)
        e = np.sqrt(np.diag(c))
        artik = v[m] - f(t_dk[m], *p)
        return {"a_um": p[0], "b_um": p[1], "tau_dk": p[2], "sa_um": e[0], "sb_um": e[1], "stau_dk": e[2],
                "artik_sigma_um": float(np.std(artik, ddof=3))}
    except Exception:  # noqa: BLE001
        return {k: math.nan for k in ("a_um", "b_um", "tau_dk", "sa_um", "sb_um", "stau_dk", "artik_sigma_um")}


def analiz(f: dict) -> dict:
    s: dict = {"fazlar": {}}
    t0 = min(d["t"][0] for d in f.values())
    for ad, d in f.items():
        r = {"bas": datetime.fromtimestamp(d["t"][0]).strftime("%H:%M"),
             "son": datetime.fromtimestamp(d["t"][-1]).strftime("%H:%M"),
             "sure_dk": (d["t"][-1] - d["t"][0]) / 60 + 1 / 6, "kayit": len(d["t"]),
             "olcum_kayit_basi": float(np.median(d["n_olcum"])),
             "ayiklanan_aci_dk": float(np.sum(d["ayiklanan_aci"]) / ((d["t"][-1] - d["t"][0]) / 60 + 1 / 6))}
        for k in ("B1_uT", "A1_uT"):
            e, se = egim_saat(d["t"], d[k])
            r[k] = {"ort": float(np.mean(d[k])), "sigma": float(np.std(d[k], ddof=1)),
                    "ardisik_sigma": ardisik_sigma(d[k]), "egim_saat": e, "egim_hata": se}
        if ad.startswith("A"):
            I = np.vstack([d[f"I{i}_A"] for i in range(1, 5)])
            r["akimlar"] = {"ort_A": np.nanmean(I, axis=1).tolist(), "sigma_mA": (np.nanstd(I, axis=1) * 1e3).tolist(),
                            "tepe_tepe_mA": ((np.nanmax(I, axis=1) - np.nanmin(I, axis=1)) * 1e3).tolist()}
            r["artik_orani_medyan"] = float(np.nanmedian(d["artik_orani"]))
        s["fazlar"][ad] = r

    # Ortam alanı: bütün akımsız kayıtlar, gün boyu
    O = [ad for ad in f if ad.startswith("O")]
    t = np.concatenate([f[ad]["t"] for ad in O])
    s["ortam_gun"] = {}
    for k in ("B1_uT", "A1_uT"):
        v = np.concatenate([f[ad][k] for ad in O])
        e, se = egim_saat(t[np.argsort(t)], v[np.argsort(t)])
        s["ortam_gun"][k] = {"egim_saat": e, "egim_hata": se, "aralik": float(np.ptp([s["fazlar"][a][k]["ort"] for a in O]))}

    # Akımlı fazlar: iki arka plan yolu, ısınma uydurması, aynı sürede karşılaştırma
    s["akimli"] = {}
    for A, (once, sonra) in CEVRE.items():
        if A not in f or once not in f:
            continue
        d = f[A]
        tdk = (d["t"] - d["t"][0]) / 60
        b1, b2, _ = ortalama_alan(f[once], son_s=600)
        z_once = net_merkez(d, b1, b2)
        r = {"once": {}, "ara": None}
        yol = {"once": z_once}
        if sonra in f:
            c1a, c2a, ta = ortalama_alan(f[once], son_s=600)
            c1b, c2b, tb = ortalama_alan(f[sonra], ilk_s=600)
            w = np.clip((d["t"] - ta) / (tb - ta), 0, 1)
            yol["ara"] = net_merkez(d, c1a + w * (c1b - c1a), c2a + w * (c2b - c2a))
            r["ara"] = {}
            r["arka_plan_farki_uT"] = abs(c1b - c1a) * 1e6
        for ad_yol, z in yol.items():
            q = r[ad_yol]
            for eksen, v in (("x", z.real), ("y", z.imag)):
                e, se = egim_saat(d["t"], v)
                bloklar = [[float(b), float(np.mean(v[(tdk >= b) & (tdk < b + 10)]))] for b in range(0, int(tdk[-1]) + 1, 10)
                           if np.any((tdk >= b) & (tdk < b + 10))]
                q[eksen] = {"ort": float(np.mean(v)), "sigma": float(np.std(v, ddof=1)), "ardisik_sigma": ardisik_sigma(v),
                            "egim_saat": e, "egim_hata": se, "bloklar_10dk": bloklar,
                            "son30_ort": float(np.mean(v[tdk >= tdk[-1] - 30])),
                            "pencere_40_60": float(np.mean(v[(tdk >= 40) & (tdk < 60)])) if tdk[-1] >= 50 else math.nan,
                            "isinma": isinma_uydur(tdk, v)}
        s["akimli"][A] = r
    if "A1" in s["akimli"] and "A2" in s["akimli"]:
        s["histerezis"] = {e: s["akimli"]["A2"]["once"][e]["pencere_40_60"] - s["akimli"]["A1"]["once"][e]["pencere_40_60"]
                           for e in ("x", "y")}
    s["t0"] = datetime.fromtimestamp(t0).isoformat(timespec="minutes")
    return s


def sekiller(f: dict, cikti: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.dates import DateFormatter

    plt.rcParams.update({"font.size": 9, "axes.edgecolor": IKINCIL, "axes.labelcolor": YAZI, "xtick.color": IKINCIL,
                         "ytick.color": IKINCIL, "axes.facecolor": YUZEY, "figure.facecolor": "white",
                         "axes.grid": True, "grid.color": IZGARA, "grid.linewidth": 0.6, "axes.spines.top": False,
                         "axes.spines.right": False, "legend.frameon": False, "lines.linewidth": 2})

    # Şekil 1: ortam alanı gün boyu (günün ortalamasından sapma), akımlı dönemler gri
    O = [ad for ad in f if ad.startswith("O")]
    fig, ax = plt.subplots(figsize=(6.4, 2.8))
    for k, renk, ad in (("B1_uT", MAVI, "B₁"), ("A1_uT", TURUNCU, "A₁")):
        ort = np.mean(np.concatenate([f[o][k] for o in O]))
        for i, o in enumerate(O):
            zaman = [datetime.fromtimestamp(x) for x in f[o]["t"]]
            ax.plot(zaman, f[o][k] - ort, color=renk, lw=0.5, alpha=0.3)
            n = 6  # 1 dk'lık ortalama (6 kayıt)
            v = f[o][k] - ort
            m = len(v) // n
            if m:
                ax.plot([datetime.fromtimestamp(x) for x in f[o]["t"][: m * n].reshape(m, n).mean(1)],
                        v[: m * n].reshape(m, n).mean(1), color=renk, lw=2,
                        label=f"{ad} (ortalama {ort:+.2f} µT)" if i == 0 else None)
    for A in ("A1", "A2"):
        if A in f:
            ax.axvspan(datetime.fromtimestamp(f[A]["t"][0]), datetime.fromtimestamp(f[A]["t"][-1]),
                       color=IZGARA, alpha=0.7, lw=0)
            ax.text(datetime.fromtimestamp((f[A]["t"][0] + f[A]["t"][-1]) / 2), 0.95, f"akım açık ({A})",
                    transform=ax.get_xaxis_transform(), ha="center", va="top", color=IKINCIL, fontsize=8)
    ax.set_ylabel("ortalamadan sapma (µT)")
    ax.xaxis.set_major_formatter(DateFormatter("%H:%M"))
    ax.legend(loc="lower center", bbox_to_anchor=(0.5, 1.0), ncols=2, fontsize=8)
    fig.tight_layout()
    fig.savefig(cikti / "sekil1_ortam.pdf")
    plt.close(fig)

    # Şekil 2-3: net merkez x ve y, akım açıldıktan sonra geçen süreye göre, A1 ve A2 üst üste
    for eksen, no in (("x", 2), ("y", 3)):
        fig, ax = plt.subplots(figsize=(6.4, 2.8))
        for A, renk in (("A1", MAVI), ("A2", TURUNCU)):
            if A not in f:
                continue
            once = CEVRE[A][0]
            b1, b2, _ = ortalama_alan(f[once], son_s=600)
            z = net_merkez(f[A], b1, b2)
            v = z.real if eksen == "x" else z.imag
            tdk = (f[A]["t"] - f[A]["t"][0]) / 60
            ax.plot(tdk, v, color=renk, lw=0.6, alpha=0.35)
            b = np.arange(0, tdk[-1] + 5, 5)
            orta = [(b0 + 2.5, np.mean(v[(tdk >= b0) & (tdk < b0 + 5)])) for b0 in b if np.any((tdk >= b0) & (tdk < b0 + 5))]
            ax.plot(*zip(*orta), color=renk, lw=2, marker="o", ms=4, label=f"{A} (5 dk ortalaması)")
        ax.axhline(0, color=IKINCIL, lw=0.8)
        ax.set_xlabel("akımlar açıldıktan sonra geçen süre (dk)")
        ax.set_ylabel(f"net {eksen}$_c$ (µm)")
        ax.legend(loc="best")
        fig.tight_layout()
        fig.savefig(cikti / f"sekil{no}_{eksen}.pdf")
        plt.close(fig)


def sekil_zaman_cizelgesi(f: dict, cikti: Path) -> None:
    """Net merkez x ve y, saate göre: soğumadan sonra merkezin kaldığı yerden devam ettiğini gösterir."""
    import matplotlib.pyplot as plt
    from matplotlib.dates import DateFormatter

    fig, ax = plt.subplots(figsize=(6.4, 2.8))
    for eksen, renk in (("x", MAVI), ("y", TURUNCU)):
        ilk = True
        for A in ("A1", "A2"):
            if A not in f:
                continue
            b1, b2, _ = ortalama_alan(f[CEVRE[A][0]], son_s=600)
            z = net_merkez(f[A], b1, b2)
            v = z.real if eksen == "x" else z.imag
            t = f[A]["t"]
            n = 30  # 5 dk
            m = len(v) // n
            ax.plot([datetime.fromtimestamp(x) for x in t], v, color=renk, lw=0.5, alpha=0.3)
            ax.plot([datetime.fromtimestamp(x) for x in t[: m * n].reshape(m, n).mean(1)],
                    v[: m * n].reshape(m, n).mean(1), color=renk, lw=2, marker="o", ms=3,
                    label=f"net {eksen}$_c$ (5 dk ortalaması)" if ilk else None)
            ilk = False
    if "A1" in f and "A2" in f:
        ax.axvspan(datetime.fromtimestamp(f["A1"]["t"][-1]), datetime.fromtimestamp(f["A2"]["t"][0]),
                   color=IZGARA, alpha=0.7, lw=0)
        ax.text(datetime.fromtimestamp((f["A1"]["t"][-1] + f["A2"]["t"][0]) / 2), 0.95,
                "akım kapalı\n(soğuma, ~2 sa)", transform=ax.get_xaxis_transform(), ha="center", va="top",
                color=IKINCIL, fontsize=8)
    ax.axhline(0, color=IKINCIL, lw=0.8)
    ax.set_ylabel("µm")
    ax.xaxis.set_major_formatter(DateFormatter("%H:%M"))
    ax.legend(loc="lower center", bbox_to_anchor=(0.5, 1.0), ncols=2, fontsize=8)
    fig.tight_layout()
    fig.savefig(cikti / "sekil4_zaman.pdf")
    plt.close(fig)


def main() -> int:
    a = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    a.add_argument("--cikti", default=str(K / "uzun_kararlilik_2026-11-12" / "rapor"))
    g = a.parse_args()
    cikti = Path(g.cikti)
    cikti.mkdir(parents=True, exist_ok=True)
    f = oku()
    s = analiz(f)
    (cikti / "sonuclar.json").write_text(json.dumps(s, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    sekiller(f, cikti)
    sekil_zaman_cizelgesi(f, cikti)
    print(json.dumps({ad: (r["bas"], r["son"], r["kayit"]) for ad, r in s["fazlar"].items()}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
