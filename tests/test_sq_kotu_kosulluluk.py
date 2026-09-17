"""BELGELEME AMACLI test: SQ'nun hedefe eklenmesi neden problemi bozar.

Bu test bir gereksinimi dogrulamaz; BIRAKILAN yaklasimin neden birakildigini
sayisal olarak gosterir ve belgeler. Nedenler:

1. Skew kuadrupol (SQ/G, yani miknatisin roll'u), 4 katli simetrik bir duzende
   dort bobin akimiyla KONTROL EDILEMEZ. Yalnizca bobinlerin kucuk acisal
   yerlesim hatalari uzerinden, cok buyuk akim degisimleri pahasina erisilebilir.
2. Uniform (monopol) akim modu dipolu ve gradyeni degistirmez; bu nedenle
   akimlarin kayabilecegi bir sifir uzayi yonudur.
3. T ile T/m'yi ayni normda toplamak ve yalnizca adim buyuklugunu cezalandiran
   regularizasyon kotu davranisa yol acar.

Bu depoda kullanilan kurulum ise 3x4 [x_c, y_c, g] uzerinedir: rank 3 oldugu
icin hedef her zaman TAM olarak erisilebilir, sifir uzayi tam olarak monopol
yonudur ve `pinv` minimum normlu cozumu secer.
"""
from __future__ import annotations

import numpy as np
import pytest

from merkezleme.modlar import MOD_SIRASI


def sq_egimleri(simulator, mod_bazi, konvansiyon, eps: float = 0.005) -> dict[str, float]:
    """Her mod icin d(SQ/G)/deps olcer."""
    temel = konvansiyon.izleme(simulator.olc(mod_bazi.nominal_akimlar, gurultu=False)).sq_over_g
    egimler: dict[str, float] = {}
    for mod in MOD_SIRASI:
        olcum = simulator.olc(mod_bazi.mod_akimlari(mod, eps), gurultu=False)
        sq = konvansiyon.izleme(olcum).sq_over_g
        egimler[mod] = (sq - temel) / eps
    return egimler


def test_ideal_duzende_sq_dort_bobinle_kontrol_edilemez(
    temiz_simulator, mod_bazi, konvansiyon
):
    """4 katli simetrik duzende hicbir mod SQ/G'yi anlamli olcude degistirmez."""
    egimler = sq_egimleri(temiz_simulator, mod_bazi, konvansiyon)
    # Karsilastirma olcegi: Q modunun gradyen tepkisi (dg/deps = 1)
    for mod, egim in egimler.items():
        assert abs(egim) < 1e-6, f"{mod} modu SQ/G'yi beklenmedik sekilde etkiliyor: {egim}"


def test_sq_hedefe_eklenirse_sistem_kotu_kosullu_olur(
    temiz_simulator, mod_bazi, konvansiyon, kfg
):
    """[x_c, y_c, g, SQ/G] uzerine kurulan 4x4 sistem tekil/kotu kosulludur."""
    eps = 0.005
    gradyen_nominal = temiz_simulator.gradyen_T_m(mod_bazi.nominal_akimlar)

    # Mod egimleri: x_c, y_c, g ve (hedefe eklenmek istenen) SQ/G
    S3 = np.zeros((3, 4))
    S4 = np.zeros((4, 4))
    for i, mod in enumerate(MOD_SIRASI):
        olcum = temiz_simulator.olc(mod_bazi.mod_akimlari(mod, eps), gurultu=False)
        z = konvansiyon.merkez(olcum)
        g = (konvansiyon.gradyen_T_m(olcum) - gradyen_nominal) / gradyen_nominal
        sq = konvansiyon.izleme(olcum).sq_over_g or 0.0
        S3[:, i] = [z.real / eps, z.imag / eps, g / eps]
        S4[:, i] = [z.real / eps, z.imag / eps, g / eps, sq / eps]

    V = mod_bazi.mod_matrisi
    R3 = S3 @ V.T / 4
    R4 = S4 @ V.T / 4

    tekil3 = np.linalg.svd(R3, compute_uv=False)
    tekil4 = np.linalg.svd(R4, compute_uv=False)
    kosul3 = tekil3[0] / tekil3[-1]
    kosul4 = tekil4[0] / tekil4[-1]

    # 3x4 kurulum: rank 3, saglikli. 4x4 kurulum: SQ satiri ~0 -> tekil.
    assert np.linalg.matrix_rank(R3, tol=1e-12) == 3
    assert np.linalg.matrix_rank(R4, tol=1e-12) == 3, "SQ satiri yeni bir yon eklemiyor"
    assert kosul4 > 1e6 * kosul3, (kosul3, kosul4)


