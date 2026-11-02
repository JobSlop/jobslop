"""The application tracker: saving jobs, statuses, notes, undo, Easy apply and CSV export."""
import csv
from pathlib import Path
from unittest import mock

from support import jf, AppTestCase, TMP

JOB = {"title": "Games Programmer", "company": "Rare", "url": "https://jobs.example/1", "location": "Twycross"}


class TrackerTests(AppTestCase):
    def saved(self, action, job=None, **extra):
        code, items = self.app.post("/api/saved", {"action": action, "job": dict(job or JOB), **extra})
        assert code == 200
        return items

    def test_save_a_job(self):
        items = self.saved("save")
        assert len(items) == 1
        assert (items[0]["status"], items[0]["saved_on"]) == ("Saved", jf.today())
        assert "applied_on" not in items[0]
        assert len(self.saved("save")) == 1, "saving the same job twice keeps one copy"
        assert self.app.get("/api/saved")[1] == items

    def test_mark_applied(self):
        self.saved("save")
        items = self.saved("applied")
        assert (items[0]["status"], items[0]["applied_on"]) == ("Applied", jf.today())
        assert "Applied" in items[0]["dates"]

    def test_add_by_hand(self):
        items = self.saved("add", {"title": "Barista", "company": "Costa", "applied_on": "2026-10-01"})
        assert items[0]["url"].startswith("manual:")
        assert (items[0]["status"], items[0]["applied_on"]) == ("Applied", "2026-10-01")

    def test_update_status_and_notes(self):
        self.saved("save")
        items = self.saved("update", {**JOB, "status": "Interview", "notes": "Call on Monday", "salary": "£40k"})
        it = items[0]
        assert (it["status"], it["notes"], it["salary"], it["applied_on"]) == ("Interview", "Call on Monday", "£40k", jf.today())
        items = self.saved("update", {**JOB, "status": "Offer"})
        assert set(items[0]["dates"]) == {"Saved", "Interview", "Offer"}

    def test_unclick_applied(self):
        """'✓ Applied' clicked again: back to Saved, and the application dates are forgotten."""
        self.saved("save")
        self.saved("applied")
        items = self.saved("update", {**JOB, "status": "Interview", "notes": "Keep me"})
        before = dict(items[0])
        items = self.saved("unapply", {"url": JOB["url"]})
        it = items[0]
        assert it["status"] == "Saved"
        assert "applied_on" not in it
        assert set(it["dates"]) == {"Saved"}
        assert it["notes"] == "Keep me", "notes survive"
        # Undo puts it back exactly as it was
        items = self.saved("put", before)
        assert items[0] == before

    def test_unclick_applied_on_a_job_never_saved_first(self):
        """'✓ Mark applied' on a search result, then clicked again: it stays on the tracker as Saved."""
        self.saved("applied")
        it = self.saved("unapply", {"url": JOB["url"]})[0]
        assert (it["status"], it["dates"]) == ("Saved", {"Saved": jf.today()})

    def test_unapply_leaves_saved_jobs_alone(self):
        self.saved("save")
        assert self.saved("unapply", {"url": JOB["url"]})[0]["status"] == "Saved"
        assert self.saved("unapply", {"url": "https://jobs.example/nope"}) == jf.load_saved()

    def test_unclick_saved(self):
        """'★ Saved' clicked again removes the job; Undo restores it in the same place."""
        self.saved("save")
        assert self.saved("remove", {"url": JOB["url"]}) == []
        assert self.saved("restore", {**JOB, "status": "Saved"}, index=0)[0]["url"] == JOB["url"]

    def test_remove_and_undo(self):
        self.saved("save")
        self.saved("save", {**JOB, "url": "https://jobs.example/2", "title": "Second"})
        removed = self.app.get("/api/saved")[1][1]
        assert len(self.saved("remove", removed)) == 1
        items = self.saved("restore", removed, index=1)
        assert [i["title"] for i in items] == ["Second", "Games Programmer"], "undo puts the card back where it was"
        assert items[1]["url"] == removed["url"]

    def test_undo_puts_the_whole_tracker_back(self):
        """Ctrl+Z / ↶: the screen remembers the tracker before a change and sends it back."""
        self.saved("save")
        before = self.app.get("/api/saved")[1]
        self.saved("save", {**JOB, "url": "https://jobs.example/2", "title": "Second"})
        self.saved("update", {**JOB, "status": "Interview"})
        code, items = self.app.post("/api/saved", {"action": "set_all", "items": before})
        assert code == 200 and items == before == jf.load_saved()
        code, items = self.app.post("/api/saved", {"action": "set_all", "items": [{"title": "no link"}, "junk"]})
        assert items == [], "only real tracker cards are accepted"

    def test_thank_you_email_opens_only_for_jobslop(self):
        mail = "mailto:jobslop@proton.me?subject=jobslop%20feedback&body=Hi"
        with mock.patch.object(jf.os, "startfile", create=True) as startfile, mock.patch.object(jf.webbrowser, "open") as browser:
            self.app.post("/api/open", {"url": mail})
            self.app.post("/api/open", {"url": "mailto:someone@else.com?subject=x"})
            self.app.post("/api/open", {"url": "mailto:jobslop@proton.me.evil.com?subject=x"})
        opened = [c.args[0] for c in startfile.call_args_list + browser.call_args_list]
        assert opened == [mail], "only the jobslop address can be opened as an email"

    def test_easy_apply(self):
        with mock.patch.object(jf, "open_in_chrome", return_value=True) as chrome:
            code, r = self.app.post("/api/apply", {"job": dict(JOB)})
        assert (code, r["chrome"]) == (200, True)
        chrome.assert_called_once_with(JOB["url"])
        assert r["saved"][0]["status"] == "Applying"
        assert jf.active_job()["url"] == JOB["url"], "the extension knows which job you're applying for"
        # the extension then reports the application was sent
        code, _ = self.app.post("/ext/applied", {}, headers={"X-JobFinder-Key": jf.pairing_code()})
        assert jf.load_saved()[0]["status"] == "Applied"

    def test_easy_apply_needs_a_link(self):
        code, _ = self.app.post("/api/apply", {"job": {"title": "x", "url": "javascript:alert(1)"}})
        assert code == 400

    def test_csv_export(self):
        with mock.patch.object(jf.Path, "home", return_value=Path(TMP)):
            code, r = self.app.post("/api/export", {"rows": [{"title": "Dev", "company": "Café Ltd"}],
                                                     "cols": ["title", "company"], "name": "tracker"})
        with open(r["path"], encoding="utf-8-sig", newline="") as f:
            rows = list(csv.reader(f))
        assert rows == [["title", "company"], ["Dev", "Café Ltd"]]
        Path(r["path"]).unlink()

    def test_status_history(self):
        item = {}
        jf.set_status(item, "Saved")
        assert "applied_on" not in item
        jf.set_status(item, "Interview", "2026-09-30T10:00")
        assert item["applied_on"] == "2026-09-30"
        jf.set_status(item, "Rejected")
        assert item["applied_on"] == "2026-09-30", "the first application date is kept"
