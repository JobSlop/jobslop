"""The Chrome extension, end to end, plus its Node.js logic tests.

1. A practice application form is opened in Chrome (headless, nothing appears on screen) with the
   real extension script and a test profile; the test then checks what was typed, picked and ticked.
2. tests/extension.test.js (the extension's matching rules and the app screen's script syntax)
   is run with Node.js.
Each part is skipped, with a note, if Chrome or Node.js isn't installed.
"""
import pytest
import html
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from support import ROOT, TMP

PROFILE = {
    "first_name": "Sarah", "middle_name": "Jane", "last_name": "de Vries", "email": "sarah@example.com",
    "phone": "07911 123456", "address1": "12 Elm Grove", "city": "Coventry", "postcode": "CV1 2AB",
    "county": "West Midlands", "country": "United Kingdom", "linkedin": "https://linkedin.com/in/sarah",
    "right_to_work": "Yes", "needs_sponsorship": "No", "over_18": "Yes", "years_experience": "4",
    "highest_qualification": "BSc", "notice_period": "1 month", "auto_consent": "yes",
    "jobs": [{"title": "Gameplay Programmer", "company": "Rare", "start": "Mar 2021", "end": "Present"}],
}

FORM = """
<form>
  <label>First name <input id="fn"></label>
  <label>Tussenvoegsel <input id="prefix"></label>
  <label>Achternaam <input id="ln"></label>
  <label>Email address <input id="email" type="email"></label>
  <label>Mobile phone <input id="phone"></label>
  <label>Postcode <input id="pc"></label>
  <label>Town / City <input id="city" value="Already typed"></label>
  <label>Country
    <select id="country"><option value="">Please select</option><option value="nl">Netherlands</option>
      <option value="gb">United Kingdom</option></select></label>
  <label>Years of experience
    <select id="years"><option value="">Choose</option><option value="a">0-2 years</option>
      <option value="b">3-5 years</option><option value="c">6+ years</option></select></label>
  <label>Highest level of education
    <select id="edu"><option value="">Select</option><option value="g">GCSE</option>
      <option value="b">Bachelor's degree</option><option value="m">Master's degree</option></select></label>
  <label>Gender <select id="gender"><option value="">Select</option><option>Female</option><option>Male</option></select></label>
  <fieldset><legend>Do you have the right to work in the UK?</legend>
    <label><input type="radio" name="rtw" id="rtw_yes" value="y"> Yes</label>
    <label><input type="radio" name="rtw" id="rtw_no" value="n"> No</label></fieldset>
  <fieldset><legend>Will you require visa sponsorship?</legend>
    <label><input type="radio" name="spon" id="spon_yes" value="y"> Yes</label>
    <label><input type="radio" name="spon" id="spon_no" value="n"> No</label></fieldset>
  <label><input type="checkbox" id="over18"> I confirm I am 18 years or older</label>
  <label><input type="checkbox" id="privacy"> I agree to the privacy policy</label>
  <label><input type="checkbox" id="news"> Send me the newsletter and job alerts</label>
  <label>Cover letter <textarea id="letter"></textarea></label>
  <button type="submit" id="submit">Submit application</button>
</form>
"""


