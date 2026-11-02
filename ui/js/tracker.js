// ============================================================= tracker board
async function loadSaved(){saved=await get("/api/saved");drawStrip();if(tab==="tracker")drawBoard();render()}
function drawBoard(){
  const f=$("#tfilter").value.toLowerCase().trim(),today=todayStr();
  const list=saved.filter(j=>!f||[j.title,j.company,j.location,j.notes].join(" ").toLowerCase().includes(f));
  const ts=$("#tsort").value,by=(k,d)=>(a,b)=>(b[k]||d).localeCompare(a[k]||d);
  if(ts==="added")list.sort((a,b)=>saved.indexOf(b)-saved.indexOf(a));
  else if(ts==="applied")list.sort(by("applied_on",""));
  else if(ts==="follow")list.sort((a,b)=>(a.follow_up||"9999").localeCompare(b.follow_up||"9999"));
  else if(ts==="salary")list.sort((a,b)=>annualOf(b)-annualOf(a));
  else if(ts==="company")list.sort((a,b)=>(a.company||"").localeCompare(b.company||""));
  else if(ts==="title")list.sort((a,b)=>(a.title||"").localeCompare(b.title||""));
  $("#boardempty").hidden=saved.length>0;
  const cols=STAGES.concat(list.some(j=>j.status==="Not interested")?["Not interested"]:[]);
  $("#board").style.gridTemplateColumns=`repeat(${cols.length},minmax(210px,1fr))`;
  $("#board").innerHTML=cols.map(st=>{const cards=list.filter(j=>(j.status||"Saved")===st);
    return `<div class="col" data-col="${st}"><h4>${st}<span>${cards.length}</span></h4>${cards.map(j=>{const idx=saved.indexOf(j),due=j.follow_up&&j.follow_up<=today&&!["Offer","Rejected"].includes(st);
      return `<div class="card" draggable="true" data-i="${idx}">
        <button class="bin" data-bin="${idx}" title="Remove from tracker">🗑</button>
        <div class="t">${esc(j.title)}</div><div class="c">${esc(j.company)}${j.location?" · "+esc(j.location):""}</div>
        <div class="d">${j.applied_on?`<span>Applied ${esc(j.applied_on)}</span>`:`<span>Saved ${esc(j.saved_on||"")}</span>`}${j.follow_up?`<span class="${due?"due":""}">${due?"Follow up due":"Follow up"} ${esc(j.follow_up)}</span>`:""}${j.notes?"<span>📝</span>":""}</div>
        <div class="cacts">${nextBtns(st).map(n=>`<button data-move="${idx}" data-to="${n}" data-tip="${esc(MOVE_TIPS[n]||"Move to "+n)}">→ ${n}</button>`).join("")}${st==="Offer"?`<button data-share="${idx}" data-tip="Tell jobslop how you got it (anonymous)">🥂 Share</button>`:""}<button data-edit="${idx}" data-tip="Status, dates, salary, notes and a follow-up reminder">Edit</button>${String(j.url).startsWith("http")?`<button data-href="${esc(j.url)}" data-tip="Open the advert in your browser">Open</button><button data-copy="${esc(j.url)}" class="copylink" data-tip="Copy link">⧉</button>`:""}</div>
      </div>`}).join("")||`<div class="muted" style="font-size:12.5px;padding:8px 4px">Drop cards here</div>`}</div>`}).join("");
  $$(".card").forEach(c=>{c.ondragstart=e=>{e.dataTransfer.setData("text/plain",c.dataset.i);e.dataTransfer.effectAllowed="move"}});
  $$(".col").forEach(col=>{col.ondragover=e=>{e.preventDefault();col.classList.add("over")};col.ondragleave=()=>col.classList.remove("over");
    col.ondrop=e=>{e.preventDefault();col.classList.remove("over");const i=+e.dataTransfer.getData("text/plain");if(!isNaN(i)&&saved[i])moveTo(saved[i],col.dataset.col)}});
  $$("[data-move]").forEach(b=>b.onclick=()=>moveTo(saved[+b.dataset.move],b.dataset.to));
  $$("[data-edit]").forEach(b=>b.onclick=()=>editApp(saved[+b.dataset.edit]));
  $$("[data-share]").forEach(b=>b.onclick=()=>celebrate(saved[+b.dataset.share]));
  $$("[data-bin]").forEach(b=>b.onclick=e=>{e.stopPropagation();binCard(+b.dataset.bin,b.closest(".card"))});
}
async function binCard(idx,el){
  const j=saved[idx];if(!j)return;
  if(el)el.classList.add("removing");
  await new Promise(r=>setTimeout(r,220));
  await trackerChange(`removing “${j.title}”`,async()=>{saved=await post("/api/saved",{action:"remove",job:{url:j.url}})});
  refreshTracked();
  toast(`Removed “${j.title}”`,UNDO);
}
const MOVE_TIPS={Applied:"Mark as applied — today's date counts towards your stats",Interview:"You've got an interview — move it on",
  Offer:"You got an offer!",Rejected:"Didn't work out — keeps your stats honest",Saved:"Put it back with your saved jobs"};
function nextBtns(st){return {Saved:["Applied"],Applying:["Applied"],Applied:["Interview","Rejected"],Interview:["Offer","Rejected"],Offer:[],Rejected:[],"Not interested":["Saved"]}[st]||[]}
async function moveTo(j,st){if(!j||j.status===st)return;
  await trackerChange(`moving “${j.title}” to ${st}`,async()=>{saved=await post("/api/saved",{action:"update",job:{url:j.url,status:st}})});
  refreshTracked();if(st==="Applied")toast("Marked as applied — keep it up! 🎉",UNDO);else if(st==="Interview")toast("An interview! Brilliant 🎉",UNDO);
  else if(st==="Offer")celebrate(saved.find(x=>x.url===j.url)||j);else toast(`Moved to ${st}`,UNDO)}
