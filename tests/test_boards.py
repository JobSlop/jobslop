"""Every job board jobslop searches, fed with saved sample answers (no internet needed).

Each test checks that a board's answer is turned into jobs correctly: title, company, link,
place, date, salary — and that boards refuse countries they don't cover or ask for a key.
If a board changes its website, the live app breaks but these tests keep passing; they guard
against *our* changes breaking the readers.
"""
import json
import re
import time
import urllib.error
from datetime import datetime, timedelta
from unittest import mock

import pytest
from support import base_opts, fake_urlopen, reset_data

from jobslop import net, settings, text
from jobslop.boards import base as board_base
from jobslop.boards import country as country_boards
from jobslop.boards import jobspy as jobspy_boards
from jobslop.boards import keyed as keyed_boards
from jobslop.boards import linkedin as linkedin_board
from jobslop.boards import registry
from jobslop.boards import remote as remote_boards
from jobslop.boards import special as special_boards
from jobslop.geo import cities


def days_ago(n):
    return (datetime.now() - timedelta(days=n)).strftime("%Y-%m-%d")


class HelperTests:
    def test_money(self):
        assert text.money(30000, 40000, "GBP") == "£30k–£40k"
        assert text.money(50000, 50000, "USD") == "$50k"
        assert text.money(15, None, "EUR") == "€15"
        assert text.money(0, None) == ""
        assert text.money("x", None) == ""
        assert text.money(1000, 2000, "XYZ") == "XYZ 1k–XYZ 2k"

    def test_to_date(self):
        assert text.to_date("2026-10-30T12:00:00Z") == "2026-10-30"
        assert text.to_date("30/10/2026") == "2026-10-30"
        assert text.to_date(0) == ""
        assert text.to_date(None) == ""
        assert text.to_date(1700000000) == "2023-11-14"

    def test_rel_date(self):
        assert text.rel_date("Just posted") == days_ago(0)
        assert text.rel_date("3 days ago") == days_ago(3)
        assert text.rel_date("2 weeks ago") == days_ago(14)
        assert text.rel_date("30+ days ago") == days_ago(30)
        assert text.rel_date("24h") == days_ago(0)
        assert text.rel_date("2026-01-05") == "2026-01-05"
        assert text.rel_date("") == ""

    def test_short_and_dutch_dates(self):
        assert text.short_date("3 days ago") == days_ago(3)
        d = text.short_date("1 Jan")
        assert re.search(r"^\d{4}-01-01$", d)
        assert d <= datetime.now().strftime("%Y-%m-%d"), "a date without a year is never in the future"
        assert country_boards.dutch_date("Vandaag") == days_ago(0)
        assert country_boards.dutch_date("gisteren") == days_ago(1)
        assert country_boards.dutch_date("3 dagen geleden") == days_ago(3)
        assert country_boards.dutch_date("2 weken geleden") == days_ago(14)
        assert country_boards.dutch_date("onbekend") == ""

    def test_strip_html(self):
        assert text.strip_html("<p>Hello&nbsp;<b>world</b></p>") == "Hello world"
        assert text.strip_html("&amp;lt;b&amp;gt;") == ""          # double-escaped tags are removed too
        assert text.strip_html("a" * 700) == "a" * 600
        assert text.strip_html(None) == ""

    def test_as_list(self):
        assert board_base.as_list(["a", {"name": "b"}]) == ["a", "b"]
        assert board_base.as_list("x") == ["x"]
        assert board_base.as_list(None) == []

    def test_job_record(self):
        j = board_base.job("X", "<b>Dev</b>", "Acme", "https://x", tags=["a", "", "b"])
        assert (j["title"], j["location"], j["tags"]) == ("Dev", "Not listed", ["a", "b"])

    def test_linkedin_search_url(self):
        u = linkedin_board.linkedin_search_url("games programmer", base_opts(where="Birmingham", posted=7, jtype="internship",
                                                                 remote="hybrid"), guest=True)
        assert "seeMoreJobPostings" in u
        for part in ("keywords=games+programmer", "location=Birmingham%2C+United+Kingdom", "distance=15",
                     "f_TPR=r604800", "f_JT=I", "f_WT=3"):
            assert part in u
        assert "location=Worldwide" in linkedin_board.linkedin_search_url("x", base_opts(local=False))

    def test_tail_place(self):
        assert cities.tail_place("Great role in the heart of West Sussex, Horsham", "GB") == "Horsham"
        assert cities.tail_place("No place mentioned here", "GB") == ""


