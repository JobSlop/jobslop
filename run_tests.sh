#!/bin/bash
# Runs all of Job Finder's tests on a Mac with pytest (no internet needed; your Job Finder data is never touched).
# Optional: Google Chrome and Node.js for the extension and app-screen tests (skipped if missing).
cd "$(dirname "$0")"
VENV="${TMPDIR:-/tmp}/jobfinder-venv"
[ -x "$VENV/bin/python" ] || python3 -m venv "$VENV"
"$VENV/bin/python" -c "import pytest, pdfminer, phonenumbers" 2>/dev/null || "$VENV/bin/pip" install --quiet pytest python-jobspy pypdf pdfminer.six phonenumbers
"$VENV/bin/python" -m pytest "$@"
