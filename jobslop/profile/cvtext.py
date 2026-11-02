"""Getting the text out of a CV (PDF or Word), including joined letters (ligatures)."""

import gzip
import re
from pathlib import Path

from jobslop.config import RES_DIR

# ---- read details out of a CV (PDF or Word) to pre-fill the profile

LIG_CANDIDATES = ("ti", "tt", "ft", "tti", "fti")   # joined letters that have no text code of their own
LIG_DEFAULT_W = {"t": 335, "i": 229, "f": 305}      # Calibri, used when the CV gives no widths to compare with
_lig_words = None


def lig_words():
    global _lig_words
    if _lig_words is None:
        try:
            with gzip.open(RES_DIR / "static" / "ligwords.txt.gz", "rt", encoding="utf-8") as f:
                _lig_words = set(f.read().split())
        except Exception:
            _lig_words = set()
    return _lig_words


def resolve_ligatures(text, marks):
    """marks: {placeholder char: candidate strings, best width match first}. Pick the one that makes real words."""
    words = lig_words()
    for p in marks:
        text = re.sub(r"(?<![^\W\d_])" + p + r"(?![^\W\d_])", "•", text)
    best = {p: c[0] for p, c in marks.items()}
    for p, cands in marks.items():
        found = re.findall(r"[\w" + "".join(marks) + r"]*" + p + r"[\w" + "".join(marks) + r"]*", text)

        def hits(c):
            n = 0
            for w in found:
                w2 = w.replace(p, c)
                for q, b in best.items():
                    w2 = w2.replace(q, b)
                w2 = w2.lower()
                if w2 in words or re.sub(r"(s|es|ed|ing|ly|er)$", "", w2) in words:
                    n += 1
            return n
        scores = [(hits(c), -i) for i, c in enumerate(cands)]
        best[p] = cands[-max(scores)[1]]

    def apply(t):
        for p in marks:
            t = re.sub(r"(?<![^\W\d_])" + p + r"(?![^\W\d_])", "•", t)   # a lone unknown glyph is a bullet/icon
        for p, c in best.items():
            t = t.replace(p, c)
        return t
    return apply


def line_key(s):
    """Loose key for matching a line of CV text back to its font info."""
    import unicodedata
    return re.sub(r"[\W_]+", "", unicodedata.normalize("NFKC", s)).lower()[:80]


BOLD_RE = re.compile(r"bold|black|heavy|semibold|demi|-b\b|,b\b|extrab", re.I)


def pdf_text(path, meta=None):
    """Read a PDF the way it looks: columns kept together, spaces from letter gaps, joined letters repaired.
    meta (optional dict) gets each line's font size and boldness, keyed by line_key()."""
    from pdfminer.converter import PDFPageAggregator
    from pdfminer.layout import LAParams, LTChar, LTFigure, LTTextBox, LTTextLine
    from pdfminer.pdfinterp import PDFPageInterpreter, PDFResourceManager
    from pdfminer.pdfpage import PDFPage

    class Collector(PDFPageAggregator):
        def render_char(self, matrix, font, fontsize, scaling, rise, cid, ncs, graphicstate):
            adv = super().render_char(matrix, font, fontsize, scaling, rise, cid, ncs, graphicstate)
            item = self.cur_item._objs[-1]
            item.jf_cid = cid
            try:
                item.jf_w = font.char_width(cid) * 1000
            except Exception:
                item.jf_w = 0
            return adv

    rm = PDFResourceManager()
    dev = Collector(rm, laparams=LAParams(line_margin=0.4, all_texts=True))
    interp = PDFPageInterpreter(rm, dev)
    lines, widths, unknown, infos = [], {}, [], []
    with open(path, "rb") as fh:
        for n, page in enumerate(PDFPage.get_pages(fh)):
            if n >= 6:
                break
            interp.process_page(page)

            def walk(obj):
                if isinstance(obj, LTTextLine):
                    chars, sizes, bolds = [], [], 0
                    for ch in obj:
                        t = ch.get_text()
                        if isinstance(ch, LTChar):
                            if t.strip():
                                sizes.append(round(ch.size, 1))
                                bolds += bool(BOLD_RE.search(ch.fontname))
                            fam = ch.fontname.split("+")[-1].lower()
                            if t in ("�", "") or t.startswith("(cid:"):
                                unknown.append((fam, ch.jf_cid, ch.jf_w))
                                t = ("\x00", len(unknown) - 1)
                            elif t in "tif" and ch.jf_w:
                                widths.setdefault((fam, t), ch.jf_w)
                        chars.append(t)
                    lines.append(chars)
                    infos.append((max(set(sizes), key=sizes.count) if sizes else 0,
                                  bool(sizes) and bolds > len(sizes) * .6))
                elif isinstance(obj, (LTTextBox, LTFigure)) or hasattr(obj, "_objs"):
                    for o in obj:
                        walk(o)
                    if isinstance(obj, LTTextBox):
                        lines.append(["\n"])
                        infos.append(None)
            walk(dev.get_result())
    # one placeholder per distinct unknown glyph; the glyph's width says how many letters it holds
    marks, slot = {}, {}
    for fam, cid, w in unknown:
        if (fam, cid) in slot:
            continue
        p = chr(0xE000 + len(slot))
        slot[(fam, cid)] = p

        def guess(c):
            exp = sum(widths.get((fam, ch)) or LIG_DEFAULT_W[ch] for ch in c)
            return abs(1 - w / exp * 1.03) if w else 0      # joined glyphs are a little narrower
        cands = sorted(LIG_CANDIDATES, key=guess)
        marks[p] = [c for c in cands if not w or guess(c) < 0.12] or cands[:1]
    out = []
    for chars in lines:
        out.append("".join(slot[unknown[c[1]][:2]] if isinstance(c, tuple) else c for c in chars))
    fix = resolve_ligatures("".join(out), marks) if marks else (lambda t: t)
    out = [fix(o) for o in out]
    if meta is not None:
        for o, info in zip(out, infos):
            if info and o.strip():
                meta.setdefault(line_key(clean_text(o)), {"size": info[0], "bold": info[1]})
    return "".join(out)


