// ============================================================= profile
const PF=[["Personal",[["first_name","First name"],["middle_name","Middle name(s)"],["last_name","Last name"],["email","Email","email"],["phone","Phone","tel"],["linkedin","LinkedIn URL"],["website","Website / portfolio"],["github","GitHub"]]],
 ["Address",[["address1","Address line 1"],["address2","Address line 2"],["city","Town / city"],["county","County / state"],["postcode","Postcode / ZIP"],["country","Country"]]],
 ["Work",[["years_experience","Years of experience"],["salary","Expected salary"],["notice_period","Notice period"],["skills","Key skills (comma separated)","area"]]],
 ["Education",[["highest_qualification","Highest qualification"],["degree_subject","Subject"],["university","University / college"]]],
 ["Eligibility",[["right_to_work","Right to work in your country?","yn"],["needs_sponsorship","Need visa sponsorship?","yn"],["driving_licence","Full driving licence?","yn"],["over_18","18 or over?","yn"],["willing_to_relocate","Willing to relocate?","yn"],["auto_consent","Let the extension tick privacy / terms boxes?","yn"]]]];
// the app's own sections, then the fields switched-on plugins add (grouped by their section)
function profileSections(){
  const extra={};(plugins.profile_fields||[]).forEach(f=>{if(!PF.some(([,fs])=>fs.some(([k])=>k===f.key)))(extra[f.section]=extra[f.section]||[]).push([f.key,f.label,f.type==="text"?"":f.type])});
  return PF.concat(Object.entries(extra))}
function drawProfileFields(){
  $("#pfields").innerHTML=profileSections().map(([sec,fs])=>`<div class="psec">${esc(sec)}</div><div class="pgrid">${fs.map(([k,l,t])=>
    t==="yn"?`<label class="f">${esc(l)}<select class="pf" id="${esc(k)}"><option value="">—</option><option>Yes</option><option>No</option></select></label>`:
    t==="area"?`<label class="f wide">${esc(l)}<textarea class="pf" id="${esc(k)}" rows="2"></textarea></label>`:
    `<label class="f">${esc(l)}<input type="${t||"text"}" class="pf" id="${esc(k)}"></label>`).join("")}</div>`).join("");
  $$(".pf").forEach(el=>el.value=profile[el.id]||"")}
drawProfileFields();
let saveTimer=null;
function saveSoon(){clearTimeout(saveTimer);$("#psaved").textContent="Saving…";saveTimer=setTimeout(async()=>{await post("/api/profile",{profile});$("#psaved").textContent="Saved ✓";drawWelcome()},500)}
async function loadProfile(){
  const r=await get("/api/profile");profile=r.profile||{};
  $$(".pf").forEach(el=>el.value=profile[el.id]||"");
  drawJobs();drawCv(r.cv);
  $("#extfolder").textContent=r.ext.folder;$("#extcode").textContent=r.ext.code;
  $("#extstatus").innerHTML=r.ext.connected?'<span style="color:var(--good)">● Extension connected</span>':"Not connected yet.";
}
function drawCv(cv){$("#cvinfo").innerHTML=cv?`📄 <b>${esc(cv.name)}</b> (${Math.round(cv.size/1024)} KB)`:"No CV uploaded yet.";$("#cvremove").hidden=!cv}
document.addEventListener("input",e=>{const t=e.target;
  if(t.classList.contains("pf")){profile[t.id]=t.value;saveSoon()}
  if(t.classList.contains("jf")){profile.jobs[+t.dataset.j][t.dataset.f]=t.value;saveSoon()}});