$("#tfilter").addEventListener("input",drawBoard);
$("#gosearch").onclick=()=>{setTab("search");setTimeout(()=>$("#q").focus(),200)};

// ============================================================= an offer: thank you, and an email to tell jobslop about it
const MAILTO=(subject,body)=>`mailto:jobslop@proton.me?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;
const sendMail=(subject,body)=>PHONE?(location.href=MAILTO(subject,body)):post("/api/open",{url:MAILTO(subject,body)});
let offerJob=null;
// anonymous on purpose: no job, company, place, dates or anything else that could identify you - just a few counts
function offerText(j){
  const s=stats(),d=j.dates||{},applied=j.applied_on||d.Applied||"",offer=d.Offer||todayStr();
  const days=applied?Math.max(0,Math.round((new Date(offer)-new Date(applied))/864e5)):"not sure";
  const first=saved.map(appliedDate).filter(Boolean).sort()[0];
  const weeks=first?Math.max(1,Math.round((new Date(offer)-new Date(first))/(7*864e5))):"not sure";
  return ["Hi jobslop,","","Good news - I got an offer!","",
    `Days from applying to the offer: ${days}`,`Weeks of job hunting with jobslop: ${weeks}`,`Used Easy apply for this one: ${d.Applying?"yes":"no"}`,
    `Applications sent: ${s.total}   Interviews: ${s.interviews}   Offers: ${s.offers}`,"",
    "What helped most (optional):","","","Anything jobslop could do better (optional):","","","Thanks!"].join("\n")}
function celebrate(j){if(!j)return;offerJob=j;$("#offerjob").textContent=[j.title,j.company].filter(Boolean).join(" at ");
  $("#offermail").value=offerText(j);openModal("m-offer");setTimeout(()=>$("#offersend").focus(),80)}
$("#offersend").onclick=()=>{sendMail("jobslop: I got an offer!",$("#offermail").value);closeModals();toast("Thank you for using jobslop! 💛")};
$("#offercopy").onclick=async()=>{if(await copyText("To: jobslop@proton.me\n\n"+$("#offermail").value))toast("Copied — paste it into an email to jobslop@proton.me")};
function feedbackText(){const s=stats();return ["Hi jobslop,","","","",
  "-- a little about how I use it (delete if you like) --",`Applications: ${s.total}   Interviews: ${s.interviews}   Offers: ${s.offers}   Jobs tracked: ${s.tracked}`,
  `Easy apply extension set up: ${$("#extdot").classList.contains("on")?"yes":"no"}`,`jobslop version: ${appVersion}`].join("\n")}
$("#feedback").onclick=()=>{$("#fbmail").value=feedbackText();openModal("m-feedback");setTimeout(()=>{const t=$("#fbmail");t.focus();t.setSelectionRange(12,12)},80)};
$("#fbsend").onclick=()=>{sendMail("jobslop feedback",$("#fbmail").value);closeModals();toast("Thank you for helping make jobslop better! 💛")};
$("#fbcopy").onclick=async()=>{if(await copyText("To: jobslop@proton.me\n\n"+$("#fbmail").value))toast("Copied — paste it into an email to jobslop@proton.me")};
$("#tsort").value=pref("tsort")||"added";
$("#tsort").addEventListener("change",()=>{pref("tsort",$("#tsort").value);drawBoard()});
let editing=null;
$("#a_status").innerHTML=STAGES.concat("Not interested").map(s=>`<option>${s}</option>`).join("");
function editApp(j){editing=j;$("#addtitle").textContent=j?"Edit application":"Add an application";$("#addsub").textContent=j?(j.source?"From "+j.source:""):"For jobs you applied to outside jobslop.";
  $("#a_title").value=j?j.title:"";$("#a_company").value=j?j.company:"";$("#a_location").value=j?(j.location||""):"";$("#a_salary").value=j?(j.salary||""):"";
  $("#a_status").value=j?(j.status||"Saved"):"Applied";$("#a_applied").value=j?(j.applied_on||""):todayStr();$("#a_follow").value=j?(j.follow_up||""):"";
  $("#a_url").value=j&&String(j.url).startsWith("http")?j.url:"";$("#a_url").disabled=!!j;$("#a_notes").value=j?(j.notes||""):"";$("#a_delete").hidden=!j;openModal("m-add")}
$("#addapp").onclick=()=>editApp(null);
$("#a_save").onclick=async()=>{
  const d={title:$("#a_title").value.trim(),company:$("#a_company").value.trim(),location:$("#a_location").value.trim(),salary:$("#a_salary").value.trim(),
    status:$("#a_status").value,applied_on:$("#a_applied").value,follow_up:$("#a_follow").value,notes:$("#a_notes").value};
  if(!d.title&&!d.company){toast("Add at least a title or company");return}
  const was=editing,becameOffer=d.status==="Offer"&&(!was||was.status!=="Offer");
  await trackerChange(was?`editing “${d.title||was.title}”`:`adding “${d.title||d.company}”`,async()=>{
    if(was)saved=await post("/api/saved",{action:"update",job:{url:was.url,...d}});
    else saved=await post("/api/saved",{action:"add",job:{url:$("#a_url").value.trim(),source:"Added by you",date:"",...d}})});
  closeModals();refreshTracked();
  if(becameOffer)celebrate(saved.find(x=>was?x.url===was.url:x.title===d.title&&x.company===d.company)||d);else toast("Saved",UNDO)};
$("#a_delete").onclick=()=>{if(!editing)return;closeModals();binCard(saved.indexOf(editing),null)};
