(async()=>{
  try{
    // preferences saved with the app win over the window's own storage
    try{const sp=await get("/api/prefs");Object.entries(sp).forEach(([k,v])=>pref(k,v))}catch(e){}
    applyTheme();
    const curOpts=`<option value="orig">Salaries as listed</option>`+CUR_LIST.map(c=>`<option value="${c}">${c} ${(CUR_SYM[c]||"").trim()}</option>`).join("");
    $$(".cursel").forEach(s=>{s.innerHTML=curOpts;s.onchange=()=>setCurrency(s.value)});
    await Promise.all([loadCountries(),loadRates()]);
    $("#ratesnote").textContent=ratesInfo?`Currency conversion uses live ${ratesInfo}.`:"";
    drawMiles(+(pref("f_miles")||15));
    try{profile=(await get("/api/profile")).profile||{}}catch(e){}
    if(!pref("country")&&profile.country){const hit=countryFromText(profile.country);if(hit)$("#country").value=hit.code}
    setCurrency(pref("currency")||"orig",true);
    drawWelcome();await Promise.all([loadKeys(),loadSaved(),loadExt(),loadTerms(),loadPlugins()]);drawStarted();
    setInterval(loadExt,60000);
  }finally{hideSplash()}
  if(PHONE){["#extchip","#csv","#tcsv"].forEach(s=>{const e=$(s);if(e)e.classList.add("pc-only")})}
  else{loadPhone();if(pref("onboarded")!=="1")setTimeout(startOnboarding,550);   // first run: show the welcome tour
    setTimeout(()=>loadUpdate(false),2500)}                                      // a new version? (checked quietly)
})();