class BoardTestCase:
    def setup_method(self):
        reset_data()

    def set_keys(self, **keys):
        settings.update_settings(lambda s: s.update(keys))

    def json_board(self, fn, answers, opts=None, q="developer"):
        """Run a board whose answers come from get_json: answers maps a URL piece -> JSON."""
        asked = []

        def fake_get_json(url, timeout=20, headers=None):
            asked.append((url, headers))
            for part, body in answers.items():
                if part in url:
                    if isinstance(body, Exception):
                        raise body
                    return json.loads(json.dumps(body))
            return {}
        with mock.patch.object(net, "get_json", side_effect=fake_get_json):
            return fn(q, opts or base_opts()), asked

    def html_board(self, fn, pages, opts=None, q="developer"):
        with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen(pages)):
            return fn(q, opts or base_opts())


class KeyedBoardTests(BoardTestCase):
    def test_reed(self):
        with pytest.raises(board_base.NeedsKey):
            keyed_boards.src_reed("x", base_opts())
        with pytest.raises(board_base.NotHere):
            keyed_boards.src_reed("x", base_opts(country="US"))
        self.set_keys(reed_key="abc")
        jobs, asked = self.json_board(keyed_boards.src_reed, {"reed.co.uk": {"results": [
            {"jobTitle": "Games Programmer", "employerName": "Studio", "jobUrl": "https://reed/1", "locationName": "Leamington Spa",
             "date": "30/10/2026", "minimumSalary": 35000, "maximumSalary": 45000, "currency": "GBP", "jobDescription": "<p>C++</p>"}]}},
            base_opts(where="Coventry", salary_min=30000, jtype="fulltime"))
        assert len(jobs) == 1
        j = jobs[0]
        assert (j["title"], j["company"], j["location"], j["date"], j["salary"], j["desc"]) == \
                         ("Games Programmer", "Studio", "Leamington Spa", "2026-10-30", "£35k–£45k", "C++")
        url, headers = asked[0]
        assert "locationName=Coventry" in url
        assert "minimumSalary=30000" in url
        assert "fullTime=true" in url
        assert headers["Authorization"].startswith("Basic ")

    def test_adzuna(self):
        with pytest.raises(board_base.NeedsKey):
            keyed_boards.src_adzuna("x", base_opts())
        self.set_keys(adzuna_id="id", adzuna_key="key")
        jobs, asked = self.json_board(keyed_boards.src_adzuna, {"adzuna.com": {"results": [
            {"title": "Data Analyst", "company": {"display_name": "Bank"}, "redirect_url": "https://adz/1",
             "location": {"display_name": "Birmingham"}, "created": "2026-10-29T10:00:00Z", "salary_min": 30000,
             "salary_max": 36000, "contract_time": "full_time", "contract_type": "permanent",
             "category": {"label": "IT Jobs"}, "description": "SQL"}]}}, base_opts(where="Birmingham", posted=7))
        j = jobs[0]
        assert (j["company"], j["salary"], j["type"], j["tags"]) == ("Bank", "£30k–£36k", "full time permanent", ["IT Jobs"])
        assert "/gb/search/1" in asked[0][0]
        assert "where=Birmingham" in asked[0][0]
        assert "max_days_old=7" in asked[0][0]

    def test_usajobs(self):
        with pytest.raises(board_base.NotHere):
            country_boards.src_usajobs("x", base_opts())
        with pytest.raises(board_base.NeedsKey):
            country_boards.src_usajobs("x", base_opts(country="US"))
        self.set_keys(usajobs_key="k", usajobs_email="me@example.com")
        jobs, asked = self.json_board(country_boards.src_usajobs, {"usajobs.gov": {"SearchResult": {"SearchResultItems": [
            {"MatchedObjectDescriptor": {"PositionTitle": "IT Specialist", "OrganizationName": "NASA",
                                         "PositionURI": "https://usajobs/1", "PositionLocationDisplay": "Houston, Texas",
                                         "PublicationStartDate": "2026-10-01",
                                         "PositionRemuneration": [{"MinimumRange": "80000", "MaximumRange": "100000", "RateIntervalCode": "PA"}],
                                         "PositionLocation": [{"Latitude": 29.7, "Longitude": -95.3}],
                                         "PositionSchedule": [{"Name": "Full-time"}],
                                         "UserArea": {"Details": {"JobSummary": "Space IT"}}}}]}}},
            base_opts(country="US", where="Houston, TX"))
        j = jobs[0]
        assert (j["title"], j["salary"], j["type"], j["lat"]) == ("IT Specialist", "$80k–$100k", "Full-time", 29.7)
        assert asked[0][1]["Authorization-Key"] == "k"


