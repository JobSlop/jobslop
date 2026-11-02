"""Reading CVs: PDF and Word files, UK / US / Dutch layouts, OCR for drawn or scanned CVs."""
import sys
from pathlib import Path
from unittest import mock

from support import TMP, make_docx, make_pdf, reset_data

from jobslop.profile import cvparse, cvtext, ocr

UK_CV = """Sarah Jane Thompson
12 Elm Grove, Coventry CV1 2AB
07700 900123 | sarah.thompson@gmail.com | linkedin.com/in/sarahthompson
PROFILE
Games programmer with 5 years of experience building gameplay systems in C++ and Unity.
EXPERIENCE
Senior Gameplay Programmer
Playground Games, Leamington Spa
March 2021 - Present
• Built combat systems in C++
• Mentored two junior programmers
Gameplay Programmer
Codemasters, Southam
June 2019 - February 2021
• Worked on vehicle handling
EDUCATION
BSc (Hons) Computer Games Programming, Staffordshire University
2016 - 2019
SKILLS
C++, Unity, Unreal Engine, Python, Git
Full UK driving licence. Notice period: 1 month
"""

US_CV = """MICHAEL J. RODRIGUEZ
Austin, TX 78701 | (512) 555-0147 | mike.rodriguez@outlook.com | github.com/mrodriguez
SUMMARY
Data analyst with SQL and Python experience.
WORK EXPERIENCE
Data Analyst, Dell Technologies — Round Rock, TX
Jan 2022 – Present
- Built dashboards in Tableau
Marketing Intern, Kraft Heinz — Chicago, IL
May 2021 – Aug 2021
EDUCATION
Bachelor of Science in Statistics, University of Texas at Austin, 2021
SKILLS
SQL, Python, Tableau, Excel
"""

NL_CV = """Curriculum Vitae
Jan de Vries
Damrak 1, 1012 LG Amsterdam
+31 6 12345678
jan.devries@ziggo.nl
WERKERVARING
Software Ontwikkelaar
Bol.com, Utrecht
jan 2020 - heden
OPLEIDING
HBO Informatica, Hogeschool Utrecht, 2015 - 2019
VAARDIGHEDEN
Java, Kotlin, SQL
"""


class CvTestCase:
    def check_fields(self, found, expected):
        for k, v in expected.items():
            assert found.get(k) == v, f"field {k!r}"


class UkCvTests(CvTestCase):
    @classmethod
    def setup_class(cls):
        cls.cv = cvparse.parse_text(UK_CV)

    def test_contact_details(self):
        self.check_fields(self.cv, {"first_name": "Sarah", "middle_name": "Jane", "last_name": "Thompson",
                                    "email": "sarah.thompson@gmail.com", "phone": "07700 900123",
                                    "linkedin": "https://linkedin.com/in/sarahthompson"})

    def test_address(self):
        self.check_fields(self.cv, {"address1": "12 Elm Grove", "city": "Coventry", "postcode": "CV1 2AB",
                                    "country": "United Kingdom"})

    def test_jobs(self):
        jobs = self.cv["jobs"]
        assert len(jobs) == 2
        assert {k: jobs[0][k] for k in ("title", "company", "location", "start", "end")} == \
                         {"title": "Senior Gameplay Programmer", "company": "Playground Games", "location": "Leamington Spa",
                          "start": "March 2021", "end": "Present"}
        assert "Built combat systems" in jobs[0]["description"]
        assert (jobs[1]["company"], jobs[1]["location"], jobs[1]["end"]) == ("Codemasters", "Southam", "February 2021")
        self.check_fields(self.cv, {"current_title": "Senior Gameplay Programmer", "current_company": "Playground Games"})

    def test_education_skills_and_extras(self):
        self.check_fields(self.cv, {"highest_qualification": "BSc", "degree_subject": "Computer Games Programming",
                                    "university": "Staffordshire University", "skills": "C++, Unity, Unreal Engine, Python, Git",
                                    "driving_licence": "Yes", "notice_period": "1 month"})
        assert self.cv["years_experience"].isdigit()


