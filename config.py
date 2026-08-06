"""Ortak konfigürasyon degerleri.

Bu dosya hem eski iki-problu (minimize_dipole.py) hem de yeni
dort-bobinli response-matrix tabanli (quad_dipole_compensation.py)
uygulamalar tarafindan kullanilir.
"""

CONFIG = {
    # --- minimize_dipole.py (eski, iki dikey prob) icin ---
    "learning_rate_dipol": 0.01,
    "learning_rate_quadrupol": 0.01,
    "bx1_target": 0.0,
    "bx2_target": 0.0,
    "nominal_akim": 50.0,

    # --- quad_dipole_compensation.py (yeni, 4 bobin) icin ---
    # Nominal (baslangic) bobin akimlari [I0, I1, I2, I3] (A)
    "nominal_akimlar": [50.0, 50.0, 50.0, 50.0],
    # Kalibrasyon sirasinda her bobine uygulanan kucuk akim sapmasi (A)
    "delta_i_kalibrasyon": 0.5,
    # Regularized least squares icin lambda katsayisi
    "lambda_regularizasyon": 0.01,
    # Her iterasyonda uygulanacak duzeltme orani (0 < alpha <= 1)
    "alpha_damping": 0.3,
    # Yakinsama esigi: ||[Bx, By]|| bu degerin altina inince optimizasyon
    # tamamlanmis sayilir (mT)
    "tolerance": 0.01,
    # Response matrix ve iterasyon loglarinin yazilacagi klasor/dosyalar
    # (script'in bulundugu klasore gore relatif)
    "response_matrix_path": "response_matrix.json",
    "log_dir": "logs",
}
