"""Artists: ArtStation's job board (art, animation and games jobs worldwide)."""

api = None                                     # set by register()


def register(_api):
    global api
    api = _api
    api.add_board("ArtStation", src_artstation, "Art, animation & games jobs worldwide")


def src_artstation(q, o):
    """ArtStation Jobs - the open JSON feed of every listing (matched to your search by jobslop)."""
    out = []
    for page in (1, 2, 3):
        d = api.http.get_json(f"https://www.artstation.com/api/v2/jobs/public/jobs.json?page={page}&per_page=50",
                              headers=api.http.BROWSER_HEADERS)
        for a in d.get("data", []):
            places = []
            for loc in a.get("recruitment_localities") or []:
                place = loc.get("locality") or {}
                places.append(place.get("formatted_name")
                              or ", ".join(x for x in (place.get("city_name"), place.get("country_name")) if x))
            sr = a.get("salary_range") or {}
            sal = api.text.money(sr.get("min_salary"), sr.get("max_salary"), sr.get("currency") or "USD")
            if sal and sr.get("period") and sr["period"] != "year":
                sal += " / " + sr["period"]
            remote = bool(a.get("work_remotely"))
            location = ("Remote · " if remote else "") + "; ".join(p for p in places if p)
            out.append(api.jobs.make(
                "ArtStation", a.get("title"), a.get("company_name"),
                f"https://www.artstation.com/jobs/{a.get('hash_id')}" if a.get("hash_id") else a.get("apply_link"),
                location or ("Remote" if remote else ""),
                api.text.to_date((a.get("listing_placement") or {}).get("posted_at") or a.get("created_at")), sal,
                " · ".join(x for x in (a.get("job_type"), a.get("level")) if x), [a.get("skills") or ""],
                a.get("about") or a.get("description"), remote=remote))
        if len(d.get("data", [])) < 50:
            break
    return out
