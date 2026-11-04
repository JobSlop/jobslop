// ============================================================= basics
const $=s=>document.querySelector(s), $$=s=>[...document.querySelectorAll(s)];
const esc=s=>String(s??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const pref=(k,v)=>{try{if(v===undefined)return localStorage.getItem(k);localStorage.setItem(k,v)}catch(e){}};
// every request lights up the loading bar at the top while it's running
let pending=0;const busy=d=>{pending=Math.max(0,pending+d);document.getElementById("loadbar").classList.toggle("on",pending>0)};
const post=(u,b)=>{busy(1);return fetch(u,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(b)}).then(r=>r.json()).finally(()=>busy(-1))};
const get=u=>{busy(1);return fetch(u).then(r=>r.json()).finally(()=>busy(-1))};
// buttons show a spinner while their job runs
async function withSpinner(btn,label,fn){const old=btn.innerHTML;btn.classList.add("busy");btn.innerHTML=`<span class="spin"></span> ${label}`;
  try{return await fn()}finally{btn.classList.remove("busy");btn.innerHTML=old}}
// On a phone (phone access), links open on the phone itself; on the computer they open in your browser
const PHONE=!!window.JF_PHONE;
if(PHONE)document.documentElement.classList.add("phone");
const openUrl=u=>PHONE?window.open(u,"_blank","noopener"):post("/api/open",{url:u});
const todayStr=()=>{const d=new Date();return d.getFullYear()+"-"+String(d.getMonth()+1).padStart(2,"0")+"-"+String(d.getDate()).padStart(2,"0")};
const dayStr=d=>d.getFullYear()+"-"+String(d.getMonth()+1).padStart(2,"0")+"-"+String(d.getDate()).padStart(2,"0");
function toast(t,action){const el=$("#toast");el.innerHTML=esc(t)+(action?`<button>${esc(action.label)}</button>`:"");
  if(action)el.querySelector("button").onclick=()=>{el.classList.remove("show");action.fn()};
  el.classList.add("show");clearTimeout(el._t);el._t=setTimeout(()=>el.classList.remove("show"),action?7000:3800)}
