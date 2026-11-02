"""Profile, CV upload, LinkedIn import, settings and job-match terms — through the app's own web API."""
import json
import re
from datetime import datetime
from unittest import mock

from support import AppTestCase, b64, make_docx, make_pdf, make_zip

from jobslop import config, extension, net, rates, runtime, settings
from jobslop.boards import registry
from jobslop.profile import cvparse
from jobslop.profile import store as pstore
from jobslop.search import engine, matching

LI_PROFILE = "First Name,Last Name,Maiden Name,Address,Birth Date,Headline,Summary,Industry,Zip Code,Geo Location,Twitter Handles,Websites,Instant Messengers\n" \
             "Regilio Mark,Henry,,,,Games Programmer,,,B3 2BJ,\"Birmingham, England, United Kingdom\",,[PORTFOLIO:https://regilio.dev],\n"
LI_POSITIONS = "Company Name,Title,Description,Location,Started On,Finished On\n" \
               "Big Studio,Gameplay Programmer,Built combat,\"Leamington Spa, England\",Mar 2021,\n" \
               "Small Studio,Junior Programmer,Tools,Birmingham,Jun 2019,Feb 2021\n"
LI_EDU = "School Name,Start Date,End Date,Notes,Degree Name,Activities\n" \
         "Staffordshire University,2016,2019,,Bachelor of Science - BS,\n"
LI_EMAILS = "Email Address,Confirmed,Primary,Updated On\nold@example.com,Yes,No,\nme@example.com,Yes,Yes,\n"
LI_PHONES = "Extension,Number,Type\n,07911 123456,Mobile\n"
LI_SKILLS = "Name\nC++\nUnreal Engine\n"


def linkedin_zip():
    return make_zip({"Profile.csv": LI_PROFILE, "Positions.csv": LI_POSITIONS, "Education.csv": LI_EDU,
                     "Email Addresses.csv": LI_EMAILS, "PhoneNumbers.csv": LI_PHONES, "Skills.csv": LI_SKILLS})


class ProfileTests(AppTestCase):
    def test_save_and_load_profile(self):
        code, r = self.app.post("/api/profile", {"profile": {"first_name": "Regilio", "city": "Birmingham",
                                                             "jobs": [{"title": "Dev", "company": "Co", "junk": "x"}],
                                                             "nested": {"not": "kept"}}})
        assert code == 200
        assert "nested" not in r["profile"]
        assert r["profile"]["jobs"][0] == {"title": "Dev", "company": "Co", "location": "", "start": "",
                                                   "end": "", "description": ""}
        code, r = self.app.get("/api/profile")
        assert r["profile"]["first_name"] == "Regilio"
        assert re.search(r"^[A-Z2-9]{4}-[A-Z2-9]{4}$", r["ext"]["code"])
        assert r["cv"] is None

    def test_profile_limits(self):
        r = pstore.save_profile({"bio": "x" * 9000, "jobs": [{"title": str(i)} for i in range(30)]})
        assert len(r["bio"]) == 8000
        assert len(r["jobs"]) == 20

    def test_clear_profile(self):
        pstore.save_profile({"first_name": "A"})
        self.app.post("/api/cv", {"name": "cv.pdf", "data": b64(make_pdf(["Hello"]))})
        code, r = self.app.post("/api/profile/clear", {"cv": True})
        assert r == {"profile": {}, "cv_removed": True}
        assert pstore.load_profile() == {}
        assert pstore.cv_file() is None

    def test_upload_parse_and_remove_cv(self):
        pdf = make_pdf(["**Sarah Thompson", "sarah@example.com", "Coventry CV1 2AB"])
        code, r = self.app.post("/api/cv", {"name": "../../My CV?.pdf", "data": b64(pdf)})
        assert code == 200
        assert r["cv"]["name"] == "My CV_.pdf", "folders and odd characters are stripped from the name"
        with mock.patch.object(cvparse, "ocr_pdf", return_value=[]):
            code, r = self.app.post("/api/cv/parse", {})
        assert (r["found"]["first_name"], r["found"]["email"], r["found"]["postcode"]) == \
                         ("Sarah", "sarah@example.com", "CV1 2AB")
        code, r = self.app.post("/api/cv", {"remove": True})
        assert r["cv"] is None
        code, r = self.app.post("/api/cv/parse", {})
        assert code == 400

    def test_only_one_cv_is_kept(self):
        self.app.post("/api/cv", {"name": "old.pdf", "data": b64(b"%PDF-1.4 old")})
        self.app.post("/api/cv", {"name": "new.docx", "data": b64(make_docx(["Hi"]))})
        assert [f.name for f in pstore.CV_DIR.iterdir()] == ["new.docx"]

    def test_cv_too_big(self):
        code, r = self.app.post("/api/cv", {"name": "big.pdf", "data": b64(b"0" * (10 * 1024 * 1024 + 1))})
        assert code == 400
        assert "10 MB" in r["error"]


