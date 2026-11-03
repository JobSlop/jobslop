// ============================================================= updates (new versions come from GitHub Releases)
let appVersion="",upd=null,updPoll=null;
async function loadUpdate(force){
  try{upd=force?await post("/api/update",{action:"check"}):await get("/api/update")}catch(e){upd=null}
  if(!upd||upd.error&&!upd.current)return upd;
  appVersion=upd.current||"";
  $("#updinfo").innerHTML=!upd.enabled?`You have jobslop ${esc(appVersion)}. Updates aren't switched on in this copy.`
    :upd.off?`You have jobslop ${esc(appVersion)}. Updates are turned off.`
    :upd.error?`You have jobslop ${esc(appVersion)}. ${esc(upd.error)}`
    :upd.available?`You have ${esc(appVersion)} — <b style="color:var(--text)">${esc(upd.version)} is available</b>.`
    :`You have the latest version (${esc(appVersion)}).`;
  $("#updoff").checked=!!upd.off;$("#updcheck").hidden=!upd.enabled||!!upd.off;$("#updoff").closest("label").hidden=!upd.enabled;
  drawUpdBar();
  if(upd.updated_from&&pref("told_updated")!==appVersion){pref("told_updated",appVersion);
    toast(`Updated to jobslop ${appVersion} ✓`,upd.notes&&upd.version===appVersion?{label:"What's new",fn:()=>showNotes(false)}:undefined)}
  return upd;
}
// the green ⬇ in the top bar (like Discord): only there when a new version is out.
// Click it for the details; while downloading it fills up; once ready it pulses until you restart.
let updPhase="",updPct=0;              // "" | "dl" (downloading) | "ready"
function drawUpdBar(){
  const ic=$("#updicon"),pop=$("#updpop"),show=!!(upd&&upd.available&&!upd.skipped&&!PHONE);
  ic.hidden=!show;if(!show){pop.classList.remove("open");return}
  ic.classList.toggle("dl",updPhase==="dl");ic.classList.toggle("ready",updPhase==="ready");ic.style.setProperty("--p",updPct);
  ic.textContent=updPhase==="ready"?"↻":"⬇";
  ic.dataset.tip=updPhase==="ready"?"Restart to finish updating jobslop":updPhase==="dl"?`Downloading jobslop ${upd.version}… ${Math.round(updPct)}%`:`Update available — jobslop ${upd.version}`;
  ic.setAttribute("aria-label",ic.dataset.tip);if(tipFor===ic)showTip(ic);
  pop.innerHTML=`<div class="kicker">${updPhase==="ready"?"Ready to install":"Update available"}</div>
    <h4>jobslop ${esc(upd.version)}</h4>
    <div class="muted" style="font-size:12.5px">You have ${esc(upd.current)}. ${upd.can_install?"Your jobs, profile and settings are kept.":upd.how==="source"?"Get the new code from GitHub and run or build it again.":"Download it where you got jobslop (e.g. your Gumroad library) — your jobs, profile and settings are kept."}</div>
    <div class="updprog" id="updprog" ${updPhase==="dl"?"":"hidden"}><i style="width:${updPct}%"></i></div>
    <div class="acts2">${upd.notes?`<button class="pill line sm" id="updnotes">What's new</button>`:""}${updPhase?"":`<button class="pill line sm" id="updskip">Skip</button>`}
      <button class="pill dark sm" id="updgo" ${updPhase==="dl"?"disabled":""}>${updPhase==="dl"?`<span class="spin"></span> Downloading…`:updPhase==="ready"?"Restart to finish":upd.can_install?"Update now":"Get it ↗"}</button></div>`;
  const on=(id,fn)=>{const e=document.getElementById(id);if(e)e.onclick=fn};
  on("updnotes",()=>{pop.classList.remove("open");showNotes(true)});on("updgo",startUpdate);
  on("updskip",async()=>{upd=await post("/api/update",{action:"skip",version:upd.version});drawUpdBar();toast("Skipped — you'll hear about the next version")});
}
$("#updicon").onclick=e=>{e.stopPropagation();if(updPhase==="ready")return restartToUpdate();$("#themepop").classList.remove("open");$("#updpop").classList.toggle("open");hideTip()};
document.addEventListener("click",e=>{if(!e.target.closest("#updpop")&&e.target.id!=="updicon")$("#updpop").classList.remove("open")});
function showNotes(offer){$("#wntitle").textContent=`What's new in jobslop ${upd.version}`;$("#wnnotes").textContent=upd.notes||"No notes for this version.";
  $("#wnupdate").hidden=!offer;openModal("m-whatsnew")}
$("#wnupdate").onclick=()=>{closeModals();startUpdate()};
async function startUpdate(){
  if(!upd)return;
  if(!upd.can_install){openUrl(upd.get_url||upd.page);return}
  if(updPhase==="ready")return restartToUpdate();
  if(updPhase==="dl")return;
  updPhase="dl";updPct=0;drawUpdBar();
  await post("/api/update",{action:"download"});
  clearInterval(updPoll);
  updPoll=setInterval(async()=>{const st=await fetch("/api/update/status").then(r=>r.json()).catch(()=>({}));
    if(st.total){updPct=Math.min(100,100*st.done/st.total);const bar=$("#updprog i");if(bar)bar.style.width=updPct+"%";
      $("#updicon").style.setProperty("--p",updPct);$("#updicon").dataset.tip=`Downloading jobslop ${upd.version}… ${Math.round(updPct)}%`}
    if(st.busy)return;clearInterval(updPoll);
    if(st.error){updPhase="";drawUpdBar();toast(st.error);return}
    if(st.ready){updPhase="ready";updPct=100;drawUpdBar();
      toast("Update downloaded and checked ✓ — restart jobslop to finish",{label:"Restart now",fn:restartToUpdate})}},600);
}
async function restartToUpdate(){
  $("#splash").classList.remove("gone");$("#splash .word").textContent="Updating jobslop…";
  try{await post("/api/update",{action:"install"})}catch(e){}
}
$("#updcheck").onclick=()=>withSpinner($("#updcheck"),"Checking…",async()=>{const r=await loadUpdate(true);
  if(r&&r.error)toast(r.error);else if(r&&r.available)toast(`jobslop ${r.version} is available`);else toast("You're up to date ✓")});
$("#updoff").onchange=async()=>{const off=$("#updoff").checked;clearInterval(updPoll);
  await post("/api/update",{action:"off",off});await loadUpdate(false);
  toast(off?"Updates turned off — jobslop won't check for new versions":"Updates turned on")};
