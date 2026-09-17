"""Bobin numaralandirmasi, polarite ve Q/H/V/M mod bazi.

Bobin numaralandirmasi (cercevedeki etiketlere gore, etiketli taraftan
bakildiginda):

    1 sag ust (45 derece)    2 sol ust (135 derece)
    3 sol alt (225 derece)   4 sag alt (315 derece)

Modlar, fiziksel akim GENLIKLERINE uygulanan pertubasyon desenleridir. Isaretli
akimda (genlik x nominal polarite) su anlamlara gelirler:

    Q = (+1,+1,+1,+1)  ->  isaretli akimda nominal kuadrupol deseni  (gradyen)
    H = (+1,-1,-1,+1)  ->  yatay dipol  (sag cift 1,4  <->  sol cift 2,3)
    V = (+1,+1,-1,-1)  ->  dusey dipol  (ust cift 1,2  <->  alt cift 3,4)
    M = (+1,-1,+1,-1)  ->  isaretli akimda uniform (monopol); racetrack
                           bobinlerde net akim sifir oldugu icin dipol ve
                           gradyene katkisi yoktur -> R'nin sifir uzayi yonu

Dort desen birbirine ortogonaldir (Hadamard bazi), bu yuzden mod bazindan
bobin bazina donusum basit bir transpoz ile yapilir:

    x = V * eps        (x: bobin basina bagil akim sapmasi, eps: mod genlikleri)
    eps = V^T * x / 4  (V^T V = 4I oldugundan)
    R = S * V^T / 4    (S: mod basina olculen egimler, 3x4)

Burada "bagil akim sapmasi" boyutsuzdur: x_i = (I_i - I_nominal) / I_nominal.
R bu boyutsuz sapmalar uzerine kuruldugu icin, dg/deps_Q ~ 1 olur ve
R_eff = (dx_c/deps_H) / (dg/deps_Q) dogrudan metre birimine oturur.
"""
from __future__ import annotations

import numpy as np

from .yapilandirma import BOBIN_SAYISI, MiknatisYapilandirmasi, ModlarYapilandirmasi

# R'nin sutun sirasi ve mod matrisinin kolon sirasi bu sirayla sabittir.
MOD_SIRASI: tuple[str, ...] = ("Q", "H", "V", "M")

# y = [x_c, y_c, g] bileseninin satir adlari (R'nin satirlari).
Y_SATIRLARI: tuple[str, ...] = ("x_c", "y_c", "g")


class ModHatasi(ValueError):
    """Mod donusumu gecersiz."""


