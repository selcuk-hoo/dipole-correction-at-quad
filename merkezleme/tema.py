"""Arayuz temalari: varsayilan ve eskilerin fosforlu monokrom ekranlari.

Arayuzdeki BUTUN renkler bu moduldedir; `arayuz.py` hicbir rengi kendi icinde
tanimlamaz. Boylece yeni bir tema eklemek icin yalnizca buraya bir `Tema`
kaydi eklenir.

Temalar
-------
* `varsayilan`      : sistem temasi (acik zemin, renkli vurgular)
* `fosfor_yesil`    : P1 fosfor yesili monokrom CRT
* `fosfor_turuncu`  : P3 fosfor amber (turuncu) monokrom CRT

Monokrom temalarda renk yerine **ters video** (zemin ile on planin yer
degistirmesi) ve parlaklik kademeleri kullanilir; gercek CRT'lerde vurgu
boyle yapiliyordu. Bu yuzden "tehlike" rengi yoktur: DURDUR dugmesi ters
videoya gecer.
"""
from __future__ import annotations

from dataclasses import dataclass

# Monokrom temalarda kullanilan yazi tipi yigini (ilk bulunani kullanilir).
MONO_YIGIN = '"DejaVu Sans Mono", "Liberation Mono", "Courier New", monospace'


@dataclass(frozen=True)
class Tema:
    """Bir temanin renk paleti ve turetilmis stilleri."""

    ad: str
    baslik: str
    monokrom: bool
    arka_plan: str
    panel_arka_plan: str
    on_plan: str
    parlak: str
    sonuk: str
    cok_sonuk: str
    # Yalnizca renkli (varsayilan) temada kullanilanlar
    vurgu: str = "#0d47a1"
    uyari_zemin: str = "#fff8e1"
    uyari_kenar: str = "#ffca28"
    iyi_zemin: str = "#2e7d32"
    tehlike_zemin: str = "#b00020"
    deneme_zemin: str = "#1565c0"
    font_yigini: str = ""

    # ------------------------------------------------------------------
    # Uygulama geneli stil sayfasi
    # ------------------------------------------------------------------
    def stil_sayfasi(self) -> str:
        """QApplication'a uygulanacak QSS. Varsayilan tema icin bostur.

        Uygulama geneline verilir; boylece QMessageBox gibi ayri ust seviye
        pencereler de temali gorunur.
        """
        if not self.monokrom:
            return ""
        return f"""
QWidget {{
    background-color: {self.arka_plan};
    color: {self.on_plan};
    font-family: {self.font_yigini};
    font-size: 10pt;
}}
QFrame#ustSerit {{
    border: 1px solid {self.sonuk};
}}
/* QLabel, QFrame'den turer; bu yuzden cerceve kurali yalnizca ust seride
   baglanir ve QLabel kurali SONRA gelir (esit ozgullukte son kural kazanir). */
QLabel {{
    background: transparent;
    border: none;
}}
QGroupBox {{
    border: 1px solid {self.sonuk};
    margin-top: 10px;
    padding: 10px 6px 6px 6px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 8px;
    padding: 0 4px;
    color: {self.parlak};
}}
QLineEdit, QPlainTextEdit {{
    background-color: {self.panel_arka_plan};
    color: {self.on_plan};
    border: 1px solid {self.sonuk};
    padding: 2px 4px;
    selection-background-color: {self.on_plan};
    selection-color: {self.arka_plan};
}}
QLineEdit:focus, QPlainTextEdit:focus {{
    border: 1px solid {self.parlak};
}}
QLineEdit:disabled, QPlainTextEdit:disabled {{
    color: {self.cok_sonuk};
    border-color: {self.cok_sonuk};
}}
QPushButton {{
    background-color: {self.arka_plan};
    color: {self.on_plan};
    border: 1px solid {self.on_plan};
    padding: 6px 10px;
}}
QPushButton:hover:enabled {{
    background-color: {self.on_plan};
    color: {self.arka_plan};
}}
QPushButton:pressed:enabled {{
    background-color: {self.parlak};
    color: {self.arka_plan};
}}
QPushButton:disabled {{
    color: {self.cok_sonuk};
    border-color: {self.cok_sonuk};
}}
QComboBox {{
    background-color: {self.panel_arka_plan};
    color: {self.on_plan};
    border: 1px solid {self.sonuk};
    padding: 2px 6px;
}}
QComboBox::drop-down {{
    border-left: 1px solid {self.sonuk};
    width: 16px;
}}
QComboBox QAbstractItemView {{
    background-color: {self.panel_arka_plan};
    color: {self.on_plan};
    border: 1px solid {self.on_plan};
    selection-background-color: {self.on_plan};
    selection-color: {self.arka_plan};
}}
QScrollBar:vertical, QScrollBar:horizontal {{
    background-color: {self.arka_plan};
    border: none;
}}
QScrollBar::handle:vertical, QScrollBar::handle:horizontal {{
    background-color: {self.sonuk};
}}
QScrollBar::add-line, QScrollBar::sub-line {{
    background: none;
    border: none;
}}
QMessageBox {{
    background-color: {self.arka_plan};
    color: {self.on_plan};
}}
QToolTip {{
    background-color: {self.panel_arka_plan};
    color: {self.on_plan};
    border: 1px solid {self.on_plan};
}}
"""

    # ------------------------------------------------------------------
    # Rol bazli stiller (arayuzdeki tek tek ogeler)
    # ------------------------------------------------------------------
    def _ters_video(self, kalin: bool = True) -> str:
        agirlik = "font-weight: bold;" if kalin else ""
        return (
            f"color: {self.arka_plan}; background-color: {self.on_plan}; "
            f"padding: 2px 6px; {agirlik}"
        )

    def kip_stili(self, canli: bool) -> str:
        """Kip etiketi: canli kip dikkat cekmeli (kazara canli calismayi onlemek icin)."""
        if self.monokrom:
            if canli:
                return self._ters_video()
            return f"color: {self.on_plan}; border: 1px solid {self.sonuk}; padding: 2px 6px;"
        zemin = self.tehlike_zemin if canli else self.iyi_zemin
        return f"color: white; background-color: {zemin}; padding: 2px 6px;"

    def deneme_stili(self) -> str:
        if self.monokrom:
            return f"color: {self.parlak}; border: 1px solid {self.on_plan}; padding: 2px 6px;"
        return f"color: white; background-color: {self.deneme_zemin}; padding: 2px 6px;"

    def eylem_stili(self) -> str:
        """Sonraki eylem satiri: en dikkat cekici metin."""
        renk = self.parlak if self.monokrom else self.vurgu
        return f"color: {renk}; font-size: 13pt;"

    def yorum_stili(self) -> str:
        """Girisin fiziksel karsiligini gosteren serit."""
        if self.monokrom:
            return (
                f"background-color: {self.panel_arka_plan}; color: {self.parlak}; "
                f"border: 1px solid {self.on_plan}; padding: 6px; font-size: 12pt;"
            )
        return (
            f"background-color: {self.uyari_zemin}; border: 1px solid {self.uyari_kenar}; "
            "padding: 6px; font-size: 12pt;"
        )

    def sonuc_stili(self) -> str:
        return f"font-size: 12pt; color: {self.on_plan}" + (";" if self.monokrom else "")

    def sonuk_stili(self) -> str:
        """Ikincil/gri metin (sutun basliklari, izleme satiri, istege bagli alanlar)."""
        renk = self.sonuk if self.monokrom else "gray"
        return f"color: {renk};"

    def zorunlu_stili(self) -> str:
        return "font-weight: bold;" + (f" color: {self.on_plan};" if self.monokrom else "")

    def durdur_stili(self) -> str:
        """DURDUR dugmesi: monokrom temalarda ters video, renkli temada kirmizi."""
        if self.monokrom:
            return self._ters_video()
        return f"color: white; background-color: {self.tehlike_zemin}; font-weight: bold;"


