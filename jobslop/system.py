"""Things that talk to the operating system: opening files, the clipboard, CSV export, certificates."""

import csv
import os
import subprocess
from datetime import datetime
from pathlib import Path

from jobslop import config


def open_path(path):
    """Open a file or folder in Explorer / Finder."""
    if config.IS_WIN:
        os.startfile(str(path))
    elif config.IS_MAC:
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


def copy_to_clipboard(text):
    if config.IS_WIN:
        subprocess.run(["clip"], input=text.encode("utf-16-le"), check=True,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    elif config.IS_MAC:
        subprocess.run(["pbcopy"], input=text.encode("utf-8"), check=True)
    else:
        subprocess.run(["xclip", "-selection", "clipboard"], input=text.encode("utf-8"), check=True)


def _use_bundled_certificates():
    """Python on a Mac often has no certificate store, so every secure connection fails.
    Use certifi's certificates for all connections (harmless on Windows)."""
    try:
        import ssl

        import certifi
        if not config.IS_WIN:
            ssl._create_default_https_context = lambda *a, **k: ssl.create_default_context(cafile=certifi.where())
    except Exception:
        pass


_use_bundled_certificates()


def export_csv(rows, cols, name):
    folder = Path.home() / "Downloads"
    folder = folder if folder.exists() else Path.home()
    path = folder / f"{name}-{datetime.now().strftime('%Y-%m-%d_%H%M')}.csv"
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for r in rows:
            w.writerow([r.get(c, "") for c in cols])
    return str(path)
