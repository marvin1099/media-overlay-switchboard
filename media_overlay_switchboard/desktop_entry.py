import os
import shlex
import shutil
import stat
from pathlib import Path
from importlib.resources import files as resource_files


DESKTOP_TEMPLATE = """\
[Desktop Entry]
Name=Media Overlay Switchboard
Comment=Media output switcher for streaming overlays
Exec={executable}
Icon=media-overlay-switchboard
Terminal={terminal}
Type=Application
Categories=AudioVideo;Utility;
StartupNotify=false
"""

ICON_NAME = "media-overlay-switchboard"
ICON_TARGET = "hicolor/scalable/apps"


def _get_icon_source() -> Path | None:
    res = resource_files("media_overlay_switchboard.resources")
    svg = res / "Lavers.svg"
    if svg.is_file():
        return svg
    png = res / "Lavers.png"
    if png.is_file():
        return png
    return None


def _user_data_dir() -> Path:
    return Path.home() / ".local" / "share"


def _detect_appimage() -> str | None:
    return os.environ.get("APPIMAGE")


def _gui_available() -> bool:
    """Return True if PySide6 can be imported (GUI mode available)."""
    try:
        import PySide6  # noqa: F401
        return True
    except ImportError:
        return False


def create_desktop_entry(
    appimage_path: str | None = None,
    terminal: bool | None = None,
) -> str | None:
    """Create a desktop entry and install the app icon.

    Parameters
    ----------
    appimage_path :
        Path to the AppImage file.  When set, the ``Exec`` line in the
        .desktop file will point to this path.  If *None*, the function
        checks ``$APPIMAGE``; if that's also unset, it uses the
        ``mo-switchboard-gui`` command.
    terminal :
        Whether the application needs a terminal (``Terminal=true``).
        When *None* (default), auto-detect: ``True`` if PySide6 is not
        available, ``False`` otherwise.

    Returns
    -------
    The path to the created .desktop file, or *None* on failure.
    """
    if appimage_path is None:
        appimage_path = _detect_appimage()

    if terminal is None:
        terminal = not _gui_available()

    icon_src = _get_icon_source()
    if icon_src is None:
        print("error: could not locate app icon (Lavers.svg / Lavers.png)")
        return None

    data_dir = _user_data_dir()
    icons_dir = data_dir / "icons" / ICON_TARGET
    icons_dir.mkdir(parents=True, exist_ok=True)

    suffix = icon_src.suffix  # .svg or .png
    icon_dst = icons_dir / f"{ICON_NAME}{suffix}"

    # Remove old icon first (in case type changed, e.g. .png → .svg)
    icon_dst.unlink(missing_ok=True)

    shutil.copy2(icon_src, icon_dst)
    print(f"Installed icon → {icon_dst}")

    # Also install a .png fallback if the source is .svg
    if suffix == ".svg":
        png_dst = icons_dir / f"{ICON_NAME}.png"
        png_dst.unlink(missing_ok=True)
        try:
            import subprocess
            subprocess.run(
                ["rsvg-convert", "-o", str(png_dst), str(icon_src)],
                capture_output=True, timeout=30,
            )
            if png_dst.is_file():
                print(f"Rendered PNG fallback → {png_dst}")
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass  # rsvg-convert not available – no big deal

    # Determine executable
    if appimage_path:
        executable = shlex.quote(str(appimage_path))
    else:
        executable = "mo-switchboard-gui"

    apps_dir = data_dir / "applications"
    apps_dir.mkdir(parents=True, exist_ok=True)
    desktop_path = apps_dir / f"{ICON_NAME}.desktop"

    desktop_content = DESKTOP_TEMPLATE.format(
        executable=executable,
        terminal="true" if terminal else "false",
    )
    desktop_path.write_text(desktop_content, encoding="utf-8")
    desktop_path.chmod(desktop_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    print(f"Created desktop entry \u2192 {desktop_path}")

    return str(desktop_path)
