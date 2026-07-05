# media-overlay-switchboard

A media output switcher for streaming overlays (OBS, etc.).

Reads text entries from a file and images from a folder, then writes
`overlay_text.txt` and `overlay_image.png` into a target directory.
Your overlay software watches those files.

Text and image navigation is **independent** (Next Text, Next Image, …).
Each can be **hidden** (empty text file / transparent placeholder PNG).

AI was used a lot, human code checking and testing was performed.
This is mosly a tool I wanted to have, but I'm sharing it becalse why not.

## Install

```bash
# clone & install from source
git clone https://codeberg.org/marvin1099/media-overlay-switchboard.git
cd media-overlay-switchboard

# with uv (recommended)
uv tool install --with 'media-overlay-switchboard[gui]' .
# or without gui
uv tool install media-overlay-switchboard

# with pipx
pipx install media-overlay-switchboard[gui]

# with pip – use --user to avoid breaking system packages
pip install --user 'media-overlay-switchboard[gui]'
```

After source edits, re-run the `uv tool install` command to update the
installed copy.

> **Note:** If you skip the `[gui]` extra, the CLI works fine — only the
> optional GUI window is unavailable.  `mo-switchboard-gui` will print a
> warning and fall back to console-only mode.

Two commands are installed:

| Command | What it does |
|---|---|
| `mo-switchboard-cli` | Client + server (all subcommands) |
| `mo-switchboard-gui` | Shortcut for `mo-switchboard-cli server` (starts server with GUI) |

### AppImage

