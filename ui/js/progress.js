// ============================================================= stats
function appliedDate(j){if(j.applied_on)return j.applied_on;if(j.dates&&j.dates.Applied)return j.dates.Applied;if(APPLIED.includes(j.status))return j.saved_on||"";return""}
function stats(){
  const t=new Date(),today=todayStr(),days=saved.map(appliedDate).filter(Boolean);
  const mon=new Date(t);mon.setDate(t.getDate()-((t.getDay()+6)%7));const weekStart=dayStr(mon),monthKey=today.slice(0,7);
  const count=pred=>days.filter(pred).length;
  const set=new Set(days);let streak=0,d=new Date(t);if(!set.has(today))d.setDate(d.getDate()-1);
  while(set.has(dayStr(d))){streak++;d.setDate(d.getDate()-1)}
  const reached=s=>saved.filter(j=>j.status===s||(j.dates&&j.dates[s])).length;
  const applied=days.length,interviews=saved.filter(j=>j.status==="Interview"||j.status==="Offer"||(j.dates&&j.dates.Interview)).length;
  const offers=reached("Offer"),rejected=reached("Rejected");
  const first=days.slice().sort()[0];const weeks=first?Math.max(1,(t-new Date(first))/(7*864e5)):1;
  return {today:count(x=>x===today),week:count(x=>x>=weekStart),month:count(x=>x.startsWith(monthKey)),total:applied,streak,interviews,offers,rejected,
    tracked:saved.length,savedOnly:saved.filter(j=>(j.status||"Saved")==="Saved").length,
    irate:applied?Math.round(100*interviews/applied):0,rrate:applied?Math.round(100*(interviews+rejected)/applied):0,perweek:applied?(applied/weeks).toFixed(1):"0",
    searches:+(pref("searches_"+today)||0)};
}
function drawStrip(){const s=stats();$("#st_today").textContent=s.today;$("#st_month").textContent=s.month;$("#st_total").textContent=s.total;$("#st_streak").textContent=s.streak;if(tab==="progress")drawProgress()}
function drawProgress(){
  const s=stats();
  const TILE_TIPS={"Day streak":"Days in a row you've applied to at least one job","Interview rate":"Interviews out of the applications you've sent",
    "Response rate":"How often you hear back: interviews plus rejections, out of applications","This week":"Applications since Monday",
    "All time":"Every application on your tracker","Offers":"Jobs that reached the Offer column"};
  const tile=(n,l,sub)=>`<div class="tile" ${TILE_TIPS[l]?`data-tip="${esc(TILE_TIPS[l])}"`:""}><div class="n">${n}</div><div class="l">${l}</div>${sub?`<div class="s">${sub}</div>`:""}</div>`;
  $("#tiles").innerHTML=tile(s.today,"Applied today",s.searches?`${s.searches} search${s.searches>1?"es":""} today`:"")+tile(s.week,"This week",`${s.perweek} a week on average`)+
    tile(s.month,"This month",new Date().toLocaleDateString(undefined,{month:"long"}))+tile(s.total,"All time",`${s.tracked} jobs tracked`)+
    tile(s.streak,"Day streak",s.streak?"Keep it going!":"Apply today to start one")+tile(s.irate+"%","Interview rate",`${s.interviews} interview${s.interviews===1?"":"s"}`)+
    tile(s.rrate+"%","Response rate","interviews + rejections")+tile(s.offers,"Offers",s.offers?"🥂":"Your first is coming");
  // last 30 days
  const counts={};saved.map(appliedDate).filter(Boolean).forEach(d=>counts[d]=(counts[d]||0)+1);
  const ds=[];for(let i=29;i>=0;i--){const d=new Date();d.setDate(d.getDate()-i);ds.push(dayStr(d))}
  const max=Math.max(1,...ds.map(d=>counts[d]||0));
  $("#bars").innerHTML=ds.map(d=>{const n=counts[d]||0;return `<div class="${n?"":"zero"}" style="height:${n?Math.max(6,100*n/max):2}%" title="${d}: ${n} application${n===1?"":"s"}"></div>`}).join("");
  const fmt=d=>new Date(d).toLocaleDateString(undefined,{day:"numeric",month:"short"});
  $("#barlabels").innerHTML=`<span>${fmt(ds[0])}</span><span>${fmt(ds[15])}</span><span>Today</span>`;
  // funnel
  const fun=[["Tracked",s.tracked],["Applied",s.total],["Interview",s.interviews],["Offer",s.offers]],top=Math.max(1,s.tracked);
  $("#funnel").innerHTML=fun.map(([l,n])=>`<div class="row"><span>${l}</span><div class="bar"><i style="width:${100*n/top}%"></i></div><b style="text-align:right">${n}</b></div>`).join("");
  // companies
  const co={};saved.filter(j=>appliedDate(j)).forEach(j=>{if(j.company)co[j.company]=(co[j.company]||0)+1});
  const tops=Object.entries(co).sort((a,b)=>b[1]-a[1]).slice(0,6);
  $("#topco").innerHTML=tops.length?tops.map(([c,n])=>`<div class="row"><span>${esc(c)}</span><b>${n}</b></div>`).join(""):`<p class="muted" style="font-size:13px">Apply to a few jobs to see this.</p>`;
  // follow ups
  const today=todayStr(),due=saved.filter(j=>j.follow_up&&!["Offer","Rejected","Not interested"].includes(j.status)).sort((a,b)=>a.follow_up.localeCompare(b.follow_up)).slice(0,6);
  $("#followups").innerHTML=due.length?due.map(j=>`<div class="row"><span>${esc(j.title)} · ${esc(j.company)}</span><b style="color:${j.follow_up<=today?"var(--warn)":"inherit"}">${esc(j.follow_up)}</b></div>`).join(""):`<p class="muted" style="font-size:13px">Set a follow-up date on an application (Edit) to be reminded here.</p>`;
  drawRing();
}
function drawRing(){const s=stats(),goal=+(pref("goal")||10);$("#goal").value=goal;const p=Math.min(1,s.week/goal),C=2*Math.PI*50;
  $("#ring").innerHTML=`<circle cx="60" cy="60" r="50" fill="none" stroke="var(--line)" stroke-width="10"/><circle cx="60" cy="60" r="50" fill="none" stroke="var(--accent)" stroke-width="10" stroke-linecap="round" stroke-dasharray="${C*p} ${C}" transform="rotate(-90 60 60)"/><text x="60" y="68" text-anchor="middle" font-size="24" fill="var(--text)" font-family="Italiana,serif">${Math.round(p*100)}%</text>`;
  $("#goaltext").textContent=`${s.week} / ${goal}`}
$("#goal").addEventListener("input",()=>{pref("goal",$("#goal").value);drawRing()});
