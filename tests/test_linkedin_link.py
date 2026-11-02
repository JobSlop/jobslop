"""Import from a LinkedIn profile link.

LinkedIn only shows profiles to signed-in people, so jobslop opens the link in your own Chrome and the
extension reads the page you're looking at. Tested here:
- recognising profile links, and turning what was read on the page into profile details
- the hand-over between the app and the extension (the app's own server endpoints)
- the extension reading a LinkedIn-style page in headless Chrome (skipped if Chrome isn't installed)
"""
import html
import json
import re
import shutil
import subprocess
from pathlib import Path
from unittest import mock

import pytest

from support import jf, AppTestCase, ROOT, TMP
from test_extension import find_chrome

# what the extension sends for a profile page: the lines of text it can see in each part of the page
LI_PAGE = {
    "url": "https://www.linkedin.com/in/sarah-test/",
    "name": "Sarah de Vries",
    "top": ["Sarah de Vries", "She/Her", "Gameplay Programmer at Rare | C++ | Unreal",
            "Coventry, England, United Kingdom", "Contact info", "500+ connections"],
    "experience": [
        {"lines": ["Rare", "Full-time · 6 yrs 2 mos", "Twycross, England, United Kingdom"],
         "roles": [["Lead Gameplay Programmer", "Mar 2023 - Present · 2 yrs 8 mos", "Leading the combat team",
                    "Skills: C++ · Leadership"],
                   ["Gameplay Programmer", "Full-time", "Sep 2019 - Feb 2023 · 3 yrs 6 mos", "Built the combat systems"]]},
        {"lines": ["Junior Programmer", "Codemasters · Full-time", "Jul 2018 - Aug 2019 · 1 yr 2 mos",
                   "Southam, England, United Kingdom · On-site"],
         "roles": [["Racing physics tools and UI.", "…see more"], ["Skills: C# · Unity"]]},
    ],
    "education": [["University of Warwick", "BSc (Hons), Computer Science", "2014 - 2017"]],
    "skills": ["C++", "Unreal Engine", "c++", "Gameplay Programming"],
}


def test_profile_links_are_recognised():
    url = jf.linkedin_profile_url
    assert url("https://www.linkedin.com/in/sarah-test/") == "https://www.linkedin.com/in/sarah-test/"
    assert url("linkedin.com/in/sarah-test?utm_source=share") == "https://www.linkedin.com/in/sarah-test/"
    assert url("uk.linkedin.com/in/Sarah-Test-123") == "https://www.linkedin.com/in/Sarah-Test-123/"
    assert url("https://www.linkedin.com/in/j%C3%B6rg/") == "https://www.linkedin.com/in/j%C3%B6rg/"
    for bad in ("", "sarah", "https://www.linkedin.com/company/rare/", "https://example.com/in/sarah",
                "https://www.linkedin.com/in/<script>/"):
        assert url(bad) is None, bad


def test_page_to_profile():
    f = jf.linkedin_from_page(LI_PAGE)
    assert (f["first_name"], f["last_name"]) == ("Sarah", "de Vries")
    assert (f["city"], f["country"]) == ("Coventry", "United Kingdom"), "the headline isn't mistaken for a place"
    jobs = f["jobs"]
    assert [(j["title"], j["company"]) for j in jobs] == [
        ("Lead Gameplay Programmer", "Rare"), ("Gameplay Programmer", "Rare"), ("Junior Programmer", "Codemasters")]
    assert (jobs[0]["start"], jobs[0]["end"], jobs[0]["location"]) == ("Mar 2023", "Present", "Twycross, England, United Kingdom")
    assert jobs[0]["description"] == "Leading the combat team", "the 'Skills:' line isn't part of the description"
    assert (jobs[1]["start"], jobs[1]["end"]) == ("Sep 2019", "Feb 2023")
    assert (jobs[2]["start"], jobs[2]["end"], jobs[2]["location"]) == ("Jul 2018", "Aug 2019", "Southam, England, United Kingdom")
    assert jobs[2]["description"] == "Racing physics tools and UI.", "'see more' isn't copied"
    assert (f["current_title"], f["current_company"]) == ("Lead Gameplay Programmer", "Rare")
    assert (f["highest_qualification"], f["degree_subject"], f["university"]) == ("BSc", "Computer Science", "University of Warwick")
    assert f["skills"] == "C++, Unreal Engine, Gameplay Programming", "the same skill twice is listed once"
    assert f["linkedin"] == "https://www.linkedin.com/in/sarah-test/"
    assert int(f["years_experience"]) >= 7


