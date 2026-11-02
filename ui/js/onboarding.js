// ============================================================= start
// ============================================================= onboarding tour (first run)
const OB_KICK=["Welcome","Step 1 · Your CV","Step 2 · Location","Step 3 · Searching","Step 4 · Apply & track"];
let obStep=0;
const obSteps=()=>$$("#m-onboard .obstep");
function showObStep(i){
  const steps=obSteps();obStep=Math.max(0,Math.min(steps.length-1,i));
  steps.forEach((s,k)=>s.hidden=k!==obStep);
  $("#obkick").textContent=OB_KICK[obStep];
  $("#obdots").innerHTML=steps.map((_,k)=>`<i class="${k===obStep?"on":""}" data-ob="${k}" title="Step ${k+1}"></i>`).join("");
  $$("#obdots i").forEach(d=>d.onclick=()=>{applyObStep();showObStep(+d.dataset.ob)});
  $("#obback").style.visibility=obStep?"visible":"hidden";
  const ready=(profile.jobs||[]).length>0;
  $("#obnext").textContent=obStep===steps.length-1?(ready?"Find jobs for me →":"Start searching →"):obStep===1?"Next (or skip)":"Next";
  if(obStep===steps.length-1)$("#obextnote").innerHTML=$("#extdot").classList.contains("on")?'<span style="color:var(--good)">● Already connected</span>':"or later from <b>Profile</b>";
}
function startOnboarding(){
  $("#obcountry").innerHTML=countries.map(c=>`<option value="${c.code}">${esc(c.name)}</option>`).join("");
  $("#obcountry").value=$("#country").value;
  $("#obtown").value=$("#where").value||profile.city||"";
  $("#obcurrency").value=currency;$("#obunit").value=unit();
  $("#obcvmsg").textContent="";
  showObStep(0);openModal("m-onboard");
}
function applyObStep(){
  if(obStep!==2)return;                               // save the location choices when leaving that step
  setCountry($("#obcountry").value);
  $("#where").value=$("#obtown").value.trim();pref("f_where",$("#where").value);
  if($("#obcurrency").value!==currency)setCurrency($("#obcurrency").value,true);
  if($("#obunit").value!==unit()){savePref("unit",$("#obunit").value);drawMiles()}
}
function finishOnboarding(go){applyObStep();savePref("onboarded","1");$("#m-onboard").classList.remove("open");drawStarted();
  // straight to something useful: jobs that fit your CV when there is one
  if(go&&(profile.jobs||[]).length){toast("Finding jobs that fit your CV…");setTimeout(()=>$("#matchbtn").click(),250);return}
  toast("You're all set — happy job hunting!");setTimeout(()=>$("#q").focus(),200)}
$("#obnext").onclick=()=>{applyObStep();if(obStep===obSteps().length-1)finishOnboarding(true);else showObStep(obStep+1)};
$("#obback").onclick=()=>{applyObStep();showObStep(obStep-1)};
$("#obskip").onclick=()=>finishOnboarding(false);
$("#obext").onclick=()=>$("#extsetup").click();
$("#retour").onclick=()=>{closeModals();startOnboarding()};
async function obUpload(f){
  $("#obcvmsg").innerHTML='<span class="spin"></span> Reading your CV…';
  await loadProfile();                                // only fill empty fields, never wipe what's there
  await uploadCv(f,false);await fillFromCv();
  $("#obcvmsg").textContent=$("#fromcvmsg").textContent||"CV saved.";
  $("#obtown").value=$("#obtown").value||profile.city||"";
  const hit=countryFromText(profile.country);if(hit&&!$("#where").value)$("#obcountry").value=hit.code;
}
$("#obligo").onclick=()=>importLinkedInLink($("#obliurl").value,(t,h)=>{$("#obcvmsg")[h?"innerHTML":"textContent"]=t.replace(/<(?!\/?span)[^>]*>/g,"")});
$("#obliurl").addEventListener("keydown",e=>{if(e.key==="Enter")$("#obligo").click()});
$("#obcv").onchange=e=>{const f=e.target.files[0];e.target.value="";if(f)obUpload(f)};
const obdrop=$("#obdrop");
["dragenter","dragover"].forEach(ev=>obdrop.addEventListener(ev,e=>{e.preventDefault();obdrop.classList.add("over")}));
["dragleave","drop"].forEach(ev=>obdrop.addEventListener(ev,()=>obdrop.classList.remove("over")));
obdrop.addEventListener("drop",e=>{e.preventDefault();e.stopPropagation();const f=e.dataTransfer.files[0];if(f)obUpload(f)});
