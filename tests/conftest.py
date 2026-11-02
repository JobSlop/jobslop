"""pytest set-up: importing support first points jobslop at a temporary data folder, so no test
ever reads or changes your real profile, saved jobs or settings."""
import importlib.util
import sys

import pytest

import support

# packages the CV reader needs; without them several tests fail in confusing ways
NEEDED = {"pypdf": "pypdf", "pdfminer": "pdfminer.six", "phonenumbers": "phonenumbers"}


def pytest_sessionstart(session):
    missing = [pkg for mod, pkg in NEEDED.items() if importlib.util.find_spec(mod) is None]
    if missing:
        pytest.exit(f"This Python ({sys.executable}) is missing {', '.join(missing)}.\n"
                    "Install them with:  python -m pip install -r requirements.txt\n"
                    "(in PyCharm: open requirements.txt and click 'Install requirements')", returncode=4)


@pytest.fixture
def clean_data():
    """An empty jobslop data folder for one test."""
    support.reset_data()
    yield support.jf
    support.reset_data()


@pytest.fixture(scope="class")
def app_server():
    """jobslop's own web server on a free port, for a whole test class."""
    app = support.AppServer()
    support.jf.state["port"] = app.port
    yield app
    app.close()
