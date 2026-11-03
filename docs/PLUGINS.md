# Making a jobslop plugin

A plugin adds things to jobslop:
- job boards
- profile fields the Chrome extension fills in
- settings
- tabs
- map layers
- Progress cards
- languages

It lives in its own GitHub repository. People install it by pasting the link in **Settings → Plugins → Install from link**.

Start from [`plugin-template/`](plugin-template/), and look at the plugins that come with jobslop in [`../plugins/`](../plugins/):

| Plugin | Shows how to |
|---|---|
| `accounting` | add boards, profile fields with autofill, a Progress card, job titles in other languages |
| `gamedev` | add a board, a server endpoint, a map layer, a tab, a Progress card, and split code over two files |
| `country-boards` | add boards that need API keys (settings) |
| `lang-nl`, `lang-es`, `lang-da` | make a language pack (no code at all) |

## What's in a plugin

```
my-plugin/                 (the top of the GitHub repository)
  plugin.json              required: what it is and what it adds
  plugin.py                optional: Python, with register(api)
  ui.js                    optional: screen code, with jobslop.plugin(...)
  lang/nl.json …           optional: its own words in other languages
  README.md
```

Releases matter. jobslop installs the **latest GitHub release** of the repository, or the default branch when there are no releases. Tag releases with the version, e.g. `v1.2.0`, and keep `version` in `plugin.json` the same. "Check for plugin updates" compares the two.

## plugin.json

```json
{
  "id": "my-plugin",
  "name": "My plugin",
  "version": "1.0.0",
  "api": 1,
  "description": "One or two sentences people see before installing.",
  "author": "your name",
  "homepage": "https://github.com/you/jobslop-plugin-my-plugin",
  "python": "plugin.py",
  "ui": "ui.js",
  "enabled_by_default": false,
  "profile_fields": [
    {"key": "portfolio_pdf", "label": "Portfolio PDF link", "section": "Portfolio", "type": "url",
     "autofill": ["portfolio (pdf|link)"]}
  ],
  "settings": [
    {"key": "my_board_key", "label": "My Board API key", "type": "secret",
     "help": "Free key:", "link": "https://example.com/developers"}
  ],
  "translations": {"nl": "lang/nl.json"},
  "search_terms": {"nl": "lang/nl-titles.json"},
  "language": {"code": "nl", "name": "Nederlands", "countries": ["NL", "BE"]}
}
```

| Field | Notes |
|---|---|
| `id` | a–z, 0–9 and `-`. It can't be the id of a plugin that comes with jobslop. |
| `version` | Like `1.2.0`. |
| `api` | The plugin API version it was made for. It's **1** now. jobslop refuses plugins made for a newer API and asks the user to update jobslop. |
| `python`, `ui` | Files inside the plugin. Leave them out if you don't need them. |
| `profile_fields` | `type` is one of `text`, `area`, `yn`, `email`, `tel`, `url`. `autofill` holds regular expressions (case-insensitive) for form labels. The Chrome extension fills the field into matching boxes, and checks these before its own rules. |
| `settings` | Boxes under Settings → Job board keys. `type` is `secret` (hidden, shown masked) or `text`. Read them with `api.setting("my_board_key")`. |
| `translations` | Language code → JSON file of `{"English text": "translation"}` for your own screen text. |
| `search_terms` | Language code → JSON file of `{"english job title": ["local title", ...]}`. |
| `language` | Makes this a **language pack**: it appears in the language picker, and its job titles are used for searches in `countries`. |

Everything in `plugin.json` is checked before any of your code runs. A mistake shows up as a message on your plugin's card in Settings.

## plugin.py

```python
api = None                      # handy: keep the api for your search functions


def register(_api):
    global api
    api = _api
    api.add_board("My Board", search, "Short description for the board's chip",
                  group="specialist", countries={"GB", "IE"}, needs=("my_board_key",))


def search(query, options):
    if options["country"] not in ("GB", "IE"):
        raise api.jobs.NotHere("UK & Ireland only")
    key = api.setting("my_board_key")
    if not key:
        raise api.jobs.NeedsKey("add a free key in Settings")
    data = api.http.get_json("https://example.com/api/jobs?q=" + query, headers={"X-Key": key})
    return [api.jobs.make("My Board", j["title"], j["company"], j["url"], j["location"],
                          api.text.to_date(j["posted"]), api.text.money(j["min"], j["max"], "GBP"))
            for j in data["jobs"]]
```

`register(api)` runs when the plugin is switched on. When it's switched off, everything it added goes away again. Your code can import its other files with `from . import helpers`.

### What `api` gives you

**Adding things**

| Call | What it does |
|---|---|
| `api.add_board(name, search, description="", *, group="specialist", countries=None, country_native=False, location_aware=False, native_types=False, needs=(), slow_without="", cache_seconds=900)` | A job board. `group` is one of `main`, `country`, `specialist`, `remote`. `countries` is `None` for everywhere. `country_native` means its results are already in the chosen country, and `location_aware` that it searches around the town itself. `needs` lists settings that must be filled in. |
| `api.add_setting(key, label, *, secret=True, help="", link="")` | A settings box, the same as in `plugin.json`. |
| `api.add_endpoint(name, fn)` | Data for your screen code at `/api/plugin/<id>/<name>`. `fn(params, body)` returns something JSON can hold. Only jobslop's own window can call it, never other websites. |
| `api.add_search_terms(lang, {"accountant": ["boekhouder"]})` | Job titles in a language. |
| `api.add_translations(lang, {"Text": "Tekst"})` | Screen text in a language. |

