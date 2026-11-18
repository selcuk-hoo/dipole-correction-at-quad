# İstem: Dönen bobin için yerçekimi açı referansı (ivmeölçer) ve yerçekimine göre skew harmonikleri

*Hazırlayan: Claude (18 Kasım 2026). İvmeölçer sisteme takıldıktan sonra yeni bir Claude Code
oturumunda bu dosyanın tamamını istem olarak verin. Klasördeki `CLAUDE.md`/`README.md` de okunmalı.*

---

## Görev

`dipole-correction-at-quad` deposunda, dönen bobinin açı sıfırını **yerçekimine** bağlayan bir referans adımı
ve bunu kullanarak **yerçekimine göre normal/skew harmonikleri** (b_n, a_n; özellikle kuadrupolün skew açısı)
veren bir çıktı ekle. Rotor kartına bir ivmeölçer takıldı. Aşağıdaki bağlamı oku, önce açık soruları
kullanıcıya sor, sonra planı onaylatıp uygula. Donanımı (motor, akım) çalıştıran her ölçüm için ayrı onay al.

## Bağlam: neden gerekli, şu an ne var

**Enkoder artımlı.** `donen_bobin/src/stator.cpp`: kuadratür enkoder, `current_enc_ppr = 3600` sayım/tur,
index (Z) kullanılmıyor; sıfır, stator açıldığı ya da `CMD_CLEAR_PULSE` geldiği andaki konum. Yazılımdaki faz
ofseti bütün kayıtlarda 0. Sonuç: bobin çerçevesindeki her açı oturumdan oturuma keyfi kayar. Kuadrupolün
bobin çerçevesindeki açısı ψ = arg(C₂)/2, 6–17 Kasım'da −82°, −50°, +6°, +32° çıktı; mıknatıs dönmedi.

**18 Kasım'da yapılanlar (bunları bozma, üzerine kur):**
- `merkezleme/kalibrasyon.py`: `kuadrupol_acisi(c2)`, `KalibrasyonSonucu.kuadrupol_acisi_rad`,
  `KalibrasyonSonucu.dondurulmus(aci, isaret)`, `kayitli_kalibrasyonu_yukle`, `csvden_kuadrupol_acisi`.
- `merkezleme/is_akisi.py`: `Faz.YON_DOGRULAMA`; kayıtlı kalibrasyon başka oturumda, matrisi ψ farkı kadar
  döndürüp 180° belirsizliğini küçük bir H adımıyla çözerek kullanılıyor (`_yon_dogrulamasini_tamamla`).
- Gradyen artık |C₂|'den (`gradyen_kaynagi: genlik`).
- Arayüz/özet: "roll" → "kuadrupol açısı (bobin sıfırına göre)", "SQ/G" → "a2/b2 (bobin çerçevesinde)".
  CSV sütunları `roll_mrad`, `sq_over_g` adlarını korudu.
- Merkezleme (x_c, y_c) yerçekimi referansına İHTİYAÇ DUYMAZ; bu iş yalnızca skew/roll ve yerçekimi
  çerçevesinde harmonikler içindir.

**Düzenek:** hava çekirdekli kuadrupol (dört bağımsız bobin, sigma profil karkas, dış ölçü 40×40 cm, boy
60 cm); dönen bobin 17 Kasım'dan beri quad'a sabit. Ölçüm bobini teğet: 5 sarım, 135 mm, iki iletken 20 mm
yarıçapta ±45°'de (`donen_bobin/merkezleme_olcer.yaml`, `BobinGeometrisi`). Dönüş 8 Hz, step motor.
Rotor kartı (ADC: ADS1263) bobinle birlikte döner; enkoder değeri statordan rotora RS485 + kayar halka ile
gider (`OLCUM_RAPORU_2026-11-04.md`).

## Yöntem (18 Kasım tartışmasında varılan)