def test_an_empty_page_gives_nothing():
    assert jf.linkedin_from_page({}) == {}
    assert jf.linkedin_from_page({"name": "", "experience": ["junk", {"lines": []}]}) == {}


class LinkHandOverTests(AppTestCase):
    def ext(self, path, body=None):
        headers = {"X-JobFinder-Key": jf.pairing_code()}
        if body is None:
            return self.app.get(path, headers=headers)
        return self.app.post(path, body, headers=headers)

    def setup_method(self):
        super().setup_method()
        jf.li_link.update(url="", at=0.0, found=None, error="")

    def test_link_is_opened_and_read_back(self):
        with mock.patch.object(jf, "open_in_chrome", return_value=True) as chrome:
            code, r = self.app.post("/api/linkedin/link", {"url": "linkedin.com/in/sarah-test?trk=x"})
        assert code == 200 and r["chrome"] is True
        chrome.assert_called_once_with("https://www.linkedin.com/in/sarah-test/")
        assert self.app.get("/api/linkedin/link")[1]["waiting"] is True
        # the extension asks which page to read, then sends what it saw
        assert self.ext("/ext/linkedin/wanted")[1]["url"] == "https://www.linkedin.com/in/sarah-test/"
        assert self.ext("/ext/linkedin", {"page": LI_PAGE})[0] == 200
        st = self.app.get("/api/linkedin/link")[1]
        assert st["waiting"] is False and st["found"]["first_name"] == "Sarah"
        assert self.ext("/ext/linkedin/wanted")[1]["url"] == "", "nothing more to read"
        # the app clears it once it has shown you what was found
        self.app.post("/api/linkedin/link", {"cancel": True})
        assert self.app.get("/api/linkedin/link")[1]["found"] is None

    def test_sign_in_problem_is_reported(self):
        with mock.patch.object(jf, "open_in_chrome", return_value=True):
            self.app.post("/api/linkedin/link", {"url": "https://www.linkedin.com/in/sarah-test/"})
        self.ext("/ext/linkedin", {"error": "Sign in to LinkedIn in Chrome first"})
        st = self.app.get("/api/linkedin/link")[1]
        assert (st["waiting"], st["error"]) == (False, "Sign in to LinkedIn in Chrome first")

    def test_bad_links_and_unasked_pages_are_refused(self):
        with mock.patch.object(jf, "open_in_chrome") as chrome:
            code, r = self.app.post("/api/linkedin/link", {"url": "https://www.linkedin.com/company/rare"})
        assert code == 400 and "linkedin.com/in/" in r["error"]
        chrome.assert_not_called()
        assert self.ext("/ext/linkedin", {"page": LI_PAGE})[0] == 409, "a page nobody asked for is ignored"
        assert self.app.get("/api/linkedin/link")[1]["found"] is None

    def test_extension_needs_the_pairing_code(self):
        assert self.app.get("/ext/linkedin/wanted")[0] == 401
        assert self.app.post("/ext/linkedin", {"page": LI_PAGE})[0] == 401

    def test_old_requests_expire(self):
        with mock.patch.object(jf, "open_in_chrome", return_value=True):
            self.app.post("/api/linkedin/link", {"url": "https://www.linkedin.com/in/sarah-test/"})
        jf.li_link["at"] -= jf.LI_LINK_WAIT + 1
        assert self.ext("/ext/linkedin/wanted")[1]["url"] == ""
        assert self.app.get("/api/linkedin/link")[1]["waiting"] is False


# a page laid out like a LinkedIn profile (text shown twice: once for screen readers, once on screen)
def item(*lines, inner=""):
    spans = "".join(f'<div><span aria-hidden="true">{ln}</span><span class="visually-hidden">{ln}</span></div>' for ln in lines)
    return f"<li>{spans}{inner}</li>"


