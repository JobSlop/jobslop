"""Regression tests for jobslop's search and "Where?" location handling.

Run them with  run_tests.bat  (or:  python -m pytest).
They never touch the internet or your own jobslop data: job boards are replaced by
fake ones, online postcode lookups are faked, and the app's data folder is a temporary one.
"""
import json
import urllib.error
from unittest import mock

from support import AppServer, FakeBoards, base_opts, fake_lookup, make_job, offline, reset_data

from jobslop import runtime
from jobslop.boards import base as board_base
from jobslop.geo import countries, osm, places
from jobslop.profile import store as pstore
from jobslop.search import contract, engine


class SearchTestCase:
    def setup_method(self):
        reset_data()

    def run_search(self, boards, query="software developer", fresh=True, **opts):
        fake = FakeBoards(boards)
        with fake.installed(), \
                mock.patch.object(places, "lookup_postcode", side_effect=fake_lookup), \
                mock.patch.object(osm, "nominatim", side_effect=OSError("no internet in tests")):
            out = engine.search(query, list(boards), base_opts(**opts), fresh=fresh)
        return out, fake


# ------------------------------------------------------------------ "Where?" understanding

class WhereTests:
    def check(self, text, cc, town, postcode="", country=None, region=None, board=None):
        r = places.resolve_where(text, cc)
        assert r is not None, f"{text!r} should be understood as a place"
        assert r["town"] == town, f"town for {text!r}"
        assert r["postcode"] == postcode, f"postcode for {text!r}"
        assert r["country_code"] == (country or cc), f"country for {text!r}"
        if region is not None:
            assert r["region"] == region, f"region for {text!r}"
        assert r["board_where"] == (board or town), f"text sent to job boards for {text!r}"
        assert r["lat"] is not None, f"{text!r} should have a point on the map for distances"
        return r

    @offline
    def test_plain_towns(self):
        self.check("Birmingham", "GB", "Birmingham")
        self.check("birmingham", "GB", "Birmingham")
        self.check("London", "GB", "London")
        self.check("Stoke-on-Trent", "GB", "Stoke-on-Trent")
        self.check("Newcastle upon Tyne", "GB", "Newcastle upon Tyne")

    @offline
    def test_town_with_county_or_country(self):
        self.check("Coventry, West Midlands", "GB", "Coventry", region="West Midlands")
        self.check("Birmingham, United Kingdom", "GB", "Birmingham")
        self.check("Birmingham UK", "GB", "Birmingham")

    @offline
    def test_uk_postcodes(self):
        self.check("B3 2BJ", "GB", "Birmingham", postcode="B3 2BJ")
        self.check("b32bj", "GB", "Birmingham", postcode="B3 2BJ")
        self.check("B3", "GB", "Birmingham", postcode="B3")
        self.check("CV1", "GB", "Coventry", postcode="CV1")

    @offline
    def test_full_uk_addresses(self):
        self.check("12 Colmore Row, Birmingham B3 2BJ", "GB", "Birmingham", postcode="B3 2BJ")
        self.check("12 Colmore Row, Birmingham, B3 2BJ, United Kingdom", "GB", "Birmingham", postcode="B3 2BJ")
        self.check("Flat 3, 22 London Road, Coventry, West Midlands, CV1 2AB", "GB", "Coventry",
                   postcode="CV1 2AB", region="West Midlands")
        self.check("12 Colmore Row\nBirmingham\nB3 2BJ", "GB", "Birmingham", postcode="B3 2BJ")

    @offline
    def test_street_names_are_not_towns(self):
        """'London Road' must not become London; 'Colmore Row' must not be a town."""
        r = places.resolve_where("22 London Road, Coventry", "GB")
        assert r["town"] == "Coventry"

    @offline
    def test_us_addresses_switch_country(self):
        r = self.check("Daytona Beach, FL 32114", "GB", "Daytona Beach", postcode="32114", country="US",
                       region="FL", board="Daytona Beach, FL")
        assert r["label"] == "Daytona Beach, FL 32114, United States"
        self.check("Austin TX", "US", "Austin", region="TX", board="Austin, TX")
        self.check("Austin, Texas", "GB", "Austin", country="US", region="TX", board="Austin, TX")
        self.check("123 Main St, Austin, TX 78701", "US", "Austin", postcode="78701", region="TX", board="Austin, TX")
        self.check("32114", "US", "Daytona Beach", postcode="32114", region="FL", board="Daytona Beach, FL")

    @offline
    def test_european_addresses(self):
        self.check("1012 AB Amsterdam", "NL", "Amsterdam", postcode="1012 AB")
        self.check("Damrak 1, 1012 LG Amsterdam", "NL", "Amsterdam", postcode="1012 LG")
        self.check("8000 Aarhus C", "DK", "Aarhus", postcode="8000")       # keeps the typed spelling
        self.check("10115 Berlin", "DE", "Berlin", postcode="10115")

    @offline
    def test_whole_country_means_no_town(self):
        for text in ("", "  ", "UK", "United Kingdom", "England", "gb"):
            assert places.resolve_where(text, "GB") is None, f"{text!r} means the whole country"

    @offline
    def test_other_country_name_switches_country(self):
        r = places.resolve_where("Germany", "GB")
        assert (r["town"], r["country_code"], r["explicit_country"]) == ("", "DE", True)

    @offline
    def test_unknown_place_is_passed_on_as_typed(self):
        r = places.resolve_where("Smalltownthatdoesnotexist", "GB")
        assert r["town"] == "Smalltownthatdoesnotexist"
        assert not r["found"]
        assert r["lat"] is None

    def test_postcode_lookup_failure_still_finds_town(self):
        """No internet: an address with a town still works, only the exact postcode spot is missing."""
        places._places["mem"].clear()
        with mock.patch.object(places, "lookup_postcode", return_value=None), \
                mock.patch.object(osm, "nominatim", side_effect=OSError("offline")):
            r = places.resolve_where("12 Colmore Row, Birmingham B3 2BJ", "GB")
        assert r["town"] == "Birmingham"
        assert r["lat"] is not None


