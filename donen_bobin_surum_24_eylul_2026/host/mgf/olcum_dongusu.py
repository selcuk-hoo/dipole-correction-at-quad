"""Merkezleme için sürekli ölçüm döngüsü (arayüzden bağımsız durum makinesi).

Hiçbir yöntem (guvenli_durdur hariç) bloklamaz: arayüz `tick()`'i kısa
aralıklarla (~50 ms) çağırır, her çağrıda cihazdan gelen paketler işlenir ve
durum makinesi bir adım ilerler. Böylece pencere donmaz; aynı sınıf sahte bir
cihazla da test edilebilir.

Döngü (otomatik yazma açıkken):

    HIZ_BEKLENIYOR   -> hız hedefe oturdu ve ek bekleme bitti
    KILIT_BEKLENIYOR -> kilit dosyası var: merkezleme'nin akımları değiştirip
                        kilidi silmesi bekleniyor
    VERI_TOPLANIYOR  -> kilit silindi: SİLİNDİKTEN SONRA gelen örneklerle
                        `pencere_s` dolunca ölç, kilide yaz -> KILIT_BEKLENIYOR

Kilit silinmeden önceki örnekler kullanılmaz; çünkü merkezleme kilidi yeni
akımlar oturduktan sonra siler.
"""
from __future__ import annotations

import enum
import math
import time
from collections import deque
from datetime import datetime
from typing import Callable

import numpy as np

from . import protocol
from .merkezleme_koprusu import (
    FILTRE_INDEKSI,
    HARMONIK_SAYISI,
    HIZ_INDEKSI,
    KAZANC_INDEKSI,
    OlcumKaydi,
    OlcumSonucu,
    Parametreler,
    kilide_yaz,
    olcum_hesapla,
    referans_faz_ofseti,
)

DURMUS_HIZ_HZ = 0.2
KANAL_GECIS_S = 0.25  # kanal değişiminden sonra atılan veri süresi
GECMIS_UZUNLUGU = 20  # ortalama ± σ için tutulan son ölçüm sayısı


class Durum(enum.Enum):
    BAGLI_DEGIL = "Bağlı değil"
    HAZIR = "Hazır (motor duruyor)"
    HIZ_BEKLENIYOR = "Hız oturuyor"
    DONUYOR = "Sürekli ölçüm (merkezleme'ye yazılmıyor)"
    KILIT_BEKLENIYOR = "Merkezleme bekleniyor"
    VERI_TOPLANIYOR = "Ölçülüyor"
    DURDURULUYOR = "Durduruluyor"
    HATA = "Hata"


_DONUYOR = (Durum.HIZ_BEKLENIYOR, Durum.DONUYOR, Durum.KILIT_BEKLENIYOR, Durum.VERI_TOPLANIYOR)


