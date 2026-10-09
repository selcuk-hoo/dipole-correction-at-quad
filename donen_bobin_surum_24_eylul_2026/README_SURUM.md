# MGF — 24 Eylül 2026 kaynak kopyası

Bu klasör, dönen bobin sisteminin bilgisayar uygulaması ve RP2350 firmware kaynaklarını içerir.

- `host/`: PySide6 masaüstü arayüzü, bağlantı/protokol, örnek işleme ve manyetik analiz.
- `src/`, `include/`: rotor/stator firmware ve ortak protokol.
- `lib/`: ADS1263, W5500 ioLibrary ve PIO programları.
- `CMakeLists.txt`: `rotor` ve `stator` firmware hedefleri. Raspberry Pi Pico SDK 2.2.0 ve uygun ARM toolchain sistemde ayrıca kurulu olmalıdır.

Masaüstü uygulamasını `host/` çalışma dizininden `python radarMGF.py` komutuyla başlatın; Python bağımlılıkları `host/requirements.txt` içindedir. Firmware derlemesi Pico SDK ortamı hazırlandıktan sonra bu klasörde CMake ile yapılır.

## Merkezleme ölçüm penceresi

Kuadrupol merkezleme (depo kökündeki `merkezleme` programı) için büyük arayüze gerek yoktur; tek pencerelik minimal bir program vardır:

```bash
cd host
python merkezleme_olcer.py        # parametreler: ../merkezleme_olcer.yaml
```

Pencere cihaza bağlanır, ADC'yi ayarlar (32×, 7200 SPS, Sinc4, Voltage), seçilen düz bobini (varsayılan AIN0-AIN1) okur ve motoru döndürür (en fazla 23 Hz). "Merkezleme'ye yaz" açıkken kendi kendine döner: `veri_kilidi/.kilit` yoksa (merkezleme yeni akımları ayarlamış demektir) kilidin silinmesinden SONRA gelen veriden ölçer ve kilidi yazar. Aynı anda depo kökünde `python -m merkezleme --dosyadan` (yarı otomatik) ya da `--otomatik --dosyadan --canli` (tam otomatik) çalıştırılır. Durdur, pencereyi kapatma ve her hata durumunda motor önce durdurulur, sonra servo kapatılır. Tema (açık/koyu) pencereden değiştirilebilir; **Yardım** düğmesi (F1) kısa bir kullanım kılavuzu açar.