class RemoteBoardTests(BoardTestCase):
    def test_himalayas(self):
        locs = ["United Kingdom", "Ireland", "France", "Spain", "Italy"]
        jobs, asked = self.json_board(remote_boards.src_himalayas, {"himalayas.app": {"jobs": [
            {"title": "Engineer", "companyName": "Remote Co", "applicationLink": "https://him/1", "locationRestrictions": locs,
             "pubDate": 1761800000, "minSalary": 60000, "maxSalary": 80000, "currency": "USD", "employmentType": "Full Time",
             "categories": ["Software"], "description": "Build"},
            {"title": "Writer", "companyName": "Words", "guid": "https://him/2", "locationRestrictions": []}]}})
        assert jobs[0]["location"] == "Remote · United Kingdom + 4 more countries"
        assert jobs[1]["location"] == "Remote · Worldwide"
        assert jobs[1]["url"] == "https://him/2"
        assert "country=GB" in asked[0][0]
        assert len(asked) == 1, "fewer than 20 jobs means there's no next page"

    def test_jobicy_retries_without_region(self):
        jobs, asked = self.json_board(remote_boards.src_jobicy, {"geo=": {"jobs": []}, "jobicy.com": {"jobs": [
            {"jobTitle": "Support", "companyName": "Help", "url": "https://jobicy/1", "jobGeo": "Europe",
             "pubDate": "2026-10-28", "annualSalaryMin": 40000, "annualSalaryMax": 50000, "salaryCurrency": "EUR",
             "jobType": ["Full-time"], "jobIndustry": ["Customer"], "jobExcerpt": "Help people"}]}})
        assert len(asked) == 2, "an empty region answer is retried without the region"
        assert (jobs[0]["location"], jobs[0]["salary"]) == ("Remote · Europe", "€40k–€50k")

    def test_remotive(self):
        jobs, _ = self.json_board(remote_boards.src_remotive, {"remotive.com": {"jobs": [
            {"title": "QA", "company_name": "Test Co", "url": "https://rem/1", "candidate_required_location": "UK",
             "publication_date": "2026-10-27T00:00:00", "salary": "£40k", "job_type": "full_time", "tags": ["qa"],
             "description": "Testing"}]}})
        assert (jobs[0]["location"], jobs[0]["type"], jobs[0]["salary"]) == ("Remote · UK", "full time", "£40k")

    def test_remoteok_skips_notice_and_survives_errors(self):
        jobs, asked = self.json_board(remote_boards.src_remoteok, {
            "tag=": urllib.error.URLError("down"),
            "remoteok.com/api": [{"legal": "notice"}, {"position": "Dev", "company": "OK", "url": "https://rok/1",
                                                       "location": "Worldwide", "epoch": 1761800000, "tags": ["js"]}]},
            q="python developer")
        assert len(jobs) == 1
        assert len(asked) == 3, "the main feed plus one per search word"

    def test_arbeitnow(self):
        jobs, asked = self.json_board(remote_boards.src_arbeitnow, {"arbeitnow.com": {"data": [
            {"title": "Entwickler", "company_name": "GmbH", "url": "https://arb/1", "location": "Berlin", "remote": True,
             "created_at": 1761800000, "job_types": ["full time"], "tags": ["it"], "description": "Code"}]}})
        assert jobs[0]["location"] == "Berlin (remote)"
        assert jobs[0]["remote"]
        assert len(asked) == 3

    def test_artstation(self):
        jobs, _ = self.json_board(special_boards.src_artstation, {"artstation.com": {"data": [
            {"title": "Environment Artist", "company_name": "Studio", "hash_id": "abc", "work_remotely": True,
             "recruitment_localities": [{"locality": {"city_name": "Guildford", "country_name": "United Kingdom"}}],
             "salary_range": {"min_salary": 30, "max_salary": 40, "currency": "GBP", "period": "hour"},
             "listing_placement": {"posted_at": "2026-10-20"}, "job_type": "Full-time", "level": "Senior", "skills": "3D"}]}})
        j = jobs[0]
        assert j["url"] == "https://www.artstation.com/jobs/abc"
        assert j["location"] == "Remote · Guildford, United Kingdom"
        assert j["salary"] == "£30–£40 / hour"
        assert j["type"] == "Full-time · Senior"


