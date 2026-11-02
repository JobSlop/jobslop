// ============================================================= keys & sources
async function loadKeys(){keys=await get("/api/settings");KEYS.forEach(k=>$("#"+k)&&($("#"+k).placeholder=keys[k]?"saved ("+keys[k]+") — paste to replace":"paste here"));await loadBoards()}
async function loadBoards(){BOARDS=await get("/api/boards");drawSources();
  const f=$("#srcfilter"),was=f.value;
  f.innerHTML='<option value="">All sources</option>'+BOARDS.map(b=>`<option>${esc(b.name)}</option>`).join("");f.value=was}
function drawSources(){
  const off=new Set((pref("off")||"").split(",").filter(Boolean)),cc=$("#country").value||"GB";
  $("#srcs").innerHTML=BOARDS.map(b=>{
    if(b.countries&&!b.countries.includes(cc))return"";     // not for this country: hide it
    const need=b.needs_key,on=!off.has(b.name)&&!need,note=need?" · needs key":(b.slow?" · slow":"");
    return `<label class="chip ${on?"on":"off"} ${need?"need":""}" title="${need?"Add a free key in ⚙ Settings":esc(b.description)}"><input type="checkbox" class="sc" value="${esc(b.name)}" ${on?"checked":""} ${need?"disabled":""}><span class="dot"></span>${esc(b.name)}${note}</label>`}).join("");
  $$(".sc").forEach(c=>c.onchange=()=>{c.closest(".chip").classList.toggle("on",c.checked);c.closest(".chip").classList.toggle("off",!c.checked);
    pref("off",$$(".sc").filter(x=>!x.checked&&!x.disabled).map(x=>x.value).join(","))});
}
$("#gear").onclick=()=>{openModal("m-keys");loadPlugins()};
