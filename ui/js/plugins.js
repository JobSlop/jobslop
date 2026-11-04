// ============================================================= plugins
// What switched-on plugins add to the screen. A plugin's ui.js calls
//   jobslop.plugin("its-id", api => { api.addTab({...}); api.addMapLayer({...}); api.addStatCard({...}) })
// Everything it adds is remembered under its id and taken away again when it is switched off.
const jobslop=(()=>{
  const parts={tabs:[],layers:[],cards:[],listeners:[]};
  const scripts={};                                       // plugin id -> the ui.js url that's running
  function plugin(id,setup){
    remove(id,true);
    const api={
      id,version:1,
      // a tab in the header: {id, title, icon, render(el)} — render is called each time the tab is opened
      addTab(o){parts.tabs.push({...o,plugin:id,key:`p-${id}-${o.id}`});drawPluginTabs()},
      // a layer on the "Search area" map: {id, label, tip, options:[[value,label]...], draw(ctx)}
      // ctx = {L, map, group, list, place, km, radiusLabel, option}; draw markers into group, a list into list
      addMapLayer(o){parts.layers.push({...o,plugin:id,key:`${id}-${o.id}`});drawMapLayerControls()},
      // a card on the Progress page: {id, title, render(el, {saved, stats})}
      addStatCard(o){parts.cards.push({...o,plugin:id,key:`${id}-${o.id}`});if(tab==="progress")drawPluginCards()},
      addStyle(css){const s=document.createElement("style");s.dataset.plugin=id;s.textContent=css;document.head.appendChild(s)},
      // the plugin's own server endpoints (api.add_endpoint in its plugin.py)
      call(name,params){return get(`/api/plugin/${id}/${name}?`+new URLSearchParams(params||{}))},
      send(name,body){return post(`/api/plugin/${id}/${name}`,body||{})},
      saved:()=>JSON.parse(JSON.stringify(saved)),profile:()=>JSON.parse(JSON.stringify(profile)),
      // the search results you can see right now (after the filters), and where you're searching
      results:()=>JSON.parse(JSON.stringify(visible(results,false))),
      searchArea:()=>({place:whereLoc&&whereLoc.lat!=null?{lat:whereLoc.lat,lon:whereLoc.lon,label:whereLoc.label||whereLoc.town||""}:null,
                       km:toMiles(+$("#miles").value||15,"mi")*1.609,radiusLabel:fmtRadius()}),
      onResults(fn){parts.listeners.push({plugin:id,event:"results",fn})},       // new results or changed filters
      leaflet:()=>loadLeaflet().then(()=>window.L),                              // the map library, loaded on first use
      pref:(k,v)=>pref(`plug_${id}_${k}`,v),
      t:s=>t(s),esc,toast,openUrl,unit:()=>unit(),
    };
    try{setup(api)}catch(e){console.error(e);toast(`${id}: its screen part couldn't start`)}
  }
  function remove(id,quiet){
    parts.tabs.filter(x=>x.plugin===id).forEach(x=>{const b=$(`.navlinks .tab[data-tab="${x.key}"]`);if(b)b.remove();const s=$("#v-"+x.key);if(s)s.remove();if(tab===x.key&&!quiet)setTab("search")});
    parts.layers.filter(x=>x.plugin===id).forEach(x=>{if(x.group)x.group.remove();const l=$("#ml-"+x.key);if(l)l.remove()});
    $$(`style[data-plugin="${id}"]`).forEach(s=>s.remove());
    for(const k in parts)parts[k]=parts[k].filter(x=>x.plugin!==id);
    drawPluginTabs();drawMapLayerControls();drawPluginCards();
  }
  // run the screen code of every switched-on plugin (once), and stop it for switched-off ones
  function sync(list){
    list.forEach(p=>{
      if(p.loaded&&p.ui&&scripts[p.id]!==p.ui+p.version){scripts[p.id]=p.ui+p.version;
        const s=document.createElement("script");s.src=p.ui+"?v="+encodeURIComponent(p.version)+"&t="+Date.now();s.dataset.plugin=p.id;document.body.appendChild(s)}
      if(!p.loaded&&scripts[p.id]){delete scripts[p.id];remove(p.id)}});
  }
  const tabFor=key=>parts.tabs.find(x=>x.key===key);
  function emit(event){parts.listeners.filter(l=>l.event===event).forEach(l=>{try{l.fn()}catch(e){console.error(e)}})}
  return {plugin,remove,sync,parts,tabFor,emit};
})();

