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

    The file uses a per-suffix structure::

        {"default": {…}, "myshow": {…}}

    Each top-level key is a socket suffix, and its value is the full set
    of config fields for that instance.  The ``"default"`` entry is used
    as a fallback when no suffix-specific config exists.

    Fields
    ------
    text_file       – path to the text entries file
    images_folder   – path to the folder with overlay images
    target_folder   – path where output files (overlay_text.txt,
                      overlay_image.png) are written
    text_separator  – string that separates entries in the text file
    ask_socket      – multi-instance socket selection (true=prompt,
                      false=auto-pick, null=warn)
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
        self.no_tray: bool = False
        self._used_fallback: bool = False

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------
    @classmethod
    def load(cls, suffix: str = "default") -> "Config":
        """Load the config for *suffix* from disk.

        Falls back to ``"default"`` when no entry for *suffix* exists.
        Automatically migrates a legacy flat config into the per-suffix
        structure on first access.
        """
        cfg = cls()
        config_path = get_config_dir() / "config.json"
        if not config_path.exists():
            cfg._used_fallback = False
            return cfg
        try:
            data = json.loads(config_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            cfg._used_fallback = False
            return cfg

        # Detect old flat format → migrate to per-suffix
        if not _is_suffixed(data):
            _migrate_to_suffixed(data, config_path)
            data = {suffix: data}

        section = data.get(suffix)
        if not section:
            section = data.get("default")
        cfg._used_fallback = (
            section is not data.get(suffix)
            and section is not None
        )
        if section and isinstance(section, dict):
            for key, value in section.items():
                if hasattr(cfg, key):
                    setattr(cfg, key, value)
        return cfg

    def save(self, suffix: str = "default") -> None:
        """Write the current config under *suffix* to disk."""
        config_path = get_config_dir() / "config.json"
        try:
            data = json.loads(config_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            data = {}
        if not _is_suffixed(data):
            data = {}

        data[suffix] = {
            k: v for k, v in self.__dict__.items() if not k.startswith("_")
        }
        config_path.write_text(
            json.dumps(data, indent=2, default=str),
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
            "no_tray",
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


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _is_suffixed(data: dict) -> bool:
    """Return True if *data* looks like a per-suffix config structure."""
    if not data:
        return True
    # Suffixed format: every top-level value is itself a dict.
    return all(isinstance(v, dict) for v in data.values())


def _migrate_to_suffixed(data: dict, config_path: Path) -> None:
    """Wrap a legacy flat config under the ``"default"`` key."""
    suffixed = {"default": data}
    config_path.write_text(
        json.dumps(suffixed, indent=2, default=str),
        encoding="utf-8",
    )