**Tanımlar.** γ: yerçekiminin (aşağı) yönünün enkoder çerçevesindeki açısı (her oturumda ölçülür).
κ: ivmeölçerin algılama ekseni ile bobinin **kuadrupol (n = 2)** manyetik açı sıfırı arasındaki sabit fark
(bir kez kalibre edilir). ψ_g: kuadrupolün yerçekimine göre skew açısı (aranan).

**1. Her oturumda yerçekimi açısı (γ).** Motor N açıda (8–12, eşit aralıklı) durdurulur; her durakta
ivmeölçer (tek eksen yeterli) ~1 s okunur, enkoder açısı kaydedilir. a(θ) = A·cos(θ − γ) + c uydurulur.
- Ofset ve ölçek hatası uydurmada düşer; dururken okunduğu için merkezkaç ve hız dalgalanması karışmaz.
- 8 Hz'de dönerken okumak İSTENMEZ: 1/tur hız dalgası teğetsel ivme yaratır (0.5° dalga, 10 mm yarıçapta
  ~0.2 m/s² ≈ %2 g → ~20 mrad faz hatası).
- Durağan referans ile 8 Hz'deki ölçüm arasındaki sabit açı farkı (ADC gecikmesi + mil burulması), mevcut
  iki yönlü "gecikme ölç" ölçümüyle düzeltilir; bu ölçümün güncel olduğunu denetle.

