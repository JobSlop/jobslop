"""My plugin: a job board for jobslop. Rename things, then fill in search()."""

api = None                                     # set by register()


def register(_api):
    """Runs when the plugin is switched on. Everything added here goes away when it is switched off."""
    global api
    api = _api
    api.add_board("My Board", search, "Jobs from my board", group="specialist")


def search(query, options):
    """Return jobs for a search. options: where, miles, country, local, posted, jtype, remote, salary_min, intern."""
    data = api.http.get_json("https://example.com/api/jobs?q=" + query)
    return [api.jobs.make("My Board", j.get("title"), j.get("company"), j.get("url"), j.get("location", ""),
                          api.text.to_date(j.get("posted")))
            for j in data.get("jobs", [])]