// Ctrl+R / F5 reloads the app (the app window doesn't do this by itself)
function reloadApp(){$("#splash").classList.remove("gone");setTimeout(()=>location.reload(),180)}
document.addEventListener("keydown",e=>{if(((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==="r")||e.key==="F5"){e.preventDefault();reloadApp()}});
// windows open on top of whatever is already open, focus moves into them, and goes back where it was on close
let modalZ=50,lastFocus=null;
function openModal(id){const m=$("#"+id);if(!m.classList.contains("open"))lastFocus=document.activeElement;
  m.style.zIndex=++modalZ;m.classList.add("open");hideTip();
  setTimeout(()=>{const f=m.querySelector("[autofocus],input:not([type=hidden]):not([disabled]),textarea,select,.box button.dark");if(f&&!PHONE)f.focus()},60)}
function closeModals(){const wasOpen=$$(".modal.open").length;$$(".modal").forEach(m=>m.classList.remove("open"));
  if(wasOpen&&lastFocus&&document.contains(lastFocus)){try{lastFocus.focus({preventScroll:true})}catch(e){}}lastFocus=null}
$$(".modal .box").forEach((b,i)=>{b.setAttribute("role","dialog");b.setAttribute("aria-modal","true");const h=b.querySelector("h3");if(h){h.id=h.id||"mt"+i;b.setAttribute("aria-labelledby",h.id)}});
$$("[data-close]").forEach(b=>b.onclick=closeModals);
$$(".modal").forEach(m=>m.addEventListener("click",e=>{if(e.target===m&&m.id!=="m-onboard")closeModals()}));
document.addEventListener("keydown",e=>{if(e.key==="Escape"){hideTip();if($("#m-onboard").classList.contains("open"))finishOnboarding();closeModals();$("#themepop").classList.remove("open");$("#updpop").classList.remove("open")}});
// keyboard: Ctrl+Z undoes your last change (typing in a box keeps its own undo), "/" jumps to the search box
const typing=e=>e.target.closest&&e.target.closest("input,textarea,select,[contenteditable]");
document.addEventListener("keydown",e=>{
  if((e.ctrlKey||e.metaKey)&&!e.shiftKey&&e.key.toLowerCase()==="z"&&!typing(e)){e.preventDefault();undoLast()}
  else if(e.key==="/"&&!typing(e)&&!e.ctrlKey&&!e.metaKey&&!$$(".modal.open").length){e.preventDefault();setTab("search");$("#q").disabled?$("#where").focus():$("#q").focus()}});

// ============================================================= tooltips: one label above everything, never cut off
const tipEl=document.createElement("div");tipEl.id="tip";tipEl.setAttribute("role","tooltip");document.body.appendChild(tipEl);
let tipFor=null,tipHover=null,tipTimer=null;
const tipOf=el=>{if(el.hasAttribute("title")){el.dataset.tip=el.getAttribute("title");el.removeAttribute("title")}return el.dataset.tip};
function showTip(el){const t=tipOf(el);if(!t||!document.contains(el))return;tipFor=el;tipEl.textContent=t;tipEl.classList.add("on");
  const r=el.getBoundingClientRect(),w=tipEl.offsetWidth,h=tipEl.offsetHeight,gap=8;
  let top=r.bottom+gap;if(top+h>innerHeight-6)top=r.top-h-gap;
  const left=Math.max(6,Math.min(innerWidth-w-6,r.left+r.width/2-w/2));
  tipEl.style.top=Math.max(6,top)+"px";tipEl.style.left=left+"px";el.setAttribute("aria-describedby","tip")}
function hideTip(){clearTimeout(tipTimer);tipEl.classList.remove("on");if(tipFor)tipFor.removeAttribute("aria-describedby");tipFor=null}
document.addEventListener("mouseover",e=>{const el=e.target.closest&&e.target.closest("[data-tip],[title]");if(el===tipHover)return;
  tipHover=el;hideTip();if(!el||PHONE||matchMedia("(hover:none)").matches)return;tipOf(el);tipTimer=setTimeout(()=>showTip(el),300)});
document.addEventListener("focusin",e=>{const el=e.target.closest&&e.target.closest("[data-tip],[title]");if(el&&e.target.matches(":focus-visible")){hideTip();showTip(el)}});
document.addEventListener("focusout",()=>{if(!tipHover)hideTip()});
document.addEventListener("mousedown",hideTip);window.addEventListener("scroll",hideTip,true);window.addEventListener("blur",hideTip);

// hover labels for controls that aren't self-explanatory (tick boxes get theirs on the whole label)
const TIPS={
  '.tab[data-tab="search"]':"Find jobs on dozens of job boards at once",
  '.tab[data-tab="tracker"]':"Every job you've saved or applied to, by stage",
  '.tab[data-tab="progress"]':"Your applications, streak, interview rate and weekly goal",
  '.tab[data-tab="profile"]':"Your details, CV and work history — used to fill in applications",
  "#q":"Job titles or skills — separate several with commas",
  "#go":"Search the ticked job boards (Enter works too)",
  "#perpage":"How many results to show on each page",
  "#csv":"Save the results you can see as a spreadsheet",
  "#hassal":"Hide jobs that don't list a salary",
  "#strict":"Only show jobs whose title contains what you searched for",
  "#filter":"Narrow the results — matches title, company, place and description",
  "#exclude":"Hide jobs whose title contains any of these words (comma separated)",
  "#srcfilter":"Only show jobs from one job board",
  "#tfilter":"Find a job on your tracker by title, company, place or notes",
  "#tsort":"Change the order of the cards in each column",
  "#addapp":"Track a job you applied to somewhere else",
  "#tcsv":"Save your whole tracker as a spreadsheet",
  "#goal":"How many applications you aim for each week (Monday to Sunday)",
  "#fromcv":"Read your CV and fill in your details and work history — you choose what to keep",
  "#clearprof":"Start again with an empty profile (you can undo this)",
  "#addjob":"Add a job to your work history by hand",
  "#cvremove":"Delete the CV saved in jobslop (the file on your computer isn't touched)",
  "#extsetup":"Opens Chrome's extensions page and the extension folder, and copies the path for you",
  "#openext":"Show the extension folder in File Explorer",
  "#copycode":"Copy the code, in case the extension asks for it",
  "#addterm":"Teach jobslop another name for a job, e.g. PR = communications",
  "#phoneon":"Use jobslop from your phone on the same Wi-Fi, protected by a PIN",
  "#phonesignout":"Signs out every phone that's connected",
  "#setcurrency":"Convert every salary to one currency so they're easy to compare",
  "#setunit":"Show distances in miles or kilometres",
  "#updcheck":"Ask GitHub now if there's a newer jobslop",
  "#feedback":"Write to jobslop@proton.me from your own email app",
  "#gsshow":"Bring back the getting-started list on the Search page",
  "#savekeys":"Save your job board keys and preferences",
  "#mapuse":"Search around this place with this radius",
  "#maprad":"How far from the pin you're willing to travel",
  "#liurl":"The address of your LinkedIn profile, e.g. linkedin.com/in/your-name",
  "#obliurl":"The address of your LinkedIn profile, e.g. linkedin.com/in/your-name",
};
Object.entries(TIPS).forEach(([sel,tip])=>$$(sel).forEach(el=>{
  const target=el.type==="checkbox"?(el.closest("label")||el):el;
  if(!target.dataset.tip&&!target.title)target.dataset.tip=tip}));
$$("#strip > div").forEach(d=>d.dataset.tip="Open your progress");

// ============================================================= undo (↶ button or Ctrl+Z)
const undoStack=[];
function remember(label,fn){undoStack.push({label,fn});if(undoStack.length>30)undoStack.shift();drawUndo()}
function drawUndo(){const b=$("#undobtn"),top=undoStack[undoStack.length-1];b.disabled=!top;
  b.dataset.tip=top?`Undo ${top.label} (Ctrl+Z)`:"Nothing to undo yet";if(tipFor===b)showTip(b)}
async function undoLast(){const a=undoStack.pop();drawUndo();if(!a)return toast("Nothing to undo");
  try{await a.fn();toast("Undone: "+a.label)}catch(e){toast("Couldn't undo that")}}
const UNDO={label:"Undo",fn:()=>undoLast()};
// any tracker change: the whole tracker is remembered first, so Undo puts it back exactly
async function trackerChange(label,fn){const before=JSON.parse(JSON.stringify(saved));const r=await fn();
  remember(label,async()=>{saved=await post("/api/saved",{action:"set_all",items:before});refreshTracked()});return r}
// profile changes (imports, removing a job, clearing): the profile is remembered first
function profileChange(label){const before=JSON.parse(JSON.stringify(profile));
  remember(label,async()=>{profile=before;await post("/api/profile",{profile});$$(".pf").forEach(el=>el.value=profile[el.id]||"");drawJobs();drawWelcome();drawStarted()})}
document.addEventListener("click",e=>{const a=e.target.closest("[data-href]");if(a){e.preventDefault();openUrl(a.dataset.href)}});
// copy-link buttons (any element with data-copy): copies, flashes a ✓, confirms with a toast
document.addEventListener("click",async e=>{const b=e.target.closest("[data-copy]");if(!b)return;e.preventDefault();e.stopPropagation();
  const ok=await copyText(b.dataset.copy);if(!ok)return toast("Couldn't copy — select the link manually");
  const old=b.innerHTML;b.innerHTML="✓";b.classList.add("done");setTimeout(()=>{b.innerHTML=old;b.classList.remove("done")},1400);toast("Link copied")});

// the job boards come from the app (core + plugins): name, description, group, countries, needs_key, slow
let BOARDS=[];
const KEYS=["apify_token"];          // the app's own keys; plugins add theirs (see plugins.settings)
const STAGES=["Saved","Applying","Applied","Interview","Offer","Rejected"];
const APPLIED=["Applied","Interview","Offer","Rejected"];
let results=[],saved=[],profile={},keys={},countries=[],tab="search",anyMode=false,cvMode=false,searching=false;

// ============================================================= theme
const PALETTES={sand:"#9b7b55",sage:"#6b8a67",ocean:"#3d7096",terracotta:"#b4623d",plum:"#86608f",graphite:"#5d6166"};
function applyTheme(){const m=pref("mode")||"auto",p=pref("palette")||"sand";
  document.documentElement.dataset.theme=m;document.documentElement.dataset.palette=p;
  $$("#modeseg button").forEach(b=>b.classList.toggle("on",b.dataset.mode===m));
  $$("#swatches button").forEach(b=>b.classList.toggle("on",b.dataset.p===p));
  const lf=pref("listfont")||"clear";document.documentElement.dataset.listfont=lf;
  $$("#fontseg button").forEach(b=>b.classList.toggle("on",b.dataset.font===lf));
  applyZoom();drawRing();}
// ---- text size of the job list and tracker (80% to 160%), kept like the theme
const ZOOMS=[.8,.9,1,1.1,1.2,1.35,1.5,1.6];
function listZoom(){const z=+pref("listzoom")||1;return ZOOMS.includes(z)?z:1}
function applyZoom(){const z=listZoom();document.documentElement.style.setProperty("--lz",z);
  const v=$("#zoomval");if(v)v.textContent=Math.round(z*100)+"%";
  const o=$("#zoomout"),i=$("#zoomin");if(o)o.disabled=z<=ZOOMS[0];if(i)i.disabled=z>=ZOOMS[ZOOMS.length-1]}
function stepZoom(d){const at=ZOOMS.indexOf(listZoom()),z=d?ZOOMS[Math.max(0,Math.min(ZOOMS.length-1,at+d))]:1;savePref("listzoom",String(z));applyZoom()}
$("#swatches").innerHTML=Object.entries(PALETTES).map(([k,c])=>`<button data-p="${k}" title="${k[0].toUpperCase()+k.slice(1)}" style="background:${c}"></button>`).join("");
// appearance is also saved with the app's settings, so it survives restarts
const savePref=(k,v)=>{pref(k,v);post("/api/prefs",{[k]:v}).catch(()=>{})};
$$("#swatches button").forEach(b=>b.onclick=()=>{savePref("palette",b.dataset.p);applyTheme()});
$$("#modeseg button").forEach(b=>b.onclick=()=>{savePref("mode",b.dataset.mode);applyTheme()});
$$("#fontseg button").forEach(b=>b.onclick=()=>{savePref("listfont",b.dataset.font);applyTheme()});
$("#zoomin").onclick=()=>stepZoom(1);$("#zoomout").onclick=()=>stepZoom(-1);$("#zoomval").onclick=()=>stepZoom(0);
// Ctrl + / Ctrl − / Ctrl 0 size the list text (the rest of the screen stays as it is)
document.addEventListener("keydown",e=>{if(!(e.ctrlKey||e.metaKey)||e.altKey)return;
  if(e.key==="="||e.key==="+"){e.preventDefault();stepZoom(1)}else if(e.key==="-"){e.preventDefault();stepZoom(-1)}else if(e.key==="0"){e.preventDefault();stepZoom(0)}});
$("#reloadbtn").onclick=reloadApp;
$("#undobtn").onclick=()=>undoLast();
$("#home").onclick=e=>{e.preventDefault();setTab("search");window.scrollTo({top:0,behavior:"smooth"});setTimeout(()=>{if(!$("#q").disabled)$("#q").focus({preventScroll:true})},250)};
$("#themebtn").onclick=e=>{e.stopPropagation();$("#themepop").classList.toggle("open")};
document.addEventListener("click",e=>{if(!e.target.closest("#themepop")&&e.target.id!=="themebtn")$("#themepop").classList.remove("open")});
