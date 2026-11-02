"""Builds static/world.json - a small offline world map (country outlines) from Natural Earth (public domain).
Usage: python make_world.py path/to/ne_50m_admin_0_countries.geojson
"""
import json
import sys
from pathlib import Path


def simplify_ring(ring, digits=2):
    out = []
    for x, y in ring:
        p = [round(x, digits), round(y, digits)]
        if not out or p != out[-1]:
            out.append(p)
    return out if len(out) >= 4 else None


src = json.load(open(sys.argv[1], encoding="utf-8"))
feats = []
for f in src["features"]:
    g = f["geometry"]
    polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
    new = []
    for poly in polys:
        rings = [r for r in (simplify_ring(r) for r in poly) if r]
        if rings:
            new.append(rings)
    if new:
        feats.append({"type": "Feature", "properties": {"n": f["properties"].get("NAME_EN") or f["properties"].get("NAME"),
                                                         "c": f["properties"].get("ISO_A2_EH") or f["properties"].get("ISO_A2")},
                      "geometry": {"type": "MultiPolygon", "coordinates": new}})
out = Path(__file__).resolve().parent / "static" / "world.json"
out.write_text(json.dumps({"type": "FeatureCollection", "features": feats}, separators=(",", ":")), encoding="utf-8")
print(len(feats), "countries ->", out, round(out.stat().st_size / 1024), "KB")