FAKE_PROFILE = f"""
<main>
  <section><h1>Sarah de Vries</h1><div>Gameplay Programmer at Rare | C++ | Unreal</div>
    <span>Coventry, England, United Kingdom</span> <a>Contact info</a></section>
  <section><div id="experience"></div><h2><span aria-hidden="true">Experience</span></h2><ul>
    {item("Rare", "Full-time · 6 yrs 2 mos", "Twycross, England, United Kingdom",
          inner="<ul>" + item("Lead Gameplay Programmer", "Mar 2023 - Present · 2 yrs 8 mos",
                              inner="<ul>" + item("Leading the combat team") + "</ul>")
                + item("Gameplay Programmer", "Sep 2019 - Feb 2023 · 3 yrs 6 mos") + "</ul>")}
    {item("Junior Programmer", "Codemasters · Full-time", "Jul 2018 - Aug 2019 · 1 yr 2 mos",
          inner="<ul>" + item("Racing physics tools and UI.") + "</ul>")}
  </ul></section>
  <section><div id="education"></div><h2><span aria-hidden="true">Education</span></h2><ul>
    {item("University of Warwick", "BSc (Hons), Computer Science", "2014 - 2017")}</ul></section>
  <section><div id="skills"></div><h2><span aria-hidden="true">Skills</span></h2><ul>
    {item("C++", inner="<ul>" + item("12 endorsements") + "</ul>")}{item("Unreal Engine")}</ul></section>
</main>
"""


def test_extension_reads_a_linkedin_style_page():
    chrome = find_chrome()
    if not chrome:
        pytest.skip("Chrome isn't installed, so the page-reading test can't run")
    work = Path(TMP) / "linkedin-page"
    work.mkdir(parents=True, exist_ok=True)
    shutil.copy(ROOT / "chrome-extension" / "content.js", work / "content.js")
    stub = "window.chrome={runtime:{lastError:null,onMessage:{addListener(){}},sendMessage(m,cb){setTimeout(()=>cb&&cb(null),0)}}};"
    run = ("window.addEventListener('load',()=>{document.getElementById('out').textContent="
           "JSON.stringify(window.__jobFinderTest.scrapeLinkedIn())});")
    (work / "page.html").write_text(f"<!doctype html><html><head><meta charset='utf-8'><script>{stub}</script></head>"
                                    f"<body>{FAKE_PROFILE}<pre id='out'></pre><script src='content.js'></script>"
                                    f"<script>{run}</script></body></html>", encoding="utf-8")
    proc = subprocess.run([chrome, "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
                           f"--user-data-dir={work / 'chrome-profile'}", "--allow-file-access-from-files",
                           "--virtual-time-budget=5000", "--dump-dom", (work / "page.html").as_uri()],
                          capture_output=True, timeout=120)
    m = re.search(r'<pre id="out">(.*?)</pre>', proc.stdout.decode("utf-8", "replace"), re.S)
    assert m and m.group(1).strip(), "the page didn't report back: " + proc.stderr.decode("utf-8", "replace")[-500:]
    page = json.loads(html.unescape(m.group(1)))
    assert page["name"] == "Sarah de Vries"
    assert page["skills"] == ["C++", "Unreal Engine"], "skill names only, not the endorsements"
    f = jf.linkedin_from_page({**page, "url": "https://www.linkedin.com/in/sarah-test/"})
    assert [(j["title"], j["company"], j["start"], j["end"]) for j in f["jobs"]] == [
        ("Lead Gameplay Programmer", "Rare", "Mar 2023", "Present"),
        ("Gameplay Programmer", "Rare", "Sep 2019", "Feb 2023"),
        ("Junior Programmer", "Codemasters", "Jul 2018", "Aug 2019")]
    assert f["jobs"][0]["description"] == "Leading the combat team"
    assert f["jobs"][2]["description"] == "Racing physics tools and UI."
    assert (f["city"], f["university"], f["degree_subject"]) == ("Coventry", "University of Warwick", "Computer Science")
