# Dönen bobin ölçümü: sistematik hatalar ve düzeltmeleri

*Merkezleme ölçüm programı (`host/mgf/merkezleme_koprusu.py`, `olcum_dongusu.py`) — Ekim 2026*

Bu rapor, merkezleme ölçüm programındaki analizin eleştirel gözden geçirilmesinde bulunan sistematik hata kaynaklarını anlatır. Her biri için şunlar verilir: hatanın nereden geldiği, ölçümü nasıl bozduğu, programın onu nasıl giderdiği ve ne kadar giderdiği. Bütün sayılar simülasyondandır; gerçek donanımdaki düzeyler (hız dalgalanması, enkoder titreşimi, örnek kaybı sıklığı) lab'da ölçülmelidir (bkz. bölüm 5).

## 1. Nasıl sınandı

Ölçüm kodu, kendi formüllerini **kullanmayan** bağımsız bir fizik modeline karşı sınandı (`host/tests/test_olcum_fizigi.py`):

- **Alan:** merkezleme simülatörünün iletkenlerinden doğrudan, B_y + i·B_x = μ0/2π · Σ I_j / (z − z_j). Çok kutup serisi ve K_n formülü kullanılmaz.
- **Akı:** bobin kesiti boyunca alanın Gauss–Legendre integrali. **Gerilim:** akının zamana göre türevi, gerçek (dalgalanan) açı fonksiyonuyla.
- **Enkoder:** firmware'deki gibi. Stator ~1 ms'de bir okur (saati ADC saatinden 40 ppm farklı), değer 0,1 ms'de rotora ulaşır, her ADC örneği o ana kadar gelen son değeri taşır (merdiven). ADC örneği ayrıca 0,28 ms eskidir (filtre gecikmesi). Net gecikme L = 0,18 ms.
- **Mıknatıs:** merkezi gerçekte (149,9 + 27,4i) µm'de olan kuadrupol (|z_c| = 152 µm), 9,5 A civarında akımlarla. Bobin: 5 sarım, 100 × 20 mm, eksene 20 mm, teğet. 23 Hz, 7200 SPS, 2 s pencere.
- **Akış:** lab'daki gibi önce referans dipol (düzgün düşey alan) ile faz ofseti bulunur, sonra kuadrupol ölçülür.