class OlcumDongusu:
    def __init__(
        self,
        p: Parametreler,
        baglanti,
        motor,
        gunluk: Callable[[str], None] = lambda m: None,
        saat: Callable[[], float] = time.monotonic,
    ) -> None:
        self.p = p
        self.conn = baglanti
        self.engine = motor
        self.gunluk = gunluk
        self.saat = saat

        self.durum = Durum.BAGLI_DEGIL
        self.hata_metni = ""
        self.kanal = p.varsayilan_kanal
        self.hedef_hiz_hz = p.hiz_hz
        self.faz_ofseti_derece = p.faz_ofseti_derece
        self.otomatik_yaz = True
        self.son_sonuc: OlcumSonucu | None = None
        self.son_sonuc_zamani: datetime | None = None
        self.olcum_sayisi = 0  # merkezleme'ye yazılan
        self.doyma_uyarisi = False
        self.gecmis: deque[OlcumSonucu] = deque(maxlen=GECMIS_UZUNLUGU)
        self.kayit = OlcumKaydi(p.kayit_dizini)
        self.csv_kaydet = True

        self._baglanti_koptu = False
        self._hiz_oturdu_zamani: float | None = None
        self._toplama_baslangici = 0
        self._surekli_baslangici = 0
        self._durdurma_zamani = 0.0
        self._tek_istek: str | None = None  # "tek" | "referans"
        self._tek_baslangici = 0

    @property
    def donuyor(self) -> bool:
        return self.durum in _DONUYOR

    @property
    def gereken_ornek(self) -> int:
        return int(math.ceil(self.p.pencere_s * self.p.ornekleme_sps))

    def genlik_istatistigi(self) -> tuple[int, np.ndarray, np.ndarray]:
        """Geçmişteki ölçümlerden (N, genlik, σ), n = 1..HARMONIK_SAYISI için,
        Tesla cinsinden (r_ref'te).

        Genlik, karmaşık değerlerin ortalamasının mutlak değeridir: harmoniğin
        fazı kararlı olduğundan gürültü √N ile azalır (genliklerin ortalaması
        alınsaydı gürültü tabanı yukarı kayardı). σ, tek ölçümlerin karmaşık
        düzlemdeki saçılımıdır."""
        bos = np.zeros(HARMONIK_SAYISI)
        if not self.gecmis:
            return 0, bos, bos
        c = np.array([s.harmonikler for s in self.gecmis])
        sigma = np.hypot(c.real.std(axis=0), c.imag.std(axis=0)) if len(c) > 1 else bos
        return len(c), np.abs(c.mean(axis=0)), sigma

    def gecmisi_sifirla(self) -> None:
        self.gecmis.clear()

    # ------------------------------------------------------------------
    # Kullanıcı eylemleri
    # ------------------------------------------------------------------
    def baglan(self, ip: str | None = None) -> bool:
        self.conn.host = ip or self.p.ip
        self.conn.port = self.p.port
        self.conn.auto_reconnect = True
        if not self.conn.connect():
            self.gunluk(f"Bağlantı kurulamadı: {self.conn.host}:{self.conn.port}")
            return False
        self.gunluk(f"Bağlandı: {self.conn.host}:{self.conn.port}")
        self._cihazi_hazirla()
        self._baglanti_koptu = False
        self.hata_metni = ""
        self.durum = Durum.HAZIR
        return True

    def kes(self, bekle: Callable[[float], None] = time.sleep) -> None:
        if self.durum is not Durum.BAGLI_DEGIL:
            self.guvenli_durdur(bekle)
            self.conn.disconnect()
            self.gunluk("Bağlantı kesildi.")
        self.durum = Durum.BAGLI_DEGIL

    def kanal_sec(self, ad: str) -> None:
        if ad not in self.p.kanallar:
            raise ValueError(f"Bilinmeyen kanal: {ad}")
        self.kanal = ad
        if self.conn.connected and self.durum is not Durum.BAGLI_DEGIL:
            self._kanal_gonder()
            self.gunluk(f"Kanal: {ad}")
        # Eski kanaldan gelen örnekler ölçüme karışmasın
        gecis = self.engine.total_samples_received + int(KANAL_GECIS_S * self.p.ornekleme_sps)
        self._toplama_baslangici = gecis
        self._tek_baslangici = gecis
        self._surekli_baslangici = gecis
        self.gecmisi_sifirla()

    def hiz_ayarla(self, hz: float) -> float:
        hz = max(0.0, min(float(hz), self.p.max_hiz_hz))
        degisti = hz != self.hedef_hiz_hz
        self.hedef_hiz_hz = hz
        if self.donuyor and degisti:
            self.gecmisi_sifirla()
            if hz <= 0:
                self.durdur()
            else:
                self.conn.send_command(protocol.CMD_SET_MOTOR_SPEED, float(hz))
                self.gunluk(f"Hız: {hz:g} Hz")
                self._hiz_bekle()
        return hz

    def baslat(self) -> None:
        if self.durum not in (Durum.HAZIR, Durum.HATA) or not self.conn.connected:
            return
        if self.hedef_hiz_hz <= 0:
            self.gunluk("Hız sıfır; başlatılmadı.")
            return
        self.hata_metni = ""
        self.gecmisi_sifirla()
        self.conn.send_command(protocol.CMD_SET_SERVO, 1)
        self.conn.send_command(protocol.CMD_SET_MOTOR_SPEED, float(self.hedef_hiz_hz))
        self.gunluk(f"Motor başlatıldı: {self.hedef_hiz_hz:g} Hz")
        self._hiz_bekle()

    def durdur(self) -> None:
        if not self.donuyor:
            return
        self._durdurmaya_basla()
        self.gunluk("Motor durduruluyor...")

    def tek_olcum(self, referans: bool = False) -> None:
        """Kilide yazmadan bir ölçüm. `referans` ise faz ofsetini, ölçülen
        dipol saf normal ve pozitif görünecek şekilde ayarlar."""
        if not self.donuyor:
            self.gunluk("Önce motoru başlatın.")
            return
        self._tek_istek = "referans" if referans else "tek"
        self._tek_baslangici = self.engine.total_samples_received
        self.gunluk("Referans ölçümü alınıyor..." if referans else "Tek ölçüm alınıyor...")

    def guvenli_durdur(self, bekle: Callable[[float], None] = time.sleep) -> None:
        """Bloklayarak: motoru durdur, durmasını bekle, servoyu kapat."""
        if not self.conn.connected:
            return
        self.conn.send_command(protocol.CMD_SET_MOTOR_SPEED, 0.0)
        bitis = self.saat() + self.p.durma_zaman_asimi_s
        while self.saat() < bitis:
            self.engine.process_queue(self.conn.rx_queue)
            if abs(self.engine.motor_speed) < DURMUS_HIZ_HZ:
                break
            bekle(0.1)
        self.conn.send_command(protocol.CMD_SET_SERVO, 0)
        self._tek_istek = None
        if self.durum is not Durum.BAGLI_DEGIL:
            self.durum = Durum.HAZIR

    # ------------------------------------------------------------------
    # Durum makinesi
    # ------------------------------------------------------------------
    def tick(self) -> None:
        if self.durum is Durum.BAGLI_DEGIL:
            return
        if not self.conn.connected:
            if not self._baglanti_koptu:
                self._baglanti_koptu = True
                self.hata_bildir("Bağlantı koptu; yeniden bağlanılınca motor durdurulacak.")
            return
        if self._baglanti_koptu:
            # Otomatik yeniden bağlanma oldu: önce güvenli duruma getir
            self._baglanti_koptu = False
            self.conn.send_command(protocol.CMD_SET_MOTOR_SPEED, 0.0)
            self.conn.send_command(protocol.CMD_SET_SERVO, 0)
            self._cihazi_hazirla()
            self.durum = Durum.HAZIR
            self.gunluk("Yeniden bağlandı; motor durduruldu, servo kapatıldı.")

        self.engine.process_queue(self.conn.rx_queue)
        simdi = self.saat()

        if self.durum is Durum.DURDURULUYOR:
            if (
                abs(self.engine.motor_speed) < DURMUS_HIZ_HZ
                or simdi - self._durdurma_zamani > self.p.durma_zaman_asimi_s
            ):
                self.conn.send_command(protocol.CMD_SET_SERVO, 0)
                self.durum = Durum.HATA if self.hata_metni else Durum.HAZIR
                self.gunluk("Motor durdu, servo kapatıldı.")
            return

        if not self.donuyor:
            return

        if not self._hiz_tamam():
            if self.durum is not Durum.HIZ_BEKLENIYOR:
                self.gunluk(f"Hız tolerans dışında ({self.engine.motor_speed:.2f} Hz); bekleniyor.")
            self._hiz_bekle()
            return

        if self.durum is Durum.HIZ_BEKLENIYOR:
            if self._hiz_oturdu_zamani is None:
                self._hiz_oturdu_zamani = simdi
            if simdi - self._hiz_oturdu_zamani < self.p.oturma_suresi_s:
                return
            self.gunluk(f"Hız oturdu: {self.engine.motor_speed:.2f} Hz")
            self.durum = Durum.KILIT_BEKLENIYOR
            self._tek_baslangici = max(self._tek_baslangici, self.engine.total_samples_received)

        if not self.engine.rotor_online:
            return

        self._tek_istegi_isle()
        if not self.donuyor:  # tek ölçüm hata verip durdurmuş olabilir
            return

        if not self.otomatik_yaz:
            # Sürekli ölçüm: her `pencere_s`'de bir, birbiriyle örtüşmeyen veriyle
            simdiki = self.engine.total_samples_received
            if self.durum is not Durum.DONUYOR:
                self.durum = Durum.DONUYOR
                self._surekli_baslangici = max(self._surekli_baslangici, simdiki)
            if self._taze_ornek(self._surekli_baslangici) >= self.gereken_ornek:
                self._olc("surekli")
                self._surekli_baslangici = simdiki
            return
        if self.durum is Durum.DONUYOR:
            self.durum = Durum.KILIT_BEKLENIYOR

        if self.durum is Durum.KILIT_BEKLENIYOR:
            if not self.p.kilit_dosyasi.exists():
                self.durum = Durum.VERI_TOPLANIYOR
                self._toplama_baslangici = max(
                    self._toplama_baslangici, self.engine.total_samples_received
                )
            return

        # VERI_TOPLANIYOR
        if self._taze_ornek(self._toplama_baslangici) < self.gereken_ornek:
            return
        sonuc = self._olc("merkezleme")
        if sonuc is None:
            self._toplama_baslangici = self.engine.total_samples_received
            return
        kilide_yaz(sonuc, self.p.kilit_dosyasi)
        self.olcum_sayisi += 1
        self.gunluk(f"Ölçüm #{self.olcum_sayisi} yazıldı: " + ozet(sonuc))
        self.durum = Durum.KILIT_BEKLENIYOR

    # ------------------------------------------------------------------
    # Yardımcılar
    # ------------------------------------------------------------------
    def _cihazi_hazirla(self) -> None:
        c = self.conn.send_command
        c(protocol.CMD_SET_GAIN, KAZANC_INDEKSI[self.p.kazanc])
        c(protocol.CMD_SET_PGA_BYPASS, 0)
        c(protocol.CMD_SET_RATE, HIZ_INDEKSI[self.p.ornekleme_sps])
        c(protocol.CMD_SET_FILTER, FILTRE_INDEKSI[self.p.filtre])
        c(protocol.CMD_SET_DATA_MODE, 1)  # Voltage
        self._kanal_gonder()
        self.engine.live_rate_sps = self.p.ornekleme_sps
        self.engine.current_gain = float(self.p.kazanc)
        self.engine.phase_offset_deg = 0.0  # faz ofseti bu programda ayrıca uygulanır
        self.gunluk(
            f"ADC: {self.p.kazanc}x, {self.p.ornekleme_sps:g} SPS, {self.p.filtre}; kanal {self.kanal}"
        )

    def _kanal_gonder(self) -> None:
        pos, neg = self.p.kanallar[self.kanal]
        self.conn.send_command(protocol.CMD_SET_SCAN_CHANNELS, (pos << 8) | neg)

    def _hiz_bekle(self) -> None:
        self._hiz_oturdu_zamani = None
        self.durum = Durum.HIZ_BEKLENIYOR

    def _hiz_tamam(self) -> bool:
        return abs(abs(self.engine.motor_speed) - self.hedef_hiz_hz) <= self.p.hiz_toleransi_hz

    def _taze_ornek(self, baslangic: int) -> int:
        return self.engine.total_samples_received - baslangic

    def _durdurmaya_basla(self) -> None:
        self.conn.send_command(protocol.CMD_SET_MOTOR_SPEED, 0.0)
        self._durdurma_zamani = self.saat()
        self._tek_istek = None
        self.durum = Durum.DURDURULUYOR

    def _olc(self, tur: str) -> OlcumSonucu | None:
        """Son `pencere_s` verisinden ölç; başarılıysa göster, geçmişe ve
        CSV'ye ekle. `tur`: merkezleme | surekli | tek | referans."""
        if self.engine.current_data_mode != 1:
            self.hata_bildir("Cihaz Voltage kipinde değil; ölçüm yapılamadı.")
            return None
        aci, gerilim = self.engine.get_latest_data(self.gereken_ornek)
        try:
            sonuc = olcum_hesapla(
                aci, gerilim, self.engine.motor_speed, self.p.bobin, self.p.r_ref_m,
                self.faz_ofseti_derece,
            )
        except ValueError as hata:
            self.gunluk(f"Ölçüm hesaplanamadı: {hata}")
            return None
        self.son_sonuc = sonuc
        self.son_sonuc_zamani = datetime.now()
        self.doyma_uyarisi = sonuc.tepe_V > self.p.doyma_uyari_orani * self.p.tam_olcek_V
        if self.doyma_uyarisi:
            self.gunluk(
                f"UYARI: sinyal tepesi {sonuc.tepe_V * 1e3:.1f} mV, ADC tam ölçeği "
                f"{self.p.tam_olcek_V * 1e3:.1f} mV; kazancı düşürün."
            )
        if tur != "referans":
            self.gecmis.append(sonuc)
        if self.csv_kaydet:
            try:
                self.kayit.ekle(sonuc, tur, self.kanal, self.faz_ofseti_derece)
            except OSError as hata:
                self.csv_kaydet = False
                self.gunluk(f"CSV'ye yazılamadı, kayıt kapatıldı: {hata}")
        return sonuc

    def _tek_istegi_isle(self) -> None:
        if self._tek_istek is None or self._taze_ornek(self._tek_baslangici) < self.gereken_ornek:
            return
        istek, self._tek_istek = self._tek_istek, None
        sonuc = self._olc(istek)
        if sonuc is None:
            return
        if istek == "referans":
            eski = self.faz_ofseti_derece
            self.faz_ofseti_derece = referans_faz_ofseti(sonuc, eski)
            self.gecmisi_sifirla()
            self.gunluk(f"Faz ofseti: {eski:.2f}° -> {self.faz_ofseti_derece:.2f}°")
        else:
            self.gunluk("Tek ölçüm: " + ozet(sonuc))

    def hata_bildir(self, metin: str) -> None:
        """Hata: motor dönüyorsa ve bağlantı varsa güvenli şekilde durdur."""
        self.hata_metni = metin
        self.gunluk("HATA: " + metin)
        if self.donuyor and self.conn.connected:
            self._durdurmaya_basla()
        else:
            self.durum = Durum.HATA


def ozet(s: OlcumSonucu) -> str:
    z = s.merkez_m * 1e6
    return (
        f"b0={s.c1.real:+.3e} a0={s.c1.imag:+.3e} b1={s.c2.real:+.3e} a1={s.c2.imag:+.3e} T, "
        f"G={s.gradyen_T_m:.4f} T/m, x_c={z.real:+.1f} µm, y_c={z.imag:+.1f} µm"
    )
