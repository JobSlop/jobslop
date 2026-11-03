// ============================================================= CV matching
const STOP=new Set("a an the and or of for in to with at on by senior junior lead principal head intern internship contract trainee graduate associate assistant i ii iii".split(" "));
const words=s=>(s||"").toLowerCase().split(/[^a-z0-9+#.]+/).filter(w=>w&&w.length>1&&!STOP.has(w));
function cvTitles(){
  const ts=(profile.jobs||[]).map(j=>j.title).concat(profile.current_title||[]).filter(Boolean);
  const seen=new Set(),out=[];
  for(const t of ts){const core=words(t).join(" ");if(core&&!seen.has(core)){seen.add(core);out.push(t.replace(/\b(intern|internship|contract|trainee)\b/ig,"").replace(/\s+/g," ").trim())}}
  return out.slice(0,3);
}
function cvTerms(){
  const skills=(profile.skills||"").split(/[,;\n]/).map(s=>s.trim().toLowerCase()).filter(s=>s.length>1).slice(0,40);
  const titles=cvTitles();
  const tw=new Set(titles.flatMap(words)),phrases=titles.map(t=>words(t).join(" ")).filter(p=>p.includes(" "));   // single words like "programmer" are too vague
  // your job match terms: a CV title that matches a term brings in all its other names
  for(const g of matchTerms){const names=[g.name].concat(g.aliases||[]).filter(Boolean);
    if(titles.some(t=>names.some(n=>t.toLowerCase().includes(n.toLowerCase()))))
      names.forEach(n=>{const p=words(n).join(" ");if(p&&!phrases.includes(p))phrases.push(p);words(n).forEach(w=>tw.add(w))})}
  return {skills,tw,phrases};
}
function matchPct(j,terms){
  if(!terms||(!terms.skills.length&&!terms.tw.size))return null;
  const jt=words(j.title),hay=(j.title+" "+(j.tags||[]).join(" ")+" "+j.desc).toLowerCase();
  // your whole job title in theirs ("Software Engineer") counts far more than a shared word ("engineer")
  const jtJoined=" "+jt.join(" ")+" ";
  const phrase=terms.phrases.some(p=>jtJoined.includes(" "+p+" "));
  const titleScore=phrase?1:(jt.length?0.7*jt.filter(w=>terms.tw.has(w)).length/jt.length:0);
  const hits=terms.skills.filter(s=>{const re=new RegExp("(^|[^a-z0-9])"+s.replace(/[.*+?^${}()|[\]\\]/g,"\\$&")+"($|[^a-z0-9+#])");return re.test(hay)}).length;
  const skillScore=terms.skills.length?Math.min(1,hits/Math.min(6,terms.skills.length)):0;
  const w=j.desc?0.5:0.8;   // no description (LinkedIn) -> lean on the title
  return Math.round(100*Math.min(1,w*Math.min(1,titleScore)+(1-w)*skillScore));
}

// ============================================================= currency
const CUR_SYM={GBP:"£",USD:"$",EUR:"€",INR:"₹",JPY:"¥",AUD:"A$",CAD:"C$",NZD:"NZ$",SGD:"S$",HKD:"HK$",BRL:"R$",ZAR:"R ",CHF:"CHF ",SEK:"kr ",NOK:"kr ",DKK:"kr ",
  PLN:"zł ",MXN:"MX$",AED:"AED ",SAR:"SAR ",CZK:"Kč ",HUF:"Ft ",RON:"lei ",TRY:"₺",ILS:"₪",MYR:"RM ",PHP:"₱",IDR:"Rp ",THB:"฿",KRW:"₩",UAH:"₴",EGP:"E£",NGN:"₦",QAR:"QAR ",VND:"₫",ARS:"AR$",CLP:"CLP$",COP:"COL$"};
const CUR_LIST=["GBP","USD","EUR","CAD","AUD","NZD","CHF","SEK","NOK","DKK","PLN","INR","JPY","SGD","HKD","AED","ZAR","BRL","MXN"];
const SYM_DETECT=[["NZ$","NZD"],["AU$","AUD"],["A$","AUD"],["CA$","CAD"],["C$","CAD"],["S$","SGD"],["HK$","HKD"],["R$","BRL"],["MX$","MXN"],["US$","USD"],["£","GBP"],["€","EUR"],["₹","INR"],["¥","JPY"],["$","USD"]];
let rates={},ratesInfo="",currency="orig";
async function loadRates(){try{const r=await get("/api/rates");rates=r.rates||{};ratesInfo=`rates from ${r.source}, ${r.updated}`}catch(e){}}
function parseSalary(s,hint){
  if(!s)return null;const t=String(s);let cur=null;
  const code=t.match(/\b(GBP|USD|EUR|INR|AUD|CAD|CHF|SEK|NOK|DKK|PLN|ZAR|SGD|NZD|JPY|BRL|MXN|AED|HKD)\b/i);
  if(code)cur=code[1].toUpperCase();else for(const [sy,c] of SYM_DETECT){if(t.includes(sy)){cur=c;break}}
  cur=cur||hint||"GBP";
  const c=t.replace(/(\d)[,  ](?=\d{3}(?!\d))/g,"$1").replace(/(\d)\.(?=\d{3}(?!\d))/g,"$1");   // 45,000 / 45.000 -> 45000
  const nums=[...c.matchAll(/(\d+(?:\.\d+)?)\s*([km])?(?![a-z])/gi)].map(m=>parseFloat(m[1])*(m[2]?(m[2].toLowerCase()==="k"?1e3:1e6):1)).filter(n=>n>0&&n<1e9).slice(0,2);
  if(!nums.length)return null;
  const per=/hour|\bhr\b|\/h\b/i.test(t)?"hour":/\bday|daily/i.test(t)?"day":/week/i.test(t)?"week":/month|\/mo\b/i.test(t)?"month":"year";
  return {cur,lo:Math.min(...nums),hi:Math.max(...nums),per};
}
const PER_YEAR={hour:1950,day:230,week:52,month:12,year:1};
const convertAmt=(n,from,to)=>(from===to||!rates[from]||!rates[to])?n:n/rates[from]*rates[to];
function workCur(){return currency!=="orig"?currency:((countries.find(c=>c.code===$("#country").value)||{}).currency||"GBP")}
function annualOf(j){const p=parseSalary(j.salary,j.cur_hint);return p?convertAmt(p.hi,p.cur,workCur())*PER_YEAR[p.per]:0}
function fmtMoney(n,cur){const s=CUR_SYM[cur]||(cur+" ");
  return s+(n>=1e6?(n/1e6).toFixed(1).replace(/\.0$/,"")+"m":n>=1e4?Math.round(n/1e3)+"k":n>=1e3?(n/1e3).toFixed(1).replace(/\.0$/,"")+"k":n>=100?Math.round(n):n.toFixed(2).replace(/\.00$/,""))}
function salaryHtml(j){
  if(!j.salary)return"";
  if(currency==="orig")return esc(j.salary);
  const p=parseSalary(j.salary,j.cur_hint);if(!p||p.cur===currency)return esc(j.salary);
  const lo=convertAmt(p.lo,p.cur,currency),hi=convertAmt(p.hi,p.cur,currency);
  const txt=(Math.round(lo)===Math.round(hi)?fmtMoney(lo,currency):fmtMoney(lo,currency)+"–"+fmtMoney(hi,currency))+(p.per!=="year"?" / "+p.per:"");
  return `<span title="Originally ${esc(j.salary)} · ${esc(ratesInfo)}">≈ ${esc(txt)}</span><span class="conv">from ${esc(p.cur)}</span>`;
}
function setCurrency(c,quiet){currency=c||"orig";savePref("currency",currency);$$(".cursel").forEach(s=>s.value=currency);
  $("#salmin").placeholder=`Min salary / year (${(CUR_SYM[workCur()]||workCur()+" ").trim()})`;render();
  if(!quiet)toast(currency==="orig"?"Showing salaries as listed":`Salaries shown in ${currency} — ${ratesInfo}`)}

// ============================================================= results
const TYPE_RE={fulltime:/full[\s-]?time|permanent/i,parttime:/part[\s-]?time/i,contract:/contract|freelance|temporary|\btemp\b|fixed[\s-]?term/i,
  internship:/\bintern\b|internship|placement|graduate (scheme|programme|program)|trainee|\bstage\b|stagiair|praktik|werkstudent|apprentice|summer analyst|\bco-?op\b/i};
function visible(list,isSaved){
  const f=$("#filter").value.toLowerCase().trim(),src=$("#srcfilter").value;
  const ex=$("#exclude").value.toLowerCase().split(",").map(s=>s.trim()).filter(Boolean);
  const salmin=+$("#salmin").value||0,hassal=$("#hassal").checked,posted=+$("#posted").value,jt=$("#jtype").value,rm=$("#remote").value;
  const cutoff=posted?dayStr(new Date(Date.now()-posted*864e5)):"";
  const terms=cvTerms();
  let out=list.filter(j=>{
    const hay=[j.title,j.company,j.location,j.type,(j.tags||[]).join(" "),j.desc].join(" ").toLowerCase();
    if(f&&!f.split(/\s+/).every(w=>hay.includes(w)))return false;
    if(ex.some(w=>j.title.toLowerCase().includes(w)))return false;
    if(src&&j.source!==src)return false;
    if(isSaved)return true;
    if($("#local").checked&&j.local_ok===false)return false;          // remote jobs that don't take people from your country
    if($("#strict").checked&&j.title_match===false)return false;      // every search word must be in the title
    const sal=annualOf(j);
    if(hassal&&!sal)return false;
    if(salmin&&sal&&sal<salmin)return false;
    if(cutoff&&j.date&&j.date<cutoff)return false;
    if(jt==="internship"){if(!TYPE_RE.internship.test(j.title+" "+(j.type||"")+" "+(j.duration||""))&&!/\binternship\b|\bplacement\b/i.test((j.desc||"").slice(0,600)))return false}
    else if(jt){const known=Object.values(TYPE_RE).some(re=>re.test(j.type||""));if(known&&!TYPE_RE[jt].test(j.type||""))return false}
    const df=$("#durfilter").value,dm=j.duration_m;
    if(df==="perm"&&dm!==1000)return false;
    if(df==="contract"&&!(dm&&dm<1000))return false;
    if(df==="short"&&!(dm&&dm<=6))return false;
    if(df==="mid"&&!(dm&&dm>6&&dm<=12))return false;
    if(df==="long"&&!(dm&&dm>12&&dm<500))return false;
    const isRemote=/remote/i.test(j.location+" "+j.type+" "+j.title)||j.remote;
    if(rm==="remote"&&!isRemote)return false;
    if(rm==="onsite"&&isRemote&&!/hybrid/i.test(hay))return false;
    if(rm==="hybrid"&&!/hybrid/i.test(hay)&&isRemote)return false;
    return true;
  });
  out.forEach(j=>j._m=matchPct(j,terms));
  const s=$("#sort").value;
  const newest=(a,b)=>(b.date||"").localeCompare(a.date||"");
  const durKey=(j,long)=>j.duration_m==null?(long?-1:1e9):j.duration_m;   // jobs that don't say go last
  if(s==="date")out.sort(newest);
  else if(s==="old")out.sort((a,b)=>(a.date||"9999").localeCompare(b.date||"9999"));
  else if(s==="salary_lo")out.sort((a,b)=>(annualOf(a)||1e12)-(annualOf(b)||1e12));
  else if(s==="dur_short")out.sort((a,b)=>durKey(a,false)-durKey(b,false)||newest(a,b));
  else if(s==="dur_long")out.sort((a,b)=>durKey(b,true)-durKey(a,true)||newest(a,b));
  else if(s==="title")out.sort((a,b)=>a.title.localeCompare(b.title));
  else if(s==="salary")out.sort((a,b)=>annualOf(b)-annualOf(a));
  else if(s==="dist")out.sort((a,b)=>(a.dist_km??1e9)-(b.dist_km??1e9)||(b.date||"").localeCompare(a.date||""));
  else if(s==="company")out.sort((a,b)=>a.company.localeCompare(b.company));
  else if(s==="cv")out.sort((a,b)=>(b._m||0)-(a._m||0)||(b.date||"").localeCompare(a.date||""));
  else out.sort((a,b)=>(b.score||0)-(a.score||0)||(b.date||"").localeCompare(a.date||""));
  return out;
}
function fmtDist(km){const u=unit(),v=u==="km"?km:km/1.609;return v<1?`under 1 ${u} away`:`${v<10?v.toFixed(1):Math.round(v)} ${u} away`}
function ago(d){if(!d)return"";const n=Math.round((Date.now()-new Date(d))/864e5);return n<=0?"today":n===1?"1 day ago":n+" days ago"}
function tracked(url){return saved.find(s=>s.url===url)}
// ---- results come in pages (25 / 50 / 100 / all), so the list never gets huge
let page=1;
const perPage=()=>+$("#perpage").value||0;           // 0 = all on one page
function drawPager(total){
  const size=perPage(),pages=size?Math.max(1,Math.ceil(total/size)):1,el=$("#pager");
  el.hidden=pages<=1;if(el.hidden)return;
  const nums=[];for(let p=1;p<=pages;p++)if(p===1||p===pages||Math.abs(p-page)<=1)nums.push(p);else if(nums[nums.length-1]!=="…")nums.push("…");
  const from=(page-1)*size+1,to=Math.min(total,page*size);
  el.innerHTML=`<span class="muted">Showing ${from}–${to} of ${total}</span><span class="pagebtns">
    <button class="pill line sm" data-page="${page-1}" ${page>1?"":"disabled"} aria-label="Previous page">‹ Prev</button>
    ${nums.map(p=>p==="…"?`<span class="muted">…</span>`:`<button class="pill line sm ${p===page?"on":""}" data-page="${p}" ${p===page?'aria-current="page"':""}>${p}</button>`).join("")}
    <button class="pill line sm" data-page="${page+1}" ${page<pages?"":"disabled"} aria-label="Next page">Next ›</button></span>`;
  $$("#pager [data-page]").forEach(b=>b.onclick=()=>{goPage(+b.dataset.page)});
}
function goPage(p){page=p;render();$("#restitle").scrollIntoView({behavior:"smooth",block:"start"})}
function render(){
  if(tab!=="search")return;
  const all=visible(results,false),size=perPage();
  const pages=size?Math.max(1,Math.ceil(all.length/size)):1;page=Math.max(1,Math.min(page,pages));
  const start=size?(page-1)*size:0,items=size?all.slice(start,start+size):all;
  drawPager(all.length);
  if(!items.length&&searching){$("#list").innerHTML=Array.from({length:5},()=>`<li class="skel"><i style="width:24px"></i><div><i class="big"></i><i class="sm"></i></div><div><i></i></div></li>`).join("");return}
  if(!items.length){$("#list").innerHTML=`<li class="empty"><span class="serif">${results.length?"Nothing matches those filters":"Begin your search"}</span>${results.length?"Try loosening a filter above.":"Type a job above, try “Any job”, or let your CV do the work."}
    <div class="emptyacts">${results.length?`<button class="pill line sm" id="clearfilters">Clear the filters</button>`:`<button class="pill line sm" id="emptyany">Show any job near me</button>${(profile.jobs||[]).length?`<button class="pill dark sm" id="emptycv">✦ Match jobs to my CV</button>`:`<button class="pill line sm" id="emptyprof">Add my CV first</button>`}`}</div></li>`;
    const on=(id,fn)=>{const b=document.getElementById(id);if(b)b.onclick=fn};
    on("clearfilters",clearFilters);on("emptycv",()=>$("#matchbtn").click());on("emptyprof",()=>setTab("profile"));
    on("emptyany",()=>{if(!anyMode)$("#anybtn").click();cvMode=false;internMode=false;runSearch()});return}
  $("#list").innerHTML=items.map((j,i)=>{const t=tracked(j.url);return `<li class="jobrow">
    <div class="num">${String(start+i+1).padStart(2,"0")}.</div>
    <div><h3 data-href="${esc(j.url)}" translate="no">${esc(j.title)}</h3>
      <div class="meta"><b translate="no">${esc(j.company)}</b><span translate="no">${esc(j.location)}</span>${j.dist_km!=null?`<span class="dist" title="Distance from ${esc($("#where").value)}">📍 ${fmtDist(j.dist_km)}</span>`:""}${j.salary?`<span class="sal">${salaryHtml(j)}</span>`:""}${j.duration?`<span class="dur" title="How long the job lasts, from the advert">⏳ ${esc(j.duration)}</span>`:""}${j.type?`<span>${esc(j.type)}</span>`:""}<span>${esc(ago(j.date))}</span><span class="tag">${esc(j.source)}</span>${j._m!=null&&(j._m>=20||$("#sort").value==="cv")?`<span class="match" title="How well this fits your CV">${j._m}% match</span>`:""}${t?`<span class="tag" style="border-color:var(--accent);color:var(--accent)">${esc(t.status)}</span>`:""}</div></div>
    <div class="acts">
      ${t?`<button class="pill line sm on" data-unsave="${i}" title="On your tracker — click to remove it">★ Saved</button>`:`<button class="pill line sm" data-save="${i}" title="Add to your tracker">☆ Save</button>`}
      ${t&&APPLIED.includes(t.status)?`<button class="pill line sm on" data-unapply="${i}" title="Click if you haven't applied after all — it goes back to Saved">✓ ${esc(t.status)}</button>`:`<button class="pill line sm" data-applied="${i}" title="Add to your tracker as applied">✓ Mark applied</button>`}
      <button class="iconbtn copylink" data-copy="${esc(j.url)}" data-tip="Copy link">⧉</button>
      <button class="pill line sm" data-href="${esc(j.url)}" data-tip="Open the advert in your browser">Open ↗</button>
      <button class="pill accent sm" data-apply="${i}" data-tip="Open in Chrome and autofill with your profile">${PHONE?"Apply ↗":"⚡ Easy apply"}</button>
    </div>
    ${j.desc?`<details><summary>Preview</summary><p>${esc(j.desc)}…</p></details>`:""}
  </li>`}).join("");
  $$("[data-save]").forEach(b=>b.onclick=()=>track("save",items[b.dataset.save]));
  $$("[data-applied]").forEach(b=>b.onclick=()=>track("applied",items[b.dataset.applied]));
  $$("[data-unsave]").forEach(b=>b.onclick=()=>untrack(items[b.dataset.unsave]));
  $$("[data-unapply]").forEach(b=>b.onclick=()=>unapply(items[b.dataset.unapply]));
  $$("[data-apply]").forEach(b=>b.onclick=()=>easyApply(items[b.dataset.apply]));
}
["#filter","#exclude","#sort","#srcfilter","#salmin","#hassal","#posted","#jtype","#remote","#durfilter","#local","#strict"].forEach(s=>$(s).addEventListener("input",()=>{pref("f_exclude",$("#exclude").value);pref("f_sort",$("#sort").value);page=1;render()}));
$("#perpage").value=pref("perpage")||"25";
$("#perpage").addEventListener("change",()=>{pref("perpage",$("#perpage").value);page=1;render()});
// "Clear the filters" (shown when filters hide every result)
function clearFilters(){$("#posted").value="0";$("#jtype").value="";$("#remote").value="";$("#salmin").value="";$("#hassal").checked=false;
  $("#strict").checked=false;$("#filter").value="";$("#exclude").value="";$("#durfilter").value="";$("#srcfilter").value="";
  ["f_posted","f_jtype","f_remote","f_exclude"].forEach(k=>pref(k,""));render();toast("Filters cleared")}
// 🎓 Internships: internship filter on, then search what's typed (or every field)
// the 🎓 button searches for internships (internMode); the Job type filter itself only hides
$("#internbtn").onclick=()=>{$("#jtype").value="internship";pref("f_jtype","internship");
  if(!$("#q").value.trim()&&!anyMode)$("#anybtn").click();
  cvMode=false;internMode=true;runSearch().finally(()=>{internMode=false});toast("Showing internships, placements and graduate schemes")};

async function track(action,job){
  const j={...job};delete j._m;
  await trackerChange(action==="applied"?`marking “${job.title}” applied`:`saving “${job.title}”`,async()=>{saved=await post("/api/saved",{action,job:j})});
  toast(action==="applied"?"Marked as applied — nice one! 🎉":"Saved to your tracker",UNDO);refreshTracked();
}
function refreshTracked(){render();drawStrip();if(tab==="tracker")drawBoard();drawStarted()}
// "★ Saved" clicked again: off the tracker (with Undo, since it may hold notes or an application)
async function untrack(job){
  const old=tracked(job.url);if(!old)return;
  await trackerChange(`removing “${old.title}”`,async()=>{saved=await post("/api/saved",{action:"remove",job:{url:old.url}})});refreshTracked();
  toast(APPLIED.includes(old.status)?`Removed “${old.title}” from your tracker, application included`:`Removed “${old.title}” from saved jobs`,UNDO);
}
// "✓ Applied" clicked again: back to Saved
async function unapply(job){
  const old=tracked(job.url);if(!old)return;
  await trackerChange(`un-applying “${old.title}”`,async()=>{saved=await post("/api/saved",{action:"unapply",job:{url:old.url}})});refreshTracked();
  toast(`“${old.title}” is back to Saved`,UNDO);
}
async function easyApply(job){
  if(PHONE){                                           // phone: open the advert here and track it as "Applying"
    window.open(job.url,"_blank","noopener");
    const j={...job,status:"Applying"};delete j._m;
    await trackerChange(`Easy apply on “${job.title}”`,async()=>{saved=await post("/api/saved",{action:"save",job:j})});refreshTracked();
    toast("Opened — it's on your Tracker as Applying");return;
  }
  if(!profile.email&&!profile.first_name)profile=(await get("/api/profile")).profile||{};
  if(!profile.email&&!profile.first_name){toast("Fill in your Profile first");setTab("profile");return}
  const j={...job};delete j._m;
  const r=await trackerChange(`Easy apply on “${job.title}”`,async()=>{const r=await post("/api/apply",{job:j});if(r.saved)saved=r.saved;return r});refreshTracked();
  toast(r.chrome?"Opened in Chrome — click ⚡ Fill application on the form":"Opened in your browser — use Chrome with the extension to autofill");
}
function csv(rows,cols,name){post("/api/export",{rows,cols,name}).then(r=>{toast("Saved to "+r.path);openUrl(r.path)})}
$("#csv").onclick=()=>{const rows=visible(results,false);if(!rows.length)return toast("Nothing to export");csv(rows,["title","company","location","salary","type","date","source","url"],"jobs-search")};
$("#tcsv").onclick=()=>{if(!saved.length)return toast("Nothing to export");csv(saved,["title","company","location","salary","status","saved_on","applied_on","follow_up","source","url","notes"],"applications")};