class ModBazi:
    """Mod desenleri ile bobin akimlari arasindaki donusumler."""

    def __init__(self, modlar: ModlarYapilandirmasi, miknatis: MiknatisYapilandirmasi) -> None:
        self.modlar = modlar
        self.miknatis = miknatis
        self._V = np.column_stack([np.array(modlar.desen(m), dtype=float) for m in MOD_SIRASI])

    # ------------------------------------------------------------------
    # Temel matrisler
    # ------------------------------------------------------------------
    @property
    def mod_matrisi(self) -> np.ndarray:
        """V (4x4): sutunlari MOD_SIRASI duzeninde mod desenleri."""
        return self._V.copy()

    @property
    def polarite(self) -> np.ndarray:
        return np.array(self.miknatis.nominal_polarite, dtype=float)

    @property
    def nominal_akimlar(self) -> np.ndarray:
        return np.full(BOBIN_SAYISI, self.miknatis.nominal_akim_A, dtype=float)

    def mod_vektoru(self, mod: str) -> np.ndarray:
        if mod not in MOD_SIRASI:
            raise ModHatasi(f"Bilinmeyen mod: {mod}")
        return np.array(self.modlar.desen(mod), dtype=float)

    # ------------------------------------------------------------------
    # Akim <-> bagil sapma <-> mod genlikleri
    # ------------------------------------------------------------------
    def bagil_sapma(self, akimlar: np.ndarray) -> np.ndarray:
        """x_i = (I_i - I_nominal) / I_nominal  (boyutsuz)."""
        akimlar = np.asarray(akimlar, dtype=float)
        if akimlar.shape != (BOBIN_SAYISI,):
            raise ModHatasi(f"{BOBIN_SAYISI} elemanli akim vektoru bekleniyor")
        return (akimlar - self.nominal_akimlar) / self.miknatis.nominal_akim_A

    def akimlar(self, bagil_sapma: np.ndarray) -> np.ndarray:
        """Bagil sapmadan fiziksel akimlara (amper)."""
        bagil_sapma = np.asarray(bagil_sapma, dtype=float)
        return self.nominal_akimlar * (1.0 + bagil_sapma)

    def mod_akimlari(self, mod: str, epsilon: float) -> np.ndarray:
        """Tek bir modun epsilon genligindeki fiziksel akimlari (amper)."""
        return self.akimlar(epsilon * self.mod_vektoru(mod))

    def mod_genlikleri(self, bagil_sapma: np.ndarray) -> dict[str, float]:
        """eps = V^T x / 4; bagil sapmayi mod bilesenlerine ayirir."""
        bagil_sapma = np.asarray(bagil_sapma, dtype=float)
        katsayilar = self._V.T @ bagil_sapma / float(BOBIN_SAYISI)
        return {mod: float(katsayilar[i]) for i, mod in enumerate(MOD_SIRASI)}

    def isaretli_akimlar(self, akimlar: np.ndarray) -> np.ndarray:
        """Isaretli akim: fiziksel genlik x nominal polarite.

        Yalnizca raporlama ve simulator icindir; guc kaynaklari her zaman
        pozitif akim surer, isaret role donanimiyla belirlenir.
        """
        return np.asarray(akimlar, dtype=float) * self.polarite

    # ------------------------------------------------------------------
    # Monopol (sifir uzayi) bileseni
    # ------------------------------------------------------------------
    def monopol_bileseni(self, bagil_sapma: np.ndarray) -> float:
        """Bagil sapmanin M modu boyunca genligi."""
        return self.mod_genlikleri(bagil_sapma)["M"]

    def monopol_cikar(self, bagil_sapma: np.ndarray) -> np.ndarray:
        """Bagil sapmadan M (monopol) bilesenini atar.

        Monopol yonu dipolu ve gradyeni degistirmedigi icin R'nin sifir
        uzayindadir; oradaki birikim yalnizca gurultudur.
        """
        bagil_sapma = np.asarray(bagil_sapma, dtype=float)
        v_m = self.mod_vektoru("M")
        return bagil_sapma - self.monopol_bileseni(bagil_sapma) * v_m

    # ------------------------------------------------------------------
    # Response matrix kurulumu
    # ------------------------------------------------------------------
    def response_matrisi(self, mod_egimleri: dict[str, np.ndarray]) -> np.ndarray:
        """Mod egimlerinden 3x4 response matrix R'yi kurar.

        `mod_egimleri`: mod -> dy/deps (3 elemanli: x_c, y_c, g). Olculmemis
        modlar (tipik olarak M) sifir kabul edilir; monopol dipol ve gradyene
        katkisiz oldugu icin bu fiziksel olarak dogrudur ve R'nin sifir
        uzayinin M yonu olmasini saglar.

        Satirlar: x_c [m], y_c [m], g [boyutsuz]
        Sutunlar: bobin basina bagil akim sapmasi [boyutsuz]
        """
        S = np.zeros((len(Y_SATIRLARI), BOBIN_SAYISI), dtype=float)
        for i, mod in enumerate(MOD_SIRASI):
            egim = mod_egimleri.get(mod)
            if egim is None:
                continue
            egim = np.asarray(egim, dtype=float)
            if egim.shape != (len(Y_SATIRLARI),):
                raise ModHatasi(f"{mod} modu egimi {len(Y_SATIRLARI)} elemanli olmalidir")
            S[:, i] = egim
        return S @ self._V.T / float(BOBIN_SAYISI)

    def mod_egimlerine_ayir(self, R: np.ndarray) -> dict[str, np.ndarray]:
        """response_matrisi'nin tersi: R'den mod egimlerini (S) geri okur."""
        R = np.asarray(R, dtype=float)
        if R.shape != (len(Y_SATIRLARI), BOBIN_SAYISI):
            raise ModHatasi(f"R {len(Y_SATIRLARI)}x{BOBIN_SAYISI} olmalidir")
        S = R @ self._V
        return {mod: S[:, i].copy() for i, mod in enumerate(MOD_SIRASI)}