def test_sq_sifirlamak_guvenlik_sinirlarini_kat_kat_asar(
    simulator_uret, mod_bazi, konvansiyon, kfg
):
    """Acisal yerlesim hatasi olsa bile SQ'yu sifirlamak asiri akim ister.

    Kucuk bir acisal hata SQ'ya zayif bir yol acar; ama roll kaynakli tipik bir
    SQ/G'yi (1 mrad roll ~ 0.002) sifirlamak icin gereken bagil akim degisimi,
    nominale gore izin verilen toplam asimetriyi (varsayilan %5) kat kat asar.
    """
    sim = simulator_uret(
        ofset_m=0j,
        arka_plan_T=0j,
        roll_rad=1e-3,  # 1 mrad roll -> SQ/G ~ -0.002
        harmonik_gurultu_bagil=0.0,
        yerlesim_hatasi_acisal_mrad=[5.0, -3.0, 2.0, -4.0],
    )
    egimler = sq_egimleri(sim, mod_bazi, konvansiyon)
    en_guclu_mod = max(egimler, key=lambda m: abs(egimler[m]))
    en_guclu = abs(egimler[en_guclu_mod])

    hedeflenen_sq = abs(konvansiyon.izleme(sim.olc(mod_bazi.nominal_akimlar, gurultu=False)).sq_over_g)
    assert hedeflenen_sq > 0

    assert hedeflenen_sq == pytest.approx(0.002, rel=0.05), hedeflenen_sq
    gereken_eps = hedeflenen_sq / en_guclu if en_guclu > 0 else np.inf
    # Olculen degerler: en guclu tutamak M modu, ~7e-3 / birim eps
    # -> gereken bagil akim degisimi ~%29, sinir ise %5.
    assert gereken_eps > 5 * kfg.guvenlik.nominale_gore_max_asimetri, (
        f"gereken bagil akim degisimi {gereken_eps:.3g} ({en_guclu_mod} modu, "
        f"egim {en_guclu:.3g}), sinir {kfg.guvenlik.nominale_gore_max_asimetri:.3g}"
    )


def test_roll_varken_de_sq_akimla_erisilemez(simulator_uret, mod_bazi, konvansiyon):
    """Kusursuz geometride roll SQ uretir, ama hicbir akim modu ona dokunamaz."""
    sim = simulator_uret(ofset_m=0j, arka_plan_T=0j, roll_rad=1e-3, harmonik_gurultu_bagil=0.0)
    temel = konvansiyon.izleme(sim.olc(mod_bazi.nominal_akimlar, gurultu=False)).sq_over_g
    assert temel == pytest.approx(-0.002, rel=0.05)
    for mod, egim in sq_egimleri(sim, mod_bazi, konvansiyon).items():
        assert abs(egim) < 1e-9, f"{mod} modu SQ/G'yi etkiliyor: {egim}"


def test_monopol_yonu_sifir_uzayidir(temiz_simulator, mod_bazi, konvansiyon):
    """Uniform (monopol) mod dipolu ve gradyeni degistirmez -> akimlarin kayabilecegi yon."""
    eps = 0.02  # buyuk bir monopol bileseni
    olcum = temiz_simulator.olc(mod_bazi.mod_akimlari("M", eps), gurultu=False)
    gradyen_nominal = temiz_simulator.gradyen_T_m(mod_bazi.nominal_akimlar)
    g = (konvansiyon.gradyen_T_m(olcum) - gradyen_nominal) / gradyen_nominal
    assert abs(konvansiyon.merkez(olcum)) < 1e-15
    assert abs(g) < 1e-12
    # Bu yuzden her adimdan sonra monopol bileseni acikca atilir.


def test_birim_karisimi_3x4_cozumu_etkilemez(mod_bazi):
    """R 3x4 ve rank 3 iken hedef tam erisilebilir; satir birimleri cozumu degistirmez.

    Satirlari olceklemek (m, m, boyutsuz -> hepsi toleransa gore) ayni akim
    cozumunu verir; yani eski kurulumdaki "T ile T/m'yi ayni normda toplama"
    sorunu bu formulasyonda ortadan kalkar.
    """
    R = mod_bazi.response_matrisi(
        {
            "H": np.array([-0.0408, 0.0, 0.0]),
            "V": np.array([0.0, -0.0408, 0.0]),
            "Q": np.array([0.0, 0.0, 1.0]),
        }
    )
    hata = np.array([120e-6, -80e-6, 5e-4])
    cozum = np.linalg.pinv(R) @ hata

    olcekler = np.array([1 / 5e-6, 1 / 5e-6, 1 / 1e-3])
    cozum_olcekli = np.linalg.pinv(olcekler[:, None] * R) @ (olcekler * hata)

    assert np.allclose(cozum, cozum_olcekli, atol=1e-12)
    # Her iki cozum de hedefi tam olarak tutturur
    assert np.allclose(R @ cozum, hata, atol=1e-15)
