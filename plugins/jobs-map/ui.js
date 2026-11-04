// Jobs map: your search results on a map around where you're searching (like Game dev's studio map).
// A "Jobs map" tab with the map and a list, and a layer on the Search area map. Jobs in the same town share
// one pin with a count; remote jobs and jobs whose place can't be found are counted, not pinned.
jobslop.plugin("jobs-map", api => {
  const {esc, t} = api;
  api.addStyle(`
    .jm-wrap{display:grid;grid-template-columns:minmax(0,1fr) 340px;gap:14px;margin-top:6px}
    .jm-map{height:min(620px,70vh);border-radius:16px;border:1px solid var(--line);overflow:hidden;background:var(--surface2)}
    .jm-side{display:flex;flex-direction:column;gap:8px;min-height:0}
    .jm-sum{font-size:13px;color:var(--muted);line-height:1.5}
    .jm-sum b{color:var(--text)}
    .jm-list{border:1px solid var(--line);border-radius:14px;overflow:auto;max-height:min(560px,62vh)}
    .jm-row{padding:9px 12px;border-bottom:1px solid var(--line);cursor:pointer;font-size:13px;transition:background .15s}
    .jm-row:hover,.jm-row.on{background:var(--accent-soft)}
    .jm-row .tt{font-weight:600}.jm-row .mm{color:var(--muted);font-size:12px;margin-top:2px}
    .jm-pin{min-width:26px;height:26px;padding:0 6px;border-radius:13px;display:grid;place-items:center;background:var(--accent);
      color:#fff;font-weight:700;font-size:12px;border:2px solid #fff;box-shadow:0 2px 8px rgba(0,0,0,.35);transform:translate(-50%,-50%)}
    .jm-empty{padding:30px;text-align:center;color:var(--muted)}
    @media (max-width:820px){.jm-wrap{grid-template-columns:1fr}.jm-map{height:50vh}}`);

  const remote = j => /remote|anywhere|worldwide/i.test(j.location || "") && !/hybrid/i.test(j.location || "");
  const kmBetween = (a, b, c, d) => {                       // haversine, in km
    const r = x => x * Math.PI / 180, s = Math.sin(r(c - a) / 2) ** 2 + Math.cos(r(a)) * Math.cos(r(c)) * Math.sin(r(d - b) / 2) ** 2;
    return 12742 * Math.asin(Math.sqrt(s));
  };
  // which results go on the map: those with a place, within the radius when a place is searched
  function placed() {
    const all = api.results(), {place, km} = api.searchArea();
    const located = all.filter(j => j.lat != null && j.lon != null && !remote(j));
    const inside = place ? located.filter(j => kmBetween(place.lat, place.lon, j.lat, j.lon) <= km * 1.25) : located;
    return {all, place, km, inside, remote: all.filter(remote).length, nowhere: all.length - located.length - all.filter(remote).length};
  }
  // jobs in the same spot share one pin
  function groups(jobs) {
    const by = new Map();
    jobs.forEach(j => { const k = j.lat.toFixed(3) + "," + j.lon.toFixed(3); if (!by.has(k)) by.set(k, []); by.get(k).push(j); });
    return [...by.values()];
  }
  const jobLine = j => `<a href="#" data-href="${esc(j.url)}"><b translate="no">${esc(j.title)}</b></a><br><span translate="no">${esc(j.company)}</span>`;
  function pins(L, layer, jobs) {
    const markers = [];
    groups(jobs).forEach(g => {
      const icon = L.divIcon({className: "", html: `<div class="jm-pin">${g.length}</div>`, iconSize: [0, 0]});
      const m = L.marker([g[0].lat, g[0].lon], {icon}).addTo(layer);
      m.bindPopup(`<div style="max-height:220px;overflow:auto"><div class="muted" style="font-size:12px;margin-bottom:4px" translate="no">${esc(g[0].location)}</div>`
        + g.map(jobLine).join("<hr style='border:0;border-top:1px solid #ddd;margin:6px 0'>") + "</div>");
      g.forEach(j => markers.push([j.url, m]));
    });
    return new Map(markers);
  }

  // ---- the tab: a big map and a list
  let map = null, layer = null, circle = null, byUrl = new Map(), shown = false;
  async function draw(el) {
    const {all, place, km, inside, remote: nRemote, nowhere} = placed();
    if (!el.dataset.ready) {
      el.dataset.ready = "1";
      el.innerHTML = `<div class="head"><div><div class="kicker">${t("Your search")}</div><h2 class="title">${t("Jobs Map")}</h2></div></div>
        <div class="jm-wrap"><div class="jm-map" id="jm-map"></div><div class="jm-side"><div class="jm-sum" id="jm-sum"></div><div class="jm-list" id="jm-list"></div></div></div>`;
    }
    const sum = el.querySelector("#jm-sum"), list = el.querySelector("#jm-list");
    if (!all.length) {
      sum.innerHTML = t("Search for jobs first — they appear here on the map.");
      list.innerHTML = "";
    } else {
      const where = place ? t("within {0} of {1}").replace("{0}", api.searchArea().radiusLabel).replace("{1}", place.label) : t("on the map");
      sum.innerHTML = `<b>${inside.length}</b> ${t("of your {0} results").replace("{0}", all.length)} ${esc(where)}`
        + (nRemote ? `<br>${t("{0} remote (not on the map)").replace("{0}", nRemote)}` : "")
        + (nowhere ? `<br>${t("{0} without a place we could find").replace("{0}", nowhere)}` : "")
        + (place ? "" : `<br>${t("Tip: fill in “Where?” to see your search radius.")}`);
      const sorted = place ? inside.slice().sort((a, b) => kmBetween(place.lat, place.lon, a.lat, a.lon) - kmBetween(place.lat, place.lon, b.lat, b.lon)) : inside;
      list.innerHTML = sorted.map(j => `<div class="jm-row" data-url="${esc(j.url)}"><div class="tt" translate="no">${esc(j.title)}</div>
        <div class="mm"><span translate="no">${esc(j.company)} · ${esc(j.location)}</span>${place ? ` · ${Math.round(kmBetween(place.lat, place.lon, j.lat, j.lon))} km` : ""}</div></div>`).join("")
        || `<div class="jm-empty">${t("None of these jobs are in this area.")}</div>`;
    }
    const L = await api.leaflet();
    const box = el.querySelector("#jm-map");
    if (!map) {
      map = L.map(box, {worldCopyJump: true}).setView([52.5, -1.9], 6);
      L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {maxZoom: 18,
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'}).addTo(map);
      layer = L.layerGroup().addTo(map);
    }
    setTimeout(() => map.invalidateSize(), 50);
    layer.clearLayers();
    if (circle) { circle.remove(); circle = null; }
    byUrl = pins(L, layer, inside);
    if (place) {
      circle = L.circle([place.lat, place.lon], {radius: km * 1000, color: getComputedStyle(document.documentElement).getPropertyValue("--accent").trim(), weight: 2, fillOpacity: .06}).addTo(map);
      map.fitBounds(circle.getBounds(), {padding: [20, 20]});
    } else if (inside.length) {
      map.fitBounds(L.latLngBounds(inside.map(j => [j.lat, j.lon])), {padding: [30, 30], maxZoom: 11});
    }
    list.querySelectorAll(".jm-row").forEach(r => r.onclick = () => {
      const m = byUrl.get(r.dataset.url); if (!m) return;
      list.querySelectorAll(".jm-row.on").forEach(x => x.classList.remove("on")); r.classList.add("on");
      map.flyTo(m.getLatLng(), Math.max(map.getZoom(), 11), {duration: .5}); m.openPopup();
    });
  }
  let tabEl = null;
  api.addTab({id: "map", title: t("Jobs map"), icon: "🗺", tip: t("Your search results on a map"),
              render(el) { tabEl = el; shown = true; draw(el); }});
  api.onResults(() => { if (shown && tabEl && tabEl.classList.contains("on")) draw(tabEl); });

  // ---- a layer on the "Search area" map
  api.addMapLayer({
    id: "jobs", label: "💼 " + t("Jobs from your search"), tip: t("Show the jobs from your last search on this map"),
    draw({L, group, list, place, km, radiusLabel}) {
      const jobs = api.results().filter(j => j.lat != null && !remote(j) && kmBetween(place.lat, place.lon, j.lat, j.lon) <= km);
      pins(L, group, jobs);
      list.innerHTML = `<div class="maplisthead"><b>${jobs.length}</b> ${esc(t("jobs from your search within {0}").replace("{0}", radiusLabel))}</div>`
        + (jobs.length ? "" : `<div class="muted" style="padding:8px">${esc(t("Search for jobs first, or pick a bigger radius."))}</div>`);
    },
  });
});
