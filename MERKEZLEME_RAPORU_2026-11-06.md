# İlk gerçek merkezleme ve günün bulguları (6 Kasım 2026)

**Özet.** Kuadrupol, nominal 7 A'da ve yüksek akım asimetrisiyle tam otomatik olarak elektriksel merkezlendi. Merkez, dönen bobinin eksenine göre **7.87 mm'den 14 µm'ye** indi (4 iterasyon, tolerans 75 µm). Bunun önünde iki engel vardı ve ikisi de ölçüm tarafındaydı. Merkezleme 9 Ekim'den beri düz bobin yerine **Morgan bobinini** okuyordu. Bobin geometrisi de yapılandırmada yanlıştı. İkisi düzeltilince kuadrupolün gradyeni beklenen değerde çıktı. Mıknatıs ve güç kaynağı bağlantıları sağlam.

İddialar şöyle işaretlendi: **[ÖLÇÜLDÜ]** doğrudan bugünkü veriden; **[YORUM]** veriden yapılan, başka açıklamalara da açık çıkarım; **[HİPOTEZ]** sınanmamış.

## 1. Sorun: alan bir kuadrupol alanı gibi görünmüyordu

Sabahki ilk denemelerde dört bobin eşit 9.5 A'dayken program yaklaşık 3.5 mT dipol ve yalnızca 0.27 mT kuadrupol gösterdi. Beklenen değer yaklaşık 2.4 mT kuadrupol ve sıfıra yakın dipoldü. Akım sıfırken ölçülen ortam alanı 90–170 µT çıktı. Telefon ise en fazla 80 µT gösteriyordu. Bu ikinci tutarsızlık, sorunun ölçümde olduğunu gösteren ilk güçlü ipucu oldu.

## 2. Neden: yanlış kanal ve yanlış geometri

**Kanal.** Eski arayüzün (radarMGF) kodu ve hazır makroları dört ADC kanalını şöyle adlandırıyor: AIN0–AIN1 Morgan A, AIN2–AIN3 Regular A, AIN4–AIN5 Morgan B, AIN6–AIN7 Regular B. Merkezleme için yazılan ilk makro AIN2–AIN3 okuyordu. 9 Ekim'de bu AIN0–AIN1'e çevrilmişti. Kanal testi (`./merkezle kanal_testi`) dört kanalı akım 0, dört bobin eşit 9.5 A ve yeniden 0 durumlarında ölçtü [ÖLÇÜLDÜ, `kayitlar/2026-11-06_124402`]:

| Kanal | G (T/m) | G / beklenen | Ortam alanı |
|---|---|---|---|
| AIN2–AIN3 (Düz bobin A) | 0.0961 | 1.01 | 33.5 µT |
| AIN6–AIN7 (Düz bobin B) | 0.0910 | 0.96 | 31 µT |
| AIN0–AIN1 (Morgan A) | 0.0079 | 0.08 | 90 µT |
| AIN4–AIN5 (Morgan B) | 0.0088 | 0.09 | 90 µT |

Beklenen G, 9.5 A'da yaklaşık 0.095 T/m (10 A'da kabaca 0.1 T/m). Düz bobinlerin gördüğü ortam alanı telefonla uyumlu. Ortam alanı test boyunca değişmedi: başta 33.5 µT, sonda 33.5 µT.

**Geometri.** Düz bobin 5 sarım ve 135 mm boyunda. Yarıçapı 20 mm olan silindirin yüzeyine 90°'lik bir yay boyunca sarılı, yani iletkenler 20 mm'de ve ±45°'de. Yapılandırmada 100 × 20 mm ve eksene 20 mm yazıyordu. Bu dipolü ~1.9, kuadrupolü ~1.35 kat büyütüyordu. Ayrıca 90°'lik teğet bir bobin oktupole (n = 4) kördür, çünkü duyarlılık sin(4 · 45°) = 0 ile orantılı. Program bu harmoniği artık "ölçülemez" diye raporluyor.

## 3. Merkezleme: 7 A, yüksek asimetri

