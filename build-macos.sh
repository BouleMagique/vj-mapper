#!/usr/bin/env bash
# =============================================================================
# VJ Mapper — Build macOS (.app)
# =============================================================================
# Produit dist/VJMapper.app + dist/VJMapper-macos-<arch>.zip
#
# Usage :
#   bash build-macos.sh                     # arch native (arm64 sur Apple Silicon)
#   TARGET_ARCH=x86_64 bash build-macos.sh  # Mac Intel (ex. Mac Pro 2013, Monterey)
#                                           # depuis un Mac Apple Silicon, via Rosetta
#
# Build Intel : les wheels imgui-bundle x86_64 exigent macOS 14 ; pour viser
# macOS 12 on le compile depuis les sources (long : ~20-40 min, cmake recupere
# par pip). Python 3.12 recupere par uv (~/.local/bin, sans sudo).
# =============================================================================
set -euo pipefail

APP="VJMapper"
ENTRY="main.py"
ARCH="${TARGET_ARCH:-$(uname -m)}"
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD="$HOME/.cache/vj-mapper-build-macos-$ARCH"
OUT="$SRC/dist"
PYREQ="3.12"
RUN=""
PIPFLAGS=""
if [ "$ARCH" = "x86_64" ]; then
    export MACOSX_DEPLOYMENT_TARGET=12.0
    PIPFLAGS="--no-binary imgui-bundle"
    [ "$(uname -m)" = "arm64" ] && RUN="arch -x86_64"
fi

echo ""
echo "=== VJ Mapper — Build macOS (.app) ==="
echo "Source : $SRC"
echo "Build  : $BUILD"
echo "Arch   : $ARCH"
echo ""

# --- Python 3.12 (uv, de la bonne arch) -------------------------------------
UV="$(command -v uv || echo "$HOME/.local/bin/uv")"
if [ ! -x "$UV" ]; then
    echo "[..] Installation de uv (~/.local/bin, sans sudo)..."
    curl -LsSf https://astral.sh/uv/install.sh | sh >/dev/null
    UV="$HOME/.local/bin/uv"
fi
PYKEY="cpython-$PYREQ-macos-$ARCH-none"
"$UV" python install "$PYKEY" >/dev/null
PY="$("$UV" python find "$PYKEY")"
echo "[OK] Python $($RUN "$PY" -c 'import sys,platform;print("%d.%d.%d"%sys.version_info[:3], platform.machine())')"

# --- Copie source ------------------------------------------------------------
echo "[..] Copie des sources..."
mkdir -p "$BUILD/src"
rsync -a --delete \
    --exclude venv --exclude .git --exclude __pycache__ --exclude dist --exclude build \
    "$SRC"/ "$BUILD/src"/
cd "$BUILD/src"

# --- Venv + deps + PyInstaller ----------------------------------------------
[ -d venv ] || $RUN "$PY" -m venv venv
echo "[..] Installation des dependances + PyInstaller..."
[ -n "$PIPFLAGS" ] && echo "     (imgui-bundle compile depuis les sources : long)"
$RUN venv/bin/pip install --upgrade pip -q
$RUN venv/bin/pip install $PIPFLAGS -r requirements.txt -q
$RUN venv/bin/pip install pyinstaller -q
echo "[OK] Environnement de build pret"

# --- PyInstaller : bundle .app ----------------------------------------------
echo "[..] PyInstaller..."
IMGUI_DIR="$($RUN venv/bin/python -c 'import imgui_bundle,os;print(os.path.dirname(imgui_bundle.__file__))')"
rm -rf dist build
$RUN venv/bin/pyinstaller --windowed --name "$APP" --target-arch "$ARCH" \
    --osx-bundle-identifier "com.boulemagique.vjmapper" \
    --add-data "$BUILD/src/vjmapper/shaders:vjmapper/shaders" \
    --add-data "$BUILD/src/scenes/example_garage_door.json:scenes" \
    --add-data "$IMGUI_DIR/assets/fonts:imgui_bundle/assets/fonts" \
    --collect-binaries glfw \
    --collect-all moderngl --collect-all glcontext \
    "$ENTRY"
[ -d "dist/$APP.app" ] || { echo "[ERREUR] dist/$APP.app absent." >&2; exit 1; }

# Sans NSMicrophoneUsageDescription, macOS refuse les entrees audio (BlackHole
# compris) sans meme demander. App Nap coupe : la sortie projo ne doit pas
# ralentir quand la fenetre de controle passe derriere.
PLIST="dist/$APP.app/Contents/Info.plist"
plutil -replace NSMicrophoneUsageDescription -string \
    "Analyse en direct du son (BlackHole, entree ligne) pour animer le mapping." "$PLIST"
plutil -replace LSAppNapIsDisabled -bool YES "$PLIST"
codesign --force --deep --sign - "dist/$APP.app"
echo "[OK] Bundle genere : dist/$APP.app"

# --- Livrable ----------------------------------------------------------------
mkdir -p "$OUT"
rm -rf "$OUT/$APP.app" "$OUT/$APP-macos-$ARCH.zip"
cp -R "dist/$APP.app" "$OUT/$APP.app"
# ditto (et pas zip) : preserve liens symboliques et metadonnees du bundle
ditto -c -k --keepParent "$OUT/$APP.app" "$OUT/$APP-macos-$ARCH.zip"

echo ""
echo "=== TERMINE ==="
echo "Livrable : $OUT/$APP-macos-$ARCH.zip"
echo ""
echo "Note : bundle NON signe. Premier lancement :"
echo "       xattr -dr com.apple.quarantine '$APP.app' puis clic droit > Ouvrir."
