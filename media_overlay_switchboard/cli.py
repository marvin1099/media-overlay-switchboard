# CLI entry point – defines the ``mo-switchboard-cli`` command with
# subcommands for server mode, client commands, and config management.

import argparse
import logging
import time
import sys
import threading

from . import __version__
from .client import resolve_target_suffix, send_command
from .config import Config, parse_config_value
from .socket_utils import find_available_suffix, list_active_sockets


# ---------------------------------------------------------------------------
# Shared argument group for client commands
# ---------------------------------------------------------------------------

_CLIENT_OPTS = argparse.ArgumentParser(add_help=False)
_CLIENT_OPTS.add_argument(
    "--suffix",
    default=None,
    help="Socket suffix of the target server instance (default: %(default)s)",
)
_CLIENT_OPTS.add_argument(
    "--no-ask",
    action="store_true",
    help="Disable interactive socket selection prompt",
)


# ---------------------------------------------------------------------------
# Parser construction
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mo-switchboard-cli",
        description="Media Overlay Switchboard – control streaming overlays",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )


    sub = parser.add_subparsers(dest="command", help="Sub-command")
    sub.required = True

    # ---- server ---------------------------------------------------------
    sp = sub.add_parser("server", help="Start the overlay server")
    sp.add_argument(
        "--suffix",
        default="default",
        help="Socket suffix (default: %(default)s). Auto-increments if taken.",
    )
    sp.add_argument(
        "--no-gui",
        action="store_true",
        help="Run in console-only mode (no Qt GUI)",
    )
    sp.add_argument("--text-file", default=None, help="Path to the text entries file")
    sp.add_argument(
        "--images-folder", default=None, help="Path to the overlay images folder"
    )
    sp.add_argument(
        "--target-folder", default=None, help="Path for output files"
    )
    sp.add_argument(
        "--separator", default=None, help="Separator between text entries"
    )
    sp.add_argument(
        "--transparent-width",
        type=int,
        default=None,
        help="Width of transparent placeholder image",
    )
    sp.add_argument(
        "--transparent-height",
        type=int,
        default=None,
        help="Height of transparent placeholder image",
    )

    # ---- list -----------------------------------------------------------
    sub.add_parser("list", help="List active server instances")

    # ---- client commands ------------------------------------------------
    _simple_cmds = [
        ("text-next", "Advance to next text entry"),
        ("text-prev", "Go back to previous text entry"),
        ("text-hide", "Hide text overlay"),
        ("text-show", "Show text overlay"),
        ("text-toggle", "Toggle text overlay visibility"),
        ("image-next", "Advance to next image"),
        ("image-prev", "Go back to previous image"),
        ("image-hide", "Hide image overlay"),
        ("image-show", "Show image overlay"),
        ("image-toggle", "Toggle image overlay visibility"),
        ("status", "Show current overlay status"),
        ("reload", "Reload text file and images folder"),
    ]
    for cmd, help_txt in _simple_cmds:
        p = sub.add_parser(cmd, help=help_txt, parents=[_CLIENT_OPTS])

    # text-set
    p = sub.add_parser("text-set", help="Set text entry by index", parents=[_CLIENT_OPTS])
    p.add_argument("index", type=int, help="Entry index (0-based)")

    # image-set
    p = sub.add_parser("image-set", help="Set image by index", parents=[_CLIENT_OPTS])
    p.add_argument("index", type=int, help="Image index (0-based)")

    # ---- config commands ------------------------------------------------
    p = sub.add_parser("config-set", help="Set a configuration value", parents=[_CLIENT_OPTS])
    p.add_argument("key", help="Configuration key")
    p.add_argument("value", help="New value")

    p = sub.add_parser("config-get", help="Read configuration", parents=[_CLIENT_OPTS])
    p.add_argument("key", nargs="?", default=None, help="Key to read (omit for all)")

    return parser


# ---------------------------------------------------------------------------
# Command runners
# ---------------------------------------------------------------------------

def _run_server(args: argparse.Namespace) -> None:
    config = Config.load(args.suffix)
    config.update_from_cli(args)

    # resolve suffix (auto-increment when already in use)
    suffix = find_available_suffix(args.suffix)

    # import server
    from .server import Server

    server = Server(config, suffix)

    if args.no_gui:
        logging.basicConfig(
            level=logging.INFO,
            format="[%(asctime)s] %(levelname)s %(message)s",
            datefmt="%H:%M:%S",
        )
        logger = logging.getLogger("mos")
        logger.info("Server starting (suffix=%s, no-gui mode)", suffix)
        _run_interactive_menu(server, suffix)
    else:
        _run_server_with_gui(server, suffix)