def find_chrome():
    candidates = []
    if sys.platform.startswith("win"):
        for var in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
            if os.environ.get(var):
                candidates.append(Path(os.environ[var]) / "Google" / "Chrome" / "Application" / "chrome.exe")
        # the tests change LOCALAPPDATA-like variables for the data folder, so also try the usual places
        candidates += [Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
                       Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
                       Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")]
    elif sys.platform == "darwin":
        candidates.append(Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"))
    else:
        candidates += [Path(p) for p in ("/usr/bin/google-chrome", "/usr/bin/chromium", "/usr/bin/chromium-browser")]
    return next((str(c) for c in candidates if c.is_file()), None)


class ExtensionFillTests:
    @classmethod
    def setup_class(cls):
        chrome = find_chrome()
        if not chrome:
            pytest.skip("Chrome isn't installed, so the form-filling test can't run")
        work = Path(TMP) / "extension-form"
        work.mkdir(exist_ok=True)
        shutil.copy(ROOT / "chrome-extension" / "content.js", work / "content.js")
        stub = ("window.chrome={runtime:{lastError:null,onMessage:{addListener(){}},sendMessage(msg,cb){"
                "const r=msg.type==='getData'?" + json.dumps({"profile": PROFILE, "full_name": "Sarah de Vries",
                                                              "cover_letter": "Dear Rare, ..."}) +
                ":null;setTimeout(()=>cb&&cb(r),0)}}};")
        run = ("window.addEventListener('load',async()=>{const r=await window.__jobFinderTest.fill();"
               "const out={result:r};document.querySelectorAll('input,select,textarea').forEach(e=>{"
               "out[e.id]=e.type==='checkbox'||e.type==='radio'?e.checked:e.value});"
               "document.getElementById('out').textContent=JSON.stringify(out);"
               "document.getElementById('submit').dataset.clicked=String(!!window.__submitted)});"
               "document.addEventListener('submit',e=>{window.__submitted=true;e.preventDefault()});")
        page = (f"<!doctype html><html lang='en'><head><meta charset='utf-8'><script>{stub}</script></head><body>"
                f"{FORM}<pre id='out'></pre><script src='content.js'></script><script>{run}</script></body></html>")
        (work / "form.html").write_text(page, encoding="utf-8")
        profile_dir = work / "chrome-profile"
        proc = subprocess.run([chrome, "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
                               f"--user-data-dir={profile_dir}", "--allow-file-access-from-files",
                               "--virtual-time-budget=20000", "--dump-dom", (work / "form.html").as_uri()],
                              capture_output=True, timeout=120)
        dom = proc.stdout.decode("utf-8", "replace")
        m = re.search(r'<pre id="out">(.*?)</pre>', dom, re.S)
        if not m or not m.group(1).strip():
            raise AssertionError("the form page didn't report back; Chrome said: " + proc.stderr.decode("utf-8", "replace")[-800:])
        cls.out = json.loads(html.unescape(m.group(1)))
        cls.dom = dom

    def test_text_boxes(self):
        o = self.out
        assert (o["fn"], o["email"], o["phone"], o["pc"]) == ("Sarah", "sarah@example.com", "07911 123456", "CV1 2AB")

    def test_dutch_name_prefix(self):
        """'de Vries' is split into tussenvoegsel 'de' and achternaam 'Vries' on Dutch forms."""
        assert (self.out["prefix"], self.out["ln"]) == ("de", "Vries")

    def test_never_overwrites_your_typing(self):
        assert self.out["city"] == "Already typed"

    def test_drop_downs(self):
        assert (self.out["country"], self.out["years"], self.out["edu"]) == ("gb", "b", "b")

    def test_personal_questions_left_alone(self):
        assert self.out["gender"] == ""

    def test_radio_buttons(self):
        assert self.out["rtw_yes"]
        assert not self.out["rtw_no"]
        assert self.out["spon_no"]
        assert not self.out["spon_yes"]

    def test_tick_boxes(self):
        assert self.out["over18"], "a fact that's true for you is ticked"
        assert self.out["privacy"], "privacy boxes are ticked only because the profile allows it"
        assert not self.out["news"], "marketing / newsletter boxes are never ticked"

    def test_cover_letter(self):
        assert self.out["letter"] == "Dear Rare, ..."

    def test_never_submits(self):
        assert 'data-clicked="false"' in self.dom
        assert self.out["result"]["n"] >= 12


class NodeLogicTests:
    def test_extension_logic_with_node(self):
        node = shutil.which("node")
        if not node:
            pytest.skip("Node.js isn't installed, so tests/extension.test.js can't run")
        proc = subprocess.run([node, "--test", str(ROOT / "tests" / "extension.test.js")], capture_output=True, timeout=120)
        out = proc.stdout.decode("utf-8", "replace")
        assert proc.returncode == 0, "Node tests failed:\n" + "\n".join(
            ln for ln in out.splitlines() if ln.startswith(("not ok", "#")) or "error" in ln.lower())[-3000:]
