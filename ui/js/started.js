// ============================================================= getting started checklist (Search page, until it's all done)
function startedItems(){
  const extOn=$("#extdot").classList.contains("on");
  return [
    {done:!!(profile.first_name||profile.email||(profile.jobs||[]).length),label:"Add your CV or LinkedIn",go:()=>setTab("profile")},
    {done:!!($("#where").value.trim()||profile.city),label:"Choose where you're looking",go:()=>{setTab("search");$("#where").focus()}},
    {done:pref("searched")==="1"||results.length>0,label:"Run your first search",go:()=>{setTab("search");($("#q").disabled?$("#go"):$("#q")).focus()}},
    {done:saved.length>0,label:"Save or apply to a job",go:()=>{setTab("search");toast("Press ☆ Save or ✓ Mark applied on any result")}},
  ].concat(PHONE?[]:[{done:extOn,label:"Set up Easy apply (Chrome)",go:()=>{setTab("profile");setTimeout(()=>$("#extsetup").scrollIntoView({behavior:"smooth",block:"center"}),150)}}]);
}
function drawStarted(){
  const box=$("#getstarted");if(!box)return;const items=startedItems(),done=items.filter(i=>i.done).length;
  box.hidden=pref("gs_hide")==="1"||done===items.length||pref("onboarded")!=="1";if(box.hidden)return;
  $("#gscount").textContent=`${done} of ${items.length} done`;$("#gsbar").style.width=(100*done/items.length)+"%";
  $("#gslist").innerHTML=items.map((it,i)=>`<li class="${it.done?"done":""}" data-gs="${i}" ${it.done?'data-tip="Done ✓"':'tabindex="0" role="button" data-tip="Click to do this now"'}><span class="ck">${it.done?"✓":i+1}</span><span>${esc(it.label)}</span></li>`).join("");
  $$("#gslist li").forEach(li=>{const it=items[+li.dataset.gs];if(it.done)return;li.onclick=it.go;li.onkeydown=e=>{if(e.key==="Enter"||e.key===" "){e.preventDefault();it.go()}}});
}
$("#gsclose").onclick=()=>{savePref("gs_hide","1");drawStarted();toast("Hidden — bring it back from ⚙ Settings")};
$("#gsshow").onclick=()=>{savePref("gs_hide","0");closeModals();setTab("search");drawStarted();if($("#getstarted").hidden)toast("You've done everything on the list already 🎉")};
$("#where").addEventListener("change",drawStarted);
