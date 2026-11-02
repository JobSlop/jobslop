"""Who may use the app's server: only its own window, the paired Chrome extension, and PIN-signed-in phones."""
import re
from unittest import mock

import pytest
from support import AppServer, AppTestCase, reset_data

from jobslop import extension, runtime
from jobslop.profile import store as pstore
from jobslop.server import handler, phone, phone_handler


class AppServerSecurityTests(AppTestCase):
    def test_app_page_loads(self):
        code, page, hdrs = self.app.request("/")
        assert code == 200
        assert "jobslop" in page
        assert 'id="where"' in page

    def test_other_websites_are_refused(self):
        """A web page in your browser must not be able to read your profile through the app."""
        for path in ("/api/profile", "/api/saved", "/api/settings"):
            code, _ = self.app.get(path, headers={"Origin": "https://evil.example"})
            assert code == 403, path
        code, _ = self.app.post("/api/profile", {"profile": {"first_name": "Hacked"}}, headers={"Origin": "https://evil.example"})
        assert code == 403
        assert pstore.load_profile() == {}

    def test_wrong_host_is_refused(self):
        """DNS-rebinding protection: requests must be addressed to 127.0.0.1 / localhost."""
        code, _ = self.app.get("/api/profile", headers={"Host": "evil.example"})
        assert code == 403

    def test_unknown_paths(self):
        assert self.app.get("/api/nope")[0] == 404
        assert self.app.post("/api/nope", {})[0] == 404

    def test_bad_requests(self):
        import urllib.request
        req = urllib.request.Request(f"http://127.0.0.1:{self.app.port}/api/profile", data=b"{not json",
                                     headers={"Content-Type": "application/json"})
        try:
            urllib.request.urlopen(req, timeout=10)
            pytest.fail("bad JSON should be refused")
        except urllib.error.HTTPError as e:
            assert e.code == 400

    def test_extension_cors_only_for_extension(self):
        code, _, hdrs = self.app.request("/ext/profile", method="OPTIONS", headers={"Origin": "chrome-extension://abc"})
        assert hdrs.get("Access-Control-Allow-Origin") == "chrome-extension://abc"
        code, _, hdrs = self.app.request("/ext/profile", method="OPTIONS", headers={"Origin": "https://evil.example"})
        assert hdrs.get("Access-Control-Allow-Origin") is None


class PhoneTests:
    """Phone access: a separate server, PIN sign-in, and PC-only actions blocked."""

    @classmethod
    def setup_class(cls):
        cls.phone = AppServer(phone_handler.PhoneHandler)

    @classmethod
    def teardown_class(cls):
        cls.phone.close()

    def setup_method(self):
        reset_data()
        phone.phone["fails"] = []
        self.pin = phone.new_pin()

    def login(self, pin):
        code, r, hdrs = self.phone.request("/phone/login", body={"pin": pin})
        cookie = re.search(r"jfs=([\w-]+)", hdrs.get("Set-Cookie", "") or "")
        return code, (f"jfs={cookie[1]}" if cookie else None)

    def test_pin_is_six_digits(self):
        assert re.search(r"^\d{6}$", self.pin)

    def test_needs_sign_in(self):
        code, page, _ = self.phone.request("/")
        assert "Enter the PIN" in page
        assert self.phone.get("/api/profile")[0] == 401

    def test_sign_in_and_use(self):
        code, cookie = self.login(self.pin)
        assert code == 200
        pstore.save_profile({"first_name": "Sarah"})
        code, r = self.phone.get("/api/profile", headers={"Cookie": cookie})
        assert (code, r["profile"]["first_name"]) == (200, "Sarah")
        code, page, _ = self.phone.request("/", headers={"Cookie": cookie})
        assert "window.JF_PHONE=true" in page

    def test_pc_only_actions_are_blocked(self):
        _, cookie = self.login(self.pin)
        for path in ("/api/settings", "/api/phone", "/api/prefs"):
            assert self.phone.get(path, headers={"Cookie": cookie})[0] == 403, path
        for path in ("/api/open", "/api/apply", "/api/export", "/api/copy", "/api/settings"):
            assert self.phone.post(path, {}, headers={"Cookie": cookie})[0] == 403, path
        assert self.phone.get("/ext/profile", headers={"Cookie": cookie, "X-JobFinder-Key": extension.pairing_code()})[0] == 403

    def test_wrong_pin_and_lockout(self):
        for _ in range(5):
            assert self.login("000000" if self.pin != "000000" else "111111")[0] == 403
        assert self.login(self.pin)[0] == 429, "after 5 wrong tries even the right PIN waits 5 minutes"

    def test_new_pin_signs_phones_out(self):
        _, cookie = self.login(self.pin)
        phone.new_pin()
        assert self.phone.get("/api/profile", headers={"Cookie": cookie})[0] == 401

    def test_phone_settings_from_the_pc(self):
        app = AppServer()
        runtime.state["port"] = app.port
        try:
            with mock.patch.object(handler, "start_phone_server", return_value=True), \
                    mock.patch.object(handler, "stop_phone_server", return_value=None):
                code, r = app.post("/api/phone", {"enabled": True})
                assert r["enabled"]
                assert re.search(r"^\d{6}$", r["pin"])
                old = r["pin"]
                code, r = app.post("/api/phone", {"new_pin": True})
                assert r["pin"] != old if r["pin"] != old else None
                code, r = app.post("/api/phone", {"signout": True})
                assert r["phones"] == 0
                code, r = app.post("/api/phone", {"enabled": False})
                assert not r["enabled"]
        finally:
            app.close()
