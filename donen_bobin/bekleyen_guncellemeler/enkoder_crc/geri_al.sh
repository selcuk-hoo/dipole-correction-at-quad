#!/usr/bin/env bash
# uygula.sh'ın yaptığını geri alır (henüz commit'lenmemişse ya da commit'ten
# sonra yeniden eski koda dönmek gerekirse). Pico'lardaki firmware'e dokunmaz:
# eski firmware'e dönmek için bundan sonra pico_yukle.sh --zorla çalıştırılır.
set -euo pipefail

BURASI=$(cd "$(dirname "$0")" && pwd)
YAMA="$BURASI/enkoder_crc.patch"
KOK=$(git -C "$BURASI" rev-parse --show-toplevel)
cd "$KOK"

if git apply --check "$YAMA" 2>/dev/null; then
    echo "Güncelleme zaten uygulanmamış."
    exit 0
fi
git apply --index --reverse "$YAMA" 2>/dev/null || git apply --reverse "$YAMA"
echo "Güncelleme geri alındı (firmware kaynağı + bilgisayar)."
