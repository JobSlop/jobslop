@echo off
rem Runs all of Job Finder's tests with pytest (about 170, under a minute). No internet needed, and
rem your own Job Finder data is never touched. Uses the same Python environment as build.bat.
rem Optional: Google Chrome (form-filling + app screen tests) and Node.js (extension logic tests);
rem those parts are skipped with a note if they're missing.
rem Extra options go straight to pytest, e.g.  run_tests.bat -k where   or   run_tests.bat tests\test_cv.py
cd /d "%~dp0"
set VENV=%TEMP%\jobfinder-venv
if not exist "%VENV%\Scripts\python.exe" python -m venv "%VENV%"
"%VENV%\Scripts\python.exe" -c "import pytest, pdfminer, phonenumbers, jobspy" 2>nul || "%VENV%\Scripts\python.exe" -m pip install --quiet pytest python-jobspy pypdf pdfminer.six phonenumbers pypdfium2
"%VENV%\Scripts\python.exe" -m pytest %*
if errorlevel 1 (echo. & echo SOME TESTS FAILED - see above) else (echo. & echo All tests passed)
pause
