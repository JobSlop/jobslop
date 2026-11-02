r"""jobslop - find jobs on many boards at once, track applications, fill forms with the Chrome extension.

Run it:  python jobfinder.py      (--browser opens it in your web browser instead of its own window)
Build the standalone program:  build.bat  ->  dist\jobslop.exe

The app itself lives in the jobslop/ package. Saved jobs and settings live in %APPDATA%\JobFinder.
"""
from jobslop.app import main

if __name__ == "__main__":
    main()
