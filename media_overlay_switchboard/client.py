# Client – sends JSON commands to a running server over a Unix socket.

import json
import socket
import sys
from pathlib import Path

from .config import Config
from .socket_utils import get_socket_path, list_active_sockets


def send_command(suffix: str, command: str, **kwargs) -> dict:
    """Connect to *suffix*, send *command* (with optional extra keyword
    arguments inside the JSON payload), and return the parsed response."""
    sock_path = get_socket_path(suffix)
    if not sock_path.exists():
        return {"status": "error", "message": f"No server found with suffix '{suffix}'"}

    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(5.0)
    try:
        s.connect(str(sock_path))
        payload: dict = {"command": command, **kwargs}
        s.sendall(json.dumps(payload).encode("utf-8"))
        data = s.recv(65536)
        if not data:
            return {"status": "error", "message": "Empty response from server"}
        return json.loads(data.decode("utf-8"))
    except (ConnectionRefusedError, FileNotFoundError) as exc:
        return {"status": "error", "message": f"Cannot connect to server: {exc}"}
    except json.JSONDecodeError:
        return {"status": "error", "message": "Invalid JSON response from server"}
    finally:
        s.close()


def resolve_target_suffix(
    config: Config,
    preferred_suffix: str | None = None,
    no_ask: bool = False,
) -> str | None:
    """Determine which socket suffix to connect to.

    Parameters
    ----------
    config :
        Application config (used for the ``ask_socket`` setting).
    preferred_suffix :
        Explicit suffix from ``--suffix`` – used directly when given.
    no_ask :
        Temporarily overrides *ask_socket* to ``False``.

    Returns
    -------
    * A suffix string when a target is found (or assumed).
    * ``None`` when resolution fails and the caller should abort.
    """
    if preferred_suffix:
        return preferred_suffix

    active = list_active_sockets()

    if not active:
        return "default"  # will produce a clear connection error later

    if len(active) == 1:
        return active[0][0]

    # ---- multiple instances running -------------------------------------
    ask = config.get_ask_socket(active[0][0])

    if ask is None:
        # default – warn and auto-pick
        print(
            f"Warning: {len(active)} server instances running. "
            f"Using '{active[0][0]}'.",
            file=sys.stderr,
        )
        print(
            "  Set ask_socket.<suffix> to true  for interactive selection, "
            "or false to suppress this message.",
            file=sys.stderr,
        )
        for suffix, _ in active:
            if suffix == "default":
                return suffix
        return active[0][0]

    if ask and not no_ask:
        if sys.stdin.isatty():
            print(f"Multiple server instances ({len(active)}). Pick one:")
            for i, (suffix, path) in enumerate(active, 1):
                print(f"  [{i}] {suffix}  ({path})")
            print("  [0] Cancel")
            try:
                choice = input("Number: ").strip()
                idx = int(choice)
                if idx == 0:
                    return None
                if 1 <= idx <= len(active):
                    return active[idx - 1][0]
            except (ValueError, EOFError):
                pass
            print("Invalid choice. Aborting.")
            return None

        # non‑interactive shell – list and bail
        print("Multiple server instances. Use --suffix to specify:")
        for suffix, _ in active:
            print(f"  mo-switchboard-cli <command> --suffix {suffix}")
        return None

    # ask_socket is False – auto-pick silently
    for suffix, _ in active:
        if suffix == "default":
            return suffix
    return active[0][0]
