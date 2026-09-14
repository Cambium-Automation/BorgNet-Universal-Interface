# BorgNet for Debian-family desktops

Requires Python 3.11 or newer (Debian 12+, Ubuntu 24.04+, or a compatible derivative), a graphical desktop and a browser. The same architecture-independent package supports amd64 and arm64 when Python dependency wheels are available for that platform.

```sh
sudo apt install ./borgnet_0.1.0-1_all.deb
borgnet
```

You can also select **BorgNet Universal Interface** in the application menu. First launch downloads Python dependencies from PyPI into a private virtual environment under `$XDG_DATA_HOME/borgnet` (default `~/.local/share/borgnet`). It requires Internet access and may take a minute. No pip installs run as root or modify the system Python. A failed setup can be retried by launching again.

The launcher opens a private authenticated link to http://127.0.0.1:7337 in your default browser. Keep that launch link private. Keep its terminal open; Ctrl+C stops the server. To select another port, run `borgnet serve --port 7338` and open the private launch link printed in the terminal. All other BorgNet CLI arguments work, including `borgnet mcp` and `borgnet --data-dir /path serve`. Configuration defaults to `~/.borgnet`; no accounts or private Mac configuration are bundled.

Color, opacity, model toggles, collapsible cards and resizable sections are included. Use the browser's Ctrl+/Ctrl- zoom shortcuts on Linux. Browser blur affects content behind panels within the page. The native macOS desktop wallpaper blur and Apple window shell are not included; Linux compositor blur is not implemented in this package.

Install model runtimes and optional assistant CLIs separately on Linux and put them on PATH. BitNet weights and the macOS binaries are not bundled. Existing remote/API connections work through the same adapters; configure credentials on the destination machine.

To remove the application, use `sudo apt remove borgnet`. Private data and per-user runtimes are retained. You may remove `~/.local/share/borgnet` (or the corresponding XDG directory) separately to reclaim downloaded dependencies. Back up `~/.borgnet` before deleting it.

## Rebuild

From the repository, using Python 3.11+ on macOS or Linux:

```sh
python3 packaging/debian/build.py
```

The builder produces `dist/borgnet_0.1.0-1_all.deb`, using the standard Debian ar/tar package format documented at https://manpages.debian.org/bookworm/dpkg-dev/deb.5.en.html. No native Mac code, virtual environments, credentials or model weights are included. This is a first-run online bootstrap package, not an offline dependency bundle. The source hash selects a fresh runtime when packaged application code changes.

Validation on macOS covers package structure, content checksums, launcher syntax and application tests. Installation and desktop integration on a real Debian system still need verification.