const JF=[["title","Job title"],["company","Company"],["location","Location"],["start","Start (e.g. Jul 2022)"],["end","End (e.g. Present)"]];
function drawJobs(){const jobs=profile.jobs||[];
  $("#jobs").innerHTML=jobs.length?jobs.map((j,i)=>`<div class="jobcard"><div class="jobhead"><span class="serif">${esc(j.title||"New job")}${j.company?" · "+esc(j.company):""}</span>
    <span style="display:flex;gap:4px"><button class="iconbtn" data-mv="${i},-1" ${i?"":"disabled"} title="Move up">↑</button><button class="iconbtn" data-mv="${i},1" ${i<jobs.length-1?"":"disabled"} title="Move down">↓</button><button class="pill line sm" data-rmjob="${i}">Remove</button></span></div>
    <div class="pgrid">${JF.map(([f,l])=>`<label class="f">${l}<input type="text" class="jf" data-j="${i}" data-f="${f}" value="${esc(j[f])}"></label>`).join("")}
    <label class="f wide">What you did<textarea class="jf" data-j="${i}" data-f="description" rows="5">${esc(j.description)}</textarea></label></div></div>`).join(""):`<p class="muted" style="font-size:13.5px">No jobs yet — add one, or use “Fill from my CV”.</p>`;
  $$("[data-rmjob]").forEach(b=>b.onclick=()=>{const j=profile.jobs[+b.dataset.rmjob]||{};profileChange(`removing “${j.title||"a job"}” from your work history`);
    profile.jobs.splice(+b.dataset.rmjob,1);drawJobs();saveSoon();toast(`Removed “${j.title||"that job"}” from your work history`,UNDO)});
  $$("[data-mv]").forEach(b=>b.onclick=()=>{const [i,d]=b.dataset.mv.split(",").map(Number),a=profile.jobs;profileChange("moving a job");[a[i],a[i+d]]=[a[i+d],a[i]];drawJobs();saveSoon()});}
$("#addjob").onclick=()=>{profile.jobs=profile.jobs||[];profile.jobs.push({title:"",company:"",location:"",start:"",end:"",description:""});drawJobs();saveSoon();
  const last=$$('.jf[data-f="title"]').pop();if(last)last.focus()};
$("#cvremove").onclick=async()=>{const r=await post("/api/cv",{remove:true});drawCv(r.cv)};
$("#openext").onclick=()=>post("/api/openfolder",{});

// ---- extension code: shown top-right, one click to copy
let extCode="";
async function copyText(t){
  try{await navigator.clipboard.writeText(t);return true}catch(e){}
  try{const ta=document.createElement("textarea");ta.value=t;document.body.appendChild(ta);ta.select();const ok=document.execCommand("copy");ta.remove();if(ok)return true}catch(e){}
  try{const r=await post("/api/copy",{text:t});return !!r.ok}catch(e){return false}   // last resort: copy through Windows
}
async function loadExt(){try{const r=await get("/api/profile");extCode=r.ext.code;$("#extchipcode").textContent=extCode;
  $("#extdot").classList.toggle("on",!!r.ext.connected);drawStarted();$("#extchip").dataset.tip=(r.ext.connected?"Extension connected · ":"Extension not connected yet · ")+"click to copy the code"}catch(e){}}
const copyCode=async()=>{if(await copyText(extCode))toast(`Extension code ${extCode} copied`)};
$("#extchip").onclick=copyCode;$("#copycode").onclick=copyCode;
// ---- "Set up for me": opens Chrome's extensions page + the folder, copies the path, then watches for the connection
let extPoll=null;
$("#extsetup").onclick=()=>withSpinner($("#extsetup"),"Opening…",async()=>{
  const r=await post("/api/ext/setup",{});
  toast("Chrome's extensions page is opening — turn on Developer mode, click Load unpacked and paste (Ctrl+V)");
  $("#extstatus").innerHTML='<span class="spin"></span> Waiting for the extension to connect…';
  clearInterval(extPoll);let tries=0;
  extPoll=setInterval(async()=>{tries++;const s=await fetch("/api/ext/status",{method:"POST"}).then(r=>r.json()).catch(()=>({}));
    if(s.connected&&s.seconds_ago<30){clearInterval(extPoll);$("#extstatus").innerHTML='<span style="color:var(--good)">● Extension connected — you\'re all set!</span>';
      $("#extdot").classList.add("on");toast("Extension connected 🎉")}
    if(tries>150){clearInterval(extPoll);$("#extstatus").textContent="Not connected yet — follow the steps below."}},2000);
});

