# GUI launcher – thin wrapper that runs mo-switchboard-cli in server mode.
#
# Invoked by the ``mo-switchboard-gui`` console-script entry point.
# It simply inserts ``server`` as the first subcommand argument and
# delegates to the CLI's ``main()``, so all server options
# (--suffix, --text-file, …) are forwarded transparently.
#
# Example
# -------
# $ mo-switchboard-gui --suffix myinstance --text-file ./entries.txt
# # → internally runs: mo-switchboard-cli server --suffix myinstance --text-file ./entries.txt

import sys

from media_overlay_switchboard.cli import main as _cli_main


def main() -> None:
    # Prevent double-insertion when the user explicitly types "server" after
    # the program name (e.g. ``mo-switchboard-gui server --suffix foo``).
    if len(sys.argv) <= 1 or sys.argv[1] != "server":
        sys.argv.insert(1, "server")

    _cli_main()
