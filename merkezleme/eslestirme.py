"""Güç kaynağı - bobin eşleştirmesi (`./merkezle eslestir`).

Her güç kaynağının ön panelinden, beslediği bobinin numarası kadar akım
ayarlanır: bobin 1'i besleyene 1 A, bobin 2'yi besleyene 2 A, ... Çıkışı açmak
gerekmez: çıkış kapalıysa ayar değeri (`CURR?`), açıksa ölçülen akım
(`MEAS:CURR?`) kullanılır. Pencere cihazları yalnızca OKUR (`*IDN?`, `OUTP?`,
`CURR?`, `MEAS:CURR?`); hiçbir ayarı değiştirmez. Eşleşme tutarlıysa adresler
`yapilandirma.yaml`'daki `guc_kaynaklari.visa_adresleri`'ne bobin sırasıyla
yazılır.

Adresler `/dev/serial/by-id/...` yollarıdır: cihazın seri numarasına bağlıdır,
USB'nin takılma sırasıyla değişmez (`/dev/ttyACM*` numaraları değişir).
"""
from __future__ import annotations

import glob
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

from .yapilandirma import BOBIN_SAYISI, yapilandirma_yukle

PORT_DESENI = "/dev/serial/by-id/usb-ITECH*IT-M3233*"
TOLERANS_A = 0.2  # ayar/ölçüm, bobin numarasına bu kadar yakın olmalı

#: yapilandirma.yaml'daki numaralandırma (etiketli taraftan bakıldığında)
BOBIN_KONUMLARI = {1: "sağ üst", 2: "sol üst", 3: "sol alt", 4: "sağ alt"}


@dataclass
class Okuma:
    adres: str
    seri: str = "?"
    cikis_acik: bool | None = None
    ayar_A: float | None = None
    olculen_A: float | None = None
    hata: str | None = None

    @property
    def akim_A(self) -> float | None:
        """Eşleştirmede kullanılan akım: çıkış açıksa ölçülen, değilse ayar."""
        return self.olculen_A if self.cikis_acik else self.ayar_A


def itech_adresleri() -> list[str]:
    return [f"ASRL{yol}::INSTR" for yol in sorted(glob.glob(PORT_DESENI))]


def _seri_no(adres: str) -> str:
    m = re.search(r"IT-M3233_(\w+?)-if", adres)
    return m.group(1) if m else adres


class CihazOkuyucu:
    """Bulunan bütün ITECH portlarını açık tutar ve her çağrıda okur."""

    def __init__(self) -> None:
        import pyvisa

        self._rm = pyvisa.ResourceManager("@py")
        self._cihazlar: dict[str, object] = {}

    def __call__(self) -> list[Okuma]:
        adresler = itech_adresleri()
        for adres in list(self._cihazlar):
            if adres not in adresler:  # USB çıkarıldı
                self._kapat(adres)
        return [self._oku(adres) for adres in adresler]

    def _oku(self, adres: str) -> Okuma:
        okuma = Okuma(adres, seri=_seri_no(adres))
        try:
            if adres not in self._cihazlar:
                self._cihazlar[adres] = self._rm.open_resource(
                    adres, timeout=1000, read_termination="\n"
                )
            c = self._cihazlar[adres]
            kimlik = c.query("*IDN?").split(",")  # type: ignore[attr-defined]
            if len(kimlik) >= 3:
                okuma.seri = kimlik[2].strip()
            okuma.cikis_acik = c.query("OUTP?").strip() in ("1", "ON")  # type: ignore[attr-defined]
            okuma.ayar_A = float(c.query("CURR?"))  # type: ignore[attr-defined]
            okuma.olculen_A = float(c.query("MEAS:CURR?"))  # type: ignore[attr-defined]
        except Exception as hata:  # noqa: BLE001 - satırda gösterilir
            okuma.hata = str(hata) or type(hata).__name__
            self._kapat(adres)  # bir sonraki okumada yeniden açılır
        return okuma

    def _kapat(self, adres: str) -> None:
        cihaz = self._cihazlar.pop(adres, None)
        try:
            cihaz.close()  # type: ignore[union-attr]
        except Exception:  # noqa: BLE001
            pass

    def kapat(self) -> None:
        for adres in list(self._cihazlar):
            self._kapat(adres)


def bobin_numarasi(okuma: Okuma, tolerans_A: float = TOLERANS_A) -> int | None:
    akim = okuma.akim_A
    if okuma.hata or akim is None:
        return None
    n = round(akim)
    if 1 <= n <= BOBIN_SAYISI and abs(akim - n) <= tolerans_A:
        return n
    return None


