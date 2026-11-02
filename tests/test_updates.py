"""In-app updates from GitHub Releases: checking, downloading with a checksum, swapping the .exe, and the
release script's settings. GitHub is never contacted: its answers are made up here."""
import hashlib
import io
import sys
from pathlib import Path
from unittest import mock

import pytest

from support import jf, AppTestCase, ROOT

NEW_EXE = b"MZ pretend new jobslop.exe" * 100
SHA = hashlib.sha256(NEW_EXE).hexdigest()
DL = "https://github.com/me/jobslop/releases/download/v9.1.0/"
RELEASE = {"tag_name": "v9.1.0", "body": "Faster search\nNew icons", "html_url": "https://github.com/me/jobslop/releases/tag/v9.1.0",
           "published_at": "2026-11-20T10:00:00Z",
           "assets": [{"name": "jobslop.exe", "size": len(NEW_EXE), "browser_download_url": DL + "jobslop.exe"},
                      {"name": "jobslop.exe.sha256", "size": 80, "browser_download_url": DL + "jobslop.exe.sha256"},
                      {"name": "jobslop-Mac.zip", "size": 5, "browser_download_url": DL + "jobslop-Mac.zip"}]}


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


def fake_urlopen(files):
    def opener(req, timeout=None):
        url = req.full_url if hasattr(req, "full_url") else req
        return FakeResponse(files[url])
    return opener


@pytest.fixture
def repo(clean_data):
    with mock.patch.object(jf, "UPDATE_REPO", "me/jobslop"), mock.patch.object(jf, "UPDATE_ASSET", "jobslop.exe"), \
            mock.patch.object(jf, "APP_VERSION", "9.0.0"):
        jf.update_state.update(done=0, total=0, busy=False, ready="", error="", updated_from="")
        yield


def test_versions():
    assert jf.is_newer("2.1.0", "2.0.9") and jf.is_newer("v10.0", "9.9.9") and jf.is_newer("2.0.1", "2.0")
    assert not jf.is_newer("2.0.0", "2.0.0") and not jf.is_newer("1.9", "2.0.0") and not jf.is_newer("", "1.0.0")


def test_only_github_download_links_are_kept():
    with mock.patch.object(jf, "UPDATE_ASSET", "jobslop.exe"):
        bad = {**RELEASE, "assets": [{"name": "jobslop.exe", "browser_download_url": "https://evil.example/jobslop.exe"}]}
        info = jf.release_info(bad)
    assert info["version"] == "9.1.0" and info["asset_url"] == "" and info["sha256_url"] == ""


def test_switched_off_without_a_repository(clean_data):
    with mock.patch.object(jf, "UPDATE_REPO", ""), mock.patch.object(jf, "get_json") as gj:
        info = jf.check_for_update(force=True)
    assert info["enabled"] is False and "available" not in info
    gj.assert_not_called()


def test_check_finds_a_new_version_and_asks_github_rarely(repo):
    with mock.patch.object(jf, "get_json", return_value=RELEASE) as gj:
        info = jf.check_for_update()
        again = jf.check_for_update()
        jf.check_for_update(force=True)
    assert (info["available"], info["version"], info["current"]) == (True, "9.1.0", "9.0.0")
    assert info["notes"] == "Faster search\nNew icons" and info["page"].endswith("/v9.1.0")
    assert again["available"] and gj.call_count == 2, "the second check uses the saved answer; Check asks again"
    assert gj.call_args.kwargs["headers"]["User-Agent"] == "jobslop/9.0.0"


def test_same_version_is_not_offered(repo):
    with mock.patch.object(jf, "get_json", return_value={**RELEASE, "tag_name": "v9.0.0"}):
        assert jf.check_for_update(force=True)["available"] is False


