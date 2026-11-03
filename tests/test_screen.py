"""The app screen itself (ui.html), in headless Chrome against the real app server with fake job boards.

Checks a full search with an address in "Where?", every sort order, every filter, tab switching,
and the 📍 Mine button reading the profile address. Skipped if Chrome isn't installed.
"""
import html
import json
import os
import re
import subprocess
import webbrowser
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

import pytest
from support import TMP, AppServer, FakeBoards, make_job, no_internet, reset_data
from test_extension import find_chrome
from test_linkedin_link import LI_PAGE

from jobslop import net, runtime, settings
from jobslop.profile import linkedin_link
from jobslop.profile import store as pstore
from jobslop.server import handler


def day(n):
    return (datetime.now() - timedelta(days=n)).strftime("%Y-%m-%d")


# what the fake boards return (the server adds score, distance and contract length as usual)
BOARD_JOBS = {
    "LinkedIn": [make_job("LinkedIn", "Games Programmer", "Rare", "Birmingham, UK", date=day(1), salary="£40k–£50k",
                          desc="Permanent role", remote=False),
                 make_job("LinkedIn", "Senior Games Programmer", "Sumo", "Coventry, UK", date=day(10), salary="£60k",
                          desc="6 month contract", remote=False)],
    "Arbeitnow": [make_job("Arbeitnow", "Games Programmer Intern", "Tiny Fox", "Birmingham, UK", date=day(3),
                           desc="12 month placement internship", remote=False),
                  make_job("Arbeitnow", "Games Programmer", "Far Away Ltd", "Manchester, UK", date=day(2), remote=False),
                  make_job("Arbeitnow", "Games Programmer", "Remote Co", "Remote · United Kingdom", date=day(5),
                           salary="£30k"),
                  # not open to people in the UK, and the title doesn't contain the search words
                  make_job("Arbeitnow", "Game Developer", "Asia Co", "Remote · Philippines", date=day(4),
                           desc="games programmer wanted")],
}