// "+15 mi" / "+25 km": the search radius as the screen shows it
function fmtRadius(){const o=$("#miles").selectedOptions[0];return o?o.textContent.replace(/^\+/,""):""}
function drawPluginTabs(){
  const nav=$(".navlinks");
  jobslop.parts.tabs.forEach(x=>{
    if(!$(`.navlinks .tab[data-tab="${x.key}"]`)){
      const b=document.createElement("button");b.className="tab";b.dataset.tab=x.key;b.textContent=(x.icon?x.icon+" ":"")+x.title;
      if(x.tip)b.dataset.tip=x.tip;b.onclick=()=>setTab(x.key);
      const tabs=$$(".navlinks .tab");tabs[tabs.length-1].after(b)}                 // next to the app's own tabs
    if(!$("#v-"+x.key)){const s=document.createElement("section");s.className="view";s.id="v-"+x.key;
      $("#v-profile").after(s)}});
}
function drawPluginCards(){
  const box=$("#plugcards");if(!box)return;
  const cards=jobslop.parts.cards;box.hidden=!cards.length;
  box.innerHTML=cards.map(c=>`<div class="panel list2"><h3>${esc(c.title)}</h3><div data-card="${esc(c.key)}"></div></div>`).join("");
  cards.forEach(c=>{try{c.render($(`[data-card="${c.key}"]`),{saved:JSON.parse(JSON.stringify(saved)),stats:stats()})}
    catch(e){console.error(e);$(`[data-card="${c.key}"]`).innerHTML='<p class="muted">This card couldn\'t be drawn.</p>'}});
}

// ---- Settings → Plugins
let plugins={plugins:[],profile_fields:[],settings:[]};
const allKeys=()=>KEYS;                 // plugin settings save themselves (see savePluginSetting)
async function loadPlugins(){plugins=await get("/api/plugins");drawPlugins();jobslop.sync(plugins.plugins);
  if(typeof drawProfileFields==="function")drawProfileFields()}
