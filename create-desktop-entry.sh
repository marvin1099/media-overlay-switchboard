#!/usr/bin/env bash
# Create a desktop entry and install the app icon for
# Media Overlay Switchboard.
#
# Usage:
#   ./create-desktop-entry.sh                    # uses mo-switchboard-gui
#   ./create-desktop-entry.sh --appimage /path   # uses the given AppImage
#
# When running inside an AppImage, the AppImage path is auto-detected
# from the $APPIMAGE environment variable.

set -euo pipefail

appimage=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --appimage)
            appimage="$2"
            shift 2
            ;;
        --help|-h)
            sed -n '/^#/{/^#\!/d;s/^# \?//p;q}' "$0"
            exit 0
            ;;
        *)
            echo "Unknown argument: $1  (use --help for usage)"
            exit 1
            ;;
    esac
done

if [[ -z "$appimage" && -n "${APPIMAGE:-}" ]]; then
    appimage="$APPIMAGE"
fi

export MOS_APPIMAGE_PATH="$appimage"

if python3 -c "
import os
from media_overlay_switchboard.desktop_entry import create_desktop_entry
import sys
result = create_desktop_entry(os.environ.get('MOS_APPIMAGE_PATH') or None)
sys.exit(0 if result else 1)
"; then
    echo "Desktop entry created successfully."
else
    echo "error: desktop entry creation failed."
    echo "Make sure media-overlay-switchboard is installed:"
    echo "  uv tool install media-overlay-switchboard"
    exit 1
fi
