"""In-app updates from GitHub Releases."""

import hashlib
import os
import re
import shutil
import sys
import threading
import time
import urllib.request
from pathlib import Path

from jobslop import config, net
from jobslop.config import DATA_DIR
from jobslop.settings import load_settings, update_settings

UPDATE_DIR = DATA_DIR / "update"
UPDATE_ASSET = "jobslop.exe" if config.IS_WIN else "jobslop-Mac.zip" if config.IS_MAC else ""
UPDATE_CHECK_EVERY = 12 * 3600
update_state = {"done": 0, "total": 0, "busy": False, "ready": "", "error": "", "updated_from": ""}


def version_tuple(v):
    nums = [int(n) for n in re.findall(r"\d+", str(v or ""))[:3]]
    return tuple(nums + [0] * (3 - len(nums)))


def is_newer(a, b):
    return version_tuple(a) > version_tuple(b)


def release_info(rel):
    """GitHub's 'latest release' answer -> what the app needs (only github.com download links are kept)."""
    assets = {a.get("name"): a for a in rel.get("assets") or [] if isinstance(a, dict)}
    gh = lambda u: u if str(u or "").startswith("https://github.com/") else ""
    exe, sha = assets.get(UPDATE_ASSET) or {}, assets.get(UPDATE_ASSET + ".sha256") or {}
    return {"version": str(rel.get("tag_name") or "").strip().lstrip("vV")[:20], "notes": str(rel.get("body") or "")[:5000],
            "page": gh(rel.get("html_url")), "asset_url": gh(exe.get("browser_download_url")),
            "size": int(exe.get("size") or 0), "sha256_url": gh(sha.get("browser_download_url")),
            "published": str(rel.get("published_at") or "")[:10]}


def check_for_update(force=False):
    """Newest release vs this version. GitHub is asked at most every 12 hours unless you press Check."""
    s = load_settings()
    out = {"enabled": bool(config.UPDATE_REPO), "current": config.APP_VERSION, "off": bool(s.get("updates_off")),
           "updated_from": update_state["updated_from"]}
    if not config.UPDATE_REPO or out["off"]:          # "Don't receive any updates": GitHub is never asked
        return out
    cache = s.get("update_check") or {}
    if force or time.time() - cache.get("t", 0) > UPDATE_CHECK_EVERY or not cache.get("info"):
        rel = net.get_json(f"https://api.github.com/repos/{config.UPDATE_REPO}/releases/latest", timeout=15,
                       headers={"Accept": "application/vnd.github+json", "User-Agent": f"jobslop/{config.APP_VERSION}"})
        cache = {"t": time.time(), "info": release_info(rel)}
        update_settings(lambda st: st.__setitem__("update_check", cache))
    info = cache["info"]
    # a ready-made copy (bought) gets new versions from the download page; a copy run from the source
    # (or built yourself) from GitHub
    how = "built" if config.FROZEN else "source"
    out.update(info, how=how, get_url=(config.DOWNLOAD_PAGE if how == "built" else "") or info["page"],
               available=bool(info["version"]) and is_newer(info["version"], config.APP_VERSION),
               can_install=config.FROZEN and config.IS_WIN and bool(info["asset_url"] and info["sha256_url"]),
               skipped=s.get("update_skip") == info["version"])
    return out


def _download(url, max_bytes, on_chunk=None):
    req = urllib.request.Request(url, headers={"User-Agent": f"jobslop/{config.APP_VERSION}"})
    with urllib.request.urlopen(req, timeout=60) as r:
        while True:
            chunk = r.read(1 << 16)
            if not chunk:
                return
            max_bytes -= len(chunk)
            if max_bytes < 0:
                raise ValueError("The download is bigger than expected - stopped")
            if on_chunk:
                on_chunk(chunk)
            yield chunk


def download_update():
    """Fetch the new jobslop.exe into the data folder and check it against the release's checksum."""
    st = update_state
    st.update(busy=True, done=0, total=0, ready="", error="")
    try:
        (UPDATE_DIR / "jobslop-new.exe").unlink(missing_ok=True)   # never install an older download by mistake
        info = check_for_update()
        if not (info.get("available") and info.get("can_install")):
            raise ValueError("There's no update that can be installed automatically")
        st["total"] = info["size"]
        want = b"".join(_download(info["sha256_url"], 10_000)).decode("ascii", "replace").split()
        want = want[0].lower() if want else ""
        if not re.fullmatch(r"[0-9a-f]{64}", want):
            raise ValueError("The update's checksum file is broken - nothing was changed")
        UPDATE_DIR.mkdir(parents=True, exist_ok=True)
        part, h, final = UPDATE_DIR / "jobslop-new.exe.part", hashlib.sha256(), UPDATE_DIR / "jobslop-new.exe"
        with open(part, "wb") as f:
            for chunk in _download(info["asset_url"], max(info["size"], 1) + 1024,
                                   lambda c: st.__setitem__("done", st["done"] + len(c))):
                f.write(chunk)
                h.update(chunk)
        if h.hexdigest() != want:
            part.unlink(missing_ok=True)
            raise ValueError("The download didn't match its checksum - nothing was changed. Try again later.")
        os.replace(part, final)
        st["ready"] = str(final)
    except Exception as e:
        st["error"] = str(e)[:200] or "The download failed"
    finally:
        st["busy"] = False


def swap_in_update(new_exe, target):
    """Put the new .exe where the running one is. Windows won't let a running program be overwritten or
    deleted, but it can be renamed - so the running copy steps aside as '.old' (the new version deletes it
    when it's next opened). If anything fails, the original is put back and nothing changes."""
    target, new_exe = Path(target), Path(new_exe)
    old = Path(str(target) + ".old")
    try:
        old.unlink(missing_ok=True)                 # left over from an earlier update
    except OSError:
        raise ValueError("An older update is still being tidied up - restart jobslop and try again")
    try:
        os.replace(target, old)
    except OSError:
        raise ValueError("jobslop can't replace itself in this folder (no permission). "
                         "Download the new version from the release page instead.")
    try:
        shutil.move(str(new_exe), str(target))      # a move, or copy + delete when it's on another drive
    except Exception:
        os.replace(old, target)
        raise ValueError("Couldn't put the new version in place - nothing was changed")


def install_update():
    """Swap in the downloaded version and close jobslop. The user opens it again to use the new version
    (it isn't started automatically)."""
    new = Path(update_state["ready"] or "")
    if not (config.FROZEN and config.IS_WIN and new.is_file()):
        raise ValueError("Download the update first")
    target = Path(sys.executable)
    swap_in_update(new, target)
    update_state["ready"] = ""
    threading.Timer(1.5, lambda: os._exit(0)).start()    # time to answer the screen and say so, then close


def after_update_cleanup():
    """On start: remember which version ran last (to say "Updated to ..."), tidy the update leftovers."""
    try:
        prev = load_settings().get("last_version", "")
        update_state["updated_from"] = prev if prev and prev != config.APP_VERSION else ""
        if prev != config.APP_VERSION:
            update_settings(lambda s: s.__setitem__("last_version", config.APP_VERSION))
    except Exception:
        pass
    old = Path(str(sys.executable) + ".old")
    if config.FROZEN and old.exists():
        # just updated: the old version may still be closing (Windows won't delete a program that's running)
        for _ in range(40):
            try:
                old.unlink()
                break
            except OSError:
                time.sleep(0.25)
    for f in ("jobslop-new.exe", "jobslop-new.exe.part"):
        try:
            (UPDATE_DIR / f).unlink(missing_ok=True)
        except OSError:
            pass                                    # tidying up must never stop jobslop from starting
