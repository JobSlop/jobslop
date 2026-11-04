"""Updates. New versions are announced by the release on GitHub (the source).

Ready-made builds can also update themselves: the .exe for each version is in the builds repository's
release of the same version (config.BUILDS_REPO). A Gumroad build first checks the buyer's licence key
with Gumroad; a personal build (tests, friends and family) doesn't. Copies built from the source are
pointed to GitHub instead. After installing, jobslop starts again by itself."""

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from jobslop import config, net
from jobslop.config import DATA_DIR
from jobslop.settings import load_settings, update_settings

UPDATE_DIR = DATA_DIR / "update"
UPDATE_ASSET = "jobslop.exe" if config.IS_WIN else "jobslop-Mac.zip" if config.IS_MAC else ""
PERSONAL_ASSET = "jobslop-personal.exe"
GUMROAD_VERIFY = "https://api.gumroad.com/v2/licenses/verify"
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


def asset_name():
    """Which file this build updates itself with (a personal build stays personal)."""
    return PERSONAL_ASSET if config.BUILD_KIND == "personal" else UPDATE_ASSET


def builds_for(version):
    """The ready-made .exe of a version, from the builds repository: {"asset_url", "sha256_url", "size"}."""
    if not config.BUILDS_REPO or not version:
        return {}
    rel = net.get_json(f"https://api.github.com/repos/{config.BUILDS_REPO}/releases/tags/v{version}", timeout=15,
                       headers={"Accept": "application/vnd.github+json", "User-Agent": f"jobslop/{config.APP_VERSION}"})
    assets = {a.get("name"): a for a in rel.get("assets") or [] if isinstance(a, dict)}
    gh = lambda u: u if str(u or "").startswith("https://github.com/") else ""
    exe, sha = assets.get(asset_name()) or {}, assets.get(asset_name() + ".sha256") or {}
    return {"asset_url": gh(exe.get("browser_download_url")), "sha256_url": gh(sha.get("browser_download_url")),
            "size": int(exe.get("size") or 0)}


# ---- the Gumroad licence (Gumroad builds only)
def verify_licence(key):
    """Ask Gumroad whether a licence key is a real, unrefunded purchase. Returns (ok, message)."""
    key = (key or "").strip()
    if not key:
        return False, "Enter your licence key (it's in your Gumroad receipt)"
    if not config.GUMROAD_PRODUCT_ID:
        return False, "This build doesn't know its Gumroad product yet - updates can't be checked"
    data = urllib.parse.urlencode({"product_id": config.GUMROAD_PRODUCT_ID, "license_key": key,
                                   "increment_uses_count": "false"}).encode()
    req = urllib.request.Request(GUMROAD_VERIFY, data=data, headers={"User-Agent": f"jobslop/{config.APP_VERSION}"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            ans = json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return False, "Gumroad doesn't know that licence key"
        return False, f"Couldn't reach Gumroad ({e.code})"
    except Exception as e:
        return False, f"Couldn't reach Gumroad ({str(e)[:60]})"
    p = ans.get("purchase") or {}
    if not ans.get("success"):
        return False, "Gumroad doesn't know that licence key"
    if p.get("refunded") or p.get("chargebacked") or p.get("disputed"):
        return False, "That purchase was refunded, so in-app updates are off"
    return True, "Licence checked ✓"


def licence_state(s=None):
    """'not_needed' (personal builds), 'ok', 'needed' (no key yet) or 'invalid'."""
    if config.BUILD_KIND != "gumroad":
        return "not_needed"
    lic = (s if s is not None else load_settings()).get("licence") or {}
    return "needed" if not lic.get("key") else "ok" if lic.get("ok") else "invalid"


def set_licence(key):
    ok, msg = verify_licence(key)
    update_settings(lambda s: s.__setitem__("licence", {"key": (key or "").strip()[:100], "ok": ok, "checked": time.time(),
                                                         "message": msg}))
    return ok, msg


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
    available = bool(info["version"]) and is_newer(info["version"], config.APP_VERSION)
    kind, licence = config.BUILD_KIND, licence_state(s)
    ready_made = kind in ("gumroad", "personal") and config.FROZEN and config.IS_WIN
    builds = cache.get("builds") or {}
    if ready_made and available and builds.get("version") != info["version"]:
        try:
            builds = {"version": info["version"], **builds_for(info["version"])}
        except Exception:
            builds = {"version": info["version"]}       # not built yet, or offline: try again next check
        if builds.get("asset_url"):
            cache["builds"] = builds
            update_settings(lambda st: st.__setitem__("update_check", cache))
    if ready_made and builds.get("version") == info["version"]:
        info = {**info, **{k: builds.get(k) or info.get(k) for k in ("asset_url", "sha256_url", "size")}}
    # bought copies get it from the download page, self-built and source copies from GitHub
    out.update(info, how=kind, licence=licence, licence_message=(s.get("licence") or {}).get("message", ""),
               get_url=(config.DOWNLOAD_PAGE if kind == "gumroad" else "") or info["page"], available=available,
               can_install=ready_made and licence in ("ok", "not_needed") and bool(info["asset_url"] and info["sha256_url"]),
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
        if config.BUILD_KIND == "gumroad":                     # checked again now: a refunded licence stops here
            ok, msg = set_licence((load_settings().get("licence") or {}).get("key", ""))
            if not ok:
                raise ValueError(msg)
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
    once this one has closed). If anything fails, the original is put back and nothing changes."""
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


def launch_fresh(exe):
    """Start a separate copy of jobslop. A self-unpacking app passes hidden settings to programs it starts;
    a new copy of itself must ignore them, or it can't find its own files and never opens."""
    env = {k: v for k, v in os.environ.items() if not k.startswith(("_PYI_", "_MEI"))}
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    return subprocess.Popen([str(exe)], env=env, cwd=str(Path(exe).parent), creationflags=flags, close_fds=True)


def install_update():
    """Swap in the downloaded version, start it, and close this one."""
    new = Path(update_state["ready"] or "")
    if not (config.FROZEN and config.IS_WIN and new.is_file()):
        raise ValueError("Download the update first")
    target = Path(sys.executable)
    swap_in_update(new, target)
    update_state["ready"] = ""
    launch_fresh(target)
    threading.Timer(0.8, lambda: os._exit(0)).start()    # time to answer the screen, then close


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