class CountryTests:
    def test_is_country_name(self):
        assert countries.is_country_name("", "GB")
        assert countries.is_country_name("UK", "GB")
        assert countries.is_country_name("Nederland", "NL")
        assert not countries.is_country_name("Birmingham", "GB")
        assert not countries.is_country_name("UK", "US")

    def test_place_text_for_boards(self):
        assert places.place(base_opts(where="")) == "United Kingdom"
        assert places.place(base_opts(where="Birmingham")) == "Birmingham, United Kingdom"
        assert places.place(base_opts(where="Austin, TX", country="US")) == "Austin, TX"


# ------------------------------------------------------------------ the search pipeline

class SearchLocationTests(SearchTestCase):
    def test_address_is_sent_to_boards_as_a_town(self):
        """Regression: a full address or postcode in Where? used to reach the boards as-is and break them."""
        for where in ("12 Colmore Row, Birmingham B3 2BJ", "B3 2BJ", "Birmingham", "birmingham, uk"):
            out, fake = self.run_search({"LinkedIn": [make_job("LinkedIn", "Software Developer")]}, where=where)
            asked = fake.asked("LinkedIn")[0][2]
            assert asked["where"] == "Birmingham", f"boards should be asked for the town, not {where!r}"
            assert len(out["results"]) == 1, where
            assert out["place"]["town"] == "Birmingham"

    def test_worldwide_boards_keep_nearby_jobs_for_an_address(self):
        """Regression: worldwide boards dropped every job when Where? held an address."""
        jobs = [make_job("Arbeitnow", "Software Developer", "Near Co", location="Birmingham, UK"),
                make_job("Arbeitnow", "Software Developer", "Close Co", location="Solihull, UK"),
                make_job("Arbeitnow", "Software Developer", "Far Co", location="Manchester, UK"),
                make_job("Arbeitnow", "Software Developer", "Remote Co", location="Remote · United Kingdom")]
        out, _ = self.run_search({"Arbeitnow": jobs}, where="12 Colmore Row, Birmingham B3 2BJ")
        companies = {j["company"] for j in out["results"]}
        assert companies == {"Near Co", "Close Co", "Remote Co"}

    def test_distances_are_measured_from_the_postcode(self):
        out, _ = self.run_search({"Arbeitnow": [make_job("Arbeitnow", "Software Developer", location="Solihull, UK")]},
                                 where="B3 2BJ")
        d = out["results"][0]["dist_km"]
        assert d is not None
        assert 5 < d < 20, f"Solihull is about 12 km from B3 2BJ, got {d}"

    def test_us_address_searches_the_us(self):
        out, fake = self.run_search({"LinkedIn": [make_job("LinkedIn", "Software Developer", location="Daytona Beach, FL")]},
                                    where="Daytona Beach, FL 32114", country="GB")
        asked = fake.asked("LinkedIn")[0][2]
        assert (asked["country"], asked["where"]) == ("US", "Daytona Beach, FL")

    def test_empty_where_searches_whole_country(self):
        out, fake = self.run_search({"LinkedIn": [make_job("LinkedIn", "Software Developer", location="Leeds, UK")]},
                                    where="")
        assert fake.asked("LinkedIn")[0][2]["where"] == ""
        assert len(out["results"]) == 1
        assert out["place"] is None

    def test_jobs_you_cant_do_from_your_country_are_marked_not_dropped(self):
        """"Workable from my country" only hides jobs on screen; the search still returns them, marked."""
        jobs = [make_job("Remotive", "Software Developer", "A", location="Remote · Worldwide"),
                make_job("Remotive", "Software Developer", "B", location="Remote · Philippines"),
                make_job("Remotive", "Software Developer", "C", location="Remote · UK"),
                make_job("LinkedIn", "Software Developer", "D", location="Leeds")]
        out, _ = self.run_search({"Remotive": jobs[:3], "LinkedIn": jobs[3:]})
        assert {j["company"]: j["local_ok"] for j in out["results"]} == {"A": True, "B": False, "C": True, "D": True}


