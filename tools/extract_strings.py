"""List the screen's English text, for making language packs:  python tools/extract_strings.py [out.json]

Collects text and labels from ui/index.html, plus text in the screen's scripts: quoted strings and the
text between tags in templates. ${...} in templates becomes {0}, {1}... (the translator matches those).
The result is a sorted list; a language pack's ui.json maps each of them to its translation.
"""
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ATTRS = ("placeholder", "title", "data-tip", "aria-label", "alt")
WORDY = re.compile(r"[A-Za-z]{2}")
CODEISH = re.compile(r"^[#.\[\]$/@{}()=:;,\w-]+$|^https?:|\.(js|css|png|json)\b|^[a-z_]+$|^[a-z]+[A-Z]\w*$|=>|&&|\|\|")
CODE_BITS = re.compile(r"function|querySelector|=>|\.join|\$\$\(|\bconst |;|=\"|\dpx|:not\(|\b(var|let)\b|//|\{\d\}&|\?\w+=")
HOLE = "⁣"          # stands for ${...} while reading a template (an invisible character no text uses)


def keep(s: str) -> bool:
    s = s.strip()
    if not s or len(s) > 400 or not WORDY.search(s):
        return False
    if CODEISH.search(s) and " " not in s:
        return False
    if s.startswith(("<", "--", "{", "#", ".", "[", "/", "(prefers", ")", "+k", ",")) or "${" in s:
        return False
    if CODE_BITS.search(s):
        return False
    if re.fullmatch(r"[a-z]+( [a-z]+)?", s) and len(s) < 18 and s != "a job":
        return False                       # class names like "f wide", single code words
    return True


class Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.found, self.skip = set(), 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skip += 1
        for k, v in attrs:
            if k in ATTRS and v and keep(v):
                self.found.add(v.strip())

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.skip -= 1

    def handle_data(self, data):
        if not self.skip and keep(data):
            self.found.add(" ".join(data.split()))


def scan(js: str) -> tuple[list[str], list[str]]:
    """(quoted strings, template literal texts) in JS. Templates have HOLE for each ${...};
    templates inside ${...} are found too."""
    found: list[str] = []
    strings: list[str] = []

    def code(i: int, stop: str | None) -> int:
        """Read code from i until `stop` ("}" closing a ${) at depth 0; returns the index after it."""
        depth = 0
        while i < len(js):
            c = js[i]
            if c in "\"'":
                i = skip_string(i, c)
                continue
            if c == "/" and js.startswith("//", i):
                i = js.find("\n", i)
                i = len(js) if i < 0 else i
                continue
            if c == "`":
                i = template(i + 1)
                continue
            if c == "{":
                depth += 1
            elif c == "}":
                if depth == 0 and stop == "}":
                    return i + 1
                depth -= 1
            i += 1
        return i

    def skip_string(i: int, q: str) -> int:
        start = i = i + 1
        while i < len(js) and js[i] not in (q, "\n"):
            i += 2 if js[i] == "\\" else 1
        strings.append(js[start:i].replace("\\" + q, q))
        return i + 1

    def template(i: int) -> int:
        text = ""
        while i < len(js) and js[i] != "`":
            if js[i] == "\\":
                text += js[i + 1:i + 2]
                i += 2
            elif js.startswith("${", i):
                text += HOLE
                i = code(i + 2, "}")
            else:
                text += js[i]
                i += 1
        found.append(text)
        return i + 1

    code(0, None)
    return strings, found


def template_text(js: str) -> set[str]:
    """Visible text in JS: string literals, and text runs inside template literals."""
    out = set()
    strings, texts = scan(js)
    for s in strings:
        if keep(s) and " " in s and not re.search(r"[<>]|\\[nu]", s):
            out.add(s)
    for text in texts:
        for part in re.split(r"<[^>]*>", text):
            holes = iter(range(100))
            s = re.sub(HOLE, lambda _: "{" + str(next(holes)) + "}", " ".join(part.split())).strip()
            if keep(s.replace("{", "").replace("}", "")) and len(re.sub(r"\{\d+\}", "", s).strip()) > 1 \
                    and (not s.startswith(("{", ":")) or re.match(r"\{\d+\} [a-z]", s)):
                out.add(s)
        for attr in ATTRS:
            for a in re.finditer(attr + r'="([^"$<>' + HOLE + r']{2,200})"', text):
                if keep(a[1]):
                    out.add(a[1].strip())
    return out


def main():
    page = Page()
    page.feed((ROOT / "ui" / "index.html").read_text(encoding="utf-8"))
    found = set(page.found)
    for f in sorted((ROOT / "ui" / "js").glob("*.js")) + sorted((ROOT / "plugins").glob("*/ui.js")):
        found |= template_text(f.read_text(encoding="utf-8"))
    words = sorted(found, key=str.lower)
    if len(sys.argv) > 1:
        Path(sys.argv[1]).write_text(json.dumps(words, indent=1, ensure_ascii=False), encoding="utf-8")
    print(len(words), "strings")


if __name__ == "__main__":
    main()
