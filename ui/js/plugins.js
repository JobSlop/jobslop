// ============================================================= plugins
// What switched-on plugins add to the screen. A plugin's ui.js calls
//   jobslop.plugin("its-id", api => { api.addTab({...}); api.addMapLayer({...}); api.addStatCard({...}) })
// Everything it adds is remembered under its id and taken away again when it is switched off.
const jobslop=(()=>{
  const parts={tabs:[],layers:[],cards:[]};
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
  return {plugin,remove,sync,parts,tabFor};
})();

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
const allKeys=()=>KEYS.concat(plugins.settings.map(s=>s.key));
async function loadPlugins(){plugins=await get("/api/plugins");drawPlugins();jobslop.sync(plugins.plugins);
  if(typeof drawProfileFields==="function")drawProfileFields()}
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
  // boxes plugins add to Settings (API keys and the like), saved with "Save settings"
  const bySec={};plugins.settings.forEach(s=>{const n=(plugins.plugins.find(p=>p.id===s.plugin)||{}).name||s.plugin;(bySec[n]=bySec[n]||[]).push(s)});
  $("#plugsettings").innerHTML=Object.entries(bySec).map(([n,ss])=>`<div class="psec" style="margin-top:12px">${esc(n)}</div><div class="pgrid">${ss.map(s=>
    `<label class="f">${esc(s.label)}<input type="${s.type==="secret"?"password":"text"}" id="${esc(s.key)}" autocomplete="off"></label>`).join("")}</div>
    ${ss.filter(s=>s.help||s.link).map(s=>`<p class="muted" style="font-size:12.5px;margin:4px 0 10px">${esc(s.help)} ${s.link?`<span class="linkish" data-href="${esc(s.link)}">${esc(s.link.replace(/^https:\/\//,""))}</span>`:""}</p>`).join("")}`).join("");
  plugins.settings.forEach(s=>{const el=$("#"+s.key);if(el)el.placeholder=keys[s.key]?"saved ("+keys[s.key]+") — paste to replace":"paste here"});
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
// "Save settings" saves everything in the Settings window: keys and job match terms
$("#savekeys").onclick=()=>withSpinner($("#savekeys"),"Saving…",async()=>{const b={};allKeys().forEach(k=>{const el=$("#"+k);if(!el)return;const v=el.value.trim();if(v)b[k]=v;el.value=""});
  await post("/api/settings",b);
  matchTerms=await post("/api/match_terms",{terms:matchTerms.filter(t=>(t.name||"").trim())});drawTerms();
  await loadKeys();closeModals();render();toast("Settings saved")});
