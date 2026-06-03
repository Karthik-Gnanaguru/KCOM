#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────────
# KCom — Linux build script
# Produces: dist/KCom/  (directory bundle)
#
# Usage (from project root):
#   chmod +x build/build_linux.sh
#   ./build/build_linux.sh            # directory bundle
#   ./build/build_linux.sh --onefile  # single-file executable
# ──────────────────────────────────────────────────────────────────────────────
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

ICON="$ROOT/kcom/resources/icons/kcom_logo.png"

echo "── KCom Linux Build ──────────────────────────────────────────"
echo "Python  : $(python3 --version)"
echo "Root    : $ROOT"
echo

# Pick a usable Python (prefer python3, fall back to python)
PY="$(command -v python3 || command -v python || true)"
if [[ -z "$PY" ]]; then
    echo "ERROR: Python 3.11+ not found. Install it with:"
    echo "         sudo apt install python3 python3-pip python3-venv"
    exit 1
fi
echo "Using  : $PY"

# Install runtime + build tooling so PyInstaller can bundle everything
"$PY" -m pip install --quiet --upgrade pip
"$PY" -m pip install --quiet -r requirements.txt
"$PY" -m pip install --quiet "pyinstaller>=6.8.0"

# Clean previous artefacts
rm -rf dist/ build/__pycache__

EXTRA=""
if [[ "${1:-}" == "--onefile" ]]; then
    EXTRA="--onefile"
    echo "Mode: single-file executable"
else
    echo "Mode: directory bundle"
fi

"$PY" -m PyInstaller build/kcom.spec $EXTRA --noconfirm

# ── Strip unused Qt6 modules to slim the bundle ──────────────────────────
if [[ -d "dist/KCom" ]]; then
    "$PY" build/post_clean.py "dist/KCom"
fi

echo
echo "── Build complete ────────────────────────────────────────────"
echo "Output: $ROOT/dist/KCom"

# Optional: wrap in AppImage (requires appimagetool in PATH)
if command -v appimagetool &>/dev/null; then
    APPDIR="$ROOT/dist/KCom.AppDir"
    rm -rf "$APPDIR"
    mkdir -p "$APPDIR/usr/bin" "$APPDIR/usr/share/applications" \
             "$APPDIR/usr/share/icons/hicolor/256x256/apps"

    cp -r "$ROOT/dist/KCom/." "$APPDIR/usr/bin/"
    cp "$ICON" "$APPDIR/usr/share/icons/hicolor/256x256/apps/kcom.png"
    cp "$ICON" "$APPDIR/kcom.png"

    cat > "$APPDIR/usr/share/applications/kcom.desktop" <<'EOF'
[Desktop Entry]
Name=KCom
Comment=Professional Serial & Network Communication Studio
Exec=KCom
Icon=kcom
Type=Application
Categories=Development;Utility;
EOF
    cp "$APPDIR/usr/share/applications/kcom.desktop" "$APPDIR/"

    cat > "$APPDIR/AppRun" <<'APPRUN'
#!/bin/bash
HERE="$(dirname "$(readlink -f "$0")")"
exec "$HERE/usr/bin/KCom" "$@"
APPRUN
    chmod +x "$APPDIR/AppRun"

    ARCH=x86_64 appimagetool --comp xz "$APPDIR" "$ROOT/dist/KCom-linux-x86_64.AppImage"
    echo "AppImage: $ROOT/dist/KCom-linux-x86_64.AppImage"
fi
