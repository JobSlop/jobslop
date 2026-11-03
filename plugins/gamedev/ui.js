// Game dev: studios on the "Search area" map, a Studios tab, and a Progress card for games applications.
jobslop.plugin("gamedev", api => {
  const {esc, t} = api;
  api.addStyle(`
    .studiodot{width:22px;height:22px;border-radius:7px;display:grid;place-items:center;background:var(--surface2);border:1.5px solid var(--accent);font-size:12px;box-shadow:0 2px 6px rgba(0,0,0,.25);transition:transform .15s}
    .studiodot:hover{transform:scale(1.25)}
    .studiodot.indie{background:var(--accent);color:#fff;border-color:#fff;font-weight:700}
    .indietag{display:inline-block;font-size:10.5px;font-weight:700;letter-spacing:.04em;padding:1px 7px;border-radius:999px;background:var(--accent-soft);color:var(--accent)}
    .gd-bar{display:flex;gap:8px;flex-wrap:wrap;align-items:flex-end;margin:6px 0 14px}
    .gd-bar .f{min-width:150px}`);

  const indie = s => s.indie ? ` <span class="indietag">${t("Indie")}</span>` : "";
  const link = s => s.source === "Wikipedia" ? t("Read about them ↗") : t("Visit website ↗");
  function rows(list, max) {
    return list.slice(0, max).map(s => `<div class="maplistrow" data-href="${esc(s.url)}" title="${esc(t("Open"))} ${esc(s.name)}">
      <span><b>${esc(s.name)}</b>${indie(s)} <span class="muted">${esc(s.type)}</span></span>
      <span class="muted">${esc(s.city)} · ${Math.round(s.dist_km)} km</span></div>`).join("");
  }

  // ---- map layer
  api.addMapLayer({
    id: "studios", label: "🎮 " + t("Game studios"),
    tip: t("Show game studios from Game Dev Map and Wikipedia's indie developer list"),
    options: [["all", t("All studios")], ["indie", t("Indie studios only")]],
    async draw({L, group, list, place, km, radiusLabel, option}) {
      list.innerHTML = `<div class="muted" style="padding:8px"><span class="spin"></span> ${t("Finding game studios…")}</div>`;
      const r = await api.call("studios", {lat: place.lat, lon: place.lon, km, kind: option});
      const icon = L.divIcon({className: "", html: '<div class="studiodot">🎮</div>', iconSize: [22, 22], iconAnchor: [11, 11]});
      const indieIcon = L.divIcon({className: "", html: '<div class="studiodot indie">✦</div>', iconSize: [22, 22], iconAnchor: [11, 11]});
      r.studios.forEach(s => L.marker([s.lat + (Math.random() - .5) * .01, s.lon + (Math.random() - .5) * .01], {icon: s.indie ? indieIcon : icon})
        .addTo(group).bindPopup(`<b>${esc(s.name)}</b>${indie(s)}<br>${esc(s.type)} · ${esc(s.city)}<br><a href="#" data-href="${esc(s.url)}">${link(s)}</a>`));
      const indieN = r.studios.filter(s => s.indie).length, only = option === "indie";
      list.innerHTML = `<div class="maplisthead"><b>${r.studios.length} ${only ? t("indie game studios") : t("game studios")}</b> ${t("within")} ${esc(radiusLabel)}`
        + `${!only && indieN ? ` <span class="indietag">${indieN} ${t("indie")}</span>` : ""} <span class="muted">· Game Dev Map + Wikipedia</span></div>`
        + (r.studios.length ? rows(r.studios, 120)
          : `<div class="muted" style="padding:8px">${t("No studios listed in this area — try a bigger radius.")}</div>`);
    },
  });

  // ---- Studios tab: studios around your town (from your profile), with links
  api.addTab({
    id: "studios", title: t("Studios"), icon: "🎮", tip: t("Game studios near you, from Game Dev Map and Wikipedia"),
    render(el) {
      const p = api.profile();
      if (!el.dataset.ready) {
        el.dataset.ready = "1";
        el.innerHTML = `<div class="head"><div><div class="kicker">${t("Game dev")}</div><h2 class="title">${t("Studios Near You")}</h2></div></div>
          <div class="gd-bar">
            <label class="f">${t("Town")}<input type="text" id="gd-town" placeholder="${esc(t("e.g. Leamington Spa"))}"></label>
            <label class="f">${t("Within")}<select id="gd-km"><option value="25">25 km</option><option value="50" selected>50 km</option><option value="100">100 km</option><option value="250">250 km</option></select></label>
            <label class="f">${t("Show")}<select id="gd-kind"><option value="all">${t("All studios")}</option><option value="indie">${t("Indie studios only")}</option></select></label>
            <button class="pill dark sm" id="gd-go">${t("Show studios")}</button></div>
          <div id="gd-list" class="maplist" style="max-height:none"></div>`;
        el.querySelector("#gd-town").value = api.pref("town") || p.city || "";
        el.querySelector("#gd-go").onclick = () => show();
        el.querySelector("#gd-town").addEventListener("keydown", e => { if (e.key === "Enter") show(); });
      }
      show();
      async function show() {
        const town = el.querySelector("#gd-town").value.trim(), out = el.querySelector("#gd-list");
        if (!town) return out.innerHTML = `<div class="muted" style="padding:10px">${t("Type a town to see the studios around it.")}</div>`;
        api.pref("town", town);
        out.innerHTML = `<div class="muted" style="padding:10px"><span class="spin"></span> ${t("Finding game studios…")}</div>`;
        const r = await api.call("studios", {town, country: p.country || "", km: el.querySelector("#gd-km").value,
                                             kind: el.querySelector("#gd-kind").value});
        if (r.error) return out.innerHTML = `<div class="muted" style="padding:10px">${esc(r.error)}</div>`;
        out.innerHTML = `<div class="maplisthead"><b>${r.studios.length} ${t("game studios")}</b> ${t("around")} ${esc(r.place || town)}</div>`
          + (rows(r.studios, 300) || `<div class="muted" style="padding:10px">${t("No studios listed here — try a bigger distance.")}</div>`);
      }
    },
  });

  // ---- Progress card: how your games applications are going
  const GAMES = /\b(game|games|gameplay|unity|unreal|godot|level design|technical artist|qa tester)\b/i;
  api.addStatCard({
    id: "games", title: t("Games applications"),
    render(el, {saved}) {
      const games = saved.filter(j => ["WorkWithIndies", "ArtStation"].includes(j.source) || GAMES.test(j.title || ""));
      const by = s => games.filter(j => j.status === s).length;
      el.innerHTML = games.length
        ? `<div class="row"><span>${t("Games jobs tracked")}</span><b>${games.length}</b></div>
           <div class="row"><span>${t("Applied")}</span><b>${by("Applied") + by("Interview") + by("Offer") + by("Rejected")}</b></div>
           <div class="row"><span>${t("Interviews")}</span><b>${by("Interview") + by("Offer")}</b></div>`
        : `<p class="muted" style="font-size:13px">${t("Save a games job to see it here.")}</p>`;
    },
  });
});