// ---- job match terms
let matchTerms=[];
async function loadTerms(){try{matchTerms=await get("/api/match_terms")}catch(e){matchTerms=[]}drawTerms()}
function drawTerms(){
  $("#mterms").innerHTML=matchTerms.length?matchTerms.map((t,i)=>`<div class="termrow">
    <input type="text" data-tn="${i}" value="${esc(t.name)}" placeholder="Job, e.g. Communications">
    <input type="text" data-ta="${i}" value="${esc((t.aliases||[]).join(", "))}" placeholder="Also called: comms, PR, public relations">
    <label class="check" title="Only count it when the word is in the job title"><input type="checkbox" data-tt="${i}" ${t.title_only?"checked":""}> Title only</label>
    <button class="iconbtn" data-tx="${i}" title="Remove">✕</button></div>`).join(""):`<p class="muted" style="font-size:12.5px;margin:0">No terms yet. Example: <b>Communications</b> — also called <i>comms, PR, public relations</i>.</p>`;
  $$("[data-tn]").forEach(e=>e.oninput=()=>matchTerms[+e.dataset.tn].name=e.value);
  $$("[data-ta]").forEach(e=>e.oninput=()=>matchTerms[+e.dataset.ta].aliases=e.value.split(",").map(s=>s.trim()).filter(Boolean));
  $$("[data-tt]").forEach(e=>e.onchange=()=>matchTerms[+e.dataset.tt].title_only=e.checked);
  $$("[data-tx]").forEach(e=>e.onclick=()=>{matchTerms.splice(+e.dataset.tx,1);drawTerms()});
}
$("#addterm").onclick=()=>{matchTerms.push({name:"",aliases:[],title_only:true});drawTerms();const l=$$("[data-tn]").pop();if(l)l.focus()};

// clear profile
$("#clearprof").onclick=()=>openModal("m-clear");
async function clearProfile(withCv){profileChange("clearing your profile");await post("/api/profile/clear",{cv:withCv});closeModals();await loadProfile();$("#fromcvmsg").textContent="";drawWelcome();drawStarted();
  toast(withCv?"Profile and CV cleared — Undo brings your details back (re-add the CV file yourself)":"Profile cleared — your CV is kept",UNDO)}
$("#clear1").onclick=()=>clearProfile(false);$("#clear2").onclick=()=>clearProfile(true);

// CV upload, drag & drop, fill from CV
let fillAfterUpload=false;
async function uploadCv(f,thenFill){
  if(!/\.(pdf|docx?|rtf|txt)$/i.test(f.name)){toast("Please use a PDF or Word file");return}
  if(f.size>10*1024*1024){toast("CV must be under 10 MB");return}
  const data=await new Promise(res=>{const rd=new FileReader();rd.onload=()=>res(rd.result.split(",")[1]);rd.readAsDataURL(f)});
  const r=await post("/api/cv",{name:f.name,data});if(r.error){toast(r.error);return}
  drawCv(r.cv);toast("CV saved");if(thenFill)fillFromCv();
}
$("#cvfile").onchange=e=>{const f=e.target.files[0];e.target.value="";if(f){uploadCv(f,fillAfterUpload);fillAfterUpload=false}};
["dragover","drop"].forEach(ev=>window.addEventListener(ev,e=>e.preventDefault()));
const drop=$("#drop");
["dragenter","dragover"].forEach(ev=>drop.addEventListener(ev,e=>{e.preventDefault();drop.classList.add("over")}));
["dragleave","drop"].forEach(ev=>drop.addEventListener(ev,()=>drop.classList.remove("over")));
drop.addEventListener("drop",e=>{const f=e.dataTransfer.files[0];if(f)uploadCv(f,true)});
window.addEventListener("drop",e=>{if(tab==="profile"&&!drop.contains(e.target)&&e.dataTransfer.files&&e.dataTransfer.files[0])uploadCv(e.dataTransfer.files[0],true)});
$("#fromcv").onclick=()=>{if($("#cvremove").hidden){fillAfterUpload=true;$("#cvfile").click()}else withSpinner($("#fromcv"),"Reading CV…",fillFromCv)};
async function fillFromCv(){
  $("#fromcvmsg").textContent="Reading your CV…";
  const r=await post("/api/cv/parse",{});if(r.error){$("#fromcvmsg").textContent=r.error;return}
  if((r.found||{}).read_with_ocr)toast("Parts of this CV are pictures of text — read them with Windows' text recognition, please double-check");
  offerImport(r.found||{},"your CV");
}