def test_dont_receive_any_updates(repo):
    """The Settings tick: GitHub is never asked, nothing is offered and nothing can be downloaded."""
    with mock.patch.object(jf, "get_json", return_value=RELEASE):
        jf.check_for_update()                                  # an update was seen before ticking the box
    jf.update_settings(lambda s: s.__setitem__("updates_off", True))
    with mock.patch.object(jf, "get_json", return_value=RELEASE) as gj:
        quiet, forced = jf.check_for_update(), jf.check_for_update(force=True)
        with mock.patch.object(jf, "FROZEN", True), mock.patch.object(jf, "IS_WIN", True):
            jf.download_update()
    gj.assert_not_called()
    assert quiet["off"] and "available" not in quiet and "available" not in forced
    assert "no update" in jf.update_state["error"].lower()


def test_skip_this_version(repo):
    jf.update_settings(lambda s: s.__setitem__("update_skip", "9.1.0"))
    with mock.patch.object(jf, "get_json", return_value=RELEASE):
        assert jf.check_for_update(force=True)["skipped"] is True


def test_install_is_only_offered_for_the_windows_app(repo):
    with mock.patch.object(jf, "get_json", return_value=RELEASE):
        with mock.patch.object(jf, "FROZEN", False):
            assert jf.check_for_update(force=True)["can_install"] is False, "running from source: download page"
        with mock.patch.object(jf, "FROZEN", True), mock.patch.object(jf, "IS_WIN", True):
            assert jf.check_for_update()["can_install"] is True
        no_sha = {**RELEASE, "assets": RELEASE["assets"][:1]}
    with mock.patch.object(jf, "get_json", return_value=no_sha), mock.patch.object(jf, "FROZEN", True), \
            mock.patch.object(jf, "IS_WIN", True):
        assert jf.check_for_update(force=True)["can_install"] is False, "no checksum, no automatic install"


def download(files):
    with mock.patch.object(jf, "get_json", return_value=RELEASE), mock.patch.object(jf, "FROZEN", True), \
            mock.patch.object(jf, "IS_WIN", True), mock.patch.object(jf.urllib.request, "urlopen", fake_urlopen(files)):
        jf.download_update()
    return jf.update_state


def test_download_is_checked_against_its_checksum(repo):
    st = download({DL + "jobslop.exe.sha256": f"{SHA}  jobslop.exe\n".encode(), DL + "jobslop.exe": NEW_EXE})
    assert (st["error"], st["busy"], st["done"]) == ("", False, len(NEW_EXE))
    assert Path(st["ready"]).read_bytes() == NEW_EXE


def test_a_damaged_download_is_thrown_away(repo):
    st = download({DL + "jobslop.exe.sha256": f"{SHA}  jobslop.exe\n".encode(), DL + "jobslop.exe": NEW_EXE[:-5] + b"XXXXX"})
    assert "checksum" in st["error"] and st["ready"] == ""
    assert not any((jf.UPDATE_DIR).glob("jobslop-new.exe*")), "nothing half-downloaded is left behind"
    st = download({DL + "jobslop.exe.sha256": b"not a checksum", DL + "jobslop.exe": NEW_EXE})
    assert "checksum" in st["error"] and st["ready"] == ""


def test_swap_puts_the_new_version_in_place(tmp_path):
    app, upd = tmp_path / "Bob's 100% apps", tmp_path / "update"
    app.mkdir(), upd.mkdir()
    (app / "jobslop.exe").write_bytes(b"old version")
    (app / "jobslop.exe.old").write_bytes(b"leftover from last time")
    (upd / "jobslop-new.exe").write_bytes(b"new version")
    jf.swap_in_update(upd / "jobslop-new.exe", app / "jobslop.exe")
    assert (app / "jobslop.exe").read_bytes() == b"new version"
    assert (app / "jobslop.exe.old").read_bytes() == b"old version", "the running copy steps aside (renamed, not deleted)"
    assert not (upd / "jobslop-new.exe").exists()


