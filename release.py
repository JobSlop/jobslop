"""Publish a new jobslop version: the source goes to GitHub, the ready-made builds to the builds repository.

jobslop works like Aseprite: the code is open (GPL-3.0) and anyone can build it themselves, while
ready-made builds are sold. The main repository's releases carry the source only. The ready-made .exe
files go to the builds repository (BUILDS_REPO) so they can update themselves: the Gumroad build only
after its licence key is checked, the personal build (testers, friends and family) without one.

One-time setup:
  1. Install the GitHub CLI (https://cli.github.com) and sign in once:   gh auth login
  2. This folder is a git repository with the GitHub repository as "origin" (see README.md).
  3. Put your Gumroad product page and product ID in jobslop/config.py (DOWNLOAD_PAGE, GUMROAD_PRODUCT_ID)
  4. The builds repository exists (BUILDS_REPO, e.g. JobSlop/jobslop-builds)

Every release:
  1. Raise APP_VERSION in jobslop/config.py (e.g. 3.0.0 -> 3.1.0) and commit your changes
  2. Run:   python release.py "What's new: one line per change"
     (or use PyCharm's "Release" run configuration and type the notes when asked)
  3. Upload dist/jobslop.exe to your Gumroad product (and jobslop-Mac.zip if you built one on a Mac)

Step 2 builds dist/jobslop.exe (Gumroad) and dist/jobslop-personal.exe (personal), pushes the code and a
"v3.1.0" tag to GitHub, creates the source release with your notes, and puts both builds (with their
checksums) in the builds repository's "v3.1.0" release. Open apps see the new version within 12 hours, or straight away with
Settings -> Updates -> Check for updates; "Get it" opens the Gumroad page (bought copies) or GitHub.
"""
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def setting(name):
    """The last "quoted" value on the line  NAME = ...  in jobslop/config.py."""
    m = re.search(rf"^{name} = ([^#\n]*)", (ROOT / "jobslop" / "config.py").read_text(encoding="utf-8"), re.M)
    vals = re.findall(r'"([^"]*)"', m[1]) if m else []
    return vals[-1] if vals else ""


def git(*args, check=True):
    # on Windows, check GitHub's certificate with Windows' own store (git's bundled one can be out of date)
    tls = ["-c", "http.sslBackend=schannel"] if sys.platform.startswith("win") else []
    r = subprocess.run(["git", *tls, *args], cwd=ROOT, capture_output=True, text=True)
    if check and r.returncode:
        sys.exit(f"git {' '.join(args)} failed:\n{r.stderr.strip()}")
    return r.stdout.strip()


def main():
    version = setting("APP_VERSION")
    repo = setting("UPDATE_REPO")
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        sys.exit("APP_VERSION in jobslop/config.py should look like 3.1.0")
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", repo):
        sys.exit('Set UPDATE_REPO in jobslop/config.py first, e.g. os.environ.get("JOBSLOP_UPDATE_REPO", "your-name/jobslop")')
    gh = shutil.which("gh") or next((p for p in (r"C:\Program Files\GitHub CLI\gh.exe",) if Path(p).is_file()), None)
    if not gh:
        sys.exit("Install the GitHub CLI first (https://cli.github.com), then run:  gh auth login")
    if git("status", "--porcelain"):
        sys.exit("Commit your changes first - a release is made from what's committed")
    notes = " ".join(sys.argv[1:]).strip() or input(f"What's new in {version}? ").strip() or f"jobslop {version}"
    tag = "v" + version
    if subprocess.run([gh, "release", "view", tag, "--repo", repo], capture_output=True).returncode == 0:
        sys.exit(f"{tag} is already released - raise APP_VERSION in jobslop/config.py first")

    builds = setting("BUILDS_REPO")
    windows = sys.platform.startswith("win")
    if windows:
        for kind in ("gumroad", "personal"):
            print(f"Building jobslop {version} ({kind})...")
            if subprocess.run(["cmd", "/c", str(ROOT / "build.bat"), kind, "nopause"], cwd=ROOT).returncode:
                sys.exit("The build failed - nothing was released")

    print(f"Publishing the source of {tag} to github.com/{repo}...")
    git("tag", "-a", tag, "-m", f"jobslop {version}")
    git("push", "origin", "HEAD")
    git("push", "origin", tag)
    notes += ("\n\nBuild it yourself from this source (see README.md), or get the ready-made app"
              + (f": {setting('DOWNLOAD_PAGE')}" if setting("DOWNLOAD_PAGE") else " from the download page") + ".")
    r = subprocess.run([gh, "release", "create", tag, "--repo", repo, "--verify-tag",
                        "--title", f"jobslop {version}", "--notes", notes])
    if r.returncode:
        sys.exit("GitHub didn't accept the release - see the message above")
    print(f"Done: https://github.com/{repo}/releases/tag/{tag}")
    if windows and builds:
        files = [str(ROOT / "dist" / f) for f in ("jobslop.exe", "jobslop.exe.sha256", "jobslop-personal.exe",
                                                   "jobslop-personal.exe.sha256")]
        print(f"Uploading the ready-made builds to github.com/{builds}...")
        r = subprocess.run([gh, "release", "create", tag, *files, "--repo", builds, "--title", f"jobslop {version} builds",
                            "--notes", f"Ready-made builds of jobslop {version}, used by the app to update itself."])
        if r.returncode:
            sys.exit(f"The builds couldn't be uploaded to {builds} - the source release is out; upload them by hand")
    print("Now upload dist/jobslop.exe to your Gumroad product.")


if __name__ == "__main__":
    main()
