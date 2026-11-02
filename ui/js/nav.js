// ============================================================= welcome
const CHEERS=["Every application is a step closer — today could be the day.","Your next chapter is out there. Let's go find it.",
 "Small steps every day add up to big moves.","You bring something no one else can. Show them.","Consistency beats luck. You've got this.",
 "The right role is looking for someone exactly like you.","One great application beats ten rushed ones — take your time.",
 "Rejections are redirections. Keep going.","Fresh day, fresh listings, fresh chances.","You're closer than you think.",
 "Back at it — that's what winners do.","Make today count: one more application, one more door.",
 "Your skills are in demand. Let's put them in front of the right people.","Progress, not perfection.",
 "Good things come to those who apply.","Keep showing up — momentum is building.","Bet on yourself today.",
 "The best time to apply was yesterday. The next best time is now."];
function drawWelcome(){
  const name=(profile.first_name||"").trim();
  $("#hello").innerHTML=name?`Welcome back, ${esc(name)}`:"Find Your Next Role";
  const where=[profile.city,(countries.find(c=>c.code===$("#country").value)||{}).name].filter(Boolean).join(" · ");
  $("#herosub").textContent=[where,new Date().toLocaleDateString(undefined,{day:"numeric",month:"long",year:"numeric"})].filter(Boolean).join("  ·  ");
  $("#cheer").textContent=CHEERS[Math.floor(Math.random()*CHEERS.length)];
}

// ============================================================= tabs
const TAB_NAMES={search:"Search",tracker:"Tracker",progress:"Progress",profile:"Profile"};
function setTab(t){const changed=tab!==t;tab=t;$$(".navlinks .tab").forEach(b=>{b.classList.toggle("on",b.dataset.tab===t);b.setAttribute("aria-current",b.dataset.tab===t?"page":"false")});
  $$("section.view").forEach(s=>s.classList.toggle("on",s.id==="v-"+t));
  // only Search needs the big header; other tabs get a slim bar so the page starts right away
  document.querySelector(".hero").classList.toggle("compact",t!=="search");
  $("#strip").style.display=t==="search"||t==="progress"?"":"none";
  document.title=`${TAB_NAMES[t]} · jobslop`;
  if(changed&&t!=="search")window.scrollTo({top:0,behavior:"instant"});
  if(t==="profile")loadProfile();if(t==="tracker")drawBoard();if(t==="progress")drawProgress();if(t==="search"){render();drawStarted()}}
$$(".navlinks .tab").forEach(b=>b.onclick=()=>setTab(b.dataset.tab));
$("#strip").onclick=()=>{setTab("progress");$("#v-progress").scrollIntoView({behavior:"smooth"})};
$("#strip").style.cursor="pointer";
