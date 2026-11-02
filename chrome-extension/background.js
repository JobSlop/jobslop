// Talks to the jobslop app on this computer. Keeps a copy of the profile and CV so
// filling still works when the app is closed.
const BASE = "http://127.0.0.1:47321";

// Auto-pairing: jobslop writes pairing.json into this folder when it sets the extension up,
// so it connects without typing a code. (A code typed in the popup still works and wins.)
async function autoKey() {
  try {
    const r = await fetch(chrome.runtime.getURL("pairing.json"), { cache: "no-store" });
    const { code } = await r.json();
    return (code || "").trim().toUpperCase();
  } catch (e) { return ""; }
}
async function ensureKey() {
  const { key, manual } = await chrome.storage.local.get(["key", "manual"]);
  if (manual && key) return key;
  const k = await autoKey();
  if (k && k !== key) await chrome.storage.local.set({ key: k });
  return k || key || "";
}
chrome.runtime.onInstalled.addListener(ensureKey);
chrome.runtime.onStartup.addListener(ensureKey);

async function api(path, options = {}) {
  const key = await ensureKey();
  const r = await fetch(BASE + path, {
    ...options,
    headers: { "X-JobFinder-Key": key || "", "Content-Type": "application/json" },
  });
  if (r.status === 401) throw new Error("bad-code");
  if (!r.ok) throw new Error("http-" + r.status);
  return r.json();
}

async function getData() {
  try {
    const d = await api("/ext/profile");
    await chrome.storage.local.set({ cache: d });
    return { ...d, live: true };
  } catch (e) {
    const { cache } = await chrome.storage.local.get("cache");
    return cache ? { ...cache, active: null, live: false, error: e.message } : { error: e.message };
  }
}

async function getCv() {
  try {
    const cv = await api("/ext/cv");
    if (cv && cv.data) await chrome.storage.local.set({ cvcache: cv });
    return cv;
  } catch (e) {
    const { cvcache } = await chrome.storage.local.get("cvcache");
    return cvcache || null;
  }
}

function fillTab(tabId) {
  // Goes to every frame in the tab (application forms are often inside iframes)
  chrome.tabs.sendMessage(tabId, { type: "fill" }, () => void chrome.runtime.lastError);
}

chrome.runtime.onMessage.addListener((msg, sender, reply) => {
  const tabId = sender.tab && sender.tab.id;
  (async () => {
    switch (msg.type) {
      case "getData": return reply(await getData());
      case "getCv": return reply(await getCv());
      case "pair": {
        await chrome.storage.local.set({ key: (msg.key || "").trim().toUpperCase(), manual: true });
        try { const d = await api("/ext/profile"); await chrome.storage.local.set({ cache: d }); reply({ ok: true, name: d.profile.first_name || "" }); }
        catch (e) { reply({ ok: false, error: e.message }); }
        return;
      }
      case "status": return reply(await getData());
      case "formHere":
        if (tabId != null) chrome.tabs.sendMessage(tabId, { type: "showButton" }, { frameId: 0 }, () => void chrome.runtime.lastError);
        return reply(true);
      case "fillTab": {
        const id = msg.tabId || tabId;
        if (id != null) fillTab(id);
        return reply(true);
      }
      case "frameResult":
        if (tabId != null) chrome.tabs.sendMessage(tabId, { type: "result", n: msg.n, cv: msg.cv, left: msg.left }, { frameId: 0 }, () => void chrome.runtime.lastError);
        return reply(true);
      case "undoTab":
        if (tabId != null) chrome.tabs.sendMessage(tabId, { type: "undo" }, () => void chrome.runtime.lastError);
        return reply(true);
      case "liWanted":
        try { reply(await api("/ext/linkedin/wanted")); } catch (e) { reply(null); }
        return;
      case "liFound":
        try { await api("/ext/linkedin", { method: "POST", body: JSON.stringify({ page: msg.page || null, error: msg.error || "" }) }); reply(true); }
        catch (e) { reply(false); }
        return;
      case "markApplied":
        try { await api("/ext/applied", { method: "POST", body: JSON.stringify({ url: msg.url || "" }) }); reply(true); }
        catch (e) { reply(false); }
        return;
    }
    reply(null);
  })();
  return true; // keep the channel open for the async reply
});

chrome.commands.onCommand.addListener(async (cmd) => {
  if (cmd !== "fill-form") return;
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (tab) fillTab(tab.id);
});
