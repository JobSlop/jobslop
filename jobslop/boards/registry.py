"""Every job board the app can search, and what the search needs to know about each."""

import threading

from jobslop.boards.country import src_jobbird, src_jobindex, src_jobs2careers, src_usajobs, src_ziprecruiter_uk
from jobslop.boards.jobspy import src_glassdoor, src_indeed
from jobslop.boards.keyed import src_adzuna, src_reed
from jobslop.boards.linkedin import src_linkedin
from jobslop.boards.remote import src_arbeitnow, src_himalayas, src_jobicy, src_remoteok, src_remotive
from jobslop.boards.special import src_acca, src_artstation, src_icaew, src_workwithindies
from jobslop.config import DATA_DIR

SOURCES = {
    "Reed": src_reed,
    "Adzuna": src_adzuna,
    "LinkedIn": src_linkedin,
    "Indeed": src_indeed,
    "Glassdoor": src_glassdoor,
    # US ZipRecruiter via JobSpy refuses UK connections; the UK site works, so that's used for the UK
    "ZipRecruiter": src_ziprecruiter_uk,
    "Jobs2Careers": src_jobs2careers,
    "USAJOBS": src_usajobs,
    "Jobindex": src_jobindex,
    "Jobbird": src_jobbird,
    "ArtStation": src_artstation,
    "WorkWithIndies": src_workwithindies,
    "ICAEW": src_icaew,
    "ACCA": src_acca,
    "Himalayas": src_himalayas,
    "Jobicy": src_jobicy,
    "Remotive": src_remotive,
    "RemoteOK": src_remoteok,
    "Arbeitnow": src_arbeitnow,
}
# How long to reuse results before asking a site again (seconds)
CACHE_TTL = {"LinkedIn": 3600, "Indeed": 3 * 3600, "Glassdoor": 3 * 3600}
DEFAULT_TTL = 15 * 60
CACHE_FILE = DATA_DIR / "cache.json"
cache_lock = threading.Lock()
COUNTRY_NATIVE = {"Reed", "Adzuna", "LinkedIn", "Indeed", "Glassdoor", "ZipRecruiter", "Jobs2Careers",
                  "USAJOBS", "Jobindex", "Jobbird", "ICAEW", "ACCA"}       # already limited to the chosen country
LOCATION_AWARE = COUNTRY_NATIVE - {"ICAEW", "ACCA"}                      # these also search around a town themselves
KEYED_SOURCES = {"Reed", "Adzuna", "USAJOBS"}                             # a 401/403 from these means a bad key
COUNTRY_PARAM = {"Himalayas", "Jobicy"}                                  # filtered by the board itself (mostly)
