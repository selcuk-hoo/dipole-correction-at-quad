# Dönen bobin ölçümü: sistematik hatalar ve düzeltmeleri

*Merkezleme ölçüm programı (`host/mgf/merkezleme_koprusu.py`, `olcum_dongusu.py`) · Ekim 2026*

Bu rapor, dönen bobinle yapılan merkez ölçümünde **hangi sistematik hataların olduğunu**, her birinin ölçümü **nasıl bozduğunu**, yazılımın bunu **nasıl düzelttiğini** ve düzeltmeden sonra **ne kadar hata kaldığını** anlatır. Düzeltilmeyen hatalar da sonda açıkça listelenmiştir.

**Sistematik hata ne demek?** Her ölçümde aynı yöne, aynı büyüklükte kayma yapan hata. Gürültü gibi rastgele değildir; ölçümü ne kadar tekrarlasanız ya da uzatsanız geçmez. Bu yüzden asıl tehlikelisi odur: ölçüm "düzgün ve tutarlı" görünür ama yanlıştır.

**Önemli uyarı:** Bu rapordaki bütün sayılar **bilgisayar simülasyonundan** gelir. Simülasyon alete elimizden geldiğince benzetildi (bölüm 2), ama gerçek aletin kendisi değildir. Gerçek donanımdaki hata düzeylerini (hız dalgalanması, zamanlama titreşimi, kayıp sıklığı gibi) lab'da ölçeceğiz (bölüm 7).

## İçindekiler

