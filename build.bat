@echo off
rem Builds dist\jobslop.exe and the tester package (jobslop-Tester-Windows + .zip).
rem Needs Python once; the .exe itself doesn't. Uses a separate Python environment so unrelated
rem big libraries on this PC don't get bundled.
rem   build.bat            double-click: builds, then waits for a key
rem   build.bat nopause    from PyCharm's "Build exe" configuration or other scripts
setlocal
cd /d "%~dp0"
set FAILED=0
set VENV=%TEMP%\jobfinder-venv
if not exist "%VENV%\Scripts\python.exe" python -m venv "%VENV%" || goto failed
"%VENV%\Scripts\python.exe" -m pip install --quiet --upgrade pyinstaller pywebview python-jobspy pypdf pdfminer.six phonenumbers pypdfium2 || goto failed
rem the test tools live in the same environment (run_tests.bat) and must never end up inside the app
"%VENV%\Scripts\python.exe" -m PyInstaller --noconfirm --onefile --windowed --name jobslop --icon "%~dp0jf.ico" ^
  --collect-all jobspy --collect-all curl_cffi --collect-data certifi --collect-data pdfminer --collect-submodules phonenumbers.data --collect-submodules phonenumbers.shortdata --collect-all pypdfium2 --collect-all pypdfium2_raw ^
  --exclude-module pytest --exclude-module _pytest --exclude-module pluggy ^
  --add-data "%~dp0chrome-extension;chrome-extension" --add-data "%~dp0ui.html;." ^
  --add-data "%~dp0static;static" --add-data "%~dp0cities.tsv.gz;." --add-data "%~dp0jf.ico;." --add-data "%~dp0plugins;plugins" ^
  --workpath "%TEMP%\jobfinder-build" --specpath "%TEMP%\jobfinder-build" jobfinder.py || goto failed
rem checksum the app checks an update download against (uploaded next to jobslop.exe by release.py)
"%VENV%\Scripts\python.exe" -c "import hashlib; h=hashlib.sha256(open('dist/jobslop.exe','rb').read()).hexdigest(); open('dist/jobslop.exe.sha256','w').write(h+'  jobslop.exe\n')" || goto failed

rem tester package: jobslop-Tester-Windows\ (exe + READ ME FIRST) and jobslop-Tester-Windows.zip
if not exist jobslop-Tester-Windows mkdir jobslop-Tester-Windows
copy /y dist\jobslop.exe jobslop-Tester-Windows\ >nul || echo Note: couldn't update jobslop-Tester-Windows\jobslop.exe (is it open?) - the zip still gets the new one.
copy /y "package\READ ME FIRST.txt" jobslop-Tester-Windows\ >nul
"%VENV%\Scripts\python.exe" -c "import zipfile; z=zipfile.ZipFile('jobslop-Tester-Windows.zip','w',zipfile.ZIP_DEFLATED); z.write('dist/jobslop.exe','jobslop-Tester-Windows/jobslop.exe'); z.write('package/READ ME FIRST.txt','jobslop-Tester-Windows/READ ME FIRST.txt'); z.close()" || goto failed
echo.
echo Done: dist\jobslop.exe and jobslop-Tester-Windows.zip
goto end

:failed
set FAILED=1
echo.
echo BUILD FAILED - see the messages above. If it says "access denied", close jobslop and build again.

:end
if /i not "%~1"=="nopause" pause
exit /b %FAILED%
