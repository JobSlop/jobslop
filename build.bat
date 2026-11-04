@echo off
rem Builds jobslop for Windows. Needs Python once; the .exe itself doesn't. Uses a separate Python
rem environment so unrelated big libraries on this PC don't get bundled.
rem   build.bat                  a build of your own (updates: get the new source and build again)
rem   build.bat gumroad          the build sold on Gumroad -> dist\jobslop.exe (updates itself with a licence key)
rem   build.bat personal         for testing, friends and family -> dist\jobslop-personal.exe and the tester
rem                              package jobslop-Tester-Windows (+ .zip); updates itself, no licence needed
rem   add "nopause" to any of these when running from PyCharm or a script (release.py builds both kinds)
setlocal
cd /d "%~dp0"
set FAILED=0
set NOPAUSE=0
set KIND=self
for %%a in (%*) do (
  if /i "%%a"=="nopause" set NOPAUSE=1
  if /i "%%a"=="gumroad" set KIND=gumroad
  if /i "%%a"=="personal" set KIND=personal
)
set OUT=jobslop.exe
if "%KIND%"=="personal" set OUT=jobslop-personal.exe
echo Building jobslop (%KIND% build)...
set VENV=%TEMP%\jobfinder-venv
if not exist "%VENV%\Scripts\python.exe" python -m venv "%VENV%" || goto failed
"%VENV%\Scripts\python.exe" -m pip install --quiet --upgrade pyinstaller pywebview python-jobspy pypdf pdfminer.six phonenumbers pypdfium2 || goto failed
rem which kind of build this is goes inside the app (jobslop\build_info.py, only while building)
if exist jobslop\build_info.py del jobslop\build_info.py
if not "%KIND%"=="self" (echo KIND = "%KIND%"> jobslop\build_info.py)
rem the test tools live in the same environment (run_tests.bat) and must never end up inside the app
rem standard modules third-party plugins may use that jobslop itself doesn't (so they're in the .exe)
set PLUGIN_STDLIB=--hidden-import xml.etree.ElementTree --hidden-import xml.dom.minidom --hidden-import statistics --hidden-import difflib --hidden-import textwrap --hidden-import uuid --hidden-import hmac --hidden-import calendar --hidden-import html.parser --hidden-import email.utils --hidden-import decimal --hidden-import fractions --hidden-import string --hidden-import random --hidden-import itertools --hidden-import functools --hidden-import typing --hidden-import dataclasses --hidden-import sqlite3
"%VENV%\Scripts\python.exe" -m PyInstaller --noconfirm --onefile %PLUGIN_STDLIB% --hidden-import jobslop.build_info --windowed --name jobslop --icon "%~dp0jf.ico" ^
  --collect-all jobspy --collect-all curl_cffi --collect-data certifi --collect-data pdfminer --collect-submodules phonenumbers.data --collect-submodules phonenumbers.shortdata --collect-all pypdfium2 --collect-all pypdfium2_raw ^
  --exclude-module pytest --exclude-module _pytest --exclude-module pluggy ^
  --add-data "%~dp0chrome-extension;chrome-extension" --add-data "%~dp0ui;ui" ^
  --add-data "%~dp0static;static" --add-data "%~dp0cities.tsv.gz;." --add-data "%~dp0jf.ico;." --add-data "%~dp0plugins;plugins" ^
  --workpath "%TEMP%\jobfinder-build" --specpath "%TEMP%\jobfinder-build" jobfinder.py || goto failed
if exist jobslop\build_info.py del jobslop\build_info.py
if "%KIND%"=="personal" move /y dist\jobslop.exe dist\%OUT% >nul || goto failed
rem checksum the app checks an update download against (uploaded next to the .exe by release.py)
"%VENV%\Scripts\python.exe" -c "import hashlib; h=hashlib.sha256(open('dist/%OUT%','rb').read()).hexdigest(); open('dist/%OUT%.sha256','w').write(h+'  %OUT%\n')" || goto failed

if not "%KIND%"=="personal" goto source
rem tester package (a personal build): jobslop-Tester-Windows\ (exe + READ ME FIRST) and jobslop-Tester-Windows.zip
if not exist jobslop-Tester-Windows mkdir jobslop-Tester-Windows
copy /y dist\%OUT% jobslop-Tester-Windows\jobslop.exe >nul || echo Note: couldn't update jobslop-Tester-Windows\jobslop.exe (is it open?) - the zip still gets the new one.
copy /y "package\READ ME FIRST.txt" jobslop-Tester-Windows\ >nul
"%VENV%\Scripts\python.exe" -c "import zipfile; z=zipfile.ZipFile('jobslop-Tester-Windows.zip','w',zipfile.ZIP_DEFLATED); z.write('dist/%OUT%','jobslop-Tester-Windows/jobslop.exe'); z.write('package/READ ME FIRST.txt','jobslop-Tester-Windows/READ ME FIRST.txt'); z.close()" || goto failed

:source
rem source for building the Mac app on a Mac
"%VENV%\Scripts\python.exe" tools\make_mac_source.py || goto failed
echo.
echo Done: dist\%OUT% (%KIND% build)
goto end

:failed
set FAILED=1
if exist jobslop\build_info.py del jobslop\build_info.py
echo.
echo BUILD FAILED - see the messages above. If it says "access denied", close jobslop and build again.

:end
if "%NOPAUSE%"=="0" pause
exit /b %FAILED%
