"""Bobin numaralandırması, polarite ve Q/H/V/M mod bazı.

Bobin numaralandırması (çerçevedeki etiketlere göre, etiketli taraftan
bakıldığında):

    1 sağ üst (45 derece)    2 sol üst (135 derece)
    3 sol alt (225 derece)   4 sağ alt (315 derece)

Modlar, fiziksel akım GENLİKLERİNE uygulanan pertürbasyon desenleridir. İşaretli
akımda (genlik x nominal polarite) şu anlamlara gelirler:

    Q = (+1,+1,+1,+1)  ->  işaretli akımda nominal kuadrupol deseni  (gradyen)
    H = (+1,-1,-1,+1)  ->  yatay dipol  (sağ çift 1,4  <->  sol çift 2,3)
    V = (+1,+1,-1,-1)  ->  düşey dipol  (üst çift 1,2  <->  alt çift 3,4)
    M = (+1,-1,+1,-1)  ->  işaretli akımda üniform (monopol); racetrack
                           bobinlerde net akım sıfır olduğu için dipol ve
                           gradyene katkısı yoktur -> R'nin sıfır uzayı yönü

Dört desen birbirine ortogonaldir (Hadamard bazı), bu yüzden mod bazından
bobin bazına dönüşüm basit bir transpoz ile yapılır:

    x = V * eps        (x: bobin başına bağıl akım sapması, eps: mod genlikleri)
    eps = V^T * x / 4  (V^T V = 4I olduğundan)
    R = S * V^T / 4    (S: mod başına ölçülen eğimler, 3x4)

Burada "bağıl akım sapması" boyutsuzdur: x_i = (I_i - I_nominal) / I_nominal.
R bu boyutsuz sapmalar üzerine kurulduğu için, dg/deps_Q ~ 1 olur ve
R_eff = (dx_c/deps_H) / (dg/deps_Q) doğrudan metre birimine oturur.
"""
from __future__ import annotations

import numpy as np

from .yapilandirma import BOBIN_SAYISI, MiknatisYapilandirmasi, ModlarYapilandirmasi

# R'nin sütun sırası ve mod matrisinin kolon sırası bu sırayla sabittir.
MOD_SIRASI: tuple[str, ...] = ("Q", "H", "V", "M")

# y = [x_c, y_c, g] bileşeninin satır adları (R'nin satırları).
Y_SATIRLARI: tuple[str, ...] = ("x_c", "y_c", "g")


class ModHatasi(ValueError):
    """Mod dönüşümü geçersiz."""


