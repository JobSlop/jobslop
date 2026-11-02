// ============================================================= search form
async function loadCountries(){countries=await get("/api/countries");
  $("#country").innerHTML=countries.map(c=>`<option value="${c.code}">${esc(c.name)}</option>`).join("");
  $("#country").value=pref("country")||"GB";}
$("#country").onchange=()=>{setCountry($("#country").value)};
$("#anybtn").onclick=()=>{anyMode=!anyMode;$("#anybtn").classList.toggle("on",anyMode);
  $("#q").disabled=anyMode;$("#q").placeholder=anyMode?"Any job — showing everything nearby":"What job? e.g. data analyst — commas for several"};
// ---- country helpers
const COUNTRY_ALIAS={uk:"GB","u.k.":"GB",britain:"GB","great britain":"GB",england:"GB",scotland:"GB",wales:"GB","northern ireland":"GB",
  usa:"US",us:"US","u.s.":"US",america:"US","united states of america":"US",deutschland:"DE",holland:"NL","the netherlands":"NL",uae:"AE"};
function countryFromText(t){const s=(t||"").trim().toLowerCase();if(!s)return null;
  return countries.find(c=>c.name.toLowerCase()===s||c.code.toLowerCase()===s||COUNTRY_ALIAS[s]===c.code)||null}
function setCountry(code){if(!countries.some(c=>c.code===code))return false;$("#country").value=code;pref("country",code);drawSources();drawWelcome();setCurrency(currency,true);return true}

// ---- "Where?" takes a town, postcode or full address; the app works out the town, postcode and country
let whereLoc=null;
async function readWhere(){
  const w=$("#where").value.trim();
  if(!w){whereLoc=null;showWhere();return null}
  try{whereLoc=await get("/api/place?"+new URLSearchParams({q:w,country:$("#country").value}))}catch(e){whereLoc=null}
  showWhere();return whereLoc}
function showWhere(){
  const h=$("#wherehint"),w=$("#where").value.trim().toLowerCase(),l=whereLoc;
  if(!w||!l||!l.town){h.hidden=true;return}
  h.textContent=l.found?`📍 Searching around ${l.label}`:`📍 “${l.town}” isn't in the offline town list — boards will be asked for it as typed`;
  h.hidden=l.found&&l.town.toLowerCase()===w&&!l.postcode}          // plain town: nothing to explain
function followWhereCountry(l){
  if(l&&l.explicit_country&&l.country_code&&l.country_code!==$("#country").value){
    if(setCountry(l.country_code))toast(`Country switched to ${$("#country").selectedOptions[0].text} to match “${$("#where").value.trim()}”`)}}
$("#where").addEventListener("change",async()=>followWhereCountry(await readWhere()));
$("#where").addEventListener("input",()=>{$("#wherehint").hidden=true});

// ---- 📍 Mine: the whole profile address (street, town, postcode, country) -> town + postcode + country
$("#locbtn").onclick=()=>withSpinner($("#locbtn"),"",async()=>{
  profile=(await get("/api/profile")).profile||{};
  const addr=[profile.address1,profile.address2,profile.city,profile.county,profile.postcode].map(x=>(x||"").trim()).filter(Boolean);
  if(!addr.length&&!profile.country){toast("Add your address or town in Profile first");setTab("profile");return}
  let hit=countryFromText(profile.country);
  const l=addr.length?await get("/api/place?"+new URLSearchParams({q:[...addr,profile.country].filter(Boolean).join(", "),country:hit?hit.code:$("#country").value})):null;
  if(l&&l.found){
    $("#where").value=[l.town,l.postcode].filter(Boolean).join(", ");
    hit=countries.find(c=>c.code===l.country_code)||hit;
  }else{
    $("#where").value=profile.city||"";
    if(!hit&&profile.city){const g=await get("/api/geocode?q="+encodeURIComponent([profile.city,profile.country].filter(Boolean).join(", ")));
      if(!g.error)hit=countries.find(c=>c.code===g.country_code)||null}
  }
  if(hit)setCountry(hit.code);
  await readWhere();
  toast(`Location set to ${l&&l.found?l.label:[profile.city,hit?hit.name:profile.country].filter(Boolean).join(", ")}`)});

// ---- distance units
const UNIT_OPTS={mi:[5,10,15,25,50,100],km:[5,10,25,40,80,150]};
const unit=()=>pref("unit")||"mi";
const toMiles=(n,u)=>u==="km"?n/1.609:n, fromMiles=(m,u)=>u==="km"?m*1.609:m;
function drawMiles(keepMiles){const u=unit(),cur=keepMiles||+$("#miles").value||15;
  let best=UNIT_OPTS[u][0];UNIT_OPTS[u].forEach(v=>{if(Math.abs(toMiles(v,u)-cur)<Math.abs(toMiles(best,u)-cur))best=v});
  $("#miles").innerHTML=UNIT_OPTS[u].map(v=>`<option value="${Math.max(1,Math.round(toMiles(v,u)))}" ${v===best?"selected":""}>+${v} ${u}</option>`).join("");
  $("#setunit").value=u;}
$("#setunit").onchange=()=>{savePref("unit",$("#setunit").value);drawMiles();render();toast(`Distances now in ${unit()==="km"?"kilometres":"miles"}`)};