class UsCvTests(CvTestCase):
    @classmethod
    def setup_class(cls):
        cls.cv = cvparse.parse_text(US_CV)

    def test_contact_and_address(self):
        self.check_fields(self.cv, {"first_name": "Michael", "middle_name": "J.", "last_name": "Rodriguez",
                                    "email": "mike.rodriguez@outlook.com", "phone": "(512) 555-0147",
                                    "github": "https://github.com/mrodriguez", "city": "Austin", "county": "TX",
                                    "postcode": "78701", "country": "United States"})

    def test_jobs_on_one_line(self):
        """US style: 'Title, Company — City, ST' on a single line."""
        jobs = self.cv["jobs"]
        assert [(j["title"], j["company"], j["location"]) for j in jobs] == \
                         [("Data Analyst", "Dell Technologies", "Round Rock, TX"),
                          ("Marketing Intern", "Kraft Heinz", "Chicago, IL")]
        assert (jobs[1]["start"], jobs[1]["end"]) == ("May 2021", "Aug 2021")

    def test_education(self):
        self.check_fields(self.cv, {"highest_qualification": "Bachelor's degree", "degree_subject": "Statistics",
                                    "university": "University of Texas at Austin"})

    def test_us_dates_with_day(self):
        """'January 18th – May 2023' (day after the month) is a date range."""
        cv = cvparse.parse_text("Irene Valle\nirene@example.com\nEXPERIENCE\nData Visualization Intern, NASCAR\n"
                           "January 18th – May 2023\n• Built charts\n")
        assert (cv["jobs"][0]["start"], cv["jobs"][0]["end"]) == ("January 2023", "May 2023")

    def test_country_from_phone_when_no_address(self):
        cv = cvparse.parse_text("Jane Doe\njane@example.com\n+1 512 555 0147\n")
        assert cv.get("country") == "United States"


class DutchCvTests(CvTestCase):
    def test_dutch_cv(self):
        cv = cvparse.parse_text(NL_CV)
        self.check_fields(cv, {"first_name": "Jan", "last_name": "de Vries", "email": "jan.devries@ziggo.nl",
                               "phone": "+31 6 12345678", "address1": "Damrak 1", "postcode": "1012 LG", "city": "Amsterdam",
                               "country": "Netherlands", "skills": "Java, Kotlin, SQL", "university": "Hogeschool Utrecht"})
        assert (cv["jobs"][0]["title"], cv["jobs"][0]["company"], cv["jobs"][0]["end"]) == \
                         ("Software Ontwikkelaar", "Bol.com", "Present")

    def test_curriculum_vitae_is_not_a_name(self):
        assert cvparse.parse_text(NL_CV).get("first_name") != "Curriculum"