VARSAYILAN = Tema(
    ad="varsayilan",
    baslik="Varsayilan (sistem)",
    monokrom=False,
    arka_plan="",
    panel_arka_plan="",
    on_plan="",
    parlak="",
    sonuk="gray",
    cok_sonuk="gray",
)

FOSFOR_YESIL = Tema(
    ad="fosfor_yesil",
    baslik="Fosfor yesili (CRT)",
    monokrom=True,
    arka_plan="#050b05",
    panel_arka_plan="#020602",
    on_plan="#33ff33",
    parlak="#ccffcc",
    sonuk="#1ea81e",
    cok_sonuk="#0f5a0f",
    font_yigini=MONO_YIGIN,
)

FOSFOR_TURUNCU = Tema(
    ad="fosfor_turuncu",
    baslik="Fosfor turuncu (CRT)",
    monokrom=True,
    arka_plan="#0b0703",
    panel_arka_plan="#060301",
    on_plan="#ffb000",
    parlak="#ffe0a0",
    sonuk="#b37a00",
    cok_sonuk="#5c3f00",
    font_yigini=MONO_YIGIN,
)

TEMALAR: dict[str, Tema] = {
    tema.ad: tema for tema in (VARSAYILAN, FOSFOR_YESIL, FOSFOR_TURUNCU)
}


def tema_al(ad: str) -> Tema:
    """Ada gore tema dondurur; bilinmeyen ad icin aciklayici hata verir."""
    if ad not in TEMALAR:
        raise KeyError(
            f"Bilinmeyen tema: {ad!r}; secenekler: {', '.join(TEMALAR)}"
        )
    return TEMALAR[ad]
