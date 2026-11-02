// ============================================================= plugins
let plugins={plugins:[],profile_fields:[],settings:[]};
const allKeys=()=>KEYS.concat(plugins.settings.map(s=>s.key));
async function loadPlugins(){plugins=await get("/api/plugins");drawPlugins()}
function drawPlugins(){
  $("#plugs").innerHTML=plugins.plugins.map(p=>`<div class="plug ${p.enabled?"on":""}">
    <div class="ph"><div><div class="pn">${esc(p.name)}${p.builtin?'<span class="tag">BUILT IN</span>':""}</div>
      <div class="pv">v${esc(p.version)}${p.author?" · "+esc(p.author):""}</div></div>
      <label class="sw" data-tip="${p.enabled?"Switch off":"Switch on"} ${esc(p.name)}"><input type="checkbox" class="plugsw" data-id="${esc(p.id)}" ${p.enabled?"checked":""} ${p.error&&!p.enabled&&!p.version?"disabled":""} aria-label="${esc(p.name)}"><span></span></label></div>
    ${p.description?`<div class="pd">${esc(p.description)}</div>`:""}
    ${p.adds.length?`<div class="pa">${p.adds.map(a=>`<span>${esc(a)}</span>`).join("")}</div>`:""}
    ${p.error?`<div class="perr">⚠ ${esc(p.error)}</div>`:""}
    ${p.homepage?`<span class="linkish" style="font-size:12px" data-href="${esc(p.homepage)}">Website ↗</span>`:""}</div>`).join("")
    ||`<p class="muted" style="font-size:13px">No plugins yet.</p>`;
  $$(".plugsw").forEach(c=>c.onchange=()=>togglePlugin(c.dataset.id,c.checked));
  const gd=plugins.plugins.some(p=>p.id==="gamedev"&&p.loaded);           // studios on the map come from Game dev
  $("#mapstudios").closest("label").hidden=!gd;$("#studiokind").hidden=!gd;if(!gd)$("#studiolist").hidden=true;
  // boxes plugins add to Settings (API keys and the like), saved with "Save settings"
  const bySec={};plugins.settings.forEach(s=>{const n=(plugins.plugins.find(p=>p.id===s.plugin)||{}).name||s.plugin;(bySec[n]=bySec[n]||[]).push(s)});
  $("#plugsettings").innerHTML=Object.entries(bySec).map(([n,ss])=>`<div class="psec" style="margin-top:12px">${esc(n)}</div><div class="pgrid">${ss.map(s=>
    `<label class="f">${esc(s.label)}<input type="${s.type==="secret"?"password":"text"}" id="${esc(s.key)}" autocomplete="off"></label>`).join("")}</div>
    ${ss.filter(s=>s.help||s.link).map(s=>`<p class="muted" style="font-size:12.5px;margin:4px 0 10px">${esc(s.help)} ${s.link?`<span class="linkish" data-href="${esc(s.link)}">${esc(s.link.replace(/^https:\/\//,""))}</span>`:""}</p>`).join("")}`).join("");
  plugins.settings.forEach(s=>{const el=$("#"+s.key);if(el)el.placeholder=keys[s.key]?"saved ("+keys[s.key]+") — paste to replace":"paste here"});
}
async function togglePlugin(id,on){
  const p=plugins.plugins.find(x=>x.id===id)||{name:id};
  plugins=await post("/api/plugins",{id,enabled:on});drawPlugins();
  const now=plugins.plugins.find(x=>x.id===id)||{};
  if(on&&now.error)return toast(`${p.name} couldn't start — see the message on its card`);
  keys=await get("/api/settings");await loadBoards();render();
  toast(`${p.name} ${on?"switched on":"switched off"}`);
}
// "Save settings" saves everything in the Settings window: keys and job match terms
$("#savekeys").onclick=()=>withSpinner($("#savekeys"),"Saving…",async()=>{const b={};allKeys().forEach(k=>{const el=$("#"+k);if(!el)return;const v=el.value.trim();if(v)b[k]=v;el.value=""});
  await post("/api/settings",b);
  matchTerms=await post("/api/match_terms",{terms:matchTerms.filter(t=>(t.name||"").trim())});drawTerms();
  await loadKeys();closeModals();render();toast("Settings saved")});
