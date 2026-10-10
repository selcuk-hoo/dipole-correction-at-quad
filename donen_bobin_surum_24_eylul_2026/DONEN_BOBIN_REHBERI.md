# Dönen bobin sistemi: nasıl çalışır, nerede zayıftır

*Ekim 2026 · Demirsiz kuadrupol merkezleme düzeneği için*

Bu yazı, elinizdeki dönen bobin ölçüm aletini herhangi bir ön bilgi gerektirmeden anlatır. Önce aletin ne yaptığını, sonra yazılımın ölçümü nasıl hesapladığını, sonra hangi hataların giderildiğini ve hangilerinin hâlâ açık olduğunu, en sonda da lab'da neleri deneyeceğinizi bulacaksınız.

**Önemli not:** Yazıdaki hata büyüklükleri **bilgisayar simülasyonundan** gelir. Simülasyon, gerçek aletin davranışını elimizden geldiğince taklit eder ama gerçek aletin kendisi değildir. Gerçek değerleri lab'da ölçeceğiz.

---

## İçindekiler

0. [Beş dakikalık özet](#0-beş-dakikalık-özet)
1. [Ne ölçüyoruz ve neden](#1-ne-ölçüyoruz-ve-neden)
2. [Alet: parçalar ve verinin yolu](#2-alet-parçalar-ve-verinin-yolu)
3. [Yazılım ölçümü nasıl hesaplıyor](#3-yazılım-ölçümü-nasıl-hesaplıyor)
4. [Bir hata ne zaman tehlikelidir](#4-bir-hata-ne-zaman-tehlikelidir)
5. [Giderilen hatalar](#5-giderilen-hatalar)
6. [Hâlâ açık olan hatalar ve zayıf yanlar](#6-hâlâ-açık-olan-hatalar-ve-zayıf-yanlar)
7. [Lab'da neleri deneyeceksiniz](#7-labda-neleri-deneyeceksiniz)
8. [Sonraki adımlar](#8-sonraki-adımlar)
9. [Sözlük](#9-sözlük)

---

## 0. Beş dakikalık özet

- **Alet ne yapıyor?** Mıknatısın içinde küçük bir tel bobini döndürüyor. Dönerken bobinde oluşan gerilimden mıknatısın manyetik alanını çıkarıyor. Bizim için en önemli sonuç, mıknatısın **merkezinin ölçüm eksenine göre nerede olduğu**.
- **Merkez nasıl bulunuyor?** Kuadrupol mıknatısın alanı tam merkezde sıfırdır. Merkez kaçıksa ölçüm ekseninde küçük bir "sahte düzgün alan" (dipol) görürüz. Bu sahte alanın büyüklüğü kaçıklığı söyler.
- **Neden zor?** Aradığımız sinyal, ana sinyalden yaklaşık **40 bin kat küçük**. Ana sinyalde yüz binde birkaçlık bir bozulma bile yanlış merkez gösterir. 1 µm hata için bile bu geçerli.
- **Ne yaptık?** Hesap yöntemini, bu bozulmaların büyük kısmını yok edecek şekilde değiştirdik: hız dalgalanması, zaman gecikmesi, enkoderin basamaklı çalışması, örnek kaybı gibi.
- **Ne kaldı?** En önemli açık konu **enkoderin her turda tekrarlanan küçük açı hatası**: her 1 açı dakikası (derecenin 60'ta biri) merkezde yaklaşık **6 µm** sahte kayma yapar. Bunu yazılım şimdilik göremiyor. Dik iki bobinle lab'da ölçülebilir (bölüm 6.1).
- **Lab'da ilk iş:** gecikmeyi ölçmek, iki bobinin merkezini karşılaştırmak, aynı alanı farklı hızlarda ölçmek (bölüm 7).

---

## 1. Ne ölçüyoruz ve neden

### 1.1 Dönen bobin nasıl çalışır

Mıknatısın deliğinde, dönme eksenine paralel duran bir tel çerçeve (bobin) düşünün. Bobin dönerken içinden geçen manyetik alan (buna **akı** denir) sürekli değişir. Faraday yasasına göre akı değiştiği anda bobinin uçlarında gerilim oluşur: akı ne kadar hızlı değişirse gerilim o kadar büyüktür.

Bir tur boyunca bobin deliğin her yönünü "gezmiş" olur. Gerilimin tur boyunca nasıl değiştiğine bakarak alanın deliğin içinde nasıl dağıldığını anlarız.

### 1.2 Alanın parçaları: dipol, kuadrupol, ...

Bir mıknatısın alanı tek parça değildir; birkaç basit alanın toplamı gibi düşünülebilir. Bu parçalara **çok kutup bileşenleri** denir ve **n** numarasıyla anılır:

| n | Adı | Nasıl bir alan? |
|---|---|---|
| 1 | dipol | Her yerde aynı yönde, aynı büyüklükte (düzgün alan) |
| 2 | kuadrupol | Merkezde sıfır, merkezden uzaklaştıkça artar |
| 3 | sekstupol | Merkezden uzaklaştıkça daha hızlı artar |
| 4, 5, 6 | oktupol, dekapol, ... | Daha da yüksek mertebeler |

Her bileşenin iki hâli vardır: **normal** ve **skew** (90/n derece çevrilmiş hâli). Pencerede ve dosyalarda bunlar `b` ve `a` harfleriyle gösterilir. `b0, a0` dipolü; `b1, a1` kuadrupolü anlatır. Hepsi Tesla biriminde, 25 mm yarıçapında verilir.

### 1.3 Merkez nasıl bulunur

Bizim mıknatıs bir **kuadrupol**: asıl işi, merkezden uzaklaştıkça artan bir alan üretmek. İdeal kuadrupolün alanı tam merkezinde sıfırdır.

Ama ölçüm eksenimiz (bobinin döndüğü eksen) mıknatısın merkezinde olmayabilir. Eksen merkezden biraz kaçıksa, eksen üzerinde alan sıfır değildir; küçük bir düzgün alan (dipol) görürüz. Kuadrupol alanı "kaydırılınca" dipol gibi görünür. Bu dipolün büyüklüğü, kaçıklığın büyüklüğüyle doğru orantılıdır:

> **Merkez kaçıklığı = −25 mm × (dipol büyüklüğü) / (kuadrupol büyüklüğü)**

Yani yalnızca iki sayıyı doğru ölçmemiz yetiyor: C₁ (dipol) ve C₂ (kuadrupol).

Merkezleme programı mıknatısı hiç hareket ettirmez. Dört bobinin akımlarını çok küçük farklarla değiştirerek dipolü sıfırlar. Ölçüm sisteminin görevi, bu dipolü ve kuadrupolü doğru ölçmek.

### 1.4 Aradığımız sinyal ne kadar küçük?

Bu bölüm, bu işin neden bu kadar titiz olması gerektiğini anlatıyor.

- Ana sinyal (kuadrupol): yaklaşık **5,5 mV**.
- 1 µm merkez kaçıklığına karşılık gelen sinyal (dipol): yaklaşık **0,14 µV**.

Aradaki oran yaklaşık **40 bin**. Yani merkezi 1 µm doğrulukla bilmek için, 5,5 mV'luk ana sinyalin yaklaşık **yüz binde 2,5'ine** kadar doğru olmamız gerekir. Ana sinyal herhangi bir şekilde bu oranda bozulursa ve bozulma dipole karışırsa, merkezi 1 µm yanlış buluruz.

Bu yüzden yazının büyük bölümü, **büyük kuadrupol sinyalinin küçük dipol sinyaline karışması** üzerine. Bu karışmanın başka yolları da var: hız dalgalanması, zamanlama kayması, enkoderin hatası.

---

## 2. Alet: parçalar ve verinin yolu

### 2.1 Şema

```
 DÖNEN KISIM                                          SABİT KISIM
 ─────────────────────────────────────────         ──────────────────────────────
  Düz bobin 1 ─┐
               ├─► ADC (sayısallaştırıcı) ─► Rotor kartı ◄─ RS485 ─► Stator kartı ◄─ Enkoder
  Düz bobin 2 ─┘      7200 ölçüm/saniye       (her ölçüme               │            (milin açısı)
                                               son açıyı ekler)         │
                                                                        ├─► Motor sürücüsü
                                                                        │
                                                                        └─► Ethernet ─► Bilgisayar
```

**Dönen bobinler ve ADC:** İki düz bobin ve sinyalleri sayıya çeviren ADC, milin üzerindeki **dönen kartta** durur. Mikrovolt düzeyindeki sinyal kabloyla sabit kısma taşınmaz; orada sayıya çevrilir ve yalnızca sayılar sabit kısma gönderilir. Bu iyi bir tasarım, çünkü çok küçük analog sinyal, dönen-sabit geçişinde kolayca gürültüye bulanırdı.

**Rotor kartı:** ADC bir ölçüm hazırladığında (saniyede 7200 kez) rotor kartı o ölçümün yanına **o ana kadar gelen son açı değerini** ekler ve pakete RS485 hattıyla sabit kısma yollar.

**Stator kartı:** Sabit kısımdaki karttır. Üç işi var:
1. **Enkoderi okur** (mil açısını ölçen sensör) ve yaklaşık her milisaniyede bir bu açıyı dönen karta bildirir.
2. **Motoru sürer** ve hızı ayarlar.
3. Gelen ölçüm paketlerini **Ethernet'le bilgisayara** iletir.

**Bilgisayar:** paketleri bir tampona yazar (yaklaşık 2 dakikalık veri tutar). Ölçüm programı bu tampondan zaman pencereleri alıp analiz eder.

### 2.2 Bobinlerimiz

- **İki düz bobin**, birbirine **dik**. Dönen düzlemde birbirinden 90° farklı dururlar.
- Her biri: **5 sarım**, **100 mm × 20 mm**, ortası eksenden **20 mm** uzakta.
- Bobin 1: AIN0–AIN1. Bobin 2: AIN4–AIN5.

Bir bobinin her çok kutba duyarlılığı farklıdır; bobinin geometrisi belirler. Bizim bobinde şöyle:

| n | 1 | 2 | 3 | 4 | 5 | 6 | 7 |
|---|---|---|---|---|---|---|---|
| Göreli duyarlılık | 20 | 32 | 35 | 31 | 21 | 9 | 2,4 |

Yani bobin en iyi n = 2–4 arasını görüyor; **n = 6'yı zor, n = 7'yi neredeyse hiç göremiyor**. Bu, bobinin geometrisinin değişmez bir sonucu, yazılımla düzeltilemez.

### 2.3 Enkoder ve "sıfır açı" sorunu

Enkoder **artımlı** türdendir: milin ne kadar döndüğünü sayar ama milin şu an hangi açıda olduğunu bilmez. Aletin açılışında sayaç sıfırlanır; yani "sıfır derece", o an milin durduğu yerdir. Her açılışta bu yer farklıdır.

Bu yüzden her açılışta **referans mıknatıs** ile "sıfır"ı belirlememiz gerekir (bölüm 3.4).

Enkoderin çözünürlüğü yaklaşık 0,1° (tur başına 3600 sayım). Bu tek başına sorun değil; simülasyonda merkeze etkisi yaklaşık 0,06 µm.

### 2.4 ADC

Sinyali sayıya çeviren ADC (ADS1263) şöyle ayarlı:
- **Kazanç 32:** küçük sinyali 32 kat büyütür. Ölçebildiği en büyük gerilim ±78 mV. Sinyal bunun %80'ine ulaşırsa program "doyma uyarısı" verir.
- **Saniyede 7200 ölçüm**, **Sinc4 filtre** (gürültüyü azaltan sayısal süzgeç).

Bu süzgeç, her ölçümü birkaç yüz mikrosaniye **geçmişe** kaydırır. Bu, bölüm 5.2'deki "gecikme" sorununun bir parçası.

---

## 3. Yazılım ölçümü nasıl hesaplıyor

### 3.1 Hangi programlar var

| Program | Ne işe yarar |
|---|---|
| `host/radarMGF.py` | İrfan'ın büyük arayüzü: 9 sekme, her türlü ölçüm ve geliştirme işi. |
| `host/merkezleme_olcer.py` | Merkezleme için sadeleştirilmiş tek pencere. Bu yazıdaki analiz bunda. |
| `python -m merkezleme` | Akımları ayarlayan merkezleme programı. Ölçümleri bir dosya aracılığıyla alır. |

Ölçüm penceresi ile merkezleme programı **bir kilit dosyası** üzerinden konuşur, trafik ışığı gibi:
1. Merkezleme akımları değiştirir ve kilit dosyasını siler. Bu "ölç" demektir.
2. Ölçüm programı, kilit silindikten **sonra** gelen veriyi kullanarak ölçer ve sonucu dosyaya yazar. Bu "veri hazır" demektir.
3. Merkezleme dosyayı okur, yeni akımları ayarlar ve kilidi tekrar siler.

Kilit silinmeden önceki veri kullanılmaz; çünkü akımlar o sırada değişiyor olabilir.

### 3.2 Bir ölçümün adımları

Her ölçüm, son 2 saniyenin verisini (yaklaşık 46 tur) kullanır. Süre pencereden ayarlanabilir.

1. **Açıyı düzelt.** Enkoder açıyı yaklaşık 1 ms'de bir güncelliyor, ama ADC saniyede 7200 ölçüm yapıyor. Bu yüzden her yeni açı değeri yaklaşık 7 ölçümde aynı kalıyor ("merdiven"). Program, açıların aslında ne zaman okunduğunu hesaplayıp aradaki açıları pürüzsüz bir eğriyle tahmin eder (bölüm 5.3).
2. **Gecikmeyi uygula.** Her ölçüm, yanındaki açıdan biraz eskidir. Program açıyı bu kadar geriye çeker (bölüm 5.2).
3. **Akıyı bul.** Gerilimleri zaman içinde toplayarak akıyı hesaplar. (Bölüm 5.1: bu adım, hız dalgalanmasına karşı en büyük korumamız.)
4. **Tam turlara kırp.** Pencereyi tam tur sayısına kısaltır.
5. **Şekil uydur.** Akının açıya göre eğrisine, birkaç sinüs dalgasının toplamı (bu dalgalar n = 1, 2, ... bileşenleridir) en iyi uyacak şekilde uydurulur. Ayrıca ADC'nin yavaş kaymasını gidermek için yavaş değişen bir terim de eklenir.
6. **Tesla'ya çevir.** Her bileşenin büyüklüğü, bobinin o bileşene duyarlılığına bölünür. Böylece sonuç gerçek alan olarak çıkar.
7. **Merkezi hesapla.** Dipol ve kuadrupol büyüklüğünden merkez bulunur.
8. **Sağlık kontrolü.** Bir şey ters gittiyse ölçüm merkezleme'ye **gönderilmez**:
   - Uydurma, veriyi iyi açıklayamıyorsa (artık yüksek).
   - Veride örnek kaybı belirtisi varsa (saat sıçraması yüksek).

### 3.3 Pencerede ne görüyorsunuz

- **Durum kutusu:** hız, yazılan ölçüm sayısı, faz ofseti, sinyal tepesi, gecikme, sağlık göstergesi ("Artık / saat sıçr."), uyarılar.
- **Son ölçüm:** b0, a0 (dipol), b1, a1 (kuadrupol), gradyen, merkez x_c ve y_c.
- **Çok kutuplar grafiği:** son 20 ölçümün ortalaması, logaritmik ölçekle. Hata çubuğu çubuktan uzunsa o bileşen gürültünün içinde kaybolmuş demektir.
- **Bobin akısı grafiği:** son pencerenin akısı, bütün turlar üst üste. Üzerindeki çizgi uydurma. Noktalar çizgiye oturmalı.
- **Günlük:** her olay, her uyarı.

### 3.4 Referans mıknatıs

Enkoderin sıfırı her açılışta değiştiği için, programın "x yönü" ile gerçek x yönü arasındaki açı bilinmez. Bunu belirlemek için **alanı düşey olan bir referans mıknatısı** takılır ve "Referans mıknatısla sıfırla"ya basılır. Program, bu mıknatısın alanı "tam normal, pozitif" görünecek şekilde bir açı düzeltmesi (faz ofseti) bulur.

Dikkat edilecekler:
- **Her bobin için ayrı yapılmalı.** İki bobin birbirine 90° farklı durur. Birinin düzeltmesini öbürüne uygularsanız merkez 90° dönük çıkar. Program artık düzeltmeyi bobin başına tutuyor ve referansı alınmamış bobinde uyarıyor.
- **Bu işlem yalnızca yönü belirler.** Merkezleme'nin sıfıra yakınsamasını etkilemez.
- **Mıknatıs yoksa ya da sinyal zayıfsa** program düzeltmeyi değiştirmez ve nedenini yazar.

### 3.5 Gecikme ölçümü

"Gecikme ölç (iki yön)" düğmesi (yalnızca "Merkezleme'ye yaz" kapalıyken çalışır):
1. Bu yönde bir pencere alır.
2. Motoru ters yöne çevirir.
3. Öbür yönde bir pencere alır.

İki yön arasındaki farktan gecikme bulunur (neden bölüm 5.2'de). Program sonucu günlüğe yazar. Kalıcı olması için `merkezleme_olcer.yaml` içindeki `olcum.gecikme_ms` değerine elle yazılır. Donanım ve ADC ayarları değişmedikçe bu değer sabit kalır. Sinyal çok zayıfsa sonuç kullanılmaz.

---

## 4. Bir hata ne zaman tehlikelidir

Merkezleme programı çalışmaya başlarken önce **bir test yapar**: akımlara küçük değişiklikler uygular ve ölçülen dipolün nasıl değiştiğine bakar. Böylece ölçüm ile akım arasındaki ilişkiyi kendisi öğrenir. Sonra dipolü sıfıra götürmeye çalışır.

Bu çalışma tarzı yüzünden hatalar üç gruba ayrılır:

**A. Ölçek hataları — zararsız.**
Ölçülen her şeyi aynı oranda büyüten ya da küçülten hatalar (bobin duyarlılığındaki hata, elektronik kazanç hatası). Merkezleme bunları kendi testinde zaten öğrenir. "Sıfır" her çarpanla yine sıfırdır. Yalnızca raporlanan µm sayıları kayar; varılan nokta doğru kalır.

**B. Sahte merkez hataları — tehlikeli.**
Mıknatısın merkezi gerçekte tam yerindeyken, ölçümde sahte bir dipol gösteren hatalar. Merkezleme bu sahte dipolü sıfırlamaya çalışır ve mıknatısı **gerçekten yanlış bir noktaya** götürür. Hiçbir tekrar bunu düzeltmez; çünkü ölçüm sistemi sıfırı "doğru" görür. Çoğu, bölüm 1.4'teki "büyük sinyalin küçük sinyale karışması" türündendir. **Yazıdaki en önemli hatalar bu grupta.**

**C. Rastgele hatalar — tekrar ve ortalamayla azalır.**
Gürültü, zamanlama titreşimi. Ölçüm süresini uzatınca ya da ortalama alınca azalır. Bir yöne sistematik kayma yapmaz.

**Bir kural:** Merkezleme çalışırken ölçüm koşulları (bobin, faz düzeltmesi, gecikme, dönüş yönü, hız) değişirse, merkezleme'nin öğrendikleri geçersiz olur. Bu yüzden "Merkezleme'ye yaz" açıkken bu ayarlar **kilitlidir**.

---

## 5. Giderilen hatalar

Her başlıkta aynı sıra: **ne oluyordu → neden kötüydü → ne yaptık → ne kadar iyileşti**. Sayıların hepsi simülasyondandır. Tüm simülasyonlarda gerçek merkez 152 µm kaçık alınmıştır.

### 5.1 Motor hızının tur içinde dalgalanması (B grubu)

**Ne oluyor:** Motor her turda mükemmel sabit hızla dönmez. Bobin gerilimi, bobinin **o anki hızıyla** orantılıdır. Hız küçük bir miktar artıp azalırsa, gerilim de aynı oranda artıp azalır.

**Neden kötüydü:** Eski yöntem gerilime bakıp "hız sabit" varsayıyordu. Hız dalgalanınca, ana sinyal (kuadrupol) bozulur; bu bozulma dipole karışır ve sahte merkez kayması çıkar.

> **Benzetme:** Bir arabanın katettiği yolu, hız göstergesine bakarak tahmin etmeye çalışın. Hız göstergesi sürekli oynuyorsa tahmininiz bozulur. Oysa **kilometre sayacına** baksanız, hızın nasıl oynadığının önemi olmaz. Gerilim "hız göstergesi" gibidir (akının ne kadar hızlı değiştiğini söyler); **akı** ise "kilometre sayacı" gibidir (yalnızca bobinin nerede olduğuna bağlıdır).

**Ne yaptık:** Gerilimi zaman içinde toplayarak (integral) akıyı hesapladık. Artık hız hiç kullanılmıyor. (Dönen bobin sistemlerinde bu işlem genellikle **donanımla**, bir integratör devresiyle yapılır; biz aynı işi yazılımla yapıyoruz. Bunun çalışması için ADC ölçümlerinin düzgün aralıklarla ve hiç kayıpsız gelmesi şart; bkz. 5.6.)

**Sonuç (merkez hatası):**

| Hız dalgalanması (açı olarak) | Eski yöntem | Yeni yöntem |
|---|---|---|
| 0,25° | 88 µm | 0,04 µm |
| 0,5° | 177 µm | 0,04 µm |
| 2° | 733 µm | 0,10 µm |

### 5.2 Gerilim ile açı arasındaki zaman farkı (B grubu)

**Ne oluyor:** İki şey ölçümü geciktirir:
- ADC'nin süzgeci, her ölçümü birkaç yüz mikrosaniye eskiden gösterir.
- Enkoderin açısı da statordan dönen karta ulaşana kadar zaman geçer.

Sonuç: her gerilim değerinin yanındaki açı etiketi, gerçekte o anki açı değildir. Aradaki fark **L**; simülasyonda 0,18 ms. (Gerçek değeri lab'da ölçeceğiz.)

> **Benzetme:** Bir koşucuyu fotoğraflıyorsunuz ama fotoğraf makinesinin saati, kronometreden biraz geride. Her fotoğrafın üzerindeki "süre" etiketi biraz yanlış.

**Neden kötüydü:**
- **Motor sabit hızla dönerken zararsız:** etiket hep aynı miktarda yanlış; bu sabit bir açı kayması olur, referans mıknatıs bunu zaten yutar.
- **Hız dalgalanırken zararlı:** kayma dalgalanır ve bölüm 5.1'deki gibi sahte merkez kayması çıkar. 0,5° dalgalanmada 4,5 µm, 2°'de 19 µm.
- **Dönüş yönü değişince zararlı:** kayma yön değiştirir. Referansı bir yönde alıp ölçümü ters yönde yaparsanız yaklaşık 8 µm hata çıkar.

**Ne yaptık:** Gecikmeyi **iki yönlü ölçümle** buluyoruz. Motor ileri dönerken gecikme açıyı bir tarafa, geri dönerken öbür tarafa kaydırır. İki yönde ölçülen farkın yarısı gecikmeyi verir. Bulunan gecikmeyle her ölçüm zamanda geri çekilir (açı etiketi düzeltilir).

**Sonuç:** Simülasyonda gerçek gecikme 0,1800 ms; ölçülen 0,1798 ms. Düzeltmeden sonra merkez hatası 0,04–0,10 µm.

**Dikkat:** Milin burulması ya da kaplindeki boşluk gibi **yöne bağlı sabit açı farkları** da bu ölçüme karışır ve aynı yöntemle giderilir. Ama onlar zaman değil açı olduğu için, bulunan değer yalnızca **ölçüldüğü hızda** doğrudur. Hız değiştirirseniz gecikmeyi tekrar ölçün.

### 5.3 Enkoderin basamaklı çalışması (B grubu)

**Ne oluyor:** Enkoder açısı yaklaşık 1 ms'de bir güncelleniyor, ADC ise 7200 kez/s ölçüyor. Yani her açı değeri yaklaşık 7 ölçümde aynı kalıyor; 23 Hz'de açı gerçekte 8°'ye kadar ilerlemiş olabiliyor.

> **Benzetme:** Her dakika bir kez güncellenen bir saatle saniye ölçmek. Aradaki saniyeleri tahmin etmeniz gerekir.

**Neden kötüydü:** Basamaklı açı, uydurmadaki sinüs dalgalarını bozar. Özellikle yüksek mertebeleri (n = 4, 5, 6) bozar. Simülasyonda merkezde 2,4 µm hata, n = 2'nin büyüklüğünde yüzde 0,25 hata.

**Ne yaptık:** Enkoder okumaları, stator kartının saatine bağlı olduğundan düzenli aralıklarla gelir. Program, her yeni açı değerinin geldiği ilk ölçümü bulur ve bunlara düzgün bir "okuma saati" uydurur. Böylece her açı okumasının tam olarak ne zaman yapıldığı, ölçüm aralığından çok daha ince bir hassasiyetle bilinir. Sonra açıyı bu anlar arasında pürüzsüz bir eğriyle (kübik eğri) doldurur.

**Sonuç:** Merkez hatası 2,4 µm → 0,04 µm. n = 6'daki bozulma 4,2 birimden 0,1 birime iner (1 birim = kuadrupolün on binde biri).

### 5.4 Toplama yönteminin küçük kazanç kaybı (A grubu)

Gerilimi örnek örnek toplayarak akı bulmak, hızlı değişen bileşenleri çok küçük bir oranda eksik gösterir (n = 2'de on binde 1,3; n = 6'da binde 1,2). Kesin formülü bilindiği için hesaba katılıyor. Kalan hata milyonda bir mertebesi.

### 5.5 Ters dönüşte işaret hatası (A grubu)

Eski kod hızın mutlak değerini kullanıyordu. Motor ters dönünce, bütün sonuçların işareti ters çıkıyordu. Akı yönteminde hız kullanılmadığı için dönüş yönü sonucu etkilemiyor.

### 5.6 Kayıp ölçümler (B grubu; tespit ediliyor, onarılamıyor)

**Ne oluyor:** Ölçüm paketleri yolda kaybolabilir. Firmware ölçümlere sıra numarası koymuyor:
- Stator kartı, bozuk gelen ölçümü sessizce atıyor; yalnızca bir sayaç artıyor.
- Bilgisayar tarafında tampon dolarsa paket düşüyor.

**Neden kötü:** Akı hesabı, ölçümlerin eşit aralıklarla ve eksiksiz geldiğini varsayar. Tek bir kayıp ölçüm bile akıda bir basamak yaratır; simülasyonda 4–8 µm merkez hatası.

**Ne yaptık:** Kayıp ölçümü geri getiremeyiz ama **fark edebiliriz.** Enkoder okumaları düzenli aralıklarla geldiği için, bir ADC ölçümü kaybolduğunda sonraki bütün açı okumaları bir ölçüm erken görünür. Program bu kaymayı ölçer:
- Sağlıklı veride yaklaşık 0,2
- Tek kayıpta yaklaşık 1
- Eşik 0,6

Eşik aşılırsa ölçüm **merkezleme'ye yazılmaz.** Üst üste 3 kez olursa motor durdurulur. Ayrıca stator kartının "bozuk ölçüm attım" sayacı artarsa günlüğe uyarı düşer.

### 5.7 Diğer korumalar

- **Çerçeve kilidi:** Merkezleme'ye yazarken bobin, hız, referans, gecikme ve dönüş yönü değiştirilemez.
- **Bağlantı koparsa:** Firmware, bağlantı kopunca motoru durdurmuyor. Program yeniden bağlanınca önce motoru durdurur, motor durunca servoyu kapatır.
- **Zayıf sinyal:** Gecikme ve referans ölçümleri, ancak yeterince kesinlerse kullanılır. Mıknatıs takılı değilken yanlışlıkla basılırsa değer değiştirilmez.
- **Mıknatıs modülasyonu:** Mıknatısın 1 kHz'de %1 modülasyonu açıkken uydurma artığı yaklaşık 6,6·10⁻³ çıkıyor ama merkez etkilenmiyor (0,05 µm). Artık eşiğini buna göre 2·10⁻²'ye ayarladık.

---

## 6. Hâlâ açık olan hatalar ve zayıf yanlar

Önem sırasına göre. Her biri için: ne olduğu, ne kadar kötü olabileceği, nasıl anlaşılacağı, ne yapılabileceği.

### 6.1 Enkoderin her turda tekrarlanan açı hatası — en önemli açık konu (B grubu)

**Ne oluyor:** Enkoder diski mile tam ortalı değilse ya da enkoder ile bobin mili arasındaki bağlantı (kaplin) her turda biraz oynuyorsa, okunan açı gerçek açıdan **tur başına bir kez** küçük miktarda sapar. Ucuz enkoderlerde ve kaplinli düzeneklerde birkaç açı dakikası görmek olağandır.

**Neden kötü:** Açı yanlışsa kuadrupol sinyali dipole karışır. Simülasyonda:

> **Sahte merkez kayması = bobinin eksene uzaklığı (20 mm) × açı hatası**
>
> - 1 açı dakikası → **5,8 µm**
> - 5 açı dakikası → **29 µm**

Bu hata dönüş yönünden bağımsızdır; iki yönlü ölçüm onu **gidermez.** Merkezleme mıknatısı bu kadar yanlış bir noktaya götürür ve bunu fark edemez.

(Tur başına iki kez tekrarlanan açı hataları önemsiz: 1 açı dakikasında 0,05 µm.)

**Nasıl anlaşılır:** İki bobin birbirine 90° dönük olduğu için bu hatayı **farklı** gösterir. Simülasyonda bobin 1'in sahte kayması bir değerse, bobin 2'ninki aynı değerin 90° döndürülmüşüdür. Yani:

> Mıknatıs aynı yerde dururken, bobin 1 ve bobin 2 **farklı merkez** gösteriyorsa, büyük olasılıkla bu hata vardır.

(Bu karşılaştırma için her bobinin referansı ayrı alınmış olmalı; bu artık programda var.)

**Ne yapılabilir:** İki bobinden gelen fark, hem hatayı hem gerçek merkezi çözmeye yetiyor. Yazılıma bir **kalibrasyon** eklenebilir: iki bobinle ölçüm yapar, sahte kaymayı bulur, kalıcı olarak düzeltir. Bu, mevcut donanımla yapılabilir. Lab'da önce farkın gerçekten var olup olmadığına bakalım (bölüm 7, test 5).

### 6.2 Dönme ekseninin oynaması ve titreşim (B ve C grubu)

**Ne oluyor:** Ölçülen merkez, **bobinin döndüğü eksene göre.** Eksen titrerse ya da yatakta oynarsa, bunu mıknatısın merkezi kaymış gibi görürüz.
- Rastgele titreşim: gürültü ekler (C grubu).
- Dönmeyle aynı ritimde bir sallanma (mil her turda yalpalıyorsa): sistematik karışma yapabilir (B grubu).

**Neden önemli:** Büyük laboratuvarlardaki dönen bobin sistemlerinde bunun için **kompanzasyon (bucking)** kullanılması yaygındır: birden çok bobin, ana sinyali birbirini yok edecek şekilde bağlanır, böylece titreşimin ana sinyal üzerinden yarattığı karışma büyük ölçüde iptal olur. Bizde bucking yok; iki bobin ayrı ayrı okunuyor.

**Nasıl anlaşılır:** Mıknatısın manyetik alanı motor hızından bağımsızdır; mekanik titreşim etkileri ise genellikle hıza bağlıdır. Aynı alanı 10, 15 ve 23 Hz'de ölçün. Sonuç hızla değişiyorsa mekanik bir etki var demektir.

**Ne yapılabilir:** Önce ölçmek. Gerekirse mekanik iyileştirme (yatak, kaplin) ya da bucking bobini.

### 6.3 Milin yerçekimiyle sarkması (B grubu; hedefe bağlı)

Uzun bir mil ortasında yerçekimiyle biraz sarkar. Ölçülen merkez, **sarkmış eksene** göredir. Sarkma dönüş yönüne bağlı değil; iki yönlü ölçüm bunu gidermez.

Bunun "hata" olup olmadığı, hedef eksenin nasıl tanımlandığına bağlı. Işın ekseni başka bir yolla (örneğin lazer izleyici) belirleniyorsa, sarkma bir ofset olarak hesaba katılmalı.

### 6.4 Çevredeki manyetik alan (B grubu; kısmen çözülmüş)

Dünya'nın manyetik alanı (yaklaşık 50 µT) ve laboratuvardaki başıboş alanlar sistemde dipol gibi görünür. Mıknatısımız **demirsiz** olduğu için bunları perdelemez. 50 µT'lık bir dipol, bizim kuadrupolde merkezi yaklaşık **0,5 mm** kaydırır.

Merkezleme programı, mıknatıs kapalıyken bir "arka plan ölçümü" alıp çıkarıyor. Ama arka plan ölçümler arasında değişirse (yakına demirli bir şey taşınırsa, kapı ya da vinç hareket ederse, komşu mıknatıs açılıp kapanırsa) çıkarma yetersiz kalır. Arka plan ölçümünü sık tekrarlayın ve ortamı sabit tutun.

### 6.5 Enkoderin okuma zamanındaki titreşim (C grubu)

Stator kartı enkoderi ana döngüsünde okuyor; bu döngü Ethernet gibi işlerle zaman zaman biraz gecikebilir. Okuma anı düzenli saatten birkaç on mikrosaniye sapabilir. Program okumaları düzenli saatle geldi varsayarak yerleştirdiği için, bu sapma küçük bir açı hatasına dönüşür.

| Okuma titreşimi | 2 s pencerede | 8 s pencerede |
|---|---|---|
| 5 µs | 1,2 µm | 0,24 µm |
| 20 µs | 4,7 µm | 1,0 µm |

Rastgele olduğu için ölçüm süresi uzadıkça azalır. Gerçek titreşim düzeyi **bilinmiyor**; lab'da tekrarlanabilirlikten anlaşılır.

**Kalıcı çözüm (firmware):** enkoder okumasına zaman damgası eklemek ya da açıyı dönen kartta ölçüm anına enterpole etmek.

### 6.6 Bobinin geometrisi (A grubu, ama mutlak değeri etkiler)

- **Duyarlılık hatası:** Sarım sayısı, genişlik, eksene uzaklık gibi değerlerde küçük bir hata, raporlanan µm sayılarını ölçekler. Merkezleme'nin sıfıra yakınsamasını bozmaz. Mutlak doğruluk için **bilinen gradyenli bir mıknatıs** ve **bilinen bir mekanik kaydırma** ile kalibrasyon gerekir.
- **Üç boyutlu etkiler:** Bobin 100 mm boyunca **ortalama** alanı ölçer. Mıknatısın uç alanları ya da eğikliği varsa ölçülen merkez bu uzunluk boyunca bir ortalamadır.

### 6.7 ADC ve elektronik

- **Doyma:** Sinyal ADC'nin ölçebileceğinin %80'ini geçerse program uyarır. Bu durumda kazancı düşürün.
- **Gürültü:** Simülasyonda 1 µV gürültü, merkezde yaklaşık 0,2 µm (2 saniyelik ölçümde). Daha uzun ölçümle azalır.
- **Süzgecin yüksek mertebeleri biraz küçültmesi:** n = 6'da yaklaşık binde birkaç. Düzeltilmedi; merkezi etkilemez (0,03 µm).
- **Şebeke ve motor sürücüsü paraziti:** Dönmeyle aynı ritimde olmayan parazit uydurma tarafından "bileşen" sayılmaz ve yalnızca artığa girer. Dönmeyle ilişkiliyse (sürücü akımı dönme açısına bağlıysa) sahte bir harmonik gibi görünebilir. Motor kapalıyken ve farklı hızlarda karşılaştırarak anlaşılabilir.

### 6.8 Firmware'den gelen sınırlar

| Sınır | Sonuç | Öneri |
|---|---|---|
| Ölçümlerde sıra numarası yok | Kayıp tespit edilir ama ölçüm kaybolur | Dönen kartta ölçüm sayacı |
| Enkoder ~1 ms'de bir güncelleniyor, arası boş | Merdiven (yazılımla telafi) ve okuma titreşimi | Zaman damgası ya da dönen kartta enterpolasyon |
| Bağlantı kopunca motor durmuyor | PC yeniden bağlanınca durduruyor | Firmware'de bağlantı bekçisi (kopunca rampalı durma) |
| Enkoder artımlı, indeks darbesi yok | Her açılışta referans gerekir | İndeksli ya da mutlak enkoder |

### 6.9 Mıknatıs tarafı (tahminler, ölçülmedi)

- Demirsiz mıknatısta histerezis (geçmişe bağlı alan) yok; alan doğrudan akımla orantılı.
- Uzun çalışmada bobinler ısınır, mekanik genleşme merkezi yavaşça kaydırabilir. Merkez zamanla sürekli bir yöne gidiyorsa ısıl etkiyi düşünün.
- Güç kaynağındaki akım gürültüsü alan gürültüsüne dönüşür.

---

## 7. Lab'da neleri deneyeceksiniz

Her test belirli bir hatayı ortaya çıkarmak için tasarlandı.

| # | Test | Neyi gösterir |
|---|---|---|
| 1 | Sürekli ölçüm; 2 s ve 8 s pencereyle merkez saçılımına bakın | Rastgele hatalar (6.5, 6.7). 8 s'de saçılım yaklaşık yarıya inmeli. |
| 2 | "Gecikme ölç" düğmesini 2–3 kez | Gecikmenin değeri ve tutarlılığı (birkaç µs içinde aynı çıkmalı). Sonucu yaml dosyasına yazın. |
| 3 | Gecikme ayarlıyken +23 ve −23 Hz'de aynı alan | Yöne bağlı kalan etkiler. İki yönde aynı sonuç çıkmalı. |
| 4 | Aynı alanı 10, 15 ve 23 Hz'de ölçün | Mekanik etkiler (6.2). Manyetik sonuç hızdan bağımsız olmalı. |
| 5 | **Mıknatıs aynı yerdeyken bobin 1 ve bobin 2'yi karşılaştırın** (her biri kendi referansıyla) | Enkoder açı hatası (6.1). İkisi aynı merkezi göstermeli; göstermiyorsa kalibrasyon gerekir. |
| 6 | Mıknatısı bilinen miktarda +x yönünde, sonra +y yönünde kaydırın | İşaret, yön ve merkez ölçeği (6.6). Okunan değişim beklenenle uyuşmalı. |
| 7 | Gradyeni bilinen mıknatısla karşılaştırma | Mutlak ölçek. |
| 8 | Referans mıknatıs: b0 pozitif, a0 sıfıra yakın çıkmalı | Referansın doğru çalıştığı. Her iki bobin için ayrı yapın. |
| 9 | Mıknatıs kapalı, motor dönüyor | Çevre alanı ve parazit düzeyi (6.4, 6.7). |
| 10 | Mıknatıs modülasyonu açık ve kapalı | Artığın ~6·10⁻³'e çıkıp merkezin değişmediği. |
| 11 | Saatlerce süren ölçüm | Isıl ve mekanik sürüklenme (6.9). |
| 12 | Pencerede "Artık / saat sıçr." değerleri ve günlükteki RS485 uyarıları | Sağlıklı düzeyler, eşiklerin uygunluğu, kayıp sıklığı. |

---

## 8. Sonraki adımlar

Öncelik sırasıyla:

**Yazılım (mevcut donanımla):**
1. **İki bobinli enkoder kalibrasyonu** (6.1): en önemli açık hatayı ölçüp düzeltir.
2. **Okuma titreşimi göstergesi** (6.5): titreşimi µs olarak pencerede göstermek.
3. **Hız profili göstergesi:** motorun tur içindeki gerçek hız dalgalanmasını göstermek.

**Firmware:**
4. Dönen kartta ölçüm sayacı (kayıpları kesin tespit etmek için).
5. Enkoder okumasına zaman damgası ya da dönen kartta açı enterpolasyonu.
6. Bağlantı kopunca motoru yavaşça durduran bekçi.

**Donanım:**
7. Kompanzasyon (bucking) bobini: titreşimden gelen karışmayı azaltır.
8. İndeksli ya da mutlak enkoder: her açılışta referans gereksinimini azaltır.

---

## 9. Sözlük

| Terim | Anlamı |
|---|---|
| Akı | Bobinin içinden geçen toplam manyetik alan. Gerilim, akının değişim hızıyla orantılıdır. |
| ADC | Analog sinyali (gerilimi) sayıya çeviren devre. |
| Artık (uydurma artığı) | Uydurmanın açıklayamadığı kısmın, açıklanan kısma oranı. Ölçümün sağlıklı olup olmadığını gösterir. |
| Bucking (kompanzasyon) | Ana sinyali birbirini yok edecek şekilde bağlanmış birden çok bobin. |
| Çerçeve | Ölçümün yapıldığı koşullar: bobin, faz düzeltmesi, gecikme, dönüş yönü, hız. |
| Çok kutup (C_n) | Alanın dipol (n=1), kuadrupol (n=2), ... bileşenleri. |
| Dipol | Her yerde aynı yönde ve büyüklükte düzgün alan. |
| Enkoder | Mil açısını ölçen sensör. |
| Faz ofseti | Enkoderin sıfırı ile gerçek x ekseni arasındaki açı. Referans mıknatısla bulunur. |
| Gecikme (L) | Bir gerilim ölçümünün, yanındaki açı etiketine göre ne kadar eski olduğu. |
| Kuadrupol | Merkezde sıfır, uzaklaştıkça artan alan. Bizim mıknatısın asıl alanı. |
| Merdiven | Enkoder değerinin basamaklı (aralıklı) güncellenmesi. |
| Normal / skew | Bir çok kutbun iki bileşeni; skew, normalin 90/n derece çevrilmiş hâli. |
| Okuma saati sıçraması | Kayıp ölçüm göstergesi: enkoder okumalarının beklenen düzenli ritme göre kayması. |
| Referans mıknatıs | Alanı bilinen (düşey) bir dipol mıknatıs; açı sıfırını bulmak için kullanılır. |
| RS485 | Dönen kart ile sabit kart arasındaki hızlı seri hat. |
| Sehim | Milin yerçekimiyle sarkması. |
| Tepki matrisi | Merkezleme'nin ölçtüğü, akım değişikliği ile dipol değişikliği arasındaki ilişki. |

---

*İlgili belgeler: `README_SURUM.md` (kullanım ve lab planı), `SISTEMATIK_HATALAR_RAPORU.md` (giderilen hataların sayısal ayrıntısı), depo kökündeki `README.md` (merkezleme programı).*
