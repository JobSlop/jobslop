"""Make jobslop-Mac-Source.zip: everything needed to build the Mac app on a Mac (see HOW TO BUILD ON MAC.txt).

    python tools/make_mac_source.py
"""
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOP = "jobslop-Mac-Source"
FILES = ["jobfinder.py", "build_mac.sh", "HOW TO BUILD ON MAC.txt", "requirements.txt", "cities.tsv.gz",
         "jf.icns", "jf.ico", "jf.png"]
FOLDERS = ["jobslop", "ui", "plugins", "static", "chrome-extension"]
SKIP = ("__pycache__", ".pyc", ".jobslop-source.json")


def main() -> None:
    out = ROOT / "jobslop-Mac-Source.zip"
    n = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for name in FILES:
            z.write(ROOT / name, f"{TOP}/{name}")
            n += 1
        for folder in FOLDERS:
            for f in sorted((ROOT / folder).rglob("*")):
                if f.is_file() and not any(s in str(f) for s in SKIP):
                    z.write(f, f"{TOP}/{f.relative_to(ROOT).as_posix()}")
                    n += 1
    print(f"{out.name}: {n} files")


if __name__ == "__main__":
    main()