class ModBazi:
    """Mod desenleri ile bobin akımları arasındaki dönüşümler."""

    def __init__(self, modlar: ModlarYapilandirmasi, miknatis: MiknatisYapilandirmasi) -> None:
        self.modlar = modlar
        self.miknatis = miknatis
        self._V = np.column_stack([np.array(modlar.desen(m), dtype=float) for m in MOD_SIRASI])

    # ------------------------------------------------------------------
    # Temel matrisler
    # ------------------------------------------------------------------
    @property
    def mod_matrisi(self) -> np.ndarray:
        """V (4x4): sütunları MOD_SIRASI düzeninde mod desenleri."""
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
    # Akım <-> bağıl sapma <-> mod genlikleri
    # ------------------------------------------------------------------
    def bagil_sapma(self, akimlar: np.ndarray) -> np.ndarray:
        """x_i = (I_i - I_nominal) / I_nominal  (boyutsuz)."""
        akimlar = np.asarray(akimlar, dtype=float)
        if akimlar.shape != (BOBIN_SAYISI,):
            raise ModHatasi(f"{BOBIN_SAYISI} elemanlı akım vektörü bekleniyor")
        return (akimlar - self.nominal_akimlar) / self.miknatis.nominal_akim_A

    def akimlar(self, bagil_sapma: np.ndarray) -> np.ndarray:
        """Bağıl sapmadan fiziksel akımlara (amper)."""
        bagil_sapma = np.asarray(bagil_sapma, dtype=float)
        return self.nominal_akimlar * (1.0 + bagil_sapma)

    def mod_akimlari(self, mod: str, epsilon: float) -> np.ndarray:
        """Tek bir modun epsilon genliğindeki fiziksel akımları (amper)."""
        return self.akimlar(epsilon * self.mod_vektoru(mod))

    def mod_genlikleri(self, bagil_sapma: np.ndarray) -> dict[str, float]:
        """eps = V^T x / 4; bağıl sapmayı mod bileşenlerine ayırır."""
        bagil_sapma = np.asarray(bagil_sapma, dtype=float)
        katsayilar = self._V.T @ bagil_sapma / float(BOBIN_SAYISI)
        return {mod: float(katsayilar[i]) for i, mod in enumerate(MOD_SIRASI)}

    def isaretli_akimlar(self, akimlar: np.ndarray) -> np.ndarray:
        """İşaretli akım: fiziksel genlik x nominal polarite.

        Yalnızca raporlama ve simülatör içindir; güç kaynakları her zaman
        pozitif akım sürer, işaret röle donanımıyla belirlenir.
        """
        return np.asarray(akimlar, dtype=float) * self.polarite

    # ------------------------------------------------------------------
    # Monopol (sıfır uzayı) bileşeni
    # ------------------------------------------------------------------
    def monopol_bileseni(self, bagil_sapma: np.ndarray) -> float:
        """Bağıl sapmanın M modu boyunca genliği."""
        return self.mod_genlikleri(bagil_sapma)["M"]

    def monopol_cikar(self, bagil_sapma: np.ndarray) -> np.ndarray:
        """Bağıl sapmadan M (monopol) bileşenini atar.

        Monopol yönü dipolu ve gradyeni değiştirmediği için R'nin sıfır
        uzayındadır; oradaki birikim yalnızca gürültüdür.
        """
        bagil_sapma = np.asarray(bagil_sapma, dtype=float)
        v_m = self.mod_vektoru("M")
        return bagil_sapma - self.monopol_bileseni(bagil_sapma) * v_m

    # ------------------------------------------------------------------
    # Response matrix kurulumu
    # ------------------------------------------------------------------
    def response_matrisi(self, mod_egimleri: dict[str, np.ndarray]) -> np.ndarray:
        """Mod eğimlerinden 3x4 response matrix R'yi kurar.

        `mod_egimleri`: mod -> dy/deps (3 elemanlı: x_c, y_c, g). Ölçülmemiş
        modlar (tipik olarak M) sıfır kabul edilir; monopol dipol ve gradyene
        katkısız olduğu için bu fiziksel olarak doğrudur ve R'nin sıfır
        uzayının M yönü olmasını sağlar.

        Satırlar: x_c [m], y_c [m], g [boyutsuz]
        Sütunlar: bobin başına bağıl akım sapması [boyutsuz]
        """
        S = np.zeros((len(Y_SATIRLARI), BOBIN_SAYISI), dtype=float)
        for i, mod in enumerate(MOD_SIRASI):
            egim = mod_egimleri.get(mod)
            if egim is None:
                continue
            egim = np.asarray(egim, dtype=float)
            if egim.shape != (len(Y_SATIRLARI),):
                raise ModHatasi(f"{mod} modu eğimi {len(Y_SATIRLARI)} elemanlı olmalıdır")
            S[:, i] = egim
        return S @ self._V.T / float(BOBIN_SAYISI)

    def mod_egimlerine_ayir(self, R: np.ndarray) -> dict[str, np.ndarray]:
        """response_matrisi'nin tersi: R'den mod eğimlerini (S) geri okur."""
        R = np.asarray(R, dtype=float)
        if R.shape != (len(Y_SATIRLARI), BOBIN_SAYISI):
            raise ModHatasi(f"R {len(Y_SATIRLARI)}x{BOBIN_SAYISI} olmalıdır")
        S = R @ self._V
        return {mod: S[:, i].copy() for i, mod in enumerate(MOD_SIRASI)}
