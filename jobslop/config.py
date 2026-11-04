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
APP_VERSION = "3.1.2"                 # raise this for every release (release.py publishes it on GitHub)
# The GitHub repository jobslop's releases are published in ("owner/name"). Empty = update checks are off.
UPDATE_REPO = os.environ.get("JOBSLOP_UPDATE_REPO", "JobSlop/jobslop")
FEEDBACK_EMAIL = "jobslop@proton.me"
# Where people who bought jobslop download new versions (the Gumroad product page). Releases on GitHub
# carry the source only; when this is empty, "Get it" opens the GitHub release instead.
DOWNLOAD_PAGE = os.environ.get("JOBSLOP_DOWNLOAD_PAGE", "")
# Ready-made builds: their .exe for each release is in this repository's release of the same version,
# so the app can update itself. Gumroad builds check the buyer's licence first; personal builds don't.
BUILDS_REPO = os.environ.get("JOBSLOP_BUILDS_REPO", "JobSlop/jobslop-builds")


def _from_build(name: str, default: str = "") -> str:
    """A value build.bat put in jobslop/build_info.py (that file only exists while a Gumroad or personal
    build is being made, and is never committed)."""
    try:
        from jobslop import build_info
        return str(getattr(build_info, name, "") or default)
    except ImportError:
        return default


# The Gumroad product whose licence keys unlock in-app updates. Kept out of the source: build.bat reads it
# from local/gumroad_product_id.txt (ignored by git) and puts it only into the Gumroad build.
GUMROAD_PRODUCT_ID = os.environ.get("JOBSLOP_GUMROAD_PRODUCT_ID") or _from_build("GUMROAD_PRODUCT_ID")


def _build_kind() -> str:
    """'gumroad' (sold), 'personal' (test builds and ones you give away), 'self' (built by someone from the
    source) or 'source' (run from the source). build.bat writes jobslop/build_info.py for the first two."""
    try:
        from jobslop import build_info
        if build_info.KIND in ("gumroad", "personal"):
            return build_info.KIND
    except ImportError:
        pass
    return "self" if FROZEN else "source"


BUILD_KIND = _build_kind()
