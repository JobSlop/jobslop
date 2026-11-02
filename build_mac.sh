#!/bin/bash
# Builds "jobslop.app" on a Mac.   Run in Terminal from this folder:   bash build_mac.sh
set -e
cd "$(dirname "$0")"
SRC="$(pwd)"     # full path to this folder (PyInstaller needs full paths for the app's files)

echo "== jobslop - Mac build =="

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 is needed. Install it from https://www.python.org/downloads/macos/ and run this again."
  exit 1
fi
python3 -c 'import sys; assert sys.version_info >= (3, 10), "Python 3.10 or newer is needed"' || exit 1

# a separate Python environment just for building, so nothing else on the Mac is touched
VENV="$HOME/.jobfinder-build-venv"
if [ ! -x "$VENV/bin/python" ]; then
  echo "Setting up the build environment (first time only)..."
  python3 -m venv "$VENV"
fi
"$VENV/bin/python" -m pip install --quiet --upgrade pip
echo "Installing build tools..."
"$VENV/bin/python" -m pip install --quiet --upgrade pyinstaller pywebview python-jobspy pypdf pdfminer.six phonenumbers certifi

echo "Building the app (takes a few minutes)..."
"$VENV/bin/python" -m PyInstaller --noconfirm --windowed --name "jobslop" --icon "$SRC/jf.icns" \
  --osx-bundle-identifier com.jobfinder.desktop \
  --collect-all jobspy --collect-all curl_cffi --collect-data certifi --collect-data pdfminer --collect-submodules phonenumbers.data --collect-submodules phonenumbers.shortdata \
  --add-data "$SRC/chrome-extension:chrome-extension" --add-data "$SRC/ui.html:." \
  --add-data "$SRC/static:static" --add-data "$SRC/cities.tsv.gz:." --add-data "$SRC/jf.ico:." --add-data "$SRC/plugins:plugins" \
  --workpath "$HOME/.jobfinder-build" --specpath "$HOME/.jobfinder-build" \
  --distpath "$SRC/dist" \
  "$SRC/jobfinder.py"

echo "Making a zip you can share..."
rm -f "jobslop-Mac.zip"
ditto -c -k --keepParent "dist/jobslop.app" "jobslop-Mac.zip"

echo
echo "Done!"
echo "  App:  dist/jobslop.app   (drag it into Applications)"
echo "  Zip:  jobslop-Mac.zip     (send this to Mac testers)"
echo "This build runs on Macs with the same kind of chip as this one ($(uname -m))."