Mıknatısın merkezi bobin eksenine göre yaklaşık 7.9 mm kaçıktı [ÖLÇÜLDÜ]. Mekanik hizalama şimdilik mümkün olmadığı için nominal akım 7 A'ya indirildi ve asimetri sınırları açıldı. Ayarlar ayrı dosyalarda (`yapilandirma_7A.yaml`, `donen_bobin/merkezleme_olcer_7A.yaml`, değişen satırlar "7A ÇALIŞTIRMASI" ile işaretli):

| Ayar | Varsayılan | Bu çalıştırma | Neden |
|---|---|---|---|
| Nominal akım | 9.5 A | 7.0 A | asimetri için pay |
| Nominale göre en fazla asimetri | %5 | %35 | en fazla 9.45 A < 10 A |
| Adım başına en fazla değişim | %2 | %30 | simülatörde ilk adım %21.6 istedi |
| Kalibrasyon adımı (D) | %0.5 | %2 | 7 A'da sinyal/gürültü |
| Merkez toleransı | 5 µm | 75 µm | tek ölçüm gürültüsü ~20 µm |
| alpha / en fazla iterasyon | 0.9 / 5 | 0.8 / 12 | |
| Dönen bobin ölçüm penceresi | 2 s | 3 s | |
| Okuma saati sıçraması eşiği | 0.6 | 0.85 | bugün sağlıklı veride 0.5–0.73, kayıpta ~1 |

Önce aynı ayarlar simülatörde, 7.6 mm'lik bir ofsetle denendi. İlk denemede adım sınırı (%20) aşıldı ve akış güvenli biçimde durdu. Sınır %30'a çekilince akış 3 iterasyonda 66 µm'ye yakınsadı.

**Gerçek çalıştırma** (`calistirmalar/2026-11-06_125537`, dönen bobin kayıtları `kayitlar/2026-11-06_125536`, 12:55–13:10) [ÖLÇÜLDÜ]:

| Adım | x_c (µm) | y_c (µm) | g |
|---|---|---|---|
| Başlangıç (dört bobin 7 A) | +7867 | +84 | −0.0012 |
| İterasyon 1 | +1593 | +11 | −0.0032 |
| İterasyon 2 | +341 | −6 | −0.0017 |
| İterasyon 3 | +78 | +22 | +0.0004 |
| **İterasyon 4** | **+14** | **−1** | **+0.0002** |

Son akımlar şöyle:

| Bobin | Akım (A) | Nominale göre |
|---|---|---|
| I1 | 8.2564 | +17.9 % |
| I2 | 6.4030 | −8.5 % |
| I3 | 5.9677 | −14.7 % |
| I4 | 7.8211 | +11.7 % |

Ayrıntılar:
- Kalibrasyonun koşul sayısı 17.4 (eşik 20), R_eff = 58 mm.
- Dört bobinin merkez kaydırma etkisi birbirine yakın: bağıl akımın %1'i başına 0.20–0.22 mm.
- Arka plan 14 kez ölçüldü, çalıştırma boyunca 0.8 µT değişti.
- Dönen bobin 29 ölçüm yazdı. Ayrıca 2 ölçüm artık yüzünden reddedildi ve yeniden alındı, hiçbiri akışı durdurmadı.
- Akış güç kaynaklarına 32 352 komut gönderdi, hiçbiri hata vermedi.

Çalıştırmanın sonunda akımlar rampayla sıfıra indirildi, çıkışlar kapatıldı, motor durduruldu. Gözetimsiz çalışıldığı için mıknatıs açık bırakılmadı.

## 4. Sınırlar