**Ölçüm süresi:** her ölçümde kullanılan veri süresi pencereden ayarlanır (varsayılan 2 s, en fazla cihaz arabelleğinin tuttuğu ~125 s). Rastgele gürültü 1/√süre ile azalır (testle doğrulandı: 8 s, 2 s'ye göre ~2 kat az saçılım). Dönmeyle eşzamanlı hatalar (bobin geometrisi, enkoder doğrusalsızlığı, mekanik titreşim) ve yavaş sürüklenme azalmaz; merkezleme'nin her adımı da o kadar uzar.

**Merkezleme olmadan ölçüm:** "Merkezleme'ye yaz" kapalıyken program her ölçüm süresinde bir sürekli ölçüm alır (birbiriyle örtüşmeyen pencereler); "Tek ölçüm" her zaman kullanılabilir. "CSV'ye kaydet" açıkken her ölçüm `olcumler/olcum_<tarih>.csv` dosyasına (oturum başına bir dosya) yazılır: hız, sinyal tepesi, faz ofseti, G, x_c, y_c ve n = 1..6 için b_n, a_n (Tesla).

**Çok kutuplar sekmesi:** n = 1..6, logaritmik eksende. "Göster": normal ve skew yan yana (çubuk yüksekliği mutlak değer; içi boş çubuk negatif; etikette işaretli değer) ya da genlik |C_n|. "Ölçek": gerçek alan (Tesla, r_ref'te), n = 1'e göre ya da n = 2'ye göre (o mertebenin genliği 1). Çubuklar son 20 ölçümün karmaşık ortalamasıdır (faz kararlı olduğundan gürültü √N ile azalır); hata çubuğu tek ölçümlerin saçılımıdır, çubuktan uzunsa o terim gürültünün altındadır. Ortalama kanal, hız, ölçüm süresi ya da faz ofseti değişince (ve "Ortalamayı sıfırla" ile) sıfırlanır.

**Bobin akısı sekmesi:** son ölçüm penceresinde bobinden geçen akı (gerilimin zaman integrali), bütün turlar enkoder açısına göre üst üste; üzerindeki çizgi uydurulan harmoniklerin toplamıdır. Noktalar çizgiye oturuyorsa ölçüm sağlıklıdır; turlar arasında kayma ya da sıçrama açı, örnek kaybı ya da doyma sorununu gösterir.

**Bobin duyarlılığı:** bobinin n. mertebeye duyarlılığı n·K_n = −2i·R^n·sin(nα)/r_ref^(n−1) ile orantılıdır; burada R = √(20² + 10²) = 22.4 mm iletkenlerin eksene uzaklığı, α = 26.6° iletkenlerin bobin ortasından açısal yarı aralığıdır. sin(nα) yüzünden duyarlılık n = 3 civarında en yüksek, n = 6'da düşük, n ≈ 7'de neredeyse sıfırdır. Gerilimdeki gürültünün C_n'ye yansıması, n = 1'e göre: n = 2..5'te 0.6–0.95 kat, n = 6'da ~2.2 kat (n = 7 ölçülmez, ~8 kat olurdu).

**Referans mıknatısla sıfırla:** enkoderin sıfırı her açılışta değişir. Referans dipol mıknatısı takılıyken bu düğmeye basılınca faz ofseti, o alan saf normal ve pozitif (b0 > 0, a0 = 0) görünecek şekilde ayarlanır. Bu yalnızca raporlanan x/y yönlerini belirler; düzeltmenin yakınsamasını etkilemez. Faz ofseti **her bobin için ayrıdır** (dik iki bobin dönen çerçevede 90° farklı durur); bobin değiştirince o bobin için de referans alınmalıdır, alınmadıysa pencere ve günlük uyarır.

**Gecikme ölç (iki yön):** ADC örneği (Sinc4 filtresi) ile enkoder açısı (stator ~1 ms'de bir okur, RS485'le rotora gönderir) arasında sabit bir zaman gecikmesi vardır. Sabit hızda bu yalnızca bir açı ofsetidir (referans giderir); ama tur içi hız dalgalanmasında güçlü n=2'yi n=1/n=3'e karıştırır (simülasyonda 0,5° dalgada ~5 µm, 2° dalgada ~19 µm sahte merkez kayması). Düğme bir pencereyi bu yönde, motoru ters çevirip bir pencereyi öbür yönde alır; gecikme iki yön arasındaki faz farkından bulunur (yöne bağlı mil burulması/boşluk da buna katılır). Ölçülen değer `olcum.gecikme_ms`'e yazılmalıdır; faz ofseti yeni gecikmeye kendiliğinden taşınır. Bilinen gecikmeyle tek yönlü ölçüm, simülasyonda 2° dalgada bile 0,1 µm içindedir.

**Sağlık kontrolü ve çerçeve kilidi:** iki ölçüt var: akı uydurmasının artığı (`olcum.artik_esigi`, varsayılan 5e-3) ve okuma saati sıçraması (`olcum.sicrama_esigi`, varsayılan 0.6 örnek). İkincisi örnek kaybını doğrudan yakalar: enkoder okumaları stator saatine bağlı düzenli aralıklarla gelir; bir ADC örneği kaybolursa sonraki bütün okumalar bir örnek kayar (sağlıklı veride ~0.2, tek kayıpta ~1; 7200 SPS'te 10 µs okuma titreşiminde bile sağlıklı değer ≤0.33). Biri aşılırsa ölçüm merkezleme'ye yazılmaz; üst üste 3 kez olursa motor durdurulur. Stator'un attığı bozuk ADC örnekleri (durum paketindeki RS485 sayacı) günlüğe yazılır. "Merkezleme'ye yaz" açıkken bobin, hız, referans ve gecikme değiştirilemez.

### Fizik

`host/mgf/merkezleme_koprusu.py` bobin gerilimini zamana göre integre ederek akıyı bulur (Φ = −∫V dt, yamuk kuralı; yamuk kuralının harmonik başına küçük kazanç hatası düzeltilir) ve akıyı enkoder açısına göre en küçük kareler ile harmoniklere ayırır (sabit + zaman polinomu + 1..15. harmonik; 1..6 raporlanır). Hız hiç kullanılmaz: dönüş yönü ve hız dalgalanması sonucu etkilemez; tek koşul ADC örneklerinin zamanda düzgün ve kayıpsız olmasıdır. Enkoder açısındaki ~1 ms'lik merdiven, taze okumaların düzenli okuma saatine oturtulması ve kübik enterpolasyonla giderilir. Bobin geometrisinden (5 sarım, 100×20 mm, eksene 20 mm, teğet) her mertebenin duyarlılığını hesaplayarak C₁..C₆'yı Tesla cinsinden, merkezleme'nin konvansiyonunda (r_ref = 25 mm) verir. Bu sayede merkez `z_c = −r_ref·C₁/C₂` gerçek uzunluk biriminde çıkar; ADC/elektronik kazanç hatası iki harmoniği aynı oranda etkilediğinden merkezi değiştirmez. n=1 sonucu `magnetic_analysis.py`'deki Bx/By formülüyle birebir aynıdır (testle doğrulanmıştır).

Bütün sayılar `merkezleme_olcer.yaml`'dadır. Açılışta `r_ref` ve birimin merkezleme yapılandırmasıyla tutarlılığı kontrol edilir.

### Makro komutu

Büyük arayüzün makro sisteminde `MERKEZLEME_OLCUM` komutu aynı hesabı tek seferlik yapar ("Merkezleme Kuadrupol Olcumu" hazır makrosu). Sürekli otomatik ölçüm için minimal pencere tercih edilmelidir.

Hangi sistematik hatanın nasıl ve ne kadar düzeltildiği: [`SISTEMATIK_HATALAR_RAPORU.md`](SISTEMATIK_HATALAR_RAPORU.md).

### Lab doğrulama planı

1. **Tekrarlanabilirlik:** sürekli ölçümde x_c, y_c saçılımı; ölçüm süresini 2 → 8 s yapınca ~2 kat azalmalı.
2. **Gecikme:** "Gecikme ölç" iki-üç kez; değerler birbirine µs düzeyinde yakın olmalı (beklenen ~0,1–0,3 ms). `olcum.gecikme_ms`'e yazın.
3. **Yön karşılaştırması:** gecikme ayarlıyken aynı alanı +23 ve −23 Hz'de ölçün (Gecikme ölç sonrası motor ters yönde kalır); C₁..C₆ yön içinde ve yönler arasında aynı olmalı.
4. **İşaret/el kuralı:** mıknatısı (ya da bobini) bilinen bir miktar +x yönünde kaydırın; x_c beklenen işaret ve büyüklükte değişmeli (y için de). Yanlışsa kanal kutupları ya da bobin tipi ters demektir.
5. **Mutlak ölçek:** bilinen gradyen |C₂|/r_ref ile karşılaştırılır (K₂'yi, dolayısıyla bobin alanını/sarım sayısını doğrular). Merkezin ölçeği K₂/K₁'ye bağlıdır (eksene uzaklık); bunu 4. maddedeki bilinen kaydırma doğrular.
6. **Referans:** referans sonrası referans mıknatıs b0 > 0, a0 ≈ 0 vermeli; bobin 1 ve bobin 2 (dik) aynı C_n'leri vermeli.
7. **Sağlık ölçütleri:** sağlıklı ölçümlerde pencerede görünen "Artık / saat sıçr." ne düzeyde? Eşikler (5e-3 ve 0.6) gerçek gürültüye göre ayarlanabilir. Reddedilen ölçüm sık geliyorsa günlükte RS485 uyarısı olup olmadığına bakın.

**Bağlantı kopması:** firmware TCP bağlantısı kopunca motoru durdurmaz; motor son hızında dönmeye devam eder. Program yeniden bağlanınca normal durdurmadaki gibi önce hızı sıfırlar, motor durunca (ya da zaman aşımında) servoyu kapatır. Firmware'e bağlantı kopunca motoru rampalı durduran bir bekçi eklenmesi önerilir.

**Gecikme ve referans güvenilirliği:** fazın artıktan tahmin edilen belirsizliği büyükse (gecikmede ±2 µs, referansta ±0,05° üstü; mıknatıs yok, yanlış kanal ya da sinyal çok zayıf) ölçülen değer uygulanmaz, günlüğe nedeni yazılır.

**Bilinen sınırlama (firmware):** örneklerde sıra numarası yok; stator ADC sağlama toplamı tutmayan örnekleri sessizce atıyor (yalnızca durum paketindeki sayaç artıyor) ve PC tarafında kuyruk dolarsa paket düşüyor. Akı integrali kayıpsız örnek varsayar; tek kayıp merkezde birkaç µm hata yapabilir. Okuma saati sıçraması bunu yakalar ve ölçüm reddedilir (onarılmaz). Kesin çözüm firmware'de örnek sayacı (ve tercihen enkoder okumasının zaman damgası).

### Testler

```bash
cd host
QT_QPA_PLATFORM=offscreen python -m pytest tests/ -q
```

Sahte bir cihazla (motor, enkoder, bobin gerilimi) durum makinesi, pencere ve uçtan uca kapalı döngü sınanır: merkezleme'nin kendi akışı kilit dosyası üzerinden bu programla konuşarak ofsetli bir mıknatısı 5 µm'nin altına merkezler.
