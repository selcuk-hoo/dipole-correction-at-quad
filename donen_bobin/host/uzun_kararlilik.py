"""Uzun kararlılık ölçümü: tek oturum, dönen bobin hiç durmaz (enkoder referansı aynı kalır).

    cd donen_bobin/host && python uzun_kararlilik.py            # tam plan (~5 saat)
    python uzun_kararlilik.py --kisa                             # her faz 2 dk (önce bununla dene)
    python uzun_kararlilik.py --sureler 30 60 60 120 20          # dakika: ortam1 akimli1 ortam2 akimli2 ortam3

Fazlar (12 Kasım 2026 planı):
  1. ortam1     akımlar sıfır: akımsız taban (ortam dipolü B1, A1) ve motor dönmeye
                başladıktan sonra oturuyor mu. 11 Kasım'da akımsız dipol ~0.95 µT/saat
                (%2.7/saat) kaydı; ADC kazanç/ofset kayması bunu açıklayamaz. Adaylar:
                motorun ısınması (mıknatısı ve sargıları bobine yakın) ya da gerçek ortam.
                ortam1'deki sürüklenme ortam2/ortam3'tekinden büyükse motor, aynıysa ortam.
  2. merkezleme 9.5 A, tolerans 10 µm, otomatik (kalibrasyon + düzeltme)
  3. akimli1    merkezlenmiş akımlar açık: net merkez ve akımlar kaydedilir
  4. ortam2     akımlar sıfır: mıknatıs soğur, ortam kaydedilir
  5. akimli2    akimli1'in AYNI akımları (yeniden optimize edilmez): soğuyup yeniden
                ısınınca merkez aynı yere dönüyor mu (ısıl histerezis)
  6. ortam3     akımlar sıfır: kapanış ortam kaydı (iki akımlı faz da çevrelenir)

Her `--aralik` saniyede o aralıktaki bütün sağlıklı ölçümlerin ortalaması
`kayitlar/<oturum>/uzun_kararlilik.csv`'ye yazılır: ham B1/A1 (µT), C2 (mT), net
merkez (son ortam fazının son 10 dakikasının ortalaması arka plan olarak çıkarılmış),
saçılımlar ve dört akım. Her ölçüm ayrıca oturumun olcumler.csv'sinde; her 15 dk'da
10 s ham veri. Faz geçişleri ve hatalar Telegram'a (telegram-mesaj -h) gider.

Güvenlik: Pico bağlantısı koparsa, ADC takılırsa (gerilim sabit), 90 s sağlıklı
ölçüm gelmezse ya da akım ayarından 20 mA saparsa ölçüm durur; akımlar rampa ile
sıfırlanır, çıkışlar kapanır, motor durur (Ctrl+C dahil). Çalışırken bilgisayar
uyumaz (systemd-inhibit).
"""
from __future__ import annotations

import argparse
import csv
import math
import os
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import numpy as np

from kanal_testi import KOK  # sys.path'e depo kökünü ekler
from mgf.merkezleme_koprusu import parametreleri_yukle
from mgf.olcum_dongusu import Durum, OlcumDongusu

FAZLAR = ("ortam1", "akimli1", "ortam2", "akimli2", "ortam3")  # merkezleme ortam1'den sonra
SURELER_DK = (30, 60, 60, 120, 20)
ARKA_PLAN_SON_S = 600         # net merkez için ortam fazının son bu kadar saniyesi
HAM_KAYIT_ARALIGI_S = 900
SESSIZLIK_SINIRI_S = 90       # bu kadar süre sağlıklı ölçüm gelmezse dur
AKIM_SAPMA_SINIRI_A = 0.020
TELEGRAM = Path.home() / "bin" / "telegram-mesaj"


class OlcumHatasi(RuntimeError):
    pass


