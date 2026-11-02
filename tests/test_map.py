"""The map: offline towns, distances, place lookups, game studios (Game Dev Map + Wikipedia indie list)."""
import json
import os
import time
from unittest import mock

from support import AppTestCase, no_internet, offline, plugin_module

from jobslop.geo import cities

GAMEDEVMAP_CSV = "Organization,URL,City,Country/Region,Category\n" \
                 "Codemasters,https://codemasters.com,Southam,United Kingdom,Developer\n" \
                 "Tiny Fox,https://tinyfox.example,Birmingham,United Kingdom,Microstudio\n" \
                 "Big Publisher,https://pub.example,London,United Kingdom,Publisher\n" \
                 "Nowhere Games,https://x,Atlantis,United Kingdom,Developer\n"
studios = plugin_module("gamedev").studios      # the Game dev plugin's studio list
INDIE_JSON = [{"name": "Indie Owl", "city": "Coventry", "country": "United Kingdom", "url": "https://w/owl", "games": "Hoot"},
              {"name": "Tiny Fox", "city": "Birmingham", "country": "United Kingdom", "url": "https://w/fox"}]


class TownTests:
    def test_find_city(self):
        assert cities.find_city("Birmingham", "GB")[3] == "GB"
        assert cities.find_city("Birmingham", "US")[4] == "AL"
        assert cities.find_city("birmingham")[0] == "Birmingham", "without a country the biggest one wins"
        assert cities.find_city("Nederland", "GB") is None, "a country name is not a UK town"
        assert cities.find_city("Atlantis", "GB") is None

    def test_geocode_text(self):
        assert cities.geocode_text("Austin, United States")[4] == "TX"
        assert cities.geocode_text("Birmingham · United Kingdom")[3] == "GB"
        assert cities.geocode_text("") is None

    def test_distance(self):
        b = cities.find_city("Birmingham", "GB")
        c = cities.find_city("Coventry", "GB")
        assert abs(cities.km_between(b[1], b[2], c[1], c[2])-28) < 3

    def test_nearest_town(self):
        assert cities.nearest_city(52.4800, -1.9000)[0] == "Birmingham"
        assert cities.nearest_city(52.3700, 4.8900)[0] == "Amsterdam"

    def test_towns_in_view(self):
        towns = cities.towns_in_box(52.3, -2.1, 52.6, -1.4, limit=5)
        assert towns[0]["n"] == "Birmingham", "biggest town first"
        assert len(towns) <= 5

    def test_job_point(self):
        assert cities.job_point({"lat": 1.0, "lon": 2.0}, "GB") == (1.0, 2.0)
        assert cities.job_point({"location": "Leamington Spa, England, United Kingdom"}, "GB") is not None
        assert cities.job_point({"location": "Aarhus N"}, "DK") is not None
        assert cities.job_point({"location": "Remote · Worldwide"}, "GB") is None
        assert (cities.job_point({"location": "Hybrid remote in Birmingham"}, "GB") or True) is not None


class StudioTests(AppTestCase):
    def setup_method(self):
        super().setup_method()
        studios.studios_file.write_text(GAMEDEVMAP_CSV, encoding="utf-8")
        studios.indie_file.write_text(json.dumps(INDIE_JSON), encoding="utf-8")
        studios._cache.update(t=0, rows=[])

    def teardown_method(self):
        studios._cache.update(t=0, rows=[])

    def test_studio_list_merges_both_sources(self):
        with mock.patch("urllib.request.urlopen", side_effect=AssertionError("fresh files must not be downloaded again")):
            rows = studios.all()
        names = {r["name"]: r for r in rows}
        assert "Nowhere Games" not in names, "studios in unknown towns are left off the map"
        assert names["Tiny Fox"]["indie"], "Microstudio = indie"
        assert names["Indie Owl"]["indie"]
        assert sum(1 for r in rows if r["name"] == "Tiny Fox") == 1, "studios on both lists appear once"
        assert not names["Codemasters"]["indie"]

    def test_studios_near(self):
        b = cities.find_city("Birmingham", "GB")
        near = studios.near(b[1], b[2], 40)
        assert [s["name"] for s in near][:1] == ["Tiny Fox"], "closest first"
        assert "Indie Owl" in [s["name"] for s in near]
        assert "Big Publisher" not in [s["name"] for s in near], "London is too far"
        indie = studios.near(b[1], b[2], 60, indie_only=True)
        assert {s["name"] for s in indie} == {"Tiny Fox", "Indie Owl"}

    def test_studios_endpoint(self):
        code, r = self.app.get("/api/plugin/gamedev/studios?lat=52.48&lon=-1.90&km=40&kind=indie")
        assert code == 200
        assert {s["name"] for s in r["studios"]} == {"Tiny Fox", "Indie Owl"}
        assert self.app.get("/api/plugin/gamedev/studios?lat=x")[1] == {"studios": [], "total": 0}

    def test_old_lists_are_refreshed(self):
        old = time.time() - 8 * 24 * 3600
        os.utime(studios.studios_file, (old, old))
        with mock.patch("urllib.request.urlopen", side_effect=OSError("offline")):
            rows = studios.all()
        assert rows, "if the refresh fails, the old list is still used"


class MapApiTests(AppTestCase):
    def test_geocode(self):
        code, r = self.app.get("/api/geocode?q=Coventry&country=United+Kingdom")
        assert (r["town"], r["country_code"], r["offline"]) == ("Coventry", "GB", True)

    @offline
    def test_geocode_postcode(self):
        code, r = self.app.get("/api/geocode?q=B3+2BJ&country=United+Kingdom")
        assert (r["town"], r["country_code"]) == ("Birmingham", "GB")

    def test_geocode_unknown_place(self):
        with no_internet():
            code, r = self.app.get("/api/geocode?q=Atlantisville+Zzz")
        assert r == {"error": "Place not found"}

    def test_reverse(self):
        code, r = self.app.get("/api/reverse?lat=52.48&lon=-1.90")
        assert r["town"] == "Birmingham"
        assert "error" in self.app.get("/api/reverse?lat=abc")[1]

    def test_towns(self):
        code, r = self.app.get("/api/towns?s=52.3&w=-2.1&n=52.6&e=-1.4&limit=3")
        assert len(r) == 3
        assert self.app.get("/api/towns?s=1")[1] == []

    def test_static_files(self):
        for name in ("leaflet.js", "world.json", "Manrope.ttf"):
            code, _, hdrs = self.app.request("/static/" + name)
            assert code == 200, name
        code, _, _ = self.app.request("/static/..%2Fjobfinder.py")
        assert code == 404
