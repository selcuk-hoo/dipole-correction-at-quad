# Sonraki açılış istemi (merkezleme / quad)

*Hazırlayan: Claude, 20 Kasım 2026. Merkezleme işine uzun bir ara verildi. Çalışmaya döndüğünüzde yeni bir Claude
Code oturumu açıp aşağıdaki bölümü (çizgiler arası) istem olarak verin. Klasör:
`/home/selcuk/projeler/dipole-correction-at-quad`.*

---

Bu depoda, hava çekirdekli kuadrupolün (dört bağımsız bobin, dört ITECH IT-M3233 güç kaynağı) elektriksel
merkezlemesi üzerinde çalışıyorduk ve uzun bir ara verdik. Hiçbir şeyi hatırlamıyorum; önce şunları sırayla oku,
sonra bana **kısa** bir durum özeti ver (en çok 10 satır) ve ne yapmamı önerdiğini söyle. Henüz hiçbir şeyi
değiştirme, donanıma dokunma.

1. `raporlar/merkezleme_2026-11-18/rapor.pdf`: bulgular, yazılım değişiklikleri, hatalar ve açık işler (kaynak:
   `rapor.tex`; sayılar `analiz.py`'den). Önce Bölüm 1 ("Nerede ne duruyor") ve Bölüm 6 ("Açık işler").
2. `planlar/YAPILACAKLAR.md`: ertelenen işlerin listesi ve nedenleri.
3. `README.md`: kullanım; "18 Kasım 2026'da eklenenler" ve "Arayüz düzeni" bölümleri.
4. `git status`, `git branch -vv`, `git tag -l -n1`, `git log --oneline -15`. Beklenen: `main` açık; `arayuz-duzen`
   dalı birleştirilmemiş; etiketler `lab-testi-oncesi-2026-11-18` ve `merkezleme-2026-11-18-test`; uzak depoya
   (GitHub) hiçbir şey gönderilmemiş.
5. Bellek: `~/.claude/projects/-home-selcuk-projeler-dipole-correction-at-quad/memory/` (özellikle
   `merkezleme-durum-2026-11-18.md`, `donanim-calistirmadan-once-sor.md`, `telegramdan-sor.md`).

## Bilmen gerekenler (özet; ayrıntı raporda)

- **Donanımda denenmemiş iki değişiklik var:** (a) `main`'de `donen_bobin/merkezleme_olcer.yaml` içinde
  `sicrama_esigi` 0.6 → 0.9; (b) `arayuz-duzen` dalındaki yeni arayüz (alt durum çubuğu, yeni Merkezleme ve
  Kararlılık düzeni, Ayarlar sekmesi). Donanımda denenmiş son durum `merkezleme-2026-11-18-test` etiketidir.
- 18 Kasım 16:30'da 10 s'lik ölçümle ölçümlerin yarısı "okuma saati sıçraması" yüzünden reddedildi ve üst üste 3 ret
  motoru durdurdu. Eşik düzeltmesi bu yüzden yapıldı; işe yarayıp yaramadığı bilinmiyor.
- Varsayılanlar 18 Kasım'da değişti: ölçüm süresi 10 s, en fazla 8 yineleme, arka plan her 3 noktada bir.
- Enkoder artımlıdır, sıfırı her oturumda keyfidir. Arayüzdeki "kuadrupol açısı" yerçekimine göre skew **değildir**.
  Kalibrasyon matrisi başka oturumda, kuadrupol açısına göre döndürülerek kullanılabilir (ayar panelinde "Kalibrasyon"
  seçimi, yön doğrulama).
- Ham ölçüm kayıtları (`kayitlar/`, `calistirmalar/`) git'te değildir; yalnızca bu bilgisayarda durur.

## Kurallar

- **Motoru döndüren ya da akım açan her adımdan önce kullanıcıdan açık onay al** (kısa deneme dahil; bir önceki
  onay sonrakini kapsamaz). Kullanıcı bilgisayar başında değilse soruyu `~/bin/claude-sor "soru" evet hayir` ile
  Telegram'dan sor ve cevabı bekle. Bir test betiği çalıştırmak (`python3 -m merkezleme.arayuz_testi`,
  `merkezleme.tani_testi`) da donanıma dokunur.
- Donanıma dokunmayan her şey serbest: kayıt analizi, kod, testler (`python3 -m pytest -q tests` ve
  `donen_bobin/host` içinde aynı komut).
- Yeni işe ayrı dalda başla; `main`'de doğrudan çalışma. Commit mesajlarının sonuna ilgili
  `Co-Authored-By` satırını ekle. Uzak depoya yalnızca kullanıcı isterse gönder.
- Belgelenen her sayı çalıştırılmış koddan gelsin; iddiaları [Ölçüldü] / [Yorum] / [Hipotez] diye ayır.
  Raporlar Türkçe LaTeX (LuaLaTeX; XeLaTeX bu bilgisayarda yok), yazar satırı "Hazırlayan: Claude".
- Kullanıcıdan gelen mesajlar için `~/Dropbox/mac-laptop-iletisimi/` gelen kutusuna da bak (genel kural).

## Önerilen ilk adımlar (kullanıcıya sor, kendiliğinden başlama)

1. `arayuz-duzen` dalını gerçek ekranda görmek ve beğenilirse `main`'e birleştirmek (`git switch arayuz-duzen`,
   `./merkezle kuru` ile bak).
2. Donanımla kısa bir merkezleme denemesi (`main`, yeni eşik); günlükte `Ölçüm reddedildi` satırlarını say.
   Çoksa eşik ve ölçüm süresi birlikte gözden geçirilmeli. Üst üste 3 retin motoru durdurması da gözden
   geçirilmeli (rapor Bölüm 6, madde 2).
3. İvmeölçer takıldıysa: `planlar/yercekimi_referansi_PROMPT.md` ayrı bir oturumda uygulanır.

---
