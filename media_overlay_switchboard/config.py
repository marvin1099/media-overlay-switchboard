# Configuration management for media-overlay-switchboard
# Uses XDG_CONFIG_HOME for persistent JSON config storage.
# Falls back to ~/.config/<project> when XDG_CONFIG_HOME is unset.

import json
import os
from pathlib import Path

from .defaults import (
    PROJECT_NAME,
    DEFAULT_TEXT_SEPARATOR,
    DEFAULT_TRANSPARENT_SIZE,
)


def get_config_dir() -> Path:
    """Return the per-project XDG config directory, creating it if needed."""
    xdg_config = os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")
    path = Path(xdg_config) / PROJECT_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_runtime_dir() -> Path:
    """Return the runtime directory for Unix socket files.

    Uses XDG_RUNTIME_DIR on Linux; falls back to ~/.cache/<project>.
    """
    xdg_runtime = os.environ.get("XDG_RUNTIME_DIR")
    if xdg_runtime:
        path = Path(xdg_runtime) / PROJECT_NAME
    else:
        path = Path.home() / ".cache" / PROJECT_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def parse_config_value(value: str):
    """Parse a CLI-provided string into the appropriate Python type.

    Handles null/None, booleans, ints, and falls back to plain string.
    """
    v = value.strip()
    if v.lower() in ("", "null", "none"):
        return None
    if v.lower() in ("true", "yes", "1"):
        return True
    if v.lower() in ("false", "no", "0"):
        return False
    try:
        return int(v)
    except ValueError:
        try:
            return float(v)
        except ValueError:
            return v


class Config:
    """Persistent configuration stored as JSON inside XDG_CONFIG_HOME.

    Fields
    ------
    text_file       – path to the text entries file
    images_folder   – path to the folder with overlay images
    target_folder   – path where output files (overlay_text.txt,
                      overlay_image.png) are written
    text_separator  – string that separates entries in the text file
    ask_socket      – whether to prompt/interactively pick a socket when
                      multiple server instances are running
    transparent_width / transparent_height – dimensions of the generated
                      transparent placeholder image
    """

    def __init__(self):
        self.text_file: str = ""
        self.images_folder: str = ""
        self.target_folder: str = ""
        self.text_separator: str = DEFAULT_TEXT_SEPARATOR
        self.ask_socket: bool | None = None
        self.transparent_width: int = DEFAULT_TRANSPARENT_SIZE[0]
        self.transparent_height: int = DEFAULT_TRANSPARENT_SIZE[1]
        self.text_index: int = 0
        self.image_index: int = 0
        self.hide_to_tray_no_warn: bool = False

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------
    @classmethod
    def load(cls) -> "Config":
        """Load the config from disk.  Returns a default config when the
        file is missing or corrupt."""
        cfg = cls()
        config_path = get_config_dir() / "config.json"
        if config_path.exists():
            try:
                data = json.loads(config_path.read_text(encoding="utf-8"))
                for key, value in data.items():
                    if hasattr(cfg, key):
                        setattr(cfg, key, value)
            except (json.JSONDecodeError, OSError):
                pass  # corrupt file – carry on with defaults
        return cfg

    def save(self) -> None:
        """Write the current config to disk."""
        config_path = get_config_dir() / "config.json"
        config_path.write_text(
            json.dumps(self.__dict__, indent=2, default=str),
            encoding="utf-8",
        )

    # ------------------------------------------------------------------
    # CLI override helper
    # ------------------------------------------------------------------
    def update_from_cli(self, ns: object) -> None:
        """Overlay CLI-parsed attributes on the current config values.

        Keys that were *not* provided by the user are left untouched.
        """
        for key in (
            "text_file",
            "images_folder",
            "target_folder",
            "text_separator",
            "ask_socket",
            "transparent_width",
            "transparent_height",
        ):
            val = getattr(ns, key, None)
            if val is not None:
                setattr(self, key, val)

    # ------------------------------------------------------------------
    # Convenience accessors
    # ------------------------------------------------------------------
    @property
    def transparent_size(self) -> tuple[int, int]:
        return (self.transparent_width, self.transparent_height)
