// ---- map picker (Leaflet + OpenStreetMap, loaded the first time it's opened)
let map=null,mapPin=null,mapCircle=null,mapPlace=null;
function loadLeaflet(){return new Promise((ok,fail)=>{if(window.L)return ok();
  const css=document.createElement("link");css.rel="stylesheet";css.href="/static/leaflet.css";document.head.appendChild(css);
  const js=document.createElement("script");js.src="/static/leaflet.js";js.onload=ok;js.onerror=()=>fail(new Error("Couldn't load the map"));document.head.appendChild(js)})}
const isDark=()=>document.documentElement.dataset.theme==="dark"||(document.documentElement.dataset.theme==="auto"&&matchMedia("(prefers-color-scheme: dark)").matches);
function drawMapRadius(){const u=unit(),v=+$("#maprad").value;$("#mapradlabel").textContent=`${v} ${u}`;
  if(mapCircle)mapCircle.setRadius(toMiles(v,u)*1609.34)}
function setMapPlace(p,fly){mapPlace=p;$("#maplabel").textContent=p.label||`${p.lat.toFixed(3)}, ${p.lon.toFixed(3)}`;
  const ll=[p.lat,p.lon];mapPin.setLatLng(ll);mapCircle.setLatLng(ll);if(fly)map.fitBounds(mapCircle.getBounds(),{padding:[30,30]})}
async function pickAt(lat,lon){$("#maplabel").innerHTML='<span class="spin"></span>';
  const r=await get(`/api/reverse?lat=${lat}&lon=${lon}`);setMapPlace(r.error?{lat,lon,label:"",town:"",country_code:""}:{...r,lat,lon},false);
  if(r.error)toast(r.error);drawMapLayers()}
