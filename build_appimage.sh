#!/usr/bin/env bash
# Build a self-contained AppImage for media-overlay-switchboard.
#
# Prerequisites:
#   - Python >= 3.10 with venv
#   - pip (within the venv)
#   - wget or curl (to download appimagetool if missing)
#
# Usage:
#   ./build_appimage.sh [--arch x86_64] [--deps-only]
#
set -euo pipefail

ARCH="${1:-x86_64}"
SCRIPT_DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
PROJECT="media-overlay-switchboard"
BUILD_DIR="$SCRIPT_DIR/build/appimage"
APP_DIR="$BUILD_DIR/AppDir"
VENV_DIR="$BUILD_DIR/venv"
PYINST_DIR="$BUILD_DIR/pyinstaller"
DIST_DIR="$SCRIPT_DIR/dist"

echo "==> Build: $PROJECT  arch=$ARCH"
echo "    Build dir: $BUILD_DIR"
echo "    Dist  dir: $DIST_DIR"

mkdir -p "$BUILD_DIR" "$DIST_DIR"

# ------------------------------------------------------------------
# 1. Create / reuse a venv and install the package + build deps
# ------------------------------------------------------------------
if [ ! -d "$VENV_DIR" ]; then
    echo "==> Creating venv …"
    python3 -m venv "$VENV_DIR"
fi

echo "==> Installing package & dependencies …"
"$VENV_DIR/bin/pip" install --upgrade pip
"$VENV_DIR/bin/pip" install \
    pyinstaller \
    "$SCRIPT_DIR[gui]"

# ------------------------------------------------------------------
# 2. Run PyInstaller
# ------------------------------------------------------------------
echo "==> Running PyInstaller …"
rm -rf "$PYINST_DIR"

"$VENV_DIR/bin/pyinstaller" \
    --distpath "$PYINST_DIR" \
    --workpath "$BUILD_DIR/pyibuild" \
    --specpath "$BUILD_DIR" \
    --onedir \
    --name mo-switchboard \
    --add-data "$SCRIPT_DIR/media_overlay_switchboard/resources:media_overlay_switchboard/resources" \
    --collect-all PySide6 \
    --collect-all PIL \
    --hidden-import media_overlay_switchboard.cli \
    --hidden-import media_overlay_switchboard.gui_launcher \
    --hidden-import media_overlay_switchboard.gui \
    --hidden-import media_overlay_switchboard.server \
    --hidden-import media_overlay_switchboard.client \
    --hidden-import media_overlay_switchboard.config \
    --hidden-import media_overlay_switchboard.socket_utils \
    --hidden-import media_overlay_switchboard.defaults \
    "$SCRIPT_DIR/media_overlay_switchboard/__main__.py" 2>&1

# ------------------------------------------------------------------
# 3. Assemble AppDir
# ------------------------------------------------------------------
echo "==> Assembling AppDir …"
rm -rf "$APP_DIR"
mkdir -p "$APP_DIR/usr/lib"
mkdir -p "$APP_DIR/usr/share/applications"
mkdir -p "$APP_DIR/usr/share/icons/hicolor/scalable/apps"

# PyInstaller bundle
cp -a "$PYINST_DIR/mo-switchboard" "$APP_DIR/usr/lib/mo-switchboard"

# Desktop file
cp "$SCRIPT_DIR/media-overlay-switchboard.desktop" \
   "$APP_DIR/usr/share/applications/"
cp "$SCRIPT_DIR/media-overlay-switchboard.desktop" \
   "$APP_DIR/"

# Icon (PNG for best compatibility with appimagetool)
cp "$SCRIPT_DIR/media_overlay_switchboard/resources/Lavers.svg" \
   "$APP_DIR/media-overlay-switchboard.svg"
cp "$SCRIPT_DIR/media_overlay_switchboard/resources/Lavers.svg" \
   "$APP_DIR/usr/share/icons/hicolor/scalable/apps/media-overlay-switchboard.svg"

# AppRun
cp "$SCRIPT_DIR/AppRun" "$APP_DIR/AppRun"
chmod +x "$APP_DIR/AppRun"

# Also create a symlink so `mo-switchboard-cli` works inside the AppImage
mkdir -p "$APP_DIR/usr/bin"
ln -sf ../../AppRun "$APP_DIR/usr/bin/mo-switchboard-cli"

# Fix the desktop file Icon line to point to the SVG in AppDir root
sed -i 's/^Icon=.*/Icon=media-overlay-switchboard/' "$APP_DIR/media-overlay-switchboard.desktop"

# ------------------------------------------------------------------
# 4. Find or download appimagetool
# ------------------------------------------------------------------
APPIMAGETOOL="$(command -v appimagetool 2>/dev/null || echo "$BUILD_DIR/appimagetool")"
if ! command -v appimagetool &>/dev/null; then
    if [ ! -f "$APPIMAGETOOL" ]; then
        echo "==> Downloading appimagetool …"
        URL="https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-$ARCH.AppImage"
        if command -v wget &>/dev/null; then
            wget -qO "$APPIMAGETOOL" "$URL"
        elif command -v curl &>/dev/null; then
            curl -sLo "$APPIMAGETOOL" "$URL"
        else
            echo "ERROR: need wget or curl to download appimagetool"
            exit 1
        fi
        chmod +x "$APPIMAGETOOL"
    fi
fi

# ------------------------------------------------------------------
# 5. Build the AppImage
# ------------------------------------------------------------------
echo "==> Building AppImage …"
APPIMAGETOOL_APPIMAGE="$APPIMAGETOOL"
# If appimagetool is an AppImage and we're root, extract it first
if [[ "$(id -u)" == "0" ]] && [[ "$APPIMAGETOOL" == *.AppImage ]]; then
    APPIMAGE_EXTRACT=1 "$APPIMAGETOOL" --version 2>/dev/null || true
    EXTRACTED="$BUILD_DIR/appimagetool-extracted"
    if [ ! -d "$EXTRACTED" ]; then
        "$APPIMAGETOOL" --appimage-extract 2>/dev/null || true
        mv squashfs-root "$EXTRACTED" 2>/dev/null || true
    fi
    if [ -f "$EXTRACTED/AppRun" ]; then
        APPIMAGETOOL_APPIMAGE="$EXTRACTED/AppRun"
    fi
fi

export VERSION="$(cd "$SCRIPT_DIR" && python -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])")"
ARCH="$ARCH" "$APPIMAGETOOL_APPIMAGE" \
    "$APP_DIR" \
    "$DIST_DIR/$PROJECT-$VERSION-$ARCH.AppImage"

echo ""
echo "==> SUCCESS: $DIST_DIR/$PROJECT-$VERSION-$ARCH.AppImage"
