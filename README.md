# dipole-correction-at-quad

Bir quadrupol mıknatısta mekanik hizalama hatası (ofset), rotating coil
ölçümlerinde istenmeyen bir **dipol alan** (Bx, By) olarak ortaya çıkar.
Bu depo, mıknatısı fiziksel olarak hareket ettirmeden, sadece bobin
akımlarını değiştirerek bu dipol alanı aktif olarak bastırmayı hedefleyen
iki uygulama içerir. İkisi de aynı fikrin farklı olgunluk seviyelerindeki
uygulamalarıdır; ikinci uygulama (`quad_dipole_compensation.py`) birincinin
(`minimize_dipole.py`) yerini almak üzere, daha genel ve daha az varsayıma
dayalı bir yöntemle yazılmıştır.

## İçindekiler

- [1. Problem](#1-problem)
- [2. `minimize_dipole.py` — ilk uygulama](#2-minimize_dipolepy--ilk-uygulama)
- [3. `quad_dipole_compensation.py` — response-matrix tabanlı uygulama](#3-quad_dipole_compensationpy--response-matrix-tabanlı-uygulama)
- [4. Neden quadrupol gradyenti (G) burada hedeflenmiyor](#4-neden-quadrupol-gradyenti-g-burada-hedeflenmiyor)
- [5. Dosya yapısı](#5-dosya-yapısı)
- [6. Kurulum ve çalıştırma](#6-kurulum-ve-çalıştırma)
- [7. Parametreler](#7-parametreler)
- [8. Olası geliştirmeler](#8-olası-geliştirmeler)

---

## 1. Problem

Dört bağımsız güç kaynağıyla beslenen (`I0, I1, I2, I3`) bir air-core
quadrupol mıknatısı düşünün. Mıknatıs mekanik olarak mükemmel
hizalanmamışsa (merkez kayması, hafif dönüklük vb.), quadrupol alanının
üzerine küçük bir dipol bileşeni biner. Bu, demet üzerinde istenmeyen bir
orbit bükülmesine (kick) yol açar.

Bu dipolü düzeltmenin iki yolu vardır:

1. Mıknatısı mekanik olarak yeniden hizalamak (yavaş, geri dönüşü zor,
   genelde demet zamanı kaybettirir).
2. Bobin akımlarını asimetrik hale getirerek, mıknatısı elektriksel
   olarak "sanki doğru hizalanmış gibi" davranmaya zorlamak.

Bu depodaki uygulamalar ikinci yolu, yani **sadece akım üzerinden**
düzeltmeyi uygular.

---

## 2. `minimize_dipole.py` — ilk uygulama

En basit senaryo: rotating coil yerine, mıknatısın **üstünde** ve
**altında** iki dikey konumda ölçülen `bx1`, `bx2` alan değerleri
kullanılır.

```
Bx1 (dipol)     = (bx1 + bx2) / 2      # ortalama
Bx2 (quadrupol) = (bx1 - bx2) / 2      # fark
```

Bu iki büyüklüğün hedef değerlerden sapması (`D1`, `D2`), sabit öğrenme
oranlarıyla (`learning_rate_dipol`, `learning_rate_quadrupol`) doğrudan
akımlara uygulanır:

- `I0` sadece dipol hatasına tepki verir.
- Dört akımın hepsi, eşit ve aynı yönde, quadrupol hatasına tepki verir.

Bu kural mıknatısın gerçek elektriksel davranışından (response matrix)
değil, elle yazılmış sabit bir varsayımdan gelir — yani "I0 dipolü, hepsi
birlikte quad'ı kontrol eder" varsayımı doğru olmayabilir. Bu, ikinci
uygulamanın yazılma sebebidir.

*(Not: bu dosyadaki `config.py` bağımlılığı önceden depoda eksikti; artık
`config.py` içinde her iki uygulama için de gerekli anahtarlar tanımlı.)*

---

## 3. `quad_dipole_compensation.py` — response-matrix tabanlı uygulama

İkinci uygulama, mıknatısın gerçek elektriksel davranışını **varsaymak**
yerine **ölçer**, ve düzeltmeyi sabit bir kuralla değil, **regularized
least squares** optimizasyonuyla hesaplar. Girdi olarak sadece rotating
coil'den (ya da eşdeğer bir ölçüm sisteminden) okunan yatay ve dikey
dipol alanları (`Bx`, `By`) kullanılır — metin kutusuna elle girilir.

### Ölçüm ve hedef

```
M = [Bx, By]        # ölçüm vektörü
Target = [0, 0]      # ilk girilen dipol alanlar da dahil, hedef HER ZAMAN sıfır
e = Target - M = -M  # hata vektörü
```

### Faz 1 — Response matrix kalibrasyonu (bir kez)

Mıknatısın `I0..I3` akımlarının `Bx, By`'yi nasıl etkilediği bilinmiyor,
bu yüzden önce ölçülür. Uygulama bir sihirbaz gibi çalışır:

1. Nominal akımlarda 1 ölçüm.
2. Her bobin için sırayla `+ΔI` ve `-ΔI` uygulanıp birer ölçüm (4 bobin ×
   2 = 8 ölçüm). Toplam **9 ölçüm**.
3. Merkezi fark (central difference) ile response matrix'in her kolonu
   hesaplanır:

   ```
   R[:, i] = (M(I_i + ΔI) - M(I_i - ΔI)) / (2·ΔI)
   ```

   Sonuç, `Bx, By`'nin `I0..I3`'e duyarlılığını veren **2×4** bir matris
   `R`'dir.

Bu adımlar tamamen otomatik değildir: uygulama her adımda hangi
akımların uygulanması gerektiğini gösterir, kullanıcı güç kaynaklarını
elle o değerlere ayarlar ve rotating coil ölçümünü girer (aradaki
"gerçek dünya" adımı — akım uygulama ve ölçüm — otomatikleştirilmemiştir,
çünkü bu uygulamanın donanım kontrolü yoktur).

Sonuç `response_matrix.json` dosyasına kaydedilir; bir sonraki
çalıştırmada bu dosya varsa kalibrasyon adımı otomatik atlanır.

### Faz 2 — Regularized least squares döngüsü

Her iterasyonda:

```
ölç Bx, By
e = -[Bx, By]
ΔI çöz:  (RᵀR + λI) ΔI = Rᵀe        # regularized least squares
I_new = I_old + α·ΔI                # damping (kademeli uygulama)
```

`‖e‖ < tolerance` olduğunda yakınsama bildirilir (optimizasyon
istenirse yine de devam ettirilebilir).

**Neden regularization (λ‖ΔI‖²) gerekli:** `R` 2×4 olduğu için sistem
**underdetermined**'dir — aynı `Bx, By` düzeltmesini veren sonsuz sayıda
`ΔI` vardır (aralarındaki fark `R`'nin 2 boyutlu null space'ine aittir,
yani `R·ΔI_null = [0,0]`: Bx,By'yi hiç değiştirmeyen ama akımları
gereksiz yere oynatan yönler). Regularized least squares çözümü, λ→0
limitinde bu sonsuz çözüm kümesinden **minimum-norm** olanı seçer —
yani "aynı düzeltmeyi en az akım değişikliğiyle yapan" çözümü. Bu hem
sayısal olarak kararlıdır (R kötü koşullu olsa bile) hem de akımlarda
gereksiz gezinmeyi engeller.

### Kalıcılık ve loglama

- `response_matrix.json`: kalibrasyon sonucu (R, nominal akımlar, ΔI,
  zaman damgası). Sonraki çalıştırmalarda otomatik yüklenir.
- `logs/dipol_duzeltme_logu.txt`: her iterasyonun `Bx, By, ‖e‖,
  I0..I3` değerleri.

---

## 4. Neden quadrupol gradyenti (G) burada hedeflenmiyor

Bu, projenin en önemli tasarım kararlarından biri, bu yüzden ayrı bir
başlıkta açıklıyoruz (kaynak: `quad_dipole_compensation.py` docstring'i).

Alternatif bir tasarım (bu depoya dahil edilmedi, ama değerlendirildi),
ölçüm vektörünü `[Bx, By, G, SQ]` olacak şekilde 4 harmoniğe genişletip,
ilk ölçülen `G` değerini de hedef olarak sabitleyerek quadrupolü açıkça
korumayı önerir. Bu depodaki uygulama **bilinçli olarak bunu yapmaz**:

- İdeal bir 4-bobinli air-core quadrupolde, tasarım simetrisi gereği
  "quad modu" (bobinlerin `+,-,+,-` alternatif işaretli, ortak ölçekte
  birlikte değişmesi) ile "dipol modları" birbirine yaklaşık
  **ortogonaldir**. Mekanik ofset bu ortogonalliği hafifçe bozduğu için
  Bx, By ile G arasında küçük bir coupling oluşur — bu uygulamanın
  düzelttiği tam olarak budur. Dolayısıyla bu düzeltmenin G'ye sızıntısı
  da doğası gereği küçüktür.
- Regularized least squares zaten minimum-norm çözümü seçtiği için
  (bkz. Faz 2), null space yönünde **gereksiz** bir G sürüklenmesi
  olmaz; kalan küçük sızıntı sadece Bx,By'yi düzeltmek için zorunlu
  olan akım değişiminin yan etkisidir.
- Gerçek hızlandırıcı ortamında bu düzeltme, **LOCO (Linear Optics from
  Closed Orbit)** gibi bir optik kalibrasyon adımından **önce**
  uygulanır. LOCO, kaynağı ne olursa olsun (mekanik ofset, bu
  düzeltmenin kendisi, sıcaklık sürüklenmesi vb.) entegre gradyent
  hatalarını orbit response matrix üzerinden ölçüp global quad
  trim'leriyle telafi eder — bu zaten onun standart işidir. Bu yüzden
  G için bu algoritma içinde ayrıca bir hedef/kısıt tanımlamaya gerek
  yoktur; iş LOCO'ya bırakılır.

**Bu kararın tek varsayımı — çalıştırma sırası:** Bu uygulama LOCO'dan
(veya herhangi bir optik ölçüm/kalibrasyon adımından) **önce**
çalıştırılmalıdır, commissioning'in erken bir adımı olarak. LOCO zaten
çalıştırılıp makine o hâle göre kalibre edildikten **sonra** bu
uygulama tekrar çalıştırılırsa (örn. yeniden hizalama sonrası), taze
bir G sapması LOCO'suz ortada kalabilir ve ayrıca telafi edilmesi
gerekebilir.

G'yi yine de korumak istenirse, `quad_dipole_compensation.py`
docstring'inde iki genişletme yolu tarif edilmiştir: G'yi düşük
ağırlıklı bir "soft penalty" olarak ölçüm vektörüne eklemek, ya da
kalibrasyonda `R`'nin G satırını da ölçüp düzeltmeyi onun null
space'ine projekte ederek G'ye birinci mertebede hiç dokunulmamasını
garanti etmek.

---

## 5. Dosya yapısı

```
config.py                      İki uygulama için de ortak parametreler (CONFIG sözlüğü)
minimize_dipole.py              İlk uygulama (iki-prob, sabit öğrenme oranı)
dipole_core.py                  quad_dipole_compensation.py'nin PyQt5'ten bağımsız
                                 çekirdek matematiği: kalibrasyon adımları, response
                                 matrix hesabı, regularized least squares, damping,
                                 response matrix'in JSON'a kayıt/yükleme.
quad_dipole_compensation.py     İkinci uygulama: PyQt5 arayüzü, kalibrasyon
                                 sihirbazı ve düzeltme döngüsü.
response_matrix.json            (çalıştırınca oluşur, .gitignore'da) Kalibrasyon
                                 sonucu — R matrisi, nominal akımlar, ΔI.
logs/                           (çalıştırınca oluşur, .gitignore'da) İterasyon logları.
```

`dipole_core.py`'nin PyQt5'e bağımlı olmaması bilinçlidir: bu sayede
çekirdek algoritma GUI olmadan da (örn. otomatik testlerle, ya da
ileride bir komut satırı / donanım-otomasyonlu sürümde) kullanılıp
doğrulanabilir.

---

## 6. Kurulum ve çalıştırma

```bash
pip install numpy matplotlib PyQt5

# İlk uygulama
python minimize_dipole.py

# İkinci (önerilen) uygulama
python quad_dipole_compensation.py
```

`quad_dipole_compensation.py` ilk çalıştırıldığında `response_matrix.json`
yoksa otomatik olarak Faz 1 kalibrasyon sihirbazını başlatır. Kalibrasyon
tamamlandıktan sonra bir daha kalibre etmeye gerek kalmaz; arayüzdeki
"Yeniden Kalibre Et" butonu ile istenildiğinde tekrarlanabilir (örn.
mıknatısın fiziksel durumu değiştiyse).

---

## 7. Parametreler

Tüm parametreler `config.py` içindeki `CONFIG` sözlüğünde tanımlıdır.

`quad_dipole_compensation.py` için:

| Anahtar | Anlamı | Tipik değer |
|---|---|---|
| `nominal_akimlar` | Kalibrasyonun ve düzeltme döngüsünün başlangıç akımları `[I0,I1,I2,I3]` (A) | mıknatısın çalışma akımı |
| `delta_i_kalibrasyon` | Kalibrasyonda her bobine uygulanan sapma ΔI (A) | nominal akımın ~%0.5–2'si |
| `lambda_regularizasyon` | Regularization katsayısı λ | 0.001–0.1 |
| `alpha_damping` | Damping katsayısı α (her iterasyonda uygulanan düzeltme oranı) | 0.2–0.5 |
| `tolerance` | Yakınsama eşiği ‖[Bx,By]‖ (mT) | ölçüm hassasiyetine göre |
| `response_matrix_path` | Kalibrasyon sonucunun kaydedileceği/okunacağı dosya | `response_matrix.json` |
| `log_dir` | İterasyon loglarının yazılacağı klasör | `logs` |

`minimize_dipole.py` için: `learning_rate_dipol`, `learning_rate_quadrupol`,
`bx1_target`, `bx2_target`, `nominal_akim`.

---

## 8. Olası geliştirmeler

- Güç kaynağı ve rotating coil ile doğrudan haberleşme (şu an her iki
  uygulama da "kullanıcı elle akımı ayarlar, elle ölçümü girer"
  modelindedir); bu otomatikleştirilirse Faz 1 kalibrasyonu da tam
  otomatik hale gelir.
- G (quadrupol gradyenti) korumasının açık şekilde eklenmesi gerekirse,
  bkz. [Bölüm 4](#4-neden-quadrupol-gradyenti-g-burada-hedeflenmiyor)'teki
  iki genişletme yolu (soft penalty veya null-space projeksiyonu).
- `minimize_dipole.py`'nin de response-matrix tabanlı yaklaşıma
  taşınması (şu an sabit/varsayılan bir coupling modeli kullanıyor).
