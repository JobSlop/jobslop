// ============================================================= keys & sources
async function loadKeys(){keys=await get("/api/settings");KEYS.forEach(k=>$("#"+k)&&($("#"+k).placeholder=keys[k]?"saved ("+keys[k]+") — paste to replace":"paste here"));await loadBoards()}
async function loadBoards(){BOARDS=await get("/api/boards");drawSources();
  const f=$("#srcfilter"),was=f.value;
  f.innerHTML='<option value="">All sources</option>'+BOARDS.map(b=>`<option value="${esc(b.name)}" translate="no">${esc(b.name)}</option>`).join("");f.value=was}
function drawSources(){
  const off=new Set((pref("off")||"").split(",").filter(Boolean)),cc=$("#country").value||"GB";
  $("#srcs").innerHTML=BOARDS.map(b=>{
    if(b.countries&&!b.countries.includes(cc))return"";     // not for this country: hide it
    const need=b.needs_key,on=!off.has(b.name)&&!need,note=need?" · needs key":(b.slow?" · slow":"");
    return `<label class="chip ${on?"on":"off"} ${need?"need":""}" data-plugin="${esc(b.plugin)}" title="${need?"Click to add its free key":esc(b.description)}"><input type="checkbox" class="sc" value="${esc(b.name)}" ${on?"checked":""} ${need?"disabled":""}><span class="dot"></span><span translate="no">${esc(b.name)}</span>${note?`<span>${note}</span>`:""}</label>`}).join("");
  $$(".chip.need").forEach(c=>c.onclick=e=>{e.preventDefault();plugOpen.add(c.dataset.plugin);openSettings("plugins")});
  $$(".sc").forEach(c=>c.onchange=()=>{c.closest(".chip").classList.toggle("on",c.checked);c.closest(".chip").classList.toggle("off",!c.checked);
    pref("off",$$(".sc").filter(x=>!x.checked&&!x.disabled).map(x=>x.value).join(","))});
}
// Settings: a side menu of sections; the last one used opens again
function showSettings(sec){
  let s=sec||pref("settab")||"general";
  const btn=$(`#setnav button[data-set="${s}"]`);
  if(!btn||getComputedStyle(btn).display==="none")s="general";       // e.g. a computer-only section on a phone
  $$("#setnav button").forEach(b=>b.classList.toggle("on",b.dataset.set===s));
  $$(".setpane > section").forEach(x=>x.hidden=x.dataset.set!==s);
  pref("settab",s);$(".setpane").scrollTop=0;
}
$$("#setnav button").forEach(b=>b.onclick=()=>showSettings(b.dataset.set));
function openSettings(sec){openModal("m-keys");showSettings(sec);loadPlugins()}
$("#gear").onclick=()=>openSettings();
