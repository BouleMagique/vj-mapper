#!/usr/bin/env bash
# =============================================================================
# VJ Mapper — Build Linux (AppImage)
# =============================================================================
# Produit dist/VJMapper-x86_64.AppImage : un seul fichier, chmod +x -> ca tourne.
# Python + GLFW + ImGui + ModernGL + shaders bundles.
#
# Usage :
#   bash build-linux.sh
#
# Le build se fait dans un dossier LOCAL (~/.cache), PyInstaller casse sur CIFS.
# =============================================================================
set -euo pipefail

APP="VJMapper"
ENTRY="main.py"
ARCH="x86_64"
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD="${XDG_CACHE_HOME:-$HOME/.cache}/vj-mapper-build"
TOOLS="$BUILD/tools"
APPDIR="$BUILD/AppDir"
OUT="$SRC/dist"

echo ""
echo "=== VJ Mapper — Build Linux (AppImage) ==="
echo "Source : $SRC"
echo "Build  : $BUILD"
echo ""

# --- Python -----------------------------------------------------------------
command -v python3 >/dev/null || { echo "[ERREUR] python3 introuvable." >&2; exit 1; }
python3 -c 'import sys; exit(0 if sys.version_info >= (3,11) else 1)' \
    || { echo "[ERREUR] Python 3.11+ requis." >&2; exit 1; }
echo "[OK] Python $(python3 -c 'import sys;print("%d.%d"%sys.version_info[:2])')"

# --- Copie source -----------------------------------------------------------
echo "[..] Copie des sources..."
mkdir -p "$BUILD/src"
rsync -a --delete \
    --exclude venv --exclude .git --exclude __pycache__ \
    --exclude dist --exclude build --exclude AppDir --exclude tools \
    "$SRC"/ "$BUILD/src"/
cd "$BUILD/src"

# --- Venv + deps + PyInstaller ----------------------------------------------
[ -d venv ] || python3 -m venv venv
echo "[..] Installation des dependances + PyInstaller..."
venv/bin/pip install --upgrade pip -q
venv/bin/pip install -r requirements.txt -q
venv/bin/pip install pyinstaller -q
echo "[OK] Environnement de build pret"

# --- PyInstaller : bundle onedir --------------------------------------------
echo "[..] PyInstaller..."
IMGUI_DIR="$(venv/bin/python -c 'import imgui_bundle,os;print(os.path.dirname(imgui_bundle.__file__))')"
rm -rf dist build
venv/bin/pyinstaller --onedir --windowed --name "$APP" \
    --add-data "$BUILD/src/vjmapper/shaders:vjmapper/shaders" \
    --add-data "$BUILD/src/scenes/example_garage_door.json:scenes" \
    --add-data "$IMGUI_DIR/assets/fonts:imgui_bundle/assets/fonts" \
    --collect-binaries glfw \
    --collect-all moderngl --collect-all glcontext \
    "$ENTRY"
echo "[OK] Bundle genere : dist/$APP/"

# --- appimagetool -----------------------------------------------------------
mkdir -p "$TOOLS"
if [ ! -x "$TOOLS/appimagetool" ]; then
    echo "[..] Telechargement d'appimagetool..."
    curl -sSL -o "$TOOLS/appimagetool" \
        "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-${ARCH}.AppImage"
    chmod +x "$TOOLS/appimagetool"
fi

# --- AppDir -----------------------------------------------------------------
echo "[..] Assemblage de l'AppDir..."
rm -rf "$APPDIR"; mkdir -p "$APPDIR/usr/bin"
cp -r "dist/$APP" "$APPDIR/usr/bin/$APP"

# Icone 256x256 (barres verticales sur fond sombre) — pur Python, sans dep
venv/bin/python - "$APPDIR/vj-mapper.png" <<'PY'
import sys, zlib, struct
W=H=256
def px(x,y):
    on = (x // 32) % 2 == 1 and 24 < y < 232 or 120 < y < 136 and 24 < x < 232
    if not on: return (12,12,18,255)
    t = y / H
    return (int(60+180*t), int(200-120*t), 255, 255)
raw=bytearray()
for y in range(H):
    raw.append(0)
    for x in range(W): raw+=bytes(px(x,y))
def ch(t,d): return struct.pack(">I",len(d))+t+d+struct.pack(">I",zlib.crc32(t+d)&0xffffffff)
png=b"\x89PNG\r\n\x1a\n"+ch(b"IHDR",struct.pack(">IIBBBBB",W,H,8,6,0,0,0))+ch(b"IDAT",zlib.compress(bytes(raw),9))+ch(b"IEND",b"")
open(sys.argv[1],"wb").write(png)
PY

cat > "$APPDIR/$APP.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=VJ Mapper
Comment=Mapping 2D audio-reactif pour la projection
Exec=VJMapper
Icon=vj-mapper
Categories=AudioVideo;Video;Graphics;
Terminal=false
EOF

cat > "$APPDIR/AppRun" <<EOF
#!/bin/bash
HERE="\$(dirname "\$(readlink -f "\$0")")"
exec "\$HERE/usr/bin/$APP/$APP" "\$@"
EOF
chmod +x "$APPDIR/AppRun"

# --- Build AppImage ----------------------------------------------------------
echo "[..] Build de l'AppImage..."
mkdir -p "$OUT"
ARCH="$ARCH" APPIMAGE_EXTRACT_AND_RUN=1 \
    "$TOOLS/appimagetool" "$APPDIR" "$OUT/$APP-$ARCH.AppImage"

echo ""
echo "=== TERMINE ==="
echo "Livrable : $OUT/$APP-$ARCH.AppImage"
echo "Scenes   : ~/Documents/VJ Mapper (creees au premier lancement)"
