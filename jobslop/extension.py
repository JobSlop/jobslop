"""The Chrome extension: pairing code, what it is sent, installing it, opening Chrome."""

import json
import os
import re
import secrets
import shutil
import subprocess
import time
import webbrowser
from pathlib import Path

from jobslop import config
from jobslop.config import APP_PORT, RES_DIR
from jobslop.profile.store import ACTIVE_MINUTES, EXT_DIR, cv_file, load_profile
from jobslop.runtime import state
from jobslop.settings import load_settings, update_settings


def pairing_code():
    s = load_settings()
    if s.get("ext_code"):
        return s["ext_code"]

    def change(s):
        if not s.get("ext_code"):
            alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
            code = "".join(secrets.choice(alphabet) for _ in range(8))
            s["ext_code"] = code[:4] + "-" + code[4:]
    return update_settings(change)["ext_code"]


def active_job():
    a = state["active"]
    if a and time.time() - a["t"] < ACTIVE_MINUTES * 60:
        return a["job"]
    return None


def render_letter(template, profile, job):
    full = " ".join(x for x in (profile.get("first_name"), profile.get("last_name")) if x)
    repl = {"company": (job or {}).get("company") or "your company",
            "title": (job or {}).get("title") or "this role",
            "first_name": profile.get("first_name", ""), "last_name": profile.get("last_name", ""),
            "full_name": full}
    return re.sub(r"\{(\w+)\}", lambda m: repl.get(m[1], m[0]), template or "")


def extension_payload():
    p = load_profile()
    jobs = p.get("jobs") or []
    if jobs:   # most recent job doubles as "current job" for forms that ask once
        p["current_title"] = p.get("current_title") or jobs[0].get("title", "")
        p["current_company"] = p.get("current_company") or jobs[0].get("company", "")
    job = active_job()
    cv = cv_file()
    return {"profile": p,
            "full_name": " ".join(x for x in (p.get("first_name"), p.get("last_name")) if x),
            "cover_letter": render_letter(p.get("cover_letter_template", ""), p, job),
            "active": {"title": job["title"], "company": job["company"], "url": job["url"]} if job else None,
            "cv_name": cv.name if cv else ""}


def install_extension():
    """Copy the bundled Chrome extension to a fixed folder the user can load in Chrome."""
    src = RES_DIR / "chrome-extension"
    try:
        if src.exists():
            shutil.copytree(src, EXT_DIR, dirs_exist_ok=True)
        # the extension reads this to connect by itself (this folder is only in your own user profile)
        (EXT_DIR / "pairing.json").write_text(json.dumps({"code": pairing_code(), "port": APP_PORT}), encoding="utf-8")
    except Exception:
        pass
    return str(EXT_DIR)


def open_in_chrome(url):
    if config.IS_WIN:
        candidates = [Path(os.environ.get(v, "")) / "Google" / "Chrome" / "Application" / "chrome.exe"
                      for v in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA")]
    elif config.IS_MAC:
        candidates = [Path(p) / "Google Chrome.app" / "Contents" / "MacOS" / "Google Chrome"
                      for p in ("/Applications", str(Path.home() / "Applications"))]
    else:
        candidates = [Path(p) for p in ("/usr/bin/google-chrome", "/usr/bin/google-chrome-stable", "/usr/bin/chromium")]
    for c in candidates:
        if c.is_file():
            subprocess.Popen([str(c), url])
            return True
    webbrowser.open(url)
    return False