def _run_server_with_gui(server, suffix: str) -> None:
    """Start the server in a background thread and launch the Qt GUI.

    Falls back to console-only mode with a warning when PySide6 is
    not installed (no ``[gui]`` extra).
    """
    try:
        from .gui import run_gui  # noqa: F401 – import check only
    except ImportError as exc:
        print(
            f"Warning: {exc} – GUI not available, falling back to --no-gui.",
            file=sys.stderr,
        )
        print("Install GUI support: pip install 'media-overlay-switchboard[gui]'")
        # fall back to CLI mode
        logging.basicConfig(
            level=logging.INFO,
            format="[%(asctime)s] %(levelname)s %(message)s",
            datefmt="%H:%M:%S",
        )
        logger = logging.getLogger("mos")
        logger.info("Server starting (suffix=%s, CLI fallback)", suffix)
        _run_interactive_menu(server, suffix)
        return

    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    # Run server socket listener in a daemon thread so it exits when the
    # GUI (main thread) closes.
    t = threading.Thread(target=server.start, daemon=True)
    t.start()

    from .gui import run_gui

    run_gui(server, suffix)


# ---------------------------------------------------------------------------
# Interactive CLI menu (used when --no-gui is passed)
# ---------------------------------------------------------------------------

def _run_interactive_menu(server: object, suffix: str) -> None:
    """Start the server socket in a background thread and show an
    interactive menu on the terminal for controlling the overlay."""

    t = threading.Thread(target=server.start, daemon=True)
    t.start()

    print()
    print("Media Overlay Switchboard  –  interactive mode")
    print(f"Socket suffix: {suffix}")
    print("─" * 50)

    notice="\nInput ? for help"
    while True:
        try:
            _print_interactive_status(server)
            time.sleep(0.01)
            cmd = input(notice + "\n> ").strip().lower()
            notice=""
            if not cmd:
                continue

            parts = cmd.split(maxsplit=1)
            action = parts[0]
            arg = parts[1] if len(parts) > 1 else None

            # text commands
            if action in ("tn", "text-next"):
                print(server.cmd_text_next().get("message", "ok"))
            elif action in ("tp", "text-prev"):
                print(server.cmd_text_prev().get("message", "ok"))
            elif action in ("ts", "text-set"):
                if arg is None:
                    print("Usage: ts <index>")
                    continue
                try:
                    idx = int(arg)
                except ValueError:
                    print("Index must be a number")
                    continue
                print(server.cmd_text_set(idx).get("message", "ok"))
            elif action in ("th", "text-hide"):
                print(server.cmd_text_hide().get("message", "ok"))
            elif action in ("tss", "text-show"):
                print(server.cmd_text_show().get("message", "ok"))
            elif action in ("tt", "text-toggle"):
                print(server.cmd_text_toggle().get("message", "ok"))

            # image commands
            elif action in ("in", "image-next"):
                print(server.cmd_image_next().get("message", "ok"))
            elif action in ("ip", "image-prev"):
                print(server.cmd_image_prev().get("message", "ok"))
            elif action in ("is", "image-set"):
                if arg is None:
                    print("Usage: is <index>")
                    continue
                try:
                    idx = int(arg)
                except ValueError:
                    print("Index must be a number")
                    continue
                print(server.cmd_image_set(idx).get("message", "ok"))
            elif action in ("ih", "image-hide"):
                print(server.cmd_image_hide().get("message", "ok"))
            elif action in ("iss", "image-show"):
                print(server.cmd_image_show().get("message", "ok"))
            elif action in ("it", "image-toggle"):
                print(server.cmd_image_toggle().get("message", "ok"))

            # source selection
            elif action in ("sf", "set-text-file"):
                if arg is None:
                    print("Usage: sf <path>")
                    continue
                server.config.text_file = arg
                server.config.save(server.suffix)
                server.reload()
                print("ok")
            elif action in ("si", "set-images-folder"):
                if arg is None:
                    print("Usage: si <path>")
                    continue
                server.config.images_folder = arg
                server.config.save(server.suffix)
                server.reload()
                print("ok")
            elif action in ("st", "set-target-folder"):
                if arg is None:
                    print("Usage: st <path>")
                    continue
                server.config.target_folder = arg
                server.config.save(server.suffix)
                server.reload()
                print("ok")

            # placeholder size
            elif action in ("sz", "set-size"):
                if arg is None:
                    print("Usage: sz <WIDTH>x<HEIGHT>  (e.g. 1920x1080)")
                    continue
                try:
                    w, h = arg.split("x", 1)
                    server.config.transparent_width = int(w)
                    server.config.transparent_height = int(h)
                    server.config.save(server.suffix)
                    server.reload()
                    print(f"Placeholder size set to {w}x{h}")
                except (ValueError, TypeError):
                    print("Invalid format. Use e.g. 1920x1080")

            # meta
            elif action in ("q", "quit", "exit"):
                print("Shutting down…")
                break
            elif action in ("?", "h", "help"):
                _print_interactive_help()
            elif action in ("stt", "status"):
                pass  # will loop and show status
            else:
                print(f"Unknown command: {action}  (type ? for help)")

        except (EOFError, KeyboardInterrupt):
            print()
            break

    server.stop()


