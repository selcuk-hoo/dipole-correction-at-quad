# Bekleyen güncelleme: enkoder paketine CRC

**Durum (6 Kasım 2026):** hazır ama uygulanmadı. Kod 4 Kasım'da yazılıp test edildi (commit `6937741`). Donanıma henüz yüklenemediği için 6 Kasım'da geri alındı. Firmware de bilgisayardaki program da şu an eski hâlinde. Bu klasörde güncelleme tek bir yama olarak duruyor ve istendiğinde iki tarafa birlikte uygulanıyor.

## Ne değişiyor

Stator, enkoder açısını RS485 üzerinden rotora gönderiyor. Bu pakette sağlama yoktu. Yüksek hızda hattaki bit hataları yanlış açı olarak kabul ediliyordu (23 Hz'de güncellemelerin yaklaşık %9'u). Ayrıntılar: `OLCUM_RAPORU_2026-11-04.md`, Bölüm 6.

- **Pico (rotor + stator):** enkoder paketinin sonuna CRC-8 eklenir (9 → 10 bayt). Rotor, CRC'si tutmayan paketi atar ve sayar. Bu sayaç watchdog'un hata sayacından ayrı tutulur, yani hat gürültüsü rotoru yeniden başlatmaz. Sayaç rotorun durum paketiyle (14 → 16 bayt) statora gider. Stator onu PC'ye `TcpStatus.rotor_error_count` alanında iletir. Eski firmware bu alana hep 0 yazıyordu.
- **Bilgisayar (ölçüm programı):** sayaç artınca Günlük'e "rotor N bozuk enkoder güncellemesi attı" yazılır. RS485 ve CRC sayaçları ham kayıtların başlığına eklenir.
- **Testler:** `test_firmware/enkoder_crc_testi.cpp` rotorun ve statorun paket kodunu bilgisayarda g++ ile derler. Paketin bütün 1, 2 ve 3 bitlik hatalarını dener ve hiçbirinde yanlış açının kabul edilmediğini doğrular. Pico gerekmez. `host/tests/test_firmware_crc.py` bunu pytest içinden çalıştırır.

**Rotor ve stator aynı sürümde olmalı.** Paket boyları değiştiği için yeni rotor eski statorla (ya da eski rotor yeni statorla) doğru çalışmaz. Bilgisayar tarafı ise iki firmware ile de çalışır, çünkü eski firmware sayacı yalnızca 0 gönderir.

## Dosyalar

| Dosya | Ne yapar |
|---|---|
| `enkoder_crc.patch` | Güncellemenin kendisi (commit `6937741`, `git format-patch` çıktısı) |
| `uygula.sh` | Yamayı koda uygular (firmware + bilgisayar) ve testleri çalıştırır |
| `pico_yukle.sh` | Rotor ve stator firmware'ini derler ve sırayla Pico'lara yükler |
| `geri_al.sh` | Yamayı koddan geri alır |

## Kullanım

```bash
cd donen_bobin/bekleyen_guncellemeler/enkoder_crc
./uygula.sh                 # 1. kodu güncelle, testleri çalıştır (58 test geçmeli)
git add donen_bobin && git commit -m "Enkoder CRC guncellemesi uygulandi"
./pico_yukle.sh             # 2. derle, önce statoru sonra rotoru yükle
```

`pico_yukle.sh` için Pico SDK 2.2.0 gerekiyor: ya `PICO_SDK_PATH` ayarlı olmalı ya da Pico VS Code eklentisinin `~/.pico-sdk` kurulumu bulunmalı. Bu bilgisayarda (6 Kasım itibarıyla) ikisi de yok. Bu yüzden derleme ve yükleme, SDK'nın kurulu olduğu bilgisayarda yapılmalı. Betik, VS Code'un `build/` klasörüne dokunmamak için `donen_bobin/build_pico_yukle/` klasöründe derler. Yükleme `picotool` ile yapılır. picotool yoksa ya da Pico'yu bulamazsa betik BOOTSEL sürücüsünün (RP2350) bağlanmasını bekler ve `.uf2` dosyasını oraya kopyalar.

Kod bu tarihten sonra değişirse `uygula.sh` önce üç yollu birleştirmeyi dener. Çakışma çıkarsa durur ve hangi dosyalarda olduğunu `git status` gösterir.

## Yükledikten sonra

1. Ölçüm programını açın, rotorun çevrimiçi olduğunu ve örnek akışının normal geldiğini görün. Akış gelmiyorsa en olası neden, iki Pico'dan birinin eski sürümde kalmasıdır.
2. 8 Hz'de bir ölçüm alın. Günlük'te CRC uyarısı çıkmamalı.
3. 23 Hz'de ham kayıt alın. Tutarsız açı (geri dönen sıçramalar) sıfıra inmeli. Eksik okumalar sürebilir, çünkü atılan paketler kayıp sayılır. Günlük'teki CRC sayacı, hat hatalarının hıza göre nasıl arttığını doğrudan gösterir. Bu, rapordaki 15–17 Hz eşiğini ölçmenin yolu.

Uyguladıktan sonra bu klasör silinebilir ya da `eski-surumler/` altına taşınabilir.