- **14 µm tek bir ölçüm.** Tek ölçümün gürültüsü ~20 µm. Son adım merkezi 78 µm'den 14 µm'ye taşıdı. Kalan gerçek ofsetin birkaç on µm mertebesinde olduğu söylenebilir. Tekrarlanabilirlik ölçümü (sabit akımda N tekrar) yapılmadı [YORUM].
- **x/y yönleri bobin çerçevesinde.** Bu bobin için faz ofseti (referans mıknatıs) alınmadı. Merkezin büyüklüğü ve yakınsama bundan etkilenmez. Ama x_c ile y_c'nin laboratuvardaki yönü bilinmiyor. Aynı nedenle özetteki "roll" (−1383 mrad) ve "SQ/G" (0.39) anlamsız.
- **Kalibrasyon uyarısı:** "V modu fiti lineer değil: g (R² = 0.90)". V modu gradyeni neredeyse hiç değiştirmediği için bu eğim gürültü düzeyinde. Merkezlemeyi etkilemedi.
- **7.9 mm'lik ofsetin nedeni bilinmiyor.** Mekanik yerleşim olabilir, bobinlerin konum ya da sarım farkları da olabilir. Hangisi olduğu bu veriden ayırt edilemez [HİPOTEZ]. Mekanik hizalama sonrası aynı ölçüm bunu gösterir.
- **Özet dosyasında "Kip: kuru" yazıyor, ama çalıştırma gerçek donanımdaydı.** Program `--canli` bayrağını özete ve pencerenin kip etiketine yansıtmıyordu. Bu düzeltildi (`merkezleme/ana.py: kipi_uygula`). Bu çalıştırmanın klasöründe `NOT.md` var.

## 5. Sonra ne yapılabilir

1. **Merkezlenmiş durumu yeniden kurmak:** 3. bölümdeki dört akım. Ya da kayıtlı kalibrasyonla yalnızca düzeltme aşamasını çalıştırmak (~4 dakika):
   `python -m merkezleme --otomatik --dosyadan --canli --yapilandirma yapilandirma_7A.yaml --kalibrasyon calistirmalar/2026-11-06_125537/kalibrasyon.json` (dönen bobin açıkken).
2. **Tekrarlanabilirlik:** son akımlarda 5–10 tekrar ölçüm, kalan ofsetin gerçek değeri için.
3. **Referans mıknatısla faz ofseti:** x/y yönlerini laboratuvara bağlamak ve mekanik hizalamaya yön vermek için.
4. **Mekanik hizalama:** ~8 mm'yi mekanik olarak kapatıp nominal 9.5 A ve varsayılan %5 sınırına dönmek. Asıl tasarım ~0.1 mm'lik ofsetler içindir.
5. **Okuma saati sıçraması:** sağlıklı veride bile 0.5–0.73 çıkıyor (raporda ~0.2 bekleniyordu). Varsayılan 0.6 eşiği bu yüzden sık sık sınırda kalıyor. Nedeni araştırılmalı.

## 6. Gürültü, hız ve şaft sabitlemesi (öğleden sonra)

**Ölçüm süresi** [ÖLÇÜLDÜ, kanal testi ham verisi]: akım açıkken merkez saçılımı 1 s'nin üstünde süreyle azalmıyor, ~20 µm'de kalıyor. Arka plandaki saçılım ise süreyle azalıyor.

**Güç kaynakları gürültünün kaynağı değil** [ÖLÇÜLDÜ, `gurultu_testi.py`]: ölçümler sırasında dört akım da 0.01 mA içinde sabit. Bunun merkezde yaratacağı oynama 0.1 µm'nin altında.

**Hız taraması, şaft sabitlenmeden önce** [ÖLÇÜLDÜ, `kayitlar/2026-11-06_140636`, her hızda 2 dk oturma]:
- 2 ve 4 Hz'de merkez dakikalarca sabit, saçılım 13–17 µm.
- 6 ve 10 Hz'de 2 dakikada ~1.2 mm sürükleniyor.
- 8 Hz'de önceki hızın izi yavaşça sönümleniyor.
- Düşük hızdaki ortalama, 8 Hz'deki ilk değerden ~1.1 mm farklı.

**Şaft sabitlendikten sonra** [ÖLÇÜLDÜ]:
- 4 Hz'de, 5 s pencereyle sıfırdan merkezleme yapıldı (`calistirmalar/2026-11-06_150208`): 6.30 mm → 75 µm, 3 iterasyon (x +72, y −21 µm). Son akımlar 7.757 / 6.286 / 6.410 / 7.881 A.
- Son akımlarda kararlılık testi (`kayitlar/2026-11-06_151703`, 4 → 8 → 4 Hz, her hızda 1 dk oturma):

| Hız | Saçılım x / y | Ortalama x / y |
|---|---|---|
| 4 Hz | 8.8 / 15.1 µm | −678 / +125 µm |
| 8 Hz | **3.1 / 1.8 µm** | −672 / +128 µm |
| 4 Hz | 12.1 / 14.2 µm | −682 / +140 µm |

