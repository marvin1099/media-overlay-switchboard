# Server – maintains overlay state, handles client commands over a Unix
# socket, and writes the two output files (overlay_text.txt and
# overlay_image.png) into the configured target folder whenever
# something changes.

import json
import logging
import os
import re
import socket
import threading
from pathlib import Path

from PIL import Image

from .config import Config
from .defaults import (
    IMAGE_EXTENSIONS,
    OUTPUT_TEXT_FILE,
    OUTPUT_TEXT_HTML_FILE,
    OUTPUT_IMAGE_FILE,
)
from .socket_utils import get_socket_path

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def create_transparent_png(width: int, height: int, output_path: Path) -> None:
    """Write a fully-transparent RGBA PNG to *output_path*."""
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    img.save(output_path, "PNG")


# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------

class Server:
    """Manages overlay state (text + image indices, visibility) and
    triggers file writes on every change.

    Safe to call from multiple threads – uses a ``threading.Lock``.
    """

    def __init__(self, config: Config, suffix: str = "default") -> None:
        self.config = config
        self.suffix = suffix

        # --- state --------------------------------------------------------
        self._lock = threading.Lock()
        self.text_entries: list[tuple[str, str | None]] = []
        self.image_files: list[Path] = []
        self.text_index = 0
        self.image_index = 0
        self.text_hidden = True   # start hidden – first Show reveals content
        self.image_hidden = True

        # ensure the target output directory exists
        if config.target_folder:
            Path(config.target_folder).mkdir(parents=True, exist_ok=True)

        self._load_text()
        self._load_images()
        # restore persisted indices and clamp to valid range
        self.text_index = config.text_index if config.text_index is not None else 0
        self.image_index = config.image_index if config.image_index is not None else 0
        self._clamp_indices()
        self._write_outputs()

        # --- window control callback (set by GUI) -------------------------
        self.window_callback: dict[str, callable] | None = None

        # --- networking ---------------------------------------------------
        self._socket: socket.socket | None = None
        self._running = False

    # ---- source loading --------------------------------------------------

    _HEX_COLOR_RE = re.compile(r"^#([0-9A-Fa-f]{6})$")

    def _load_text(self) -> None:
        """Read the text file, split on the configured separator, and
        extract optional hex colours per entry.

        Each entry may start with a hex colour line (e.g. ``#FF0000``) on
        its own line.  The colour applies to that entry only.  If absent,
        the default colour (white) is used::

            First entry (default colour)

            -- TEXTSPLIT --

            #FF0000
            Second entry in red

            -- TEXTSPLIT --

            #00FF00
            Third entry in green
        """
        path_str = self.config.text_file
        if not path_str:
            self.text_entries = []
            return
        path = Path(path_str)
        if not path.exists():
            logger.warning("Text file not found: %s", path)
            self.text_entries = []
            return
        content = path.read_text(encoding="utf-8")
        sep = self.config.text_separator
        if not sep:
            raw = [content.strip()] if content.strip() else []
        else:
            # consume at most one \n before and after the separator
            pattern = re.compile(r'\n?' + re.escape(sep) + r'\n?')
            raw = pattern.split(content)
            # drop leading/trailing empty strings from split artefacts
            while raw and not raw[0]:
                raw.pop(0)
            while raw and not raw[-1]:
                raw.pop()

        self.text_entries = []
        for entry in raw:
            # skip leading blank lines for colour detection
            body = entry.lstrip("\n")
            lines = body.split("\n", 1)
            first = lines[0].strip()
            m = self._HEX_COLOR_RE.match(first)
            if m:
                colour = m.group(0)
                text = (lines[1] if len(lines) > 1 else "").lstrip("\n")
            else:
                colour = None
                text = entry.lstrip("\n")
            self.text_entries.append((text, colour))
        logger.info("Loaded %d text entries from %s", len(self.text_entries), path)

    def _load_images(self) -> None:
        """Scan the images folder and sort recognised image files."""
        path_str = self.config.images_folder
        if not path_str:
            self.image_files = []
            return
        folder = Path(path_str)
        if not folder.is_dir():
            logger.warning("Images folder not found: %s", folder)
            self.image_files = []
            return
        self.image_files = sorted(
            p for p in folder.iterdir() if p.suffix.lower() in IMAGE_EXTENSIONS
        )
        logger.info("Found %d image files in %s", len(self.image_files), folder)

    def _clamp_indices(self) -> None:
        """Clamp text/image indices to valid range (caller must hold lock)."""
        self.text_index = (
            max(0, min(self.text_index, len(self.text_entries) - 1))
            if self.text_entries
            else 0
        )
        self.image_index = (
            max(0, min(self.image_index, len(self.image_files) - 1))
            if self.image_files
            else 0
        )

    def _persist_indices(self) -> None:
        """Save current indices to config and flush to disk."""
        self.config.text_index = self.text_index
        self.config.image_index = self.image_index
        self.config.save(self.suffix)

    def reload(self) -> None:
        """Re-read source files and clamp indices (thread-safe)."""
        with self._lock:
            self._load_text()
            self._load_images()
            self._clamp_indices()
            self._write_outputs()

    # ---- output file writing ---------------------------------------------

    def _write_outputs(self) -> None:
        """Write the current state to the three target files (no lock –
        caller must hold ``_lock`` when appropriate)."""
        target = self.config.target_folder
        if not target:
            return
        target_path = Path(target)
        target_path.mkdir(parents=True, exist_ok=True)

        # text output – plain text
        text_out = target_path / OUTPUT_TEXT_FILE
        html_out = target_path / OUTPUT_TEXT_HTML_FILE
        if self.text_hidden or not self.text_entries:
            text_out.write_text("", encoding="utf-8")
            html_out.write_text("", encoding="utf-8")
        else:
            idx = max(0, min(self.text_index, len(self.text_entries) - 1))
            entry_text, entry_colour = self.text_entries[idx]
            text_out.write_text(entry_text, encoding="utf-8")

            # text output – HTML (for OBS Browser source with colour)
            colour = entry_colour or "#FFFFFF"
            safe_text = (
                entry_text
                .replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
            )
            html_lines = [
                "<!DOCTYPE html>",
                "<html><head><meta charset=\"utf-8\">",
                "<style>",
                "  body {",
                "    margin: 0; padding: 0;",
                "    background: transparent;",
                "    font-family: sans-serif;",
                "    font-size: 24px;",
                f"    color: {colour};",
                "  }",
                "  div {",
                "    white-space: pre-wrap;",
                "  }",
                "</style></head><body>",
                f"<div>{safe_text}</div>",
                "</body></html>",
            ]
            html_out.write_text("\n".join(html_lines), encoding="utf-8")

        # image output
        image_out = target_path / OUTPUT_IMAGE_FILE
        if self.image_hidden or not self.image_files:
            create_transparent_png(
                self.config.transparent_width,
                self.config.transparent_height,
                image_out,
            )
        else:
            idx = max(0, min(self.image_index, len(self.image_files) - 1))
            source = self.image_files[idx]
            # Always write RGBA PNG so the overlay doesn't have to guess
            # the source format.
            img = Image.open(source).convert("RGBA")
            img.save(image_out, "PNG")

    # ---- status ----------------------------------------------------------

    def get_status(self) -> dict:
        """Return a serialisable snapshot of the current state."""
        with self._lock:
            text_entry, text_colour = (
                self.text_entries[self.text_index]
                if self.text_entries and not self.text_hidden
                else ("", None)
            )
            image_name = (
                self.image_files[self.image_index].name
                if self.image_files and not self.image_hidden
                else ""
            )
            return {
                "text_index": self.text_index if self.text_entries else -1,
                "text_total": len(self.text_entries),
                "text_hidden": self.text_hidden,
                "text_entry": text_entry,
                "text_colour": text_colour,
                "image_index": self.image_index if self.image_files else -1,
                "image_total": len(self.image_files),
                "image_hidden": self.image_hidden,
                "image_file": image_name,
                "suffix": self.suffix,
            }

    # ---- command handlers ------------------------------------------------

    # Each cmd_* method holds the lock, modifies state, writes outputs
    # and returns a response dict.

    def cmd_text_next(self) -> dict:
        with self._lock:
            if not self.text_entries:
                return {"status": "error", "message": "No text entries loaded"}
            self.text_index = (self.text_index + 1) % len(self.text_entries)
            self._write_outputs()
        return {"status": "ok"}

    def cmd_text_prev(self) -> dict:
        with self._lock:
            if not self.text_entries:
                return {"status": "error", "message": "No text entries loaded"}
            self.text_index = (self.text_index - 1) % len(self.text_entries)
            self._write_outputs()
        return {"status": "ok"}

    def cmd_text_set(self, index: int) -> dict:
        with self._lock:
            if not self.text_entries:
                return {"status": "error", "message": "No text entries loaded"}
            if index < 0 or index >= len(self.text_entries):
                return {
                    "status": "error",
                    "message": f"Index {index} out of range "
                    f"(0 – {len(self.text_entries) - 1})",
                }
            self.text_index = index
            self._write_outputs()
        return {"status": "ok"}

    def cmd_text_hide(self) -> dict:
        with self._lock:
            self.text_hidden = True
            self._write_outputs()
        return {"status": "ok"}

    def cmd_text_show(self) -> dict:
        with self._lock:
            self.text_hidden = False
            self._write_outputs()
        return {"status": "ok"}

    def cmd_text_toggle(self) -> dict:
        with self._lock:
            self.text_hidden = not self.text_hidden
            self._write_outputs()
        return {"status": "ok"}

    def cmd_image_next(self) -> dict:
        with self._lock:
            if not self.image_files:
                return {"status": "error", "message": "No image files loaded"}
            self.image_index = (self.image_index + 1) % len(self.image_files)
            self._write_outputs()
        return {"status": "ok"}

    def cmd_image_prev(self) -> dict:
        with self._lock:
            if not self.image_files:
                return {"status": "error", "message": "No image files loaded"}
            self.image_index = (self.image_index - 1) % len(self.image_files)
            self._write_outputs()
        return {"status": "ok"}

    def cmd_image_set(self, index: int) -> dict:
        with self._lock:
            if not self.image_files:
                return {"status": "error", "message": "No image files loaded"}
            if index < 0 or index >= len(self.image_files):
                return {
                    "status": "error",
                    "message": f"Index {index} out of range "
                    f"(0 – {len(self.image_files) - 1})",
                }
            self.image_index = index
            self._write_outputs()
        return {"status": "ok"}

    def cmd_image_hide(self) -> dict:
        with self._lock:
            self.image_hidden = True
            self._write_outputs()
        return {"status": "ok"}

    def cmd_image_show(self) -> dict:
        with self._lock:
            self.image_hidden = False
            self._write_outputs()
        return {"status": "ok"}

    def cmd_image_toggle(self) -> dict:
        with self._lock:
            self.image_hidden = not self.image_hidden
            self._write_outputs()
        return {"status": "ok"}

    def cmd_reload(self) -> dict:
        self.reload()
        return {"status": "ok"}

    # ---- socket dispatch ------------------------------------------------

    def _handle_client(self, conn: socket.socket) -> None:
        """Read one JSON command from *conn* and write a JSON response."""
        try:
            raw = conn.recv(65536)
            if not raw:
                return
            try:
                msg = json.loads(raw.decode("utf-8"))
            except json.JSONDecodeError:
                conn.sendall(
                    json.dumps({"status": "error", "message": "Invalid JSON"}).encode("utf-8")
                )
                return

            command = msg.get("command", "")
            response = self._dispatch(command, msg)
            conn.sendall(json.dumps(response).encode("utf-8"))
        except Exception as exc:
            logger.error("Error handling client: %s", exc)
            try:
                conn.sendall(
                    json.dumps({"status": "error", "message": str(exc)}).encode("utf-8")
                )
            except OSError:
                pass
        finally:
            conn.close()

    def _dispatch(self, command: str, msg: dict) -> dict:
        handlers = {
            "text-next": lambda: self.cmd_text_next(),
            "text-prev": lambda: self.cmd_text_prev(),
            "text-set": lambda: self.cmd_text_set(msg.get("index", 0)),
            "text-hide": lambda: self.cmd_text_hide(),
            "text-show": lambda: self.cmd_text_show(),
            "text-toggle": lambda: self.cmd_text_toggle(),
            "image-next": lambda: self.cmd_image_next(),
            "image-prev": lambda: self.cmd_image_prev(),
            "image-set": lambda: self.cmd_image_set(msg.get("index", 0)),
            "image-hide": lambda: self.cmd_image_hide(),
            "image-show": lambda: self.cmd_image_show(),
            "image-toggle": lambda: self.cmd_image_toggle(),
            "reload": lambda: self.cmd_reload(),
            "status": lambda: {**{"status": "ok"}, **self.get_status()},
            "window-show": lambda: self._window_show(),
            "window-hide": lambda: self._window_hide(),
            "window-toggle": lambda: self._window_toggle(),
            "window-quit": lambda: self._window_quit(),
        }
        handler = handlers.get(command)
        if handler is None:
            return {"status": "error", "message": f"Unknown command: {command}"}
        return handler()

    def _window_show(self) -> dict:
        cb = self.window_callback
        if cb and "show" in cb:
            cb["show"]()
            return {"status": "ok", "message": "Window shown"}
        return {"status": "error", "message": "No GUI window attached"}

    def _window_hide(self) -> dict:
        cb = self.window_callback
        if cb and "hide" in cb:
            cb["hide"]()
            return {"status": "ok", "message": "Window hidden"}
        return {"status": "error", "message": "No GUI window attached"}

    def _window_toggle(self) -> dict:
        cb = self.window_callback
        if cb and "toggle" in cb:
            cb["toggle"]()
            return {"status": "ok", "message": "Window toggled"}
        return {"status": "error", "message": "No GUI window attached"}

    def _window_quit(self) -> dict:
        cb = self.window_callback
        if cb and "quit" in cb:
            cb["quit"]()
            return {"status": "ok", "message": "Quitting"}
        return {"status": "error", "message": "No GUI window attached"}

    # ---- lifecycle ------------------------------------------------------

    def start(self) -> None:
        """Bind the Unix socket and enter the accept-loop (blocks)."""
        sock_path = get_socket_path(self.suffix)
        sock_path.parent.mkdir(parents=True, exist_ok=True)

        if sock_path.exists():
            sock_path.unlink()

        self._socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._socket.bind(str(sock_path))
        self._socket.listen(5)
        self._socket.settimeout(1.0)  # allows polling self._running
        self._running = True
        logger.info("Server listening on %s", sock_path)

        while self._running:
            try:
                conn, _ = self._socket.accept()
                threading.Thread(
                    target=self._handle_client, args=(conn,), daemon=True
                ).start()
            except socket.timeout:
                continue
            except OSError:
                break

    def stop(self) -> None:
        """Signal the server loop to exit and clean up the socket file."""
        self._running = False
        if self._socket is not None:
            try:
                self._socket.close()
            except OSError:
                pass
        sock_path = get_socket_path(self.suffix)
        if sock_path.exists():
            try:
                sock_path.unlink()
            except OSError:
                pass

        with self._lock:
            self._persist_indices()