def kaydi_hesapla(olcumler: list, arka: tuple[complex, complex] | None, r_ref_m: float) -> dict[str, float]:
    """Bir aralıktaki ölçümlerin (her biri .harmonikler, .hiz_hz, .artik_orani,
    .ayiklanan_aci) ortalaması. `arka` (C1, C2, Tesla) verilirse net merkez de."""
    n = len(olcumler)
    c1 = np.array([o.harmonikler[0] for o in olcumler])
    c2 = np.array([o.harmonikler[1] for o in olcumler])
    k = {"n_olcum": n, "B1_uT": c1.real.mean() * 1e6, "A1_uT": c1.imag.mean() * 1e6,
         "sB1_uT": c1.real.std(ddof=1) * 1e6 if n > 1 else math.nan,
         "sA1_uT": c1.imag.std(ddof=1) * 1e6 if n > 1 else math.nan,
         "B2_mT": c2.real.mean() * 1e3, "A2_mT": c2.imag.mean() * 1e3,
         "x_net_um": math.nan, "y_net_um": math.nan, "sx_um": math.nan, "sy_um": math.nan,
         "hiz_hz": float(np.mean([o.hiz_hz for o in olcumler])),
         "artik_orani": float(np.median([o.artik_orani for o in olcumler])),
         "ayiklanan_aci": int(sum(getattr(o, "ayiklanan_aci", 0) for o in olcumler))}
    if arka is not None and abs(c2.mean() - arka[1]) > 1e-4:  # kuadrupol açık (≥ 0.1 mT)
        z = -r_ref_m * (c1 - arka[0]) / (c2 - arka[1]) * 1e6
        zo = -r_ref_m * (c1.mean() - arka[0]) / (c2.mean() - arka[1]) * 1e6
        k.update(x_net_um=zo.real, y_net_um=zo.imag,
                 sx_um=z.real.std(ddof=1) if n > 1 else math.nan,
                 sy_um=z.imag.std(ddof=1) if n > 1 else math.nan)
    return k


SUTUNLAR = ["zaman", "gecen_dk", "faz", "n_olcum", "B1_uT", "A1_uT", "sB1_uT", "sA1_uT", "B2_mT", "A2_mT",
            "x_net_um", "y_net_um", "sx_um", "sy_um", "hiz_hz", "artik_orani", "ayiklanan_aci",
            "I1_A", "I2_A", "I3_A", "I4_A"]


def faz_ozeti(satirlar: list[dict]) -> str:
    """Bir fazın kayıtlarından kısa özet: ortamda B1/A1, akımlıda net x/y (ort, σ, eğim)."""
    if len(satirlar) < 3:
        return "kayıt yok"
    t = np.array([s["gecen_dk"] for s in satirlar])
    akimli = math.isfinite(satirlar[-1]["x_net_um"])
    a, b, birim = (("x_net_um", "y_net_um", "µm") if akimli else ("B1_uT", "A1_uT", "µT"))
    parca = []
    for ad in (a, b):
        v = np.array([s[ad] for s in satirlar], dtype=float)
        m = np.isfinite(v)
        egim = np.polyfit(t[m], v[m], 1)[0] * 60 if m.sum() >= 3 else math.nan
        parca.append(f"{ad.split('_')[0]} {np.nanmean(v):+.2f} ± {np.nanstd(v, ddof=1):.2f} {birim}, "
                     f"{egim:+.2f} {birim}/saat")
    return "; ".join(parca)


