#!/usr/bin/env bash
# Enkoder CRC güncellemesini koda uygular: Pico firmware'i (rotor + stator) ve
# bilgisayardaki ölçüm programı birlikte, tek yamayla. Sonra testleri çalıştırır.
#
#   ./uygula.sh            uygula ve test et
#   ./uygula.sh --testsiz  yalnızca uygula
#
# Pico'lara yüklemek ayrı adım: ./pico_yukle.sh
set -euo pipefail

BURASI=$(cd "$(dirname "$0")" && pwd)
YAMA="$BURASI/enkoder_crc.patch"
KOK=$(git -C "$BURASI" rev-parse --show-toplevel)
cd "$KOK"

if git apply --reverse --check "$YAMA" 2>/dev/null; then
    echo "Güncelleme zaten uygulanmış."
elif git apply --check "$YAMA" 2>/dev/null; then
    # --index: yamanın eklediği yeni dosyalar (testler) da git'e eklenir
    git apply --index "$YAMA" 2>/dev/null || git apply "$YAMA"
    echo "Güncelleme uygulandı (firmware + bilgisayar)."
else
    echo "Yama doğrudan uymuyor (kod o tarihten beri değişmiş); üç yollu birleştirme deneniyor..."
    if ! git apply --3way "$YAMA"; then
        echo "HATA: çakışma var. 'git status' ile çakışan dosyalara bakın, elle çözün." >&2
        exit 1
    fi
    echo "Güncelleme birleştirilerek uygulandı; 'git diff' ile kontrol edin."
fi

if [[ "${1:-}" == "--testsiz" ]]; then
    exit 0
fi

# Testler: firmware CRC'si g++ ile bilgisayarda derlenip sınanır (Pico gerekmez),
# ölçüm programının testleri de sayaç bildirimini sınar.
PY=${PYTHON:-}
if [[ -z "$PY" ]]; then
    if [[ -x "$HOME/venvs/merkezleme/bin/python" ]]; then
        PY="$HOME/venvs/merkezleme/bin/python"
    else
        PY=python3
    fi
fi
echo "Testler çalışıyor ($PY)..."
cd "$KOK/donen_bobin/host"
QT_QPA_PLATFORM=offscreen "$PY" -m pytest tests/ -q
echo
echo "Tamam. Sıradaki adım: Pico'lara yüklemek ($BURASI/pico_yukle.sh)."
echo "Değişiklikleri kaydetmek için:"
echo "  git add donen_bobin && git commit -m 'Enkoder CRC guncellemesi uygulandi'"