1. [Ölçümün temeli: formüller ve anlamları](#1-ölçümün-temeli-formüller-ve-anlamları)
2. [Nasıl sınadık](#2-nasıl-sınadık)
3. [Özet tablo](#3-özet-tablo)
4. [Giderilen hatalar (ayrıntı)](#4-giderilen-hatalar-ayrıntı)
5. [Geliştirme sırasında bulunan kendi hatalarımız](#5-geliştirme-sırasında-bulunan-kendi-hatalarımız)
6. [Giderilmeyen ya da kısmen giderilen etkiler](#6-giderilmeyen-ya-da-kısmen-giderilen-etkiler)
7. [Lab'da doğrulanması gerekenler](#7-labda-doğrulanması-gerekenler)

---

## 1. Ölçümün temeli: formüller ve anlamları

Hataları anlamak için önce hesabın nasıl yapıldığını bilmek gerekir. Aşağıdaki beş formül bütün hesabı özetler. Her birinin altında harflerin ne olduğu yazılı.

### 1.1 Bobinde gerilim nasıl oluşur

```
V = − dΦ/dt          (Faraday yasası)
```

- **V:** bobinin uçlarındaki gerilim (volt).
- **Φ (fi):** bobinin içinden geçen manyetik akı, yani bobin içindeki toplam alan.
- **dΦ/dt:** akının zamanla değişim hızı. Akı ne kadar hızlı değişirse gerilim o kadar büyük.

Bobin döndüğü için akı sürekli değişir. Akı, bobinin açısına (θ) bağlıdır. Bu yüzden gerilimi şöyle de yazabiliriz:

```
V = − ω · dΦ/dθ       (ω: bobinin o andaki dönüş hızı, rad/s)
```

Burası çok önemli: **gerilim, o anki hızla orantılıdır.** Hız her an biraz değişirse gerilim de değişir. Bölüm 4.1'deki en büyük hata buradan çıkıyor.

### 1.2 Akının çok kutuplardan oluşması

Bobinin içinden geçen akıyı, alanın çok kutup bileşenlerinin toplamı olarak yazabiliriz:

```
Φ(θ) = N · ℓ · Re[ Σ  Cₙ · Kₙ · e^(i·n·θ) ]          (n = 1, 2, 3, ...)
```

- **N:** bobinin sarım sayısı (5).
- **ℓ:** bobinin dönme ekseni boyunca uzunluğu (100 mm).
- **Cₙ:** alanın n. çok kutup bileşeni, Tesla biriminde, 25 mm yarıçapında (n = 1 dipol, n = 2 kuadrupol, n = 3 sekstupol, ...). Karmaşık sayıdır: gerçek kısmı **normal** (b), sanal kısmı **skew** (a) bileşendir.
- **Kₙ:** bobinin n. çok kutba **duyarlılığı**; yalnızca bobinin geometrisinden hesaplanır.
- **e^(i·n·θ):** n. bileşenin, bobin döndükçe n kat hızlı döndüğünü gösteren terim (tur başına n kez tekrarlanır).
- **Re[ ]:** karmaşık sayının gerçek kısmı.

Bobinin duyarlılığı şöyle bulunur:

```
Kₙ = (z₂ⁿ − z₁ⁿ) / ( n · r_refⁿ⁻¹ )
```

- **z₁, z₂:** bobinin iki iletkeninin konumları (karmaşık sayı olarak, metre). Bizim teğet bobinde z₁ = 20 mm + i·10 mm, z₂ = 20 mm − i·10 mm.
- **r_ref:** referans yarıçapı (25 mm).

Yani yazılım, ölçülen akıyı açıya göre sinüs dalgalarına ayırır ve her n için Cₙ'i şöyle bulur:

```
Cₙ = Φₙ / ( N · ℓ · Kₙ )          (Φₙ: akının n. sinüs bileşeninin büyüklüğü)
```

### 1.3 Merkez nasıl bulunur

İdeal bir kuadrupolün alanı tam merkezinde sıfırdır. Ölçüm ekseni merkezden biraz kaçıksa, eksende küçük bir "sahte" dipol görürüz. Bu dipolün büyüklüğü kaçıklıkla orantılıdır:

```
z_c = − r_ref · C₁ / C₂
```

- **z_c:** merkezin ölçüm eksenine göre kaçıklığı (karmaşık sayı: gerçek kısmı x, sanal kısmı y).
- **C₁:** dipol bileşeni (sahte dipol).
- **C₂:** kuadrupol bileşeni (ana sinyal).

Merkezleme programı mıknatısı hareket ettirmez. Dört bobinin akımlarını çok küçük farklarla ayarlayarak C₁'i sıfırlar.

### 1.4 Neden bu kadar küçük hatalar önemli

Simülasyondaki mıknatısta (gradyen yaklaşık 0,095 T/m, 23 Hz):

- Ana sinyal (kuadrupol, n = 2): yaklaşık **5,5 mV**.
- 1 µm merkez kaçıklığının yarattığı sinyal (n = 1): yaklaşık **0,14 µV**.

Oran yaklaşık **40 bin**. Yani 1 µm hassasiyet için, ana sinyalin yaklaşık **yüz binde 2,5'ine** kadar doğru olmamız gerekir. Büyük sinyalde küçük bir bozulma dipole karışırsa, merkezi yanlış bulursunuz. Aşağıdaki hataların çoğu tam olarak bu tür "ana sinyalin dipole karışması"dır.

---

## 2. Nasıl sınadık

Ölçüm kodunu, **kendi formüllerini kullanmayan** bağımsız bir fizik modeline karşı sınadık (`host/tests/test_olcum_fizigi.py`). Neden bağımsız? Yazılım kendi formülleriyle ürettiği veriyi kendi formülleriyle çözerse, formülde bir hata varsa iki taraf aynı yanlışı yapar ve test geçer. Bağımsız model bunu önler.

Bağımsız modelin kurulumu:

- **Alan:** mıknatısın tel demetlerinin her birinden gelen alan, doğrudan toplanır (çok kutup serisi ya da Kₙ formülü kullanılmaz).
- **Akı:** bobinin iki iletkeni arasındaki kesit boyunca alanın sayısal integrali.
- **Gerilim:** akının zamana göre türevi; gerçek (dalgalanan) açı fonksiyonuyla.
- **Enkoder:** firmware'deki gibi. Stator yaklaşık her 1 ms'de bir okur, değer 0,1 ms'de dönen karta ulaşır, her ADC ölçümü o ana kadar gelen **son** açı değerini taşır ("merdiven"). ADC ölçümü ayrıca 0,28 ms eskidir (filtre gecikmesi). Net gecikme **L = 0,18 ms**.
- **Mıknatıs:** merkezi gerçekte (149,9 + 27,4i) µm'de olan bir kuadrupol; yani merkez **152 µm** kaçık. Akımlar 9,5 A civarı.
- **Bobin ve ayarlar:** 5 sarım, 100 × 20 mm, eksene 20 mm, teğet. 23 Hz, 7200 ölçüm/saniye, 2 saniyelik pencere.
- **Akış:** lab'daki gibi. Önce referans dipol (düzgün düşey alan) ile faz düzeltmesi bulunur, sonra kuadrupol ölçülür.

**Birimler:** merkez hatası µm cinsindendir. Yüksek çok kutup (n = 3–6) hataları için **"birim"** kullanılır: 1 birim, kuadrupol büyüklüğünün on binde biridir.

---

## 3. Özet tablo

| # | Hata | Düzeltmesiz etki | Ne yapıldı | Düzeltmeli etki |
|---|---|---|---|---|
| 1 | Motor hızının tur içinde dalgalanması | 0,5° dalgalanmada merkez **177 µm** kayar | Gerilim yerine akı kullanılıyor (hız hiç gerekmiyor) | 0,04 µm |
| 2 | Gerilim ile açı arasında zaman farkı (gecikme) × hız dalgalanması | 0,5° dalgalanmada **4,5 µm**; 2°'de **19 µm** | Gecikme iki yönlü ölçümle bulunup düzeltiliyor | 0,04–0,10 µm |
| 3 | Gecikme × dönüş yönü değişimi | Referans bir yönde, ölçüm öbür yönde: **8 µm** | Aynı düzeltme | 0,06 µm |
| 4 | Enkoderin basamaklı (merdiven) çalışması | Merkez **2,4 µm**; n = 6'da **4,2 birim** | Okuma anları bulunup açı pürüzsüz doldurulur | 0,04 µm; n = 6'da 0,1 birim |
| 5 | Toplama yönteminin küçük kazanç kaybı | n = 2'de 1,3·10⁻⁴; n = 6'da 1,2·10⁻³ | Kesin formülle düzeltiliyor | yaklaşık 10⁻⁶ |
| 6 | Ters dönüşte işaret hatası | Ters yönde bütün sonuçların işareti ters | Akı yönteminde yön önemsiz | Yok |
| 7 | Kayıp ölçüm örnekleri | Tek kayıpta **4–8 µm** | Onarılamaz; tespit edilip ölçüm reddedilir | Merkezleme'ye gitmez |
| 8 | Merkezleme sürerken ölçüm koşullarının değişmesi | Merkezleme'nin öğrendikleri geçersiz olur | Koşullar kilitlenir | Engellenir |
| 9 | Faz düzeltmesi iki bobin için ortaktı | Bobin 2'de merkez **90° dönük** çıkıyordu | Her bobinin kendi faz düzeltmesi var | Yok |

---

## 4. Giderilen hatalar (ayrıntı)

### 4.1 Tur içi hız dalgalanması → akı kullanmak

**Ne oluyor?** Motor her turda mükemmel sabit hızla dönmez; yük torku, eksen kaçıklığı, adım motorunun doğası hızı turun bir yerinde biraz artırıp bir yerinde azaltır. Bölüm 1.1'de gördüğümüz gibi:

```
V = − ω(t) · dΦ/dθ
```

gerilim, o anki hız ω(t) ile orantılı.

**Neden kötü?** Eski yöntem gerilimi açıya göre sinüs dalgalarına ayırıyor ve hepsini **ortalama hız** ile bölüyordu. Yani "hız sabit" varsayıyordu. Gerçekte hız turun bir yerinde biraz fazlaysa, o bölgede gerilim de biraz fazladır. Güçlü ana sinyal (n = 2) bu dalgalanmayla çarpılınca, kendi frekansının iki yanına, n = 1 ve n = 3'e "taşar". n = 1 merkezi belirlediği için hata doğrudan merkezde görünür.

> **Benzetme:** Bir arabanın katettiği yolu hız göstergesinden tahmin etmeye çalışıyorsunuz, ama gösterge sürekli oynuyor. Oysa kilometre sayacına baksanız, hızın nasıl oynadığının önemi olmaz. Gerilim "hız göstergesi" gibi; akı "kilometre sayacı" gibi.

**Sonuç (merkez hatası, µm):**

| Hız dalgalanması (açı olarak, tepe) | Eski yöntem (gerilim) | Akı, gecikme bilinmeden | Akı, gecikme biliniyorken |
|---|---|---|---|
| 0° (dalgalanma yok) | 0,12 | 0,05 | 0,04 |
| 0,25° | 88 | 2,2 | 0,04 |
| 0,5° | 177 | 4,5 | 0,04 |
| 1° | 358 | 9,2 | 0,05 |
| 2° | 733 | 18,9 | 0,10 |

Simülasyondaki dalgalanma, tur başına bir ve iki kez tekrarlanan bileşenlerden oluşur. 0,5° açı dalgalanması yaklaşık yüzde 1–2 tepe hız dalgalanmasına karşılık gelir.

**Ne yaptık?** Gerilimi zaman içinde toplayarak akıyı hesaplıyoruz:

```
Φ(t) = − ∫ V dt
```

Akı yalnızca bobinin **nerede olduğuna** bağlıdır, ne hızla gittiğine değil. Sonra akıyı enkoder açısına karşı sinüs dalgalarına ayırıyoruz. Hız hiçbir yerde kullanılmıyor. (Dönen bobin sistemlerinde bu işlem çoğunlukla donanımla, bir integratör devresiyle yapılır. Burada aynısını yazılımla yapıyoruz.)

Akıdaki ADC ofsetinin integrali (zamanla doğrusal artan bir kayma) ve yavaş sürüklenme, 3. dereceden bir zaman terimiyle birlikte uydurulup çıkarılır.

**Koşul:** Bu yöntem, ADC ölçümlerinin zamanda eşit aralıklarla ve **eksiksiz** gelmesine dayanır. Kayıp ölçüm sorunu için bölüm 4.7'ye bakın.

### 4.2 Gerilim ile açı arasındaki zaman farkı → iki yönlü ölçüm

**Ne oluyor?** İki şey yüzünden her gerilim ölçümü, yanındaki açı etiketinden farklı bir ana aittir:
- ADC'nin Sinc4 süzgeci, her ölçümü birkaç yüz mikrosaniye geriye kaydırır.
- Enkoder açısı, statordan RS485 ile dönen karta ulaşana kadar zaman geçer.

Aradaki net fark **L**'dir. Simülasyonda L = 0,18 ms. (Gerçek değeri lab'da ölçeceğiz.)

> **Benzetme:** Bir koşucuyu fotoğraflıyorsunuz, ama fotoğraf makinesinin saati kronometreden biraz geride. Her fotoğrafın üzerindeki "süre" etiketi biraz yanlış.

**Ne kadar kötü?**

- **Hız sabitken zararsızdır.** Açı etiketi her zaman aynı miktarda yanlıştır; bu bir sabit açı kaymasıdır (ω·L; 23 Hz'de yaklaşık 1,5°). Referans mıknatıs bu kaymayı faz düzeltmesine katar ve giderir.
- **Hız dalgalanırken zararlıdır.** Kayma da dalgalanır, bölüm 4.1'deki gibi ana sinyal dipole karışır. 0,5° dalgalanmada 4,5 µm, 2°'de 19 µm (tablo 4.1, "gecikme bilinmeden" sütunu).
- **Dönüş yönü değişince zararlıdır.** Kayma yön değiştirir. Bölüm 4.3'e bakın.

**Ne yaptık?** Gecikmeyi iki yönlü ölçümle buluyoruz.

Açı etiketi ω·L kadar yanlış olduğundan, n. çok kutbun fazı n·ω·L kadar kayar. Motor ileri dönerken bir tarafa, geri dönerken öbür tarafa kayar:

```
ψ = |ω| · L                           (açı etiketindeki hata, radyan)
Cₙ(ileri)  →  Cₙ · e^(−i·n·ψ)
Cₙ(geri)   →  Cₙ · e^(+i·n·ψ)
iki yön arasındaki faz farkı = 2·n·ψ      →      L = ψ / |ω|
```

Yani iki yön arasındaki faz farkı gecikmeyi verir. Bulunan L ile her gerilim ölçümü **zamanda geri kaydırılır** (açı etiketini sabit bir açıyla değil, zamanla kaydırıyoruz; hız dalgalanırken doğru olan budur).

Faz farkı, ölçülmesi en kolay bileşenden okunur: akıdaki büyüklüğü ve n'i en büyük olandan. Kuadrupolde bu n = 2; referans dipol ölçümünde n = 1.

**Güvenilirlik kontrolü:** Fazın belirsizliği ölçüm artığından tahmin edilir. Gecikmenin belirsizliği ±2 µs'yi aşarsa (mıknatıs yok, yanlış kanal, sinyal çok zayıf) bulunan gecikme **kullanılmaz** ve günlüğe nedeni yazılır. Referans için aynı kontrol ±0,05°'dir. Sağlık sorunu olan bir referans da kullanılmaz.

**Doğruluk:** Gerçek L = 0,1800 ms; ölçülen 0,1798 ms. Hem kuadrupolde hem referans dipolde, 1°'lik hız dalgalanmasıyla bile. Güçlü sinyalde belirsizlik 0,1 µs'nin altında. Çok zayıf sinyalde (denenen örnekte) ±9 µs çıktı ve ölçüm reddedildi.

**Kullanım:** Bulunan değer günlükte yazılır. `merkezleme_olcer.yaml` içindeki `olcum.gecikme_ms` değerine elle yazılırsa kalıcı olur. Donanım ve ADC ayarları değişmedikçe sabit kalır. Faz düzeltmesi yeni gecikmeye kendiliğinden taşınır (referansı yeniden almak gerekmez).

**Önemli not:** Milin burulması ya da kaplin boşluğu gibi **yöne bağlı sabit açı farkları** da aynı şekilde görünür ve ölçülen "gecikme"ye karışır. Aynı yöntemle giderilirler. Ama bunlar zaman değil açı olduğundan, bulunan L yalnızca **ölçüldüğü hızda** tam doğrudur. Hızı değiştirirseniz gecikmeyi yeniden ölçün.

### 4.3 Gecikme ve dönüş yönü

**Ne oluyor?** Referans +23 Hz'de alınıp ölçüm −23 Hz'de yapılırsa, gecikmenin yarattığı açı kayması işaret değiştirir. Referans düzeltmesi bir işarete göre ayarlanmıştı; ölçüm öbür işaretle yapılınca toplam hata, kaymanın iki katı olur: 2·ω·L, yaklaşık 3°.

**Ne kadar kötü?** Merkez 152 µm kaçıkken bu **7,95 µm** hata demektir.

**Ne yaptık?** Gecikme biliniyorsa açı etiketi zamanda kaydırıldığından, ölçüm çerçevesi yönden bağımsız hâle gelir. Hata **0,06 µm**'ye iner. Ayrıca merkezleme'ye yazılırken yön değiştirilemez (bölüm 4.8).

### 4.4 Enkoderin basamaklı çalışması (merdiven) → okuma anlarını bulup doldurmak

**Ne oluyor?** Stator enkoderi yaklaşık her 1 ms'de bir okuyup dönen karta yollar. Dönen kart ise her ADC ölçümüne **o ana kadar gelen son açı değerini** yazar (firmware'de ara değer hesabı yok). ADC saniyede 7200 ölçüm yaptığından, yaklaşık 7 ardışık ölçüm aynı açıyı taşır. 23 Hz'de açı bu sürede 8°'ye kadar ilerlemiş olabilir.

> **Benzetme:** Dakikada bir güncellenen bir saatle saniyeleri ölçmeye çalışmak.

**Ne kadar kötü?** Basamaklı açı, uydurmadaki sinüs dalgalarını bozar. Etkisi yüksek çok kutuplarda ve ana sinyalde:

| | n=1 | n=2 | n=3 | n=4 | n=5 | n=6 | Merkez |
|---|---|---|---|---|---|---|---|
| Düzeltmesiz (birim) | 0,87 | 24,7 | 0,71 | 0,67 | 1,28 | 4,23 | 2,4 µm |
| Düzeltmeli (birim) | 0,02 | 0,005 | 0,04 | 0,03 | 0,04 | 0,10 | 0,04 µm |

(Birim: kuadrupol büyüklüğünün on binde biri.) Merdiven, bir "örnekleme-tut" süzgeci gibi davranır: yüksek mertebeleri zayıflatır ve gürültü katar. Uydurma artığı da 7·10⁻²'den 2·10⁻⁴'e iner.

**Ne yaptık?**
1. Her yeni açı değerinin geldiği ilk ölçüm bulunur (buna "taze nokta" diyoruz).
2. Okumalar statorun saatine bağlı düzenli aralıklarla geldiği için, taze noktaların sırasına bir doğru uydurulur. Buna **okuma saati** diyoruz; açıların tam ne zaman okunduğunu, ölçüm aralığından çok daha ince bir hassasiyetle verir. Atlanan okumalar (2 ya da 3 kat aralıklar) de doğru sayılır. Taze nokta, okunma anından **sonraki** ilk ölçüm olduğundan, okuma anı yarım ölçüm geriye alınır.
3. Açı, bu okuma anları arasında **kübik eğriyle** (Hermite) pürüzsüzce doldurulur. Düz çizgiyle doldurmak yetmez; çünkü hız dalgalanırken açının eğriliğini izleyemez ve µm düzeyinde hata bırakır.

Okumalar düzenli değilse (uydurmanın sapması 0,45 ölçümü aşarsa) program okuma saati varsaymaktan vazgeçer, taze noktaların kendileri arasında doldurur.

### 4.5 Toplama yönteminin küçük kazanç kaybı → kesin formülle düzeltme

**Ne oluyor?** Akı, gerilim ölçümlerini örnek örnek toplayarak (yamuk kuralıyla) bulunur. Yamuk kuralı, hızlı değişen sinüsleri çok küçük bir oranda eksik gösterir:

```
ölçülen = gerçek · (x/2) · cot(x/2)         x = 2π · f / f_örnekleme
```

- **f:** o bileşenin frekansı (n. bileşen için n × dönme frekansı).
- **f_örnekleme:** ADC'nin örnekleme hızı (7200).
- Faz hatası yoktur, yalnızca büyüklük küçülür.

**Ne kadar kötü?** (23 Hz, 7200 ölçüm/saniye için kayıp oranları)

| n | 1 | 2 | 3 | 4 | 5 | 6 |
|---|---|---|---|---|---|---|
| Kayıp | 3,4·10⁻⁵ | 1,3·10⁻⁴ | 3,0·10⁻⁴ | 5,4·10⁻⁴ | 8,4·10⁻⁴ | 1,2·10⁻³ |

Merkezde etkisi küçüktür (C₁/C₂ oranı 10⁻⁴ kadar değişir; 152 µm'de 0,015 µm). Ama harmoniklerin mutlak değerini bozar.

**Ne yaptık?** Her bileşen, ölçülen hızla hesaplanan bu çarpana bölünür (yani tersiyle çarpılır). |C₂| hatası 1,3·10⁻⁴'ten yaklaşık 10⁻⁶'ya iner.

### 4.6 Ters dönüşte işaret hatası

**Ne oluyordu?** Eski kod hızın **mutlak değerini** kullanıyordu. Motor ters dönünce gerilimin işareti değişiyor ama bölen aynı kalıyordu. Sonuç: ters yönde bütün çok kutup değerlerinin işareti ters çıkıyordu.

**Ne kadar kötüydü?** Merkez, C₁/C₂ oranından hesaplandığından etkilenmiyordu. Ama raporlanan çok kutuplar, gradyenin işareti ve CSV kayıtları yanlıştı.

**Ne yaptık?** Akı yönteminde hız kullanılmadığı için dönüş yönü sonucu etkilemez. Testlerde +23, −23 ve 10 Hz aynı sonucu veriyor.

### 4.7 Kayıp ölçümler → tespit edip reddetmek

**Ne oluyor?** Firmware ölçümlere sıra numarası koymuyor, bu yüzden bir ölçümün kaybolduğu bilinmiyor:
- Stator kartı, sağlama toplamı tutmayan ölçümü **sessizce atıyor**; yalnızca durum paketindeki bir sayaç artıyor.
- Bilgisayar tarafında alım kuyruğu dolarsa paketler düşüyor.

Akı hesabı ise ölçümlerin eşit aralıklarla ve eksiksiz geldiğini varsayıyor.

**Ne kadar kötü?** Tek bir kayıp ölçüm, akıda bir basamak yaratır. Merkezde **4–8 µm** hata (dört farklı konumda denendi); üç kayıpta 6–14 µm.

**Ne yaptık?** Kayıp ölçümü geri getiremeyiz ama **fark edebiliriz.** İki bağımsız ölçüt kullanıyoruz:

| Ölçüt | Sağlıklı | 1 kayıp | 3 kayıp | Eşik |
|---|---|---|---|---|
| **Uydurma artığı** (uydurmanın açıklayamadığı kısım / açıkladığı kısım) | 2·10⁻⁴ | 1,1–1,4·10⁻² | 1,6–1,7·10⁻² | 2·10⁻² |
| **Okuma saati sıçraması** (ölçüm sayısı cinsinden) | yaklaşık 0,2 | 0,98–1,00 | 1,5–1,9 | 0,6 |

**Okuma saati sıçraması nedir?** Enkoder okumaları düzenli aralıklarla geldiği için, bir ADC ölçümü kaybolduğunda sonraki bütün açı okumaları bir ölçüm erken görünür. Okuma saati uydurmasının artığındaki bu kalıcı kayma "sıçrama" olarak ölçülür. Bir kayıp yaklaşık 1 ölçüm kayma demektir. Sağlıklı veride kayma ancak 0,2 civarında olur.

**Tek bir kayıp, artığı eşiğin altında bırakabilir** (1,1–1,4·10⁻² < 2·10⁻²). Sıçrama ölçütü bu yüzden eklendi ve tek kaybı net yakalıyor.

**Yanlış alarm denemesi:** Atlanan okumalar ve titreşim alarm vermiyor. 7200 ölçüm/saniyede ve 10 µs okuma titreşiminde bile sağlıklı değer 0,33'ü geçmedi. 2400–19200 ölçüm/saniye ve ±1000 ppm saat farkıyla da denendi.

**Ne olur?** İki ölçütten biri eşiği aşarsa ölçüm merkezleme'ye **yazılmaz**. Üst üste 3 kez olursa motor durdurulur. Makro komutu da aynı kontrolü yapar. Ayrıca stator kartının "bozuk ölçüm attım" sayacı artarsa günlüğe uyarı düşer.

**Kalıcı çözüm:** Firmware'de ölçüm sayacı (tercihen enkoder okumasına zaman damgası da).

**Artık eşiği hakkında not:** Mıknatısın 1 kHz'lik %1 modülasyonu açıkken sağlıklı ölçümde bile artık yaklaşık 6,6·10⁻³ çıkıyor (modülasyon yok: 2,1·10⁻⁴; %0,1 derinlik: 6,9·10⁻⁴). Merkez bundan etkilenmiyor (0,05 µm). İlk seçtiğimiz 5·10⁻³ eşiği modülasyon açıkken bütün ölçümleri reddederdi; bu yüzden 2·10⁻²'ye yükseltildi.

### 4.8 Ölçüm koşullarının değişmesi → koşul kilidi

**Ne oluyor?** Merkezleme programı çalışmaya başlarken akımları değiştirip ölçülen dipolün nasıl tepki verdiğini öğrenir. Bu öğrenme belirli bir **ölçüm çerçevesinde** yapılır: bobin (kanal), faz düzeltmesi, gecikme, dönüş yönü ve hız.

**Ne kadar kötü?** Merkezleme sürerken bunlardan biri değişirse ölçümler döner ya da ölçeklenir. Düzeltmeler yanlış yöne gider; sonuç sapabilir ya da yanlış bir noktaya yakınsayabilir.

**Ne yaptık?** "Merkezleme'ye yaz" açıkken ve motor dönerken bobin değiştirme, hız değiştirme, referans alma ve gecikme ölçümü reddedilir. Pencerede bu denetimler pasiftir. Yazma kapatılıp ayar değiştirilir ve yazma yeniden açılırsa günlükte uyarı çıkar.

### 4.9 Faz düzeltmesi iki bobin için ortaktı

**Ne oluyordu?** İki bobin birbirine dik olduğundan dönen çerçevede 90° farklı durur. Eski kodda tek bir faz düzeltmesi vardı. Bobin 1'le referans alınıp bobin 2'ye geçilince, bobin 2'nin merkezi **90° dönük** raporlanıyordu. Simülasyonda gerçek merkez (149,9 + 27,4i) µm iken, bobin 1'in düzeltmesiyle bobin 2 (27,4 − 149,9i) µm gösterdi.

**Ne yaptık?** Faz düzeltmesi ve referans hızı artık her bobin için ayrı saklanıyor. Referansı alınmamış bobin için pencere ve günlük "referans alınmadı" uyarısı veriyor. Gecikme ölçümü, referansı alınmış bütün bobinlerin düzeltmelerini yeni gecikmeye taşıyor.

### 4.10 Diğer korumalar

- **Bağlantı kopması:** Firmware, bağlantı kopunca motoru durdurmuyor; motor son hızında dönmeye devam ediyor. Program yeniden bağlanınca önce hızı sıfırlıyor, motor durunca servoyu kapatıyor. (Servoyu hemen kesmek, 23 Hz'de dönen mili rampasız bırakmak olurdu.) Durma kararı için en az 1,2 saniye bekleniyor; çünkü hız bilgisi saniyede bir geliyor ve eski bir değer yanıltabilir.
- **Zayıf sinyal:** Mıknatıs takılı değilken ya da sinyal çok zayıfken gecikme ve referans ölçümleri uygulanmıyor (bölüm 4.2).
- **Raporlanmayan üst çok kutupların sızması:** Uydurmada yalnızca n = 1..6 olsaydı, kuadrupolün izinli n = 10 gibi bileşenleri pencere kenarından raporlanan bileşenlere sızardı. Bu yüzden uydurmaya n = 1..15 dahil, n = 1..6 raporlanıyor.

---

## 5. Geliştirme sırasında bulunan kendi hatalarımız

Bunlar bu çalışma sırasında kendi yazdığım kodda bulunup düzeltildi. Ölçüm hatalarının nasıl gizlenebildiğini gösterdiği için kaydediyorum.

1. **Referans dipolde gecikme fazı.** İki yönlü ölçümün ilk sürümü gecikme fazını her zaman n = 2'den okuyordu. Referans dipolde (düzgün alan) C₂ sıfır olduğundan bu faz gürültüydü ve referansı bozuyordu: iki yönlü ölçümde merkez hatası 0,2–0,6 µm'ydi. Faz artık o ölçümde en iyi görünen bileşenden okunuyor; hata 0,04–0,10 µm.
2. **Okuma anı yarım ölçüm yanlış yöndeydi.** Taze nokta, okunma anından **sonraki** ilk ölçüm olduğundan okuma anı yarım ölçüm **geriye** alınmalıydı. İlk sürümde ileri alınmıştı; bu bir ölçümlük (139 µs) sabit zaman hatası demekti. Düzeltildi; ölçülen gecikme artık doğru çıkıyor.
3. **Dönüş yönü.** Bölüm 4.6'daki işaret hatası, ilk yeniden yazımda bulundu.
4. **Eski artık eşiği (5·10⁻³)** mıknatıs modülasyonuyla uyumsuzdu (bölüm 4.7).

---

## 6. Giderilmeyen ya da kısmen giderilen etkiler

### 6.1 Enkoderin her turda tekrarlanan açı hatası (en önemli açık konu)

**Ne oluyor?** Enkoder diski mile tam ortalı değilse ya da enkoder ile bobin mili arasındaki bağlantı (kaplin) her turda biraz oynuyorsa, okunan açı gerçek açıdan **tur başına bir kez** küçük miktarda sapar:

```
okunan açı = gerçek açı + ε · cos(gerçek açı + φ)         (ε: sapmanın büyüklüğü, φ: hangi açıda olduğu)
```

Birkaç açı dakikası (1 açı dakikası = derecenin 60'ta biri) olağandır.

**Ne kadar kötü?** Simülasyonda sahte merkez kayması **φ'den bağımsız** olarak şu kadar çıktı:

```
sahte kayma  ≈  d · ε          (d: bobinin eksene uzaklığı = 20 mm)
```

| ε | Sahte merkez kayması |
|---|---|
| 1 açı dakikası | **5,8 µm** |
| 5 açı dakikası | **29 µm** |

Bu hata dönüş yönünden bağımsızdır; iki yönlü ölçüm onu **gidermez.** Merkezleme mıknatısı bu kadar yanlış bir noktaya götürür ve fark edemez. (Tur başına **iki** kez tekrarlanan açı hataları önemsiz: 1 açı dakikasında 0,05 µm.)

**Nasıl anlaşılır?** İki bobin birbirine 90° dik olduğundan bu hatayı **farklı** gösterir. Simülasyonda bobin 2'nin sahte kayması, bobin 1'inkinin 90° döndürülmüş hâli çıktı (ikisi de kendi referansıyla ayarlıyken). Yani mıknatıs aynı yerde dururken iki bobin **farklı merkez** gösteriyorsa, büyük olasılıkla bu hata vardır. İki bobinin farkından hem sahte kayma hem gerçek merkez hesaplanabilir; mevcut donanımla bir kalibrasyon yazılabilir.

### 6.2 Enkoder okuma zamanının titremesi (rastgele)

Stator kartı enkoderi ana döngüsünde okuyor. Bu döngü Ethernet gibi işlerle zaman zaman gecikebilir; okuma anı düzenli saatten birkaç on mikrosaniye sapabilir. Program okumaları düzenli saatle geldi varsaydığı için bu sapma küçük bir açı hatasına dönüşür.

| Okuma titreşimi | 2 s pencerede merkez hatası | 8 s pencerede |
|---|---|---|
| 5 µs | 1,2 µm | 0,24 µm |
| 20 µs | 4,7 µm | 1,0 µm |

Sistematik değil, rastgeledir; ölçüm süresini uzatınca azalır. Gerçek titreşim düzeyi bilinmiyor. **Kalıcı çözüm:** firmware'de zaman damgası ya da dönen kartta açının ölçüm anına enterpolasyonu.

### 6.3 Enkoderin 0,1° çözünürlüğü

Enkoder tur başına 3600 sayım veriyor (yaklaşık 0,1°). Simülasyonda bu kuantalamanın merkeze etkisi **0,06 µm** çıktı; yani tek başına sorun değil.

### 6.4 ADC süzgecinin yüksek çok kutupları küçültmesi

Sinc4 süzgeci, hızlı değişen bileşenleri biraz zayıflatır. **Tahminimiz** (ADC'nin gerçek frekans yanıtından hesaplanmadı): n = 2'de yaklaşık 3·10⁻⁴, n = 6'da yaklaşık 2·10⁻³. Düzeltilmedi. Merkezde etkisinin 0,03 µm civarında olması beklenir (bu da tahmin).

### 6.5 Bobin geometrisi ve elektronik kazanç (ölçek hataları)

Sarım sayısı, genişlik, eksene uzaklık gibi değerlerdeki küçük hatalar (Kₙ'deki hata) ve elektronik kazanç hatası, ölçülen her şeyi aynı oranda büyütür ya da küçültür. Merkezleme'nin sıfıra yakınsamasını **bozmaz**: sıfır, hangi çarpanla çarpılırsa çarpılsın sıfırdır; merkezleme kendi testinde ölçeği zaten öğrenir. Ama raporlanan µm değerlerinin mutlak doğruluğunu etkiler. Bilinen gradyenli bir mıknatısla (gradyen için) ve bilinen bir mekanik kaydırmayla (merkez ölçeği ve yön için) doğrulanmalı.

**Üç boyutlu etki:** Bobin 100 mm boyunca **ortalama** alanı ölçer. Mıknatısın uç alanları ya da eğikliği varsa ölçülen merkez bu uzunluk boyunca bir ortalamadır.

### 6.6 Mil sehimi (yerçekimi), eksen oynaması, bobin eğikliği

Hepsi **dönüş yönünden bağımsızdır;** iki yönlü ölçüm gidermez.
- **Sehim:** Uzun mil ortasında yerçekimiyle sarkar. Ölçülen merkez sarkmış eksene göredir. Bunun bir "hata" olup olmadığı, hedef eksenin nasıl tanımlandığına bağlıdır.
- **Eksen oynaması / titreşim:** Eksen titrerse bunu mıknatısın merkezi kaymış gibi görürüz. Dönmeyle aynı ritimde bir yalpalama varsa sistematik karışma yapabilir. Büyük sistemlerde bunun için ana sinyali iptal eden ek bobinler (kompanzasyon) kullanılması yaygındır; bizde yok.
- **Anlaşılması:** Manyetik alan motor hızından bağımsızdır, mekanik etkiler genellikle hıza bağlıdır. Aynı alanı farklı hızlarda ölçmek ayırt etmeye yarar.

### 6.7 Polarite ve yön

Kanal kutupları (bobin uçlarının hangisi artı) ya da bobin tipi ters tanımlıysa merkez 180° döner ya da aynalanır. Bunu bir kez, mıknatısı bilinen bir miktar ve yönde kaydırarak kontrol etmek gerekir.

### 6.8 Çevredeki manyetik alan

Dünya'nın alanı (yaklaşık 50 µT) bizim kuadrupolde merkezi yaklaşık **0,5 mm** kaydırır (demirsiz olduğundan perdelenmez). Merkezleme programı arka planı ölçüp çıkarıyor. Ama arka plan ölçümler arasında değişirse çıkarma yetersiz kalır.

### 6.9 Bobinin yüksek çok kutuplara duyarlılığı

Bobin geometrisinden gelen değişmez bir sınır: n = 6'da duyarlılık düşük (gürültü n = 1'e göre yaklaşık 2,2 kat), n = 7'de neredeyse sıfır. Yazılımla düzeltilemez.

### 6.10 Gecikmenin hıza bağlı bileşeni

Burulma gibi yöne bağlı açı kaymaları ölçüldüğü hızda doğru ölçülür (bölüm 4.2). Hız değişirse gecikme yeniden ölçülmeli.

---

## 7. Lab'da doğrulanması gerekenler

Simülasyon, analizin kendi içinde doğru olduğunu ve modellediğimiz hataları giderdiğini gösterir. Gerçek düzeyleri ve modellemediğimiz etkileri yalnızca lab gösterir.

1. **Tekrarlanabilirlik:** merkezin (x_c, y_c) saçılımına bakın. Ölçüm süresini 2 s'den 8 s'ye çıkarınca saçılım yaklaşık yarıya inmeli.
2. **Gecikme:** "Gecikme ölç" düğmesini iki-üç kez kullanın. Değerler birkaç µs içinde tutarlı olmalı. Sonucu `olcum.gecikme_ms`'e yazın.
3. **Yön karşılaştırması:** gecikme ayarlıyken aynı alanı +23 ve −23 Hz'de ölçün. Aynı çıkmalı. Kalan fark, bilmediğimiz yöne bağlı bir etkiyi gösterir.
4. **Hız karşılaştırması:** aynı alanı 10, 15 ve 23 Hz'de ölçün. Manyetik sonuç hızdan bağımsız olmalı; değişiyorsa mekanik bir etki (6.6) vardır.
5. **İki bobin karşılaştırması:** mıknatıs aynı yerdeyken bobin 1 ve bobin 2'yi, her biri **kendi referansıyla** ölçün. Aynı merkezi göstermeliler. Göstermiyorsa enkoder açı hatası (6.1) vardır.
6. **İşaret ve ölçek:** mıknatısı bilinen miktarda +x, sonra +y yönünde kaydırın. Merkez beklenen işaret ve büyüklükte değişmeli.
7. **Mutlak ölçek:** bilinen gradyenle |C₂|/r_ref karşılaştırılmalı.
8. **Referans:** referans sonrası b0 pozitif, a0 sıfıra yakın olmalı; her iki bobin için ayrı yapılmalı.
9. **Sağlık ölçütleri:** sağlıklı ölçümlerde "Artık / saat sıçr." hangi düzeyde? Eşikler buna göre ayarlanabilir. Reddedilen ölçüm sık geliyorsa günlükte RS485 uyarılarına bakın.

Ayrıntılı kullanım ve lab planı: `README_SURUM.md`. Sistemin genel anlatımı: `DONEN_BOBIN_REHBERI.md`. Simülasyon testleri: `host/tests/test_olcum_fizigi.py`, `test_merkezleme_olcer.py`, `test_kapali_dongu.py`.
