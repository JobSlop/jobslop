"""Publish a new jobslop version on GitHub, so everyone's app offers it as an update.

One-time setup:
  1. Make a GitHub repository for jobslop (it can be private for the code, but the RELEASES must be
     downloadable, so make the repository public - or use a separate public repo just for releases).
  2. Put its name in jobfinder.py:   UPDATE_REPO = os.environ.get("JOBSLOP_UPDATE_REPO", "your-name/jobslop")
  3. Install the GitHub CLI (https://cli.github.com) and sign in once:   gh auth login

Every release:
  1. Raise APP_VERSION in jobfinder.py (e.g. 2.0.0 -> 2.1.0)
  2. Run:   python release.py "What's new: one line per change"
     (or use PyCharm's "Release" run configuration and type the notes when asked)

It builds jobslop.exe, writes its checksum, and creates the GitHub release "v2.1.0" with both files.
Apps that are open see the update within 12 hours, or straight away with Settings -> Check for updates.
"""
import hashlib
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def setting(name):
    """The last "quoted" value on the line  NAME = ...  in jobfinder.py."""
    m = re.search(rf"^{name} = ([^#\n]*)", (ROOT / "jobfinder.py").read_text(encoding="utf-8"), re.M)
    vals = re.findall(r'"([^"]*)"', m[1]) if m else []
    return vals[-1] if vals else ""


def main():
    version = setting("APP_VERSION")
    repo = setting("UPDATE_REPO")
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        sys.exit("APP_VERSION in jobfinder.py should look like 2.1.0")
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", repo):
        sys.exit('Set UPDATE_REPO in jobfinder.py first, e.g. os.environ.get("JOBSLOP_UPDATE_REPO", "your-name/jobslop")')
    gh = shutil.which("gh")
    if not gh:
        sys.exit("Install the GitHub CLI first (https://cli.github.com), then run:  gh auth login")
    notes = " ".join(sys.argv[1:]).strip() or input(f"What's new in {version}? ").strip() or f"jobslop {version}"
    tag = "v" + version
    if subprocess.run([gh, "release", "view", tag, "--repo", repo], capture_output=True).returncode == 0:
        sys.exit(f"{tag} is already released - raise APP_VERSION in jobfinder.py first")

    print(f"Building jobslop {version}...")
    if subprocess.run(["cmd", "/c", str(ROOT / "build.bat"), "nopause"], cwd=ROOT).returncode:
        sys.exit("The build failed - nothing was released")
    exe, sha = ROOT / "dist" / "jobslop.exe", ROOT / "dist" / "jobslop.exe.sha256"
    digest = hashlib.sha256(exe.read_bytes()).hexdigest()
    if not sha.is_file() or sha.read_text().split()[0] != digest:
        sys.exit("The checksum file doesn't match the .exe - nothing was released")

    print(f"Publishing {tag} to github.com/{repo}...")
    r = subprocess.run([gh, "release", "create", tag, str(exe), str(sha), "--repo", repo,
                        "--title", f"jobslop {version}", "--notes", notes])
    if r.returncode:
        sys.exit("GitHub didn't accept the release - see the message above")
    print(f"Done: https://github.com/{repo}/releases/tag/{tag}")


if __name__ == "__main__":
    main()