**Using things**

| Name | What it is |
|---|---|
| `api.setting(key)` | A setting's value, `""` if empty. |
| `api.data_dir` | A folder of your own for files you want to keep. |
| `api.log(message)` | A line for the plugin log. |
| `api.http.get_json(url, timeout=20, headers=None)`, `api.http.get_text(url, timeout=25)`, `api.http.BROWSER_HEADERS` | Fetching from the web. |
| `api.jobs.make(source, title, company, url, location="", date="", salary="", jtype="", tags=None, desc="", remote=True)` | One job, the way jobslop shows it. |
| `api.jobs.NotHere`, `api.jobs.NeedsKey` | Raise these from `search` and jobslop shows "not available here" or "needs key" next to the board. Any other error shows as the board's error, and other boards keep working. |
| `api.jobs.km_radius(options)` | The search radius in km. |
| `api.text.strip_html`, `to_date`, `rel_date` ("3 days ago"), `short_date`, `money(lo, hi, currency)` | Turning raw text into jobslop's formats. |
| `api.geo.find_town(name, country=None)`, `place_town(text, country=None)`, `nearest_town(lat, lon)` | jobslop's offline list of ~70,000 towns. Each returns `{"name", "lat", "lon", "country", "region", "population"}` or `None`. |
| `api.geo.km_between`, `town_at_end(text, country)`, `country(code)`, `country_code(text)`, `is_country_name(text, code)`, `normalise(text)` | Distances, countries and place names. |

**Search options.** The `options` passed to `search` hold:
- `where` (a town or `""`) and `miles`
- `country` (an ISO code like `"GB"`) and `local`
- `posted`, `jtype`, `remote`, `salary_min` and `intern`

Results are reused for `cache_seconds` before your board is asked again.

**What a plugin can use.** Python's standard library, plus `jobslop`'s bundled packages. Don't import `jobslop.*`: it isn't part of the API and can change in any version. Everything you need is on `api`, and if something is missing, ask for it.

## ui.js

```js
jobslop.plugin("my-plugin", api => {
  api.addStyle(`.my-thing{color:var(--accent)}`);

  api.addTab({id: "main", title: "My tab", icon: "✨", tip: "What this tab is for",
              render(el) { el.innerHTML = `<h2 class="title">${api.esc(api.t("Hello"))}</h2>`; }});

  api.addStatCard({id: "count", title: "My numbers",
                   render(el, {saved, stats}) { el.innerHTML = `<div class="row"><span>Saved</span><b>${saved.length}</b></div>`; }});

  api.addMapLayer({id: "places", label: "📍 My places", options: [["all", "All"], ["new", "New only"]],
    async draw({L, map, group, list, place, km, option}) {
      const r = await api.call("places", {lat: place.lat, lon: place.lon, km});
      r.items.forEach(p => L.marker([p.lat, p.lon]).addTo(group));
      list.innerHTML = `<div class="maplisthead">${r.items.length} places</div>`;
    }});
});
```

| Call | What it does |
|---|---|
| `api.addTab({id, title, icon, tip, render(el)})` | A tab in the header. `render` runs each time it's opened. |
| `api.addMapLayer({id, label, tip, options, draw(ctx)})` | A tick, and an optional choice, on the Search area map. `ctx` is `{L, map, group, list, place, km, radiusLabel, option}`: draw markers into `group` and a list into `list`. |
| `api.addStatCard({id, title, render(el, {saved, stats})})` | A card on the Progress page. |
| `api.addStyle(css)` | Your styles. Use jobslop's colour variables (`--accent`, `--surface`, `--line`, `--muted`…) so light and dark modes both work. |
| `api.call(name, params)`, `api.send(name, body)` | Your plugin's endpoints. |
| `api.saved()`, `api.profile()` | Copies of the saved jobs and the profile. |
| `api.pref(key, value?)` | A small remembered setting for your screen. |
| `api.t(text)`, `api.esc(text)`, `api.toast(text)`, `api.openUrl(url)`, `api.unit()` | Translation, safe HTML, a short message, opening a link, and "mi"/"km". |

Switching the plugin off removes its tabs, layers, cards and styles.

## Languages

jobslop's screen is written in English. With another language chosen, any text whose English is in a language's word list is swapped for the translation, including text drawn later. Text with values in it matches `{0}`, `{1}`…, e.g. `"Found {0} jobs": "{0} vacatures gevonden"`.

Job titles, company names and places are marked `translate="no"` and never change. Mark your own user data the same way.

To make a language pack:
1. Copy `plugins/lang-nl`.
2. Change `id`, `name` and `language`, then translate `lang/ui.json` and `lang/search_terms.json`.
3. `python tools/extract_strings.py strings.json` lists every English text on the screen, to check nothing is missing.

## Safety

- Plugins are Python, so a plugin can do anything the user's account can. Before installing, jobslop shows what a plugin adds and warns when it runs code. It's only installed once the user confirms.
- Downloads come only from GitHub. They're limited in size and number of files, and no file may land outside the plugin's folder. Links inside the zip are refused.
- A plugin from a link can't take the id of a built-in plugin, unless the link is that plugin's own repository.
- Plugin endpoints and files only answer jobslop's own window. From a phone, plugins can't be installed, removed or switched on and off.

## Testing your plugin

Put the folder in jobslop's data folder under `plugins/`:
- **Windows:** `%APPDATA%\JobFinder\plugins\my-plugin`
- **Mac:** `~/Library/Application Support/JobFinder/plugins/my-plugin`

Restart jobslop and switch it on in Settings → Plugins. Errors show on its card.