class FileTests(CvTestCase):
    def setup_method(self):
        reset_data()

    def write(self, name, data):
        p = Path(TMP) / name
        p.write_bytes(data)
        return p

    def test_pdf_cv(self):
        p = self.write("cv.pdf", make_pdf(["**Sarah Jane Thompson"] + UK_CV.splitlines()[1:]))
        with mock.patch.object(cvparse, "ocr_pdf", return_value=[]) as ocr:
            cv = cvparse.parse_cv(p)
        self.check_fields(cv, {"first_name": "Sarah", "last_name": "Thompson", "postcode": "CV1 2AB",
                               "university": "Staffordshire University"})
        assert len(cv["jobs"]) == 2
        ocr.assert_not_called()          # a normal PDF doesn't need OCR

    def test_word_cv(self):
        p = self.write("cv.docx", make_docx(["**Sarah Jane Thompson"] + UK_CV.splitlines()[1:]))
        cv = cvparse.parse_cv(p)
        self.check_fields(cv, {"first_name": "Sarah", "email": "sarah.thompson@gmail.com", "city": "Coventry"})
        assert cv["jobs"][1]["location"] == "Southam"

    def test_text_cv(self):
        p = self.write("cv.txt", UK_CV.encode("utf-8"))
        assert cvparse.parse_cv(p).get("last_name") == "Thompson"

    def test_drawn_name_is_read_with_ocr(self):
        """CVs whose name and email are drawn as shapes: OCR fills in what the text layer lacks."""
        body = UK_CV.splitlines()[3:]                      # no name, address or email in the text layer
        p = self.write("drawn.pdf", make_pdf(body))
        W = 1785
        ocr_lines = [{"t": "SARAH THOMPSON", "x": 150, "y": 100, "h": 60, "page": 0, "w": W},
                     {"t": "EMAIL", "x": 1200, "y": 300, "h": 20, "page": 0, "w": W},
                     {"t": "sarah.thompson@gmail.com", "x": 1200, "y": 340, "h": 20, "page": 0, "w": W},
                     {"t": "LOCATION", "x": 1200, "y": 420, "h": 20, "page": 0, "w": W},
                     {"t": "Coventry", "x": 1200, "y": 460, "h": 20, "page": 0, "w": W},
                     {"t": "Games programmer with C++ experience.", "x": 150, "y": 500, "h": 20, "page": 0, "w": W}]
        with mock.patch.object(cvparse, "ocr_pdf", return_value=ocr_lines):
            cv = cvparse.parse_cv(p)
        self.check_fields(cv, {"first_name": "Sarah", "last_name": "Thompson", "email": "sarah.thompson@gmail.com",
                               "read_with_ocr": "yes"})
        assert len(cv["jobs"]) == 2, "jobs from the text layer are kept"

    def test_ocr_pairs_labels_with_values(self):
        """Stacked fields: a label with its value underneath, or beside it."""
        W = 1785
        text, _ = cvparse.ocr_to_text([
            {"t": "PHONE", "x": 100, "y": 100, "h": 20, "page": 0, "w": W},
            {"t": "07700 900123", "x": 100, "y": 135, "h": 20, "page": 0, "w": W},
            {"t": "Email:", "x": 100, "y": 220, "h": 20, "page": 0, "w": W},
            {"t": "me@example.com", "x": 300, "y": 222, "h": 20, "page": 0, "w": W}])
        assert "Phone: 07700 900123" in text
        assert "Email: me@example.com" in text

    def test_ocr_is_windows_only(self):
        with mock.patch.object(sys, "platform", "darwin"):
            assert ocr.ocr_pdf("whatever.pdf") == []


class PieceTests:
    def test_find_phone(self):
        assert cvparse.find_phone("Call 07911 123456 today", ["GB"]) == "07911 123456"
        assert cvparse.find_phone("Tel: +44 7911 123456", ["GB"], with_region=True) == ("+44 7911 123456", "GB")
        assert cvparse.find_phone("Bel +31 6 12345678", ["GB", "NL"], with_region=True) == ("+31 6 12345678", "NL")
        assert cvparse.find_phone("Daytona Beach, FL 32114 (407) 701-0378", ["US"]) == "(407) 701-0378"
        assert not cvparse.find_phone("Born 2019, ID 12345", ["GB"])

    def test_street_and_flat(self):
        out = {}
        cvparse.split_street("Flat 3, 22 London Road", out)
        assert (out.get("address1"), out.get("address2")) == ("22 London Road", "Flat 3")

    def test_place_detection(self):
        assert cvparse.is_place("Birmingham")
        assert cvparse.is_place("Austin, TX")
        assert cvparse.is_place("Kensington, London")
        assert not cvparse.is_place("Hilton, Southam"), "a company name and a town in different countries"
        assert not cvparse.is_place("Marketing Intern, Kraft Heinz — Chicago, IL")

    def test_job_heading_split(self):
        assert cvparse.split_header(["Gameplay Programmer", "Codemasters, Southam"]) == \
                         ("Gameplay Programmer", "Codemasters", "Southam")
        assert cvparse.split_header(["Receptionist, Hilton"]) == ("Receptionist", "Hilton", ""), \
                         "a company that shares its name with a town stays the company"
        assert cvparse.split_header(["Engineer, Rolls-Royce, Derby"]) == ("Engineer", "Rolls-Royce", "Derby")

    def test_dates(self):
        assert cvparse.find_dates("March 2021 - Present")[:2] == ("March 2021", "Present")
        assert cvparse.find_dates("06/2019 – 02/2021")[:2] == ("06/2019", "02/2021")
        assert cvparse.find_dates("No dates at all") is None

    def test_clean_text(self):
        assert cvtext.clean_text("Phone07700900123Email") == "Phone07700900123 Email"