Hıza bağlı kayma yok (farklar gürültü içinde), oturma sürelerinde de geçiş görülmedi. 8 Hz'de gürültü 3 / 2 µm'ye indi. Ortalamalarda arka plan çıkarılmadı.

**Bobinin konumu değişmiş görünüyor:**
- Benzer akımlarda ölçülen kuadrupol 1.77–1.86 mT'den 1.06 mT'ye düştü (%42).
- Ortam alanı değişmedi (33.5 → 32.1 µT). Yani ölçüm ölçeği sağlam, bobinin gördüğü gradyen azalmış.
- Başlangıç ofseti de 7.87 mm'den 6.30 mm'ye inmiş ve yönü değişmiş.

Sabitleme sırasında dönen bobin mıknatısa göre kaymış olabilir. Örneğin eksen boyunca, kısmen mıknatısın dışına çıkmış olabilir [HİPOTEZ]. Bu doğruysa ölçülen merkez, mıknatısın yalnızca bobinin içinde kalan kısmının ortalamasıdır.

## 7. Bobin merkeze taşındıktan sonra: 8 Hz, 10 µm tolerans

Kullanıcı dönen bobini mıknatısın merkezine doğru taşıdı. Merkezleme 8 Hz'de, 5 s pencereyle, sıfırdan kalibrasyon ve 10 µm toleransla yapıldı (`calistirmalar/2026-11-06_152726`) [ÖLÇÜLDÜ]:

| Adım | x_c (µm) | y_c (µm) |
|---|---|---|
| Başlangıç | +252 | +459 |
| İterasyon 1 | +62 | +99 |
| İterasyon 2 | +5 | +18 |
| İterasyon 3 | +11 | +3 |
| **İterasyon 4** | **−3.0** | **−0.7** |

- Son akımlar 7.082 / 7.041 / 6.923 / 6.964 A. Nominalden sapma en fazla %1.2.
- Kuadrupol geri geldi: |C2| = 1.857 mT, G_hedef = 0.069 T/m. Bu, 7 A için beklenen ~0.07 T/m. Bölüm 6'daki %42'lik düşüş, bobinin konumundan geliyormuş [YORUM].
- Kalibrasyon uyarısı: "M modu fiti lineer değil (R² = 0.95 / 0.91)". M modu merkezi neredeyse hiç kaydırmadığı için (M sütunu oranı 0.037) eğim gürültü düzeyinde. Zararsız.

**Son akımlarda kararlılık testi** (`kayitlar/2026-11-06_154308`, 8 → 4 → 8 Hz, her hızda 1 dk oturma, 10'ar ölçüm). Merkez, merkezleme çalıştırmasındaki ortalama arka plan çıkarılarak hesaplandı. Arka plan 33.07 µT, saçılımı 0.17 / 0.09 µT [ÖLÇÜLDÜ]:

| Hız | n | Merkez x / y (ortalamanın hatasıyla) | Tek ölçüm saçılımı |
|---|---|---|---|
| 8 Hz | 20 | **+0.0 ± 0.9 / +5.4 ± 0.9 µm** | 3–5 µm |
| 4 Hz | 10 | −3.2 ± 2.8 / −4.7 ± 2.4 µm | 8–9 µm |

Merkez 8 Hz'de x'te sıfırda, y'de ~5 µm kaçık. 4 Hz ile 8 Hz arasında y'de ~10 µm'lik bir fark kalıyor (~4σ). Hıza bağlı mekanik etkinin küçük bir kalıntısı olabilir [YORUM]. Sabitlemeden önceki ~1 mm'lik farkla karşılaştırıldığında ihmal edilebilir.

**Bugünün sonucu:** merkez, 8 Hz'de bobin eksenine göre ~5 µm içinde. Bu, tasarım hedefi olan 5 µm'nin sınırında. Akımların nominalden sapması %1.2'yi geçmiyor, yani varsayılan güvenlik sınırları (%5) içinde. Bir sonraki çalıştırma nominal 9.5 A ve varsayılan yapılandırmayla yapılabilir.