// ---- bringing details in from a CV or LinkedIn: add to what you have, or replace it
const fieldLabel=k=>{const el=document.getElementById(k);return ((el&&el.closest("label")?.firstChild.textContent)||k.replace(/_/g," ")).trim()};
const sameJob=(a,b)=>(a.title||"").toLowerCase().trim()===(b.title||"").toLowerCase().trim()&&(a.company||"").toLowerCase().trim()===(b.company||"").toLowerCase().trim();
let pendingImport=null;
function offerImport(found,source){
  const jobs=(found.jobs||[]).filter(j=>j.title||j.company);delete found.jobs;delete found.current_title;delete found.current_company;
  const keys=Object.keys(found).filter(k=>{const el=document.getElementById(k);return el&&el.classList.contains("pf")&&String(found[k]).trim()});
  if(!keys.length&&!jobs.length){$("#fromcvmsg").textContent=`Couldn't find details in ${source} (scanned image PDFs can't be read).`;toast("Nothing found to import");return}
  const haveFields=keys.filter(k=>(document.getElementById(k).value||"").trim()),haveJobs=(profile.jobs||[]).filter(j=>j.title||j.company);
  pendingImport={found,jobs,keys,source};
  if(!haveFields.length&&!haveJobs.length){applyImport("add");return}       // empty profile: nothing to decide
  const differ=keys.filter(k=>{const cur=(document.getElementById(k).value||"").trim();return cur&&cur!==String(found[k]).trim()});
  const fresh=keys.filter(k=>!(document.getElementById(k).value||"").trim());
  const newJobs=jobs.filter(j=>!haveJobs.some(h=>sameJob(h,j)));
  $("#imptitle").textContent=source==="your CV"?"Fill from your CV":"Import from LinkedIn";
  $("#impsub").textContent=`Found ${keys.length} detail${keys.length===1?"":"s"} and ${jobs.length} job${jobs.length===1?"":"s"} in ${source}. Your profile already has some details — how should they be combined?`;
  $("#implist").innerHTML=[
    fresh.length?`<li><b>${fresh.length} empty field${fresh.length===1?"":"s"}</b> can be filled: ${esc(fresh.map(fieldLabel).slice(0,8).join(", "))}${fresh.length>8?"…":""}</li>`:"",
    differ.length?`<li><b>${differ.length} different</b> from what you have: ${differ.slice(0,6).map(k=>`${esc(fieldLabel(k))} <span class="muted">(“${esc(String(document.getElementById(k).value).slice(0,28))}” → “${esc(String(found[k]).slice(0,28))}”)</span>`).join(", ")}${differ.length>6?"…":""}</li>`:"",
    jobs.length?`<li><b>${newJobs.length} new job${newJobs.length===1?"":"s"}</b>${jobs.length-newJobs.length?` (${jobs.length-newJobs.length} already in your work history)`:""}: ${esc(newJobs.slice(0,4).map(j=>j.title+(j.company?" at "+j.company:"")).join("; "))}</li>`:""].join("");
  $("#impadd").innerHTML=`Add to my profile`;$("#impreplace").textContent="Replace my profile";
  openModal("m-import");
}
async function applyImport(mode){
  const p=pendingImport;if(!p)return;pendingImport=null;closeModals();
  profileChange(`importing from ${p.source}`);
  const filled=[];
  for(const k of p.keys){const el=document.getElementById(k),cur=(el.value||"").trim();
    if(mode==="replace"||!cur){if(cur!==String(p.found[k]).trim()){el.value=p.found[k];profile[k]=p.found[k];filled.push(k);el.style.borderColor="var(--good)";setTimeout(()=>el.style.borderColor="",6000)}}}
  let jobsAdded=0;
  if(p.jobs.length){
    if(mode==="replace"){profile.jobs=p.jobs;jobsAdded=p.jobs.length}
    else{const have=(profile.jobs||[]).filter(j=>j.title||j.company);const add=p.jobs.filter(j=>!have.some(h=>sameJob(h,j)));
      profile.jobs=have.concat(add);jobsAdded=add.length}
    drawJobs();
  }
  if(filled.length||jobsAdded){await post("/api/profile",{profile});drawWelcome()}
  const n=filled.filter(k=>k!=="country").length,jt=jobsAdded?` and ${mode==="replace"?"replaced your work history with":"added"} ${jobsAdded} job${jobsAdded>1?"s":""}`:"";
  const msg=(n||jobsAdded)?`${mode==="replace"?"Replaced":"Filled"} ${n} field${n===1?"":"s"}${jt} from ${p.source} (green borders) — please check them.`:"Nothing new — your profile already has these details.";
  $("#fromcvmsg").textContent=msg;toast(msg.split(" (")[0],(n||jobsAdded)?UNDO:undefined);drawStarted();
}
$("#impadd").onclick=()=>applyImport("add");
$("#impreplace").onclick=()=>applyImport("replace");
$("#fromli").onclick=()=>{$("#liurl").value=$("#liurl").value||profile.linkedin||"";$("#listatus").textContent="";openModal("m-lihelp")};
// a profile link: the app opens it in Chrome, the extension reads the page and sends it back here
let liPoll=null;
async function importLinkedInLink(url,say){
  url=(url||"").trim();if(!url){say("Paste your profile link first — it looks like linkedin.com/in/your-name");return}
  const r=await post("/api/linkedin/link",{url});if(r.error){say(r.error);return}
  say(r.connected?`<span class="spin"></span> Opened in Chrome — reading your profile. Keep that tab open for a few seconds…`
    :`<span class="spin"></span> Opened in Chrome. The Chrome extension doesn't seem to be set up yet — set it up (Profile → Chrome extension), then press Import again.`,true);
  clearInterval(liPoll);let n=0;
  liPoll=setInterval(async()=>{n++;let st={};try{st=await fetch("/api/linkedin/link").then(r=>r.json())}catch(e){}
    if(st.found){clearInterval(liPoll);post("/api/linkedin/link",{cancel:true});say("Read your LinkedIn profile ✓");
      if($("#m-onboard").classList.contains("open")){await loadProfile();offerImport(st.found,"your LinkedIn profile");$("#obcvmsg").textContent=$("#fromcvmsg").textContent||"LinkedIn profile read ✓";return}
      closeModals();setTab("profile");await loadProfile();offerImport(st.found,"your LinkedIn profile")}
    else if(st.error){clearInterval(liPoll);say(esc(st.error))}
    else if(!st.waiting||n>150){clearInterval(liPoll);say("Didn't hear back from Chrome. Check you're signed in to LinkedIn there and the extension is set up, then try again — or use a file instead.")}},2000);
}
$("#ligo").onclick=()=>importLinkedInLink($("#liurl").value,(t,h)=>{$("#listatus")[h?"innerHTML":"textContent"]=t.replace(/<(?!\/?span)[^>]*>/g,"")});
$("#liurl").addEventListener("keydown",e=>{if(e.key==="Enter")$("#ligo").click()});
$("#lipick").onclick=()=>{clearInterval(liPoll);closeModals();$("#lifile").click()};
$("#lifile").onchange=async e=>{const f=e.target.files[0];e.target.value="";if(!f)return;
  if(f.size>30*1024*1024){toast("That file is too big (30 MB max)");return}
  await withSpinner($("#fromli"),"Reading…",async()=>{
    const data=await new Promise(res=>{const rd=new FileReader();rd.onload=()=>res(rd.result.split(",")[1]);rd.readAsDataURL(f)});
    const r=await post("/api/linkedin",{name:f.name,data});
    if(r.error){toast(r.error);$("#fromcvmsg").textContent=r.error;return}
    offerImport(r.found||{},"your LinkedIn "+(/\.zip$/i.test(f.name)?"export":"profile"))})};
