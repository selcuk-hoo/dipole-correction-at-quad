"""Ölçüm penceresinin yardım metni ve penceresi.

Sayılar (hız sınırı, dosya yolları, ...) parametrelerden doldurulur; böylece
yardım, merkezleme_olcer.yaml ile çelişmez.
"""
from __future__ import annotations

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QTextBrowser, QVBoxLayout

from .merkezleme_koprusu import REPO_KOKU, Parametreler


def _goreli(yol) -> str:
    try:
        return str(yol.relative_to(REPO_KOKU))
    except ValueError:
        return str(yol)


def yardim_html(p: Parametreler, max_pencere_s: float) -> str:
    kanallar = ", ".join(p.kanallar)
    return f"""
<h2>Dönen bobin — merkezleme ölçümü</h2>
<p>Bu pencere, dönen bobinle mıknatısın harmoniklerini (n = 1..6) ölçer. İki türlü
kullanılır:</p>
<ul>
<li><b>Merkezleme ile birlikte:</b> ölçümler <code>{_goreli(p.kilit_dosyasi)}</code> dosyası
üzerinden merkezleme programına otomatik verilir.</li>
<li><b>Tek başına:</b> sürekli ölçüm alır, grafikleri gösterir ve CSV'ye kaydeder.</li>
</ul>

<h3>Hızlı başlangıç</h3>
<ol>
<li><b>Bağlan</b> — ADC ayarları ({p.kazanc}×, {p.ornekleme_sps:g} SPS, {p.filtre})
cihaza gönderilir.</li>
<li><b>Başlat</b> — servo açılır, motor seçilen hıza çıkar. Hız oturunca ölçüm başlar.</li>
<li><b>Referans mıknatısla sıfırla</b> — enkoderin sıfırı cihaz her açıldığında değişir.
Referans dipol mıknatısı takılıyken basın: onun alanı saf normal ve pozitif
(b0 &gt; 0, a0 = 0) görünecek şekilde faz ofseti ayarlanır.</li>
<li><b>Gecikme ölç (iki yön)</b> — ADC örneği ile enkoder açısı arasında sabit bir zaman
gecikmesi vardır; bilinmezse hız dalgalanması n = 2'yi n = 1'e karıştırır (µm'ler).
"Merkezleme'ye yaz" kapalıyken basın: bir pencere bu yönde, motor ters çevrilip bir
pencere öbür yönde alınır ve gecikme bulunur. Ölçülen değeri günlükte yazdığı gibi
parametre dosyasına (<code>olcum.gecikme_ms</code>) yazın; donanım değişmedikçe sabittir.
Faz ofseti yeni gecikmeye kendiliğinden taşınır.</li>
<li><b>Merkezleme için:</b> "Merkezleme'ye yaz" açıkken depo kökünde
<code>python -m merkezleme --dosyadan</code> (yarı otomatik) ya da
<code>--otomatik --dosyadan --canli</code> (tam otomatik) çalıştırın.</li>
<li><b>Durdur</b> — önce motor durur, sonra servo kapanır. Pencereyi kapatmak ya da bir
hata oluşması da aynı sonucu verir.</li>
</ol>

<h3>Ayarlar</h3>
<table cellspacing="0" cellpadding="3">
<tr><td valign="top"><b>Bobin</b></td><td>İki düz bobin ({kanallar}): birbirine dik,
geometrileri aynı.</td></tr>
<tr><td valign="top"><b>Hız</b></td><td>En fazla {p.max_hiz_hz:g} Hz.</td></tr>
<tr><td valign="top"><b>Ölçüm süresi</b></td><td>Her ölçümde kullanılan veri süresi
(en fazla ~{max_pencere_s:.0f} s). Uzun ölçüm rastgele gürültüyü 1/√süre oranında azaltır.
Dönmeyle eşzamanlı hataları ve yavaş sürüklenmeyi azaltmaz; merkezleme'nin her adımı da
o kadar uzar.</td></tr>
<tr><td valign="top"><b>Merkezleme'ye yaz</b></td><td>Açıkken merkezleme kilidi silince
(yeni akımlar oturmuş demektir) yalnızca <i>bundan sonra</i> gelen veriyle ölçülür ve
dosyaya yazılır. Kapalıyken her ölçüm süresinde bir sürekli ölçüm alınır.</td></tr>
<tr><td valign="top"><b>CSV'ye kaydet</b></td><td>Her ölçüm,
<code>{_goreli(p.kayit_dizini)}</code> içinde oturum başına bir dosyaya yazılır.</td></tr>
<tr><td valign="top"><b>Tek ölçüm</b></td><td>Merkezleme'ye yazmadan bir ölçüm alır.</td></tr>
</table>
<p>Bobin, hız, ölçüm süresi ya da faz ofseti değişince grafikteki ortalama sıfırlanır.</p>

<h3>Ölçülen büyüklükler</h3>
<p>Değerler Tesla cinsinden, r_ref = {p.r_ref_m * 1e3:g} mm'de. <b>b</b> normal,
<b>a</b> skew bileşendir; dosya biçiminde 0 = dipol, 1 = kuadrupoldür (b0, a0, b1, a1).
Gradyen = |C₂|/r_ref. x_c, y_c manyetik merkezdir (−r_ref·C₁/C₂).
<b>Sinyal tepesi</b> ADC tam ölçeğinin %{100 * p.doyma_uyari_orani:.0f}'ini aşarsa
uyarı verilir.</p>

<h3>Grafikler</h3>
<p><b>Çok kutuplar:</b> n = 1..6, logaritmik eksende.</p>
<ul>
<li><i>Göster:</i> normal ve skew yan yana (içi boş çubuk: negatif değer) ya da genlik |C_n|.</li>
<li><i>Ölçek:</i> gerçek alan (T), n = 1'e göre ya da n = 2'ye göre (o mertebe = 1).</li>
<li>Çubuklar son ölçümlerin ortalamasını, hata çubukları tek ölçümlerin saçılımını gösterir.
Hata çubuğu çubuktan uzunsa o terim gürültünün altındadır.</li>
<li>Bu bobin n = 6'ya az, n = 7'ye neredeyse hiç duyarlı değildir.</li>
</ul>
<p><b>Bobin akısı:</b> son ölçüm penceresinde bobinden geçen akı (gerilimin zaman
integrali), enkoder açısına göre (turlar üst üste); çizgi, uydurulan harmoniklerin
toplamıdır. Noktalar çizgiye oturmalıdır. Sayısal karşılığı <i>uydurma artığı</i>dır
(sağlıklı ölçümde ~1e-4..1e-3). İkinci ölçüt <i>okuma saati sıçraması</i>dır: bir ADC örneği
kaybolursa enkoder okumaları bir örnek kayar (sağlıklı ~0.2, kayıpta ~1). İkisinden biri
eşiği (<code>olcum.artik_esigi</code>, <code>olcum.sicrama_esigi</code>) aşan ölçüm
merkezleme'ye yazılmaz; üst üste 3 kez olursa motor durdurulur.</p>
<p><b>Çerçeve kilidi:</b> "Merkezleme'ye yaz" açıkken ve motor dönerken bobin, hız, referans
ve gecikme değiştirilemez; merkezleme'nin kalibrasyonu bu çerçevede yapılır.</p>
<p><b>Günlük:</b> olaylar, uyarılar ve her ölçümün özeti.</p>

<h3>Sorun giderme</h3>
<ul>
<li><b>Bağlantı kurulamadı:</b> IP adresini (varsayılan {p.ip}) ve kabloyu kontrol edin.</li>
<li><b>Rotor ÇEVRİMDIŞI:</b> rotor kartından veri gelmiyor; ölçüm yapılmaz.</li>
<li><b>Hız oturmuyor:</b> motor sürücüsünü kontrol edin.</li>
<li><b>Ölçüm reddedildi:</b> artık yüksekse yanlış kanal, doyma ya da enkoder sorunu; saat
sıçraması yüksekse örnek kaybı (RS485/TCP; günlükte RS485 uyarısı var mı?). Bobin akısı
grafiğine bakın.</li>
<li><b>Doyma uyarısı:</b> parametre dosyasındaki <code>adc.kazanc</code> değerini düşürün.</li>
<li><b>Merkezleme zaman aşımına uğruyor:</b> bu pencerede "Merkezleme'ye yaz" açık mı ve motor
dönüyor mu, kontrol edin.</li>
</ul>
<p>Bütün sayılar (bobin geometrisi, ADC, hız sınırları, dosya yolları):
<code>{_goreli(p.kaynak)}</code>. Ayrıntılar: <code>README_SURUM.md</code>.</p>
"""


class YardimPenceresi(QDialog):
    def __init__(self, p: Parametreler, max_pencere_s: float, ust=None) -> None:
        super().__init__(ust)
        self.setWindowTitle("Yardım — merkezleme ölçümü")
        self.resize(680, 720)
        duzen = QVBoxLayout(self)
        self.metin = QTextBrowser()
        self.metin.setHtml(yardim_html(p, max_pencere_s))
        duzen.addWidget(self.metin)
        dugmeler = QDialogButtonBox()
        dugmeler.addButton("Kapat", QDialogButtonBox.RejectRole)
        dugmeler.rejected.connect(self.reject)
        duzen.addWidget(dugmeler)