class SearchMatchingTests(SearchTestCase):
    def test_title_matches_rank_first(self):
        jobs = [make_job("LinkedIn", "Office Manager", "Desc Co", desc="We need a software developer to help"),
                make_job("LinkedIn", "Software Developer", "Title Co")]
        out, _ = self.run_search({"LinkedIn": jobs})
        assert out["results"][0]["company"] == "Title Co"

    def test_unrelated_jobs_are_dropped(self):
        out, _ = self.run_search({"LinkedIn": [make_job("LinkedIn", "Chef de Partie", desc="kitchen work")]})
        assert out["results"] == []

    def test_title_match_is_marked_not_filtered(self):
        """"Title must match" only hides jobs on screen; each job says whether every search word is in its title."""
        jobs = [make_job("LinkedIn", "Software Engineer", "A", desc="developer"),
                make_job("LinkedIn", "Senior Software Developer", "B")]
        out, _ = self.run_search({"LinkedIn": jobs}, strict=True)
        assert {j["company"]: j["title_match"] for j in out["results"]} == {"A": False, "B": True}

    def test_several_job_titles_with_commas(self):
        jobs = [make_job("LinkedIn", "Games Programmer", "A"), make_job("LinkedIn", "Gameplay Engineer", "B"),
                make_job("LinkedIn", "Accountant", "C")]
        out, fake = self.run_search({"LinkedIn": jobs}, query="games programmer, gameplay engineer")
        assert {c[1] for c in fake.calls} == {"games programmer", "gameplay engineer"}
        assert {j["company"] for j in out["results"]} == {"A", "B"}

    def test_any_job_mode_keeps_everything(self):
        jobs = [make_job("LinkedIn", "Chef", "A"), make_job("LinkedIn", "Nurse", "B")]
        out, _ = self.run_search({"LinkedIn": jobs}, query="")
        assert len(out["results"]) == 2

    def test_same_job_on_two_boards_is_shown_once(self):
        out, _ = self.run_search({"LinkedIn": [make_job("LinkedIn", "Software Developer", "Acme Ltd")],
                                  "Indeed": [make_job("Indeed", "Software Developer", "Acme Ltd")]})
        assert len(out["results"]) == 1

    def test_jobs_without_a_link_are_dropped(self):
        j = make_job("LinkedIn", "Software Developer")
        j["url"] = ""
        out, _ = self.run_search({"LinkedIn": [j]})
        assert out["results"] == []

    def test_internship_search(self):
        """The 🎓 Internships button adds the word to the search and ranks internships first; nothing is dropped."""
        jobs = [make_job("Himalayas", "Software Developer Intern", "A", location="Remote · UK"),
                make_job("Himalayas", "Senior Software Developer", "B", location="Remote · UK")]
        out, fake = self.run_search({"Himalayas": jobs}, intern=True)
        assert [j["company"] for j in out["results"]] == ["A", "B"]
        assert "internship" in fake.calls[0][1], "boards without an internship filter get the word added"

    def test_screen_filters_never_narrow_what_boards_are_asked(self):
        """Date, job type, remote and salary filters hide results on screen; the boards always get the full search."""
        out, fake = self.run_search({"Reed": [make_job("Reed", "Software Developer")]},
                                    posted=7, jtype="parttime", remote="remote", salary_min=50000, local=False, strict=True)
        asked = fake.asked("Reed")[0][2]
        assert (asked["posted"], asked["jtype"], asked["remote"], asked["salary_min"]) == (0, "", "", 0)
        assert asked["local"] is True and asked["strict"] is False
        assert len(out["results"]) == 1

    def test_changing_a_filter_reuses_the_saved_results(self):
        boards = {"LinkedIn": [make_job("LinkedIn", "Software Developer")]}
        self.run_search(boards, fresh=True)
        _, fake = self.run_search(boards, fresh=False, posted=3, jtype="contract", salary_min=40000)
        assert fake.calls == [], "filters don't start a new search of the boards"

    def test_results_have_duration_and_score(self):
        out, _ = self.run_search({"LinkedIn": [make_job("LinkedIn", "Software Developer",
                                                        desc="This is a 6 month contract role")]})
        j = out["results"][0]
        assert (j["duration"], j["duration_m"]) == ("6-month contract", 6)
        assert j["score"] > 0