// Two map styles: the free OpenStreetMap street map (online), and a built-in offline map
// (country outlines + 70,000 towns that ship with the app). The offline map is always underneath,
// so the map still works with no internet; it switches over by itself if street tiles can't load.
let mapStyle=pref("mapstyle")||"street",worldLayer=null,townLayer=null,tileErrors=0,tileLoads=0;
const accentColor=()=>getComputedStyle(document.documentElement).getPropertyValue("--accent").trim();
async function addOfflineBase(){
  if(worldLayer)return;
  const world=await get("/static/world.json");
  // the offline outlines sit in their own layer BELOW the street map, so street tiles are never covered
  if(!map.getPane("offlineBase")){map.createPane("offlineBase");map.getPane("offlineBase").style.zIndex=150}
  worldLayer=L.geoJSON(world,{pane:"offlineBase",interactive:false,style:()=>({color:isDark()?"#8a8170":"#a69c8a",weight:1,fillColor:isDark()?"#3d3a33":"#f6f2ea",fillOpacity:1})}).addTo(map);
  townLayer=L.layerGroup().addTo(map);
  map.on("moveend",drawTowns);
}
async function drawTowns(){
  if(!townLayer)return;
  if(mapStyle!=="offline"){townLayer.clearLayers();return}
  const b=map.getBounds(),z=map.getZoom(),limit=z<5?12:z<7?30:z<9?60:120;
  const towns=await get(`/api/towns?s=${b.getSouth()}&w=${b.getWest()}&n=${b.getNorth()}&e=${b.getEast()}&limit=${limit}`);
  townLayer.clearLayers();
  towns.forEach((t,i)=>{const m=L.circleMarker([t.lat,t.lon],{radius:i<8?3.5:2.5,color:isDark()?"#ece7dc":"#3a342b",weight:0,fillOpacity:.8,interactive:false}).addTo(townLayer);
    if(i<(z<6?10:z<8?25:45))m.bindTooltip(t.n,{permanent:true,direction:"right",className:"townlabel",offset:[4,0]})});
}
function setMapStyle(style,quiet){
  mapStyle=style;pref("mapstyle",style);$$("#mapseg button").forEach(b=>b.classList.toggle("on",b.dataset.style===style));
  document.getElementById("map").classList.toggle("darktiles",isDark());
  if(map._tiles){map.removeLayer(map._tiles);map._tiles=null}
  if(style==="street"){
    tileErrors=0;tileLoads=0;
    map._tiles=L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png",{maxZoom:19,attribution:'&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'}).addTo(map);
    map._tiles.on("tileload",()=>tileLoads++);
    map._tiles.on("tileerror",()=>{tileErrors++;if(tileErrors>=4&&tileLoads===0&&mapStyle==="street"){setMapStyle("offline",true);toast("No internet for street maps — showing the built-in offline map")}});
  }
  drawTowns();
  if(!quiet&&style==="offline")toast("Offline map: country outlines and 70,000 towns built into the app");
}
// ---- extra layers plugins add (api.addMapLayer): a tick (and optional choice) each, markers + a list
function drawMapLayerControls(){
  const box=$("#maplayers");if(!box)return;
  box.innerHTML=jobslop.parts.layers.map(l=>`<label class="check" ${l.tip?`data-tip="${esc(l.tip)}"`:""}><input type="checkbox" class="mapl" data-k="${esc(l.key)}" ${pref("ml_"+l.key)==="1"?"checked":""}> ${esc(l.label)}</label>`+
    (l.options?`<select class="maplopt" data-k="${esc(l.key)}" style="padding:5px 8px;border-radius:999px;font-size:12.5px;width:auto!important;flex:0 0 auto">${l.options.map(([v,n])=>`<option value="${esc(v)}">${esc(n)}</option>`).join("")}</select>`:"")).join("");
  $$(".maplopt").forEach(s=>{s.value=pref("mlo_"+s.dataset.k)||s.options[0].value;
    s.onchange=()=>{pref("mlo_"+s.dataset.k,s.value);const c=$(`.mapl[data-k="${s.dataset.k}"]`);if(!c.checked){c.checked=true;pref("ml_"+s.dataset.k,"1")}drawMapLayers()}});
  $$(".mapl").forEach(c=>c.onchange=()=>{pref("ml_"+c.dataset.k,c.checked?"1":"");drawMapLayers()});
  if(map)drawMapLayers();
}
async function drawMapLayers(){
  if(!map)return;
  const km=toMiles(+$("#maprad").value,unit())*1.609;
  for(const l of jobslop.parts.layers){
    if(!l.group)l.group=L.layerGroup().addTo(map);
    l.group.clearLayers();
    let list=$("#ml-"+l.key);
    if(!list){list=document.createElement("div");list.id="ml-"+l.key;list.className="maplist";$("#maplists").appendChild(list)}
    const on=($(`.mapl[data-k="${l.key}"]`)||{}).checked;
    if(!on||!mapPlace){list.innerHTML="";list.hidden=true;continue}
    list.hidden=false;
    try{await l.draw({L,map,group:l.group,list,place:mapPlace,km,radiusLabel:`${$("#maprad").value} ${unit()}`,
                      option:($(`.maplopt[data-k="${l.key}"]`)||{}).value})}
    catch(e){console.error(e);list.innerHTML='<div class="muted" style="padding:8px">This layer couldn’t be drawn.</div>'}
  }
}
$("#mapbtn").onclick=async()=>{
  openModal("m-map");const u=unit();$("#maprad").max=u==="km"?160:100;$("#maprad").value=Math.round(fromMiles(+$("#miles").value||15,u));drawMapRadius();
  try{await loadLeaflet()}catch(e){$("#map").innerHTML=`<span class="muted">${esc(e.message)}</span>`;return}
  const cname=(countries.find(c=>c.code===$("#country").value)||{}).name||"";
  const q=[$("#where").value.trim(),cname].filter(Boolean).join(", ")||cname;
  const start=await get("/api/geocode?q="+encodeURIComponent(q));
  const p=start.error?{lat:52.5,lon:-1.9,label:"",town:"",country_code:""}:start;
  if(!map){$("#map").innerHTML="";$("#map").style.display="block";
    map=L.map("map",{zoomControl:true,worldCopyJump:true}).setView([p.lat,p.lon],9);
    const pinIcon=L.divIcon({className:"",html:'<div class="mappin"></div>',iconSize:[22,22],iconAnchor:[11,22]});
    mapPin=L.marker([p.lat,p.lon],{draggable:true,icon:pinIcon}).addTo(map);
    mapCircle=L.circle([p.lat,p.lon],{radius:1000,color:accentColor(),weight:2,fillOpacity:.12}).addTo(map);
    map.on("click",e=>pickAt(e.latlng.lat,e.latlng.lng));
    mapPin.on("dragend",()=>{const ll=mapPin.getLatLng();pickAt(ll.lat,ll.lng)});
    await addOfflineBase();}
  mapCircle.setStyle({color:accentColor()});
  setMapStyle(mapStyle,true);
  setTimeout(()=>{map.invalidateSize();drawMapRadius();setMapPlace(p,true);drawMapLayers()},120);
};
$$("#mapseg button").forEach(b=>b.onclick=()=>setMapStyle(b.dataset.style));
$("#maprad").addEventListener("input",()=>{drawMapRadius()});
$("#maprad").addEventListener("change",()=>{if(mapCircle)map.fitBounds(mapCircle.getBounds(),{padding:[30,30]});drawMapLayers()});
$("#mapfind").onclick=()=>withSpinner($("#mapfind"),"",async()=>{const q=$("#mapq").value.trim();if(!q)return;
  const r=await get("/api/geocode?q="+encodeURIComponent(q));if(r.error)return toast(r.error);setMapPlace(r,true);drawMapLayers()});