def test_a_failed_swap_changes_nothing(tmp_path):
    (tmp_path / "jobslop.exe").write_bytes(b"old version")
    (tmp_path / "jobslop-new.exe").write_bytes(b"new version")
    with mock.patch.object(jf.shutil, "move", side_effect=OSError("disk full")), pytest.raises(ValueError, match="nothing was changed"):
        jf.swap_in_update(tmp_path / "jobslop-new.exe", tmp_path / "jobslop.exe")
    assert (tmp_path / "jobslop.exe").read_bytes() == b"old version" and not (tmp_path / "jobslop.exe.old").exists()
    with mock.patch.object(jf.os, "replace", side_effect=PermissionError(5, "denied")), pytest.raises(ValueError, match="no permission"):
        jf.swap_in_update(tmp_path / "jobslop-new.exe", tmp_path / "jobslop.exe")
    assert (tmp_path / "jobslop.exe").read_bytes() == b"old version"


def test_new_copy_starts_without_the_old_ones_hidden_settings():
    """The bug behind 'it didn't reopen': a self-unpacking app passes its unpack folder to programs it starts."""
    fake_env = {"PATH": r"C:\Windows", "APPDATA": r"C:\Users\me\AppData\Roaming", "_PYI_APPLICATION_HOME_DIR": r"C:\Temp\_MEI1",
                "_PYI_PARENT_PROCESS_LEVEL": "1", "_PYI_ARCHIVE_FILE": r"C:\Apps\jobslop.exe", "_MEIPASS2": r"C:\Temp\_MEI1"}
    with mock.patch.dict(jf.os.environ, fake_env, clear=True), mock.patch.object(jf.subprocess, "Popen") as popen:
        jf.launch_fresh(Path(r"C:\Apps\jobslop.exe"))
    env = popen.call_args.kwargs["env"]
    assert popen.call_args.args[0] == [r"C:\Apps\jobslop.exe"], "started directly - no shell or script"
    assert env["PYINSTALLER_RESET_ENVIRONMENT"] == "1"
    assert not [k for k in env if k.startswith(("_PYI_", "_MEI"))]
    assert env["APPDATA"] == fake_env["APPDATA"], "everything else is passed on as it was"


def test_start_up_never_crashes_over_the_old_copy(repo, tmp_path):
    """Right after an update the old version may still be closing, so its .old file can't be deleted yet."""
    exe = tmp_path / "jobslop.exe"
    exe.write_bytes(b"new")
    (tmp_path / "jobslop.exe.old").write_bytes(b"old")
    calls = []

    def locked_then_free(self, missing_ok=False):
        calls.append(self.name)
        if self.name.endswith(".old") and calls.count(self.name) < 3:
            raise PermissionError(5, "Access is denied")
        return orig(self, missing_ok)
    orig = Path.unlink
    with mock.patch.object(jf, "FROZEN", True), mock.patch.object(jf.sys, "executable", str(exe)), \
            mock.patch.object(Path, "unlink", locked_then_free), mock.patch.object(jf.time, "sleep"):
        jf.after_update_cleanup()
    assert not (tmp_path / "jobslop.exe.old").exists(), "deleted once the old version had closed"
    (tmp_path / "jobslop.exe.old").write_bytes(b"old")
    always_locked = lambda self, missing_ok=False: (_ for _ in ()).throw(PermissionError(5, "Access is denied"))
    with mock.patch.object(jf, "FROZEN", True), mock.patch.object(jf.sys, "executable", str(exe)), \
            mock.patch.object(Path, "unlink", always_locked), mock.patch.object(jf.time, "sleep"):
        jf.after_update_cleanup()                          # still locked: jobslop starts anyway


def test_install_needs_a_finished_download(repo):
    with mock.patch.object(jf, "FROZEN", True), mock.patch.object(jf, "IS_WIN", True), \
            mock.patch.object(jf.subprocess, "Popen") as popen, pytest.raises(ValueError):
        jf.install_update()
    popen.assert_not_called()


