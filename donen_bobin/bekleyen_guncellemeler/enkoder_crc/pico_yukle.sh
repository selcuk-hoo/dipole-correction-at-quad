#!/usr/bin/env bash
# Rotor ve stator firmware'ini derler ve Pico'lara yükler.
#
#   ./pico_yukle.sh            ikisini de derle, sırayla yükle (önce stator, sonra rotor)
#   ./pico_yukle.sh stator     yalnızca stator
#   ./pico_yukle.sh rotor      yalnızca rotor
#   ./pico_yukle.sh --derle    yalnızca derle, yükleme
#   --zorla                    CRC güncellemesi uygulanmamışken de çalış (eski firmware'e dönmek için)
#
# ÖNEMLİ: paket boyları değiştiği için rotor ve stator AYNI sürümde olmalı.
# Yalnızca birini yüklemek sistemi çalışmaz hâle getirir.
#
# Pico SDK: PICO_SDK_PATH ortam değişkeni ya da Pico VS Code eklentisinin
# ~/.pico-sdk kurulumu (CMakeLists.txt onu kendisi bulur).
set -euo pipefail

BURASI=$(cd "$(dirname "$0")" && pwd)
YAMA="$BURASI/enkoder_crc.patch"
KOK=$(git -C "$BURASI" rev-parse --show-toplevel)
FW="$KOK/donen_bobin"
DERLEME="$FW/build_pico_yukle"   # VS Code'un build/ klasörüne dokunmamak için ayrı

hedefler=()
yalniz_derle=0
zorla=0
for a in "$@"; do
    case "$a" in
        rotor|stator) hedefler+=("$a") ;;
        --derle) yalniz_derle=1 ;;
        --zorla) zorla=1 ;;
        *) echo "Bilinmeyen seçenek: $a" >&2; exit 2 ;;
    esac
done
[[ ${#hedefler[@]} -eq 0 ]] && hedefler=(stator rotor)

# --- Ön kontroller ----------------------------------------------------------
cd "$KOK"
if ! git apply --reverse --check "$YAMA" 2>/dev/null && [[ $zorla -eq 0 ]]; then
    echo "HATA: CRC güncellemesi kaynakta uygulanmamış. Önce ./uygula.sh çalıştırın" >&2
    echo "      (eski firmware'i yüklemek istiyorsanız --zorla ekleyin)." >&2
    exit 1
fi
if [[ -z "${PICO_SDK_PATH:-}" && ! -f "$HOME/.pico-sdk/cmake/pico-vscode.cmake" ]]; then
    echo "HATA: Pico SDK bulunamadı. PICO_SDK_PATH'i ayarlayın ya da Pico VS Code" >&2
    echo "      eklentisiyle SDK 2.2.0'ı kurun (~/.pico-sdk)." >&2
    exit 1
fi

# --- Derleme ----------------------------------------------------------------
echo "Derleniyor: ${hedefler[*]} ($DERLEME)"
cmake -S "$FW" -B "$DERLEME" -DCMAKE_BUILD_TYPE=Release >/dev/null
cmake --build "$DERLEME" -j"$(nproc)" --target "${hedefler[@]}"
for h in "${hedefler[@]}"; do
    [[ -f "$DERLEME/$h.uf2" ]] || { echo "HATA: $DERLEME/$h.uf2 oluşmadı." >&2; exit 1; }
done
echo "Derleme tamam: $(cd "$DERLEME" && ls "${hedefler[@]/%/.uf2}" | tr '\n' ' ')"
[[ $yalniz_derle -eq 1 ]] && exit 0

# --- Yükleme ----------------------------------------------------------------
picotool_bul() {
    command -v picotool 2>/dev/null && return
    local p
    for p in "$HOME"/.pico-sdk/picotool/*/picotool/picotool; do
        [[ -x "$p" ]] && { echo "$p"; return; }
    done
}
PICOTOOL=$(picotool_bul || true)

# BOOTSEL sürücüsünün bağlandığı yeri bekler (Pico 2'de etiketi RP2350)
surucu_bekle() {
    local i yer
    for ((i = 0; i < 120; i++)); do
        yer=$(findmnt -rn -o TARGET -S LABEL=RP2350 2>/dev/null | head -1 || true)
        [[ -n "$yer" ]] && { echo "$yer"; return 0; }
        sleep 0.5
    done
    return 1
}

yukle() {
    local h=$1 uf2="$DERLEME/$1.uf2"
    echo
    echo "=== $h ==="
    echo "Yalnızca $h Pico'sunu USB ile bağlayın (diğerini çıkarın)."
    echo "Pico çalışıyorsa picotool onu kendisi BOOTSEL'e alabilir; olmazsa BOOTSEL"
    echo "düğmesine basılı tutarak takın."
    read -rp "Hazır olunca Enter... " _
    if [[ -n "$PICOTOOL" ]] && "$PICOTOOL" load -x -f "$uf2"; then
        echo "$h yüklendi (picotool)."
        return
    fi
    echo "picotool ile olmadı; BOOTSEL sürücüsü bekleniyor (60 s)..."
    local yer
    yer=$(surucu_bekle) || { echo "HATA: RP2350 sürücüsü görünmedi." >&2; exit 1; }
    cp "$uf2" "$yer/" && sync
    echo "$h yüklendi ($yer)."
}

for h in "${hedefler[@]}"; do
    yukle "$h"
done
if [[ ${#hedefler[@]} -eq 1 ]]; then
    echo
    echo "UYARI: yalnızca $h yüklendi. Diğer Pico da aynı sürüme getirilmeden sistem doğru çalışmaz."
fi
echo
echo "Bitti. Doğrulama için README.md'deki 'Yükledikten sonra' adımlarına bakın."