$("#mapq").addEventListener("keydown",e=>{if(e.key==="Enter"){e.preventDefault();$("#mapfind").click()}});
$("#mapuse").onclick=()=>{
  if(!mapPlace)return closeModals();
  $("#where").value=mapPlace.town||$("#where").value;
  if(mapPlace.country_code&&!setCountry(mapPlace.country_code))toast(`${mapPlace.country} isn't in the country list — keeping ${$("#country").selectedOptions[0].text}`);
  const u=unit(),miles=Math.max(1,Math.round(toMiles(+$("#maprad").value,u)));
  if(![...$("#miles").options].some(o=>+o.value===miles))$("#miles").insertAdjacentHTML("beforeend",`<option value="${miles}">+${$("#maprad").value} ${u}</option>`);
  $("#miles").value=String(miles);closeModals();
  toast(`Searching around ${mapPlace.label||"the chosen spot"} (+${$("#maprad").value} ${u})`)};
["q","where","miles","exclude"].forEach(id=>{const v=pref("f_"+id);if(v!==null&&v!==undefined)$("#"+id).value=v});
["posted","jtype","remote","salmin","sort"].forEach(id=>{const v=pref("f_"+id);if(v)$("#"+id).value=v});
setTimeout(()=>{if($("#where").value.trim())readWhere()},400);

let internMode=false;                                   // set by the 🎓 Internships button for one search
$("#f").onsubmit=e=>{e.preventDefault();cvMode=false;internMode=false;runSearch()};
$("#matchbtn").onclick=async()=>{
  profile=(await get("/api/profile")).profile||{};
  const titles=cvTitles();
  if(!titles.length&&!(profile.skills||"").trim()){toast("Add your work history or CV in Profile first");setTab("profile");return}
  if(anyMode)$("#anybtn").click();
  $("#q").value=titles.length?titles.join(", "):(profile.skills||"").split(",").slice(0,2).join(",");
  if(!$("#where").value&&profile.city)$("#locbtn").click();
  cvMode=true;$("#sort").value="cv";runSearch();
};

