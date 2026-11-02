"""The user's profile and CV file."""

import base64
import json
import re
import shutil
from pathlib import Path

from jobslop.config import DATA_DIR

PROFILE_FILE = DATA_DIR / "profile.json"
CV_DIR = DATA_DIR / "cv"
EXT_DIR = DATA_DIR / "chrome-extension"
ACTIVE_MINUTES = 60                    # how long an Easy apply stays "current" for the extension


JOB_FIELDS = ("title", "company", "location", "start", "end", "description")


def load_profile():
    try:
        return json.loads(PROFILE_FILE.read_text(encoding="utf-8-sig"))
    except Exception:
        return {}


def save_profile(data):
    clean = {str(k)[:40]: str(v)[:8000] for k, v in data.items() if isinstance(v, (str, int, float))}
    if isinstance(data.get("jobs"), list):
        clean["jobs"] = [{f: str(j.get(f) or "")[:3000] for f in JOB_FIELDS}
                         for j in data["jobs"] if isinstance(j, dict)][:20]
    PROFILE_FILE.write_text(json.dumps(clean, indent=2, ensure_ascii=False), encoding="utf-8")
    return clean


def cv_file():
    files = [f for f in CV_DIR.glob("*") if f.is_file()] if CV_DIR.exists() else []
    return max(files, key=lambda f: f.stat().st_mtime) if files else None


def save_cv(name, b64):
    data = base64.b64decode(b64)
    if len(data) > 10 * 1024 * 1024:
        raise ValueError("CV must be under 10 MB")
    safe = re.sub(r"[^\w.\- ()]+", "_", Path(name).name)[:120] or "cv.pdf"
    if CV_DIR.exists():
        shutil.rmtree(CV_DIR)
    CV_DIR.mkdir(parents=True)
    (CV_DIR / safe).write_bytes(data)
    return safe
