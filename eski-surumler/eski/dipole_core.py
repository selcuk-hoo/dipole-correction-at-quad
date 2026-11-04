"""Response-matrix tabanli dipol bastirma algoritmasinin cekirdek matematigi.

PyQt5/matplotlib gibi arayuz bagimliliklarindan tamamen bagimsizdir, boylece
GUI'siz ortamlarda da (ornegin otomatik testlerle) dogrulanabilir.

Algoritma (bkz. README icin paylasilan tasarim notlari):

  Faz 1 - Response matrix kalibrasyonu
    Nominal akimlarda 1 olcum, sonra her bobin sirayla +dI ve -dI
    kadar degistirilerek 8 olcum daha alinir (toplam 9). Merkezi fark ile

        R[:, i] = (M(I_i + dI) - M(I_i - dI)) / (2 * dI)

    hesaplanir. Burada olcum vektoru M = [Bx, By] (yalniz dipol bilesenleri;
    quadrupole hedeflenmiyor, bkz. modul dokstringi).

  Faz 2 - Regularized least squares dongusu
    Hedef daima [Bx, By] = [0, 0] oldugundan hata vektoru e = -M olur.
    Akim duzeltmesi

        (R^T R + lambda I) dI = R^T e

    normal denklemleriyle cozulur. lambda regularizasyon terimi hem
    R 2x4 oldugu icin (underdetermined) coziimu tekillestirir hem de
    akimlarda gereksiz buyuk degisimleri bastirir. Duzeltme dogrudan
    uygulanmaz, damping ile kademeli uygulanir:

        I_new = I_old + alpha * dI,   0 < alpha <= 1
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone

import numpy as np


@dataclass
class CalibrationStep:
    """Kalibrasyon sihirbazinin tek bir adimi."""

    coil: int | None  # None => nominal olcum, aksi halde 0..3
    sign: int  # +1, -1 ya da 0 (nominal icin)

    @property
    def label(self) -> str:
        if self.coil is None:
            return "Nominal akimlar"
        isaret = "+" if self.sign > 0 else "-"
        return f"I{self.coil} {isaret}= dI"

    def target_currents(self, nominal: np.ndarray, delta_i: float) -> np.ndarray:
        currents = nominal.copy()
        if self.coil is not None:
            currents[self.coil] += self.sign * delta_i
        return currents


def build_calibration_steps() -> list[CalibrationStep]:
    """9 adimlik kalibrasyon sirasini uretir: 1 nominal + 4 bobin x (+dI, -dI)."""
    steps = [CalibrationStep(coil=None, sign=0)]
    for coil in range(4):
        steps.append(CalibrationStep(coil=coil, sign=+1))
        steps.append(CalibrationStep(coil=coil, sign=-1))
    return steps


def compute_response_matrix(
    measurements: list[tuple[float, float]], delta_i: float
) -> np.ndarray:
    """9 olcumden (nominal + 4x[+dI,-dI]) 2x4 response matrix hesaplar.

    measurements sirasi build_calibration_steps() ile ayni olmalidir:
    [nominal, coil0+, coil0-, coil1+, coil1-, coil2+, coil2-, coil3+, coil3-]
    """
    if len(measurements) != 9:
        raise ValueError(f"9 olcum bekleniyor, {len(measurements)} geldi")
    if delta_i == 0:
        raise ValueError("delta_i sifir olamaz")

    M = np.array(measurements, dtype=float)  # shape (9, 2)
    R = np.zeros((2, 4))
    for coil in range(4):
        Mp = M[1 + 2 * coil]
        Mm = M[2 + 2 * coil]
        R[:, coil] = (Mp - Mm) / (2 * delta_i)
    return R


def solve_regularized_correction(
    R: np.ndarray, error: np.ndarray, lam: float
) -> np.ndarray:
    """min ||R*dI - error||^2 + lam*||dI||^2 problemini cozer.

    Normal denklemler: (R^T R + lam*I) dI = R^T error
    """
    n = R.shape[1]
    A = R.T @ R + lam * np.eye(n)
    b = R.T @ error
    return np.linalg.solve(A, b)


def damped_update(
    currents: np.ndarray, delta_currents: np.ndarray, alpha: float
) -> np.ndarray:
    if not (0 < alpha <= 1):
        raise ValueError("alpha (0, 1] araliginda olmalidir")
    return currents + alpha * delta_currents


@dataclass
class ResponseMatrixData:
    R: np.ndarray
    nominal_currents: np.ndarray
    delta_i: float
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def save(self, path: str) -> None:
        payload = {
            "timestamp": self.timestamp,
            "delta_i": self.delta_i,
            "nominal_currents": self.nominal_currents.tolist(),
            "R": self.R.tolist(),
        }
        os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
        with open(path, "w") as f:
            json.dump(payload, f, indent=2)

    @classmethod
    def load(cls, path: str) -> "ResponseMatrixData":
        with open(path) as f:
            payload = json.load(f)
        return cls(
            R=np.array(payload["R"], dtype=float),
            nominal_currents=np.array(payload["nominal_currents"], dtype=float),
            delta_i=float(payload["delta_i"]),
            timestamp=payload.get("timestamp", ""),
        )