// one row per plugin, like Blender's add-ons: ▸ to fold open, a tick box to switch it on, its settings inside
let plugOpen=new Set((pref("plugopen")||"").split(",").filter(Boolean));
function settingControl(s){
  const id=`ps-${esc(s.key)}`,key=`data-key="${esc(s.key)}" data-type="${esc(s.type)}"`;
  if(s.type==="toggle")return `<label class="check"><input type="checkbox" class="pset" id="${id}" ${key} ${s.value==="1"?"checked":""}> ${esc(s.label)}</label>`;
  if(s.type==="choice")return `<label class="f">${esc(s.label)}<select class="pset" id="${id}" ${key}>${s.options.map(([v,l])=>`<option value="${esc(v)}" ${v===s.value?"selected":""}>${esc(l)}</option>`).join("")}</select></label>`;
  if(s.type==="secret")return `<label class="f">${esc(s.label)}<input type="password" class="pset" id="${id}" ${key} autocomplete="off" placeholder="${esc(s.value?t("saved ({0}) — paste to replace").replace("{0}",s.value):t("paste here"))}"></label>`;
  return `<label class="f">${esc(s.label)}<input type="${s.type==="number"?"number":"text"}" class="pset" id="${id}" ${key} value="${esc(s.value)}"></label>`;
}
function pluginRow(p){
  const sets=plugins.settings.filter(s=>s.plugin===p.id),open=plugOpen.has(p.id),upd=pluginUpdates[p.id];
  const kind=p.language?"🌐 "+t("Language"):p.builtin?t("Built in"):t("Installed");
  return `<div class="prow ${p.enabled?"on":"off"} ${open?"open":""}" data-id="${esc(p.id)}">
    <div class="phead">
      <button class="pfold" aria-expanded="${open}" aria-label="${esc(t("Show details"))}" data-tip="${esc(t("Show details and settings"))}">›</button>
      <input type="checkbox" class="plugsw" data-id="${esc(p.id)}" ${p.enabled?"checked":""} ${p.error&&!p.enabled&&!p.version?"disabled":""} aria-label="${esc(p.name)}" data-tip="${p.enabled?t("Switch off"):t("Switch on")} ${esc(p.name)}">
      <span class="pname">${esc(p.name)}${p.version?`<small>v${esc(p.version)}</small>`:""}</span>
      ${upd?`<span class="tag">${esc(t("Update to {0}").replace("{0}",upd.latest))}</span>`:""}${p.error?`<span class="perr">⚠</span>`:""}
      <span class="pkind">${esc(kind)}</span>
    </div>
    <div class="pbody" ${open?"":"hidden"}>
      ${p.description?`<div class="pd">${esc(p.description)}</div>`:""}
      ${p.adds.length?`<div class="pa">${p.adds.map(a=>`<span>${esc(a)}</span>`).join("")}</div>`:""}
      ${p.error?`<div class="perr">⚠ ${esc(p.error)}</div>`:""}
      <div class="pbtns">${p.author?`<span class="muted" style="font-size:12px">${esc(t("by {0}").replace("{0}",p.author))}</span>`:""}
        ${p.homepage?`<span class="linkish" style="font-size:12px" data-href="${esc(p.homepage)}">${esc(t("Website ↗"))}</span>`:""}
        ${upd?`<button class="pill dark sm plugupd" data-link="${esc(upd.link)}">${esc(t("Update to {0}").replace("{0}",upd.latest))}</button>`:""}
        ${!p.builtin?`<button class="pill line sm plugrm" data-id="${esc(p.id)}" data-tip="Remove this plugin from jobslop">Remove</button>`:""}</div>
      ${sets.length?`<div class="psets"><div class="psec" style="margin:0 0 8px">${esc(t("Settings"))}</div><div class="pgrid">${sets.map(settingControl).join("")}</div>
        ${sets.filter(s=>s.help||s.link).map(s=>`<div class="help">${esc(s.help)} ${s.link?`<span class="linkish" data-href="${esc(s.link)}">${esc(s.link.replace(/^https:\/\//,""))}</span>`:""}</div>`).join("")}</div>`
        :!p.enabled&&p.has_settings?`<div class="help muted" style="font-size:12px">${esc(t("Switch it on to change its settings."))}</div>`:""}
    </div></div>`;
}
function drawPlugins(){
  const q=($("#plugfind")||{value:""}).value.trim().toLowerCase(),only=($("#plugonly")||{}).checked;
  const list=plugins.plugins.filter(p=>(!only||p.enabled)&&(!q||`${p.name} ${p.description} ${t(p.name)} ${t(p.description)}`.toLowerCase().includes(q)));
  $("#plugs").innerHTML=list.map(pluginRow).join("")||`<p class="muted" style="font-size:13px">${esc(plugins.plugins.length?t("No plugins match."):t("No plugins yet."))}</p>`;
  $$(".plugsw").forEach(c=>c.onchange=()=>togglePlugin(c.dataset.id,c.checked));
  $$(".prow .pfold,.prow .pname").forEach(b=>b.onclick=()=>{
    const row=b.closest(".prow"),id=row.dataset.id,open=!plugOpen.has(id);
    open?plugOpen.add(id):plugOpen.delete(id);pref("plugopen",[...plugOpen].join(","));
    row.classList.toggle("open",open);row.querySelector(".pbody").hidden=!open;row.querySelector(".pfold").setAttribute("aria-expanded",open)});
  $$(".plugrm").forEach(b=>b.onclick=()=>removePlugin(b.dataset.id));
  $$(".plugupd").forEach(b=>b.onclick=()=>previewPlugin(b.dataset.link,b));
  $$(".pset").forEach(el=>el.onchange=()=>savePluginSetting(el));
}
// a plugin's setting is saved as soon as it changes (an empty key box leaves the saved key alone)
async function savePluginSetting(el){
  const v=el.type==="checkbox"?(el.checked?"1":""):el.value.trim();
  if(el.dataset.type==="secret"&&!v)return;
  await post("/api/settings",{[el.dataset.key]:v});
  if(el.dataset.type==="secret")el.value="";
  plugins=await get("/api/plugins");keys=await get("/api/settings");drawPlugins();await loadBoards();
  toast(t("Saved ✓"));
}
async function togglePlugin(id,on){
  const p=plugins.plugins.find(x=>x.id===id)||{name:id};
  plugins=await post("/api/plugins",{id,enabled:on});drawPlugins();jobslop.sync(plugins.plugins);drawProfileFields();
  const now=plugins.plugins.find(x=>x.id===id)||{};
  if(on&&now.error)return toast(`${p.name} couldn't start — see the message on its card`);
  keys=await get("/api/settings");await loadBoards();render();
  // a plugin can bring words in other languages; switching off the chosen language's pack goes back to English
  if(!on&&LANGS.some(l=>l.code===LANG&&l.plugin===id)){savePref("lang","en");await loadLanguage("en")}else await loadLanguage(LANG);
  toast(t(on?"{0} switched on":"{0} switched off").replace("{0}",p.name));
}
$("#plugfind").addEventListener("input",()=>drawPlugins());
$("#plugonly").onchange=()=>{pref("plugonly",$("#plugonly").checked?"1":"");drawPlugins()};
$("#plugonly").checked=pref("plugonly")==="1";

// ---- install from a GitHub link: download and show what it is first, install only when the user says yes
let pluginUpdates={},pendingPlugin=null;
async function previewPlugin(link,btn){
  link=(link||"").trim();if(!link){$("#plugmsg").textContent=t("Paste the GitHub link of a plugin first");return}
  await withSpinner(btn||$("#plugget"),t("Checking…"),async()=>{
    const r=await post("/api/plugins/install",{link});
    if(r.error){$("#plugmsg").textContent=r.error;return}
    const p=pendingPlugin=r.preview;$("#plugmsg").textContent="";
    $("#pititle").textContent=p.replaces?t("Update {0}?").replace("{0}",p.name):t("Install {0}?").replace("{0}",p.name);
    $("#pibody").innerHTML=`<div class="pimeta">v${esc(p.version)}${p.author?" · "+esc(p.author):""}${p.replaces?" · "+esc(t("you have {0}").replace("{0}",p.replaces)):""} · <span class="linkish" data-href="${esc(p.source)}">${esc(p.source.replace("https://",""))}</span></div>
      ${p.description?`<p style="margin:0 0 10px">${esc(p.description)}</p>`:""}
      ${p.adds.length?`<div class="plug" style="border:0;padding:0;background:none"><div class="pa">${p.adds.map(a=>`<span>${esc(a)}</span>`).join("")}</div></div>`:""}`;
    $("#piwarn").hidden=!p.runs_code;$("#pigo").textContent=p.replaces?t("Update"):t("Install");
    openModal("m-plugin")});
}
$("#plugget").onclick=()=>previewPlugin($("#pluglink").value);
$("#pluglink").addEventListener("keydown",e=>{if(e.key==="Enter"){e.preventDefault();$("#plugget").click()}});
$("#pigo").onclick=()=>withSpinner($("#pigo"),t("Installing…"),async()=>{
  if(!pendingPlugin)return;
  const r=await post("/api/plugins/install",{token:pendingPlugin.token});pendingPlugin=null;closeModals();
  if(r.error)return toast(r.error);
  plugins=r;delete pluginUpdates[r.installed];drawPlugins();jobslop.sync(plugins.plugins);drawProfileFields();$("#pluglink").value="";
  keys=await get("/api/settings");await loadBoards();await loadLanguage(LANG);render();
  const p=plugins.plugins.find(x=>x.id===r.installed)||{name:r.installed};
  toast(p.error?t("{0} couldn't start — see the message on its card").replace("{0}",p.name):t("{0} installed").replace("{0}",p.name));
});
async function removePlugin(id){
  const p=plugins.plugins.find(x=>x.id===id)||{name:id};
  if(!confirm(t("Remove {0}? You can install it again from its link.").replace("{0}",p.name)))return;
  const r=await post("/api/plugins/remove",{id});if(r.error)return toast(r.error);
  plugins=r;jobslop.sync(plugins.plugins);drawPlugins();drawProfileFields();keys=await get("/api/settings");await loadBoards();await loadLanguage(LANG);render();
  toast(t("{0} removed").replace("{0}",p.name));
}
$("#plugcheck").onclick=()=>withSpinner($("#plugcheck"),t("Checking…"),async()=>{
  const r=await post("/api/plugins/check",{});
  pluginUpdates={};(r.updates||[]).forEach(u=>pluginUpdates[u.id]=u);drawPlugins();
  $("#plugmsg").textContent=r.updates&&r.updates.length?t("{0} plugin update(s) available").replace("{0}",r.updates.length):t("Your plugins are up to date");
});

// "Save settings" saves everything in the Settings window: keys and job match terms
$("#savekeys").onclick=()=>withSpinner($("#savekeys"),"Saving…",async()=>{const b={};allKeys().forEach(k=>{const el=$("#"+k);if(!el)return;const v=el.value.trim();if(v)b[k]=v;el.value=""});
  await post("/api/settings",b);
  matchTerms=await post("/api/match_terms",{terms:matchTerms.filter(t=>(t.name||"").trim())});drawTerms();
  await loadKeys();closeModals();render();toast("Settings saved")});
