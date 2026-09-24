"""Merkezleme programıyla dosya/kilit tabanlı köprü.

Protokol, `merkezleme/olcum_kaynagi.py:DosyaGirisi` ile birebir aynıdır:
kilit dosyası YOKSA "ölç" sinyali, VARSA "veri hazır" sinyalidir. Bu modül
veriyi üretip kilidi VAR eder (atomik geçici-dosya + rename); kilidin
silinmesi (bir sonraki ölçüm istendiğinde) karşı tarafın (merkezleme'nin)
sorumluluğundadır - bkz. o modülün docstring'i.

Alan hesabı: aynı ("Regular") dönen bobin sinyalinden, açının 1. ve 2.
harmoniği (Fourier) çıkarılır:

    n=1 (dipol, b0/a0)     : magnetic_analysis.py'deki yöntemle birebir aynı.
    n=2 (kuadrupol, b1/a1) : aynı N*A formülünün n=2'ye genellenmesi. EMF
                             genliği ~ N*A*n*omega*B_n olduğundan payda n
                             çarpanı içerir (Faraday yasası, kesin fizik).

    Bobinin n'e göre EK geometrik duyarlılık farkı (bobinin dönme eksenine
    olan mesafesi/aperture'a bağlı - kesin fizik değil, bilinmeyen bir
    donanım detayı) `merkezleme_duyarlilik_n2` sabitiyle KABA olarak temsil
    edilir; varsayılan 1.0 (düzeltme uygulanmaz). merkezleme tarafı yalnızca
    BAĞIL değerlerle (ilk ölçüme göre) çalıştığından, bu sabitteki hata
    düzeltmenin yakınsamasını BOZMAZ; yalnızca merkezleme'nin mutlak mikron
    toleransının gerçek karşılığını kaydırır. Gerekirse empirik olarak
    (bilinen bir ofsetle karşılaştırılarak) ayarlanabilir.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

# repo kökü: .../donen_bobin_surum_24_eylul_2026/host/mgf/bu_dosya.py -> 3 üst
_REPO_KOKU = Path(__file__).resolve().parents[3]
VARSAYILAN_KILIT_YOLU = _REPO_KOKU / "veri_kilidi" / ".kilit"


def harmonik_hesapla(
    enc_deg: np.ndarray,
    adc_v: np.ndarray,
    n: int,
    turns: float,
    area_m2: float,
    omega: float,
    duyarlilik_katsayisi: float = 1.0,
) -> tuple[float, float]:
    """(normal, skew) bileşenlerini `adc_v` sinyalinin n. harmoniğinden hesaplar.

    `magnetic_analysis.py:finish_scan`'deki n=1 dipol formülünün (Bx, By)
    doğrudan genellemesidir; işaret/etiket kuralı da aynıdır: normal = By
    benzeri, skew = Bx benzeri.
    """
    y = adc_v - np.mean(adc_v)
    rad = np.radians(enc_deg)
    a = float(np.sum(y * np.cos(n * rad)))
    b = float(np.sum(y * np.sin(n * rad)))
    olcek = 2.0 / (len(adc_v) * turns * area_m2 * n * omega * duyarlilik_katsayisi)
    skew = b * olcek
    normal = -a * olcek
    return normal, skew


def _adc_volt_donustur(engine, adc: np.ndarray) -> np.ndarray:
    """RAW modda ADC kodlarını Volt'a çevirir; Voltage modunda olduğu gibi bırakır."""
    adc = adc.astype(np.float64)
    if getattr(engine, "current_data_mode", 1) == 0:  # RAW
        vref = getattr(engine, "current_vref", 2.5)
        gain = getattr(engine, "current_gain", 1.0)
        return adc * (vref / (gain * 2147483647.0))
    return adc


def kuadrupol_olcumu_yaz(
    engine,
    turns: float,
    length_mm: float,
    width_mm: float,
    duyarlilik_katsayisi_n2: float = 1.0,
    kilit_yolu: Path | str | None = None,
    scan_duration_s: float = 2.0,
) -> dict:
    """"Regular" bobinden bir tarama alır, n=1/n=2 harmonikleri hesaplar ve
    sonucu `{"b0","a0","b1","a1"}` olarak `kilit_yolu`na atomik biçimde yazar.

    Dönen sözlük, yazılan veridir (loglama/hata ayıklama için).
    """
    if kilit_yolu is None:
        kilit_yolu = VARSAYILAN_KILIT_YOLU
    kilit_yolu = Path(kilit_yolu)

    sps = getattr(engine, "live_rate_sps", 2400.0)
    num_points = max(100, int(scan_duration_s * sps * 1.05))
    enc, adc = engine.get_latest_data(num_points)
    if len(adc) < 100:
        raise RuntimeError("Yetersiz veri: tarama için örnek sayısı çok az")

    raw_enc = (enc + engine.phase_offset_deg) % 360.0
    motor_speed = max(0.01, abs(engine.motor_speed))
    omega = 2.0 * np.pi * motor_speed
    area_m2 = (length_mm * 1e-3) * (width_mm * 1e-3)
    adc_v = _adc_volt_donustur(engine, adc)

    b0, a0 = harmonik_hesapla(raw_enc, adc_v, 1, turns, area_m2, omega)
    b1, a1 = harmonik_hesapla(
        raw_enc, adc_v, 2, turns, area_m2, omega, duyarlilik_katsayisi_n2
    )

    veri = {"b0": b0, "a0": a0, "b1": b1, "a1": a1}

    kilit_yolu.parent.mkdir(parents=True, exist_ok=True)
    gecici = kilit_yolu.with_suffix(".tmp")
    gecici.write_text(json.dumps(veri), encoding="utf-8")
    gecici.replace(kilit_yolu)
    return veri