**2. Bir kez: κ'nın kalibrasyonu (uçtan uca çevirme).** Bobin sistemi quad'ın içinde düşey eksen etrafında
180° çevrilir (öbür uçtan takılır); quad yerinde kalır. Her iki konumda 1. adım yapılır ve kuadrupol açısı
ölçülür. Ölçülen q = (kuadrupol açısı − γ) için:
- A: q_A = ψ_g − κ ; B (çevrilmiş): q_B = −ψ_g − κ (kuadrupol simetrisi yüzünden mod 90°).
- ψ_g = (q_A − q_B)/2, κ = −(q_A + q_B)/2.
- Enkoder sıfırının arada değişmesi ya da çevirme ekseninin tam düşey olmaması sonucu etkilemez (her konum
  kendi γ'sıyla bağlanır). Gereken: ivmeölçer bobinle aynı rijit gövdede (kaplinlerin bobin tarafında) ve
  quad çevirme sırasında yerinden oynamıyor.
- **Bu işaret/çerçeve formüllerini koda koymadan önce simülatörle doğrula** (bkz. Testler). Uçtan uca
  çevirmede bobinin dönme yönü quad'a göre tersine döner; `merkezleme_koprusu.olcum_hesapla`'nın ters yönde
  doğru harmonik verdiğini ve gecikme işaretini denetle.
- Alternatif: quad tabanına terazi konup quad döndürülür (bobin sabit); o zaman dönme ekseninin düşeyliği
  terazinin iki konumda aynı okumaya getirilmesiyle sağlanır ve ψ quad tabanına göre çıkar.

**3. Yerçekimi çerçevesinde harmonikler.** Bobin çerçevesindeki C_n'ler, kuadrupolün yerçekimine göre açısı
için γ + κ kadar döndürülür: C_nᵍ = C_n · e^(−i·n·(γ + κ)) (işaret yönünü testle sabitle). b_n = Re, a_n = Im.
- n = 2 için açı tam kalibre (κ n = 2 ile ölçüldü). n ≠ 2 için bobinin harmonik başına açı sıfırı biraz farklı
  olabilir: iki iletkenin yarıçapları 10 µm farklıysa n = 1 sıfırı 0.25 mrad kayar, n = 2 kaymaz (açısal
  yerleşim hataları iki harmoniği eşit kaydırır). a_n hatası ≈ n·δ·b_n olduğundan küçük harmoniklerde (n ≥ 3,
  ana alanın ~1e-4'ü) ihmal edilebilir; n = 1'de merkez vektörünü yalnızca döndürür. Raporda belirt.

**Helmholtz neden seçilmedi (yeniden önerme):** dipol (n = 1) referansı verir; teğet bobinde n = 1 → n = 2
geçişi iletken yarıçap farkına çok duyarlı (0.1 mm → 2.5 mrad). Ayrıca bobine yakın çelik parçaların (sigma
profil T-somunları, motor) referans alanında mıknatıslanması Helmholtz'u çevirmekle gitmez.

## Hata bütçesi ve bilinen ölçümler

- Kuadrupol açısı ölçümü (17 Kasım, bobin çerçevesinde): tek ölçüm (2 s) σ ≈ 0.3–0.5 mrad, 1 dk ortalaması
  σ ≈ 0.1–0.2 mrad.
- Isınmayla kuadrupol açısı kayıyor: soğuk başlangıçta 2.4 sa'te +0.55 mrad, ısınmış düzende 3.4 sa'te
  +0.17 mrad (mıknatıs mı bobin bağlantısı mı ayrılamadı).
- İvmeölçer: ADXL355 sınıfı (~25 µg/√Hz) ile durak başına 1 s ve 12 durakta γ için ~0.01–0.03 mrad
  beklenir (tahmin; ölçüp doğrula). Basit dijital terazi ~1–2 mrad.
- Akım modlarıyla (H, V, Q, M; ±%0.5) kuadrupol açısında gürültü üstü değişim görülmedi; skew quad bu dört
  akımla düzeltilemiyor gibi (HİPOTEZ; istenirse %2 adımla dene).

## Yapılacaklar (onaydan sonra)

1. Rotor firmware'i: ivmeölçeri oku, durağan okumaları mevcut rotor veri hattına ekle (paket biçimi
   `OLCUM_RAPORU_2026-11-04.md`'de). Host `mgf` tarafında ayrıştır.
2. Host: "Açı referansı al" komutu/düğmesi: motoru N açıda durdur, oku, uydur; γ'yı, uydurma artığını,
   tarih/saati oturum klasörüne yaz (`aci_referansi.json`). Uydurma artığı büyükse uyar.
3. κ kalibrasyonu için iki konumlu yönlendirmeli adım (A, çevir, B); sonucu kalıcı bir dosyaya yaz
   (ör. `donen_bobin/aci_kalibrasyonu.json`: κ, tarih, iki konumdaki ham değerler).
4. γ ve κ varsa: arayüzde ve kayıtta "kuadrupol skew açısı (yerçekimine göre)" ve yerçekimi çerçevesinde
   b_n/a_n; yoksa mevcut "bobin sıfırına göre" etiketleri kalsın. Kalibrasyon matrisi ve merkezleme
   değişmesin.
5. İsteğe bağlı: enkoderin Z çıkışı varsa index'e göre sıfırlama (o zaman γ her oturumda değil, ara sıra
   kontrol için ölçülür).
6. README ve `merkezleme/harmonikler.py` docstring'ini güncelle.

## Testler

- Simülatörle (`merkezleme/simulator.py`; `roll_rad` ve `olcum_cercevesi_acisi_derece` var): bilinen bir
  yerçekimi açısı, enkoder ofseti, ivmeölçer montaj açısı ve quad skew'u ver; 1–3. adımların ψ_g'yi ve κ'yı
  geri bulduğunu, enkoder sıfırının iki konum arasında değişmesine dayanıklı olduğunu doğrula.
- Sinüs uydurmasının ofset/ölçek hatasına dayanıklılığı; duraklarda enkoder ile okuma eşleşmesi.
- Mevcut testler (`python3 -m pytest -q tests` ve `donen_bobin/host` içinde) geçmeli.

## Kullanıcıya sorulacak açık sorular

1. İvmeölçerin modeli, nereye takıldı (rotor kartı mı, bobin taşıyıcısı mı), kaç eksen?
2. Rotor veri hattında ek veri için yer var mı; firmware'i değiştirmeye izin var mı?
3. Enkoderin Z (index) çıkışı var mı?
4. Uçtan uca çevirme mekanik olarak nasıl yapılacak: bobin öbür uçtan mı takılacak, quad mı döndürülecek?
5. Skew açısı için hedef hassasiyet: 1 mrad mı, 0.1 mrad mı?