class SearchErrorTests(SearchTestCase):
    def test_board_errors_are_reported_not_crashing(self):
        boards = {"Reed": board_base.NeedsKey("add a key"), "Jobindex": board_base.NotHere("Denmark only"),
                  "ZipRecruiter": urllib.error.HTTPError("u", 403, "Forbidden", {}, None),
                  "LinkedIn": [make_job("LinkedIn", "Software Developer")]}
        out, _ = self.run_search(boards)
        st = out["status"]
        assert st["Reed"]["error"] == "needs key"
        assert st["Jobindex"]["error"] == "Denmark only"
        assert "key" not in st["ZipRecruiter"]["error"], "ZipRecruiter has no key, so don't blame one"
        assert st["LinkedIn"]["found"] == 1

    def test_rejected_key_is_reported_for_keyed_boards(self):
        out, _ = self.run_search({"Reed": urllib.error.HTTPError("u", 401, "Unauthorized", {}, None)})
        assert "key rejected" in out["status"]["Reed"]["error"]

    def test_results_are_cached_and_reused(self):
        boards = {"LinkedIn": [make_job("LinkedIn", "Software Developer")]}
        self.run_search(boards, fresh=True)
        out, fake = self.run_search(boards, fresh=False)
        assert fake.calls == [], "the second identical search should come from the cache"
        assert out["status"]["LinkedIn"]["cached"]

    def test_address_and_town_share_the_cache(self):
        boards = {"LinkedIn": [make_job("LinkedIn", "Software Developer")]}
        self.run_search(boards, where="Birmingham", fresh=True)
        _, fake = self.run_search(boards, where="12 Colmore Row, Birmingham B3 2BJ", fresh=False)
        assert fake.calls == []


class DataFileTests:
    def test_profile_saved_with_bom_still_loads(self):
        """Some Windows editors put a hidden marker (BOM) at the start of a file; the profile must still load."""
        pstore.PROFILE_FILE.write_text("﻿" + json.dumps({"city": "Coventry", "postcode": "CV1 2AB"}), encoding="utf-8")
        try:
            assert pstore.load_profile().get("city") == "Coventry"
        finally:
            pstore.PROFILE_FILE.unlink(missing_ok=True)


class ContractLengthTests:
    def check(self, text, label, months):
        assert contract.contract_length({"title": text, "type": "", "desc": ""}) == (label, months), text

    def test_lengths(self):
        self.check("6 month contract", "6-month contract", 6)
        self.check("12-month fixed term contract", "12-month fixed term", 12)
        self.check("Maternity cover", "Maternity cover", 12)
        self.check("Permanent role", "Permanent", 1000)
        self.check("Temporary assistant", "Contract", 500)
        self.check("Software developer", "", None)


# ------------------------------------------------------------------ the app's own web API

class ApiTests(SearchTestCase):
    @classmethod
    def setup_class(cls):
        cls.app = AppServer()

    @classmethod
    def teardown_class(cls):
        cls.app.close()

    def setup_method(self):
        super().setup_method()
        runtime.state["port"] = self.app.port

    def get(self, path):
        code, data = self.app.get(path)
        assert code == 200, data
        return data

    @offline
    def test_place_endpoint(self):
        r = self.get("/api/place?q=12+Colmore+Row%2C+Birmingham+B3+2BJ&country=GB")
        assert (r["town"], r["postcode"], r["country_code"]) == ("Birmingham", "B3 2BJ", "GB")
        assert self.get("/api/place?q=&country=GB")["town"] == ""

    def test_search_endpoint_with_an_address(self):
        fake = FakeBoards({"LinkedIn": [make_job("LinkedIn", "Software Developer")]})
        with fake.installed(), \
                mock.patch.object(places, "lookup_postcode", side_effect=fake_lookup), \
                mock.patch.object(osm, "nominatim", side_effect=OSError("offline")):
            r = self.get("/api/search?q=software+developer&where=12+Colmore+Row%2C+Birmingham+B3+2BJ"
                         "&country=GB&sources=LinkedIn&fresh=1")
        assert len(r["results"]) == 1
        assert fake.calls[0][2]["where"] == "Birmingham"

    def test_search_endpoint_needs_a_query(self):
        assert self.get("/api/search?q=&country=GB")["results"] == []

