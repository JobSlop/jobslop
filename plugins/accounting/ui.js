// Accounting: a Progress card showing how accounting applications are going, by qualification level.
jobslop.plugin("accounting", api => {
  const {t} = api;
  const ACCOUNTING = /\b(account(ant|ancy|ing)?|bookkeep(er|ing)|audit(or)?|tax|payroll|controller|finance|financial|aca|acca|cima|aat)\b/i;
  const PART = /\b(part[- ]qualified|trainee|graduate|aat|studying)\b/i;
  api.addStatCard({
    id: "accounting", title: t("Accounting applications"),
    render(el, {saved}) {
      const jobs = saved.filter(j => ["ICAEW", "ACCA"].includes(j.source) || ACCOUNTING.test(j.title || ""));
      const applied = jobs.filter(j => ["Applied", "Interview", "Offer", "Rejected"].includes(j.status));
      const part = jobs.filter(j => PART.test(`${j.title} ${j.desc || ""}`)).length;
      el.innerHTML = jobs.length
        ? `<div class="row"><span>${t("Accounting jobs tracked")}</span><b>${jobs.length}</b></div>
           <div class="row"><span>${t("Applied")}</span><b>${applied.length}</b></div>
           <div class="row"><span>${t("Part-qualified / trainee roles")}</span><b>${part}</b></div>
           <div class="row"><span>${t("From ICAEW & ACCA")}</span><b>${jobs.filter(j => ["ICAEW", "ACCA"].includes(j.source)).length}</b></div>`
        : `<p class="muted" style="font-size:13px">${t("Save an accounting job to see it here.")}</p>`;
    },
  });
});
