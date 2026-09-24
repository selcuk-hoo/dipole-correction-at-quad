# MGF — 24 Eylül 2026 kaynak kopyası

Bu klasör, dönen bobin sisteminin bilgisayar uygulaması ve RP2350 firmware kaynaklarını içerir.

- `host/`: PySide6 masaüstü arayüzü, bağlantı/protokol, örnek işleme ve manyetik analiz.
- `src/`, `include/`: rotor/stator firmware ve ortak protokol.
- `lib/`: ADS1263, W5500 ioLibrary ve PIO programları.
- `CMakeLists.txt`: `rotor` ve `stator` firmware hedefleri. Raspberry Pi Pico SDK 2.2.0 ve uygun ARM toolchain sistemde ayrıca kurulu olmalıdır.

Masaüstü uygulamasını `host/` çalışma dizininden `python radarMGF.py` komutuyla başlatın; Python bağımlılıkları `host/requirements.txt` içindedir. Firmware derlemesi Pico SDK ortamı hazırlandıktan sonra bu klasörde CMake ile yapılır.

## Merkezleme köprüsü

`host/mgf/merkezleme_koprusu.py`, `../merkezleme` (kuadrupol elektriksel merkezleme) programıyla dosya/kilit üzerinden otomatik ölçüm alışverişi sağlar. "Regular" (düz sargı) bobin kanalından tek bir taramada n=1 (dipol) ve n=2 (kuadrupol) harmonikleri hesaplanır ve `../../veri_kilidi/.kilit` dosyasına yazılır - protokol ve format `merkezleme/olcum_kaynagi.py:DosyaGirisi` docstring'inde tanımlıdır. Makro sisteminden `MERKEZLEME_OLCUM` komutuyla tetiklenir ("Merkezleme Kuadrupol Olcumu" hazır makrosuna bakın); bobin geometrisi ve n=2 duyarlılık düzeltmesi `settings.json`'da (`coil_turns`, `coil_length_mm`, `coil_width_mm`, `merkezleme_duyarlilik_n2`) saklanır.