HARNESS = r"""
<script>
window.addEventListener("load", () => setTimeout(async () => {
  const out = {};
  const titles = () => visible(results, false).map(j => j.company);
  try {
    // 1. a real search with a full address in "Where?"
    $("#q").value = "games programmer";
    $("#where").value = "12 Colmore Row, Birmingham B3 2BJ";
    $$(".sc").forEach(c => c.checked = ["LinkedIn", "Arbeitnow"].includes(c.value));
    await runSearch();
    out.searchCount = results.length;
    out.status = $("#status").innerText;
    out.hint = $("#wherehint").hidden ? "" : $("#wherehint").textContent;
    out.country = $("#country").value;
    out.listRows = $$("#list .jobrow").length;
    out.distanceShown = $("#list").innerText.includes("away");
    out.durationShown = $("#list").innerText.includes("⏳");
    // 2. every sort order
    out.sorts = {};
    for (const o of [...$("#sort").options]) { $("#sort").value = o.value; out.sorts[o.value] = titles(); }
    $("#sort").value = "score";
    // 3. filters
    const f = {};
    const tryFilter = (name, set, reset) => { set(); f[name] = titles(); reset(); };
    tryFilter("perm", () => $("#durfilter").value = "perm", () => $("#durfilter").value = "");
    tryFilter("short", () => $("#durfilter").value = "short", () => $("#durfilter").value = "");
    tryFilter("intern", () => $("#jtype").value = "internship", () => $("#jtype").value = "");
    tryFilter("remote", () => $("#remote").value = "remote", () => $("#remote").value = "");
    tryFilter("hassal", () => $("#hassal").checked = true, () => $("#hassal").checked = false);
    tryFilter("salmin", () => $("#salmin").value = "45000", () => $("#salmin").value = "");
    tryFilter("exclude", () => $("#exclude").value = "senior, intern", () => $("#exclude").value = "");
    tryFilter("posted", () => $("#posted").value = "3", () => $("#posted").value = "0");
    tryFilter("text", () => $("#filter").value = "sumo", () => $("#filter").value = "");
    tryFilter("nolocal", () => $("#local").checked = false, () => $("#local").checked = true);
    tryFilter("nolocalStrict", () => { $("#local").checked = false; $("#strict").checked = true; },
              () => { $("#local").checked = true; $("#strict").checked = false; });
    out.filters = f;
    // 3b. the 🎓 Internships button searches for internships and turns on the Job type filter
    $("#internbtn").click();
    await new Promise(r => setTimeout(r, 4000));
    out.internFilter = $("#jtype").value;
    out.internVisible = titles();
    out.internTotal = results.length;
    $("#jtype").value = "";
    // 4. tabs: the big welcome header shrinks away from Search
    setTab("tracker");
    out.boardEmpty = !$("#boardempty").hidden;
    out.trackerCompact = document.querySelector(".hero").classList.contains("compact");
    out.trackerTitle = document.title;
    setTab("search");
    out.searchCompact = document.querySelector(".hero").classList.contains("compact");
    // 5. save a job, then the tracker shows it
    await track("save", visible(results, false)[0]);
    out.saved = (await get("/api/saved")).map(j => j.company);
    // 5b. Save and Applied can be clicked again to undo them
    const row = () => $("#list .jobrow");
    const label = (sel) => (row().querySelector(sel) || {}).textContent || "";
    out.savedButton = label("[data-unsave]");
    row().querySelector("[data-applied]").click();
    await new Promise(r => setTimeout(r, 600));
    out.appliedButton = label("[data-unapply]");
    out.statusAfterApply = tracked(visible(results, false)[0].url).status;
    row().querySelector("[data-unapply]").click();
    await new Promise(r => setTimeout(r, 600));
    out.statusAfterUnapply = tracked(visible(results, false)[0].url).status;
    out.applyButtonBack = label("[data-applied]");
    row().querySelector("[data-unsave]").click();
    await new Promise(r => setTimeout(r, 600));
    out.saveButtonBack = label("[data-save]");
    out.savedAfterUnsave = (await get("/api/saved")).length;
    $("#toast button").click();                       // Undo
    await new Promise(r => setTimeout(r, 600));
    out.savedAfterUndo = (await get("/api/saved")).length;
    // 6. 📍 Mine reads the whole profile address
    $("#where").value = "";
    $("#locbtn").click();
    await new Promise(r => setTimeout(r, 1500));
    out.mine = $("#where").value;
    out.mineCountry = $("#country").value;
    const wait = (ms) => new Promise(r => setTimeout(r, ms));
    // 7. Ctrl+Z undoes the last change; the undo button says what it will undo
    const before7 = (await get("/api/saved")).length;
    await track("save", visible(results, false)[1]);
    out.undoTip = $("#undobtn").dataset.tip;
    out.undoEnabled = !$("#undobtn").disabled;
    document.body.dispatchEvent(new KeyboardEvent("keydown", {key: "z", ctrlKey: true, bubbles: true}));
    await wait(800);
    out.undoCounts = [before7, (await get("/api/saved")).length];
    // 8. the logo goes back to Search
    setTab("profile");
    $("#home").click();
    out.logoTab = tab;
    // 9. labels float above everything, also in the slim header; title= text becomes a label too
    setTab("tracker");
    $("#themebtn").dispatchEvent(new MouseEvent("mouseover", {bubbles: true}));
    await wait(500);
    const tb = $("#tip").getBoundingClientRect();
    out.tip = {text: $("#tip").textContent, on: $("#tip").classList.contains("on"), inBody: $("#tip").parentElement === document.body,
               fixed: getComputedStyle($("#tip")).position, below: tb.top >= $("#themebtn").getBoundingClientRect().bottom,
               inside: tb.left >= 0 && tb.right <= innerWidth && tb.top >= 0 && tb.bottom <= innerHeight};
    document.body.dispatchEvent(new MouseEvent("mouseover", {bubbles: true}));
    setTab("search");
    $("#anybtn").dispatchEvent(new MouseEvent("mouseover", {bubbles: true}));
    await wait(500);
    out.titleTip = $("#tip").textContent;
    document.dispatchEvent(new KeyboardEvent("keydown", {key: "Escape", bubbles: true}));
    out.tipAfterEscape = $("#tip").classList.contains("on");
    // 10. getting-started list: what's left (the extension isn't connected in this test)
    out.started = {shown: !$("#getstarted").hidden, count: $("#gscount").textContent,
                   left: $$("#gslist li:not(.done)").map(li => li.textContent)};
    // 11. an offer: a thank-you window with an email ready to check and send
    const jo = visible(results, false)[0];
    await track("applied", jo);
    await moveTo(tracked(jo.url), "Offer");
    out.offerOpen = $("#m-offer").classList.contains("open");
    out.offerMail = $("#offermail").value;
    out.offerJob = [jo.title, jo.company, jo.location];
    $("#offersend").click();
    await wait(600);
    out.offerClosed = !$("#m-offer").classList.contains("open");
    // 12. LinkedIn link: opened in Chrome, then what the extension read is offered for the profile
    setTab("profile"); await loadProfile();
    $("#fromli").click();
    $("#liurl").value = "https://www.linkedin.com/in/sarah-test/";
    $("#ligo").click();
    await wait(800);
    out.liStatus = $("#listatus").textContent;
    await fetch("/harness/lifound");
    await wait(3500);
    out.liImportOpen = $("#m-import").classList.contains("open");
    out.liImportText = $("#impsub").textContent;
    $("#impadd").click();
    await wait(800);
    out.liJobs = ((await get("/api/profile")).profile.jobs || []).map(j => j.company);
    $("#undobtn").click();
    await wait(800);
    out.liJobsAfterUndo = ((await get("/api/profile")).profile.jobs || []).length;
    // 13. results come in pages
    setTab("search");
    const real = results;
    results = Array.from({length: 60}, (_, k) => ({...real[0], url: real[0].url + "#" + k, title: "Games Programmer " + k}));
    $("#perpage").value = "25"; $("#perpage").dispatchEvent(new Event("change"));
    const num = () => ($("#list .jobrow .num") || {}).textContent;
    out.pages = {rows: $$("#list .jobrow").length, shown: !$("#pager").hidden, text: $("#pager .muted").textContent,
                 buttons: $$("#pager [data-page]").map(b => b.textContent.trim())};
    $("#pager [aria-label='Next page']").click();
    out.pages.second = [num(), $$("#list .jobrow").length, $("#pager .muted").textContent];
    $("#pager [data-page='3']").click();
    out.pages.third = [num(), $$("#list .jobrow").length];
    $("#filter").value = "programmer 5"; $("#filter").dispatchEvent(new Event("input"));
    out.pages.afterFilter = [num(), $("#pager").hidden];
    $("#filter").value = ""; $("#filter").dispatchEvent(new Event("input"));
    $("#perpage").value = "0"; $("#perpage").dispatchEvent(new Event("change"));
    out.pages.all = [$$("#list .jobrow").length, $("#pager").hidden];
    $("#perpage").value = "25"; $("#perpage").dispatchEvent(new Event("change"));
    results = real; render();
    // 14. a new version: the bar offers it (GitHub isn't asked in this test)
    upd = {enabled: true, current: "2.0.0", version: "2.1.0", available: true, can_install: true, notes: "New things", skipped: false};
    drawUpdBar();
    $("#updicon").click();
    out.updBar = {shown: !$("#updicon").hidden, tip: $("#updicon").dataset.tip, open: $("#updpop").classList.contains("open"),
                  text: $("#updpop").textContent.replace(/\s+/g, " ").trim(),
                  buttons: $$("#updpop button").map(b => b.textContent.trim())};
    updPhase = "dl"; updPct = 40; drawUpdBar();
    out.updDownloading = [$("#updicon").classList.contains("dl"), $("#updicon").dataset.tip, $("#updgo").disabled];
    updPhase = "ready"; drawUpdBar();
    out.updReady = [$("#updicon").classList.contains("ready"), $("#updicon").textContent, $("#updgo").textContent.trim()];
    updPhase = ""; drawUpdBar();
    document.body.click();
    out.updClosedOutside = !$("#updpop").classList.contains("open");
    $("#updicon").click();
    $("#updnotes").click();
    out.updNotes = [$("#wntitle").textContent, $("#wnnotes").textContent, $("#m-whatsnew").classList.contains("open")];
    closeModals();
    upd = null; drawUpdBar();
    // 15. hover labels on things that aren't obvious
    await track("save", visible(results, false)[2]);
    setTab("progress");
    const tileTip = (name) => ($$("#tiles .tile").find(t => t.querySelector(".l").textContent === name) || {dataset: {}}).dataset.tip;
    setTab("tracker");
    out.tips = {tab: $('.tab[data-tab="tracker"]').dataset.tip, hassal: $("#hassal").closest("label").dataset.tip,
                csv: $("#csv").dataset.tip, streak: (setTab("progress"), tileTip("Day streak")),
                move: (setTab("tracker"), ($("[data-move]") || {dataset: {}}).dataset.tip),
                edit: ($("[data-edit]") || {dataset: {}}).dataset.tip, strip: $("#strip > div").dataset.tip};
    $("#hassal").dispatchEvent(new MouseEvent("mouseover", {bubbles: true}));
    await wait(500);
    out.tips.shown = $("#tip").classList.contains("on") ? $("#tip").textContent : "";
    setTab("search");
    // 16. plugins: Settings lists them with their key boxes; switching one off takes its boards away
    plugOpen.add("country-boards");
    openSettings("plugins"); await loadPlugins();
    out.settingsTabs = {shown: $$(".setpane > section").filter(s => !s.hidden).map(s => s.dataset.set),
                        nav: $$("#setnav button").map(b => b.textContent)};
    const accChips = () => $$(".sc").map(c => c.value).filter(v => ["ICAEW", "ACCA"].includes(v));
    out.plugins = {cards: $$("#plugs .prow .pname").map(e => e.firstChild.textContent.trim()),
                   keyBoxes: $$('.prow[data-id="country-boards"] .pset').map(i => i.dataset.key),
                   folded: $$(".prow").filter(r => r.querySelector(".pbody").hidden).map(r => r.dataset.id).includes("accounting"),
                   ticks: $$(".prow .plugsw").every(c => c.type === "checkbox")};
    $('.prow[data-id="accounting"] .pfold').click();
    out.plugins.unfolds = !$('.prow[data-id="accounting"] .pbody').hidden;
    $("#plugonly").checked = true; $("#plugonly").dispatchEvent(new Event("change"));
    out.plugins.enabledOnly = $$(".prow").every(r => r.classList.contains("on"));
    $("#plugonly").checked = false; $("#plugonly").dispatchEvent(new Event("change"));
    $("#plugfind").value = "remote"; $("#plugfind").dispatchEvent(new Event("input"));
    out.plugins.found = $$(".prow").map(r => r.dataset.id);
    $("#plugfind").value = ""; $("#plugfind").dispatchEvent(new Event("input"));
    showSettings("help");
    out.settingsTabs.help = $$(".setpane > section").filter(s => !s.hidden).map(s => s.dataset.set);
    showSettings("plugins");
    await togglePlugin("accounting", false);
    out.plugins.chipsOff = accChips();
    out.plugins.cardOff = $('.plugsw[data-id="accounting"]').checked;
    await togglePlugin("accounting", true);
    out.plugins.chipsOn = accChips();
    out.plugins.cardOn = $('.plugsw[data-id="accounting"]').checked;
    await previewPlugin("https://gitlab.com/someone/plugin");
    out.plugins.badLink = $("#plugmsg").textContent;
    out.plugins.installOpen = $("#m-plugin").classList.contains("open");
    out.plugins.removable = $$(".plugrm").length;
    closeModals();
    // 17. what plugins add to the screen: a tab, a map layer, a Progress card, profile fields — and all gone when off
    const until = async (ok) => { for (let i = 0; i < 40 && !ok(); i++) await new Promise(r => setTimeout(r, 100)); return ok(); };
    await togglePlugin("gamedev", true);
    const tabBtn = () => $('.navlinks .tab[data-tab="p-gamedev-studios"]');
    out.pluginUi = {tabShown: !!(await until(tabBtn))};
    out.pluginUi.tabText = tabBtn() ? tabBtn().textContent : "";
    setTab("p-gamedev-studios");
    out.pluginUi.tabTitle = document.title;
    out.pluginUi.tabHeading = ($("#v-p-gamedev-studios h2") || {}).textContent;
    out.pluginUi.layer = $$("#maplayers label").map(l => l.textContent.trim());
    setTab("progress");
    out.pluginUi.cards = $$("#plugcards h3").map(h => h.textContent);
    setTab("profile");
    out.pluginUi.fields = $$("#pfields .psec").map(s => s.textContent);
    out.pluginUi.engines = !!$("#pfields #engines");
    await togglePlugin("gamedev", false);
    out.pluginUi.after = {tab: !!tabBtn(), section: !!$("#v-p-gamedev-studios"), layer: $$("#maplayers label").length,
                          cards: $$("#plugcards h3").map(h => h.textContent), engines: !!$("#pfields #engines"),
                          style: !!$('style[data-plugin="gamedev"]')};
    setTab("search");
    // 18. another language: the screen changes, your data and saved answers don't, and English comes back
    results = real; render();
    const englishTitle = $("#list h3") ? $("#list h3").textContent : "";
    await chooseLanguage("nl");
    out.lang = {go: $("#go").textContent, tabs: $$(".navlinks .tab").map(b => b.textContent).slice(0, 4),
                placeholder: $("#q").placeholder, title: document.title, picker: $("#setlang").value,
                jobTitle: $("#list h3") ? $("#list h3").textContent : "", englishTitle};
    toast("Settings saved"); await new Promise(r => setTimeout(r, 50));
    out.lang.toast = $("#toast") ? $("#toast").textContent : "";
    setTab("profile");
    const yn = $("#right_to_work");
    out.lang.yesNo = yn ? [...yn.options].map(o => o.value + "=" + o.textContent) : [];
    setTab("search");
    await chooseLanguage("en");
    out.lang.back = {go: $("#go").textContent, placeholder: $("#q").placeholder, tab: $$(".navlinks .tab")[0].textContent};
    await togglePlugin("lang-nl", false);
  } catch (e) { out.error = String(e && e.stack || e); }
  out.loadErrors = window.__loadErrors;
  document.getElementById("selftest").textContent = JSON.stringify(out);
}, 800));
</script><pre id="selftest"></pre>
"""


