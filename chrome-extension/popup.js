const $ = (id) => document.getElementById(id);
const send = (msg) => new Promise((res) => chrome.runtime.sendMessage(msg, (r) => { void chrome.runtime.lastError; res(r); }));

function setState(text, kind) {
  $("state").textContent = text;
  $("dot").className = "dot " + (kind || "");
}

async function refresh() {
  const d = await send({ type: "status" });      // pairs automatically when jobslop set the extension up
  if (d && d.profile) {
    const name = d.profile.first_name ? ` as ${d.profile.first_name}` : "";
    if (d.live) setState(`Connected${name}`, "ok");
    else setState("jobslop is closed — using your saved copy", "bad");
    $("cv").textContent = d.cv_name ? `CV: ${d.cv_name}` : "No CV uploaded yet.";
    $("pair").style.display = "none";
    $("main").style.display = "block";
  } else if (d && d.error === "bad-code") {
    showPair("That code doesn't match");
  } else {
    showPair("Can't reach jobslop — is it open?");
  }
}

function showPair(msg) {
  setState(msg || "Not connected", "bad");
  $("cv").textContent = "";
  $("pair").style.display = "block";
  $("main").style.display = "none";
}

$("connect").onclick = async () => {
  $("connect").textContent = "Connecting…";
  const r = await send({ type: "pair", key: $("code").value });
  $("connect").textContent = "Connect";
  if (r && r.ok) refresh();
  else showPair(r && r.error === "bad-code" ? "That code doesn't match" : "Can't reach jobslop — is it open?");
};
$("code").addEventListener("keydown", (e) => { if (e.key === "Enter") $("connect").click(); });
$("fill").onclick = async () => {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (tab) await send({ type: "fillTab", tabId: tab.id });
  window.close();
};
$("change").onclick = () => showPair("");
refresh();
