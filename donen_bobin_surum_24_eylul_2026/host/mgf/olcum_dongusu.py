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

Ölçüm çerçevesi (kanal, faz ofseti, gecikme, dönüş yönü, hız) merkezleme'ye
yazılırken değiştirilemez: merkezleme'nin kalibrasyonu bu çerçevede yapılır;
yarıda değişirse düzeltmeler yanlış yöne gider.

Gecikme ölçümü (iki yön): bir pencere bu yönde, motor ters çevrilip bir
pencere öbür yönde alınır; iki yön arasındaki faz farkından ADC ile enkoder
arasındaki sabit zaman gecikmesi bulunur ve sonraki tek yönlü ölçümlerde
uygulanır (bkz. merkezleme_koprusu.cift_yon_birlestir).
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
    cift_yon_hesapla,
    kilide_yaz,
    olcum_hesapla,
    referans_faz_ofseti,
    saglik_sorunlari,
)

DURMUS_HIZ_HZ = 0.2
KANAL_GECIS_S = 0.25  # kanal değişiminden sonra atılan veri süresi
GECMIS_UZUNLUGU = 20  # ortalama ± σ için tutulan son ölçüm sayısı
MIN_PENCERE_S = 0.5
MAX_ARDISIK_RED = 3  # sağlıksız bu kadar ölçümden sonra durdurulur
# Durma kararı için en az bu kadar beklenir: hız, saniyede bir gelen durum
# paketinden okunur; daha önce okunan değer durdurma komutundan eski olabilir.
MIN_DURMA_BEKLEMESI_S = 1.2
# Gecikme ve referans, ancak bu kadar kesin ölçülmüşse uygulanır (1σ). Gecikme
# hatası 2 µs: 23 Hz'de 0.017° faz; merkez 150 µm'deyken yön değişiminde 0.09 µm.
GECIKME_BELIRSIZLIK_SINIRI_S = 2e-6
REFERANS_FAZ_SINIRI_DERECE = 0.05


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
        self.pencere_s = p.pencere_s
        # Faz ofseti her bobin için ayrıdır: bobinler dönen çerçevede farklı
        # açılarda durur (dik iki bobin arasında 90°). Bir bobinin ofsetiyle
        # öbürü ölçülürse merkez o açı kadar dönük raporlanır.
        self._faz_ofsetleri = {ad: p.faz_ofseti_derece for ad in p.kanallar}
        # Referans alınırken ölçülen hız (işaretli), bobin başına; None: alınmadı
        self._referans_hizlari: dict[str, float | None] = {ad: None for ad in p.kanallar}
        self.gecikme_s = p.gecikme_s
        self.gecikme_kaynagi = "parametre dosyası"
        self.yon = 1  # motor hız komutunun işareti
        self.otomatik_yaz = True
        self.son_sonuc: OlcumSonucu | None = None
        self.son_sonuc_zamani: datetime | None = None
        self.olcum_sayisi = 0  # merkezleme'ye yazılan
        self.doyma_uyarisi = False
        self.saglik: list[str] = []  # son ölçümün sağlık sorunları (boş: sağlıklı)
        self._rs485_hata_sayisi: int | None = None
        self.gecmis: deque[OlcumSonucu] = deque(maxlen=GECMIS_UZUNLUGU)
        self.kayit = OlcumKaydi(p.kayit_dizini)
        self.csv_kaydet = True

        self._baglanti_koptu = False
        self._hiz_oturdu_zamani: float | None = None
        self._toplama_baslangici = 0
        self._surekli_baslangici = 0
        self._durdurma_zamani = 0.0
        self._tek_istek: str | None = None  # "tek" | "referans" | "gecikme"
        self._tek_baslangici = 0
        self._yarim: tuple[np.ndarray, np.ndarray] | None = None  # gecikme ölçümünün ilk yönü
        self._beklenen_isaret: float | None = None  # ters çevirmeden sonra ölçülen hızın işareti
        self._ardisik_red = 0
        self._yazim_cercevesi: tuple | None = None

    @property
    def donuyor(self) -> bool:
        return self.durum in _DONUYOR

    @property
    def faz_ofseti_derece(self) -> float:
        """Seçili bobinin faz ofseti."""
        return self._faz_ofsetleri[self.kanal]

    @faz_ofseti_derece.setter
    def faz_ofseti_derece(self, deger: float) -> None:
        self._faz_ofsetleri[self.kanal] = deger

    @property
    def referans_alindi(self) -> bool:
        """Seçili bobin için bu oturumda referans alındı mı."""
        return self._referans_hizlari[self.kanal] is not None

    @property
    def cerceve(self) -> tuple:
        """Merkezleme'ye yazılan ölçümlerin karşılaştırılabilir olması için
        sabit kalması gerekenler."""
        return (self.kanal, self.faz_ofseti_derece, self.gecikme_s, self.yon, self.hedef_hiz_hz)

    @property
    def cerceve_kilitli(self) -> bool:
        return self.otomatik_yaz and self.donuyor

    @property
    def gecikme_olculuyor(self) -> bool:
        return self._tek_istek == "gecikme"

    def _kilitli_mi(self, eylem: str) -> bool:
        if self.cerceve_kilitli:
            self.gunluk(
                f"{eylem}: merkezleme'ye yazılırken yapılamaz (ölçüm çerçevesi değişir). "
                "Önce 'Merkezleme'ye yaz'ı kapatın."
            )
            return True
        return False

    @property
    def gereken_ornek(self) -> int:
        return int(math.ceil(self.pencere_s * self.p.ornekleme_sps))

    @property
    def max_pencere_s(self) -> float:
        """Cihaz arabelleğinin (DataEngine halka tamponu) %90'ı."""
        return 0.9 * getattr(self.engine, "max_points", 1_000_000) / self.p.ornekleme_sps

    def pencere_ayarla(self, saniye: float) -> float:
        """Ölçüm süresi: rastgele gürültü 1/√süre ile azalır; dönmeyle
        eşzamanlı hatalar ve yavaş sürüklenme azalmaz."""
        saniye = max(MIN_PENCERE_S, min(float(saniye), self.max_pencere_s))
        if saniye != self.pencere_s:
            self.pencere_s = saniye
            self.gecmisi_sifirla()  # farklı süreli ölçümler aynı ortalamaya girmesin
            self.gunluk(f"Ölçüm süresi: {saniye:g} s")
        return saniye

    def harmonik_istatistigi(self) -> tuple[int, np.ndarray, np.ndarray]:
        """Geçmişteki ölçümlerden (N, ortalama C_n, σ_b + i·σ_a), n = 1..H,
        Tesla cinsinden (r_ref'te).

        Ortalama karmaşık değerlerin ortalamasıdır: harmoniğin fazı kararlı
        olduğundan gürültü √N ile azalır (genliklerin ortalaması alınsaydı
        gürültü tabanı yukarı kayardı). σ, tek ölçümlerin normal ve skew
        bileşenlerindeki saçılımıdır."""
        if not self.gecmis:
            return 0, np.zeros(HARMONIK_SAYISI, complex), np.zeros(HARMONIK_SAYISI, complex)
        c = np.array([s.harmonikler for s in self.gecmis])
        sigma = (
            c.real.std(axis=0) + 1j * c.imag.std(axis=0) if len(c) > 1
            else np.zeros(HARMONIK_SAYISI, complex)
        )
        return len(c), c.mean(axis=0), sigma

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

    def otomatik_yaz_ayarla(self, acik: bool) -> bool:
        if acik and self.gecikme_olculuyor:
            self.gunluk("Gecikme ölçümü sürerken merkezleme'ye yazma açılamaz.")
            return False
        self.otomatik_yaz = acik
        self.gunluk("Merkezleme'ye otomatik yazma " + ("açık." if acik else "kapalı."))
        if acik and self._yazim_cercevesi not in (None, self.cerceve):
            self.gunluk(
                "UYARI: ölçüm çerçevesi (kanal/faz ofseti/gecikme/yön/hız) önceki yazımlardan "
                "farklı. Merkezleme yarıda ise kalibrasyonu geçersiz olabilir; yeniden başlatın."
            )
        return True

    def kanal_sec(self, ad: str) -> bool:
        if ad not in self.p.kanallar:
            raise ValueError(f"Bilinmeyen kanal: {ad}")
        if ad == self.kanal:
            return True
        if self._kilitli_mi("Kanal değiştirme"):
            return False
        self._gecikme_olcumunu_iptal_et("kanal değişti")
        self.kanal = ad
        if self.conn.connected and self.durum is not Durum.BAGLI_DEGIL:
            self._kanal_gonder()
            self.gunluk(f"Kanal: {ad}")
        self.gunluk(
            f"{ad} faz ofseti: {self.faz_ofseti_derece:.2f}°"
            + ("" if self.referans_alindi else " (bu bobin için referans alınmadı; referans alın)")
        )
        # Eski kanaldan gelen örnekler ölçüme karışmasın
        gecis = self.engine.total_samples_received + int(KANAL_GECIS_S * self.p.ornekleme_sps)
        self._toplama_baslangici = gecis
        self._tek_baslangici = gecis
        self._surekli_baslangici = gecis
        self.gecmisi_sifirla()
        return True

    def hiz_ayarla(self, hz: float) -> float:
        """Hız büyüklüğü (Hz); yön `self.yon`'dadır. Dönen değer geçerli hedef."""
        hz = max(0.0, min(float(hz), self.p.max_hiz_hz))
        degisti = hz != self.hedef_hiz_hz
        if self.donuyor and degisti:
            if self._kilitli_mi("Hız değiştirme"):
                return self.hedef_hiz_hz
            self._gecikme_olcumunu_iptal_et("hız değişti")
            self.hedef_hiz_hz = hz
            self.gecmisi_sifirla()
            if hz <= 0:
                self.durdur()
            else:
                self._hiz_gonder()
                self.gunluk(f"Hız: {hz:g} Hz")
                self._hiz_bekle()
        self.hedef_hiz_hz = hz
        return hz

    def baslat(self) -> None:
        if self.durum not in (Durum.HAZIR, Durum.HATA) or not self.conn.connected:
            return
        if self.hedef_hiz_hz <= 0:
            self.gunluk("Hız sıfır; başlatılmadı.")
            return
        self.hata_metni = ""
        self.gecmisi_sifirla()
        self._beklenen_isaret = None
        self._ardisik_red = 0
        self.conn.send_command(protocol.CMD_SET_SERVO, 1)
        self._hiz_gonder()
        self.gunluk(f"Motor başlatıldı: {self.yon * self.hedef_hiz_hz:+g} Hz")
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
        if referans and self._kilitli_mi("Referans"):
            return
        if self.gecikme_olculuyor:
            self.gunluk("Gecikme ölçümü sürüyor; bitince tekrar deneyin.")
            return
        self._tek_istek = "referans" if referans else "tek"
        self._tek_baslangici = self.engine.total_samples_received
        self.gunluk("Referans ölçümü alınıyor..." if referans else "Tek ölçüm alınıyor...")

    def gecikme_olc(self) -> None:
        """İki yönlü ölçümle ADC-enkoder gecikmesini ölç (motor bir kez ters
        döner). Sonraki ölçümler bu gecikmeyle analiz edilir; faz ofseti
        yeni gecikmeye taşınır."""
        if not self.donuyor:
            self.gunluk("Önce motoru başlatın.")
            return
        if self._kilitli_mi("Gecikme ölçümü") or self.gecikme_olculuyor:
            return
        self._tek_istek = "gecikme"
        self._yarim = None
        self._tek_baslangici = self.engine.total_samples_received
        self.gunluk("Gecikme ölçümü: önce bu yönde, sonra ters yönde birer pencere...")

    def guvenli_durdur(self, bekle: Callable[[float], None] = time.sleep) -> None:
        """Bloklayarak: motoru durdur, durmasını bekle, servoyu kapat."""
        if not self.conn.connected:
            return
        self.conn.send_command(protocol.CMD_SET_MOTOR_SPEED, 0.0)
        baslangic = self.saat()
        bitis = baslangic + self.p.durma_zaman_asimi_s
        while self.saat() < bitis:
            self.engine.process_queue(self.conn.rx_queue)
            if (
                abs(self.engine.motor_speed) < DURMUS_HIZ_HZ
                and self.saat() - baslangic >= MIN_DURMA_BEKLEMESI_S
            ):
                break
            bekle(0.1)
        self.conn.send_command(protocol.CMD_SET_SERVO, 0)
        self._tek_istek = None
        self._yarim = None
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
            # Otomatik yeniden bağlanma oldu. Firmware bağlantı kopunca motoru
            # durdurmaz: motor hâlâ dönüyor olabilir. Normal durdurmadaki gibi
            # önce hız sıfırlanır, motor durunca (ya da zaman aşımında) servo
            # kapatılır; dönerken servoyu kesmek mili rampasız bırakır.
            self._baglanti_koptu = False
            self._durdurmaya_basla()
            self._cihazi_hazirla()
            self.gunluk("Yeniden bağlandı; motor durduruluyor, durunca servo kapatılacak.")

        self.engine.process_queue(self.conn.rx_queue)
        self._rs485_hatalarini_izle()
        simdi = self.saat()

        if self.durum is Durum.DURDURULUYOR:
            gecen = simdi - self._durdurma_zamani
            if (
                abs(self.engine.motor_speed) < DURMUS_HIZ_HZ and gecen >= MIN_DURMA_BEKLEMESI_S
            ) or gecen > self.p.durma_zaman_asimi_s:
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
        if sonuc is None or self._saglik_reddi(sonuc):
            self._toplama_baslangici = self.engine.total_samples_received
            return
        kilide_yaz(sonuc, self.p.kilit_dosyasi)
        self._yazim_cercevesi = self.cerceve
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

    def _hiz_gonder(self) -> None:
        self.conn.send_command(protocol.CMD_SET_MOTOR_SPEED, float(self.yon * self.hedef_hiz_hz))

    def _hiz_bekle(self) -> None:
        self._hiz_oturdu_zamani = None
        self.durum = Durum.HIZ_BEKLENIYOR

    def _hiz_tamam(self) -> bool:
        hiz = self.engine.motor_speed
        if self._beklenen_isaret is not None and hiz * self._beklenen_isaret <= 0:
            return False  # ters çevirme henüz bitmedi (durum paketi gecikmeli gelir)
        return abs(abs(hiz) - self.hedef_hiz_hz) <= self.p.hiz_toleransi_hz

    def _yonu_cevir(self) -> None:
        isaret = math.copysign(1.0, self.engine.motor_speed)
        self.yon = -self.yon
        self._beklenen_isaret = -isaret
        self._hiz_gonder()
        self.gunluk(f"Motor ters çevriliyor: {self.yon * self.hedef_hiz_hz:+g} Hz")
        self._hiz_bekle()

    def _gecikme_olcumunu_iptal_et(self, neden: str) -> None:
        if self.gecikme_olculuyor:
            self.gunluk(f"Gecikme ölçümü iptal edildi ({neden}).")
        if self.gecikme_olculuyor or self._yarim is not None:
            self._tek_istek = None
            self._yarim = None

    def _saglik_reddi(self, sonuc: OlcumSonucu) -> bool:
        """Merkezleme'ye yazılacak ölçüm için sağlık kontrolü."""
        if not self.saglik:
            self._ardisik_red = 0
            return False
        self._ardisik_red += 1
        self.gunluk("Ölçüm reddedildi: " + "; ".join(self.saglik))
        if self._ardisik_red >= MAX_ARDISIK_RED:
            self.hata_bildir(f"Üst üste {MAX_ARDISIK_RED} ölçüm reddedildi ({self.saglik[0]}).")
        return True

    def _rs485_hatalarini_izle(self) -> None:
        """Stator, ADC sağlama toplamı tutmayan örnekleri atar ve sayar (durum
        paketi, saniyede bir). Atılan örnek akı integralini bozar; saat
        sıçraması kontrolü onu ayrıca yakalar, burada yalnızca bildirilir."""
        sayi = getattr(self.engine, "rs485_error_count", None)
        if sayi is None:
            return
        if self._rs485_hata_sayisi is not None and sayi != self._rs485_hata_sayisi:
            fark = (sayi - self._rs485_hata_sayisi) % 65536
            self.gunluk(f"UYARI: stator {fark} bozuk ADC örneği attı (RS485); o andaki ölçüm reddedilebilir.")
        self._rs485_hata_sayisi = sayi

    def _taze_ornek(self, baslangic: int) -> int:
        return self.engine.total_samples_received - baslangic

    def _durdurmaya_basla(self) -> None:
        self.conn.send_command(protocol.CMD_SET_MOTOR_SPEED, 0.0)
        self._durdurma_zamani = self.saat()
        self._tek_istek = None
        self._yarim = None
        self.durum = Durum.DURDURULUYOR

    def _son_veri(self) -> tuple[np.ndarray, np.ndarray] | None:
        if self.engine.current_data_mode != 1:
            self.hata_bildir("Cihaz Voltage kipinde değil; ölçüm yapılamadı.")
            return None
        aci, gerilim = self.engine.get_latest_data(self.gereken_ornek)
        return np.array(aci, dtype=np.float64), np.array(gerilim, dtype=np.float64)

    def _olc(self, tur: str, ilk_yon: tuple[np.ndarray, np.ndarray] | None = None) -> OlcumSonucu | None:
        """Son `pencere_s` verisinden ölç; başarılıysa göster, geçmişe ve
        CSV'ye ekle. `tur`: merkezleme | surekli | tek | referans | gecikme.
        `ilk_yon` verilirse (öbür yöndeki veri) çift yönlü ölçülür."""
        veri = self._son_veri()
        if veri is None:
            return None
        try:
            if ilk_yon is None:
                sonuc = olcum_hesapla(
                    *veri, self.p.ornekleme_sps, self.p.bobin, self.p.r_ref_m,
                    self.faz_ofseti_derece, gecikme_s=self.gecikme_s,
                )
            else:
                sonuc = cift_yon_hesapla(
                    ilk_yon, veri, self.p.ornekleme_sps, self.p.bobin, self.p.r_ref_m,
                    self.faz_ofseti_derece, gecikme_s=self.gecikme_s,
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
        self.saglik = saglik_sorunlari(sonuc, self.p)
        if self.saglik and tur != "merkezleme":  # merkezleme'de reddedilirken yazılır
            self.gunluk("UYARI: " + "; ".join(self.saglik))
        if tur not in ("referans", "gecikme"):
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
        if self._tek_istek == "gecikme" and self._yarim is None:
            # İlk yön: veriyi sakla, motoru ters çevir; hız oturunca ikinci pencere
            self._yarim = self._son_veri()
            if self._yarim is not None:
                self._yonu_cevir()
            return
        istek, self._tek_istek = self._tek_istek, None
        ilk_yon, self._yarim = self._yarim, None
        sonuc = self._olc(istek, ilk_yon)
        if sonuc is None:
            return
        if istek == "referans":
            sigma = math.degrees(sonuc.faz_belirsizligi(1))
            if self.saglik or sigma > REFERANS_FAZ_SINIRI_DERECE:
                neden = "; ".join(self.saglik) or (
                    f"n = 1 fazı belirsiz (±{sigma:.3f}° > {REFERANS_FAZ_SINIRI_DERECE}°): "
                    "referans mıknatıs takılı mı, sinyal yeterli mi?"
                )
                self.gunluk(f"Referans kullanılmadı, faz ofseti değişmedi ({neden}).")
                return
            eski = self.faz_ofseti_derece
            self.faz_ofseti_derece = referans_faz_ofseti(sonuc, eski)
            self._referans_hizlari[self.kanal] = sonuc.hiz_hz
            self.gecmisi_sifirla()
            self.gunluk(f"Faz ofseti: {eski:.2f}° -> {self.faz_ofseti_derece:.2f}°")
        elif istek == "gecikme":
            self._gecikmeyi_uygula(sonuc)
        else:
            self.gunluk("Tek ölçüm: " + ozet(sonuc))

    def _gecikmeyi_uygula(self, sonuc: OlcumSonucu) -> None:
        if self.saglik:
            self.gunluk("Gecikme ölçümü kullanılmadı (sağlık sorunu); tekrarlayın.")
            return
        sigma = sonuc.gecikme_belirsizligi_s
        if not sigma <= GECIKME_BELIRSIZLIK_SINIRI_S:  # nan da reddedilir
            self.gunluk(
                f"Gecikme ölçümü kullanılmadı: belirsizlik ±{sigma * 1e6:.2f} µs > "
                f"{GECIKME_BELIRSIZLIK_SINIRI_S * 1e6:g} µs (sinyal yok ya da çok zayıf; "
                "mıknatıs takılı ve kanal doğru mu?)"
            )
            return
        eski, yeni = self.gecikme_s, sonuc.gecikme_s
        self.gecikme_s = yeni
        self.gecikme_kaynagi = f"ölçüldü, {abs(sonuc.hiz_hz):.1f} Hz"
        self.gecmisi_sifirla()
        self.gunluk(
            f"Gecikme: {eski * 1e3:.4f} ms -> {yeni * 1e3:.4f} ms (±{sigma * 1e6:.2f} µs). Kalıcı yapmak için "
            f"merkezleme_olcer.yaml -> olcum.gecikme_ms: {yeni * 1e3:.4f}"
        )
        for ad, hiz in self._referans_hizlari.items():
            if hiz is None:
                self.gunluk(f"{ad}: faz ofseti bu oturumda referansla ayarlanmadı; referansı yeniden alın.")
                continue
            # Referansta açı ω_ref·L_eski kadar geri kaydırılmıştı; aynı çerçeve için
            # faz ofseti ω_ref·(L_yeni - L_eski) kadar azaltılır.
            eski_ofset = self._faz_ofsetleri[ad]
            self._faz_ofsetleri[ad] = (eski_ofset - 360.0 * hiz * (yeni - eski)) % 360.0
            self.gunluk(
                f"{ad}: faz ofseti yeni gecikmeye taşındı: "
                f"{eski_ofset:.3f}° -> {self._faz_ofsetleri[ad]:.3f}°"
            )
        self.gunluk("Çift yönlü ölçüm: " + ozet(sonuc))

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
