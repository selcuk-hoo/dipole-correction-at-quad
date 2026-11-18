# Sonradan yapılacaklar

*Son güncelleme: 18 Kasım 2026 (Claude). Her maddede neden ve nereden çıktığı yazılı; yapılınca
silin ya da "yapıldı" diye işaretleyin.*

## Ölçüm ve yöntem

1. **Yerçekimi açı referansı (ivmeölçer).** Ayrıntılı istem: `planlar/yercekimi_referansi_PROMPT.md`.
   İvmeölçer rotor kartına takılınca başlanacak.

2. **Kalibrasyon "şüpheli" denetimlerini kuadrupol çerçevesinde yapmak.** 6 Kasım öğleden sonrasından
   beri yapılan kalibrasyonların çoğu "şüpheli" işaretli. Görülen nedenler ("H modu en çok y_c'yi
   etkiliyor, x_c bekleniyordu", "V modu x_c'yi…", "H modu fiti lineer değil: g (R² = 0.89)") büyük
   olasılıkla iki şeyden geliyor [HİPOTEZ]:
   - Enkoder sıfırı keyfi olduğu için x_c/y_c eksenleri oturumdan oturuma dönüyor; "H → x_c" beklentisi
     bobin çerçevesinde anlamsız. Kuadrupol çerçevesinde (ψ = arg(C₂)/2 kadar döndürülmüş) bütün
     kalibrasyonlarda H y yönünde, V x yönünde çıkıyor (sütun açıları −46°, 43°, 134°, −135°). Bunun
     fiziksel olarak doğru mu, bobin numaralandırması/polarite sorunu mu olduğu da ayrıca netleşmeli.
   - g satırı 18 Kasım'a kadar B₂'den (bobin çerçevesi) hesaplanıyordu; H/V modlarının g eğimi ~0
     olduğu için R² gürültüye ve çerçeveye çok duyarlı.
   Yapılacak: denetimleri (`merkezleme/kalibrasyon.py`, `supheli_nedenleri`) kuadrupol çerçevesinde ve
   anlamlı bir eğim eşiğiyle yapmak; eski kalibrasyonları yeni denetimle yeniden değerlendirmek.

3. **Merkezlemenin son yinelemelerdeki salınımı: nedeni bulundu (18 Kasım).** 17 ve 18 Kasım'da
   merkezleme y'de ±20 µm salınıp 5 µm toleransa ulaşmadan bitti. 18 Kasım tanı ölçümü
   (`merkezleme/tani_testi.py`, `kayitlar/tani_testi_2026-11-18_153117.*`) [ÖLÇÜLDÜ]:
   - aynı akımda tekrar: σ = 4.4 µm (x), 2.6 µm (y); akım değişiminden sonra ek gürültü yok;
   - ±2.9 mA adımlara tepki doğrusal, döngüler arası 1.2 µm tekrarlanabilir, matris öngörüsüyle uyumlu;
   - histerezis (yukarıdan/aşağıdan gelme) ve sıfırdan geçmenin etkisi gürültü düzeyinde;
   - üstüne 10-20 s'lik yavaş bir dalgalanma (~5-10 µm) biniyor.
   Yani düzeltme her yinelemede tek 2 s'lik ölçümün gürültüsünü kovalıyor [YORUM]. Seçenekler: ölçüm
   süresini uzatmak (10 s deneniyor), yinelemede birkaç ölçümün ortalaması, yakınsama ölçütünü
   gürültüye göre koymak (ör. ortalamanın standart hatası), α'yı küçültmek ya da toleransı ~10 µm'ye
   çıkarmak. **Karar (18.11):** ölçüm süresi 10 s, en fazla 8 yineleme. Sonraki merkezlemelerde
   yakınsamayı izleyin; yetmezse ortalama/ölçüt seçeneklerine dönülür.

4. **Skew quad akımlarla düzeltilebilir mi?** ±%0.5'lik kalibrasyon adımlarında hiçbir mod (H, V, Q, M)
   kuadrupol açısını gürültü üstünde değiştirmedi [YORUM]. Kesin cevap için %2'lik adımlarla deneme.

5. **Isınmanın kaynağını ayırmak.** 17 Kasım'da soğuk başlangıçta merkez y'de 22 µm, kuadrupol açısı
   0.55 mrad kaydı; mıknatıs mı güç kaynakları mı ayrılamadı. Öneriler: bobinlere ve ölçüm bobini
   yakınına sıcaklık sensörü; bir bobin devresinde bağımsız akım ölçümü (hassas şönt + multimetre ya
   da DCCT) ile soğuk başlayan bir izleme.

6. **Bobin ve quad çevresinde çelik var mı?** Sigma profil T-somunları ve cıvatalar çoğu zaman çinko
   kaplı çelik. Mıknatısla kontrol edilmeli; varsa hava çekirdekli quad'ın alanını bozar.

7. **Akım okumasının kesilmesi.** 17 Kasım'da izlemede güç kaynağı akımları 13–26 dk sonra okunamadı
   (hep NaN). Artık hata günlüğe yazılıyor; bir sonraki uzun ölçümde nedenine bakılacak.

8. **Motoru durduran `IndexError`.** Boş ölçüm penceresi artık ölçümü atlatıyor ve beklenmeyen
   hataların yeri günlüğe yazılıyor. Bir sonraki olayda günlükteki traceback'e bakılacak; pencerenin
   neden boşaldığı bilinmiyor.

## Arayüz ve kullanım (görsel iyileştirme konuşmasında ele alınacak)

9. **Elle giriş paneli otomatik kullanımda gereksiz.** B/A kutuları, biçim seçici, mutlak gradyen,
   "Kaynaktan doldur" ekranın yarısını kaplıyor. "Elle giriş" kipine saklanabilir; yerine merkezin
   yineleme yineleme küçük bir grafiği (salınım hemen görünür).

10. **İki ayrı "Otomatik" kutusu** (ayar paneli ve çalışma sayfası), yalnızca başlangıçta eşitleniyor.

11. **Sekmeler arası gizli bağımlılık.** Merkezleme, dönen bobin sekmesindeki "Merkezleme'ye yaz"
    kutusuna bağlı; izleme bu kutuyu kendiliğinden kapatıp açıyor. Aynı program içindeki iki sekme hâlâ
    kilit dosyası üzerinden konuşuyor.

12. **İki tema sistemi.** Merkezleme penceresinin tema seçicisi bütün uygulamaya yazıp dönen bobin
    temasını eziyor (`merkezleme_acilinca` yamasıyla geri alınıyor).

13. **Ayar panelindeki kalibrasyon açıklaması uzun** (şüphe nedenlerinin hepsi tek paragrafta).

## Yapı

14. **Aynı iş için üç ayrı yol:** `./merkezle` (birleşik pencere, Kararlılık sekmesi var),
    `./merkezle otomatik` (iki süreç + kilit dosyası, izleme yok), `donen_bobin/host/uzun_kararlilik.py`
    (arayüzsüz). Düzeltmeler birine yapılınca ötekilerde eksik kalıyor (ör. arka plan ortalaması, izleme
    bekçisi, yön doğrulama yalnızca bazı yollarda). Hedef: tek çekirdek (akış + izleme + bekçi), iki ön yüz.
