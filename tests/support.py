"""Shared set-up for jobslop's tests.

Importing this module points jobslop at a temporary data folder BEFORE the app is imported,
so tests never read or change your real profile, saved jobs or settings. Nothing here uses the
internet: job boards, postcode lookups and OpenStreetMap are replaced with fakes.
"""
import base64
import io
import json
import os
import sys
import tempfile
import threading
import urllib.request
import zipfile
from pathlib import Path
from unittest import mock

TMP = tempfile.mkdtemp(prefix="jobfinder-tests-")
import atexit, shutil  # noqa: E401,E402
atexit.register(shutil.rmtree, TMP, True)          # tidy up the temporary data folder afterwards
for _var in ("APPDATA", "HOME", "XDG_DATA_HOME", "USERPROFILE"):
    os.environ[_var] = TMP
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import jobfinder as jf  # noqa: E402

assert str(jf.DATA_DIR).startswith(TMP), "tests must not use the real jobslop data folder"

# exact spots for the postcodes used in tests, instead of asking postcodes.io / OpenStreetMap
FAKE_POSTCODES = {
    ("GB", "B3 2BJ"): (52.4820, -1.9020), ("GB", "B32BJ"): (52.4820, -1.9020), ("GB", "B3"): (52.4830, -1.9010),
    ("GB", "CV1"): (52.4080, -1.5100), ("GB", "CV1 2AB"): (52.4080, -1.5100),
    ("US", "32114"): (29.2000, -81.0300), ("US", "78701"): (30.2700, -97.7400),
    ("NL", "1012 AB"): (52.3740, 4.8900), ("NL", "1012 LG"): (52.3760, 4.8950),
    ("DK", "8000"): (56.1570, 10.2100), ("DE", "10115"): (52.5320, 13.3840),
}


def fake_lookup(pc, cc):
    return FAKE_POSTCODES.get((cc, pc)) or FAKE_POSTCODES.get((cc, pc.replace(" ", "")))


def no_internet():
    """Context manager: postcodes from the table above, OpenStreetMap and other web calls fail."""
    from contextlib import ExitStack
    stack = ExitStack()
    stack.enter_context(mock.patch.object(jf, "lookup_postcode", side_effect=fake_lookup))
    stack.enter_context(mock.patch.object(jf, "nominatim", side_effect=OSError("no internet in tests")))
    jf._places["mem"].clear()
    return stack


def offline(fn):
    """Decorator version of no_internet()."""
    def wrapper(self, *a, **k):
        with no_internet():
            return fn(self, *a, **k)
    wrapper.__name__ = fn.__name__
    wrapper.__doc__ = fn.__doc__
    return wrapper


def reset_data():
    """Empty data folder: no profile, settings, saved jobs, cache or CV."""
    for f in (jf.CACHE_FILE, jf.SETTINGS_FILE, jf.SAVED_FILE, jf.PROFILE_FILE, jf.PLACES_FILE, jf.RATES_FILE):
        f.unlink(missing_ok=True)
    import shutil
    shutil.rmtree(jf.CV_DIR, ignore_errors=True)
    jf._places["mem"].clear()
    jf._places["disk"] = None
    jf.state.update(active=None, ext_seen=0.0)


def make_job(source, title, company="Acme", location="Birmingham, UK", desc="", url=None, **extra):
    j = jf.job(source, title, company, url or f"https://example.com/{source}/{title.replace(' ', '-')}/{company}",
               location=location, desc=desc)
    j.update(extra)
    return j


def base_opts(**over):
    o = {"where": "", "country": "GB", "local": True, "strict": False, "miles": 15, "posted": 0,
         "jtype": "", "remote": "", "salary_min": 0}
    o.update(over)
    return o


class FakeBoards:
    """Stands in for the real job boards: returns set jobs and records what each board was asked."""

    def __init__(self, jobs_by_board):
        self.jobs_by_board = jobs_by_board
        self.calls = []

    def sources(self):
        def make(name):
            def src(q, o):
                self.calls.append((name, q, dict(o)))
                result = self.jobs_by_board[name]
                if isinstance(result, Exception):
                    raise result
                return [dict(j) for j in result]
            return src
        return {name: make(name) for name in self.jobs_by_board}

    def asked(self, name):
        return [c for c in self.calls if c[0] == name]