class UzunOlcum:
    def __init__(self, p, kfg, dongu: OlcumDongusu, grup, sureler_s, aralik_s: float, bildir) -> None:
        self.p, self.kfg, self.d, self.grup = p, kfg, dongu, grup
        self.sureler_s, self.aralik_s, self.bildir = list(sureler_s), aralik_s, bildir
        self.t0 = time.monotonic()
        self._son_sonuc = None
        self._son_saglikli_t = time.monotonic()
        self._son_saglik_kontrol = 0.0
        self._biriken: list = []
        self._ortam_gecmisi: list[tuple[float, complex, complex]] = []  # (t, C1, C2): son ortam fazı
        self.arka: tuple[complex, complex] | None = None
        self.hedef_akimlar = np.zeros(4)
        self.akimli = False
        self._akim = [math.nan] * 4
        # Akım ayarı her değiştiğinde artar; okuma, başladığı andaki sayaçla saklanır.
        # Ayardan önce başlamış (eski) bir okuma sapma denetiminde kullanılmaz.
        self._ayar_sayaci = 0
        self._akim_sayaci = -1
        self._akim_kilidi = threading.Lock()
        self._akim_dur = threading.Event()
        self._akim_isi: threading.Thread | None = None
        self.csv_yolu = dongu.oturum.klasor() / "uzun_kararlilik.csv"
        with open(self.csv_yolu, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(SUTUNLAR)
        self.faz_satirlari: dict[str, list[dict]] = {}
        self.faz_ayarlari: dict[str, np.ndarray] = {}  # her fazda güç kaynaklarına yazılmış akımlar
        self._son_ham_t = 0.0

    # --- bekleme ve sağlık -------------------------------------------------
    def bekle(self, saniye: float) -> None:
        """Dönen bobin döngüsünü işleterek bekler; sağlık kontrolü yapar."""
        bitis = time.monotonic() + saniye
        while time.monotonic() < bitis:
            self.d.tick()
            self._yeni_olcumu_al()
            simdi = time.monotonic()
            if simdi - self._son_saglik_kontrol >= 1.0:
                self._son_saglik_kontrol = simdi
                self._sagligi_denetle()
            time.sleep(0.02)

    def _yeni_olcumu_al(self) -> None:
        s = self.d.son_sonuc
        if s is not None and s is not self._son_sonuc:
            self._son_sonuc = s
            if not self.d.saglik:
                self._biriken.append(s)
                self._son_saglikli_t = time.monotonic()

    def _sagligi_denetle(self) -> None:
        d = self.d
        if d.durum in (Durum.HATA, Durum.BAGLI_DEGIL) or not d.conn.connected:
            raise OlcumHatasi(f"dönen bobin bağlantısı/durumu: {d.durum.value} {getattr(d, 'hata_metni', '')}")
        veri = d._ham_veri(0.5)
        if veri is not None and len(veri[1]) > 100 and float(np.ptp(veri[1])) == 0.0:
            raise OlcumHatasi(f"ADC takıldı: gerilim {veri[1][0] * 1e3:.3f} mV'ta sabit")
        if time.monotonic() - self._son_saglikli_t > SESSIZLIK_SINIRI_S:
            raise OlcumHatasi(f"{SESSIZLIK_SINIRI_S} s sağlıklı ölçüm gelmedi")
        if self.akimli:
            with self._akim_kilidi:
                akim = np.array(self._akim)
                taze = self._akim_sayaci == self._ayar_sayaci
            if taze and np.all(np.isfinite(akim)) and np.max(np.abs(akim - self.hedef_akimlar)) > AKIM_SAPMA_SINIRI_A:
                raise OlcumHatasi(f"akımlar ayardan saptı: {akim.round(4)} (ayar {self.hedef_akimlar.round(4)})")

    def _akimlari_oku(self) -> None:
        while not self._akim_dur.is_set():
            sayac = self._ayar_sayaci
            try:
                akim = [float(a) for a in self.grup.akimlari_oku()]
            except Exception as hata:  # noqa: BLE001 - okunamazsa NaN; sapma denetimi atlanır
                # Yutulmasın: 12 Kasım'da sessiz bir zaman aşımı yanıt kaymasına yol açtı
                print(f"{datetime.now():%H:%M:%S}  UYARI: akım okunamadı: {hata!r}", flush=True)
                akim = [math.nan] * 4
            with self._akim_kilidi:
                self._akim, self._akim_sayaci = akim, sayac
            self._akim_dur.wait(2.0)

    def _ayar_degisti(self) -> None:
        with self._akim_kilidi:
            self._ayar_sayaci += 1

    def _rampala(self, hedef: np.ndarray) -> None:
        self.akimli = False
        self._ayar_degisti()
        self.grup.rampala(np.asarray(hedef, dtype=float))
        self._ayar_degisti()  # rampa sırasında başlamış okumalar da eski
        self.hedef_akimlar = np.asarray(hedef, dtype=float)
        self.akimli = bool(np.any(self.hedef_akimlar > 0))
        self._son_saglikli_t = time.monotonic()  # rampa sırasında ölçüm reddi olağan

    # --- fazlar --------------------------------------------------------------
    def kayit_fazi(self, faz: str, sure_s: float) -> None:
        self.bildir(f"▶ <b>{faz}</b> başladı ({sure_s / 60:.0f} dk)")
        self.d.otomatik_yaz_ayarla(False)  # sürekli ölçüm
        bitis = time.monotonic() + sure_s
        satirlar = self.faz_satirlari.setdefault(faz, [])
        self.faz_ayarlari[faz] = np.array(self.grup.ayar_akimlari_A, dtype=float)
        if not self.akimli:
            self._ortam_gecmisi = []
        self._biriken = []
        while time.monotonic() < bitis:
            self.bekle(self.aralik_s)
            if time.monotonic() - self._son_ham_t >= HAM_KAYIT_ARALIGI_S:
                self._son_ham_t = time.monotonic()
                self.d.ham_kaydet(10.0, faz)
            olcumler, self._biriken = self._biriken, []
            if not olcumler:
                continue
            if not self.akimli:
                simdi = time.monotonic()
                self._ortam_gecmisi += [(simdi, o.harmonikler[0], o.harmonikler[1]) for o in olcumler]
            k = kaydi_hesapla(olcumler, self.arka if self.akimli else None, self.p.r_ref_m)
            with self._akim_kilidi:
                akim = list(self._akim)
            k.update(zaman=datetime.now().isoformat(timespec="seconds"),
                     gecen_dk=(time.monotonic() - self.t0) / 60, faz=faz,
                     **{f"I{i + 1}_A": akim[i] for i in range(4)})
            satirlar.append(k)
            with open(self.csv_yolu, "a", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow([k[s] if isinstance(k[s], str) else f"{k[s]:.6g}" for s in SUTUNLAR])
        if not self.akimli and self._ortam_gecmisi:
            son = self._ortam_gecmisi[-1][0]
            secim = [(c1, c2) for t, c1, c2 in self._ortam_gecmisi if son - t <= ARKA_PLAN_SON_S]
            self.arka = (complex(np.mean([c[0] for c in secim])), complex(np.mean([c[1] for c in secim])))
        self.bildir(f"■ <b>{faz}</b> bitti: {faz_ozeti(satirlar)}")

    def merkezle(self) -> np.ndarray:
        from merkezleme.harmonikler import HarmonikKonvansiyonu
        from merkezleme.is_akisi import Faz, IsAkisi, otomatik_yurut
        from merkezleme.kayit import Calistirma
        from merkezleme.modlar import ModBazi
        from merkezleme.olcum_kaynagi import DosyaGirisi

        self.bildir(f"▶ <b>merkezleme</b> başladı ({self.kfg.miknatis.nominal_akim_A:g} A, "
                    f"{self.kfg.duzeltme.merkez_toleransi_um:g} µm)")
        self.akimli = False
        konv = HarmonikKonvansiyonu(self.kfg.harmonikler)
        kaynak = DosyaGirisi(self.kfg.dosya_girisi, konv, bekle=self.bekle)
        akis = IsAkisi(self.kfg, self.grup, kaynak, Calistirma(self.kfg), konv,
                       ModBazi(self.kfg.modlar, self.kfg.miknatis))
        Path(self.kfg.dosya_girisi.kilit_dosyasi).unlink(missing_ok=True)
        self.d.otomatik_yaz_ayarla(True)
        try:
            akis.basla()
            otomatik_yurut(akis, kaynak)
        finally:
            self.d.otomatik_yaz_ayarla(False)
            akis.ozeti_yaz()
        if akis.faz is not Faz.TAMAMLANDI:
            raise OlcumHatasi(f"merkezleme bitmedi ({akis.faz.value}): {akis.durdurma_nedeni}")
        akimlar = np.array(akis.kaynaklar.ayar_akimlari_A, dtype=float)
        y = akis.son_y
        self.bildir(f"■ <b>merkezleme</b> bitti, {akis.iterasyon} iterasyon\n"
                    f"Akımlar: <b>{' / '.join(f'{a:.4f}' for a in akimlar)}</b> A\n"
                    f"<i>{y}</i>")
        self.hedef_akimlar = akimlar
        self._ayar_degisti()  # kalibrasyon adımlarından kalan okumalar eski
        self.akimli = True
        return akimlar

    def calistir(self, akimlar: np.ndarray | None = None) -> None:
        """Fazları sırayla yürütür. `akimlar` verilirse merkezleme atlanır ve bu
        akımlar kullanılır (kesilen bir ölçümü bobin durmadan sürdürmek için).
        Süresi 0 olan fazlar atlanır."""
        self._akim_isi = threading.Thread(target=self._akimlari_oku, daemon=True)
        self._akim_isi.start()
        s = dict(zip(FAZLAR, self.sureler_s))

        def akimlari_ac(hedef: np.ndarray) -> None:
            if not self.grup.baslatildi:  # merkezleme atlanınca kaynakları akış başlatmaz
                self.grup.baslat()
            self._rampala(hedef)
            self.bekle(10.0)  # rampa sonrası ilk ölçümler otursun
            self._biriken = []

        if s["ortam1"] > 0:
            self.kayit_fazi("ortam1", s["ortam1"])
        if akimlar is None:
            akimlar = self.merkezle()
        else:
            akimlar = np.asarray(akimlar, dtype=float)
            self.bildir(f"▶ merkezleme atlandı; akımlar <b>{' / '.join(f'{a:.4f}' for a in akimlar)}</b> A")
            akimlari_ac(akimlar)
        if s["akimli1"] > 0:
            self.kayit_fazi("akimli1", s["akimli1"])
        if s["ortam2"] > 0:
            self._rampala(np.zeros(4))
            self.kayit_fazi("ortam2", s["ortam2"])
        if s["akimli2"] > 0:
            if not self.akimli:
                akimlari_ac(akimlar)
            self.kayit_fazi("akimli2", s["akimli2"])
        if s["ortam3"] > 0:
            self._rampala(np.zeros(4))
            self.kayit_fazi("ortam3", s["ortam3"])

    def durdur(self) -> None:
        self._akim_dur.set()
        if self._akim_isi is not None:
            self._akim_isi.join(timeout=10)


def telegram(metin: str) -> None:
    print(f"{datetime.now():%H:%M:%S}  {metin}", flush=True)
    if TELEGRAM.exists():
        try:
            subprocess.run([str(TELEGRAM), "-h", metin], timeout=30, check=False,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:  # noqa: BLE001 - bildirim ölçümü durdurmasın
            pass


def main(argv: list[str] | None = None) -> int:
    a = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    a.add_argument("--sureler", type=float, nargs=5, default=list(SURELER_DK),
                   metavar=("ORTAM1", "AKIMLI1", "ORTAM2", "AKIMLI2", "ORTAM3"), help="dakika")
    a.add_argument("--kisa", action="store_true", help="her faz 2 dk (betiği denemek için)")
    a.add_argument("--aralik", type=float, default=10.0, help="kayıt aralığı (s)")
    a.add_argument("--nominal", type=float, default=9.5)
    a.add_argument("--tolerans", type=float, default=10.0, help="merkez toleransı (µm)")
    a.add_argument("--hiz", type=float, default=8.0)
    a.add_argument("--akimlar", type=float, nargs=4, default=None, metavar=("I1", "I2", "I3", "I4"),
                   help="merkezlemeyi atla, bu akımları kullan (kesilen ölçümü sürdürmek için)")
    a.add_argument("--yapilandirma", default=str(KOK / "yapilandirma.yaml"))
    a.add_argument("--parametreler", default=None)
    g = a.parse_args(argv)
    if argv is None:
        from uyku import uykuyu_engelle

        uykuyu_engelle("Uzun kararlılık ölçümü sürüyor")
    # SIGTERM (systemctl stop, kill, zaman sınırı) de Ctrl+C gibi güvenli kapanışa gitsin:
    # 12 Kasım 14:00'te süreç dışarıdan öldürüldü, kapanış kodu çalışmadı (motor dönmeye devam etti).
    import signal

    def _sigterm(_imza, _cerceve):
        raise KeyboardInterrupt("SIGTERM")

    signal.signal(signal.SIGTERM, _sigterm)
    if not 0 < g.hiz <= 8.0:
        print("hız en fazla 8 Hz (11 Kasım: 10 Hz'de ADC takıldı)", file=sys.stderr)
        return 2
    sureler_s = [120.0] * 5 if g.kisa else [m * 60 for m in g.sureler]
    if g.akimlar is not None and not all(0 < a <= 10.0 for a in g.akimlar):
        print("akımlar 0 ile 10 A arasında olmalı", file=sys.stderr)
        return 2

    from merkezleme.birlesik import ayarlari_uygula
    from merkezleme.guc_kaynagi import KaynakGrubu, KomutGunlugu
    from merkezleme.yapilandirma import yapilandirma_yukle
    from mgf.connection import MgfConnection
    from mgf.data_engine import DataEngine

    os.chdir(KOK)  # göreli yollar (calistirmalar/, veri_kilidi/) depo köküne göre
    kfg = ayarlari_uygula(yapilandirma_yukle(g.yapilandirma), g.nominal, g.tolerans)
    p = parametreleri_yukle(g.parametreler)
    dongu = OlcumDongusu(p, MgfConnection(p.ip, p.port), DataEngine(),
                         gunluk=lambda m: print(f"{datetime.now():%H:%M:%S}  {m}", flush=True))
    if not dongu.baglan():
        telegram("🔴 <b>Uzun ölçüm başlamadı</b>: Pico'ya bağlanılamadı")
        return 1
    scpi = KomutGunlugu()
    olcum: UzunOlcum | None = None
    grup = None
    kod = 0
    try:
        # Dönen bobin önce dönsün (sağlık denetimi bağlantıyı ve ADC'yi izler)
        dongu.otomatik_yaz_ayarla(False)
        dongu.hiz_ayarla(g.hiz)
        dongu.baslat()
        bitis = time.monotonic() + 60
        while dongu.durum is not Durum.DONUYOR:
            dongu.tick()
            time.sleep(0.02)
            if time.monotonic() > bitis or dongu.durum is Durum.HATA:
                raise OlcumHatasi(f"motor {g.hiz} Hz'e oturmadı ({dongu.durum.value})")
        grup = KaynakGrubu.olustur(kfg.guc_kaynaklari, kfg.guvenlik, canli=True, gunluk=scpi)
        olcum = UzunOlcum(p, kfg, dongu, grup, sureler_s, g.aralik, telegram)
        grup.bekle = olcum.bekle  # rampa beklerken dönen bobin döngüsü işlesin, sağlık denetlensin
        toplam = sum(sureler_s) / 60
        telegram(f"🟢 <b>Uzun kararlılık ölçümü başladı</b>\n\n~{toplam + 10:.0f} dk; "
                 f"kayıt: <code>{olcum.csv_yolu.relative_to(KOK)}</code>")
        olcum.calistir(None if g.akimlar is None else np.array(g.akimlar))
        telegram("🟢 <b>Uzun ölçüm bitti</b>\n\n" + "\n".join(
            f"<b>{f}</b>: {faz_ozeti(olcum.faz_satirlari.get(f, []))}" for f in FAZLAR))
    except (Exception, KeyboardInterrupt) as hata:
        kod = 1
        telegram(f"🔴 <b>Uzun ölçüm durdu</b>\n\n{type(hata).__name__}: {hata}\n\n"
                 "<i>Akımlar rampayla sıfırlanıyor, motor durduruluyor.</i>")
    finally:
        if olcum is not None:
            olcum.durdur()
        if grup is not None:
            try:
                grup.guvenli_kapat()
            except Exception as hata:  # noqa: BLE001
                telegram(f"🔴 <b>Güvenli kapatma başarısız</b>: {hata!r}\nGüç kaynaklarını elle sıfırlayın!")
                try:
                    grup.acil_sifirla()
                except Exception:  # noqa: BLE001
                    pass
        try:
            dongu.durdur()
            bitis = time.monotonic() + 10
            while dongu.donuyor and time.monotonic() < bitis:
                dongu.tick()
                time.sleep(0.02)
            dongu.kes()
        except Exception:  # noqa: BLE001
            pass
        try:
            (dongu.oturum.klasor() / "scpi_gunlugu.txt").write_text("\n".join(scpi.satirlar()) + "\n",
                                                                    encoding="utf-8")
        except OSError:
            pass
    return kod


if __name__ == "__main__":
    raise SystemExit(main())