Pre-built AppImages are available on the
[releases page](https://codeberg.org/marvin1099/media-overlay-switchboard/releases).

To build it yourself:

```bash
# ensure build deps are available
pip install pyinstaller

# build the AppImage
./build_appimage.sh
```

The resulting `.AppImage` is placed in `dist/` and bundles Python, PySide6,
Pillow, icon, desktop file, and both entry points into a single portable
executable. Requires `appimagetool` (downloaded automatically) and a working
Python venv.

## Quick start

### 1. Prepare sources

Create a text file — entries are separated by `-- TEXTSPLIT --`:

```
Welcome to the stream!

still first paragraph if you want blank lines

-- TEXTSPLIT --
Now playing: Game Title
-- TEXTSPLIT --
Thanks for watching!
```

Place images in a folder, they will displayed like when sorted by name:

```
~/stream/images/
├── 01-intro.png
├── 02-gameplay.png
└── 03-ending.png
```

### 2. Start the server

```bash
mo-switchboard-cli server
```

Or set the paths right on startup:

```bash
mo-switchboard-cli server \
  --text-file ~/stream/text.txt \
  --images-folder ~/stream/images \
  --target-folder ~/stream/overlay
```

The server listens on a Unix socket at
`$XDG_RUNTIME_DIR/media-overlay-switchboard-default.sock`
and writes `overlay_text.txt` + `overlay_image.png` into the target folder.

Use `--no-gui` for console-only mode (no Qt window):

```bash
mo-switchboard-cli server --no-gui <other-args>
```

Or with a custom socket suffix (multiple instances):

```bash
mo-switchboard-cli server --suffix myshow <other-args>
```

### 3. Send commands

In another terminal (or from hotkeys):

```bash
mo-switchboard-cli text-next --suffix default
mo-switchboard-cli text-prev --suffix default
mo-switchboard-cli text-show --suffix default
mo-switchboard-cli text-hide --suffix default
mo-switchboard-cli text-toggle --suffix default

mo-switchboard-cli image-next --suffix default
mo-switchboard-cli image-prev --suffix default
mo-switchboard-cli image-show --suffix default
mo-switchboard-cli image-hide --suffix default
mo-switchboard-cli image-toggle --suffix default

mo-switchboard-cli text-set 0 --suffix default    # jump to entry by index
mo-switchboard-cli image-set 2 --suffix default   # jump to image by index

mo-switchboard-cli status --suffix default        # show current state
mo-switchboard-cli reload --suffix default         # re-read sources
```

Successful commands produce no output (exit code 0). Errors go to stderr
and exit with code 1.

### 4. Point OBS at the output files

Add a **Text (GDI+)** / **Text** source pointing to the `overlay_text.txt`
file, and an **Image** source pointing to `overlay_image.png`.

Because the files are overwritten in place, your overlay software picks up
every change automatically.

## GUI

```bash
mo-switchboard-gui --suffix default
```

This starts the server with a PySide6 status window (requires `[gui]` extra).
The window shows current text/image state in scrollable group boxes with
Prev / Next / Toggle buttons. When closing the window, a dialog asks whether
to hide to tray or quit — this can be suppressed with a "Don't show again"
checkbox.

The tray icon supports **Show Window** (double-click or context menu) and
**Quit**.

When PySide6 is not installed, `mo-switchboard-gui` prints a warning and
starts the server in console-only interactive mode — you still get a
working overlay.

### Desktop entry & icon

For the app icon to show in your system tray and taskbar, install the
provided `.desktop` file and icon:

```bash
# Copy the icon to the system icon theme
mkdir -p ~/.local/share/icons/hicolor/scalable/apps
cp media_overlay_switchboard/resources/Lavers.svg \
   ~/.local/share/icons/hicolor/scalable/apps/media-overlay-switchboard.svg

# Install the .desktop file
cp media-overlay-switchboard.desktop \
   ~/.local/share/applications/

# Update the icon cache
gtk-update-icon-cache ~/.local/share/icons/hicolor 2>/dev/null || true
```

> **Note:** Some desktop environments (GNOME) don't show tray icons at all
> without an extension like [AppIndicator](https://extensions.gnome.org/extension/615/appindicator-support/).
> KDE Plasma works out of the box.

## Interactive menu mode

When started with `--no-gui` (or when GUI dependencies are missing),
the server runs in the background and a terminal menu is displayed:

```
MOS [default] — commands
  tn/tp/ts th/tss/tt   text next/prev/set, hide/show/toggle
  in/ip/is ih/iss/it   image next/prev/set, hide/show/toggle
  sf/si/st             select text file / images folder / target folder
  sz <WxH>             set placeholder image size (e.g. sz 1920x1080)
  q                    quit
  ?                    help
```

The current text/image index and placeholder size are shown in the status
line.  Ctrl+C exits cleanly.

## Multi-instance

Each server instance gets its own socket suffix. If a suffix is already
taken the server auto-increments (e.g. `default` → `default1` → `default2`).

```bash
mo-switchboard-cli server --suffix stream-a ...
mo-switchboard-cli server --suffix stream-b ...

mo-switchboard-cli text-next --suffix stream-a   # controls stream-a only
```

When multiple instances are running and no `--suffix` is given, the CLI
behaviour depends on the `ask_socket` config setting:

| Value | Behaviour |
|---|---|---|
| `true` | Prompt to pick a socket interactively |
| `false` | Auto-picks a socket (usually `default` or first found) |
| `null` (not set) | Print a warning to stderr with a hint to set `ask_socket` |

The setting is per socket suffix. Set it for a specific suffix:

```bash
mo-switchboard-cli config-set ask_socket.default true
mo-switchboard-cli config-set ask_socket.stream1 false
```

If no entry exists for the current suffix, the `default` entry is used as
fallback (if set). Otherwise the global default (`null`) applies.

```bash
mo-switchboard-cli config-set ask_socket true
```

## Placeholder size

When an image is hidden, a transparent placeholder PNG is written instead.
The size defaults to 1920×1080 and can be changed:

```bash
mo-switchboard-cli server --transparent-width 1280 --transparent-height 720
mo-switchboard-cli config-set transparent_width 1280
mo-switchboard-cli config-set transparent_height 720
```

In the GUI, the size is adjustable via spinboxes inside the Image Overlay box.
In interactive menu mode, use the `sz` command.

## Index persistence

The current text and image indices are saved to the config file when the
server stops, and restored on the next start. This means your overlay
position survives restarts.

## Configuration

Persistent config is stored at
`$XDG_CONFIG_HOME/media-overlay-switchboard/config.json`.

```bash
mo-switchboard-cli config-get                  # show all
mo-switchboard-cli config-get text_file         # show one key
mo-switchboard-cli config-set ask_socket false  # set a value
```

All config keys:

| Key | Type | Default | Description |
|---|---|---|---|
| `text_file` | string | `""` | Path to text entries file |
| `images_folder` | string | `""` | Path to images folder |
| `target_folder` | string | `""` | Path for output files |
| `text_separator` | string | `-- TEXTSPLIT --` | Separator between entries |
| `ask_socket` | dict | `{}` | Per-suffix socket prompt (e.g. `{"default": true}`) |
| `transparent_width` | int | `1920` | Placeholder image width |
| `transparent_height` | int | `1080` | Placeholder image height |
| `text_index` | int | `0` | Current text entry (persisted) |
| `image_index` | int | `0` | Current image index (persisted) |
| `hide_to_tray_no_warn` | bool | `false` | Skip close-to-tray warning |

The server also accepts `--text-file`, `--images-folder`, `--target-folder`,
`--separator`, `--transparent-width`, `--transparent-height` on the command
line — these override the config for that session.