**Birim:** üst harmonik hataları "birim" cinsinden verilir: 1 birim = |C₂|'nin 10⁻⁴'ü (r_ref = 25 mm'de). Merkez hatası µm cinsindendir.

## 2. Özet tablo

| # | Hata kaynağı | Düzeltmesiz etki | Nasıl düzeltiliyor | Düzeltmeli etki |
|---|---|---|---|---|
| 1 | Tur içi hız dalgalanması | 0,5° dalgada merkez **177 µm**, n=3–6 **45 birim** | Gerilim yerine akı (Φ = −∫V dt); hız hiç kullanılmaz | 0,04 µm (gecikme biliniyorsa) |
| 2 | ADC–enkoder zaman gecikmesi × hız dalgalanması | 0,5° dalgada **4,5 µm**, 2° dalgada **19 µm** | Gecikme iki yönlü ölçümle bulunur, açı zamanda kaydırılır | 0,04–0,10 µm |
| 3 | Gecikme × dönüş yönü değişimi | Referans +23 Hz'de, ölçüm −23 Hz'de: **8 µm** | Aynı (gecikme bilinince çerçeve yönden bağımsız) | 0,06 µm |
| 4 | Enkoder merdiveni (1 ms'lik basamaklar) | Merkez **2,4 µm**; n=2 kazancı %0,25; n=6 **4,2 birim** | Okuma saati uydurması + kübik enterpolasyon | 0,04 µm; n=6 0,1 birim |
| 5 | Yamuk integrali kazanç hatası | n=2'de 1,3·10⁻⁴, n=6'da 1,2·10⁻³ | Analitik düzeltme (x/2)·cot(x/2) | ~10⁻⁶ |
| 6 | Dönüş yönünde işaret | Ters yönde bütün C_n'lerin işareti ters | Akı uzayında yön sonucu etkilemez | Yok |
| 7 | Örnek kaybı (RS485/TCP) | Tek kayıp: merkez **4–8 µm** | Düzeltilemez; **tespit edilip reddedilir** | Ölçüm merkezleme'ye yazılmaz |
| 8 | Ölçüm sırasında çerçeve değişimi | Merkezleme'nin kalibrasyonu geçersizleşir | Çerçeve kilidi | Engellenir |

İç hatalar (geliştirme sırasında kendi kodumda bulunanlar) bölüm 3.9'dadır.

## 3. Ayrıntılar

### 3.1 Tur içi hız dalgalanması → akı integrasyonu

**Kaynak:** motor her turda tam sabit hızla dönmez (yük torku, eksen kaçıklığı, step motor karakteristiği). Bobin gerilimi V = −dΦ/dt = −ω(t)·dΦ/dθ, yani o anki hızla orantılıdır.

**Etki:** eski yöntem gerilimi açıya göre harmoniklere ayırıp **ortalama** hızla bölüyordu. Hız tur içinde ω₀(1 + ε·cos θ) gibi dalgalanırsa gerilim, harmoniklerin bu dalgayla çarpımını içerir: güçlü n=2 sinyali n=1 ve n=3'e karışır. n=1 merkezi belirlediğinden hata doğrudan merkezde görünür:

| Açı dalgası (tepe) | Gerilim yöntemi: merkez / n=3–6 | Akı yöntemi (gecikme biliniyor) |
|---|---|---|
| 0° | 0,12 µm / 0,02 birim | 0,04 µm / 0,09 birim |
| 0,25° | 88 µm / 23 birim | 0,04 µm / 0,09 birim |
| 0,5° | 177 µm / 45 birim | 0,04 µm / 0,09 birim |
| 1° | 358 µm / 90 birim | 0,05 µm / 0,09 birim |
| 2° | 733 µm / 179 birim | 0,10 µm / 0,10 birim |

(Simülasyondaki dalga tur başına 1 ve 2 periyotludur; 0,5° açı dalgası ~%1–2 tepe hız dalgasına karşılık gelir.)

**Düzeltme:** gerilim zamana göre integre edilir (Φ = −∫V dt, ADC örnekleri zamanda düzgün aralıklıdır) ve akı, enkoder açısına karşı uydurulur. Akı yalnızca bobinin **konumuna** bağlıdır, hızına bağlı değildir. Bu, dönen bobin sistemlerinde donanımla yapılan integratörün yazılımdaki karşılığıdır. Akıdaki ADC ofsetinin integrali (doğrusal artış) ve yavaş sürüklenme, 3. dereceden bir zaman polinomuyla birlikte uydurulur.

**Koşul:** örnekler kayıpsız olmalıdır (bkz. 3.7).

### 3.2 ADC–enkoder zaman gecikmesi → iki yönlü ölçüm

**Kaynak:** bir ADC örneği, Sinc4 filtresi yüzünden birkaç yüz µs önceki gerilimi gösterir. Enkoder değeri ise statordan RS485 ile rotora gecikmeli ulaşır. Sonuçta her gerilim örneği, yanında yazan açıdan L kadar **farklı bir zamana** aittir (simülasyonda L = 0,18 ms).

**Etki:**
- **Sabit hızda** gecikme yalnızca bir açı ofsetidir (ω·L, 23 Hz'de 1,5°). Referans mıknatıs bunu faz ofsetine katarak giderir; zararsızdır.
- **Hız dalgalanırken** ofset de dalgalanır (ω(t)·L) ve n=2'yi yine n=1'e karıştırır. Akı yönteminde bile, gecikme bilinmezse:

| Açı dalgası | Akı, L = 0 varsayılırsa | Akı, L biliniyorsa |
|---|---|---|
| 0,25° | 2,2 µm | 0,04 µm |
| 0,5° | 4,5 µm | 0,04 µm |
| 1° | 9,2 µm | 0,05 µm |
| 2° | 18,9 µm | 0,10 µm |

**Düzeltme:** "Gecikme ölç (iki yön)" düğmesi.
1. Bir pencere bu yönde alınır, motor ters çevrilir, bir pencere öbür yönde alınır.
2. Gecikme, harmonikleri bir yönde e^{−inψ}, öbür yönde e^{+inψ} ile döndürür (ψ = |ω|·L). İki yönün faz farkı 2nψ'dir; buradan L bulunur.
3. Bulunan L ile her gerilim örneği zamanda geri kaydırılır (sabit açı ofseti olarak değil). Hız dalgalanmasında doğru olan budur.

Faz farkı, akıdaki genliği × n en büyük olan harmonikten okunur: kuadrupolde n=2, referans dipolde n=1.

**Güvenilirlik:** fazın artıktan tahmin edilen belirsizliği ±2 µs'yi aşarsa (mıknatıs yok, yanlış kanal, sinyal çok zayıf) gecikme uygulanmaz. Referans için aynı kontrol ±0,05°'dir; sağlık sorunu olan referans da uygulanmaz.

**Doğruluk:** gerçek 0,1800 ms, ölçülen 0,1798 ms; hem kuadrupolde hem referans dipolde, 1° hız dalgasıyla. Ölçülen değer `olcum.gecikme_ms`'e yazılır. Donanım (ADC hızı/filtresi, firmware) değişmedikçe sabittir. Faz ofseti, yeni gecikmeye kendiliğinden taşınır (referans tekrar alınmadan).

**Not:** yöne bağlı sabit bir açı farkı da (mil burulması, kaplin boşluğu) aynı biçimde görünür ve ölçülen "gecikme"ye katılır. Bu bileşen zaman değil açı olduğu için ölçülen L yalnızca **ölçüldüğü hızda** tam doğrudur. Hız değişirse gecikme yeniden ölçülmelidir.

### 3.3 Gecikme ve dönüş yönü

**Etki:** referans +23 Hz'de alınıp ölçüm −23 Hz'de yapılırsa, gecikmenin açı ofseti işaret değiştirir. Çerçeve 2·ω·L (3°) döner; merkez 152 µm'deyken bu **7,95 µm** hata demektir.

**Düzeltme:** gecikme biliniyorsa açı zamanda kaydırıldığından çerçeve yönden bağımsızdır: **0,06 µm**. Ayrıca merkezleme'ye yazılırken yön değiştirilemez (çerçeve kilidi).

### 3.4 Enkoder merdiveni → okuma saati + kübik enterpolasyon

**Kaynak:** stator enkoderi ~1 ms'de bir okuyup rotora gönderir; rotor her ADC örneğine son aldığı değeri yazar (firmware'de enterpolasyon yok). 7200 SPS'te ~7 ardışık örnek aynı açıyı taşır ve açı 0–1 ms (23 Hz'de 0–8°) eskir.

**Etki** (düzeltmesiz / düzeltmeli, birim):

| | n=1 | n=2 | n=3 | n=4 | n=5 | n=6 | Merkez |
|---|---|---|---|---|---|---|---|
| Düzeltmesiz | 0,87 | 24,7 | 0,71 | 0,67 | 1,28 | 4,23 | 2,4 µm |
| Düzeltmeli | 0,02 | 0,005 | 0,04 | 0,03 | 0,04 | 0,10 | 0,04 µm |

Merdiven bir örnekleme tutma (sample-and-hold) filtresi gibi davranır: yüksek mertebeleri zayıflatır ve gürültü katar. Uydurma artığı da 7·10⁻² iken 2·10⁻⁴'e iner.

**Düzeltme:**
1. Her yeni enkoder değerinin geldiği ilk örnek ("taze nokta") bulunur.
2. Okumalar stator saatine bağlı düzenli aralıklarla geldiğinden, taze noktaların indeksine doğru uydurulur ("okuma saati"). Atlanan okumalar 2×, 3× aralık olarak sayılır. Taze nokta varıştan sonraki ilk örnek olduğundan yarım örnek geri gidilir.
3. Açı, bu okuma anları arasında kübik Hermite ile enterpole edilir. Doğrusal enterpolasyon, okumalar arasındaki hız eğriliğini izleyemez ve dalgalanmada µm düzeyinde hata bırakır.

Okumalar düzenli değilse (uydurmanın sapması > 0,45 örnek) taze noktaların kendileri arasında enterpole edilir.

### 3.5 Yamuk integrali kazanç hatası → analitik düzeltme

**Kaynak:** akı, örneklerin yamuk kuralıyla toplanmasıyla bulunur. Yamuk kuralı, frekansı f olan bir sinüsü (x/2)·cot(x/2) çarpanı kadar küçültür (x = 2π·f/f_örnekleme; faz hatası yoktur).

**Etki** (23 Hz, 7200 SPS): n=1: 3,4·10⁻⁵; n=2: 1,3·10⁻⁴; n=3: 3,0·10⁻⁴; n=4: 5,4·10⁻⁴; n=5: 8,4·10⁻⁴; n=6: 1,2·10⁻³ göreli kazanç kaybı. Merkezde etkisi küçüktür (C₁/C₂ oranı 10⁻⁴ değişir: 152 µm'de 0,015 µm) ama harmoniklerin mutlak değerini bozar.

**Düzeltme:** her harmonik, ölçülen ortalama hızla hesaplanan bu çarpana bölünür. |C₂| hatası 1,3·10⁻⁴'ten ~10⁻⁶'ya iner.

### 3.6 Dönüş yönünde işaret

**Kaynak:** eski kod hızın mutlak değerini kullanıyordu. Motor ters dönünce gerilimin işareti değişir ama bölen değişmezdi.

**Etki:** ters yönde bütün C_n'lerin işareti ters çıkar. Merkez (C₁/C₂ oranı) etkilenmez ama raporlanan harmonikler, gradyenin işareti ve CSV kayıtları yanlıştır.

**Düzeltme:** akı uzayında hız kullanılmadığından yön sonucu etkilemez. Testlerde +23, −23 ve 10 Hz aynı sonucu verir.

### 3.7 Örnek kaybı → tespit ve red

**Kaynak:** firmware örneklere sıra numarası koymuyor.
- Stator, ADC sağlama toplamı tutmayan örnekleri **sessizce atıyor**; yalnızca durum paketindeki bir sayaç artıyor.
- PC'de alım kuyruğu dolarsa paket düşüyor.

Akı integrali ise örneklerin zamanda düzgün ve kayıpsız olduğunu varsayar.

**Etki:** tek bir kayıp örnek, akıda bir basamak (v·Δt) yaratır. Sonuç: merkezde **4–8 µm** hata (dört farklı konumda denendi), üç kayıpta 6–14 µm.

**Düzeltme (tespit):** kayıp örnek onarılamaz ama yakalanır; iki bağımsız ölçüt kullanılır:

| Ölçüt | Sağlıklı | 1 kayıp | 3 kayıp | Eşik |
|---|---|---|---|---|
| Uydurma artığı (rms artık / rms harmonik) | 2·10⁻⁴ | 1,1–1,4·10⁻² | 1,6–1,7·10⁻² | 2·10⁻² |
| Okuma saati sıçraması (örnek) | ~0,2 | 0,98–1,00 | 1,5–1,9 | 0,6 |

- **Okuma saati sıçraması:** enkoder okumaları düzenli saatle geldiğinden, kaybolan bir ADC örneği sonraki bütün okumaları bir örnek erken gösterir. Okuma saati uydurmasının artığının kayan medyanındaki tepe-tepe değişim bunu ölçer.
- **Yanlış alarm:** atlanan okumalar ve titreşim alarm vermez. 7200 SPS'te 10 µs okuma titreşiminde bile sağlıklı değer ≤ 0,33'tür. 2400–19200 SPS ve ±1000 ppm saat farkında da denendi.
- **Red:** iki ölçütten biri aşılırsa ölçüm merkezleme'ye yazılmaz; üst üste 3 kez olursa motor durdurulur. Makro komutu da aynı kontrolle reddeder.
- **RS485 sayacı:** stator'un durum paketindeki RS485 hata sayacı artınca günlüğe uyarı yazılır.

**Kalıcı çözüm:** firmware'de örnek sayacı (tercihen enkoder okumasına zaman damgası).

### 3.8 Ölçüm çerçevesi değişimi → çerçeve kilidi

**Kaynak:** merkezleme programı ilk adımlarda ölçüm ile akımlar arasındaki ilişkiyi kalibre eder. Bu kalibrasyon belirli bir "ölçüm çerçevesi"nde yapılır: kanal (iki dik bobin), faz ofseti, gecikme, dönüş yönü ve hız.

**Etki:** merkezleme sürerken bunlardan biri değişirse ölçümler döner ya da ölçeği değişir. Düzeltmeler yanlış yöne gider; ıraksama ya da yanlış merkeze yakınsama olabilir.

**Düzeltme:** "Merkezleme'ye yaz" açıkken ve motor dönerken kanal, hız, referans ve gecikme ölçümü reddedilir (pencerede denetimler devre dışıdır). Yazma kapatılıp çerçeve değiştirildikten sonra yeniden açılırsa günlükte uyarı çıkar.

### 3.9 Diğer düzeltmeler ve iç hatalar

- **Raporlanmayan üst harmoniklerin sızması:** uydurmada yalnızca n=1..6 olsaydı, kuadrupolün izinli n=10'u gibi terimler pencere kenarından raporlanan mertebelere sızardı. Uydurmaya n=1..15 alınır, 1..6 raporlanır.
- **ADC ofseti ve sürüklenmesi:** akıda doğrusal artış ve yavaş eğri olarak görünür; zaman polinomuyla birlikte uydurulup çıkarılır.
- **İç hata — referans dipolde gecikme fazı:** iki yönlü ölçümün ilk sürümü gecikme fazını her zaman n=2'den okuyordu. Referans dipolde C₂ ≈ 0 olduğundan faz gürültüydü ve referansı bozuyordu: çift yönlü ölçümde merkez hatası 0,2–0,6 µm'ydi. Faz artık en iyi ölçülen harmonikten okunuyor; hata 0,04–0,10 µm.
- **İç hata — okuma saatinde yarım örnek işareti:** taze nokta varıştan **sonraki** örnek olduğundan okuma anı yarım örnek **geri**dedir. İlk sürümde ileri alınmıştı; bu, bir örneklik (139 µs) sabit zaman hatası demekti. Düzeltildi; ölçülen gecikme artık doğru çıkıyor.

## 4. Düzeltilmeyen ya da kısmen düzeltilen etkiler

| Etki | Büyüklük | Durum |
|---|---|---|
| Enkoder okuma zamanı titreşimi (rastgele) | 5 µs: 1,2 µm (2 s) → 0,24 µm (8 s); 20 µs: 4,7 µm (2 s) → 1,0 µm (8 s) | Sistematik değil; ölçüm süresiyle azalır. Kalıcı çözüm firmware'de zaman damgası. |
| ADC Sinc4 filtresinin genlik düşümü | Tahmini n=2: 2,7·10⁻⁴, n=6: 2,4·10⁻³ | Düzeltilmedi (ADS1263 yanıt modeline bağlı). Merkezde etkisi ~2·10⁻⁴ ölçek: 152 µm'de 0,03 µm. |
| Bobin geometrisi (K_n): sarım, alan, eksene uzaklık | Mutlak ölçek | Yakınsamayı etkilemez (sıfır sıfırdır). Lab'da bilinen gradyen ve bilinen kaydırmayla doğrulanmalı. |
| Elektronik kazanç hatası | Bütün C_n aynı oranda | Merkezi etkilemez. |
| Mil sehimi (yerçekimi), eksen salgısı, bobin eğikliği | Bilinmiyor | Yönden bağımsız oldukları için iki yönlü ölçüm gidermez. Lab'da tekrarlanabilirlik ve bobin 1 / bobin 2 karşılaştırmasıyla izlenmeli. |
| Polarite / el kuralı (kanal kutupları, bobin tipi) | Merkez 180° döner ya da aynalanır | Lab'da bilinen mekanik kaydırmayla bir kez kontrol edilmeli. |
| Yüksek mertebe duyarlılığı | n=6 zayıf (gürültü n=1'in ~2,2 katı), n=7 kör | Bobin geometrisinin sonucu (sin(nα), α = 26,6°). |
| Gecikmenin hıza bağlı açı bileşeni (burulma) | Hız değişince | Gecikme ölçüldüğü hızda geçerlidir; hız değişirse yeniden ölçülmeli. |

## 5. Lab'da doğrulanması gerekenler

Simülasyon, analizin kendi içinde doğru olduğunu ve modellenen hataları giderdiğini gösterir. Gerçek düzeyleri ve modellenmemiş etkileri yalnızca lab gösterir:

1. **Tekrarlanabilirlik:** x_c, y_c saçılımı; ölçüm süresi 2 → 8 s yapılınca ~2 kat azalmalı.
2. **Gecikme:** iki-üç kez ölçülmeli; µs düzeyinde tutarlı olmalı. Sonuç `olcum.gecikme_ms`'e yazılır.
3. **Yön karşılaştırması:** gecikme ayarlıyken +23 ve −23 Hz'de aynı C_n'ler çıkmalı. Kalan fark, modellenmemiş yöne bağlı bir etkiyi gösterir.
4. **İşaret ve ölçek:** mıknatısı bilinen miktarda +x (sonra +y) kaydırın; x_c beklenen işaret ve büyüklükte değişmeli.
5. **Mutlak ölçek:** bilinen gradyen, |C₂|/r_ref ile karşılaştırılır.
6. **Referans ve iki bobin:** referans sonrası b0 > 0, a0 ≈ 0; dik iki bobin aynı C_n'leri vermeli.
7. **Sağlık ölçütleri:** sağlıklı ölçümlerde artık ve saat sıçraması hangi düzeyde? Eşikler buna göre ayarlanabilir. Sık red varsa günlükteki RS485 uyarılarına bakılmalı.

Ayrıntılı plan: `README_SURUM.md` → "Lab doğrulama planı". Simülasyon testleri: `host/tests/test_olcum_fizigi.py`, `test_merkezleme_olcer.py`, `test_kapali_dongu.py`.
