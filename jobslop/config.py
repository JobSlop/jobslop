"""Fixed settings: version, ports, the data folder and the folder the app's own files are bundled in."""

import os
import sys
from pathlib import Path

IS_WIN, IS_MAC = sys.platform.startswith("win"), sys.platform == "darwin"
FROZEN = bool(getattr(sys, "frozen", False))          # running as the built jobslop.exe / app


def _data_dir() -> Path:
    if IS_WIN:
        return Path(os.environ.get("APPDATA") or Path.home()) / "JobFinder"
    if IS_MAC:
        return Path.home() / "Library" / "Application Support" / "JobFinder"
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / "JobFinder"


# Saved jobs, profile and settings. The folder keeps its old "JobFinder" name so nothing is lost.
DATA_DIR = _data_dir()
DATA_DIR.mkdir(parents=True, exist_ok=True)

# ui/, static/, chrome-extension/, plugins/ ... : the project folder, or inside the .exe when built
RES_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))

APP_PORT = 47321                       # fixed so the Chrome extension can find the app
APP_VERSION = "3.1.0"                 # raise this for every release (release.py publishes it on GitHub)
# The GitHub repository jobslop's releases are published in ("owner/name"). Empty = update checks are off.
UPDATE_REPO = os.environ.get("JOBSLOP_UPDATE_REPO", "JobSlop/jobslop")
FEEDBACK_EMAIL = "jobslop@proton.me"
# Where people who bought jobslop download new versions (the Gumroad product page). Releases on GitHub
# carry the source only; when this is empty, "Get it" opens the GitHub release instead.
DOWNLOAD_PAGE = os.environ.get("JOBSLOP_DOWNLOAD_PAGE", "")
