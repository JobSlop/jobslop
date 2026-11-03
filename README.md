# jobslop

Search dozens of job boards at once, match jobs to your CV, track every application, and let the Chrome
extension fill in application forms for you. Everything stays on your own computer.

- **Search:** LinkedIn, Indeed, Glassdoor and ZipRecruiter, plus many more through plugins: one per country (UK, US, Denmark, Netherlands), Adzuna, remote boards, accounting, art and games. Every plugin starts switched off; pick yours in the welcome tour.
- **Match:** drop in your CV and jobslop ranks jobs by how well they fit.
- **Track:** a board of everything you've saved and applied to, with streaks, a weekly goal and follow-up reminders.
- **Easy apply:** the Chrome extension fills application forms with your profile and CV. It never submits; you always check and send.
- **Plugins and languages:** extra boards, profile fields, tabs and map layers, plus Dutch, Spanish and Danish. Anyone can [make a plugin](docs/PLUGINS.md).

## Get jobslop

**Ready-made app:** buy it on Gumroad (link coming soon). That supports development, and it's the easy way: download, open, done. New versions are announced in the app.

**Build it yourself, free:** jobslop is open source under the [GPL-3.0](LICENSE). You need Python 3.11 or newer.

```bash
git clone https://github.com/JobSlop/jobslop.git
cd jobslop
python -m pip install -r requirements.txt
python jobfinder.py
```

To make the standalone app:

- **Windows:** double-click `build.bat`. You get `dist\jobslop.exe`.
- **Mac:** see [HOW TO BUILD ON MAC.txt](HOW%20TO%20BUILD%20ON%20MAC.txt). You get `dist/jobslop.app`.

Your data (profile, CV, saved jobs, settings) lives in `%APPDATA%\JobFinder` on Windows and `~/Library/Application Support/JobFinder` on a Mac. Updating never touches it.

## Development

```bash
python -m pytest            # about 340 tests, no internet needed; uses a temporary data folder
python -m ruff check .      # lint
```

| Path | What's there |
|---|---|
| `jobslop/` | The app: `boards/`, `search/`, `profile/`, `geo/`, `plugins/` (plugin system), `server/` (local web server), `i18n.py` |
| `ui/` | The screen (`index.html`, `app.css`, `js/`) |
| `plugins/` | The built-in plugins. Each also lives in its own repo, `JobSlop/jobslop-plugin-<name>` |
| `chrome-extension/` | The Easy apply extension |
| `docs/` | `PLUGINS.md` (how to make plugins), `plugin-template/` |
| `tools/` | `extract_strings.py` (text for language packs), `make_mac_source.py` |

## Credits

- Town list: [GeoNames](https://www.geonames.org) (CC BY 4.0)
- Country outlines: [Natural Earth](https://www.naturalearthdata.com) (public domain)
- Map: [Leaflet](https://leafletjs.com) (BSD-2-Clause) with [OpenStreetMap](https://www.openstreetmap.org/copyright) tiles
- QR codes: [qrcode-generator](https://github.com/kazuhikoarase/qrcode-generator) (MIT)
- Fonts: Manrope and Italiana (SIL Open Font License)
- Indeed, Glassdoor and ZipRecruiter searches through [JobSpy](https://github.com/speedyapply/JobSpy) (MIT)

jobslop is not affiliated with any of the job boards it searches.

## Licence

Copyright (C) 2026 JobSlop. jobslop is free software: you can redistribute it and/or modify it under the
terms of the GNU General Public License version 3, or (at your option) any later version. See [LICENSE](LICENSE).
