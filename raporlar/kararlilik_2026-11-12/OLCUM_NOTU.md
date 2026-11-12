# Uzun kararlılık ölçümü, 12 Kasım 2026

Plan (`donen_bobin/host/uzun_kararlilik.py`): ortam1 → merkezleme (9.5 A, 10 µm) → akimli1 60 dk →
ortam2 60 dk → akimli2 120 dk (aynı akımlar) → ortam3 20 dk. Dönen bobin 8 Hz, hiç durmaz.

## Bölüm 1 (sağlam): 10:30:42 – 11:00:48, yalnız ortam1

- Kaynak oturum: `kayitlar/2026-11-12_103042/` (tam kayıtlar orada; bu klasörde kopyaları).
- `bolum1/ortam1.csv`: 180 kayıt (10 s), akımlar sıfır. B1 = +3.03 ± 0.23 µT, A1 = −33.24 ± 0.19 µT;
  sürüklenme B1 +0.69, A1 +0.21 µT/saat.
- `bolum1/ham_*_ortam1.csv`: 10 s'lik ham veriler (10:30:54, 10:45:57).

## Kesinti: 11:01:06

Merkezleme başlarken güç kaynağı yanıtları kaydı (`*IDN?` -> '0', `SYST:ERR?` -> '6.74978'); betik bunu
cihaz hatası sayıp güvenle durdu (akımlar rampayla sıfır, çıkışlar kapalı, motor durdu). Hiçbir sorgu
2 s'yi geçmemişti; kayma, ikinci bir iş parçacığı farklı kaynaklara eş zamanlı sorgu göndermeye
başlayınca başladı. Düzeltme: bütün kaynaklar için ortak iletişim kilidi (commit 498d3f1), tampon
boşaltma ve yanıt biçimi denetimi (6cd64f1). Merkezleme bu bölümde tamamlanmadı; bölüm 1'de
akımlı veri yok.

## Bölüm 2: kaldığı yerden

Motor durup yeniden başladığı için başa 5 dk akımsız faz (ortam1, net merkez için arka plan ve enkoder
referansı kontrolü: B1 ≈ +3.0, A1 ≈ −33.2 µT beklenir), ardından merkezleme ve planın kalanı.
