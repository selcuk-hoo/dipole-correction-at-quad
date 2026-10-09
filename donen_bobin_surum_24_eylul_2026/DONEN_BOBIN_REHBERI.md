# Dönen bobin ölçüm sistemi: nasıl çalışır, nerede zayıftır

*Ekim 2026 · demirsiz kuadrupol merkezleme düzeneği için*

Bu yazı, İrfan'ın geliştirdiği dönen bobin sistemini ve üzerine yapılan değişiklikleri baştan sona anlatır: ölçümün fiziği, donanım zinciri, yazılımın her adımda ne yaptığı, sistematik hataların hangilerinin giderildiği, hangilerinin açık olduğu ve lab'da bunların nasıl sınanacağı. Sayısal değerler, aksi belirtilmedikçe, bu düzeneğin parametreleriyle yapılmış simülasyonlardandır (bkz. `SISTEMATIK_HATALAR_RAPORU.md`). Gerçek donanımdaki düzeyler lab'da ölçülmelidir.

---

## İçindekiler

1. [Ölçümün fiziği](#1-ölçümün-fiziği)
2. [Elimizdeki alet](#2-elimizdeki-alet)
3. [Yazılım: bir ölçüm nasıl yapılır](#3-yazılım-bir-ölçüm-nasıl-yapılır)
4. [Hangi hatalar merkezleme için önemli](#4-hangi-hatalar-merkezleme-için-önemli)
5. [Giderilen hatalar](#5-giderilen-hatalar)
6. [Açık duran hatalar ve zayıf yanlar](#6-açık-duran-hatalar-ve-zayıf-yanlar)
7. [Lab'da yapılacak testler](#7-labda-yapılacak-testler)
8. [Önerilen iyileştirmeler](#8-önerilen-iyileştirmeler)
9. [Sözlük](#9-sözlük)

---

## 1. Ölçümün fiziği

### 1.1 Dönen bir bobin neyi ölçer

Mıknatısın açıklığına, mıknatıs eksenine paralel bir tel çerçeve (bobin) yerleştirilir ve eksen etrafında döndürülür. Bobinden geçen manyetik akı Φ, bobinin o anki açısına göre değişir; Faraday yasasına göre uçlarında V = −dΦ/dt gerilimi oluşur. Bobin bir tur attığında alanın açıklık içindeki dağılımını "taramış" olur. Akının açıya göre değişimini Fourier bileşenlerine ayırmak, alanın çok kutup bileşenlerini verir.

### 1.2 Çok kutuplar

Mıknatıs açıklığındaki iki boyutlu alan, karmaşık sayılarla tek bir seri olarak yazılır (z = x + iy, r_ref = 25 mm referans yarıçapı):

  B_y + i·B_x = Σ C_n · (z / r_ref)^(n−1)

| n | Ad | Alan biçimi |
|---|---|---|
| 1 | dipol | düzgün alan |
| 2 | kuadrupol | merkezden uzaklıkla doğrusal artan alan (gradyen) |
| 3 | sekstupol | uzaklığın karesiyle |
| 4, 5, 6 | oktupol, dekapol, dodekapol | ... |

C_n karmaşık sayıdır: gerçek kısmı **normal** (b_n), sanal kısmı **skew** (a_n) bileşendir. Dosyalarda ve pencerede b0/a0 n = 1'i, b1/a1 n = 2'yi gösterir.

### 1.3 Merkez neden C₁/C₂'den çıkar

İdeal bir kuadrupolün alanı tam merkezinde sıfırdır: yalnızca C₂ vardır. Mıknatıs ölçüm eksenine göre z_c kadar kaçıksa, ölçüm ekseninde alan sıfır değildir. Kuadrupol alanı kaydırılınca bir dipol bileşeni doğar (buna "feed-down" denir):

  C₁ = −C₂ · z_c / r_ref  →  **z_c = −r_ref · C₁ / C₂**

Merkezleme programı mıknatısı hareket ettirmez; dört bobinin akımlarına küçük asimetriler uygulayarak C₁'i sıfırlar. Ölçüm sisteminin görevi C₁ ve C₂'yi doğru ölçmektir.

### 1.4 Ölçeği hissetmek: 1 µm ne kadar küçük

Merkezdeki 1 µm'lik kaçıklık, C₁'in C₂'ye oranında 1 µm / 25 mm = **4·10⁻⁵** demektir. Bizim bobinde n = 1'in duyarlılığı n = 2'ninkinden biraz farklı olduğundan (bölüm 2.2), gerilimde bu oran ~**2,5·10⁻⁵**'tir. Yani:

> Ana (n = 2) sinyalin **milyonda 25'i** kadar bir sızıntı, merkezde **1 µm** hata yapar.

Bu yüzden n = 2'yi n = 1'e karıştıran her küçük etki (hız dalgalanması, açı hatası, zamanlama kayması) önemlidir. Bu yazının büyük kısmı bu tür karışmalarla ilgilidir.

Örnek (simülasyondaki mıknatıs, G ≈ 0,095 T/m, 23 Hz):
- n = 2 sinyalinin tepe değeri ≈ **5,5 mV**,
- 1 µm merkeze karşılık gelen n = 1 sinyali ≈ **0,14 µV**.

---

## 2. Elimizdeki alet

### 2.1 Veri zinciri

```
  ┌──────────────── DÖNEN KISIM ────────────────┐        ┌────────── SABİT KISIM ───────────┐
  │                                              │        │                                  │
  │  Düz bobin 1 ─┐                              │        │  Enkoder (artımlı, 3600/tur)     │
  │  Düz bobin 2 ─┼─► ADS1263 ADC ─► Rotor kartı ◄──RS485──►  Stator kartı (RP2350)        │
  │               │   32×, 7200 SPS,  (RP2350)   │ 8 Mb/s │   - enkoderi okur (~1 kHz gönderir)
  │               │   Sinc4           her örneğe │        │   - motora adım darbesi verir   │
  │               │                   son enkoder│        │   - servo açık/kapalı          │
  │               │                   değerini   │        │   - Ethernet (W5500)            │
  │               │                   ekler      │        │                                  │
  └──────────────────────────────────────────────┘        └───────────────┬──────────────────┘
                                                                          │ TCP
                                                                          ▼
                                                             PC: merkezleme_olcer.py
                                                             (analiz) ── kilit dosyası ──► merkezleme
```

**Dönen kısım:** iki düz bobin ve onları okuyan ADC (ADS1263) dönen karttadır. Bobin kabloları dönen–sabit geçişinden geçmez; analog sinyal, mile bağlı kartta sayısallaştırılır ve geçişten yalnızca sayısal veri (RS485) geçer. Bu iyi bir tasarımdır: mikrovoltluk sinyal, geçişteki (kayar halka vb.) temas gürültüsünden korunur.

**Rotor kartı:** ADC her örneği hazırladığında (7200 kez/s) bir paket oluşturur: [ADC değeri, o ana kadar statordan gelen **son** enkoder değeri] ve bunu RS485 ile statora yollar.

**Stator kartı:**
- Enkoderi sürekli okur ve en fazla milisaniyede bir, değer değiştiyse rotora gönderir.
- Motoru adım/yön darbeleriyle sürer: 3600 adım/tur, ivme 10 tur/s². 23 Hz'e ~2,3 s'de çıkar.
- Gelen örnekleri TCP ile PC'ye aktarır.
- Saniyede bir durum paketi yollar: ölçülen hız, hata sayaçları.

**PC:** paketleri bir halka tamponda tutar (1 milyon örnek ≈ 139 s). Ölçüm programı bu tampondan pencereler alıp analiz eder.

### 2.2 Bobinler ve duyarlılıkları

- İki düz bobin: 5 sarım, 100 mm (eksen boyunca) × 20 mm, ortaları eksenden 20 mm uzakta, **teğet** (bobin düzlemi yarıçapa dik).
- Birbirlerine diktirler; yani dönen çerçevede 90° farklı açıda dururlar.
- AIN0–AIN1 bobin 1, AIN4–AIN5 bobin 2'dir.

Bir bobinin n. harmoniğe duyarlılığı, iletkenlerinin konumlarından hesaplanır: K_n = (z₂ⁿ − z₁ⁿ)/(n·r_refⁿ⁻¹). Gerilim n·K_n ile orantılıdır:

| n | 1 | 2 | 3 | 4 | 5 | 6 | 7 |
|---|---|---|---|---|---|---|---|
| n·\|K_n\| (mm) | 20 | 32 | 35 | 31 | 21 | 9 | 2,4 |

İletkenler eksenden R = 22,4 mm uzakta ve bobin ortasından ±26,6° açıdadır. Duyarlılık sin(n·26,6°) ile gider: n = 3 civarında en yüksek, **n = 6'da zayıf, n = 7'de neredeyse kör**. Bu, bobin geometrisinin değişmez bir özelliğidir.

### 2.3 Enkoder ve "sıfır" sorunu

Enkoder **artımlıdır** (incremental): yalnızca açı değişimlerini sayar, mutlak açıyı bilmez. Çözünürlük 3600 sayım/tur, yani 0,1°. Firmware sayacı açılışta sıfırlar; bu yüzden "sıfır açı" her açılışta milin o anki konumudur. Bu, **referans mıknatıs** ölçümünü gerektirir (bölüm 3.4).

0,1° çözünürlük tek başına sorun değildir: simülasyonda merkeze etkisi **0,06 µm**.

### 2.4 ADC

ADS1263 32 bitlik bir delta-sigma ADC'dir. Ayarlar:
- Kazanç 32: tam ölçek ±78 mV. Pencere, sinyal tepesi bunun %80'ini aşarsa doyma uyarısı verir.
- 7200 örnek/s, Sinc4 sayısal filtre.

Filtre, her örneği birkaç yüz mikrosaniye **geçmişe** kaydırır. Bu, bölüm 5.2'deki gecikmenin bir parçasıdır.

---

## 3. Yazılım: bir ölçüm nasıl yapılır

### 3.1 Programlar

| Program | Ne yapar |
|---|---|
| `host/radarMGF.py` (İrfan'ın büyük arayüzü) | Geliştirme ve genel ölçüm: 9 sekme, FFT, kayıt, makrolar. |
| `host/merkezleme_olcer.py` (minimal pencere) | Merkezleme için sadeleştirilmiş tek pencere. Bu yazıda anlatılan analiz burada. |
| `python -m merkezleme` (depo kökü) | Akımları ayarlayan merkezleme programı. Ölçümleri `veri_kilidi/.kilit` dosyasından alır. |

Minimal pencere ile merkezleme programı bir **kilit dosyası** üzerinden konuşur:
1. Merkezleme akımları ayarlar ve kilidi siler ("ölç").
2. Ölçüm programı, kilit silindikten **sonra** gelen veriyle ölçer ve sonucu kilide yazar ("veri hazır").
3. Merkezleme okur, yeni akımları ayarlar, kilidi siler.

Kilit silinmeden önceki veri kullanılmaz, çünkü akımlar o sırada değişiyor olabilir.

### 3.2 Bir ölçümün adımları

Her ölçüm, son `pencere_s` saniyelik (varsayılan 2 s, ~46 tur) veriden yapılır:

1. **Açıyı düzelt (merdiven).** Enkoder değeri ~1 ms'de bir güncellenir; araya düşen ~7 örnek aynı (eskimiş) açıyı taşır. Program her yeni değerin geldiği ilk örneği bulur, okumaların düzenli saatine bir doğru oturtur ve açıyı aralarda kübik eğriyle enterpole eder (bölüm 5.3).
2. **Gecikmeyi uygula.** Gerilim örneği, yanındaki açıdan L kadar eskidir. Açı zamanda L kadar geri kaydırılır (bölüm 5.2).
3. **Akıyı bul.** Gerilim zamana göre toplanır: Φ = −∫V dt. Akı yalnızca bobinin **konumuna** bağlıdır, hızına bağlı değildir (bölüm 5.1).
4. **Tam turlara kırp.** Pencere tam tur sayısına indirilir.
5. **Uydur.** Akı, açıya karşı en küçük karelerle uydurulur:
   - sabit + 3. dereceden zaman polinomu (ADC ofsetinin integrali ve yavaş sürüklenme),
   - 1'den 15'e kadar harmonikler.

   n = 1..6 raporlanır; üstteki harmonikler, raporlanan mertebelere sızmasınlar diye modelde tutulur.
6. **Harmonikleri Tesla'ya çevir.** Her harmoniğin akı genliği, bobinin o mertebedeki duyarlılığına (N·L·K_n) bölünür. Toplama yönteminin (yamuk kuralı) küçük kazanç kaybı da düzeltilir.
7. **Merkezi hesapla.** z_c = −r_ref·C₁/C₂.
8. **Sağlık kontrolü.** İki ölçüt vardır; biri aşılırsa ölçüm merkezleme'ye yazılmaz:
   - **Uydurma artığı:** uydurmanın açıklayamadığı kısım / harmonik içerik (eşik 2·10⁻²),
   - **Okuma saati sıçraması:** kayıp örnek göstergesi (eşik 0,6).

### 3.3 Pencerede gördükleriniz

- **Durum kutusu:** ölçülen hız, yazılan ölçüm sayısı, faz ofseti (seçili bobinin), sinyal tepesi, gecikme, "Artık / saat sıçr.", kayıt dosyası, uyarılar.
- **Son ölçüm:** b0, a0 (dipol), b1, a1 (kuadrupol), gradyen, x_c, y_c.
- **Çok kutuplar sekmesi:** son 20 ölçümün ortalaması ± tek ölçüm saçılımı, logaritmik eksende. Hata çubuğu çubuktan uzunsa o terim gürültünün altındadır.
- **Bobin akısı sekmesi:** son pencerenin akısı açıya karşı, bütün turlar üst üste; çizgi uydurmadır. Noktalar çizgiye oturmalıdır.
- **Günlük:** her olay ve uyarı.

### 3.4 Referans mıknatıs (her bobin için ayrı)

Enkoderin sıfırı her açılışta değiştiğinden, programın "x yönü" ile mıknatısın x yönü arasındaki açı bilinmez. Alanı **düşey** olan bir referans dipol mıknatısı takılır ve "Referans mıknatısla sıfırla"ya basılır. Program, o alanı saf normal ve pozitif (b0 > 0, a0 = 0) gösterecek açı ofsetini bulur.

- **Her bobin için ayrı:** iki bobin dönen çerçevede 90° farklı durduğundan, birinin ofseti öbürüne uygulanırsa merkez 90° dönük çıkar. Program artık ofseti bobin başına tutuyor ve referansı alınmamış bobinde uyarıyor.
- **Yalnızca yön belirler:** referans x/y yönlerini belirler. Merkezlemenin yakınsamasını etkilemez (bölüm 4).
- **Kontrol:** referans mıknatıs takılı değilken ya da sinyal zayıfken basılırsa program ofseti değiştirmez ve nedenini yazar.

### 3.5 Gecikme ölçümü (iki yönlü)

"Gecikme ölç (iki yön)" düğmesi (yalnızca "Merkezleme'ye yaz" kapalıyken):
1. Bu yönde bir pencere alınır.
2. Motor ters çevrilir.
3. Öbür yönde bir pencere alınır.

Gecikme, iki yön arasındaki faz farkından bulunur (bölüm 5.2). Ölçülen değer günlükte yazılır; `merkezleme_olcer.yaml` → `olcum.gecikme_ms`'e girilince kalıcı olur. Donanım ve ADC ayarları değişmedikçe sabittir. Sinyal zayıfsa (belirsizlik > 2 µs) uygulanmaz.

---

## 4. Hangi hatalar merkezleme için önemli

Bu, sistemi değerlendirmenin anahtarıdır. Merkezleme programı ilk adımlarda, akımları değiştirip ölçülen C₁'in nasıl değiştiğini **kendisi ölçer** (tepki matrisi) ve sonra C₁'i sıfıra sürer. Bu nedenle hatalar üç sınıfa ayrılır:

**A. Ölçek ve dönme hataları — zararsız.** Bobin duyarlılığındaki (K_n) hata, elektronik kazanç hatası, küçük bir faz ofseti hatası ölçülen C₁'i bir sayıyla çarpar ya da döndürür. Merkezleme bunu tepki matrisine katar; **sıfır, sıfır olarak kalır.** Bunlar yalnızca raporlanan µm değerlerinin doğruluğunu etkiler, varılan noktayı etkilemez.

**B. Ofset tipi hatalar — kritik.** Gerçek merkez sıfırken ölçümde **sahte bir C₁** üreten her etki, merkezleme'yi yanlış bir noktaya götürür. Bu kaymayı hiçbir yinelemeyle fark edemez. Bunlar çoğunlukla n = 2'nin n = 1'e karışmasıdır (bölüm 1.4: milyonda 25 sızıntı = 1 µm). **Bu yazıdaki en önemli hatalar bu sınıftadır.**

**C. Rastgele hatalar — tekrarlanabilirlik.** Gürültü, zamanlama titreşimi. Ölçüm süresi uzatılarak ya da ortalama alınarak azalır, sistematik kayma yapmaz.

Bir ek kural: merkezleme sürerken ölçüm çerçevesi değişirse (bobin, faz ofseti, gecikme, yön, hız), A sınıfı bir hata yarıda değişmiş olur ve tepki matrisi geçersizleşir. Program bu yüzden "Merkezleme'ye yaz" açıkken bunları kilitler.

---

## 5. Giderilen hatalar

Ayrıntılı sayılar: `SISTEMATIK_HATALAR_RAPORU.md`. Burada sezgisi anlatılıyor.

### 5.1 Tur içi hız dalgalanması (B sınıfı) — giderildi

**Kaynak:** motor her turda tam sabit hızla dönmez. Gerilim V = −ω(t)·dΦ/dθ, yani o anki hızla orantılıdır.

**Neden kötüydü:** eski yöntem gerilimi ortalama hızla bölüyordu. Hız turun bir yerinde %1 hızlıysa, n = 2 sinyali o bölgede %1 büyük görünür; bu, n = 2'nin n = 1 ve n = 3'e karışmasıdır.

| Açı dalgası | Eski yöntem | Yeni yöntem |
|---|---|---|
| 0,25° | 88 µm | 0,04 µm |
| 0,5° (~%1–2 hız dalgası) | 177 µm | 0,04 µm |
| 2° | 733 µm | 0,10 µm |

**Çözüm:** gerilim zamanda toplanarak akı bulunur. Akı bobinin nerede olduğuna bağlıdır, ne hızla gittiğine değil. Dönen bobin sistemlerinde bu, donanım integratörüyle (dijital integratör kartı) yapılır; burada ADC örnekleri zamanda düzgün aralıklı olduğundan yazılımla yapılabiliyor.

### 5.2 ADC–enkoder zaman gecikmesi (B sınıfı) — giderildi

**Kaynak:** gerilim örneği ADC filtresi yüzünden birkaç yüz µs eskidir. Enkoder değeri de rotora gecikmeli ulaşır. Sonuçta her örnek, yanında yazan açıdan L kadar farklı bir ana aittir (simülasyonda 0,18 ms; gerçek değer lab'da ölçülecek).

**Neden önemli:**
- **Sabit hızda zararsız:** L yalnızca sabit bir açı kaymasıdır (23 Hz'de 1,5°) ve referans onu yutar.
- **Hız dalgalanırken:** kayma da dalgalanır ve yine n = 2 → n = 1 karışması olur. 0,5° dalgada 4,5 µm, 2°'de 19 µm.
- **Yön değişince:** kayma işaret değiştirir. Referans bir yönde, ölçüm öbür yönde alınırsa 8 µm (152 µm'lik bir merkezde).

**Çözüm:** iki yönlü ölçüm. Gecikme, harmonikleri bir yönde bir tarafa, öbür yönde öbür tarafa döndürür; iki yönün farkı L'yi verir (doğruluk: 0,1800'e karşı 0,1798 ms). Bilinen L ile her örneğin açısı zamanda kaydırılır; hata 0,04–0,10 µm'ye iner.

Mil burulması ya da kaplin boşluğu gibi **yöne bağlı sabit bir açı farkı** da ölçülen "gecikme"nin içine girer ve aynı şekilde giderilir. Ama bu bileşen zaman değil açı olduğundan, L **ölçüldüğü hızda** geçerlidir. Hız değişirse yeniden ölçün.

### 5.3 Enkoder merdiveni (B sınıfı) — giderildi

**Kaynak:** açı ~1 ms'de bir güncellenir. 23 Hz'de bu 8,3°'lik basamaklar demektir; aradaki örnekler 0–8° eski açıyı taşır.

**Neden kötüydü:** basamaklı açı harmonikleri bozar. Merkezde 2,4 µm; n = 2 kazancında %0,25; n = 6'da 4 birim (1 birim = C₂'nin 10⁻⁴'ü).

**Çözüm:** okumalar stator saatine bağlı düzenli aralıklarla gelir. Program her yeni değerin geldiği ilk örneğe bir doğru oturtup okuma anlarını örnek altı hassasiyetle bulur, sonra açıyı kübik eğriyle enterpole eder. Kalan hata: merkezde 0,04 µm, n = 6'da 0,1 birim.

### 5.4 Yamuk toplamının kazanç kaybı (A sınıfı) — giderildi

Gerilimi örnekten örneğe toplamak (yamuk kuralı), hızlı değişen bileşenleri biraz küçültür: n = 2'de 1,3·10⁻⁴, n = 6'da 1,2·10⁻³. Kesin formülü bilindiği için düzeltilir; kalan ~10⁻⁶.

### 5.5 Dönüş yönünde işaret (A sınıfı) — giderildi

Eski kod hızın mutlak değerini kullandığı için ters yönde bütün harmoniklerin işareti ters çıkıyordu. Akı yönteminde yön sonucu etkilemez.

### 5.6 Örnek kaybı (B sınıfı) — tespit ediliyor

**Kaynak:** firmware örneklere sıra numarası koymuyor:
- Stator, RS485'te bozulmuş gelen örnekleri sessizce atıyor.
- PC tarafında alım kuyruğu dolarsa paket düşüyor.

Akı toplamı örneklerin kayıpsız olduğunu varsayar.

**Etki:** tek bir kayıp, akıda bir basamak yaratır; merkezde **4–8 µm**.

**Çözüm (tespit, onarım değil):** enkoder okumaları düzenli saatle geldiğinden, kayıp bir örnek sonraki bütün okumaları bir örnek erken gösterir. Program bu kaymayı ölçer ("saat sıçraması": sağlıklıda ~0,2, tek kayıpta ~1) ve ölçümü reddeder. Stator'un hata sayacı artarsa günlüğe uyarı düşer.

### 5.7 Diğer koruma ve düzeltmeler

- **Çerçeve kilidi:** "Merkezleme'ye yaz" açıkken bobin, hız, referans, gecikme değiştirilemez.
- **Faz ofseti bobin başına:** iki bobin karıştırılırsa merkez 90° dönük çıkıyordu; düzeltildi.
- **Bağlantı kopması:** firmware bağlantı kopunca motoru **durdurmaz**. Program yeniden bağlanınca önce motoru durdurur, durunca servoyu kapatır.
- **Zayıf sinyal:** gecikme ve referans, ancak fazları yeterince kesin ölçülmüşse uygulanır.
- **Mıknatıs modülasyonu:** mıknatısın 1 kHz %1 modülasyonu açıkken uydurma artığı ~6,6·10⁻³ olur ama merkez etkilenmez (0,05 µm). Artık eşiği buna göre 2·10⁻²'ye ayarlandı.

---

## 6. Açık duran hatalar ve zayıf yanlar

Önem sırasına göre. Her biri için sınıf (bölüm 4), büyüklük, nasıl fark edileceği ve ne yapılabileceği verilmiştir.

### 6.1 Enkoderin tur başına açı hatası — B sınıfı, en önemli açık konu

**Nedir:** enkoder diski mile tam ortalı değilse ya da enkoder ile bobin mili arasındaki kaplin her turda biraz salınıyorsa, okunan açı gerçek açıdan tur başına bir kez salınan bir hatayla sapar: ε·cos(θ + φ). Ucuz enkoderlerde ve kaplinli düzeneklerde birkaç açı dakikası olağandır.

**Neden kritik:** bu açı hatası n = 2'yi doğrudan n = 1'e karıştırır. Simülasyonda sahte merkez kayması tam olarak

  **Δz = d · ε** (d = bobinin eksene uzaklığı = 20 mm)

- 1 açı dakikası → **5,8 µm**
- 5 açı dakikası → **29 µm**

Bu hata **yönden bağımsızdır**; iki yönlü ölçüm onu gidermez. Merkezleme mıknatısı bu kadar yanlış bir noktaya götürür ve bunu fark edemez. 2 periyotlu (tur başına iki kez) açı hataları ise önemsizdir (1 açı dakikasında 0,05 µm).

**Nasıl fark edilir:** iki bobin bu hatayı birbirine **90° dönük** gösterir. Simülasyonda bobin 1'in sahte kayması s ise bobin 2'ninki i·s'dir. Mıknatıs merkeze yakınken iki bobin farklı merkez gösteriyorsa, büyük olasılıkla bu hata vardır. Fark z₁ − z₂ = s·(1 − i) ilişkisinden s hesaplanabilir.

**Ne yapılabilir:** iki bobinli bir **kalibrasyon** yazılıma eklenebilir:
1. İki bobinle merkez ölçülür; açı farkları kendi referanslarından bilinir.
2. Farktan sahte kayma çözülür.
3. Kalıcı bir düzeltme olarak saklanır.

Bu, mevcut donanımla yapılabilir. Alternatif: bobin milde 180° döndürülüp yeniden takılırsa sahte kayma işaret değiştirir; iki ölçümün ortalaması onu yok eder.

### 6.2 Dönme ekseninin oynaması, titreşim — B ve C sınıfı

**Nedir:** ölçülen merkez, **bobinin dönme eksenine göre**dir. Yatak boşluğu, mil eğilmesi, motor ya da zemin titreşimi bu ekseni oynatırsa, kuadrupol alanı bu oynamayı doğrudan dipol olarak gösterir. Eksen 1 µm kayarsa ölçülen merkez de ~1 µm değişir.
- **Rastgele titreşim:** gürültü ekler.
- **Dönmeyle eşzamanlı salınım** (örneğin mil turda bir kez yalpalıyorsa): sistematik karışma yapabilir.

**Neden önemli:** büyük dönen bobin sistemlerinde (CERN, Fermilab) bu yüzden **kompanzasyon (bucking)** kullanılır. Birden çok bobin, ana harmoniği birbirini yok edecek biçimde bağlanır; titreşimin ana harmonik üzerinden yarattığı karışma büyük ölçüde iptal edilir. Bizim sistemde bucking yok; iki bobin ayrı ayrı okunuyor.

**Nasıl fark edilir:** manyetik harmonikler hızdan bağımsızdır, mekanik titreşim etkileri genellikle hıza bağlıdır (rezonanslar). Aynı alanı 10, 15, 23 Hz'de ölçün; sonuçlar hıza göre değişiyorsa mekanik bir etki vardır.

**Ne yapılabilir:** önce ölçmek. Gerekirse mekanik iyileştirme (yatak, kaplin) ya da bucking için ek bobin.

### 6.3 Mil sehimi (yerçekimi) — B sınıfı, hedefe bağlı

Uzun bir mil ortasında yerçekimiyle biraz sarkar. Ölçülen merkez sarkmış eksene göredir; yani program mıknatısı bu eksene ortalar. Sehim yönden bağımsızdır, iki yönlü ölçüm gidermez. Bunun hata olup olmadığı, merkezin hangi eksene göre istendiğine bağlıdır: ışın ekseni dış referanslarla (lazer izleyici vb.) tanımlanıyorsa, sehim bir ofset olarak hesaba katılmalıdır.

### 6.4 Arka plan manyetik alanı — B sınıfı, kısmen çözülmüş

**Nedir:** Dünya'nın alanı (~50 µT) ve laboratuvardaki başıboş alanlar. Mıknatıs **demirsiz** olduğundan bunları perdelemez.

**Büyüklük:** 50 µT'lık bir dipol, G ≈ 0,095 T/m'lik bir kuadrupolde merkezi r_ref·C₁/C₂ ≈ **0,5 mm** kaydırır.

**Durum:** merkezleme programı mıknatıs kapalıyken arka plan ölçümü alıp çıkarıyor. Arka plan ölçümler arasında değişirse çıkarma eksik kalır: yakına demir taşınması, kapı ya da vinç, komşu mıknatısların açılıp kapanması. Arka plan ölçümünü sık tekrarlamak ve ortamı sabit tutmak önemlidir.

### 6.5 Enkoder okuma zamanlamasının titreşimi — C sınıfı

**Nedir:** stator enkoderi ana döngüsünde okur. Bu döngü Ethernet gönderimi gibi işlerle zaman zaman gecikebilir; okuma anı düzenli saatten birkaç ya da birkaç on µs sapar. Program okuma anlarını düzenli saat varsayarak bulduğu için bu sapma açı hatasına dönüşür.

| Titreşim | 2 s pencere | 8 s pencere |
|---|---|---|
| 5 µs | 1,2 µm | 0,24 µm |
| 20 µs | 4,7 µm | 1,0 µm |

Rastgeledir; ölçüm süresi uzatılarak azalır. Gerçek düzeyi bilinmiyor. Lab'da tekrarlanabilirlikten anlaşılır; yazılım bunu doğrudan gösterecek şekilde genişletilebilir.

**Kalıcı çözüm (firmware):** enkoder okumasına zaman damgası eklemek, ya da rotorda açıyı örnek anına enterpole etmek.

### 6.6 Bobin geometrisi ve 3B etkiler — A sınıfı

- **Duyarlılık hatası:** sarım, genişlik, eksene uzaklıktaki küçük hatalar duyarlılığı (K_n) değiştirir. Bu ölçek ve dönme hatasıdır; merkezleme sonucunu değiştirmez, raporlanan µm'leri değiştirir.
- **Yana kayık bobin:** bobin 0,5 mm yana kayıksa n = 2'nin fazı ~1,4° kayar ve raporlanan merkez yönü o kadar döner.
- **Mutlak doğruluk:** bilinen gradyenle (|C₂|/r_ref) ve bilinen bir mekanik kaydırmayla kalibre edilir.
- **3B:** bobin 100 mm boyunca **ortalama** alanı ölçer. Mıknatıs boyu ya da uç alanları farklıysa, ya da mıknatıs eksene göre eğikse, ölçülen merkez bu uzunluk boyunca ortalamadır.

### 6.7 ADC ve elektronik

- **Doyma:** kazanç 32'de tam ölçek ±78 mV. Pencere %80'de uyarır; doyarsa kazancı düşürün.
- **Gürültü:** simülasyonda 1 µV gürültü merkezde ~0,2 µm (2 s) yapar. Yüksek gradyende etkisi azalır.
- **Sinc4 filtresinin genlik düşümü:** yüksek mertebelerde ~10⁻³. Düzeltilmedi; merkezde ihmal edilebilir (0,03 µm).
- **50 Hz şebeke ve motor sürücüsü paraziti:** dönmeyle eşzamanlı değilse uydurma onu harmonik saymaz, artığa gider. Eşzamanlıysa (sürücü akımı dönme açısına bağlıysa) harmonik gibi görünebilir. Motor kapalıyken ve farklı hızlarda karşılaştırılmalı.
- **Ofset ve sürüklenme:** uydurmadaki zaman polinomuyla giderilir.

### 6.8 Firmware'den gelen sınırlar

| Sınır | Sonuç | Öneri |
|---|---|---|
| Örnek sıra numarası yok | Kayıp tespit edilir ama ölçüm kaybolur | Rotorda örnek sayacı |
| Enkoder ~1 ms'de bir, enterpolasyonsuz | Merdiven (yazılımla telafi) ve okuma titreşimi | Zaman damgası ya da rotorda enterpolasyon |
| Bağlantı kopunca motor dönmeye devam eder | PC tarafı yeniden bağlanınca durduruyor | Firmware'de bağlantı bekçisi (rampalı durma) |
| Enkoder artımlı, indekssiz | Her açılışta referans gerekir | İndeksli ya da mutlak enkoder |

### 6.9 Mıknatıs tarafı

- **Histerezis yok:** demirsiz mıknatısın avantajı; alan doğrudan akımla orantılıdır.
- **Isınma:** bobin direnci değişir (sabit akım kaynağı bunu dengeler), mekanik genleşme merkezi kaydırabilir. Uzun çalışmalarda merkez zamanla sürükleniyorsa ısıl etki düşünülmeli.
- **Güç kaynağı akım gürültüsü:** alan gürültüsüne dönüşür; C sınıfı.

---

## 7. Lab'da yapılacak testler

Her test, belirli bir hatayı ortaya çıkarmak için tasarlanmıştır.

| # | Test | Ne gösterir |
|---|---|---|
| 1 | Sürekli ölçüm, 2 s ve 8 s pencere; x_c, y_c saçılımı | Rastgele hatalar (6.5, 6.7). 8 s'de saçılım ~yarıya inmeli. |
| 2 | "Gecikme ölç" 2–3 kez | L'nin değeri ve tutarlılığı (µs düzeyinde). Sonuç yaml'a. |
| 3 | Gecikme ayarlıyken +23 ve −23 Hz | Yöne bağlı kalan etkiler. Aynı çıkmalı. |
| 4 | Aynı alan 10, 15, 23 Hz | Mekanik/titreşim etkileri (6.2). Manyetik sonuç hızdan bağımsız olmalı. |
| 5 | **Merkeze yakınken bobin 1 ve bobin 2** (her biri kendi referansıyla) | Enkoder tur başına hatası (6.1). Fark ~0 olmalı; değilse kalibrasyon gerekir. |
| 6 | Mıknatısı bilinen miktarda +x, sonra +y kaydırma | İşaret, el kuralı ve merkez ölçeği (6.6). |
| 7 | Bilinen gradyenle karşılaştırma | Mutlak ölçek (K₂). |
| 8 | Referans mıknatıs | b0 > 0, a0 ≈ 0; referans her iki bobin için ayrı alınmalı. |
| 9 | Mıknatıs kapalı, motor dönüyor | Arka plan alanı ve parazit düzeyi (6.4, 6.7). |
| 10 | Modülasyon açık / kapalı | Artığın ~6·10⁻³'e çıkıp merkezin değişmediği. |
| 11 | Uzun süre (saatler) ölçüm | Isıl ve mekanik sürüklenme (6.9). |
| 12 | "Artık / saat sıçr." değerleri, günlükte RS485 uyarıları | Sağlıklı düzeyler; eşiklerin uygunluğu; örnek kaybı sıklığı. |

---

## 8. Önerilen iyileştirmeler

Öncelik sırasıyla:

**Yazılım (mevcut donanımla):**
1. **İki bobinli enkoder kalibrasyonu** (6.1): en önemli açık sistematik hatayı ölçüp düzeltir.
2. **Okuma titreşimi göstergesi** (6.5): okuma saati uydurmasının sapmasından titreşimi µs olarak göstermek.
3. **Hız dalgalanması göstergesi:** enkoder verisinden tur içi hız profilini çıkarıp göstermek (motorun gerçek davranışını görmek için).

**Firmware:**
4. Rotorda örnek sayacı (kayıp tespiti yerine kayıp onarımı ya da kesin tespit).
5. Enkoder okumasına zaman damgası ya da rotorda açı enterpolasyonu.
6. Bağlantı kopunca motoru rampalı durduran bekçi.

**Donanım:**
7. Kompanzasyon (bucking) bobini: titreşim duyarlılığını azaltır, küçük harmonikleri daha iyi ölçer.
8. İndeksli ya da mutlak enkoder: açılışta referans gereksinimini kaldırır.

---

## 9. Sözlük

| Terim | Anlamı |
|---|---|
| Akı (Φ) | Bobinden geçen manyetik alan toplamı. Gerilim akının zamana göre değişimidir. |
| Artık (uydurma artığı) | Uydurmanın açıklayamadığı kısmın, harmonik içeriğe oranı. Ölçümün sağlığını gösterir. |
| Bucking (kompanzasyon) | Ana harmoniği iptal edecek biçimde birleştirilmiş bobinler. |
| Çerçeve | Ölçümün yapıldığı koşullar: bobin, faz ofseti, gecikme, yön, hız. |
| Çok kutup (C_n) | Alanın dipol, kuadrupol, sekstupol... bileşenleri. |
| Faz ofseti | Enkoder açısı ile mıknatısın x ekseni arasındaki açı. Referansla bulunur. |
| Feed-down | Kaçık bir çok kutbun alt mertebeler üretmesi (kaçık kuadrupol → dipol). |
| Gecikme (L) | Gerilim örneğinin, yanındaki açıya göre ne kadar eski olduğu. |
| K_n (duyarlılık) | Bobinin n. harmoniğe ne kadar duyarlı olduğu; geometrisinden hesaplanır. |
| Merdiven | Enkoder değerinin basamaklı güncellenmesi. |
| Okuma saati sıçraması | Kayıp örnek göstergesi. |
| Referans mıknatıs | Alanı bilinen yönde (düşey) bir dipol; açı sıfırını bulmak için. |
| r_ref | Harmoniklerin verildiği referans yarıçap (25 mm). |
| Skew / normal | Çok kutbun 90°/n döndürülmüş ve döndürülmemiş bileşenleri. |
| Tepki matrisi | Merkezlemenin ölçtüğü, akım değişimleri ile C₁ değişimleri arasındaki ilişki. |

---

*İlgili belgeler: `README_SURUM.md` (kullanım ve lab planı), `SISTEMATIK_HATALAR_RAPORU.md` (giderilen hataların sayısal ayrıntısı), depo kökündeki `README.md` (merkezleme programı ve konvansiyonlar).*