class FakeResponse(io.BytesIO):
    """What urllib.request.urlopen returns, for faking web pages."""

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def fake_urlopen(pages):
    """urlopen replacement: pages maps a piece of the URL -> response text (first match wins)."""
    def opener(req, *a, **k):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        for part, body in pages.items():
            if part in url:
                if isinstance(body, Exception):
                    raise body
                return FakeResponse(body.encode("utf-8") if isinstance(body, str) else body)
        raise AssertionError(f"unexpected web request in a test: {url}")
    return opener


def b64(data):
    return base64.b64encode(data if isinstance(data, bytes) else data.encode("utf-8")).decode()


def make_zip(files):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, text in files.items():
            z.writestr(name, text)
    return buf.getvalue()


def make_docx(paragraphs):
    """A minimal Word document with the given paragraphs (strings; '**text' makes it bold)."""
    def para(t):
        bold = t.startswith("**")
        t = t[2:] if bold else t
        t = t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        rpr = "<w:rPr><w:b/><w:sz w:val=\"28\"/></w:rPr>" if bold else ""
        return f'<w:p><w:r>{rpr}<w:t xml:space="preserve">{t}</w:t></w:r></w:p>'
    body = "".join(para(p) for p in paragraphs)
    return make_zip({
        "[Content_Types].xml": '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                               '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                               '<Default Extension="xml" ContentType="application/xml"/>'
                               '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>',
        "_rels/.rels": '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                       '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>',
        "word/document.xml": '<?xml version="1.0" encoding="UTF-8"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                             f"<w:body>{body}</w:body></w:document>",
    })


def make_pdf(lines):
    """A minimal real PDF with one line of text per entry (Helvetica; '**text' = big bold heading line)."""
    y, ops = 800, []
    for t in lines:
        big = t.startswith("**")
        t = t[2:] if big else t
        t = t.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        ops.append(f"BT /{'F2' if big else 'F1'} {20 if big else 10} Tf 50 {y} Td ({t}) Tj ET")
        y -= 26 if big else 14
    content = "\n".join(ops).encode("cp1252")             # = the PDF WinAnsi encoding
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R "
            b"/Resources << /Font << /F1 5 0 R /F2 6 0 R >> >> >>",
            b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"\nendstream",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>"]
    out, offsets = io.BytesIO(), []
    out.write(b"%PDF-1.4\n")
    for i, o in enumerate(objs, 1):
        offsets.append(out.tell())
        out.write(f"{i} 0 obj\n".encode() + o + b"\nendobj\n")
    xref = out.tell()
    out.write(f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode())
    for off in offsets:
        out.write(f"{off:010d} 00000 n \n".encode())
    out.write(f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode())
    return out.getvalue()


class AppServer:
    """Runs jobslop's own web server (the one the app window talks to) on a free port."""

    def __init__(self, handler=None):
        from http.server import ThreadingHTTPServer
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler or jf.Handler)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()

    def request(self, path, body=None, headers=None, method=None):
        """Returns (status, parsed JSON or text, response headers)."""
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", data=data, method=method,
                                     headers={"Content-Type": "application/json", **(headers or {})})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                raw, code, hdrs = r.read(), r.status, r.headers
        except urllib.error.HTTPError as e:
            raw, code, hdrs = e.read(), e.code, e.headers
        text = raw.decode("utf-8", "replace")
        try:
            return code, json.loads(text), hdrs
        except ValueError:
            return code, text, hdrs

    def get(self, path, **k):
        code, data, _ = self.request(path, **k)
        return code, data

    def post(self, path, body, **k):
        code, data, _ = self.request(path, body=body, **k)
        return code, data


class AppTestCase:
    """A test with a clean data folder and the app's web server running."""

    @classmethod
    def setup_class(cls):
        cls.app = AppServer()
        jf.state["port"] = cls.app.port

    @classmethod
    def teardown_class(cls):
        cls.app.close()

    def setup_method(self):
        reset_data()
        jf.state["port"] = self.app.port