def docx_text(path, meta=None):
    """Word text in reading order: headers first, then the body (tables cell by cell, text boxes once)."""
    import zipfile
    from xml.etree import ElementTree as ET
    w = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    mc = "{http://schemas.openxmlformats.org/markup-compatibility/2006}"
    with zipfile.ZipFile(path) as z:
        names = sorted(n for n in z.namelist() if re.fullmatch(r"word/header\d*\.xml", n)) + ["word/document.xml"]
        parts = [ET.fromstring(z.read(n)) for n in names if n in z.namelist()]
    lines = []

    def para_text(p):
        out = []

        def walk(e):
            if e.tag == mc + "Fallback":          # old-style copy of a text box we already read
                return
            if e.tag == w + "t":
                out.append(e.text or "")
            elif e.tag == w + "tab":
                out.append("  |  ")
            elif e.tag in (w + "br", w + "cr"):
                out.append("\n")
            elif e.tag == w + "p" and e is not p:
                return                            # paragraphs inside a text box are read on their own
            for c in e:
                walk(c)
        walk(p)
        return "".join(out)

    def walk(e):
        if e.tag == mc + "Fallback":
            return
        if e.tag == w + "p":
            listed = e.find(w + "pPr/" + w + "numPr") is not None    # Word list item = bullet point
            t = para_text(e)
            lines.append(("• " if listed else "") + t)
            if meta is not None and t.strip():
                st = e.find(w + "pPr/" + w + "pStyle")
                style = (st.get(w + "val", "") if st is not None else "").lower()
                szs = [int(x.get(w + "val")) / 2 for x in e.iter(w + "sz") if (x.get(w + "val") or "").isdigit()]
                runs = [r for r in e.iter(w + "r") if "".join(x.text or "" for x in r.iter(w + "t")).strip()]

                def is_bold(r):
                    b = r.find(w + "rPr/" + w + "b")
                    return b is not None and b.get(w + "val", "1") not in ("0", "false")
                size = max(szs) if szs else 26 if style.startswith("title") else 16 if style.startswith("heading") else 11
                meta.setdefault(line_key(clean_text(t)), {"size": size,
                                                          "bold": (bool(runs) and all(map(is_bold, runs)))
                                                          or style.startswith("heading"),
                                                          "heading": style.startswith("heading")})
        if e.tag == w + "tc":
            lines.append("")
        for c in e:
            walk(c)
    for root in parts:
        walk(root)
    return "\n".join(lines)


def cv_text(path, meta=None):
    path = Path(path)
    ext = path.suffix.lower()
    if ext == ".pdf":
        try:
            text = pdf_text(path, meta)
            if len(text.strip()) > 40:
                return text
        except Exception:
            pass
        from pypdf import PdfReader
        reader = PdfReader(str(path))
        return "\n".join((p.extract_text() or "") for p in reader.pages[:6])
    if ext == ".docx":
        return docx_text(path, meta)
    if ext in (".txt", ".rtf"):
        return path.read_text(encoding="utf-8", errors="replace")
    raise ValueError("Can only read PDF, Word (.docx) or text CVs")


def clean_text(t):
    """Remove icon glyphs, emoji, rating dots and PDF spacing glitches from CV text."""
    import unicodedata
    t = unicodedata.normalize("NFKC", t)                       # "ﬁ" -> "fi", odd widths -> normal
    t = t.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    t = re.sub(r"(https?:)/\s+/", r"\1//", t)                  # "https:/ /" -> "https://"
    t = t.replace("\xad", "-")                                 # soft hyphens are drawn as hyphens in many PDFs
    t = "".join(" " if unicodedata.category(c) in ("So", "Co", "Cn", "Cs", "Sk", "Cf") or c in "○●◯◉★☆✓✔" else c
                for c in t)
    t = t.replace("\xad", "-")                                 # soft hyphens are drawn as hyphens in many PDFs
    t = re.sub(r"(\w)-\n(\w)", r"\1\2", t)                     # words split across lines
    t = re.sub(r"\b(?![AI]\b)([A-Z]) ([a-z]{2,})", r"\1\2", t)  # "T eamCity" -> "TeamCity"
    t = re.sub(r"\)([A-Za-z])", r") \1", t)                    # "(Project)content" -> "(Project) content"
    t = re.sub(r"(\d{3,})(?=[A-Z][a-z]{2,})", r"\1 ", t)       # "+44 754 9768198Coventry" -> "... 9768198 Coventry"
    t = re.sub(r"[ \t]+", " ", t)
    return t