class CountryBoardTests(BoardTestCase):
    def test_jobindex(self):
        with pytest.raises(board_base.NotHere):
            country_boards.src_jobindex("x", base_opts())
        jobs, asked = self.json_board(country_boards.src_jobindex, {"jobindex.dk": {"total_pages": 1, "results": [
            {"headline": "Udvikler", "companytext": "Firma", "share_url": "https://ji/1", "area": "Aarhus",
             "firstdate": "2026-10-25", "addresses": [{"coordinates": {"latitude": 56.15, "longitude": 10.2}}]}]}},
            base_opts(country="DK", where="Aarhus"))
        assert (jobs[0]["lat"], jobs[0]["location"]) == (56.15, "Aarhus")
        assert "address=Aarhus" in asked[0][0]

    def test_jobbird(self):
        with pytest.raises(board_base.NotHere):
            country_boards.src_jobbird("x", base_opts())
        card = ('<a href="https://www.jobbird.com/nl/vacature/123-dev" class="job-search__result-list__result__title">Developer</a>'
                '<span class="cro-recruiter-name"><span>Bedrijf BV</span></span>'
                '<span class="cro-job-location"><span>Utrecht</span></span>'
                '<span class="cro-time-posted"><span>2 dagen geleden</span></span>')
        jobs = self.html_board(country_boards.src_jobbird, {"jobbird.com": card}, base_opts(country="NL", where="Utrecht"))
        assert len(jobs) == 1
        assert (jobs[0]["title"], jobs[0]["company"], jobs[0]["location"], jobs[0]["date"]) == \
                         ("Developer", "Bedrijf BV", "Utrecht", days_ago(2))

    def test_jobs2careers(self):
        with pytest.raises(board_base.NotHere):
            country_boards.src_jobs2careers("x", base_opts())
        ads = {"jobAds": {"byId": {"1": {"adType": "job", "title": "Nurse", "companyName": "Hospital", "link": "https://j2c/1",
                                         "cityState": "Austin, TX", "datePosted": "2026-10-30", "workLocation": "onsite",
                                         "salaryDetails": {"0": {"label": "$30/hr"}}, "workTypeDetails": {"0": {"label": "Full-time"}},
                                         "coordinates": {"0": "30.27,-97.74"}},
                                   "2": {"adType": "sponsored", "title": "Ad"}}}}
        page = "<script>window.__DATA__=" + json.dumps(ads, separators=(",", ":")) + ";</script>"
        jobs = self.html_board(country_boards.src_jobs2careers, {"jobs2careers.com": page}, base_opts(country="US", where="Austin"))
        assert len(jobs) == 1, "sponsored adverts are skipped"
        assert (jobs[0]["salary"], jobs[0]["type"], jobs[0]["lat"]) == ("$30/hr", "Full-time", 30.27)

    def test_ziprecruiter_uk(self):
        with pytest.raises(board_base.NotHere):
            country_boards.src_ziprecruiter_uk("x", base_opts(country="US"))
        card = ('<li class="job-listing"><a class="jobList-title" href="https://zip/1">Software Engineer</a>'
                '<li><i class="fa-building"></i>Tech Ltd</li><li><i class="fa-map-marker-alt"></i>Birmingham</li>'
                '<div class="jobList-description">Great job</div><div class="jobList-date">3 days ago</div>'
                '<li><i class="fa-pound-sign"></i>£40,000</li>')
        jobs = self.html_board(country_boards.src_ziprecruiter_uk, {"ziprecruiter.co.uk": card})
        assert (jobs[0]["company"], jobs[0]["location"], jobs[0]["date"], jobs[0]["salary"]) == \
                         ("Tech Ltd", "Birmingham", days_ago(3), "£40,000")

    def test_workwithindies(self):
        card = ('<a href="/careers/abc" class="job-card w-inline-block"><div class="job-card-text bold">Tiny Studio</div>'
                '<div class="text-block-28">Gameplay Programmer</div><div class="job-card-text-smol">Remote (EU)</div></a>')
        jobs = self.html_board(special_boards.src_workwithindies, {"workwithindies.com": card})
        j = jobs[0]
        assert (j["title"], j["company"], j["url"], j["remote"]) == \
                         ("Gameplay Programmer", "Tiny Studio", "https://www.workwithindies.com/careers/abc", True)

    def test_icaew_and_acca_rss(self):
        rss = ("<rss><item><title>Big Four: Audit Senior</title><link>https://icaew/1?trk=x</link>"
               "<pubDate>Wed, 29 Oct 2026 10:00:00 GMT</pubDate>"
               "<description>£45,000: Big Four: Great audit role. Birmingham (GB)</description></item>"
               "<item><title>Tax Manager</title><link>https://icaew/2</link><pubDate>x</pubDate>"
               "<description>Role based in Dubai (AE)</description></item></rss>")
        jobs = self.html_board(special_boards.src_icaew, {"icaewjobs.com": rss})
        assert len(jobs) == 1, "jobs in other countries are dropped when 'workable from my country' is on"
        j = jobs[0]
        assert (j["company"], j["title"], j["location"], j["salary"], j["date"], j["url"]) == \
                         ("Big Four", "Audit Senior", "Birmingham", "£45,000", "2026-10-29", "https://icaew/1")
        jobs = self.html_board(special_boards.src_acca, {"accaglobal.com": rss}, base_opts(local=False))
        assert len(jobs) == 2


