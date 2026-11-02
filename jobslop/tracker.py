"""Saved jobs and their application status."""

import json
import threading
from datetime import datetime

from jobslop.config import DATA_DIR

SAVED_FILE = DATA_DIR / "saved_jobs.json"


# ---------------------------------------------------------------- saved jobs

lock = threading.Lock()


def load_saved():
    try:
        return json.loads(SAVED_FILE.read_text(encoding="utf-8-sig"))
    except Exception:
        return []


def write_saved(items):
    SAVED_FILE.write_text(json.dumps(items, indent=2, ensure_ascii=False), encoding="utf-8")


def today():
    return datetime.now().strftime("%Y-%m-%d")


APPLIED_STAGES = ("Applied", "Interview", "Offer", "Rejected")


def set_status(item, status, applied_on=None):
    """Change a tracked job's status and remember when each step happened (for the stats)."""
    item["status"] = status
    item.setdefault("dates", {})[status] = today()
    if status in APPLIED_STAGES and not item.get("applied_on"):
        item["applied_on"] = (applied_on or today())[:10]