def _print_interactive_help() -> None:
    print()
    print("  tn / tp              text next / prev")
    print("  ts <n>               text set to index n")
    print("  th / tss / tt        text hide / show / toggle")
    print("  in / ip              image next / prev")
    print("  is <n>               image set to index n")
    print("  ih / iss / it        image hide / show / toggle")
    print("  sf <path>            set text file")
    print("  si <path>            set images folder")
    print("  st <path>            set target folder")
    print("  sz <WxH>             set placeholder size (e.g. 1920x1080)")
    print("  q / exit             quit")
    print("  ? / help             this help")
    print()


def _print_interactive_status(server: object) -> None:
    st = server.get_status()
    print()
    print(f"  Text:   entry {st['text_index'] + 1} / {st['text_total']}"
          f"  [{ 'SHOWN' if not st['text_hidden'] else 'HIDDEN' }]"
          f"  file: {server.config.text_file or '(none)'}")
    print(f"  Image:  file {st['image_index'] + 1} / {st['image_total']}"
          f"  [{ 'SHOWN' if not st['image_hidden'] else 'HIDDEN' }]"
          f"  folder: {server.config.images_folder or '(none)'}")
    print(f"  Target: {server.config.target_folder or '(none)'}")
    print(f"  Size:   {server.config.transparent_width}x{server.config.transparent_height}")


def _run_list(_args: object = None) -> None:
    active = list_active_sockets()
    if not active:
        print("No active server instances found.")
        return
    print(f"Active server instances ({len(active)}):")
    for suffix, path in active:
        print(f"  {suffix:20s}  {path}")


def _run_client_command(args: argparse.Namespace) -> None:
    config = Config.load()
    suffix = resolve_target_suffix(config, args.suffix, no_ask=args.no_ask)
    if suffix is None:
        sys.exit(1)

    command = args.command  # e.g. "text-next", "text-set"

    kwargs: dict = {}
    if command in ("text-set", "image-set"):
        kwargs["index"] = args.index

    result = send_command(suffix, command, **kwargs)

    # Pretty-print the response
    if result.get("status") == "ok" and command == "status":
        _print_status(result)
    elif result.get("status") != "ok":
        print(f"error: {result.get('message', 'unknown error')}")
        sys.exit(1)


def _print_status(data: dict) -> None:
    """Display the status dict in a human-friendly way."""
    print(f"Server instance:  {data.get('suffix', '?')}")
    print()
    print("Text:")
    print(f"  Entry:    {data.get('text_index', -1) + 1} / {data.get('text_total', 0)}")
    print(f"  Hidden:   {data.get('text_hidden', False)}")
    if data.get("text_entry"):
        print(f"  Content:  {data['text_entry'][:120]}")
    print()
    print("Image:")
    print(f"  Index:    {data.get('image_index', -1) + 1} / {data.get('image_total', 0)}")
    print(f"  Hidden:   {data.get('image_hidden', False)}")
    if data.get("image_file"):
        print(f"  File:     {data['image_file']}")


def _run_config_set(args: argparse.Namespace) -> None:
    suffix = args.suffix or "default"
    config = Config.load(suffix)
    parsed = parse_config_value(args.value)
    key = args.key
    if "." in key:
        parent, child = key.split(".", 1)
        if not hasattr(config, parent):
            print(f"error: Unknown config key '{parent}'")
            sys.exit(1)
        obj = getattr(config, parent)
        if not isinstance(obj, dict):
            print(f"error: '{parent}' is not a dict")
            sys.exit(1)
        obj[child] = parsed
    else:
        if not hasattr(config, key):
            print(f"error: Unknown config key '{key}'")
            sys.exit(1)
        setattr(config, key, parsed)
    config.save(suffix)
    print(f"config.{key} = {repr(parsed)}")


def _run_config_get(args: argparse.Namespace) -> None:
    suffix = args.suffix or "default"
    config = Config.load(suffix)
    if args.key:
        if "." in args.key:
            parent, child = args.key.split(".", 1)
            if not hasattr(config, parent):
                print(f"error: Unknown config key '{parent}'")
                sys.exit(1)
            obj = getattr(config, parent)
            if isinstance(obj, dict):
                val = obj.get(child, "<not set>")
            else:
                val = "<not a dict>"
            print(f"{args.key} = {repr(val)}")
        else:
            if not hasattr(config, args.key):
                print(f"error: Unknown config key '{args.key}'")
                sys.exit(1)
            val = getattr(config, args.key)
            print(f"{args.key} = {repr(val)}")
    else:
        print("Configuration:")
        for key, value in config.__dict__.items():
            print(f"  {key:25s} = {repr(value)}")


# ---------------------------------------------------------------------------
# Main dispatcher
# ---------------------------------------------------------------------------

_COMMAND_MAP = {
    "server": _run_server,
    "list": _run_list,
    "config-set": _run_config_set,
    "config-get": _run_config_get,
}


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    handler = _COMMAND_MAP.get(args.command)
    if handler:
        handler(args)
    else:
        # any other command is treated as a client command
        _run_client_command(args)


if __name__ == "__main__":
    main()
