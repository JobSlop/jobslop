"""Builds cities.tsv.gz (offline town lookup for the map and job distances) from GeoNames cities5000.zip.
GeoNames data: CC BY 4.0, https://www.geonames.org/
Usage: python make_cities.py path/to/cities5000.zip
"""
import gzip, io, sys, zipfile
from pathlib import Path


def latin(s):
    return all(ord(c) < 0x250 or c in "’'" for c in s)


src = Path(sys.argv[1])
out_rows = []
with zipfile.ZipFile(src) as z:
    with z.open("cities5000.txt") as f:
        for line in io.TextIOWrapper(f, encoding="utf-8"):
            c = line.rstrip("\n").split("\t")
            if len(c) < 15:
                continue
            name, ascii_name, alts, lat, lon, cc, admin1, pop = c[1], c[2], c[3], c[4], c[5], c[8], c[10], c[14]
            names = []
            for n in [name, ascii_name] + alts.split(","):
                n = n.strip()
                if n and latin(n) and len(n) <= 40 and not any(ch.isdigit() for ch in n) \
                        and not (len(n) <= 4 and n.isupper()) and n.lower() not in (x.lower() for x in names):
                    names.append(n)
            if int(pop or 0) < 100000:
                names = names[:10]          # big cities keep every spelling (København, Den Haag, Kopenhagen…)
            if not names:
                continue
            out_rows.append("\t".join([names[0], f"{float(lat):.4f}", f"{float(lon):.4f}", cc, admin1, pop, "|".join(names[1:])]))

out = Path(__file__).resolve().parent / "cities.tsv.gz"
with gzip.open(out, "wt", encoding="utf-8", compresslevel=9) as g:
    g.write("\n".join(out_rows))
print(len(out_rows), "towns ->", out, round(out.stat().st_size / 1024), "KB")
