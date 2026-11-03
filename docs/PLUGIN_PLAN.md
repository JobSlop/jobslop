# jobslop plugins — plan

## Status (3 November 2026)

Steps 1–9 are done and committed locally. Step 10 waits for your OK.

| Step | Status |
|---|---|
| 1. git | done |
| 2. backend split into `jobslop/` | done |
| 3. board registry, `/api/boards` | done |
| 4. plugin system, Settings → Plugins | done |
| 5. boards moved into built-in plugins | done |
| 6. screen split into `ui/`, screen-side plugin API, profile fields + autofill | done |
| 7. translation, NL/ES/DA packs, local job titles | done |
| 8. install / update / remove from GitHub links | done |
| 9. builds bundle `ui/` and `plugins/`, `docs/PLUGINS.md`, `docs/plugin-template/` | done |
| 10. public plugin repos + jobslop 3.0.0 release | **waiting for your OK** |

Differences from the plan:
- **Server routes:** most routes are still one handler, `jobslop/server/handler.py`. The plugin routes have their own module (`server/plugin_routes.py`). Splitting the rest by area is a follow-up.
- **Chrome extension popup:** not translated yet. The screen is.
- **Translations:** the Dutch, Spanish and Danish texts are mine. A native speaker should check them.
- **Plugin log:** `api.log()` messages are kept, but nothing on screen shows them yet.

## Decisions made
- Plugins are full Python, like Blender add-ons. Installing one from a link shows a warning.
- Language packs translate both the app's text and search terms.
- Country boards and remote boards become plugins that are on by default.
- I set up git locally now. The public repos come at the end, with your OK.

## 1. What goes where

| Part | Contents | Starts |
|---|---|---|
| **Core app** | Search, Tracker, Progress, Profile, CV reading, map, Chrome extension, updates, phone access, plugin manager. Boards: LinkedIn, Indeed, Glassdoor, ZipRecruiter | always |
| `country-boards` | Reed, Adzuna, Jobs2Careers, USAJOBS, Jobindex, Jobbird (+ their keys in Settings) | **on** |
| `remote-boards` | Himalayas, Jobicy, Remotive, RemoteOK, Arbeitnow | **on** |
| `accounting` | ICAEW, ACCA, accounting profile fields (ACCA/ICAEW membership no., qualification stage), "Qualified jobs" stats card | off |
| `gamedev` | WorkWithIndies, the game-studio map layer (Game Dev Map + Wikipedia indies), "Studios near you" card | off |
| `artists` | ArtStation, portfolio profile fields (ArtStation, Behance, showreel) | off |
| `lang-nl`, `lang-es`, `lang-da` | Dutch, Spanish and Danish translations of the app plus local job-title search terms | off; the language picker turns them on |

Each plugin is its own GitHub repo, for example `JobSlop/jobslop-plugin-accounting`. The built-in ones ship inside the app as well, so they work offline, and they update from their repo.

## 2. What a plugin looks like

```
jobslop-plugin-accounting/
  plugin.json          what it is and what it adds
  plugin.py            Python: register(api)
  ui.js                optional: screen parts (tabs, map layers, cards)
  lang/nl.json …       optional: its own translations
```

```json
{
  "id": "accounting", "name": "Accounting", "version": "1.0.0", "api": 1,
  "description": "ICAEW and ACCA job boards plus accounting profile fields",
  "author": "jobslop", "python": "plugin.py", "ui": "ui.js",
  "profile_fields": [
    {"section": "Accounting", "key": "acca_number", "label": "ACCA membership number",
     "autofill": ["acca (membership|registration) (number|no)"]}
  ]
}
```

```python
def register(api):
    api.add_board(Board(name="ICAEW", description="Chartered accountancy jobs",
                        countries=None, country_native=True, search=search_icaew))
```

- `"api": 1` is the plugin-API version. A plugin made for a newer jobslop is refused with a clear message instead of crashing.
- Simple things need no code: profile fields, settings boxes and translations are written in `plugin.json` or the `lang/` files.
- Profile fields can list `autofill` label patterns, so the Chrome extension fills them on application forms.

## 3. The API — what plugins may touch

Python side (`api` passed to `register`):

| Call | Adds |
|---|---|
| `api.add_board(Board)` | a job board: name, description, countries, needs-key, cache time, `search(query, options) → [job]` |
| `api.add_setting(key, label, secret=True)` | a box in Settings (e.g. Reed API key); read with `api.setting(key)` |
| `api.add_search_terms(lang, {"accountant": ["boekhouder"]})` | job-title translations used when searching in that language's countries |
| `api.add_endpoint("studios", fn)` | a data URL for its own screen code, served at `/api/plugin/<id>/studios` (app-only, blocked from phone) |
| `api.http.get_json / get_html`, `api.job(...)`, `api.strip_html`, `api.to_date`, `api.money`, `api.find_city`, `api.km_between`, `api.data_dir` | helpers, so plugins don't depend on internals; each plugin gets its own data folder |

Screen side (`ui.js` calls `jobslop.plugin(id, {...})`):