# put first in <head>: records any error while the screen's script files load (they share one page)
CATCH_LOAD_ERRORS = ('<script>window.__loadErrors=[];addEventListener("error",e=>__loadErrors.push('
                     '(e.filename||"").split("/").pop()+": "+e.message))</script>')


class HarnessHandler(handler.Handler):
    """The normal app server, plus /harness: the app screen with the test script added."""

    def do_GET(self):
        if self.path == "/harness":
            page = handler.load_page().replace("<head>", "<head>" + CATCH_LOAD_ERRORS, 1)
            return self.send(page.replace("</body>", HARNESS + "</body>"), "text/html")
        if self.path == "/harness/lifound":            # stands in for the extension reading the LinkedIn page
            linkedin_link.li_link["found"] = linkedin_link.linkedin_from_page(LI_PAGE)
            return self.send("{}")
        return super().do_GET()


class ScreenTests:
    @classmethod
    def setup_class(cls):
        chrome = find_chrome()
        if not chrome:
            pytest.skip("Chrome isn't installed, so the app screen test can't run")
        reset_data()
        pstore.save_profile({"first_name": "Sarah", "address1": "22 London Road", "city": "Coventry",
                         "postcode": "CV1 2AB", "country": "United Kingdom"})
        settings.update_settings(lambda s: s.update(ui={"tour_done": "1", "onboarded": "1"}))
        app = AppServer(HarnessHandler)
        runtime.state["port"] = app.port
        fake = FakeBoards(BOARD_JOBS)
        try:
            with fake.installed(), no_internet(), \
                    mock.patch.object(net, "get_json", side_effect=OSError("offline")), \
                    mock.patch.object(handler, "open_in_chrome", return_value=True) as open_chrome, \
                    mock.patch.object(os, "startfile", create=True) as startfile, \
                    mock.patch.object(webbrowser, "open") as browser,                     mock.patch("urllib.request.urlopen", side_effect=OSError("no internet in tests")):
                proc = subprocess.run([chrome, "--headless=new", "--disable-gpu", "--no-first-run",
                                       "--no-default-browser-check", f"--user-data-dir={Path(TMP) / 'chrome-screen'}",
                                       "--window-size=1300,900", "--virtual-time-budget=120000", "--dump-dom",
                                       f"http://127.0.0.1:{app.port}/harness"], capture_output=True, timeout=180)
        finally:
            app.close()
        dom = proc.stdout.decode("utf-8", "replace")
        m = re.search(r'<pre id="selftest">(.*?)</pre>', dom, re.S)
        if not m or not m.group(1).strip():
            raise AssertionError("the app screen didn't report back; Chrome said: " + proc.stderr.decode("utf-8", "replace")[-800:])
        cls.out = json.loads(html.unescape(m.group(1)))
        cls.fake = fake
        cls.opened = [str(c.args[0]) for c in startfile.call_args_list + browser.call_args_list]
        cls.chrome = [str(c.args[0]) for c in open_chrome.call_args_list]

    def test_no_script_errors(self):
        assert "error" not in self.out, self.out.get("error")
        assert self.out["loadErrors"] == [], "errors while the screen's files loaded"

    def test_search_with_an_address(self):
        o = self.out
        assert o["country"] == "GB"
        assert "Searching around Birmingham, B3 2BJ" in o["hint"]
        assert {c[2]["where"] for c in self.fake.calls if c[0] == "LinkedIn"} == {"Birmingham"}
        assert o["searchCount"] == 5, "everything is fetched, except the Manchester job outside the 15-mile radius"
        assert o["listRows"] == 4
        assert "LinkedIn: 2" in o["status"]
        assert o["distanceShown"]
        assert o["durationShown"]

    def test_sort_orders(self):
        s = self.out["sorts"]
        assert s["date"] == ["Rare", "Tiny Fox", "Remote Co", "Sumo"]
        assert s["old"] == s["date"][::-1]
        assert s["salary"][:3] == ["Sumo", "Rare", "Remote Co"]
        assert s["salary_lo"][:3] == ["Remote Co", "Rare", "Sumo"]
        assert s["company"] == sorted(s["company"])
        assert set(s["title"][:2]) == {"Rare", "Remote Co"} and s["title"][2:] == ["Tiny Fox", "Sumo"]   # A-Z by title
        assert s["dur_short"][0] == "Sumo", "the 6-month contract is the shortest"
        assert s["dur_long"][0] == "Rare", "permanent comes first"
        assert s["dist"][:2] == ["Rare", "Tiny Fox"], "Birmingham jobs are nearest"
        for name, order in s.items():
            assert len(order) == 4, f"sorting by {name} must not lose jobs"

    def test_filters(self):
        f = self.out["filters"]
        assert f["perm"] == ["Rare"]
        assert f["short"] == ["Sumo"]
        assert f["intern"] == ["Tiny Fox"]
        assert f["remote"] == ["Remote Co"]
        assert set(f["hassal"]) == {"Rare", "Sumo", "Remote Co"}
        assert set(f["salmin"]) == {"Rare", "Sumo", "Tiny Fox"}, "jobs without a salary stay unless 'Has salary'"
        assert set(f["exclude"]) == {"Rare", "Remote Co"}
        assert set(f["posted"]) == {"Rare", "Tiny Fox"}
        assert f["text"] == ["Sumo"]
        assert set(f["nolocal"]) == {"Rare", "Sumo", "Tiny Fox", "Remote Co", "Asia Co"}, \
            "unticking 'Workable from my country' shows the job that was only hidden"
        assert "Asia Co" not in f["nolocalStrict"], "'Title must match' hides titles without the search words"

    def test_internship_button(self):
        o = self.out
        assert o["internFilter"] == "internship"
        assert o["internVisible"] == ["Tiny Fox"], "the Job type filter hides the rest"
        assert o["internTotal"] >= 5, "but nothing was dropped from the list"
        asked = {(c[0], c[1]) for c in self.fake.calls}
        assert ("Arbeitnow", "games programmer internship") in asked
        assert ("LinkedIn", "games programmer") in asked, "LinkedIn has its own internship filter, so no extra word"

    def test_filters_never_search_again(self):
        plain = [c for c in self.fake.calls if c[1] == "games programmer"]
        assert len(plain) == 2, "one search per board; changing filters only hides or shows jobs"

    def test_tabs(self):
        assert self.out["trackerCompact"], "the welcome header is small on other tabs"
        assert not self.out["searchCompact"]
        assert "Tracker" in self.out["trackerTitle"]

    def test_saving_from_results(self):
        assert len(self.out["saved"]) == 1

    def test_save_and_applied_can_be_undone(self):
        o = self.out
        assert o["savedButton"] == "★ Saved"
        assert (o["appliedButton"], o["statusAfterApply"]) == ("✓ Applied", "Applied")
        assert o["statusAfterUnapply"] == "Saved", "clicking ✓ Applied again puts it back to Saved"
        assert o["applyButtonBack"] == "✓ Mark applied"
        assert (o["saveButtonBack"], o["savedAfterUnsave"]) == ("☆ Save", 0), "clicking ★ Saved again removes it"
        assert o["savedAfterUndo"] == 1, "Undo brings it back"

    def test_mine_button_uses_profile_address(self):
        assert self.out["mine"] == "Coventry, CV1 2AB"
        assert self.out["mineCountry"] == "GB"

    def test_tracker_starts_with_a_friendly_empty_state(self):
        assert self.out["boardEmpty"] is True

    def test_ctrl_z_undoes_the_last_change(self):
        o = self.out
        assert o["undoEnabled"] and o["undoTip"].startswith("Undo saving") and "Ctrl+Z" in o["undoTip"]
        assert o["undoCounts"][1] == o["undoCounts"][0], "the job saved just before Ctrl+Z is gone again"

    def test_logo_goes_to_search(self):
        assert self.out["logoTab"] == "search"

    def test_labels_sit_on_top_and_inside_the_window(self):
        t = self.out["tip"]
        assert (t["text"], t["on"], t["inBody"], t["fixed"]) == ("Light, dark and colours", True, True, "fixed")
        assert t["below"], "the label sits just under the button, in a layer above the header (not cut off by it)"
        assert t["inside"], "the label is never pushed off the edge of the window"
        assert self.out["titleTip"] == "Search every job in the area", "hover text from title= uses the same label"
        assert self.out["tipAfterEscape"] is False, "Esc hides it"

    def test_getting_started_list(self):
        st = self.out["started"]
        assert st["shown"] and st["count"] == "4 of 5 done"
        assert st["left"] == ["5Set up Easy apply (Chrome)"]

    def test_offer_thank_you_and_email(self):
        o = self.out
        assert o["offerOpen"] and o["offerClosed"]
        assert "Good news - I got an offer!" in o["offerMail"] and "Days from applying to the offer:" in o["offerMail"]
        mails = [u for u in self.opened if u.startswith("mailto:")]
        assert len(mails) == 1 and mails[0].startswith("mailto:jobslop@proton.me?subject=jobslop%3A%20I%20got%20an%20offer")
        from urllib.parse import unquote
        sent = unquote(mails[0])
        assert "Used Easy apply for this one:" in sent and "Applications sent:" in sent
        for detail in o["offerJob"] + ["Sarah", "Coventry", "LinkedIn", "Arbeitnow"]:
            assert detail not in sent and detail not in o["offerMail"], f"the email is anonymous: {detail!r} isn't in it"

    def test_results_come_in_pages(self):
        p = self.out["pages"]
        assert (p["rows"], p["shown"], p["text"]) == (25, True, "Showing 1–25 of 60")
        assert p["buttons"] == ["‹ Prev", "1", "2", "3", "Next ›"]
        assert p["second"] == ["26.", 25, "Showing 26–50 of 60"], "numbering carries on across pages"
        assert p["third"] == ["51.", 10]
        assert p["afterFilter"][0] == "01.", "changing a filter goes back to page 1"
        assert p["all"] == [60, True], "'All' shows everything on one page"

    def test_hover_labels(self):
        t = self.out["tips"]
        assert t["tab"] == "Every job you've saved or applied to, by stage"
        assert t["hassal"] == t["shown"] == "Hide jobs that don't list a salary", "tick boxes: the label sits on the whole tick box"
        assert t["csv"].startswith("Save the results") and t["strip"] == "Open your progress"
        assert t["streak"] == "Days in a row you've applied to at least one job"
        assert t["move"] and t["edit"].startswith("Status, dates"), "tracker card buttons explain themselves"

    def test_update_bar(self):
        u = self.out["updBar"]
        assert u["shown"] and u["open"] and u["tip"] == "Update available — jobslop 2.1.0"
        assert "Update available" in u["text"] and "jobslop 2.1.0" in u["text"] and "You have 2.0.0." in u["text"]
        assert u["buttons"] == ["What's new", "Skip", "Update now"]
        assert self.out["updDownloading"] == [True, "Downloading jobslop 2.1.0… 40%", True], "the icon fills up while downloading"
        assert self.out["updReady"] == [True, "↻", "Restart to finish"]
        assert self.out["updClosedOutside"], "clicking elsewhere closes the panel"
        assert self.out["updNotes"] == ["What's new in jobslop 2.1.0", "New things", True]

    def test_linkedin_link_import(self):
        o = self.out
        assert "Opened in Chrome" in o["liStatus"]
        assert self.chrome == ["https://www.linkedin.com/in/sarah-test/"]
        assert o["liImportOpen"] and "your LinkedIn profile" in o["liImportText"]
        assert o["liJobs"] == ["Rare", "Rare", "Codemasters"]
        assert o["liJobsAfterUndo"] == 0, "Undo takes the import back out"

    def test_plugins_in_settings(self):
        pl = self.out["plugins"]
        assert {"Accounting", "Artists", "Country boards", "Game dev", "Remote boards"} <= set(pl["cards"])
        assert {"reed_key", "adzuna_id", "adzuna_key", "usajobs_key", "usajobs_email"} <= set(pl["keyBoxes"]), "keys sit in their plugin's fold"
        assert pl["folded"] and pl["unfolds"] and pl["ticks"], "rows start folded, open with the arrow, and use tick boxes"
        assert pl["enabledOnly"] and pl["found"] == ["remote-boards"]
        st = self.out["settingsTabs"]
        assert st["shown"] == ["plugins"] and st["help"] == ["help"], "one section at a time"
        assert st["nav"][:3] == ["General", "Searching", "Plugins"]
        assert pl["chipsOff"] == [] and pl["cardOff"] is False, "switching Accounting off removes its boards"
        assert pl["chipsOn"] == ["ICAEW", "ACCA"] and pl["cardOn"], "and switching it on brings them back"
        assert pl["badLink"].startswith("That isn't a GitHub link") and not pl["installOpen"]
        assert pl["removable"] == 0, "built-in plugins can be switched off, not removed"

    def test_what_plugins_add_to_the_screen(self):
        ui = self.out["pluginUi"]
        assert ui["tabShown"] and ui["tabText"] == "🎮 Studios"
        assert ui["tabTitle"] == "Studios · jobslop" and ui["tabHeading"] == "Studios Near You"
        assert ui["layer"] == ["🎮 Game studios"], "the map gets the studios layer"
        assert "Games applications" in ui["cards"] and "Accounting applications" in ui["cards"]
        assert "Games" in ui["fields"] and "Accounting" in ui["fields"] and ui["engines"]
        assert ui["after"] == {"tab": False, "section": False, "layer": 0, "cards": ["Accounting applications"],
                               "engines": False, "style": False}, "switching Game dev off takes all of it away"

    def test_another_language(self):
        lang = self.out["lang"]
        assert lang["go"] == "Vacatures zoeken" and lang["tabs"] == ["Zoeken", "Tracker", "Voortgang", "Profiel"]
        assert lang["placeholder"].startswith("Welke baan?") and lang["title"] == "Zoeken · jobslop" and lang["picker"] == "nl"
        assert lang["toast"] == "Instellingen opgeslagen", "messages shown later are translated too"
        assert lang["jobTitle"] == lang["englishTitle"] != "", "job titles are never translated"
        assert lang["yesNo"] == ["=—", "Yes=Ja", "No=Nee"], "answers are still saved as Yes / No"
        assert lang["back"] == {"go": "Search jobs", "placeholder": "What job? e.g. data analyst — commas for several", "tab": "Search"}
