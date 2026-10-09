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

**Referans mıknatısla sıfırla:** enkoderin sıfırı her açılışta değişir. Referans dipol mıknatısı takılıyken bu düğmeye basılınca faz ofseti, o alan saf normal ve pozitif (b0 > 0, a0 = 0) görünecek şekilde ayarlanır. Bu yalnızca raporlanan x/y yönlerini belirler; düzeltmenin yakınsamasını etkilemez.

### Fizik

`host/mgf/merkezleme_koprusu.py` bobin gerilimini enkoder açısına göre en küçük kareler ile harmoniklere ayırır (sabit + sürüklenme + 1..6. harmonik; güçlü n=2'nin zayıf n=1'e sızmaması için) ve bobin geometrisinden (5 sarım, 100×20 mm, eksene 20 mm) her mertebenin duyarlılığını hesaplayarak C₁, C₂'yi Tesla cinsinden, merkezleme'nin konvansiyonunda (r_ref = 25 mm) verir. Bu sayede merkez `z_c = −r_ref·C₁/C₂` gerçek uzunluk biriminde çıkar; ADC/elektronik kazanç hatası iki harmoniği aynı oranda etkilediğinden merkezi değiştirmez. n=1 sonucu `magnetic_analysis.py`'deki Bx/By formülüyle birebir aynıdır (testle doğrulanmıştır).

Bütün sayılar `merkezleme_olcer.yaml`'dadır. Açılışta `r_ref` ve birimin merkezleme yapılandırmasıyla tutarlılığı kontrol edilir.

### Makro komutu

Büyük arayüzün makro sisteminde `MERKEZLEME_OLCUM` komutu aynı hesabı tek seferlik yapar ("Merkezleme Kuadrupol Olcumu" hazır makrosu). Sürekli otomatik ölçüm için minimal pencere tercih edilmelidir.

### Testler

```bash
cd host
QT_QPA_PLATFORM=offscreen python -m pytest tests/ -q
```

Sahte bir cihazla (motor, enkoder, bobin gerilimi) durum makinesi, pencere ve uçtan uca kapalı döngü sınanır: merkezleme'nin kendi akışı kilit dosyası üzerinden bu programla konuşarak ofsetli bir mıknatısı 5 µm'nin altına merkezler.
