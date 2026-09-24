"""Yapılandırma katmanı.

`yapilandirma.yaml` dosyasını okur, tip açıklamalı dataclass'lara dönüştürür ve
doğrular. Programın başka hiçbir yerinde fiziksel sabit ya da sınır yoktur;
hepsi buradan gelir.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import yaml

Kip = Literal["kuru", "canli"]
GirisBicimi = Literal["genlik_faz", "normal_skew"]
Birim = Literal["T", "mT", "units"]
FazBirimi = Literal["derece", "radyan"]
GradyenKaynagi = Literal["normal", "genlik"]
ArkaPlanCikarma = Literal["tum", "yalniz_dipol"]
GradyenHedefiKaynagi = Literal["ilk_olcum", "yapilandirma"]

BOBIN_SAYISI = 4
MOD_ADLARI = ("Q", "H", "V", "M")


class YapilandirmaHatasi(ValueError):
    """Yapılandırma dosyası geçersiz."""


def _zorunlu(sozluk: dict[str, Any], anahtar: str, yol: str) -> Any:
    if anahtar not in sozluk:
        raise YapilandirmaHatasi(f"{yol}.{anahtar} eksik")
    return sozluk[anahtar]


def _dogrula_secenek(deger: Any, secenekler: tuple[str, ...], yol: str) -> Any:
    if deger not in secenekler:
        raise YapilandirmaHatasi(
            f"{yol} değeri {deger!r} geçersiz; seçenekler: {', '.join(secenekler)}"
        )
    return deger


def _dogrula_dort_eleman(deger: Any, yol: str) -> list[float]:
    if not isinstance(deger, (list, tuple)) or len(deger) != BOBIN_SAYISI:
        raise YapilandirmaHatasi(f"{yol} {BOBIN_SAYISI} elemanlı bir liste olmalıdır")
    return [float(x) for x in deger]


@dataclass(frozen=True)
class GenelYapilandirma:
    kip: Kip
    modulator_acik: bool
    calistirma_kok_dizini: str
    durum_dosyasi_adi: str
    tema: str = "varsayilan"


@dataclass(frozen=True)
class MiknatisYapilandirmasi:
    nominal_akim_A: float
    bobin_acilari_derece: list[float]
    nominal_polarite: list[int]
    gradyen_hedefi_kaynagi: GradyenHedefiKaynagi
    nominal_gradyen_T_m: float
    endustans_mH: float

    @property
    def bobin_acilari_rad(self) -> list[float]:
        return [math.radians(a) for a in self.bobin_acilari_derece]


@dataclass(frozen=True)
class ModlarYapilandirmasi:
    """Fiziksel akım genliklerine uygulanan mod desenleri."""

    desenler: dict[str, list[float]]

    def desen(self, mod: str) -> list[float]:
        if mod not in self.desenler:
            raise YapilandirmaHatasi(f"modlar.{mod} tanımlı değil")
        return self.desenler[mod]


@dataclass(frozen=True)
class HarmoniklerYapilandirmasi:
    r_ref_mm: float
    giris_bicimi: GirisBicimi
    birim: Birim
    units_referans_n: int
    units_mutlak_gradyen_T_m: float | None
    faz_birimi: FazBirimi
    faz_n_carpani: bool
    faz_isareti: int
    feed_down_isareti: int
    eslenik: bool
    gradyen_kaynagi: GradyenKaynagi
    arka_plan_cikarma: ArkaPlanCikarma
    opsiyonel_harmonikler: list[int]

    @property
    def r_ref_m(self) -> float:
        return self.r_ref_mm * 1e-3

    @property
    def zorunlu_harmonikler(self) -> tuple[int, ...]:
        return (1, 2)

    @property
    def tum_harmonikler(self) -> tuple[int, ...]:
        return tuple(sorted({1, 2, *self.opsiyonel_harmonikler}))


@dataclass(frozen=True)
class GucKaynaklariYapilandirmasi:
    visa_adresleri: list[str]
    uyum_gerilimi_V: float
    rampa_hizi_A_s: float
    rampa_adim_suresi_s: float
    oturma_suresi_s: float
    akim_tolerans_A: float
    oturma_dogrulama_denemesi: int


@dataclass(frozen=True)
class GuvenlikYapilandirmasi:
    bobin_basi_max_akim_A: float
    adim_basi_max_bagil_degisim: float
    nominale_gore_max_asimetri: float


@dataclass(frozen=True)
class KalibrasyonYapilandirmasi:
    modlar: list[str]
    m_modu_kontrolu: bool
    nokta_sayisi: int
    delta_bagil: float
    ortak_sifir_noktasi: bool
    monoton_olmayan_sira: bool
    arka_plan_her_n_noktada: int
    olcum_basi_tahmini_sure_dk: float
    kosul_sayisi_esigi: float
    m_sutunu_esigi_bagil: float
    lineerlik_r2_esigi: float
    dosya_adi: str

    @property
    def olculen_modlar(self) -> list[str]:
        """Kalibrasyonda gerçekten ölçülecek modlar (M isteğe bağlı)."""
        modlar = list(self.modlar)
        if self.m_modu_kontrolu and "M" not in modlar:
            modlar.append("M")
        return modlar


@dataclass(frozen=True)
class DuzeltmeYapilandirmasi:
    alpha: float
    max_iterasyon: int
    merkez_toleransi_um: float
    g_toleransi: float
    monopol_cikar: bool
    tekrarlanabilirlik_N: int
    tolerans_tekrarlanabilirlik_carpani: float

    @property
    def merkez_toleransi_m(self) -> float:
        return self.merkez_toleransi_um * 1e-6


@dataclass(frozen=True)
class DogrulamaYapilandirmasi:
    yazim_hatasi_sapma_carpani: float
    c1_makul_aralik: tuple[float, float]
    c2_makul_aralik: tuple[float, float]


@dataclass(frozen=True)
class SimulatorYapilandirmasi:
    bobin_yaricapi_m: float
    demet_yari_acisi_derece: float
    sarim_sayisi: int
    olcum_cercevesi_acisi_derece: float
    miknatis_ofseti_mm: list[float]
    roll_mrad: float
    arka_plan_T: list[float]
    arka_plan_surukleme_T_s: float
    harmonik_gurultu_bagil: float
    harmonik_surukleme_bagil_s: float
    yerlesim_hatasi_radyal_mm: list[float]
    yerlesim_hatasi_acisal_mrad: list[float]
    sarim_hatasi_bagil: list[float]
    tohum: int

    @property
    def demet_yari_acisi_rad(self) -> float:
        return math.radians(self.demet_yari_acisi_derece)

    @property
    def beklenen_r_eff_m(self) -> float:
        """Analitik R_eff = a*sqrt(2) / (4*cos(alpha)).

        Tek bobinin iki iletken demeti (theta +/- alpha) ve Hadamard mod bazı
        için türetilmiştir; testlerde kalibrasyondan çıkan R_eff ile karşılaştırılır.
        """
        return self.bobin_yaricapi_m * math.sqrt(2.0) / (4.0 * math.cos(self.demet_yari_acisi_rad))


@dataclass(frozen=True)
class DosyaGirisiYapilandirmasi:
    """Paylaşımlı dosya üzerinden otomatik ölçüm alışverişi.

    Aynı bilgisayarda çalışan ayrı bir dönen bobin programıyla elle girişsiz
    koordinasyon içindir. `kilit_dosyasi` YOK ise "ölç" sinyalidir (sıra dönen
    bobinde); VAR ise "veri hazır" sinyalidir (sıra bu programda). Dönen bobin
    tarafı veriyi geçici bir dosyaya yazıp ATOMİK olarak `kilit_dosyasi`'na
    taşımalıdır (`os.rename`), böylece yarım yazılmış bir dosya asla okunmaz.
    """

    kilit_dosyasi: str
    zaman_asimi_s: float
    yoklama_araligi_s: float


VARSAYILAN_DOSYA_GIRISI = DosyaGirisiYapilandirmasi(
    kilit_dosyasi="veri_kilidi/.kilit",
    zaman_asimi_s=30.0,
    yoklama_araligi_s=0.2,
)


@dataclass(frozen=True)
class Yapilandirma:
    genel: GenelYapilandirma
    miknatis: MiknatisYapilandirmasi
    modlar: ModlarYapilandirmasi
    harmonikler: HarmoniklerYapilandirmasi
    guc_kaynaklari: GucKaynaklariYapilandirmasi
    guvenlik: GuvenlikYapilandirmasi
    kalibrasyon: KalibrasyonYapilandirmasi
    duzeltme: DuzeltmeYapilandirmasi
    dogrulama: DogrulamaYapilandirmasi
    simulator: SimulatorYapilandirmasi
    dosya_girisi: DosyaGirisiYapilandirmasi = field(
        default_factory=lambda: VARSAYILAN_DOSYA_GIRISI
    )
    kaynak_dosya: Path | None = field(default=None)

    @property
    def nominal_akimlar(self) -> list[float]:
        return [self.miknatis.nominal_akim_A] * BOBIN_SAYISI


def _genel_yukle(veri: dict[str, Any]) -> GenelYapilandirma:
    yol = "genel"
    # Tema adları tema.py içinde tanımlıdır; arayüz kurulu olmasa da doğrulanır.
    from .tema import TEMALAR

    tema = str(veri.get("tema", "varsayilan"))
    if tema not in TEMALAR:
        raise YapilandirmaHatasi(
            f"{yol}.tema değeri {tema!r} geçersiz; seçenekler: {', '.join(TEMALAR)}"
        )
    return GenelYapilandirma(
        tema=tema,
        kip=_dogrula_secenek(_zorunlu(veri, "kip", yol), ("kuru", "canli"), f"{yol}.kip"),
        modulator_acik=bool(_zorunlu(veri, "modulator_acik", yol)),
        calistirma_kok_dizini=str(_zorunlu(veri, "calistirma_kok_dizini", yol)),
        durum_dosyasi_adi=str(_zorunlu(veri, "durum_dosyasi_adi", yol)),
    )


def _miknatis_yukle(veri: dict[str, Any]) -> MiknatisYapilandirmasi:
    yol = "miknatis"
    polarite = _dogrula_dort_eleman(_zorunlu(veri, "nominal_polarite", yol), f"{yol}.nominal_polarite")
    if any(p not in (1.0, -1.0) for p in polarite):
        raise YapilandirmaHatasi(f"{yol}.nominal_polarite yalnızca +1 ve -1 içerebilir")
    nominal_akim = float(_zorunlu(veri, "nominal_akim_A", yol))
    if nominal_akim <= 0:
        raise YapilandirmaHatasi(f"{yol}.nominal_akim_A pozitif olmalıdır")
    return MiknatisYapilandirmasi(
        nominal_akim_A=nominal_akim,
        bobin_acilari_derece=_dogrula_dort_eleman(
            _zorunlu(veri, "bobin_acilari_derece", yol), f"{yol}.bobin_acilari_derece"
        ),
        nominal_polarite=[int(p) for p in polarite],
        gradyen_hedefi_kaynagi=_dogrula_secenek(
            _zorunlu(veri, "gradyen_hedefi_kaynagi", yol),
            ("ilk_olcum", "yapilandirma"),
            f"{yol}.gradyen_hedefi_kaynagi",
        ),
        nominal_gradyen_T_m=float(_zorunlu(veri, "nominal_gradyen_T_m", yol)),
        endustans_mH=float(veri.get("endustans_mH", 0.0)),
    )


def _modlar_yukle(veri: dict[str, Any]) -> ModlarYapilandirmasi:
    desenler: dict[str, list[float]] = {}
    for mod in MOD_ADLARI:
        desenler[mod] = _dogrula_dort_eleman(_zorunlu(veri, mod, "modlar"), f"modlar.{mod}")
    # Modların ortogonallığı, mod bazından bobin bazına dönüşümün geçerliliği için şart.
    for i, mod_a in enumerate(MOD_ADLARI):
        for mod_b in MOD_ADLARI[i + 1 :]:
            ic_carpim = sum(a * b for a, b in zip(desenler[mod_a], desenler[mod_b]))
            if abs(ic_carpim) > 1e-9:
                raise YapilandirmaHatasi(
                    f"modlar.{mod_a} ve modlar.{mod_b} ortogonal değil (iç çarpım {ic_carpim:g}); "
                    "mod bazından bobin bazına dönüşüm yalnızca ortogonal bazda geçerlidir"
                )
    return ModlarYapilandirmasi(desenler=desenler)


def _harmonikler_yukle(veri: dict[str, Any]) -> HarmoniklerYapilandirmasi:
    yol = "harmonikler"
    faz_isareti = int(_zorunlu(veri, "faz_isareti", yol))
    feed_down_isareti = int(_zorunlu(veri, "feed_down_isareti", yol))
    for ad, deger in (("faz_isareti", faz_isareti), ("feed_down_isareti", feed_down_isareti)):
        if deger not in (1, -1):
            raise YapilandirmaHatasi(f"{yol}.{ad} yalnızca +1 ya da -1 olabilir")
    mutlak_gradyen = veri.get("units_mutlak_gradyen_T_m")
    return HarmoniklerYapilandirmasi(
        r_ref_mm=float(_zorunlu(veri, "r_ref_mm", yol)),
        giris_bicimi=_dogrula_secenek(
            _zorunlu(veri, "giris_bicimi", yol),
            ("genlik_faz", "normal_skew"),
            f"{yol}.giris_bicimi",
        ),
        birim=_dogrula_secenek(_zorunlu(veri, "birim", yol), ("T", "mT", "units"), f"{yol}.birim"),
        units_referans_n=int(veri.get("units_referans_n", 2)),
        units_mutlak_gradyen_T_m=None if mutlak_gradyen is None else float(mutlak_gradyen),
        faz_birimi=_dogrula_secenek(
            _zorunlu(veri, "faz_birimi", yol), ("derece", "radyan"), f"{yol}.faz_birimi"
        ),
        faz_n_carpani=bool(_zorunlu(veri, "faz_n_carpani", yol)),
        faz_isareti=faz_isareti,
        feed_down_isareti=feed_down_isareti,
        eslenik=bool(_zorunlu(veri, "eslenik", yol)),
        gradyen_kaynagi=_dogrula_secenek(
            _zorunlu(veri, "gradyen_kaynagi", yol), ("normal", "genlik"), f"{yol}.gradyen_kaynagi"
        ),
        arka_plan_cikarma=_dogrula_secenek(
            _zorunlu(veri, "arka_plan_cikarma", yol),
            ("tum", "yalniz_dipol"),
            f"{yol}.arka_plan_cikarma",
        ),
        opsiyonel_harmonikler=[int(n) for n in veri.get("opsiyonel_harmonikler", [])],
    )


def _guc_kaynaklari_yukle(veri: dict[str, Any]) -> GucKaynaklariYapilandirmasi:
    yol = "guc_kaynaklari"
    adresler = _zorunlu(veri, "visa_adresleri", yol)
    if not isinstance(adresler, (list, tuple)) or len(adresler) != BOBIN_SAYISI:
        raise YapilandirmaHatasi(f"{yol}.visa_adresleri {BOBIN_SAYISI} adres içermelidir")
    rampa_hizi = float(_zorunlu(veri, "rampa_hizi_A_s", yol))
    if rampa_hizi <= 0:
        raise YapilandirmaHatasi(f"{yol}.rampa_hizi_A_s pozitif olmalıdır")
    return GucKaynaklariYapilandirmasi(
        visa_adresleri=[str(a) for a in adresler],
        uyum_gerilimi_V=float(_zorunlu(veri, "uyum_gerilimi_V", yol)),
        rampa_hizi_A_s=rampa_hizi,
        rampa_adim_suresi_s=float(_zorunlu(veri, "rampa_adim_suresi_s", yol)),
        oturma_suresi_s=float(_zorunlu(veri, "oturma_suresi_s", yol)),
        akim_tolerans_A=float(_zorunlu(veri, "akim_tolerans_A", yol)),
        oturma_dogrulama_denemesi=int(_zorunlu(veri, "oturma_dogrulama_denemesi", yol)),
    )


def _guvenlik_yukle(veri: dict[str, Any]) -> GuvenlikYapilandirmasi:
    yol = "guvenlik"
    return GuvenlikYapilandirmasi(
        bobin_basi_max_akim_A=float(_zorunlu(veri, "bobin_basi_max_akim_A", yol)),
        adim_basi_max_bagil_degisim=float(_zorunlu(veri, "adim_basi_max_bagil_degisim", yol)),
        nominale_gore_max_asimetri=float(_zorunlu(veri, "nominale_gore_max_asimetri", yol)),
    )


def _kalibrasyon_yukle(veri: dict[str, Any]) -> KalibrasyonYapilandirmasi:
    yol = "kalibrasyon"
    nokta_sayisi = int(_zorunlu(veri, "nokta_sayisi", yol))
    if nokta_sayisi not in (3, 5):
        raise YapilandirmaHatasi(f"{yol}.nokta_sayisi yalnızca 3 ya da 5 olabilir")
    modlar = [str(m) for m in _zorunlu(veri, "modlar", yol)]
    for mod in modlar:
        if mod not in MOD_ADLARI:
            raise YapilandirmaHatasi(f"{yol}.modlar içinde bilinmeyen mod: {mod}")
    for zorunlu_mod in ("H", "V", "Q"):
        if zorunlu_mod not in modlar:
            raise YapilandirmaHatasi(f"{yol}.modlar içinde {zorunlu_mod} modu zorunludur")
    delta = float(_zorunlu(veri, "delta_bagil", yol))
    if delta <= 0:
        raise YapilandirmaHatasi(f"{yol}.delta_bagil pozitif olmalıdır")
    return KalibrasyonYapilandirmasi(
        modlar=modlar,
        m_modu_kontrolu=bool(_zorunlu(veri, "m_modu_kontrolu", yol)),
        nokta_sayisi=nokta_sayisi,
        delta_bagil=delta,
        ortak_sifir_noktasi=bool(_zorunlu(veri, "ortak_sifir_noktasi", yol)),
        monoton_olmayan_sira=bool(_zorunlu(veri, "monoton_olmayan_sira", yol)),
        arka_plan_her_n_noktada=max(1, int(_zorunlu(veri, "arka_plan_her_n_noktada", yol))),
        olcum_basi_tahmini_sure_dk=float(_zorunlu(veri, "olcum_basi_tahmini_sure_dk", yol)),
        kosul_sayisi_esigi=float(_zorunlu(veri, "kosul_sayisi_esigi", yol)),
        m_sutunu_esigi_bagil=float(_zorunlu(veri, "m_sutunu_esigi_bagil", yol)),
        lineerlik_r2_esigi=float(_zorunlu(veri, "lineerlik_r2_esigi", yol)),
        dosya_adi=str(_zorunlu(veri, "dosya_adi", yol)),
    )


def _duzeltme_yukle(veri: dict[str, Any]) -> DuzeltmeYapilandirmasi:
    yol = "duzeltme"
    alpha = float(_zorunlu(veri, "alpha", yol))
    if not 0.0 < alpha <= 1.0:
        raise YapilandirmaHatasi(f"{yol}.alpha (0, 1] aralığında olmalıdır")
    return DuzeltmeYapilandirmasi(
        alpha=alpha,
        max_iterasyon=int(_zorunlu(veri, "max_iterasyon", yol)),
        merkez_toleransi_um=float(_zorunlu(veri, "merkez_toleransi_um", yol)),
        g_toleransi=float(_zorunlu(veri, "g_toleransi", yol)),
        monopol_cikar=bool(_zorunlu(veri, "monopol_cikar", yol)),
        tekrarlanabilirlik_N=int(_zorunlu(veri, "tekrarlanabilirlik_N", yol)),
        tolerans_tekrarlanabilirlik_carpani=float(
            _zorunlu(veri, "tolerans_tekrarlanabilirlik_carpani", yol)
        ),
    )


def _dogrulama_yukle(veri: dict[str, Any]) -> DogrulamaYapilandirmasi:
    yol = "dogrulama"

    def aralik(anahtar: str) -> tuple[float, float]:
        deger = _zorunlu(veri, anahtar, yol)
        if not isinstance(deger, (list, tuple)) or len(deger) != 2:
            raise YapilandirmaHatasi(f"{yol}.{anahtar} iki elemanlı [alt, üst] olmalıdır")
        alt, ust = float(deger[0]), float(deger[1])
        if not 0 < alt < ust:
            raise YapilandirmaHatasi(f"{yol}.{anahtar} için 0 < alt < üst olmalıdır")
        return alt, ust

    return DogrulamaYapilandirmasi(
        yazim_hatasi_sapma_carpani=float(_zorunlu(veri, "yazim_hatasi_sapma_carpani", yol)),
        c1_makul_aralik=aralik("c1_makul_aralik"),
        c2_makul_aralik=aralik("c2_makul_aralik"),
    )


def _simulator_yukle(veri: dict[str, Any]) -> SimulatorYapilandirmasi:
    yol = "simulator"
    ofset = _zorunlu(veri, "miknatis_ofseti_mm", yol)
    arka_plan = _zorunlu(veri, "arka_plan_T", yol)
    for ad, deger in (("miknatis_ofseti_mm", ofset), ("arka_plan_T", arka_plan)):
        if not isinstance(deger, (list, tuple)) or len(deger) != 2:
            raise YapilandirmaHatasi(f"{yol}.{ad} iki elemanlı olmalıdır")
    return SimulatorYapilandirmasi(
        bobin_yaricapi_m=float(_zorunlu(veri, "bobin_yaricapi_m", yol)),
        demet_yari_acisi_derece=float(_zorunlu(veri, "demet_yari_acisi_derece", yol)),
        sarim_sayisi=int(_zorunlu(veri, "sarim_sayisi", yol)),
        olcum_cercevesi_acisi_derece=float(_zorunlu(veri, "olcum_cercevesi_acisi_derece", yol)),
        miknatis_ofseti_mm=[float(ofset[0]), float(ofset[1])],
        roll_mrad=float(_zorunlu(veri, "roll_mrad", yol)),
        arka_plan_T=[float(arka_plan[0]), float(arka_plan[1])],
        arka_plan_surukleme_T_s=float(veri.get("arka_plan_surukleme_T_s", 0.0)),
        harmonik_gurultu_bagil=float(veri.get("harmonik_gurultu_bagil", 0.0)),
        harmonik_surukleme_bagil_s=float(veri.get("harmonik_surukleme_bagil_s", 0.0)),
        yerlesim_hatasi_radyal_mm=_dogrula_dort_eleman(
            veri.get("yerlesim_hatasi_radyal_mm", [0.0] * BOBIN_SAYISI),
            f"{yol}.yerlesim_hatasi_radyal_mm",
        ),
        yerlesim_hatasi_acisal_mrad=_dogrula_dort_eleman(
            veri.get("yerlesim_hatasi_acisal_mrad", [0.0] * BOBIN_SAYISI),
            f"{yol}.yerlesim_hatasi_acisal_mrad",
        ),
        sarim_hatasi_bagil=_dogrula_dort_eleman(
            veri.get("sarim_hatasi_bagil", [0.0] * BOBIN_SAYISI), f"{yol}.sarim_hatasi_bagil"
        ),
        tohum=int(veri.get("tohum", 0)),
    )


def _dosya_girisi_yukle(veri: dict[str, Any]) -> DosyaGirisiYapilandirmasi:
    v = VARSAYILAN_DOSYA_GIRISI
    return DosyaGirisiYapilandirmasi(
        kilit_dosyasi=str(veri.get("kilit_dosyasi", v.kilit_dosyasi)),
        zaman_asimi_s=float(veri.get("zaman_asimi_s", v.zaman_asimi_s)),
        yoklama_araligi_s=float(veri.get("yoklama_araligi_s", v.yoklama_araligi_s)),
    )


def yapilandirma_yukle(dosya: str | Path) -> Yapilandirma:
    """YAML dosyasını okuyup doğrulanmış Yapılandırma nesnesi döndürür."""
    dosya_yolu = Path(dosya)
    if not dosya_yolu.exists():
        raise YapilandirmaHatasi(f"Yapılandırma dosyası bulunamadı: {dosya_yolu}")
    with dosya_yolu.open(encoding="utf-8") as f:
        veri = yaml.safe_load(f)
    if not isinstance(veri, dict):
        raise YapilandirmaHatasi(f"{dosya_yolu} bir YAML sözlüğü içermiyor")

    for bolum in (
        "genel",
        "miknatis",
        "modlar",
        "harmonikler",
        "guc_kaynaklari",
        "guvenlik",
        "kalibrasyon",
        "duzeltme",
        "dogrulama",
        "simulator",
    ):
        if bolum not in veri:
            raise YapilandirmaHatasi(f"Yapılandırmada '{bolum}' bölümü eksik")

    return Yapilandirma(
        genel=_genel_yukle(veri["genel"]),
        miknatis=_miknatis_yukle(veri["miknatis"]),
        modlar=_modlar_yukle(veri["modlar"]),
        harmonikler=_harmonikler_yukle(veri["harmonikler"]),
        guc_kaynaklari=_guc_kaynaklari_yukle(veri["guc_kaynaklari"]),
        guvenlik=_guvenlik_yukle(veri["guvenlik"]),
        kalibrasyon=_kalibrasyon_yukle(veri["kalibrasyon"]),
        duzeltme=_duzeltme_yukle(veri["duzeltme"]),
        dogrulama=_dogrulama_yukle(veri["dogrulama"]),
        simulator=_simulator_yukle(veri["simulator"]),
        dosya_girisi=_dosya_girisi_yukle(veri.get("dosya_girisi", {})),
        kaynak_dosya=dosya_yolu,
    )
