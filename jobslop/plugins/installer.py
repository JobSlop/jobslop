"""Installing, updating and removing plugins from a GitHub link.

Installing has two steps so nothing runs before the user has seen what they're getting:
  1. prepare(link)   download the repository's latest release (or its main branch), unpack it into a
                     staging folder and read its plugin.json -> what it is and what it adds
  2. confirm(token)  move it into the plugins folder, remember where it came from, switch it on
"""

import io
import json
import re
import secrets
import shutil
import threading
import time
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from jobslop import config, net
from jobslop.config import DATA_DIR
from jobslop.plugins.manager import PLUGINS, SOURCE_FILE, PluginManager
from jobslop.plugins.manifest import MANIFEST, ManifestError, read, version_tuple

STAGING_DIR = DATA_DIR / "plugins-staging"
MAX_DOWNLOAD = 8 * 1024 * 1024         # bytes: a plugin is code and a few word lists, not a video
MAX_UNPACKED = 25 * 1024 * 1024
MAX_FILES = 400
STAGE_MINUTES = 30                      # a prepared install is forgotten after this
DOWNLOAD_HOSTS = ("github.com", "api.github.com", "codeload.github.com")
LINK_RE = re.compile(r"^(?:https?://)?(?:www\.)?github\.com/([A-Za-z0-9-]{1,39})/([A-Za-z0-9._-]{1,100}?)(?:\.git)?(?:/.*)?$")


class InstallError(ValueError):
    """Something the user should be told, in plain words."""


@dataclass(frozen=True)
class Repo:
    owner: str
    name: str

    @property
    def url(self) -> str:
        return f"https://github.com/{self.owner}/{self.name}"

    @property
    def api(self) -> str:
        return f"https://api.github.com/repos/{self.owner}/{self.name}"


def parse_link(link: str) -> Repo:
    """'https://github.com/JobSlop/jobslop-plugin-accounting' (or without https://, or a page inside it)."""
    m = LINK_RE.match((link or "").strip())
    if not m or m[2] in (".", ".."):
        raise InstallError("That isn't a GitHub link - it should look like github.com/someone/their-plugin")
    return Repo(m[1], m[2])


def _github(url: str):
    return net.get_json(url, timeout=20, headers={"Accept": "application/vnd.github+json",
                                                   "User-Agent": f"jobslop/{config.APP_VERSION}"})


def latest(repo: Repo) -> dict:
    """Where to download the newest version: {"zip", "ref", "version"} (a release, else the main branch)."""
    try:
        rel = _github(repo.api + "/releases/latest")
        tag = str(rel.get("tag_name") or "")
        return {"zip": f"{repo.api}/zipball/{urllib.parse.quote(tag)}", "ref": tag,
                "version": tag.lstrip("vV"), "notes": str(rel.get("body") or "")[:3000]}
    except Exception as e:
        if "404" not in str(e):
            raise InstallError(f"Couldn't reach GitHub ({str(e)[:80]})") from None
    try:
        info = _github(repo.api)
    except Exception as e:
        raise InstallError("That repository doesn't exist or isn't public" if "404" in str(e)
                           else f"Couldn't reach GitHub ({str(e)[:80]})") from None
    branch = str(info.get("default_branch") or "main")
    return {"zip": f"{repo.api}/zipball/{urllib.parse.quote(branch)}", "ref": branch, "version": "", "notes": ""}


def download(url: str, max_bytes: int = MAX_DOWNLOAD) -> bytes:
    if urllib.parse.urlparse(url).hostname not in DOWNLOAD_HOSTS:
        raise InstallError("Plugins can only be downloaded from GitHub")
    req = urllib.request.Request(url, headers={"User-Agent": f"jobslop/{config.APP_VERSION}"})
    with urllib.request.urlopen(req, timeout=60) as r:
        if urllib.parse.urlparse(r.geturl()).hostname not in DOWNLOAD_HOSTS:
            raise InstallError("GitHub sent the download somewhere unexpected - stopped")
        data = r.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise InstallError(f"That plugin is too big (over {max_bytes // (1024 * 1024)} MB)")
    return data


def unpack(data: bytes, dest: Path) -> Path:
    """Unpack a GitHub zip safely into dest; returns the folder that holds plugin.json."""
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise InstallError("The download isn't a valid zip file") from None
    infos = z.infolist()
    if len(infos) > MAX_FILES:
        raise InstallError("That plugin has too many files")
    if sum(i.file_size for i in infos) > MAX_UNPACKED:
        raise InstallError("That plugin is too big once unpacked")
    root = dest.resolve()
    for info in infos:
        name = info.filename.replace("\\", "/")
        parts = PurePosixPath(name).parts
        if name.startswith("/") or re.match(r"^[A-Za-z]:", name) or ".." in parts:
            raise InstallError("The plugin's zip tries to write outside its folder - not installed")
        if (info.external_attr >> 16) & 0o170000 == 0o120000:
            raise InstallError("The plugin's zip contains links to other files - not installed")
        target = (dest / name).resolve()
        if root != target and root not in target.parents:
            raise InstallError("The plugin's zip tries to write outside its folder - not installed")
        if info.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        with z.open(info) as src, open(target, "wb") as out:
            shutil.copyfileobj(src, out)
    # GitHub zips put everything in one "owner-repo-sha" folder; plugin.json is at its top
    candidates = [dest] + [d for d in dest.iterdir() if d.is_dir()]
    for folder in candidates:
        if (folder / MANIFEST).is_file():
            return folder
    raise InstallError("That repository isn't a jobslop plugin (there's no plugin.json at its top)")