def eslesme_bul(okumalar: list[Okuma]) -> tuple[list[str] | None, list[str]]:
    """(bobin 1..4 sırasıyla adresler, sorunlar). Sorun varsa adresler None."""
    sorunlar: list[str] = []
    if len(okumalar) != BOBIN_SAYISI:
        sorunlar.append(f"{len(okumalar)} güç kaynağı bulundu, {BOBIN_SAYISI} olmalı.")
    bobine_gore: dict[int, list[Okuma]] = {}
    for o in okumalar:
        if o.hata:
            sorunlar.append(f"{o.seri}: okunamadı ({o.hata}).")
            continue
        n = bobin_numarasi(o)
        if n is None:
            sorunlar.append(
                f"{o.seri}: {o.akim_A:.3f} A bir bobin numarasına (1-{BOBIN_SAYISI} A) yakın değil."
            )
            continue
        bobine_gore.setdefault(n, []).append(o)
    for n, liste in sorted(bobine_gore.items()):
        if len(liste) > 1:
            sorunlar.append(f"{n} A birden fazla cihazda: " + ", ".join(o.seri for o in liste) + ".")
    eksik = [n for n in range(1, BOBIN_SAYISI + 1) if n not in bobine_gore]
    if eksik and len(okumalar) == BOBIN_SAYISI:
        sorunlar.append("Hiçbir cihazda yok: " + ", ".join(f"{n} A" for n in eksik) + ".")
    if sorunlar:
        return None, sorunlar
    return [bobine_gore[n][0].adres for n in range(1, BOBIN_SAYISI + 1)], []


def yapilandirmaya_yaz(yol: str | Path, adresler: list[str]) -> None:
    """`guc_kaynaklari.visa_adresleri` listesini yerinde değiştirir; dosyanın
    geri kalanına (yorumlar dahil) dokunmaz. Yazdıktan sonra dosyayı yeniden
    yükleyip adreslerin doğru okunduğunu doğrular."""
    yol = Path(yol)
    satirlar = yol.read_text(encoding="utf-8").splitlines(keepends=True)
    try:
        bas = next(i for i, s in enumerate(satirlar) if re.match(r"^\s+visa_adresleri:", s))
    except StopIteration:
        raise ValueError(f"{yol}: visa_adresleri bulunamadı") from None
    girinti = re.match(r"^(\s*)", satirlar[bas]).group(1)  # type: ignore[union-attr]
    son = bas + 1
    while son < len(satirlar) and re.match(rf"^{girinti}\s+(- |#)", satirlar[son]):
        son += 1
    yeni = [f"{girinti}visa_adresleri:   # ./merkezle eslestir, {datetime.now():%Y-%m-%d %H:%M}\n"]
    yeni += [
        f"{girinti}  - {a}   # bobin {n} ({BOBIN_KONUMLARI.get(n, '')})\n"
        for n, a in enumerate(adresler, start=1)
    ]
    eski = yol.read_text(encoding="utf-8")
    yol.write_text("".join(satirlar[:bas] + yeni + satirlar[son:]), encoding="utf-8")
    try:
        okunan = yapilandirma_yukle(yol).guc_kaynaklari.visa_adresleri
        if okunan != list(adresler):
            raise ValueError(f"yazılan adresler geri okunamadı: {okunan}")
    except Exception:
        yol.write_text(eski, encoding="utf-8")  # bozuk dosya bırakma
        raise


def adresleri_denetle(yol: str | Path) -> int:
    """Gerçek donanımla başlamadan önce: yapılandırmadaki seri port adresleri
    bu bilgisayarda var mı? Yoksa açıklayıcı bir mesajla 1 döner."""
    adresler = yapilandirma_yukle(yol).guc_kaynaklari.visa_adresleri
    eksik = []
    for a in adresler:
        m = re.fullmatch(r"ASRL(/\S+)::INSTR", a)
        if m is None or not Path(m.group(1)).exists():
            eksik.append(a)
    if not eksik:
        return 0
    print("HATA: güç kaynağı adresleri bu bilgisayarda bulunamadı:")
    for a in eksik:
        print(f"   {a}")
    print("Güç kaynaklarını USB ile bağlayıp eşleştirin:  ./merkezle eslestir")
    return 1


