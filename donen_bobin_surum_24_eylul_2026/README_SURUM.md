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

Pencere cihaza bağlanır, ADC'yi ayarlar (32×, 7200 SPS, Sinc4, Voltage), seçilen düz bobini (varsayılan AIN0-AIN1) okur ve motoru döndürür (en fazla 23 Hz). "Merkezleme'ye yaz" açıkken kendi kendine döner: `veri_kilidi/.kilit` yoksa (merkezleme yeni akımları ayarlamış demektir) kilidin silinmesinden SONRA gelen 2 s'lik veriden ölçer ve kilidi yazar. Aynı anda depo kökünde `python -m merkezleme --dosyadan` (yarı otomatik) ya da `--otomatik --dosyadan --canli` (tam otomatik) çalıştırılır. Durdur, pencereyi kapatma ve her hata durumunda motor önce durdurulur, sonra servo kapatılır. Tema (açık/koyu) pencereden değiştirilebilir.

**Merkezleme olmadan ölçüm:** "Merkezleme'ye yaz" kapalıyken program her 2 s'de bir sürekli ölçüm alır (birbiriyle örtüşmeyen pencereler); "Tek ölçüm" her zaman kullanılabilir. "CSV'ye kaydet" açıkken her ölçüm `olcumler/olcum_<tarih>.csv` dosyasına (oturum başına bir dosya) yazılır: hız, sinyal tepesi, faz ofseti, G, x_c, y_c ve n = 1..6 için b_n, a_n (Tesla).

**Grafikler:** "Çok kutuplar" sekmesi n = 1..6 için b_n (normal) ve a_n (skew) değerlerini ana alana göre birim (10⁻⁴·|C₂|, r_ref'te) cinsinden, son 20 ölçümün ortalaması ± σ olarak gösterir; n = 2 ana alan olduğu için çizilmez. Ortalama kanal, hız ya da faz ofseti değişince (ve "Ortalamayı sıfırla" ile) sıfırlanır. "Ham sinyal" sekmesi son pencerenin bobin gerilimini açıya göre, uydurulan eğriyle birlikte gösterir; ikisinin örtüşmesi ölçümün sağlıklı olduğunu gösterir. Bobinin n. mertebeye duyarlılığı n·K_n = −2i·R^n·sin(nα)/r_ref^(n−1) ile orantılıdır; burada R = √(20² + 10²) = 22.4 mm iletkenlerin eksene uzaklığı, α = 26.6° iletkenlerin bobin ortasından açısal yarı aralığıdır. sin(nα) yüzünden duyarlılık n = 3 civarında en yüksek, n = 6'da düşük, n ≈ 7'de neredeyse sıfırdır. Gerilimdeki gürültünün C_n'ye yansıması, n = 1'e göre: n = 2..5'te 0.6–0.95 kat, n = 6'da ~2.2 kat (n = 7 ölçülmez, ~8 kat olurdu).

**Referans mıknatısla sıfırla:** enkoderin sıfırı her açılışta değişir. Referans dipol mıknatısı takılıyken bu düğmeye basılınca faz ofseti, o alan saf normal ve pozitif (b0 > 0, a0 = 0) görünecek şekilde ayarlanır. Bu yalnızca raporlanan x/y yönlerini belirler; düzeltmenin yakınsamasını etkilemez.

### Fizik

`host/mgf/merkezleme_koprusu.py` bobin gerilimini enkoder açısına göre en küçük kareler ile harmoniklere ayırır (sabit + sürüklenme + 1..6. harmonik; güçlü n=2'nin zayıf n=1'e sızmaması için) ve bobin geometrisinden (5 sarım, 100×20 mm, eksene 20 mm, teğet) her mertebenin duyarlılığını hesaplayarak C₁..C₆'yı Tesla cinsinden, merkezleme'nin konvansiyonunda (r_ref = 25 mm) verir. Bu sayede merkez `z_c = −r_ref·C₁/C₂` gerçek uzunluk biriminde çıkar; ADC/elektronik kazanç hatası iki harmoniği aynı oranda etkilediğinden merkezi değiştirmez. n=1 sonucu `magnetic_analysis.py`'deki Bx/By formülüyle birebir aynıdır (testle doğrulanmıştır).

Bütün sayılar `merkezleme_olcer.yaml`'dadır. Açılışta `r_ref` ve birimin merkezleme yapılandırmasıyla tutarlılığı kontrol edilir.

### Makro komutu

Büyük arayüzün makro sisteminde `MERKEZLEME_OLCUM` komutu aynı hesabı tek seferlik yapar ("Merkezleme Kuadrupol Olcumu" hazır makrosu). Sürekli otomatik ölçüm için minimal pencere tercih edilmelidir.

### Testler

```bash
cd host
QT_QPA_PLATFORM=offscreen python -m pytest tests/ -q
```

Sahte bir cihazla (motor, enkoder, bobin gerilimi) durum makinesi, pencere ve uçtan uca kapalı döngü sınanır: merkezleme'nin kendi akışı kilit dosyası üzerinden bu programla konuşarak ofsetli bir mıknatısı 5 µm'nin altına merkezler.