class LinkedInTests(AppTestCase):
    def test_data_export_zip(self):
        code, r = self.app.post("/api/linkedin", {"name": "Basic_LinkedInDataExport.zip", "data": b64(linkedin_zip())})
        assert code == 200, r
        f = r["found"]
        assert (f["first_name"], f["middle_name"], f["last_name"]) == ("Regilio", "Mark", "Henry")
        assert (f["city"], f["country"], f["postcode"]) == ("Birmingham", "United Kingdom", "B3 2BJ")
        assert (f["email"], f["phone"], f["website"]) == ("me@example.com", "07911 123456", "https://regilio.dev")
        assert [j["title"] for j in f["jobs"]] == ["Gameplay Programmer", "Junior Programmer"]
        assert f["jobs"][0]["end"] == "Present"
        assert (f["current_title"], f["current_company"]) == ("Gameplay Programmer", "Big Studio")
        assert f["years_experience"] == str(datetime.now().year - 2019)
        assert f["university"] == "Staffordshire University"
        assert f["skills"] == "C++, Unreal Engine"

    def test_positions_csv_on_its_own(self):
        code, r = self.app.post("/api/linkedin", {"name": "Positions.csv", "data": b64(LI_POSITIONS)})
        assert len(r["found"]["jobs"]) == 2

    def test_profile_pdf(self):
        pdf = make_pdf(["**Regilio Henry", "me@example.com", "www.linkedin.com/in/regilio (LinkedIn)", "Birmingham, England, United Kingdom"])
        with mock.patch.object(cvparse, "ocr_pdf", return_value=[]):
            code, r = self.app.post("/api/linkedin", {"name": "Profile.pdf", "data": b64(pdf)})
        assert (r["found"]["first_name"], r["found"]["email"]) == ("Regilio", "me@example.com")
        assert "linkedin.com" not in r["found"].get("website", "")

    def test_bad_files(self):
        for name, data, msg in (("x.zip", b"", "empty"), ("photo.png", b"\x89PNG....", "LinkedIn profile PDF"),
                                ("other.zip", make_zip({"notes.csv": "a,b\n1,2"}), "doesn't look like")):
            code, r = self.app.post("/api/linkedin", {"name": name, "data": b64(data) if data else ""})
            assert code == 400, name
            assert msg in r["error"], name
        assert not list(config.DATA_DIR.glob("linkedin-import*")), "temporary import files are cleaned up"


