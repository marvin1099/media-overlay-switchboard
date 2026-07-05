# Socket path helpers – multi-instance support via configurable suffixes.
#
# Each server instance binds a Unix socket at
#   $XDG_RUNTIME_DIR/media-overlay-switchboard-<suffix>.sock
# The default suffix is "default".  If a socket is already taken the
# server auto-increments (default → default1 → default2 …).

import os
import socket
from pathlib import Path

from .config import get_runtime_dir
from .defaults import PROJECT_NAME


def get_socket_path(suffix: str) -> Path:
    """Return the absolute socket path for a given *suffix*."""
    return get_runtime_dir() / f"{PROJECT_NAME}-{suffix}.sock"


def is_port_alive(socket_path: Path) -> bool:
    """Return True when a working server is listening at *socket_path*.

    Removes stale socket files automatically so they don't accumulate.
    """
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(1.0)
        s.connect(str(socket_path))
        s.close()
        return True
    except (ConnectionRefusedError, FileNotFoundError, OSError):
        if socket_path.exists():
            try:
                socket_path.unlink()
            except OSError:
                pass
        return False


def find_available_suffix(base_suffix: str) -> str:
    """Return a suffix that is not in use, auto-incrementing when needed.

    Examples
    --------
    find_available_suffix("default") → "default"
    # (if "default" is taken)       → "default1"
    # (if "default1" is also taken) → "default2"
    """
    suffix = base_suffix
    counter = 0
    while True:
        sock_path = get_socket_path(suffix)
        if not sock_path.exists() or not is_port_alive(sock_path):
            return suffix
        counter += 1
        suffix = f"{base_suffix}{counter}"


def list_active_sockets() -> list[tuple[str, Path]]:
    """Scan the runtime directory and return (suffix, path) for every
    server socket that is currently accepting connections."""
    runtime_dir = get_runtime_dir()
    if not runtime_dir.exists():
        return []
    active: list[tuple[str, Path]] = []
    for entry in sorted(runtime_dir.iterdir()):
        if entry.suffix == ".sock" and entry.stem.startswith(f"{PROJECT_NAME}-"):
            suffix = entry.stem[len(f"{PROJECT_NAME}-"):]
            if is_port_alive(entry):
                active.append((suffix, entry))
    return active