# ---------------------------------------------------------------------------
# Pencere
# ---------------------------------------------------------------------------
def pencere_olustur(yapilandirma_yolu: str | Path, okuyucu: Callable[[], list[Okuma]], tema_adi: str):
    from PyQt5.QtCore import QTimer
    from PyQt5.QtWidgets import (
        QApplication,
        QHBoxLayout,
        QHeaderView,
        QLabel,
        QPushButton,
        QTableWidget,
        QTableWidgetItem,
        QVBoxLayout,
        QWidget,
    )

    from .tema import tema_al

    class EslestirmePenceresi(QWidget):
        SUTUNLAR = ("Seri no", "Çıkış", "Ayar (A)", "Ölçülen (A)", "Bobin")

        def __init__(self) -> None:
            super().__init__()
            self.setWindowTitle("Güç kaynağı eşleştirme")
            self.yapilandirma_yolu = Path(yapilandirma_yolu)
            self.okuyucu = okuyucu
            self.adresler: list[str] | None = None

            yerlesim = QVBoxLayout(self)
            yerlesim.addWidget(QLabel(
                "Her güç kaynağının ön panelinden, beslediği bobinin numarası kadar akım ayarlayın:\n"
                "bobin 1 (sağ üst) → 1 A, bobin 2 (sol üst) → 2 A, bobin 3 (sol alt) → 3 A, "
                "bobin 4 (sağ alt) → 4 A.\n"
                "Çıkışı açmanız gerekmez; ayar değeri okunur. Bu pencere cihazlara komut göndermez."
            ))
            self.tablo = QTableWidget(0, len(self.SUTUNLAR))
            self.tablo.setHorizontalHeaderLabels(self.SUTUNLAR)
            self.tablo.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
            self.tablo.verticalHeader().setVisible(False)
            yerlesim.addWidget(self.tablo)
            self.durum = QLabel()
            self.durum.setWordWrap(True)
            yerlesim.addWidget(self.durum)
            dugmeler = QHBoxLayout()
            dugmeler.addStretch()
            self.kaydet_dugmesi = QPushButton("Eşleşmeyi kaydet")
            self.kaydet_dugmesi.clicked.connect(self.kaydet)
            dugmeler.addWidget(self.kaydet_dugmesi)
            kapat = QPushButton("Kapat")
            kapat.clicked.connect(self.close)
            dugmeler.addWidget(kapat)
            yerlesim.addLayout(dugmeler)

            self.zamanlayici = QTimer(self)
            self.zamanlayici.timeout.connect(self.yenile)
            self.zamanlayici.start(1000)
            self.yenile()

        def yenile(self) -> None:
            okumalar = self.okuyucu()
            self.tablo.setRowCount(len(okumalar))
            for i, o in enumerate(okumalar):
                n = bobin_numarasi(o)
                hucreler = (
                    o.seri,
                    "?" if o.cikis_acik is None else ("AÇIK" if o.cikis_acik else "kapalı"),
                    "" if o.ayar_A is None else f"{o.ayar_A:.3f}",
                    "" if o.olculen_A is None else f"{o.olculen_A:.3f}",
                    f"HATA: {o.hata}" if o.hata else (
                        f"{n} ({BOBIN_KONUMLARI[n]})" if n else "—"
                    ),
                )
                for j, metin in enumerate(hucreler):
                    self.tablo.setItem(i, j, QTableWidgetItem(metin))
            self.adresler, sorunlar = eslesme_bul(okumalar)
            self.kaydet_dugmesi.setEnabled(self.adresler is not None)
            if self.adresler is not None:
                self.durum.setText("Eşleşme tamam. 'Eşleşmeyi kaydet'e basın.")
            else:
                self.durum.setText("Bekleniyor:\n" + "\n".join(sorunlar))

        def kaydet(self) -> None:
            if self.adresler is None:
                return
            try:
                yapilandirmaya_yaz(self.yapilandirma_yolu, self.adresler)
            except Exception as hata:  # noqa: BLE001
                self.durum.setText(f"Kaydedilemedi: {hata}")
                return
            self.zamanlayici.stop()
            self.kaydet_dugmesi.setEnabled(False)
            self.durum.setText(
                f"Kaydedildi: {self.yapilandirma_yolu}.\n"
                "Çıkışı açtıysanız ön panelden akımı sıfıra indirip kapatın. "
                "Ayar değerlerini değiştirmeniz gerekmez: program başlarken akımı 0'a yazar."
            )

        def closeEvent(self, olay) -> None:  # noqa: N802 - Qt adı
            self.zamanlayici.stop()
            olay.accept()

    pencere = EslestirmePenceresi()
    uygulama = QApplication.instance()
    if uygulama is not None:
        uygulama.setStyleSheet(tema_al(tema_adi).stil_sayfasi())
    return pencere


def calistir(yapilandirma_yolu: str | Path) -> int:
    from PyQt5.QtWidgets import QApplication

    kfg = yapilandirma_yukle(yapilandirma_yolu)
    uygulama = QApplication([])
    okuyucu = CihazOkuyucu()
    pencere = pencere_olustur(yapilandirma_yolu, okuyucu, kfg.genel.tema)
    pencere.resize(820, 420)
    pencere.show()
    try:
        return int(uygulama.exec_())
    finally:
        okuyucu.kapat()
