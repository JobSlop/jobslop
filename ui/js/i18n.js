// ============================================================= language
// The screen is written in English. With another language chosen, every piece of text whose English
// is in the language pack is swapped for its translation — also text drawn later (lists, messages),
// which a watcher on the page catches. Text with values in it is matched with {0}, {1}… standing in for
// them: "Found {0} jobs" -> "{0} vacatures gevonden". Anything marked translate="no" (job titles,
// company names) is never touched. t("text") gives the translation in code.
let LANG="en",WORDS={},PATTERNS=[],LANGS=[{code:"en",name:"English",enabled:true}];
const I18N_ATTRS=["placeholder","title","data-tip","aria-label"];
const normText=s=>String(s).replace(/\s+/g," ").trim();
function t(s){
  if(LANG==="en"||s==null)return s;
  const k=normText(s);if(!k)return s;
  if(WORDS[k])return WORDS[k];
  for(const [re,out] of PATTERNS){const m=k.match(re);if(m)return out.replace(/\{(\d+)\}/g,(_,i)=>m[+i+1]??"")}
  const icon=k.match(/^([^\p{L}\p{N}"“(]+)\s(.+)$/u);                  // "🎮 Studios": an icon, then known text
  if(icon){const rest=t(icon[2]);if(rest!==icon[2])return icon[1]+" "+rest}
  return s;
}
function compileWords(words){
  WORDS={};PATTERNS=[];
  for(const [en,tr] of Object.entries(words||{})){
    const k=normText(en);
    if(/\{\d+\}/.test(k)){
      const re=new RegExp("^"+k.replace(/[.*+?^$()|[\]\\]/g,"\\$&").replace(/\\?\{(\d+)\\?\}/g,"(.+?)")+"$");
      PATTERNS.push([re,tr]);
    }else WORDS[k]=tr;
  }
  PATTERNS.sort((a,b)=>b[0].source.length-a[0].source.length);       // most specific first
}
const noTranslate=el=>!el||el.closest('[translate="no"],script,style,textarea,code');
function trNode(n){
  if(n.nodeType!==3||noTranslate(n.parentElement))return;
  if(n.__tr===undefined||n.nodeValue!==n.__tr)n.__en=n.nodeValue;     // new text from the app: remember its English
  const en=n.__en,core=normText(en);
  const out=core&&LANG!=="en"?en.replace(en.trim(),t(core)):en;
  n.__tr=out;if(n.nodeValue!==out)n.nodeValue=out;
}
function trAttrs(el){
  if(el.nodeType!==1||noTranslate(el))return;
  el.__en=el.__en||{};el.__tr=el.__tr||{};
  for(const a of I18N_ATTRS){
    if(!el.hasAttribute(a))continue;
    const v=el.getAttribute(a);
    if(el.__tr[a]===undefined||v!==el.__tr[a])el.__en[a]=v;
    const out=LANG==="en"?el.__en[a]:t(el.__en[a]);
    el.__tr[a]=out;if(v!==out)el.setAttribute(a,out);
  }
}
function trTree(root){
  if(!root)return;
  if(root.nodeType===3)return trNode(root);
  if(root.nodeType!==1)return;
  trAttrs(root);
  const w=document.createTreeWalker(root,NodeFilter.SHOW_TEXT|NodeFilter.SHOW_ELEMENT);
  for(let n=w.nextNode();n;n=w.nextNode())n.nodeType===3?trNode(n):trAttrs(n);
}
let i18nObserver=null;
function watchTranslations(){
  if(i18nObserver)return;
  i18nObserver=new MutationObserver(list=>{
    for(const m of list){
      if(m.type==="characterData")trNode(m.target);
      else if(m.type==="attributes")trAttrs(m.target);
      else m.addedNodes.forEach(trTree);
    }});
  i18nObserver.observe(document.body,{subtree:true,childList:true,characterData:true,attributes:true,attributeFilter:I18N_ATTRS});
}
async function loadLanguage(code){
  const r=await get("/api/i18n"+(code?"?lang="+encodeURIComponent(code):""));
  LANG=r.lang||"en";LANGS=r.languages||LANGS;compileWords(r.words);
  document.documentElement.lang=LANG;
  trTree(document.body);watchTranslations();
  if(typeof drawLanguagePicker==="function")drawLanguagePicker();
  if(document.title.includes("·")&&typeof setTab==="function")setTab(tab);   // the window title
}
// the language picker (Settings and the welcome tour): a language whose pack is off gets switched on
function drawLanguagePicker(){
  $$(".langsel").forEach(sel=>{
    sel.innerHTML=LANGS.map(l=>`<option value="${esc(l.code)}">${esc(l.name)}</option>`).join("");
    sel.value=LANG;
    sel.onchange=()=>chooseLanguage(sel.value);
  });
}
async function chooseLanguage(code){
  const l=LANGS.find(x=>x.code===code)||{code:"en"};
  if(l.plugin&&!l.enabled){
    plugins=await post("/api/plugins",{id:l.plugin,enabled:true});
    if(typeof drawPlugins==="function"){drawPlugins();jobslop.sync(plugins.plugins)}
    if(typeof loadBoards==="function")await loadBoards();
  }
  savePref("lang",code);
  await loadLanguage(code);
  toast(t("Language changed"));
}