class BigBoardTests(BoardTestCase):
    LI_CARD = ('<li><a class="base-card__full-link absolute" href="https://uk.linkedin.com/jobs/view/123?refId=x">x</a>'
               '<h3 class="base-search-card__title">Games Programmer</h3>'
               '<h4 class="base-search-card__subtitle"><a>Big Studio</a></h4>'
               '<span class="job-search-card__location">Leamington Spa, England</span>'
               '<time datetime="2026-10-30">1 day ago</time></li>')

    def test_linkedin_direct(self):
        jobspy_boards.li_state.update(last=0, blocked_until=0)
        with mock.patch.object(linkedin_board, "LI_GAP", 0):
            jobs = self.html_board(linkedin_board.src_linkedin, {"linkedin.com": self.LI_CARD})
        j = jobs[0]
        assert (j["title"], j["company"], j["url"], j["location"], j["date"]) == \
                         ("Games Programmer", "Big Studio", "https://uk.linkedin.com/jobs/view/123",
                          "Leamington Spa, England", "2026-10-30")

    def test_linkedin_slow_down(self):
        jobspy_boards.li_state.update(last=0, blocked_until=0)
        err = urllib.error.HTTPError("u", 429, "Too many", {}, None)
        with mock.patch.object(linkedin_board, "LI_GAP", 0), pytest.raises(RuntimeError) as e:
            self.html_board(linkedin_board.src_linkedin, {"linkedin.com": err})
        assert "slow down" in str(e.value)
        assert jobspy_boards.li_state["blocked_until"] > time.time(), "LinkedIn is paused after it asks us to slow down"
        jobspy_boards.li_state.update(blocked_until=0)

    def test_linkedin_with_apify(self):
        self.set_keys(apify_token="tok")
        items = [{"title": "Dev", "companyName": "Co", "link": "https://linkedin.com/jobs/view/9?x=1", "location": "Leeds",
                  "postedAt": "2026-10-29", "salaryInfo": ["£40k", "£50k"], "employmentType": "Full-time"}]
        with mock.patch.object(linkedin_board, "apify_run", return_value=items) as run:
            jobs = linkedin_board.src_linkedin("dev", base_opts())
        assert (jobs[0]["url"], jobs[0]["salary"]) == ("https://linkedin.com/jobs/view/9", "£40k – £50k")
        assert run.call_args[0][0] == "curious_coder~linkedin-jobs-scraper"

    def test_indeed_and_glassdoor_fall_back_to_apify(self):
        with mock.patch.object(jobspy_boards, "jobspy_run", side_effect=RuntimeError("Indeed refused")):
            with pytest.raises(RuntimeError) as e:
                jobspy_boards.src_indeed("dev", base_opts())
            assert "Apify token" in str(e.value)
            self.set_keys(apify_token="tok")
            items = [{"positionName": "Dev", "company": "Co", "url": "https://indeed/1", "location": "Leeds",
                      "postedAt": "2 days ago", "salary": "£30k", "jobType": ["Full-time"], "description": "x"}]
            with mock.patch.object(jobspy_boards, "apify_run", return_value=items):
                jobs = jobspy_boards.src_indeed("dev", base_opts())
            assert (jobs[0]["source"], jobs[0]["date"]) == ("Indeed", days_ago(2))
            with mock.patch.object(jobspy_boards, "apify_run", return_value=[{"job_title": "Dev", "company_name": "Co",
                                                                   "url": "https://gd/1", "date": "1 day ago"}]):
                jobs = jobspy_boards.src_glassdoor("dev", base_opts())
            assert jobs[0]["source"] == "Glassdoor"

    def test_jobspy_rows_become_jobs(self):
        """Indeed/Glassdoor via JobSpy: table rows -> jobs, with the place and filters passed on."""
        try:
            import jobspy  # noqa: F401
            import pandas as pd
        except ImportError:
            pytest.skip("JobSpy isn't installed in this Python")
        df = pd.DataFrame([{"title": "Dev", "company": "Co", "job_url": "https://indeed/1", "location": "Leeds, ENG",
                            "date_posted": "2026-10-30", "min_amount": 30000, "max_amount": 40000, "currency": "GBP",
                            "interval": "yearly", "job_type": "fulltime", "description": "x", "is_remote": False}])
        jobspy_boards.js_state.clear()
        with mock.patch("jobspy.scrape_jobs", return_value=df) as scrape, mock.patch.object(jobspy_boards, "JS_GAP", 0):
            jobs = jobspy_boards.jobspy_run("indeed", "dev", base_opts(where="Leeds", jtype="fulltime"))
        assert (jobs[0]["salary"], jobs[0]["type"]) == ("£30k–£40k", "Full time")
        kw = scrape.call_args.kwargs
        assert (kw["location"], kw["job_type"]) == ("Leeds, United Kingdom", "fulltime")

    def test_every_board_is_registered(self):
        assert len(registry.SOURCES) == 19
        for name, fn in registry.SOURCES.items():
            assert callable(fn), name

