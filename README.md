# Air-core kuadrupolde elektriksel merkezleme

pEDM (proton elektrik dipol momenti) depolama halkası deneyi için geliştirilen
demirsiz (air-core) kuadrupol prototipinde, **mekanik ofsetten kaynaklanan dipol
harmoniklerini dört bobin akımına küçük asimetriler uygulayarak sıfırlayan**
yazılım. Mıknatıs mekanik olarak hareket ettirilmez; gradyen nominal değerinde
tutulur.

Donanım: dört bobin, her biri ayrı bir **ITECH IT-M3233** DC güç kaynağıyla
(sabit akım kipi, nominal 10 A) beslenir. Alan, ayrı bir bilgisayarda çalışan
rotating coil yazılımıyla ölçülür; sonuçlar bu programın arayüzüne **elle**
girilir. Polarite her enjeksiyondan önce ayrı röle donanımıyla değiştirilir;
mıknatıs ayrıca ayrı bir modülatör kartıyla 1 kHz'de %1 derinlikle modüle edilir
(program bu ikisini kontrol etmez, yalnızca durumu kaydeder ve gerektiğinde
kullanıcıdan değiştirmesini ister).

## İçindekiler

- [1. Konvansiyonlar](#1-konvansiyonlar) ← **tüm işaret/birim/numaralandırma tanımları burada**
- [2. Yöntem](#2-yöntem)
- [3. İş akışı](#3-iş-akışı)
- [4. Kurulum ve çalıştırma](#4-kurulum-ve-çalıştırma)
- [5. Modüller](#5-modüller)
- [6. Çıktılar](#6-çıktılar)
- [7. Yapılandırma referansı](#7-yapılandırma-referansı)
- [8. Güvenlik](#8-güvenlik)
- [9. Simülatör ve testler](#9-simülatör-ve-testler)
- [10. Bırakılan yaklaşım ve nedenleri](#10-bırakılan-yaklaşım-ve-nedenleri)

---

## 1. Konvansiyonlar

Bu bölüm tek referanstır. Kodda karşılığı **yalnızca** `merkezleme/harmonikler.py`
ve `merkezleme/modlar.py` dosyalarındadır; konvansiyon seçimleri koda dağıtılmamıştır
ve hepsi `yapilandirma.yaml` üzerinden değiştirilebilir.

### 1.1 Harmonik tanımı

`n = 1` dipol, `n = 2` kuadrupoldür. Referans yarıçapı `r_ref`'te karmaşık gösterim:

```
B_y + i·B_x = Σ_{n≥1} C_n · (z / r_ref)^(n−1),      z = x + i·y
C_n = B_n + i·A_n          (B: normal, A: skew)
```

Buradan doğrudan çıkanlar:

| Büyüklük | Tanım |
|---|---|
| `z = 0`'da alan | `B_y = B_1`, `B_x = A_1` |
| Gradyen | `G = B_2 / r_ref` (normal kuadrupol) |
| Skew kuadrupol oranı | `SQ/G = A_2 / B_2` |
| Roll açısı (alan çerçevesinde) | `½·arg(C_2)` |

### 1.2 Manyetik merkez (feed-down)

Kuadrupolün merkezi `z_c`'de ise alan `C_2·(z − z_c)/r_ref` olur, yani görünen
dipol `C_1 = −C_2·z_c/r_ref`. Tersine çevirerek:

```
z_c = feed_down_isareti · ( −r_ref · C_1 / C_2 )
x_c = Re(z_c),   y_c = Im(z_c)
```

Bu bir **orandır**: girilen birim (T, mT ya da normalize "units") merkezi
etkilemez. Sağlama: `1 µT` arka plan dipolü, `G = 0.2 T/m`'de `1e−6/0.2 = 5 µm`
merkez hatası verir — deneyin bilinen sayısıyla birebir.

### 1.3 Bobin numaralandırması ve polarite

Çerçevedeki etiketlere göre (etiketli taraftan bakıldığında):

```
        y
        ↑
   2 ●──┼──● 1        1: sağ üst   (135° ← 45°)
     │  │  │          2: sol üst   (135°)
 ────┼──●──┼──→ x     3: sol alt   (225°)
     │  │  │          4: sağ alt   (315°)
   3 ●──┼──● 4
```

`nominal_polarite = [+1, −1, +1, −1]`: her bobinin nominal kuadrupol polaritesi.
**İşaretli akım** = fiziksel akım genliği × bu işaret. Güç kaynakları yalnızca
pozitif akım sürer; işaret röle donanımıyla belirlenir.

### 1.4 Mod bazı (Q / H / V / M)

Modlar, fiziksel akım **genliklerine** uygulanan pertürbasyon desenleridir.
İşaretli akımda ne anlama geldikleri sağ kolonda:

| Mod | Genlik deseni | İşaretli akımda | Etkisi |
|---|---|---|---|
| `Q` | `(+1, +1, +1, +1)` | nominal kuadrupol deseni `(+,−,+,−)` | gradyen |
| `H` | `(+1, −1, −1, +1)` | `(+,+,−,−)` | yatay merkez kayması (`x_c`) |
| `V` | `(+1, +1, −1, −1)` | `(+,−,−,+)` | düşey merkez kayması (`y_c`) |
| `M` | `(+1, −1, +1, −1)` | uniform `(+,+,+,+)` | **monopol**: dipole ve gradyene katkısız |

Dördü birbirine ortogonaldir (Hadamard bazı: `VᵀV = 4I`). Mod genliği `ε`
**bağıldır**: `ε = δI / I_nominal`. Bu seçim sayesinde `dg/dε_Q = 1` çıkar ve
`R_eff` doğrudan metre birimine oturur.

`M` modunun dipole ve gradyene katkısız olması, racetrack bobinin iki demetinin
zıt yönlü akım taşımasından gelir: işaretli akımda uniform bir değişim net akım
üretmez. Bu yön `R`'nin **sıfır uzayıdır**.

### 1.5 Kontrol edilen vektör ve hedef

```
y = [x_c, y_c, g],      g = (G − G_hedef) / G_hedef
Hedef: y = [0, 0, 0]
```

`x_c, y_c` metre, `g` boyutsuzdur. `G_hedef`, başlangıçta nominal akımlarda
ölçülen gradyendir (`gradyen_hedefi_kaynagi: ilk_olcum`) ya da yapılandırmadan
gelir.

**Skew kuadrupol hedef DEĞİLDİR**; yalnızca izlenir (`SQ/G`, roll, `b3/a3/b4/a4`
ile birlikte). Nedeni [Bölüm 10](#10-bırakılan-yaklaşım-ve-nedenleri)'da.

### 1.6 Giriş biçimleri ve birimler

Rotating coil ayrı bir bilgisayarda çalıştığı için değerler elle girilir. İki
biçim de desteklenir, arayüzden anında geçiş yapılabilir:

| Biçim | Alanlar | Dönüşüm |
|---|---|---|
| `genlik_faz` | `\|C_n\|`, faz | `C_n = \|C_n\|·exp(i·faz_isareti·n·φ)` (`faz_n_carpani: true`) veya `exp(i·faz_isareti·φ)` |
| `normal_skew` | `B_n`, `A_n` | `C_n = B_n + i·A_n` |

Birim `T`, `mT` ya da normalize `units` olabilir; `r_ref` ve birim arayüzde
alanların yanında yazar. Girilen değerin türetilmiş karşılığı (`B_n`/`A_n` ya da
`|C_n|`/faz) **salt okunur** olarak hemen gösterilir.

> **`units` biçiminin sınırı:** normalize girdi mutlak ölçek taşımaz. Merkez
> hesaplanabilir (orandır) ama gradyen okunamaz; bu yüzden `units` biçiminde
> mutlak gradyen ayrı bir alandan girilir. Ayrıca akımlar sıfırken (arka plan
> ölçümü) normalizasyon tanımsızdır — arka plan çıkarma kullanılacaksa birim
> `T` ya da `mT` olmalıdır.

Arka plan **kompleks uzayda** çıkarılır: `C_n^net = C_n^ölçülen − C_n^arka_plan`.
Genlikleri çıkarmak yanlıştır; bu yüzden arka plan da aynı biçimde (faz bilgisiyle)
girilir.

### 1.7 Konvansiyon hatalarına bağışıklık

Hedef tam olarak sıfır olduğu için, **tutarlı uygulanan** bir işaret ya da eşlenik
hatası kapalı çevrimin yakınsamasını bozmaz: raporlanan merkez
`y_rapor = T·y_gerçek` biçiminde tersinir bir dönüşümse, kalibrasyon da aynı
dönüşümle ölçüldüğü için `R_rapor = T·R_gerçek` olur ve çözüm `y_rapor → 0`'a
sürer; bu da `y_gerçek → 0` demektir. Konvansiyon yalnızca **raporlanan** merkezin
işaretini/yönünü, `R_eff`'i ve teşhis çıktılarını etkiler.

Bu yüzden konvansiyon riski üç katmanda yönetilir:

1. Tüm seçimler tek modülde ve YAML'da (`faz_birimi`, `faz_n_carpani`,
   `faz_isareti`, `eslenik`, `feed_down_isareti`, `gradyen_kaynagi`).
2. Kalibrasyon, **beklenen mod–bileşen eşleşmesini** kontrol eder: `H → x_c`,
   `V → y_c`, `Q → g`. Eşleşme tersse "bobin numaralandırması ya da faz/eşlenik
   konvansiyonu ters olabilir" uyarısı verilir.
3. Faz birimini yanlış seçmek (derece/radyan) fitleri doğrusallıktan çıkarır ve
   lineerlik kontrolüne takılır.

---

## 2. Yöntem

### 2.1 Response matrix (Faz 1)

Mod eğimleri `S` (3×4, sütunlar `Q/H/V/M`) ölçülür ve bobin bazına çevrilir:

```
R = S · Vᵀ / 4          (V: ortogonal mod matrisi)
```

- Satırlar: `x_c` [m], `y_c` [m], `g` [boyutsuz]
- Sütunlar: bobin başına **bağıl** akım sapması `δI_i / I_nominal` [boyutsuz]

`H`, `V`, `Q` zorunlu; `M` isteğe bağlı kontroldür (ölçülmezse sütunu sıfır kabul
edilir — monopol dipole ve gradyene katkısız olduğu için bu fiziksel olarak
doğrudur). Mod başına 3 nokta (`−Δ, 0, +Δ`) ya da 5 nokta (`−2Δ … +2Δ`);
`Δ` varsayılan olarak nominal akımın %0.5'i. Sıfır noktası modlar arasında
paylaşılabilir ve aynı zamanda `G_hedef`'in ölçüldüğü noktadır.

**Noktalar monoton olmayan sırada alınır.** Sıralama, zaman indeksi ile `ε`
arasındaki korelasyonu en küçükleyen permütasyon seçilerek yapılır (5 noktada tam
dekorelasyon mümkündür); ayrıca modlar birbirine geçmeli (round-robin) sıralanır,
böylece yavaş bir sürüklenme tek bir modun eğimine yüklenmez. İki noktalı modlarda
(3 nokta + ortak sıfır) modlar arası yön değiştirilir.

Her bileşen için doğru fit edilir; **eğim, kesişim, artıklar ve lineerlik (R²)**
kaydedilir. R² yalnızca gerçekten tepki veren bileşenler için hesaplanır — tepki
ölçütü, tepkinin hem ilgili **toleransın** hem de fit artıklarının belirgin
üzerinde olmasıdır. (Aksi halde örneğin `H` modunda sabit sıfır civarında gezinen
`g` bileşeni, gürültüden dolayı haksız yere "lineer değil" görünür.)

Raporlanan tanılar: tekil değerler, ham ve **toleransa göre ölçeklenmiş** koşul
sayısı, `M` sütunu oranı, ve

```
R_eff = (dx_c/dε_H) / (dg/dε_Q)
```

Koşul sayısı eşiği ölçeklenmiş değere uygulanır: satırlar farklı birimde olduğu
için (m, m, boyutsuz) ham koşul sayısı birim seçiminden etkilenir ve tek başına
anlamlı değildir. Ölçeklenmiş değer "her üç hedefi de kendi toleransına,
karşılaştırılabilir akım çabasıyla kontrol edebiliyor muyum?" sorusunu yanıtlar.
Bu prototip için sağlıklı değer ≈ 8.2'dir (eşik 20).

Kalibrasyon şu durumlarda **şüpheli** işaretlenir: ölçeklenmiş koşul sayısı
eşiğin üstünde, `M` sütunu küçük değil, fitler lineer değil, ya da mod–bileşen
eşleşmesi beklenenden farklı.

### 2.2 Düzeltme (Faz 2)

```
ΔI = α · pinv(R) · (y_hedef − y)
```

`pinv` Moore–Penrose pseudo-inverse'tir (minimum normlu çözüm). **Tikhonov
regularizasyonu eklenmez:** `R` 3×4 ve rank 3 olduğu için hedef zaten tam olarak
erişilebilir; regularizasyon yalnızca yolu yavaşlatır, varış noktasını
değiştirmez. `α` varsayılan 0.9; sistem lineer olduğu için 1–3 iterasyon yeter.

`R`'nin sıfır uzayı tam olarak `M` (monopol) yönü olduğundan `pinv` bu yönde
bileşen üretmez; buna **ek olarak** her adımdan sonra `(I − I_nominal)` farkının
monopol bileşeni açıkça atılır, böylece ölçüm gürültüsü sıfır uzayında birikmez.

Uygulamadan önce önerilen akımlar, nominale göre asimetrileri, mod genlikleri ve
beklenen merkez değişimi gösterilir; kullanıcı onayı istenir.

**Durma:** `|x_c|` ve `|y_c|` merkez toleransının (varsayılan 5 µm) ve `|g|` kendi
toleransının (varsayılan 1e−3) altına inince, ya da maksimum iterasyona ulaşınca.
Tolerans, ölçülen merkez tekrarlanabilirliğinin ~2.5 katından küçük olmamalıdır;
tekrarlanabilirlik rutini (sabit akımlarda N tekrar ölçüm) bunu ölçer ve tolerans
çok sıkıysa uyarır.

### 2.3 Beklenen büyüklükler

Bu prototip için analitik olarak türetilen ve simülatörle doğrulanan ilişki:

```
R_eff = a·√2 / (4·cos α)
```

`a` = bobin yarıçapı, `α` = racetrack demetlerinin yarı açısı.

| Büyüklük | Değer | Kaynak |
|---|---|---|
| `R_eff` (a = 100 mm, α = 30°) | **40.8 mm** | analitik = simülatör (birebir) |
| `δI/I` (d = 100 µm) | **%0.245** | `d / R_eff` |
| 1 µT arka plan @ 0.2 T/m | **5.0 µm** | `ΔC_1 / G` |
| Tek adımda düzeltilebilir ofset | **≈ 577 µm** | `R_eff · sınır / √2` (sınır %2) |
| Nominal gradyen (72 sarım, 10 A) | **0.0998 T/m** | simülatör |

---

## 3. İş akışı

Güç kaynakları bu yazılımdan doğrudan kontrol edilir; rotating coil ölçümü
kullanıcı tarafından alınır ve elle girilir. Her ölçüm noktasında sıra sabittir:

1. Program dört akımı **rampa ile sıfıra** indirir, oturmasını bekler,
   "Arka plan ölçümünü alın ve girin" der.
2. Kullanıcı arka plan harmoniklerini girer ve onaylar.
3. (Gerekiyorsa) kullanıcıdan bir eylem istenir — röle ile polarite değişimi,
   modülatörün açılıp kapatılması. Akımlar sıfırdayken sorulur.
4. Program akımları hedefe **rampa ile** çıkarır, oturmasını `MEAS:CURR?` ile
   doğrular, ölçülen akımları gösterir, "Ölçümü alın ve girin" der.
5. Kullanıcı harmonikleri girer ve onaylar.
6. Program arka planı çıkarır, `y`'yi hesaplar, sonucu gösterir ve kaydeder,
   sonraki adıma geçer.

Arka planın her noktada mı yoksa N noktada bir mi alınacağı yapılandırılabilir
(varsayılan: her noktada). Kullanıcı arka plan adımını atlarsa son geçerli arka
plan kullanılır ve bu durum CSV'ye `arka_plan_taze = 0` ve bir not olarak
kaydedilir.

Elle giriş sayısı ve tahmini süre başlamadan önce gösterilir:

| Kalibrasyon | Nokta | Arka plan her noktada | Arka plan 3 noktada bir |
|---|---|---|---|
| 3 nokta (H,V,Q,M) | 9 | 18 giriş | 12 giriş |
| 5 nokta (H,V,Q,M) | 17 | 34 giriş | 23 giriş |

### Rutinler

- **Tekrarlanabilirlik:** sabit akımlarda N tekrar ölçüm; `σ(x_c), σ(y_c), σ(g)`
  raporlanır ve tolerans yeterliliği kontrol edilir. Sonuç, yazım hatası
  doğrulamasının ölçeği olarak da kullanılır.
- **Polarite doğrulaması:** düzeltilmiş akımlar uygulanır ve ölçüm alınır;
  akımlar sıfırlanır, kullanıcıdan röle ile polariteyi değiştirmesi istenir; aynı
  akım genlikleri ters polariteyle uygulanır ve ölçüm alınır.
  `merkez(+) − merkez(−)` raporlanır. Her iki ölçümde de arka plan çıkarma sırası
  uygulanır.
- **Modülatör karşılaştırması:** düzeltilmiş merkez, modülatör kapalı ve açık
  durumlarında ölçülüp karşılaştırılır. Program modülatörü kontrol etmez;
  kullanıcıdan durumu değiştirmesini ister ve hangi durumda ölçüldüğünü kaydeder.

### Kesinti ve devam

Her adımdan sonra durum dosyası **atomik olarak** yazılır (geçici dosya +
`os.replace`). Program kapanır ya da çökerse `--devam` ile kaldığı yerden devam
edilir. Duraklat/Devam ve "DURDUR ve akımları sıfırla" her an kullanılabilir.

---

## 4. Kurulum ve çalıştırma

```bash
pip install numpy pyyaml PyQt5          # arayüz için
pip install pyvisa pyvisa-py            # yalnızca gerçek donanım için
pip install pytest                      # testler için
```

```bash
python -m merkezleme                    # KURU ÇALIŞMA, elle giriş (varsayılan)
python -m merkezleme --deneme           # deneme kipi: alanlar simülatörden dolar
python -m merkezleme --otomatik         # arayüzsüz, simülatörle baştan sona
python -m merkezleme --dosyadan         # yarı otomatik: alanlar dönen bobin
                                         # programından dolar, onay yine kullanıcıda
python -m merkezleme --otomatik --dosyadan --canli   # TAM OTOMATİK, gerçek donanım
python -m merkezleme --devam            # yarım kalmış son çalıştırmadan devam
python -m merkezleme --kalibrasyon calistirmalar/<tarih>/kalibrasyon.json
python -m merkezleme --canli            # GERÇEK DONANIM (açık bayrak zorunlu)
```

**Varsayılan kip kuru çalışmadır:** SCPI komutları kaydedilir ama cihaza
gönderilmez. Gerçek donanım için `--canli` zorunludur; yapılandırmada `kip: canli`
yazsa bile bayrak verilmediyse kuru çalışmada devam edilir ve uyarı basılır.
Arayüzde kip etiketi canlıda dikkat çekecek şekilde işaretlenir (renkli temada
kırmızı, monokrom temalarda ters video).

### Temalar

Üç tema var; arayüzün sağ üstündeki seçiciden **çalışma sırasında** değiştirilebilir,
başlangıç değeri `genel.tema` ya da `--tema` ile verilir:

| Tema | Açıklama |
|---|---|
| `varsayilan` | Sistem teması (açık zemin, renkli vurgular) |
| `fosfor_yesil` | P1 fosfor yeşili monokrom CRT |
| `fosfor_turuncu` | P3 fosfor amber (turuncu) monokrom CRT |

```bash
python -m merkezleme --deneme --tema fosfor_yesil
python -m merkezleme --deneme --tema fosfor_turuncu
```

Monokrom temalarda renk yerine **ters video** ve parlaklık kademeleri kullanılır
(gerçek CRT'lerde vurgu böyle yapılıyordu); bu yüzden "tehlike" rengi yoktur,
DURDUR düğmesi ters videoya geçer. Yazı tipi baştan sona monospace'tir.

Arayüzdeki bütün renkler `merkezleme/tema.py` içindedir; `arayuz.py` hiçbir rengi
kendi içinde tanımlamaz. Yeni bir tema eklemek için oraya bir `Tema` kaydı
eklemek yeterlidir. Stil sayfası uygulama geneline verildiği için `QMessageBox`
gibi ayrı pencereler de temalı görünür.

### Dosyadan otomatik ölçüm (`--dosyadan`)

Dönen bobin programı **aynı bilgisayarda** ayrı bir süreç olarak çalışıyorsa,
elle girişin yerini paylaşımlı bir kilit dosyası alabilir. Protokol, dosyanın
VARLIĞI/YOKLUĞUnu tek sinyal olarak kullanır:

* kilit **yok** → "ölç" sinyali: sıra dönen bobin programındadır.
* kilit **var** → "veri hazır" sinyali: sıra bu programdadır; dosyanın
  içeriği ölçülen harmonikleri taşır.

Bu program her ölçüm isteğinde önce eski kilidi siler (akımlar zaten
rampalanıp oturmuş olur - "yeni akım hazır, ölç"), sonra yeni kilit belirene
kadar yoklar. Dönen bobin tarafı kendi verisini önce geçici bir dosyaya yazıp
ardından **atomik olarak** (`os.rename`) kilit dosyasının adına taşımalıdır;
böylece hiçbir zaman yarım yazılmış bir dosya okunmaz. Dosya içeriği JSON'dur:

```json
{"b0": 1.2e-06, "a0": -4.8e-07, "b1": 2.4941e-03, "a1": -5.0e-06}
```

`b`: normal, `a`: skew; `0` = dipol, `1` = kuadrupol (bu programın n=1/n=2'si).
Değerler `harmonikler.birim` biriminde kabul edilir (elle giriş kutularıyla
aynı sözleşme). Dosya yolu ve zamanlamalar `dosya_girisi` bölümünde
(bkz. §7) ayarlanır.

`--dosyadan` tek başına **yarı otomatik** çalışır: arayüz açık kalır, alanlar
dosyadan otomatik dolar, ama "Onayla" ve "Önerilen akımları UYGULA" düğmelerine
yine kullanıcı basar. `--otomatik --dosyadan` ile birleşince **tam otomatik**
olur (arayüzsüz, `otomatik_yurut` onayları da kendisi verir); bu kombinasyon
`--canli` ile gerçek donanımda da kullanılabilir — `--otomatik` tek başına
(`--dosyadan` olmadan) yalnızca simülatörle çalıştığı için `--canli` ile
birlikte reddedilir. Beklenmeyen bir hata ya da zaman aşımında (dönen bobin
programı yanıt vermezse) akımlar güvenli şekilde sıfıra indirilir.

---

## 5. Modüller

| Modül | Sorumluluk |
|---|---|
| `yapilandirma.py` | YAML → tip açıklamalı dataclass'lar, doğrulama. Kodda gizli sabit yok. |
| `harmonikler.py` | **Tüm konvansiyonlar**: giriş biçimleri, arka plan, feed-down, `g`, izleme |
| `modlar.py` | Bobin numaralandırma, Q/H/V/M mod bazı, `R` kurulumu, monopol çıkarma |
| `guc_kaynagi.py` | `GucKaynagi` (IT-M3233), `KaynakGrubu`, `SahteGucKaynagi`, kuru çalışma |
| `kalibrasyon.py` | Nokta planı, fitler, `R`, SVD, `R_eff`, şüphe bayrakları, JSON |
| `duzeltme.py` | `pinv` düzeltmesi, güvenlik değerlendirmesi, yakınsama, tekrarlanabilirlik |
| `dogrulama.py` | Mertebe kontrolü ve "olası yazım hatası" |
| `olcum_kaynagi.py` | Soyut ölçüm kaynağı (`ElleGiris` / `SimulatorGirisi` / `DosyaGirisi`), alan dönüşümleri |
| `is_akisi.py` | Adım sırası durum makinesi, görev kuyruğu, durum dosyası, rutinler |
| `arayuz.py` | PyQt5 arayüzü |
| `tema.py` | Arayüz temaları ve **bütün renkler** (varsayılan + iki fosfor CRT) |
| `simulator.py` | 2D çizgi akımı mıknatıs modeli |
| `kayit.py` | Tarihli çalıştırma klasörü, CSV/JSON/SCPI günlüğü/Markdown özeti |
| `ana.py` | Komut satırı girişi |

`is_akisi.py` bloklamaz: `olcum_gonder`, `duzeltmeyi_onayla`,
`kullanici_eylemini_onayla` gibi çağrılarla ilerler. Arayüz bunları düğmelerden,
testler `otomatik_yurut` ile döngüden çağırır — aynı durum makinesi.

### Güç kaynağı katmanı

`eski/guc_kaynagi_orijinal.py` temel alınmıştır; **kullanılan SCPI komut kümesi
aynıdır ve genişletilmemiştir**: `*CLS`, `*IDN?`, `SYST:REM`, `VOLT`, `CURR`,
`SYST:ERR?`, `OUTP ON/OFF`, `MEAS:VOLT?`, `MEAS:CURR?`.

Eklenenler: `olcumleri_oku()` float döndürür ve ayrıştırma hatalarını yakalar;
her yazmadan sonra `SYST:ERR?` kontrol edilir; sabit akım kipinde `VOLT` bir uyum
sınırı olduğu için akımdan **önce** yazılır; akımlar asla tek adımda
değiştirilmez (yazılımda rampa, A/s), rampa sonunda oturma `MEAS:CURR?` ile
doğrulanır ve ardından bekleme uygulanır; bobin endüktif olduğu için (≈6.5 mH)
akım sıfır değilken `OUTP OFF` kullanılmaz. `KaynakGrubu` dört kanalı eş zamanlı
adımlarla rampalar, hepsini okur ve acil durumda hepsini rampa ile sıfırlar.

---

## 6. Çıktılar

Tüm çıktılar **düz metin**tir; ikili biçim kullanılmaz. Her çalıştırma kendi
tarihli klasörüne yazar:

```
calistirmalar/2026-09-17_143500/
    yapilandirma.yaml     kullanılan yapılandırmanın kopyası (tekrarlanabilirlik)
    olcumler.csv          her adım: zaman, adım türü, dört akımın ayar ve ölçülen
                          değerleri, girilen tüm harmonikler (ham / arka plan /
                          net), hesaplanan y, izleme büyüklükleri
    kalibrasyon.json      R, tekil değerler, fit parametreleri, R_eff
    scpi_gunlugu.txt      gönderilen (kuru çalışmada kaydedilen) komutlar
    durum.json            kaldığı yerden devam için durum dosyası
    ozet.md               çalıştırma sonu Markdown özeti
```

Özet şunları içerir: başlangıç ve son merkez, son akımlar ve nominale göre
asimetrileri, iterasyon sayısı, `R`'nin tekil değerleri, `R_eff`, `SQ/G`,
düzeltme öncesi ve sonrası `b3/a3/b4/a4`, arka plan değerleri ve değişimi,
tekrarlanabilirlik ve notlar.

---

## 7. Yapılandırma referansı

Tüm yapılandırma tek dosyadadır: **`yapilandirma.yaml`**. Öne çıkan anahtarlar:

| Bölüm | Anahtar | Varsayılan | Anlamı |
|---|---|---|---|
| `genel` | `kip` | `kuru` | `kuru` \| `canli` (canlı için `--canli` şart) |
| | `modulator_acik` | `false` | 1 kHz modülatör durumu (yalnızca kaydedilir) |
| | `tema` | `varsayilan` | `varsayilan` \| `fosfor_yesil` \| `fosfor_turuncu` |
| `miknatis` | `nominal_akim_A` | `9.5` | Bobin başına nominal akım |
| | `bobin_acilari_derece` | `[45,135,225,315]` | Bobin konumları |
| | `nominal_polarite` | `[1,-1,1,-1]` | Nominal kuadrupol polaritesi |
| | `gradyen_hedefi_kaynagi` | `ilk_olcum` | `G_hedef` ilk ölçümden mi, yapılandırmadan mı |
| `modlar` | `Q/H/V/M` | Hadamard | Genlik bazında mod desenleri (ortogonal olmalı) |
| `harmonikler` | `r_ref_mm` | `25.0` | Referans yarıçapı |
| | `giris_bicimi` | `genlik_faz` | `genlik_faz` \| `normal_skew` |
| | `birim` | `T` | `T` \| `mT` \| `units` |
| | `faz_birimi`, `faz_n_carpani`, `faz_isareti` | `derece`, `true`, `1` | Faz konvansiyonu |
| | `feed_down_isareti`, `eslenik` | `1`, `false` | Merkez konvansiyonu |
| | `arka_plan_cikarma` | `tum` | `tum` \| `yalniz_dipol` |
| `guc_kaynaklari` | `visa_adresleri` | `ASRL1..4::INSTR` | Dört kaynağın adresi (bobin sırasıyla) |
| | `uyum_gerilimi_V` | `20.0` | Sabit akım kipinde uyum sınırı |
| | `rampa_hizi_A_s` | `0.5` | Rampa hızı |
| | `akim_tolerans_A` | `0.02` | Oturma doğrulama toleransı |
| `guvenlik` | `bobin_basi_max_akim_A` | `10.0` | Asla aşılmaz (güç kaynağı donanım tavanı) |
| | `adim_basi_max_bagil_degisim` | `0.02` | Bobin başına, her iterasyonda |
| | `nominale_gore_max_asimetri` | `0.05` | Bobin başına, toplam |
| `kalibrasyon` | `nokta_sayisi` | `3` | `3` \| `5` |
| | `delta_bagil` | `0.005` | `Δ` (nominal akımın oranı) |
| | `ortak_sifir_noktasi` | `true` | Sıfır noktası modlar arasında paylaşılsın mı |
| | `arka_plan_her_n_noktada` | `1` | 1 = her noktada |
| `duzeltme` | `alpha` | `0.9` | Düzeltme oranı |
| | `merkez_toleransi_um` | `5.0` | `\|x_c\|` ve `\|y_c\|` eşiği |
| | `g_toleransi` | `0.001` | `\|g\|` eşiği |
| | `monopol_cikar` | `true` | Her adımda monopol bileşenini at |
| `dogrulama` | `yazim_hatasi_sapma_carpani` | `5.0` | Beklenenden kaç kat sapma uyarı verir |
| `simulator` | `bobin_yaricapi_m`, `demet_yari_acisi_derece` | `0.10`, `30.0` | `R_eff`'i belirler |
| `dosya_girisi` *(isteğe bağlı)* | `kilit_dosyasi` | `veri_kilidi/.kilit` | `--dosyadan` kilit/veri dosyasının yolu |
| | `zaman_asimi_s` | `30.0` | Bu sürede veri gelmezse hata (akımlar sıfırlanır) |
| | `yoklama_araligi_s` | `0.2` | Kilit dosyasının yoklanma aralığı |

---

## 8. Güvenlik

- Bobin başına maksimum akım asla aşılmaz; negatif akım reddedilir (işaret röle
  ile değiştirilir).
- Adım başı bağıl değişim ve nominale göre toplam asimetri sınırlanır. Bir çözüm
  sınırı aşıyorsa **uygulanmaz**; neden kaydedilir ve akış durur.
- Akımlar asla tek adımda değiştirilmez; endüktif bobinde akım sıfır değilken
  çıkış kapatılmaz.
- Beklenmeyen hata, iletişim kopması, pencerenin kapatılması ya da kullanıcı
  kesintisinde tüm akımlar rampa ile sıfıra indirilir.
- Rotating coil başka bir bilgisayarda olduğu için tek gerçek hata kaynağı yazım
  hatasıdır. Üç katman: (a) mertebe kontrolü, (b) kalibrasyon varken beklenen
  `y`'den sapma için "olası yazım hatası" uyarısı ve yeniden onay, (c) girişin
  fiziksel karşılığının (`x_c`, `y_c`, `g`) yazarken **canlı** gösterilmesi.

---

## 9. Simülatör ve testler

`simulator.py`, mıknatısı 2 boyutlu çizgi akımlarıyla modeller: dört racetrack
bobin, her biri `a ≈ 10 cm` yarıçapta ve kutup ekseni etrafında `±α` açılarında
**iki zıt yönlü** iletken demetiyle; bobin başına radyal/açısal yerleşim ve sarım
sayısı hataları; mıknatıs ofseti `(dx, dy)` ve roll; yavaş değişebilen uniform
arka plan; her harmoniğe ölçüm gürültüsü ve sürüklenme. Çıktısı, elle girişle
**aynı biçimdedir**.

Gürültü ölçeği sabittir (nominal `|C_2|`); anlık `|C_2|` kullanılmaz, çünkü arka
plan ölçümünde akımlar sıfır olduğundan anlık değer sıfıra gider ve ölçek
anlamsızlaşır.

```bash
python -m pytest tests/ -q                 # 162 test, ~2 s
QT_QPA_PLATFORM=offscreen python -m pytest tests/ -q   # arayüz testleri dahil
```

Testler donanımsız ve elle girişsiz çalışır; elle giriş katmanı soyut olduğu için
simülatöre bağlanır, güç kaynakları için sahte sürüm kullanılır. Kapsanan
senaryolar: ≤3 iterasyonda yakınsama (rastgele ofsetlerden), `g`'nin tolerans
içinde kalması, akım asimetrisinin `d/R_eff` olması, monopol bileşeninin çok
sayıda iterasyonda büyümemesi, `SQ/G`'nin pratikte değişmemesi, 3 ve 5 noktalı
kalibrasyondan çıkan `R_eff`'in simülatör geometrisiyle tutarlılığı, arka plan
çıkarmanın etkisi, yazım hatası uyarısının bilerek bozulmuş girişi yakalaması,
durum dosyasından devam, güvenlik sınırları ve arayüzün tüm akışı.

`tests/test_sq_kotu_kosulluluk.py` bir gereksinimi doğrulamaz; **belgeleme
amaçlıdır** ve aşağıdaki bölümü sayısal olarak gösterir.

---

## 10. Bırakılan yaklaşım ve nedenleri

Bu depoda önce farklı bir yaklaşım denenmişti: `[Bx, By, G, SQ]` üzerinde doğrudan
4×4 response matrix, `ΔI` üzerinde Tikhonov regularizasyonu ve yüksek damping.
Eski dosyalar `eski/` klasöründe, o dönemin belgesi `eski/README_eski.md`
içindedir. Bırakılma nedenleri, testlerle de doğrulanmış hâlde:

1. **Skew kuadrupol dört bobin akımıyla kontrol edilemez.** 4 katlı simetrik
   düzende `C_2` her akım kombinasyonu için saf gerçektir: `A_2 ≡ 0`. Ölçülen
   `d(SQ/G)/dε` ideal geometride ~1e−15'tir (yani tam olarak sıfır). SQ'ya ancak
   bobinlerin küçük açısal yerleşim hataları üzerinden zayıf bir yol açılır:
   5 mrad mertebesinde hatalarla en güçlü tutamak ~7e−3/birim `ε` olur, ve 1 mrad
   roll'dan gelen tipik `SQ/G = 0.002`'yi sıfırlamak **%29 bağıl akım değişimi**
   ister — izin verilen toplam asimetri %5. SQ'yu hedefe koymak problemi kötü
   koşullu yapar ve akımları nominalden çok uzağa sürükler.
2. **Monopol modu bir sıfır uzayı yönüdür.** Uniform (işaretli akımda uniform)
   akım modu dipolü ve gradyeni değiştirmez, dolayısıyla akımların serbestçe
   kayabileceği bir yöndür. Bu yaklaşımda `pinv` o yönde bileşen üretmez ve her
   adımda bileşen açıkça atılır.
3. **T ile T/m'yi aynı normda toplamak.** Eski kurulumda farklı birimdeki
   büyüklükler aynı normda toplanıyor ve yalnızca adım büyüklüğünü cezalandıran
   bir regularizasyon kullanılıyordu; bu, ağırlıklı ve keyfi bir ödünleşmeye
   zorluyordu. Yeni kurulumda `R` 3×4 ve rank 3 olduğu için hedef **tam olarak**
   erişilebilir: satırları toleranslarına göre ölçeklemek çözümü değiştirmez
   (testle doğrulanmıştır), yani birim karışımı sorunu ortadan kalkar.