| Call | Adds |
|---|---|
| `addTab({id, title, icon, render(el)})` | a new tab in the header |
| `addMapLayer({id, label, draw(map, place, radiusKm)})` | a toggle + layer on the map |
| `addStatCard({id, title, render(el, stats)})` | a card on the Progress page |
| `t("text")` | the app's translator |

Plugins never get the raw server, the profile file or other plugins. They only get what's listed above. Board searches run in the existing worker pool, with the same error handling, so a broken board only shows "error" next to its name.

## 4. Code layout (SOLID)

`jobfinder.py` (3,700 lines) becomes a package. `jobfinder.py` stays as the launcher, so the build and PyCharm still work.

```
jobslop/
  config.py            version, folders, ports
  storage.py           reading/writing the JSON files
  geo/                 countries, offline towns, "Where?" resolving, distances
  boards/              Board type, registry, shared HTTP/JobSpy/Apify helpers, core boards
  search/              search engine, scoring, job match terms, cache, contract length
  tracker.py           saved jobs, statuses
  profile/             profile store, CV reading, OCR, LinkedIn import
  extension.py         Chrome extension pairing and payload
  updates.py           app updates
  i18n.py              languages, search-term translation
  plugins/             manifest checks, loader, api, install from GitHub, enable/disable
  server/              web server split by area (search, tracker, profile, map, plugins, phone)
ui/
  index.html, app.css, js/*.js   the screen split by area, plus the plugin and translation layer
plugins/               the 8 built-in plugins, each laid out exactly as its own repo
```

- **Single responsibility:** each module has one job.
- **Open/closed:** new boards, tabs, fields and cards are added through registries without editing core files. The hard-coded board lists in both files are removed, and the screen asks `/api/boards` instead.
- **Liskov substitution:** every board follows the same contract: `search(query, options)`, which can raise "not here" or "needs key".
- **Interface segregation:** small separate registrars, rather than one big object.
- **Dependency inversion:** the search engine depends on the board registry, not on specific boards.

Throughout: type hints, docstrings, no star imports, and `ruff`-clean code.

## 5. Translation

- Every visible text in the screen goes through `t("…")`, with the English text as the key, so English needs no pack.
- A language pack holds:
  - `ui.json` (English → translation).
  - `search_terms.json` (job titles).
  - `countries` (e.g. Dutch → NL and BE).
- Settings → Language lists the installed packs.
- When you search in the Netherlands with the Dutch pack on, "accountant" also searches "boekhouder" and "financieel administrateus".
- The Chrome extension popup is translated too.
- I'll write the translations myself. They'll be decent, but a native speaker should check them before release.

## 6. Installing from a link

Settings → Plugins → "Install from GitHub link":
1. Only `github.com/owner/repo` links are accepted. The app gets the repo's latest release from GitHub's API, or the default branch if there are no releases.
2. Size limit. Every zip path is checked so nothing can be written outside the plugin's folder. `plugin.json` must be valid.
3. The app shows the name, author and what the plugin adds, plus the warning *"This plugin can run code on your computer. Only install plugins from people you trust."* Nothing runs until you confirm.
4. The plugin is stored in `%APPDATA%\JobFinder\plugins\<id>`, along with the release or commit it came from. "Check for plugin updates" compares that against its repo.
5. Remove or turn off at any time. Turned off means its code isn't loaded on the next start, and its boards, tabs and fields disappear at once.

Limitation: plugins can only use Python's standard library and what jobslop already bundles. I'll make sure the common standard-library modules are included in the exe.

## 7. Steps (tests pass and a git commit at the end of each)

1. **git** — set up the repo, ignoring dist, zips, update-test and .venv. Commit the current 2.3.1 state.
2. **Split the backend into the package.** No behaviour change, and all 232 tests are moved to the new module paths.
3. **Board registry.** Boards describe themselves, `/api/boards` is added, and the screen stops hard-coding lists.
4. **Plugin system.** Manifest, loader, API, on/off, and the Settings → Plugins screen.
5. **Move boards into plugins:** country, remote, accounting, artists, then gamedev with its map layer.
6. **Split the screen and add the screen-side plugin API:** tabs, map layers, stat cards, profile fields with autofill.
7. **Translation.** Add `t()` everywhere, a language picker and search-term translation. Make the NL, ES and DA packs.
8. **Install, update and remove from GitHub links.**
9. **Build scripts** (Windows and Mac) bundle `plugins/`. Add `docs/PLUGINS.md`, a guide for plugin makers, plus a starter template.
10. **With your OK:** create the 8 public plugin repos and publish jobslop 3.0.0.

New tests: manifest checks, a bad or too-new plugin, an unsafe zip, install/enable/disable, boards from a plugin, translations, search-term expansion, plugin tabs, fields and cards appearing on screen, and the extension filling a plugin field.

## 8. Things to know

- **v2.3.1** (the update-restart fix) is built but not published. Publishing it first means everyone can update cleanly to 3.0.
- **Your data and settings carry over.** Board on/off choices and keys are moved to their plugins automatically.
- **This is several sessions of work.** Each step lands working, so we can stop between steps.