def test_install_swaps_starts_the_new_version_and_closes(repo, tmp_path):
    jf.UPDATE_DIR.mkdir(parents=True, exist_ok=True)
    new = jf.UPDATE_DIR / "jobslop-new.exe"
    new.write_bytes(NEW_EXE)
    exe = tmp_path / "jobslop.exe"
    exe.write_bytes(b"old")
    jf.update_state["ready"] = str(new)
    with mock.patch.object(jf, "FROZEN", True), mock.patch.object(jf, "IS_WIN", True), \
            mock.patch.object(jf.sys, "executable", str(exe)), \
            mock.patch.object(jf.subprocess, "Popen") as popen, mock.patch.object(jf.threading, "Timer") as timer:
        jf.install_update()
    assert exe.read_bytes() == NEW_EXE and popen.call_args.args[0] == [str(exe)]
    timer.return_value.start.assert_called_once()
    assert jf.update_state["ready"] == ""


def test_after_an_update_the_app_says_so(repo):
    jf.update_settings(lambda s: s.__setitem__("last_version", "8.5.0"))
    jf.UPDATE_DIR.mkdir(parents=True, exist_ok=True)
    (jf.UPDATE_DIR / "jobslop-new.exe").write_bytes(b"x")
    jf.after_update_cleanup()
    assert jf.update_state["updated_from"] == "8.5.0" and jf.load_settings()["last_version"] == "9.0.0"
    assert not (jf.UPDATE_DIR / "jobslop-new.exe").exists()
    jf.after_update_cleanup()
    assert jf.update_state["updated_from"] == "", "only said once"


def test_release_script_reads_the_version_and_repository():
    sys.path.insert(0, str(ROOT))
    import release
    assert release.setting("APP_VERSION") == jf.APP_VERSION
    assert release.setting("UPDATE_REPO") == jf.UPDATE_REPO or jf.UPDATE_REPO.startswith(release.setting("UPDATE_REPO"))


class UpdateApiTests(AppTestCase):
    def test_check_and_actions(self):
        with mock.patch.object(jf, "UPDATE_REPO", "me/jobslop"), mock.patch.object(jf, "UPDATE_ASSET", "jobslop.exe"), \
                mock.patch.object(jf, "APP_VERSION", "9.0.0"), mock.patch.object(jf, "get_json", return_value=RELEASE):
            code, info = self.app.get("/api/update")
            assert code == 200 and info["available"] and info["version"] == "9.1.0"
            assert self.app.post("/api/update", {"action": "skip", "version": "9.1.0"})[1]["skipped"] is True
            off = self.app.post("/api/update", {"action": "off", "off": True})[1]
            assert off["off"] is True and "available" not in off
            on = self.app.post("/api/update", {"action": "off", "off": False})[1]
            assert on["off"] is False and on["available"] is True
            code, r = self.app.post("/api/update", {"action": "install"})
            assert code == 400 and "Download the update first" in r["error"]
            assert self.app.post("/api/update", {"action": "nonsense"})[0] == 400

    def test_github_being_down_is_reported_not_crashing(self):
        with mock.patch.object(jf, "UPDATE_REPO", "me/jobslop"), mock.patch.object(jf, "get_json", side_effect=OSError("offline")):
            code, info = self.app.get("/api/update")
        assert code == 200 and "Couldn't check for updates" in info["error"]

    def test_status(self):
        jf.update_state.update(done=5, total=10, busy=True, ready="", error="")
        assert self.app.get("/api/update/status")[1] == {"done": 5, "total": 10, "busy": True, "ready": "", "error": ""}
        jf.update_state.update(done=0, total=0, busy=False)

    def test_phones_cant_update_the_computer(self):
        assert "/api/update" in jf.PHONE_BLOCKED and "/api/update/status" in jf.PHONE_BLOCKED
