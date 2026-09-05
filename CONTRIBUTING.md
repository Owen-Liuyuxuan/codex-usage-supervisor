# Contributing

Thank you for improving Codex Usage Supervisor. The project targets Ubuntu
22.04 with GNOME Shell 42 and Python 3.10.

## Development setup

The core parser has no third-party Python dependencies. Desktop integration
uses the distribution packages for PyGObject, GTK4, and Libadwaita:

```bash
sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 gnome-shell
PYTHONPATH=src python3 -m unittest discover -s tests -v
node --check extension/extension.js
shellcheck packaging/build_deb.sh
```

Build the Debian package with `./packaging/build_deb.sh`. For extension testing,
install the build, restart GNOME Shell, and watch the user journal:

```bash
journalctl --user -f -o cat | grep -i codex
```

## Change guidelines

- Keep prompt and response bodies out of the D-Bus contract.
- Do not add network calls to the Codex provider.
- Never store service credentials in the repository or settings JSON.
- Keep filesystem parsing outside the GNOME Shell process.
- Add tests for changes to aggregation or serialization behavior.
- Support the shell versions declared in `extension/metadata.json`.

Submit focused changes with a clear description, verification evidence, and
screenshots for visible UI changes.

