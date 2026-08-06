# dipole-correction-at-quad
Dört kutuplu mıknatısın hizalama hatası dipol alan olarak okunur (Bx ve By). Gradient descent ya da başka bir yöntemle dipol alanın sıfırlanması hedefleniyor.

## Uygulamalar

- `minimize_dipole.py` — İki dikey rotating-coil probundan gelen `bx1`, `bx2`
  ölçümlerinin ortalamasından dipol, farkından quadrupol alanı hesaplayıp
  akımları sabit öğrenme oranlarıyla düzelten ilk uygulama.

- `quad_dipole_compensation.py` — Dört bağımsız güç kaynağıyla beslenen bir
  quadrupolde, rotating coil'den doğrudan okunan yatay/dikey dipol alanları
  (`Bx`, `By`) metin kutusuna girilerek sıfırlanmasını hedefleyen yeni
  uygulama. Quadrupole gradyenti burada bir kontrol değişkeni olarak
  hedeflenmez; bunun yerine akım düzeltmelerine eklenen regularization
  terimi (λ‖ΔI‖²) sayesinde akımlarda gereksiz büyük değişiklik yapılması
  önlenir.

  Akış:
  1. **Faz 1 – Response matrix kalibrasyonu** (bir kez, `response_matrix.json`
     dosyasına kaydedilir): Uygulama sırasıyla nominal akımları ve her
     bobinin ±ΔI kadar değiştirilmiş halini gösterir; kullanıcı güç
     kaynaklarını elle bu değerlere ayarlayıp rotating coil ölçümünü girer.
     Merkezi fark ile 2×4'lük response matrix `R` hesaplanır.
  2. **Faz 2 – Regularized least squares döngüsü**: Her iterasyonda ölçülen
     `[Bx, By]` için hata `e = -[Bx, By]` (hedef her zaman sıfır) hesaplanır,
     `(RᵀR + λI) ΔI = Rᵀe` çözülür, `I_new = I_old + α·ΔI` ile kademeli
     (damped) olarak uygulanır. `‖e‖ < tolerance` olunca yakınsama bildirilir.

  Parametreler (`config.py` içindeki `CONFIG` sözlüğünde):
  `nominal_akimlar`, `delta_i_kalibrasyon`, `lambda_regularizasyon`,
  `alpha_damping`, `tolerance`, `response_matrix_path`, `log_dir`.

  Çekirdek matematik (`dipole_core.py`) PyQt5'ten bağımsızdır ve ayrıca
  test edilebilir.

  Çalıştırma:
  ```
  pip install numpy matplotlib PyQt5
  python quad_dipole_compensation.py
  ```