class Installer:
    def __init__(self, plugins: PluginManager = PLUGINS, staging: Path = STAGING_DIR) -> None:
        self.plugins, self.staging = plugins, Path(staging)
        self._pending: dict[str, dict] = {}
        self._lock = threading.Lock()

    def _tidy(self) -> None:
        now = time.time()
        for token, p in list(self._pending.items()):
            if now - p["t"] > STAGE_MINUTES * 60:
                shutil.rmtree(p["dir"], ignore_errors=True)
                del self._pending[token]

    def prepare(self, link: str) -> dict:
        """Download and check a plugin; returns what the user is asked to confirm (nothing runs yet)."""
        repo = parse_link(link)
        where = latest(repo)
        data = download(where["zip"])
        with self._lock:
            self._tidy()
            token = secrets.token_urlsafe(16)
            stage = self.staging / token
            stage.mkdir(parents=True, exist_ok=True)
        try:
            folder = unpack(data, stage)
            m = read(folder)
            self._check_name(m.id, repo)
        except (ManifestError, InstallError) as e:
            shutil.rmtree(stage, ignore_errors=True)
            raise InstallError(str(e) if isinstance(e, InstallError) else f"Can't install it: {e}") from None
        current = self.plugins.get(m.id)
        with self._lock:
            self._pending[token] = {"t": time.time(), "dir": stage, "folder": folder, "repo": repo, "ref": where["ref"]}
        return {"token": token, "id": m.id, "name": m.name, "version": m.version, "author": m.author,
                "description": m.description, "adds": m.adds(), "runs_code": bool(m.python or m.ui),
                "source": repo.url, "ref": where["ref"],
                "replaces": current.manifest.version if current and current.manifest else ""}

    def _check_name(self, pid: str, repo: Repo) -> None:
        """A plugin from a link may not pretend to be a built-in one (unless it IS that one's own repo)."""
        builtin = self.plugins.builtin_dir / pid / MANIFEST
        if builtin.is_file():
            try:
                home = read(builtin.parent).homepage.rstrip("/").lower()
            except ManifestError:
                home = ""
            if home != repo.url.lower():
                raise InstallError(f'A plugin that comes with jobslop is already called "{pid}" - this one can\'t replace it')

    def confirm(self, token: str) -> str:
        with self._lock:
            p = self._pending.pop(token, None)
        if not p:
            raise InstallError("That install has expired - paste the link again")
        try:
            m = read(p["folder"])
            target = self.plugins.installed_dir / m.id
            self.plugins.unload(m.id)
            self.plugins.installed_dir.mkdir(parents=True, exist_ok=True)
            old = target.with_name(target.name + ".old")
            shutil.rmtree(old, ignore_errors=True)
            if target.exists():
                target.rename(old)
            shutil.move(str(p["folder"]), str(target))
            shutil.rmtree(old, ignore_errors=True)
            (target / SOURCE_FILE).write_text(json.dumps({
                "url": p["repo"].url, "ref": p["ref"], "installed": time.strftime("%Y-%m-%d %H:%M")}), encoding="utf-8")
        finally:
            shutil.rmtree(p["dir"], ignore_errors=True)
        self.plugins.discover()
        self.plugins.set_enabled(m.id, True)
        return m.id

    def remove(self, pid: str) -> None:
        p = self.plugins.get(pid)
        if not p or p.builtin:
            raise InstallError("Only plugins you installed from a link can be removed - built-in ones can be switched off")
        self.plugins.unload(pid)
        folder = self.plugins.installed_dir / p.folder.name
        if folder.resolve().parent != self.plugins.installed_dir.resolve():
            raise InstallError("That plugin isn't in the plugins folder")
        shutil.rmtree(folder, ignore_errors=True)
        self.plugins.discover()
        self.plugins.load_enabled()            # a built-in copy it was replacing comes back

    def check_updates(self) -> list[dict]:
        """For each plugin with a GitHub home: is there a newer release?"""
        out = []
        for p in self.plugins.all():
            m = p.manifest
            link = (p.source or {}).get("url") or (m.homepage if m else "")
            if not m or not link:
                continue
            try:
                repo = parse_link(link)
                rel = _github(repo.api + "/releases/latest")
                newest = str(rel.get("tag_name") or "").lstrip("vV")
            except Exception:
                continue                       # no releases, offline, or not on GitHub: nothing to offer
            if newest and version_tuple(newest) > version_tuple(m.version):
                out.append({"id": p.id, "current": m.version, "latest": newest, "link": repo.url})
        return out


INSTALLER = Installer()
