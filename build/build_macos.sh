#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────────
# KCom — macOS build script
# Produces: dist/KCom.app  (and optionally dist/KCom-macos.dmg)
#
# Usage (from project root):
#   chmod +x build/build_macos.sh
#   ./build/build_macos.sh
#
# Optional (for DMG):
#   brew install create-dmg
# ──────────────────────────────────────────────────────────────────────────────
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

ICON_PNG="$ROOT/kcom/resources/icons/kcom_logo.png"

PY="$(command -v python3 || command -v python || true)"
if [[ -z "$PY" ]]; then
    echo "ERROR: Python 3.11+ not found. Install it with:  brew install python@3.11"
    exit 1
fi

echo "── KCom macOS Build ──────────────────────────────────────────"
echo "Python  : $($PY --version)"
echo "Using   : $PY"
echo "Root    : $ROOT"
echo

"$PY" -m pip install --quiet --upgrade pip
"$PY" -m pip install --quiet -r requirements.txt
"$PY" -m pip install --quiet "pyinstaller>=6.8.0"

rm -rf dist/ build/__pycache__

"$PY" -m PyInstaller build/kcom.spec \
    --noconfirm \
    --windowed \
    --osx-bundle-identifier "com.kcom.app"

APP="dist/KCom.app"

# ── Strip unused Qt6 modules to slim the .app bundle ─────────────────────
if [[ -d "$APP" ]]; then
    "$PY" build/post_clean.py "$APP"
fi

echo
echo "── App bundle ready ──────────────────────────────────────────"
echo "Output: $ROOT/$APP"

# Convert PNG → ICNS and embed in the bundle (macOS only)
if command -v sips &>/dev/null && command -v iconutil &>/dev/null; then
    ICONSET="$ROOT/dist/kcom.iconset"
    mkdir -p "$ICONSET"
    for size in 16 32 64 128 256 512; do
        sips -z $size $size "$ICON_PNG" --out "$ICONSET/icon_${size}x${size}.png" &>/dev/null
        sips -z $((size*2)) $((size*2)) "$ICON_PNG" \
             --out "$ICONSET/icon_${size}x${size}@2x.png" &>/dev/null
    done
    iconutil -c icns "$ICONSET" -o "$APP/Contents/Resources/kcom.icns" 2>/dev/null || true
    rm -rf "$ICONSET"
    echo "Icon:   embedded kcom.icns"
fi

# Optional: wrap in DMG
if command -v create-dmg &>/dev/null; then
    echo "Creating DMG…"
    create-dmg \
        --volname "KCom" \
        --window-size 600 400 \
        --icon-size 128 \
        --icon "KCom.app" 175 190 \
        --app-drop-link 425 190 \
        "dist/KCom-macos.dmg" \
        "dist/"
    echo "DMG:    $ROOT/dist/KCom-macos.dmg"
else
    echo "(create-dmg not found — install with: brew install create-dmg)"
fi