// Like other search tools: searching again while a search runs cancels it and starts over with what's in
// the boxes now; Stop (or Esc) ends it and keeps the jobs found so far.
let searchRun=0,searchAbort=null,searchStopped=false;
function stopSearch(){if(!searching||!searchAbort)return;searchStopped=true;searchAbort.abort()}
$("#stopbtn").onclick=stopSearch;
document.addEventListener("keydown",e=>{if(e.key==="Escape"&&searching&&!document.querySelector(".modal.open"))stopSearch()});
async function runSearch(){
  const q=$("#q").value.trim();if(!q&&!anyMode){toast("Type a job, or switch on “Any job”");return}
  ["q","where","miles","exclude"].forEach(id=>pref("f_"+id,$("#"+id).value));
  ["posted","jtype","remote","salmin","sort"].forEach(id=>pref("f_"+id,$("#"+id).value));
  const srcs=$$(".sc:checked").map(c=>c.value);if(!srcs.length){toast("Pick at least one source");return}
  if(!profile.first_name&&!profile.skills){try{profile=(await get("/api/profile")).profile||{}}catch(e){}}
  followWhereCountry(await readWhere());
  setTab("search");$("#v-search").scrollIntoView({behavior:"smooth"});
  if(searchAbort)searchAbort.abort();                  // a search still running is replaced by this one
  const run=++searchRun,abort=searchAbort=new AbortController();searchStopped=false;
  searching=true;$("#go").innerHTML='<span class="spin"></span> Searching…';$("#go").dataset.tip="Start over with what's in the boxes now";
  $("#stopbtn").hidden=false;results=[];page=1;render();
  $("#restitle").textContent=cvMode?"Matched to Your CV":anyMode?"Every Job Nearby":"Search Results";
  const st={};srcs.forEach(s=>st[s]=null);
  const drawStatus=()=>{const left=srcs.filter(s=>st[s]===null).length;
    $("#status").innerHTML=srcs.map(s=>st[s]===null?(abort.signal.aborted?`<span class="srcstat muted">${s}: stopped</span>`:`<span class="srcstat"><span class="spin"></span>${s}</span>`):`<span class="srcstat done">${s}: ${st[s]}</span>`).join("")+
      (left&&!abort.signal.aborted?`<span class="muted"> — waiting for ${left} site${left>1?"s":""}…</span>`:left?`<span class="muted"> — stopped, ${results.length} jobs</span>`:`<span class="muted"> — done, ${results.length} jobs</span>`)};drawStatus();
  // only "what" and "where" go to the job boards; the filters below the results just hide jobs (see visible())
  const base={q,where:$("#where").value.trim(),miles:$("#miles").value,country:$("#country").value,
    fresh:$("#fresh").checked?1:0,any:anyMode?1:0,intern:internMode?1:0};
  const keyOf=j=>(j.title+"|"+j.company).toLowerCase().replace(/[^a-z0-9|]/g,"");
  await Promise.all(srcs.map(async s=>{
    busy(1);
    try{const r=await fetch("/api/search?"+new URLSearchParams({...base,sources:s}),{signal:abort.signal}).then(x=>x.json());
      if(run!==searchRun||abort.signal.aborted)return;
      const v=r.status[s]||{found:0};
      const have=new Map(results.map(j=>[keyOf(j),j]));r.results.forEach(j=>{const k=keyOf(j),o=have.get(k);if(!o||o.score<j.score)have.set(k,j)});
      results=[...have.values()];
      st[s]=v.error&&!v.found?`<span class="warn">${esc(v.error)}</span>`:`${v.found}${v.cached?" (saved)":""}`;
    }catch(err){if(abort.signal.aborted)return;st[s]=`<span class="warn">failed</span>`}
    finally{busy(-1)}
    if(run===searchRun){drawStatus();render()}}));
  if(run!==searchRun)return;                            // a newer search took over
  searching=false;searchAbort=null;$("#fresh").checked=false;$("#go").textContent="Search jobs";delete $("#go").dataset.tip;
  $("#stopbtn").hidden=true;
  drawStatus();render();
  if(searchStopped){toast(`Search stopped — ${results.length} job${results.length===1?"":"s"} found so far`);return}
  toast(results.length?`Found ${results.length} jobs`:"No jobs found — try a wider area or fewer filters");
  pref("searches_"+todayStr(),String(+(pref("searches_"+todayStr())||0)+1));savePref("searched","1");drawStarted();
}