class SettingsTests(AppTestCase):
    def test_keys_are_masked(self):
        code, r = self.app.post("/api/settings", {"reed_key": " abcdefghijk ", "apify_token": "short"})
        assert r["reed_key"] == "abc••••••jk"
        assert r["apify_token"] == "set"
        assert settings.load_settings()["reed_key"] == "abcdefghijk", "keys are stored trimmed"
        assert self.app.get("/api/settings")[1]["adzuna_id"] == ""

    def test_screen_preferences(self):
        code, r = self.app.post("/api/prefs", {"theme": "dark", "f_where": "B3 2BJ"})
        assert r["theme"] == "dark"
        assert self.app.get("/api/prefs")[1]["f_where"] == "B3 2BJ"

    def test_pairing_code_stays_the_same(self):
        assert extension.pairing_code() == extension.pairing_code()

    def test_match_terms(self):
        code, r = self.app.post("/api/match_terms", {"terms": [
            {"name": "Communications", "aliases": "comms, PR, public relations", "title_only": True}, {"name": ""}]})
        assert r == [{"name": "Communications", "aliases": ["comms", "PR", "public relations"], "title_only": True}]
        assert self.app.get("/api/match_terms")[1] == r
        g = matching.find_group("PR", matching.match_groups())
        assert g["name"] == "Communications"
        assert matching.group_score({"title": "PR Manager", "tags": [], "desc": ""}, g) > 0
        assert matching.group_score({"title": "Office Manager", "tags": [], "desc": "good communications"}, g) == 0, \
                         "title-only terms ignore the description"

    def test_match_terms_expand_the_search(self):
        settings.update_settings(lambda s: s.update(match_terms=[{"name": "Games Programmer", "aliases": ["Gameplay Programmer"]}]))
        from support import FakeBoards, base_opts, make_job
        fake = FakeBoards({"LinkedIn": [make_job("LinkedIn", "Gameplay Programmer")]})
        with mock.patch.dict(registry.SOURCES, fake.sources(), clear=True):
            out = engine.search("games programmer", ["LinkedIn"], base_opts(), fresh=True)
        assert {c[1] for c in fake.calls} == {"Games Programmer", "Gameplay Programmer"}
        assert len(out["results"]) == 1

    def test_countries_list(self):
        code, r = self.app.get("/api/countries")
        codes = {c["code"] for c in r}
        assert {"GB", "US", "NL", "DK", "DE"} <= codes
        assert next(c for c in r if c["code"] == "GB")["currency"] == "GBP"

    def test_exchange_rates_work_offline(self):
        with mock.patch.object(net, "get_json", side_effect=OSError("offline")):
            code, r = self.app.get("/api/rates")
        assert r["source"] == "built-in (offline)"
        assert r["rates"]["USD"] == 1
        with mock.patch.object(net, "get_json", return_value={"rates": {"GBP": 0.8, "EUR": 0.9}}):
            rates.RATES_FILE.unlink(missing_ok=True)
            r = rates.get_rates()
        assert (r["rates"]["GBP"], r["rates"]["USD"]) == (0.8, 1)
        with mock.patch.object(net, "get_json", side_effect=AssertionError("should use the saved rates")):
            assert rates.get_rates()["rates"]["GBP"] == 0.8


class ExtensionDataTests(AppTestCase):
    def test_cover_letter_template(self):
        letter = extension.render_letter("Dear {company}, I'm {full_name} applying for {title}. {unknown}",
                                  {"first_name": "Sarah", "last_name": "Thompson"}, {"company": "Rare", "title": "Programmer"})
        assert letter == "Dear Rare, I'm Sarah Thompson applying for Programmer. {unknown}"
        assert "your company" in extension.render_letter("{company}", {}, None)

    def test_extension_payload(self):
        pstore.save_profile({"first_name": "Sarah", "last_name": "Thompson", "cover_letter_template": "Hi {company}",
                         "jobs": [{"title": "Programmer", "company": "Rare"}]})
        runtime.state["active"] = {"job": {"title": "Dev", "company": "Sumo", "url": "https://x"}, "t": __import__("time").time()}
        p = extension.extension_payload()
        assert (p["full_name"], p["cover_letter"], p["active"]["company"]) == ("Sarah Thompson", "Hi Sumo", "Sumo")
        assert (p["profile"]["current_title"], p["profile"]["current_company"]) == ("Programmer", "Rare")

    def test_extension_needs_the_pairing_code(self):
        code, _ = self.app.get("/ext/profile")
        assert code == 401
        code, _ = self.app.get("/ext/profile", headers={"X-JobFinder-Key": "WRONG-CODE"})
        assert code == 401
        pstore.save_profile({"first_name": "Sarah"})
        code, r = self.app.get("/ext/profile", headers={"X-JobFinder-Key": extension.pairing_code().lower(),
                                                        "Origin": "chrome-extension://abc"})
        assert (code, r["profile"]["first_name"]) == (200, "Sarah")
        code, r = self.app.post("/api/ext/status", {})
        assert r["connected"]

    def test_extension_gets_the_cv(self):
        self.app.post("/api/cv", {"name": "cv.pdf", "data": b64(b"%PDF-1.4 test")})
        code, r = self.app.get("/ext/cv", headers={"X-JobFinder-Key": extension.pairing_code()})
        assert (r["name"], r["type"]) == ("cv.pdf", "application/pdf")

    def test_extension_folder_is_installed(self):
        folder = extension.install_extension()
        assert (pstore.EXT_DIR / "manifest.json").exists()
        pairing = json.loads((pstore.EXT_DIR / "pairing.json").read_text(encoding="utf-8"))
        assert pairing["code"] == extension.pairing_code()
        assert folder == str(pstore.EXT_DIR)
