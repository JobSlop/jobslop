// My plugin's screen part: a card on the Progress page (delete this file and "ui" in plugin.json if you don't need it).
jobslop.plugin("my-plugin", api => {
  api.addStatCard({
    id: "mine", title: api.t("From My Board"),
    render(el, {saved}) {
      const mine = saved.filter(j => j.source === "My Board");
      el.innerHTML = `<div class="row"><span>${api.esc(api.t("Jobs tracked"))}</span><b>${mine.length}</b></div>`;
    },
  });
});
