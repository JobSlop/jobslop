// jobslop autofill - recognises application form fields and fills them from your profile.
// It never submits anything: you always check the form and press submit yourself.
(() => {
  if (window.__jobFinderAutofill) return;
  window.__jobFinderAutofill = true;
  const TOP = window === window.top;

  const send = (msg) => new Promise((res) => {
    try { chrome.runtime.sendMessage(msg, (r) => { void chrome.runtime.lastError; res(r); }); }
    catch (e) { res(null); }
  });

  // ---- which profile value belongs in which field (order matters: first match wins)
  // Labels are recognised in English (UK + US), Dutch, Danish, German, French, Spanish, Portuguese,
  // Italian, Swedish and Polish.
  const RULES = [
    ["email", /e[- ]?mail|courriel|correo|correio|e-?post\b/, ["email"]],
    ["linkedin", /linked\s?in/],
    ["github", /github/],
    ["website", /website|portfolio|personal (site|url|page)|\burl\b|webside|hjemmeside|webstek|homepage|site web|sitio web|p[áa]gina web|sito web/, ["url"]],
    ["phone_country", /country (dial(l?ing)? )?code|dial(l?ing)? code|phone (country|prefix)|landcode|landekode|landesvorwahl|indicatif|c[óo]digo (de )?pa[íi]s|prefisso/],
    ["phone", /phone|mobile|telephone|\btel\b|contact number|\bcell\b|telefoon|mobiel|telefonnummer|telefon|mobil|t[ée]l[ée]phone|portable|tel[ée]fono|celular|m[óo]vil|telefone|telem[óo]vel|cellulare|numer telefonu/, ["tel", "tel-national"]],
    ["name_prefix", /tussenvoegsel|voorvoegsel/],
    ["middle_name", /middle\s*name|middle\s*initial|\bm\.?\s?i\.?\b(?!\w)|other (given|first) names?|mellemnavn|zweiter vorname|deuxi[èe]me pr[ée]nom|segundo nombre/, ["additional-name"]],
    ["first_name", /first\s*name|given\s*name|forename|\bfname\b|preferred name|voornaam|roepnaam|fornavn|vorname|pr[ée]nom|\bnombre\b(?!\s*(completo|de la empresa|de usuario))|\bnome\b(?!\s*completo)|f[öo]rnamn|imi[ęe](?! i nazwisko)/, ["given-name"]],
    ["last_name", /last\s*name|surname|family\s*name|\blname\b|achternaam|familienaam|efternavn|nachname|familienname|nom de famille|\bnom\b(?!\s*(complet|de l))|apellidos?|sobrenome|cognome|efternamn|nazwisko/, ["family-name"]],
    ["postcode", /post\s*code|postal|\bzip\b|postcode|postnummer|postnr|\bplz\b|postleitzahl|code postal|c[óo]digo postal|\bcap\b|\bcep\b|kod pocztowy/, ["postal-code"]],
    ["address2", /address\s*(line)?\s*2|apartment|\bflat\b|suite|\bapt\b|toevoeging|adresse\s*2|direcci[óo]n\s*2|complemento/, ["address-line2"]],
    ["city", /\bcity\b|\btown\b|woonplaats|\bplaats\b|\bstad\b|bynavn|\bstadt\b|\bort\b|wohnort|\bville\b|ciudad|localidad|cidade|citt[àa]|miejscowo|\bmiasto\b/, ["address-level2"]],
    ["county", /\bcounty\b|\bregion\b|\bstate\b|province|provincie|provins|bundesland|r[ée]gion|d[ée]partement|provincia|\bestado\b|wojew[óo]dztwo|kommune/, ["address-level1"]],
    ["country", /country|\bland\b|\bpays\b|pa[íi]s|paese|\bkraj\b/, ["country", "country-name"]],
    ["address1", /address|street|\badres\b|straat|adresse|\bgade\b|\bvej\b|stra[ßs]e|direcci[óo]n|\bcalle\b|endere[çc]o|indirizzo|\bulica\b/, ["address-line1", "street-address"]],
    ["current_company", /current (company|employer)|\bemployer\b|\bcompany\b|organi[sz]ation name|most recent (company|employer)|werkgever|bedrijf|organisatie|arbejdsgiver|virksomhed|\bfirma\b|arbeitgeber|unternehmen|employeur|entreprise|\bempresa\b|azienda|pracodawca/, ["organization"]],
    ["current_title", /current (job )?(title|role|position)|job title|most recent (title|role)|headline|functietitel|huidige functie|\bfunctie\b|stillingsbetegnelse|jobtitel|\bstilling\b|berufsbezeichnung|aktuelle position|intitul[ée] du poste|poste actuel|\bpuesto\b|\bcargo\b|t[íi]tulo del puesto|stanowisko/, ["organization-title"]],
    ["salary", /salary|pay expectation|compensation|desired pay|expected pay|salaris|gewenst salaris|l[øo]nforventning|\bl[øo]n\b|gehalt|gehaltsvorstellung|salaire|pr[ée]tentions|salario|sal[áa]rio|retribuzione|wynagrodzenie/],
    ["notice_period", /notice period|when can you start|start date|availability to start|earliest start|opzegtermijn|beschikbaar per|beschikbaarheid|opsigelse|tiltr[æa]delse|k[üu]ndigungsfrist|eintrittsdatum|fr[üu]hester eintritt|pr[ée]avis|disponibilit[ée]|preaviso|disponibilidad|aviso pr[ée]vio|okres wypowiedzenia/],
    ["years_experience", /years of (relevant |professional )?experience|how many years|jaren (werk)?ervaring|aantal jaren|[åa]rs erfaring|berufserfahrung|jahre erfahrung|ann[ée]es d.exp[ée]rience|a[ñn]os de experiencia|anos de experi[êe]ncia|anni di esperienza|lata do[śs]wiadczenia/],
    ["highest_qualification", /highest (level of )?(education|qualification|degree)|qualification|degree level|education level|opleidingsniveau|hoogst genoten opleiding|\bopleiding\b|uddannelsesniveau|h[øo]jeste uddannelse|\buddannelse\b|schulabschluss|bildungsabschluss|\babschluss\b|niveau d.[ée]tudes|dipl[ôo]me|nivel de estudios|titulaci[óo]n|escolaridade|titolo di studio|wykszta[łl]cenie/],
    ["degree_subject", /degree subject|field of study|\bmajor\b|discipline|subject studied|studierichting|fagomr[åa]de|studieretning|studiengang|fachrichtung|domaine d.[ée]tudes|especialidad|\bcarrera\b|kierunek/],
    ["university", /university|school|college|institution|universiteit|hogeschool|onderwijsinstelling|universitet|uddannelsessted|universit[äa]t|hochschule|universit[ée]|[ée]cole|universidad|universidade|universit[àa]|uczelnia/],
    ["right_to_work", /right to work|eligible to work|authori[sz]ed to work|work authori[sz]ation|legally (able|entitled|permitted|authorized)|permission to work|work permit|werkvergunning|tewerkstellingsvergunning|recht om te werken|arbejdstilladelse|ret til at arbejde|arbeitserlaubnis|arbeitsgenehmigung|autorisation de travail|permiso de trabajo|autoriza[çc][ãa]o de trabalho|pozwolenie na prac/],
    ["needs_sponsorship", /sponsor|\bvisum\b|parrainage de visa/],
    ["willing_to_relocate", /relocat|willing to move|verhuizen|flytte|umzug|umziehen|d[ée]m[ée]nag|reubicar|mudar(te|se)? de/],
    ["driving_licence", /driving licen[cs]e|driver'?s licen[cs]e|rijbewijs|k[øo]rekort|f[üu]hrerschein|permis de conduire|carn[ée] de conducir|carta de condu[çc][ãa]o|patente di guida|prawo jazdy/],
    ["full_name", /full name|your name|legal name|^\s*name\b|\bname\s*\*?\s*$|candidate name|volledige naam|\bnaam\b|fulde navn|\bnavn\b|vollst[äa]ndiger name|nom complet|nombre completo|nome completo|imi[ęe] i nazwisko/, ["name"]],
    ["cover_letter", /cover\s*letter|covering letter|motivation(al)? letter|motivatiebrief|sollicitatiebrief|motivatie|ans[øo]gning|anschreiben|motivationsschreiben|lettre de motivation|carta de (presentaci[óo]n|motivaci[óo]n)|carta de motiva[çc][ãa]o|lettera di presentazione|list motywacyjny/],
    ["skills", /\bskills\b|vaardigheden|kompetencer|f[äa]higkeiten|kenntnisse|comp[ée]tences|habilidades|competencias|umiej[ęe]tno/],
  ];
  const YES_NO = new Set(["right_to_work", "needs_sponsorship", "driving_licence", "over_18", "willing_to_relocate"]);
  // "Are you 18 or over?" is checked before the personal-question filter (which skips anything about age)
  const OVER_18 = /(18|eighteen) (years|or (older|over|above))|over (the age of )?(18|eighteen)|at least (18|eighteen)|aged? 18|legal (working )?age|18\+|18 jaar|18 år|vollj[äa]hrig|majeur|mayor de edad|maggiorenne/;
  const CONSENT = /privacy|terms|consent|i agree|agree to|i accept|accept the|data (protection|processing)|gdpr|avg\b|voorwaarden|akkoord|toestemming|samtykke|vilk[åa]r|datenschutz|einwillig|zustimm|conditions|politique de confidentialit|t[ée]rminos|privacidad/;
  const MARKETING = /newsletter|marketing|promotion|offers|updates about|job alerts?|talent (community|pool)|future (roles|opportunities|vacancies)|nieuwsbrief|nyhedsbrev/;
  // Personal/diversity questions are left for you to answer yourself (incl. US EEO questions)
  const SKIP = /gender|ethnic|\brace\b|hispanic|latino|disab|religio|sexual|veteran|pronoun|date of birth|\bdob\b|\bage\b|marital|password|captcha|search|referr|how did you hear|\beeo|geslacht|etniciteit|geboortedatum|leeftijd|\bk[øo]n\b|etnicitet|f[øo]dselsdato|\balder\b|geschlecht|geburtsdatum|\balter\b|herkunft|\bsexe\b|date de naissance|g[ée]nero|\bsexo\b|fecha de nacimiento|\bedad\b|nascita|hoe heb je|hvor h[øo]rte|wie haben sie|comment avez|c[óo]mo nos/;
  // "Yes"/"No" in those languages, for radio buttons and drop-downs
  const YES_WORDS = ["yes", "ja", "oui", "sí", "si", "sim", "tak", "igen", "i do", "i have", "i am", "true"];
  const NO_WORDS = ["no", "nee", "nej", "nein", "non", "não", "nao", "nie", "nei", "i do not", "i don't", "i am not", "false"];
  // country names as they appear in other languages' drop-downs
  const COUNTRY_NAMES = {
    gb: ["united kingdom", "uk", "great britain", "england", "verenigd koninkrijk", "storbritannien", "vereinigtes königreich", "royaume-uni", "reino unido", "regno unito", "wielka brytania"],
    nl: ["netherlands", "the netherlands", "nederland", "holland", "niederlande", "pays-bas", "países bajos", "paesi bassi", "holandia"],
    dk: ["denmark", "danmark", "denemarken", "dänemark", "danemark", "dinamarca", "danimarca", "dania"],
    us: ["united states", "united states of america", "usa", "us", "verenigde staten", "vereinigte staaten", "états-unis", "estados unidos", "stati uniti", "stany zjednoczone"],
    de: ["germany", "deutschland", "duitsland", "tyskland", "allemagne", "alemania", "alemanha", "germania", "niemcy"],
  };
  const pageLang = (document.documentElement.lang || navigator.language || "en").slice(0, 2).toLowerCase();
  const yesNoText = (yes) => ({ nl: ["Ja", "Nee"], da: ["Ja", "Nej"], de: ["Ja", "Nein"], fr: ["Oui", "Non"], es: ["Sí", "No"],
    pt: ["Sim", "Não"], it: ["Sì", "No"], sv: ["Ja", "Nej"], no: ["Ja", "Nei"], pl: ["Tak", "Nie"] }[pageLang] || ["Yes", "No"])[yes ? 0 : 1];

  const clean = (s) => (s || "").replace(/[_\-\[\].]+/g, " ").replace(/([a-z])([A-Z])/g, "$1 $2").replace(/\s+/g, " ").trim();

  function describe(el) {
    const parts = [];
    if (el.id) {
      try { const l = document.querySelector(`label[for="${CSS.escape(el.id)}"]`); if (l) parts.push(l.innerText); } catch (e) {}
    }
    const wrap = el.closest("label");
    if (wrap) parts.push(wrap.innerText);
    const lb = el.getAttribute("aria-labelledby");
    if (lb) lb.split(/\s+/).forEach((i) => { const n = document.getElementById(i); if (n) parts.push(n.innerText); });
    ["aria-label", "placeholder", "name", "id", "title", "data-automation-id", "data-testid", "data-qa"].forEach((a) => {
      const v = el.getAttribute(a); if (v) parts.push(v);
    });
    if (clean(parts.join(" ")).length < 4 || /^(input|field|question)\s*\d*$/i.test(clean(parts.join(" ")))) {
      // fall back to nearby text (question text above the box)
      let p = el.parentElement;
      for (let i = 0; i < 4 && p; i++, p = p.parentElement) {
        const t = (p.innerText || "").trim();
        if (t && t.length < 160) { parts.push(t); break; }
      }
    }
    return clean(parts.join(" | ")).toLowerCase();
  }

  // Exact field names used by common application systems (more reliable than reading labels)
  const NAME_MAP = { // Lever
    "name": "full_name", "email": "email", "phone": "phone", "org": "current_company", "location": "city",
    "urls[linkedin]": "linkedin", "urls[github]": "github", "urls[portfolio]": "website", "urls[other]": "website",
  };
  const AUTOMATION_MAP = { // Workday data-automation-id
    "legalnamesection_firstname": "first_name", "legalnamesection_lastname": "last_name",
    "addresssection_addressline1": "address1", "addresssection_addressline2": "address2",
    "addresssection_city": "city", "addresssection_postalcode": "postcode", "addresssection_countryregion": "county",
    "email": "email", "phone-number": "phone", "phonenumber": "phone",
  };

  function keyFor(el, desc) {
    const nm = (el.getAttribute("name") || "").toLowerCase();
    if (NAME_MAP[nm]) return NAME_MAP[nm];
    const aid = (el.getAttribute("data-automation-id") || "").toLowerCase();
    if (AUTOMATION_MAP[aid]) return AUTOMATION_MAP[aid];
    const ac = (el.getAttribute("autocomplete") || "").toLowerCase().split(/\s+/).pop();
    if (ac && ac !== "off" && ac !== "on") {
      for (const [k, , acs] of RULES) if (acs && acs.includes(ac)) return k;
    }
    if (OVER_18.test(desc)) return "over_18";
    if (SKIP.test(desc)) return null;
    for (const [k, re] of RULES) if (re.test(desc)) return k;
    return null;
  }

  const visible = (el) => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length) &&
    getComputedStyle(el).visibility !== "hidden";

  // all matching elements, including inside open shadow roots (some application widgets use them)
  function deepQuery(sel, root = document) {
    const out = [...root.querySelectorAll(sel)];
    root.querySelectorAll("*").forEach((el) => { if (el.shadowRoot) out.push(...deepQuery(sel, el.shadowRoot)); });
    return out;
  }
  const isCombo = (el) => el.getAttribute("role") === "combobox" || el.getAttribute("aria-autocomplete") === "list";

  function fields() {
    return deepQuery("input, textarea, select").filter((el) => {
      const t = (el.type || "").toLowerCase();
      if (["hidden", "submit", "button", "reset", "image", "password", "checkbox", "radio", "search", "file"].includes(t)) return false;
      if (el.tagName === "INPUT" && isCombo(el)) return false;          // searchable drop-downs: handled separately
      return !el.disabled && !el.readOnly && visible(el);
    });
  }

  // ---- everything filled is logged so "Undo" can put it back
  let filledLog = [];
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const markFilled = (el) => { el.style.outline = "2px solid #3fb950"; el.style.outlineOffset = "1px"; };

  // ---- setting values in a way React/Angular/Vue forms notice
  function nativeSet(el, value) {
    const proto = el instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype
      : el instanceof HTMLSelectElement ? HTMLSelectElement.prototype : HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(proto, "value").set.call(el, value);
  }
  function setValue(el, value, quiet) {
    if (!quiet) filledLog.push({ el, kind: "value", prev: el.value });
    el.focus();
    nativeSet(el, value);
    el.dispatchEvent(new InputEvent("input", { bubbles: true, inputType: "insertText", data: String(value) }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
    // some forms ignore a pasted value: type it in character by character instead
    if (el.tagName !== "SELECT" && el.value !== String(value)) {
      nativeSet(el, "");
      for (const ch of String(value)) {
        el.dispatchEvent(new KeyboardEvent("keydown", { key: ch, bubbles: true }));
        nativeSet(el, el.value + ch);
        el.dispatchEvent(new InputEvent("input", { bubbles: true, inputType: "insertText", data: ch }));
        el.dispatchEvent(new KeyboardEvent("keyup", { key: ch, bubbles: true }));
      }
      el.dispatchEvent(new Event("change", { bubbles: true }));
    }
    el.blur();
    if (!quiet) markFilled(el);
  }

  function undoFill() {
    for (const item of filledLog.reverse()) {
      const el = item.el;
      try {
        if (item.kind === "value") setValue(el, item.prev, true);
        else if (item.kind === "checked") { el.checked = item.prev; el.dispatchEvent(new Event("change", { bubbles: true })); }
        else if (item.kind === "files") { el.files = new DataTransfer().files; el.dispatchEvent(new Event("change", { bubbles: true })); }
        el.style.outline = "";
      } catch (e) {}
    }
    const n = filledLog.length;
    filledLog = [];
    clearMissing();
    return n;
  }

  // ---- required fields still empty after filling: outlined in amber, with "Next empty field"
  let missing = [];
  function clearMissing() { missing.forEach((el) => { if (el.style.outline.includes("dashed")) el.style.outline = ""; }); missing = []; }
  function findMissing() {
    clearMissing();
    const req = (el) => el.required || el.getAttribute("aria-required") === "true" || /\*\s*$/.test((describe(el).split("|")[0] || "").trim());
    missing = deepQuery("input, textarea, select").filter((el) => {
      const t = (el.type || "").toLowerCase();
      if (["hidden", "submit", "button", "reset", "image", "radio"].includes(t) || el.disabled || !visible(el) || !req(el)) return false;
      if (t === "checkbox") return false;               // consent boxes are yours to tick
      if (t === "file") return !(el.files && el.files.length);
      return !String(el.value || "").trim();
    });
    missing.forEach((el) => { el.style.outline = "2px dashed #e0a040"; el.style.outlineOffset = "2px"; });
    return missing.length;
  }

  const word = (w) => new RegExp("(^|[^a-z])" + w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + "($|[^a-z])", "i");

  function alternatives(key, value) {
    const v = String(value).toLowerCase().trim();
    if (YES_NO.has(key)) return /^(y|ja|j$|oui|s[ií]|sim|tak)/.test(v) ? YES_WORDS : NO_WORDS;
    if (key === "country") {
      // "United Kingdom" in the profile should also pick "Verenigd Koninkrijk", "Storbritannien", ...
      const group = Object.values(COUNTRY_NAMES).find((names) => names.includes(v) ||
        (v === "gb" || v === "scotland" || v === "wales" || v === "northern ireland") && names.includes("united kingdom"));
      if (group) return group;
    }
    return [v];
  }

  // ---- picking the right choice in drop-downs, radio buttons and searchable menus
  const US_STATES = { al: "alabama", ak: "alaska", az: "arizona", ar: "arkansas", ca: "california", co: "colorado",
    ct: "connecticut", de: "delaware", fl: "florida", ga: "georgia", hi: "hawaii", id: "idaho", il: "illinois", in: "indiana",
    ia: "iowa", ks: "kansas", ky: "kentucky", la: "louisiana", me: "maine", md: "maryland", ma: "massachusetts", mi: "michigan",
    mn: "minnesota", ms: "mississippi", mo: "missouri", mt: "montana", ne: "nebraska", nv: "nevada", nh: "new hampshire",
    nj: "new jersey", nm: "new mexico", ny: "new york", nc: "north carolina", nd: "north dakota", oh: "ohio", ok: "oklahoma",
    or: "oregon", pa: "pennsylvania", ri: "rhode island", sc: "south carolina", sd: "south dakota", tn: "tennessee",
    tx: "texas", ut: "utah", vt: "vermont", va: "virginia", wa: "washington", wv: "west virginia", wi: "wisconsin",
    wy: "wyoming", dc: "district of columbia" };
  const DIAL = { gb: "44", us: "1", nl: "31", dk: "45", de: "49", ie: "353", fr: "33", es: "34", it: "39", be: "32",
    se: "46", no: "47", ca: "1", au: "61", in: "91", pt: "351", pl: "48", ch: "41", at: "43", nz: "64" };
  // qualification in the profile -> words a drop-down might use for it (best first)
  const QUAL = [
    [/phd|doctor/, /ph\.?d|doctor|doctoraat|promotie|ph\.d/],
    [/master|msc|mba|meng|\bma\b|mres|kandidat/, /master|msc|m\.sc|mba|postgraduate|graduate degree|\bwo\b|kandidat|cand\./],
    [/bachelor|bsc|\bba\b|beng|llb|hbo/, /bachelor|undergraduate|\bbsc\b|\bba\b|b\.s\.|b\.a\.|\bhbo\b|university degree|4[- ]year degree|degree/],
    [/hnd|hnc|foundation|associate/, /hnd|hnc|foundation|associate|level [45]|2[- ]year degree|college/],
    [/a-?level|btec|diploma|mbo|erhvervs/, /a[- ]?level|btec|level 3|high school|secondary|diploma|\bmbo\b|havo|vwo|gymnasi|studentereksamen/],
    [/gcse/, /gcse|level 2|secondary|high school|vmbo|folkeskole/],
  ];
  const days = (t) => {               // "1 month" / "4 weeks" / "Immediately" -> days
    t = String(t).toLowerCase();
    if (/immediate|right away|asap|direct|straks|omg[åa]ende|sofort|now\b|none|no notice/.test(t)) return 0;
    const n = parseFloat((t.match(/\d+(\.\d+)?/) || ["1"])[0]);
    return /month|maand|m[åa]ned|monat|mois|mes/.test(t) ? n * 30 : /week|uge|woche|semaine|semana/.test(t) ? n * 7 : /day|dag|tag|jour|d[íi]a/.test(t) ? n : NaN;
  };
  const range = (t) => {              // "3-5 years" -> [3,5], "10+" -> [10,inf], "less than 1" -> [0,1]
    t = String(t).toLowerCase().replace(/,(?=\d{3})/g, "").replace(/(\d+(?:\.\d+)?)\s*k\b/g, (m, n) => String(n * 1000));
    const nums = (t.match(/\d+(\.\d+)?/g) || []).map(Number);
    if (!nums.length) return /no experience|none|geen|ingen|keine|entry/.test(t) ? [0, 0.5] : null;
    if (/less than|under|fewer|up to|<|minder dan|under|weniger|moins de|menos de/.test(t)) return [0, nums[0]];
    if (/\+|more than|over|above|or more|plus|>|meer dan|mere end|mehr als|plus de|m[áa]s de/.test(t)) return [nums[0], Infinity];
    return nums.length > 1 ? [nums[0], nums[1]] : [nums[0], nums[0]];
  };

  function optionScore(key, value, raw) {
    const text = clean(raw).toLowerCase();
    if (!text || /^(select|choose|please|kies|v[æa]lg|w[äa]hle|s[ée]lectionnez|seleccione|--|—)/.test(text)) return 0;
    const v = String(value).toLowerCase().trim();
    if (YES_NO.has(key)) {
      const yes = /^(y|ja|j$|oui|s[ií]|sim|tak|true)/.test(v);
      const words = yes ? YES_WORDS : NO_WORDS;
      if (words.includes(text)) return 10;
      return words.some((a) => word(a).test(text)) && !(yes ? NO_WORDS : YES_WORDS).some((a) => text.startsWith(a)) ? 7 : 0;
    }
    if (key === "years_experience" || key === "salary") {
      const n = parseFloat(v.replace(/,/g, "").replace(/(\d+)\s*k\b/, (m, x) => x * 1000));
      const r = range(text);
      if (isNaN(n) || !r) return 0;
      return n >= r[0] && n <= r[1] ? (r[0] === r[1] ? 10 : 9) : 0;
    }
    if (key === "notice_period") {
      const a = days(v), b = days(text);
      return isNaN(a) || isNaN(b) ? (text === v ? 10 : 0) : Math.max(0.5, 10 - Math.abs(a - b) / 7);
    }
    if (key === "highest_qualification") {
      const lvl = QUAL.findIndex(([mine]) => mine.test(v));
      if (text === v) return 10;
      if (lvl >= 0 && QUAL[lvl][1].test(text)) return 8;
      return 0;
    }
    if (key === "county") {
      const names = [v, US_STATES[v], Object.keys(US_STATES).find((c) => US_STATES[c] === v)].filter(Boolean);
      if (names.includes(text)) return 10;
      return names.some((x) => x.length > 2 && text.startsWith(x)) ? 7 : 0;
    }
    if (key === "country" || key === "phone_country") {
      const code = Object.keys(COUNTRY_NAMES).find((c) => COUNTRY_NAMES[c].includes(v)) ||
        (/^(gb|scotland|wales|northern ireland)$/.test(v) ? "gb" : v.length === 2 ? v : "");
      const names = COUNTRY_NAMES[code] || [v];
      const dial = DIAL[code];
      if (key === "phone_country" && dial && new RegExp("\\+\\s?" + dial + "(?!\\d)").test(text)) return names.some((x) => text.includes(x)) ? 10 : 8;
      if (names.includes(text)) return 10;
      if (names.some((x) => x.length > 2 && (text.startsWith(x + " ") || text.startsWith(x + ",") || text.startsWith(x + " (")))) return 8;
      return names.some((x) => x.length > 3 && text.includes(x)) ? 5 : 0;
    }
    if (text === v) return 10;
    if (text.startsWith(v + " ") || text.startsWith(v + ",")) return 8;
    if (v.length > 2 && text.includes(v)) return 6;
    if (text.length > 2 && v.includes(text)) return 5;
    const vs = v.split(/\W+/).filter((w) => w.length > 2), ts = new Set(text.split(/\W+/));
    const common = vs.filter((w) => ts.has(w)).length;
    return vs.length && common ? (common / vs.length) * 4 : 0;
  }
  // best of a list of choices: [element, its visible text]
  function bestChoice(key, value, choices) {
    let best = null, top = 0;
    for (const [el, txt] of choices) {
      const s = optionScore(key, value, txt);
      if (s > top) { best = el; top = s; }
    }
    return top >= 3 ? best : null;
  }

  function chooseOption(sel, key, value) {
    const hit = bestChoice(key, value, [...sel.options].filter((o) => o.value !== "").map((o) => [o, o.text || o.value]));
    if (!hit) return false;
    setValue(sel, hit.value);
    return true;
  }

  // questions answered by picking one choice (radio buttons, yes/no drop-downs, tick boxes)
  const CHOICE_KEYS = new Set([...YES_NO, "highest_qualification", "years_experience", "notice_period", "country", "county", "salary"]);
  function choiceKey(q) {
    if (OVER_18.test(q)) return "over_18";
    if (SKIP.test(q)) return null;
    const r = RULES.find(([k, re]) => CHOICE_KEYS.has(k) && re.test(q));
    return r ? r[0] : null;
  }

  function fillRadios(data) {
    let n = 0;
    const groups = {};
    document.querySelectorAll('input[type="radio"]').forEach((r) => {
      if (r.name && !r.disabled) (groups[r.name] = groups[r.name] || []).push(r);
    });
    for (const radios of Object.values(groups)) {
      if (radios.some((r) => r.checked)) continue;
      // question text: fieldset legend, or the smallest container holding all options
      // (a fieldset only counts if it holds just this question, not a whole form section)
      let box = radios[0].closest("fieldset");
      const ownFieldset = box && box.querySelector("legend") &&
        [...box.querySelectorAll("input, select, textarea")].every((el) => el.type === "radio" && el.name === radios[0].name);
      let q = ownFieldset ? box.querySelector("legend").innerText : "";
      if (!q) {
        box = radios[0].parentElement;
        while (box && !radios.every((r) => box.contains(r))) box = box.parentElement;
        // only look further out when there's no question text next to the options themselves
        const optText = radios.map((r) => (r.closest("label") || {}).innerText || "").join(" ");
        const questionLen = () => ((box.innerText || "").replace(/\s+/g, " ").length - optText.replace(/\s+/g, " ").length);
        for (let i = 0; i < 2 && box && questionLen() < 6; i++) box = box.parentElement;
        q = box ? (box.innerText || "").slice(0, 300) : "";
      }
      q = clean(q).toLowerCase() + " " + clean(radios[0].name).toLowerCase();
      const key = choiceKey(q);
      if (!key || !data[key]) continue;
      const labelOf = (r) => clean((r.id && document.querySelector(`label[for="${CSS.escape(r.id)}"]`)?.innerText) ||
        r.closest("label")?.innerText || r.getAttribute("aria-label") || r.value).toLowerCase();
      const pick = bestChoice(key, data[key], radios.map((r) => [r, labelOf(r)]));
      if (pick) {
        filledLog.push({ el: pick, kind: "checked", prev: false });
        pick.click();
        pick.dispatchEvent(new Event("change", { bubbles: true }));
        n++;
      }
    }
    return n;
  }

  async function attachCv() {
    const inputs = deepQuery('input[type="file"]').filter((i) => !i.disabled);
    if (!inputs.length) return false;
    const CV_RE = /resume|r[ée]sum[ée]|\bcv\b|curriculum|lebenslauf|levensloop|hoja de vida|currículo|curr[íi]culum/;
    const OTHER_RE = /cover|motivat|anschreiben|ans[øo]gning|lettre|carta|brief|photo|foto|image|bild|billede|afbeelding|avatar|portrait/;
    const target = inputs.find((i) => CV_RE.test(describe(i)) && !OTHER_RE.test(describe(i))) ||
      (inputs.length === 1 && !OTHER_RE.test(describe(inputs[0])) ? inputs[0] : null);
    if (!target || (target.files && target.files.length)) return false;
    const cv = await send({ type: "getCv" });
    if (!cv || !cv.data) return false;
    const bytes = Uint8Array.from(atob(cv.data), (c) => c.charCodeAt(0));
    const file = new File([bytes], cv.name, { type: cv.type || "application/octet-stream" });
    const dt = new DataTransfer();
    dt.items.add(file);
    try {
      filledLog.push({ el: target, kind: "files" });
      target.files = dt.files;
      target.dispatchEvent(new Event("input", { bubbles: true }));
      target.dispatchEvent(new Event("change", { bubbles: true }));
      // some upload widgets only react to a drop
      const zone = target.closest("[class*=drop], [class*=upload]");
      if (zone) zone.dispatchEvent(new DragEvent("drop", { bubbles: true, dataTransfer: dt }));
      return true;
    } catch (e) { return false; }
  }

  // ---- employment history: each block holding one job title / company box is one past job
  const MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"];

  function jobGroups(items) {
    const titles = items.filter((k) => k.key === "current_title").map((k) => k.el);
    const comps = items.filter((k) => k.key === "current_company").map((k) => k.el);
    const count = (p, arr) => arr.filter((e) => p.contains(e)).length;
    const groups = [];
    for (const el of titles.concat(comps)) {
      let p = el.parentElement, best = null;
      while (p && p !== document.body) {
        if (count(p, titles) > 1 || count(p, comps) > 1 || p.querySelectorAll("input, textarea, select").length > 15) break;
        best = p;
        p = p.parentElement;
      }
      if (best && !groups.includes(best)) groups.push(best);
    }
    // a real job block has a title AND a company box, or a title/company plus From/To dates
    const dateish = items.filter((k) => /^job_(start|end)$/.test(jobFieldKey(k.desc, k.el, null) || "")).map((k) => k.el);
    const valid = groups.filter((g) => (count(g, titles) === 1 && count(g, comps) === 1) || count(g, dateish) > 0);
    // a group nested in another one is the same job
    const outer = valid.filter((g) => !valid.some((o) => o !== g && o.contains(g)));
    return outer.sort((a, b) => (a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING ? -1 : 1));
  }

  function jobFieldKey(desc, el, key) {
    if (key === "current_title" || key === "current_company") return key;
    // "From" / "Start month" are dates; "Are you authorised to work in the UK?" isn't an end date
    const label = desc.split("|")[0];
    const dateLike = el.type === "month" || el.type === "date" || label.length <= 30 ||
      /date|month|year|datum|dato|monat|jahr|mois|ann[ée]e|fecha|\bmes\b|a[ñn]o\b|maand|jaar|m[åa]ned|\b[åa]r\b/.test(label);
    if (dateLike && /\b(from|start(ed|ing)?|began|van|vanaf|begindatum|startdato|fra|von|beginn|desde|inicio|d[ée]but)\b/.test(desc)) return "job_start";
    if (dateLike && /\b(to|end(ed)?|until|finish(ed)?|leaving|left|tot|einddatum|slutdato|til|bis|ende|hasta|fin)\b/.test(desc)) return "job_end";
    if (el.tagName === "TEXTAREA" || /descri|responsib|duties|achievement|what you did|beschrijving|taken|beskrivelse|opgaver|beschreibung|aufgaben|t[âa]ches|funciones|tareas/.test(desc)) return "job_description";
    if (/location|city|town|locatie|plaats|lokation|\bsted\b|\bort\b|\blieu\b|ubicaci[óo]n/.test(desc)) return "job_location";
    return null;
  }

  function dateFor(el, text) {
    // "Jul 2022" -> what the box wants
    if (!text || /present|current/i.test(text)) return el.type === "month" || el.type === "date" ? "" : text;
    const y = (text.match(/(19|20)\d{2}/) || [""])[0];
    const mi = MONTHS.findIndex((m) => text.toLowerCase().includes(m));
    const mm = String(mi >= 0 ? mi + 1 : 1).padStart(2, "0");
    if (el.type === "month") return y ? `${y}-${mm}` : "";
    if (el.type === "date") return y ? `${y}-${mm}-01` : "";
    if (/mm\s*\/\s*yyyy/i.test(el.placeholder || "")) return y ? `${mm}/${y}` : text;
    return text;
  }

  function chooseDatePart(sel, text) {
    const y = (text.match(/(19|20)\d{2}/) || [""])[0];
    const mi = MONTHS.findIndex((m) => text.toLowerCase().includes(m));
    const opts = [...sel.options];
    // month names in drop-downs may be Dutch, Danish, German, French, Spanish, Italian…
    const MONTH_WORDS = [["jan", "ene", "gen"], ["feb", "fév", "fev"], ["mar", "mrt", "mär", "maa"], ["apr", "avr", "abr"],
      ["may", "mei", "maj", "mai", "mag"], ["jun", "juin", "giu"], ["jul", "juil", "lug"], ["aug", "aoû", "aou", "ago"],
      ["sep", "set"], ["oct", "okt", "ott"], ["nov"], ["dec", "dez", "déc", "dic"]];
    let hit = y && opts.find((o) => o.text.trim() === y || o.value === y);
    if (!hit && mi >= 0) hit = opts.find((o) => MONTH_WORDS[mi].some((m) => o.text.trim().toLowerCase().startsWith(m)) ||
      o.value === String(mi + 1) || o.value === String(mi + 1).padStart(2, "0"));
    if (!hit) return false;
    setValue(sel, hit.value);
    return true;
  }

  async function fill() {
    const resp = await send({ type: "getData" });
    if (!resp || !resp.profile) return { n: 0, cv: false, error: resp && resp.error };
    const data = { ...resp.profile, full_name: resp.full_name, cover_letter: resp.cover_letter };
    const jobs = Array.isArray(data.jobs) ? data.jobs : [];
    data.current_title = data.current_title || (jobs[0] || {}).title || "";       // most recent job doubles as "current"
    data.current_company = data.current_company || (jobs[0] || {}).company || "";
    data.phone_country = data.country || "";
    data.over_18 = data.over_18 || "";
    const items = fields().map((el) => { const desc = describe(el); return { el, desc, key: keyFor(el, desc) }; });
    // a "full name" box gets your middle name too when you have one
    if (data.middle_name && data.full_name && !data.full_name.includes(data.middle_name))
      data.full_name = [data.first_name, data.middle_name, data.last_name].filter(Boolean).join(" ");
    // Dutch forms split "de Vries" into tussenvoegsel "de" + achternaam "Vries"
    if (items.some((i) => i.key === "name_prefix")) {
      const m = String(data.last_name || "").match(/^((?:(?:van|de|der|den|het|ten|ter|te|op|in|'t|'s)\s+)+)(.+)$/i);
      if (m) { data.name_prefix = m[1].trim(); data.last_name = m[2]; }
    }
    const groups = jobs.length ? jobGroups(items) : [];
    let n = 0;
    for (const { el, desc, key: baseKey } of items) {
      if (el.tagName !== "SELECT" && el.value && el.value.trim()) continue; // never overwrite your typing
      let key = baseKey, value;
      const gi = groups.findIndex((g) => g.contains(el));
      let jk = gi >= 0 ? jobFieldKey(desc, el, baseKey) : null;
      if (jk) {
        const job = jobs[gi];
        if (!job) continue;              // more job sections on the page than jobs in your profile
        value = { current_title: job.title, current_company: job.company, job_start: job.start,
                  job_end: job.end, job_description: job.description, job_location: job.location }[jk];
        // nothing for this box in the job: a normal question ("City", "Right to work") is still answered below
        if (!value && (!baseKey || baseKey === "current_title" || baseKey === "current_company")) continue;
        if (!value) jk = null;
      }
      if (jk) {
        key = jk;
        if (key === "job_start" || key === "job_end") {
          if (el.tagName === "SELECT") { if (!(el.selectedIndex > 0 && el.value) && chooseDatePart(el, value)) n++; continue; }
          value = dateFor(el, value);
          if (!value) continue;
        }
        if (el.tagName === "SELECT") { if (!(el.selectedIndex > 0 && el.value) && chooseOption(el, key, value)) n++; continue; }
        setValue(el, value);
        n++;
        continue;
      }
      if (!key) continue;
      if ((key === "cover_letter" || key === "skills") && el.tagName !== "TEXTAREA") continue;
      value = data[key];
      if (!value) continue;
      if (el.tagName === "SELECT") {
        if (el.selectedIndex > 0 && el.value) continue;
        if (chooseOption(el, key, value)) n++;
      } else {
        setValue(el, YES_NO.has(key) ? yesNoText(String(value).toLowerCase().startsWith("y")) : String(value));
        n++;
      }
    }
    n += fillRadios(data);
    n += fillCheckboxes(data);
    n += await fillCombos(data, jobs);
    const cv = await attachCv();
    const left = findMissing();
    return { n, cv, left };
  }

  // ---- tick boxes. Single boxes that state a fact ("I have the right to work in the UK", "I am 18 or over")
  // are ticked when your profile says Yes. Groups ("Which of these apply?") get the options that match.
  // Privacy/terms boxes only when you've allowed that in your profile; marketing/newsletter boxes never.
  const yes = (v) => /^(y|ja|oui|s[ií]|sim|tak|true)/i.test(String(v || ""));
  function tick(box) {
    filledLog.push({ el: box, kind: "checked", prev: false });
    box.click();
    if (!box.checked) { box.checked = true; box.dispatchEvent(new Event("change", { bubbles: true })); }
    box.dispatchEvent(new Event("input", { bubbles: true }));
    markFilled(box.closest("label") || box);
  }
  function fillCheckboxes(data) {
    let n = 0;
    const boxes = deepQuery('input[type="checkbox"], [role="checkbox"]').filter((b) => !b.disabled && visible(b));
    const isOn = (b) => b.checked || b.getAttribute("aria-checked") === "true";
    // groups of boxes sharing one question (same name, or same fieldset)
    const groups = {};
    for (const b of boxes) {
      const g = b.name && boxes.filter((o) => o.name === b.name).length > 1 ? "n:" + b.name : null;
      if (g) (groups[g] = groups[g] || []).push(b);
    }
    for (const list of Object.values(groups)) {
      if (list.some(isOn)) continue;
      let box = list[0].closest("fieldset") || list[0].parentElement;
      while (box && !list.every((b) => box.contains(b))) box = box.parentElement;
      const q = clean((box && (box.querySelector("legend") || {}).innerText) || (box ? (box.innerText || "").slice(0, 200) : "")).toLowerCase();
      const key = choiceKey(q);
      if (!key || !data[key] || YES_NO.has(key)) continue;
      const labelOf = (b) => clean(b.closest("label")?.innerText || (b.id && document.querySelector(`label[for="${CSS.escape(b.id)}"]`)?.innerText) || b.value).toLowerCase();
      const pick = bestChoice(key, data[key], list.map((b) => [b, labelOf(b)]));
      if (pick) { tick(pick); n++; }
    }
    for (const box of boxes) {
      if (isOn(box) || (box.name && groups["n:" + box.name])) continue;
      const desc = describe(box);
      if (MARKETING.test(desc)) continue;
      if (CONSENT.test(desc)) {
        if (yes(data.auto_consent)) { tick(box); n++; }
        continue;
      }
      const key = choiceKey(desc);
      if (!key || !YES_NO.has(key)) continue;
      // "I require sponsorship" is ticked only if you need it; the rest when your answer is Yes
      const negative = /\b(not|don'?t|do not|niet|ikke|nicht|pas)\b/.test(desc);
      if (yes(data[key]) !== negative) { tick(box); n++; }
    }
    return n;
  }

  // ---- searchable drop-downs (Greenhouse/react-select, Workday, Lever...): type, wait for the list, click the match
  async function fillCombos(data, jobs) {
    let n = 0;
    const combos = deepQuery('input[role="combobox"], input[aria-autocomplete="list"], button[aria-haspopup="listbox"]')
      .filter((el) => visible(el) && !el.disabled);
    for (const el of combos) {
      const isButton = el.tagName === "BUTTON";
      const shown = isButton ? (el.innerText || "").trim() : el.value;
      const chosen = el.closest("[class*=control], [class*=container]")?.querySelector("[class*=single-value], [class*=singleValue]");
      if (chosen || (isButton ? shown && !/^(select|choose|kies|vælg|wähle|sélection|selecciona|—|-)/i.test(shown) : shown)) continue;
      const desc = describe(el);
      const key = keyFor(el, desc);
      if (!key || ["cover_letter", "skills"].includes(key)) continue;
      const value = key === "current_title" ? (data.current_title || (jobs[0] || {}).title) :
        key === "current_company" ? (data.current_company || (jobs[0] || {}).company) : data[key];
      if (!value) continue;
      el.scrollIntoView({ block: "center" });
      el.focus();
      el.dispatchEvent(new MouseEvent("mousedown", { bubbles: true }));
      el.click();
      // type to narrow the list — except for ranges/levels, where the wording rarely matches what we'd type
      const typeIt = !isButton && !["years_experience", "salary", "notice_period", "highest_qualification"].includes(key);
      if (typeIt) setValue(el, YES_NO.has(key) ? yesNoText(yes(value)) : key === "phone_country" ? String(value) : String(value), true);
      let hit = null;
      for (let tries = 0; tries < 7 && !hit; tries++) {         // the list can take a moment to appear
        await sleep(200);
        const opts = deepQuery('[role="option"], [class*="option"]:not([class*="options"]), [data-automation-id="promptOption"], li[data-value]')
          .filter((o) => visible(o) && (o.innerText || "").trim());
        hit = bestChoice(key, value, opts.map((o) => [o, o.innerText || o.textContent]));
      }
      if (hit) {
        filledLog.push({ el: el.closest("[class*=control]") || el, kind: "combo" });
        hit.scrollIntoView({ block: "nearest" });
        hit.dispatchEvent(new MouseEvent("mousedown", { bubbles: true }));
        hit.click();
        hit.dispatchEvent(new MouseEvent("mouseup", { bubbles: true }));
        markFilled(el.closest("[class*=control]") || el);
        n++;
      } else {
        // nothing matched: clear what was typed and close the list
        if (!isButton) setValue(el, "", true);
        el.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
      }
      await sleep(120);
    }
    return n;
  }

  // ---- is this an application form?
  function looksLikeApplication() {
    let hits = 0;
    for (const el of fields()) {
      if (keyFor(el, describe(el))) hits++;
      if (hits >= 3) return true;
    }
    return hits >= 1 && !!document.querySelector('input[type="file"]');
  }

  // ---- floating button (top page only)
  let ui = null, total = { n: 0, cv: false }, activeJob = null;

  function buildUi() {
    if (ui || !TOP) return;
    if (sessionStorage.getItem("jf-hide") === "1") return;
    const host = document.createElement("div");
    host.style.cssText = "position:fixed;right:18px;bottom:18px;z-index:2147483647";
    const root = host.attachShadow({ mode: "open" });
    // the app's fonts, bundled with the extension (added under unique names so pages aren't affected)
    try {
      [["JFItaliana", "Italiana-Regular.ttf", {}], ["JFManrope", "Manrope.ttf", { weight: "200 800" }]].forEach(([fam, file, d]) => {
        const f = new FontFace(fam, `url(${chrome.runtime.getURL(file)})`, d);
        f.load().then((ff) => document.fonts.add(ff)).catch(() => {});
      });
    } catch (e) {}
    const logo = chrome.runtime.getURL("icons/jf48.png");
    root.innerHTML = `<style>
      :host{all:initial}
      .box{font:400 13.5px/1.45 JFManrope,"Segoe UI",system-ui,sans-serif;color:#f4efe6;width:300px;border-radius:20px;padding:14px 16px 16px;
        background:radial-gradient(300px 160px at 90% 0%,rgba(155,123,85,.35),transparent 70%),linear-gradient(160deg,#2a2620,#191714);
        border:1px solid rgba(255,255,255,.12);box-shadow:0 18px 50px rgba(0,0,0,.35)}
      .top{display:flex;align-items:center;gap:10px}
      .top img{width:30px;height:30px;border-radius:8px}
      .kick{font-size:10.5px;letter-spacing:.16em;text-transform:uppercase;color:rgba(244,239,230,.6)}
      .kick:before{content:"✦ ";color:#c9a57a}
      .title{font-family:JFItaliana,"Bodoni MT",Didot,serif;font-size:24px;line-height:1.1;margin:8px 0 2px}
      .job{font-size:12.5px;color:rgba(244,239,230,.72);margin-bottom:10px}
      .row{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
      button{font:inherit;cursor:pointer;border-radius:999px;padding:9px 16px;border:1px solid transparent;font-weight:600}
      .go{background:#f4efe6;color:#1d1b18;flex:1}
      .go:hover{background:#fff}
      .ok{background:transparent;color:#f4efe6;border-color:rgba(255,255,255,.4);font-weight:500}
      .ok:hover{background:rgba(255,255,255,.1)}
      .x{margin-left:auto;background:transparent;color:rgba(244,239,230,.55);padding:4px 8px;font-weight:400}
      .x:hover{color:#fff}
      .msg{font-size:12.5px;color:rgba(244,239,230,.85);margin-top:10px;display:none;line-height:1.5}
      .spin{display:inline-block;width:11px;height:11px;border:2px solid currentColor;border-right-color:transparent;border-radius:50%;animation:r .7s linear infinite;vertical-align:-1px;margin-right:6px}
      @keyframes r{to{transform:rotate(360deg)}}
    </style>
    <div class="box">
      <div class="top"><img src="${logo}" alt=""><div class="kick">jobslop</div><button class="x" id="x" title="Hide on this page">✕</button></div>
      <div class="title">Fill application</div>
      <div class="job" id="job">Your profile and CV, filled in for you.</div>
      <div class="row"><button class="go" id="go">⚡ Fill this form</button></div>
      <div class="msg" id="msg"></div>
      <div class="row" style="margin-top:10px">
        <button class="ok" id="next" hidden title="Jump to the next required field that's still empty">Next empty field →</button>
        <button class="ok" id="undo" hidden title="Put the form back the way it was">↶ Undo</button>
        <button class="ok" id="applied" hidden>✓ Mark as applied</button>
      </div>
    </div>`;
    document.documentElement.appendChild(host);
    ui = root;
    root.getElementById("x").onclick = () => { sessionStorage.setItem("jf-hide", "1"); host.remove(); };
    root.getElementById("go").onclick = () => {
      total = { n: 0, cv: false, left: 0 };
      showMsg('<span class="spin"></span>Filling in your details…', true);
      send({ type: "fillTab" });
    };
    root.getElementById("undo").onclick = () => {
      send({ type: "undoTab" });
      showMsg("Undone — the form is back the way it was (choices picked in searchable menus stay as they are).");
      ["undo", "next", "applied"].forEach((id) => root.getElementById(id).hidden = true);
    };
    let nextIdx = 0;
    root.getElementById("next").onclick = () => {
      const left = missing.filter((el) => !String(el.value || "").trim() || (el.type === "file" && !(el.files && el.files.length)));
      if (!left.length) { showMsg("All required fields have something in them now — check and submit when ready."); root.getElementById("next").hidden = true; return; }
      const el = left[nextIdx++ % left.length];
      el.scrollIntoView({ behavior: "smooth", block: "center" });
      setTimeout(() => el.focus(), 300);
    };
    root.getElementById("applied").onclick = async () => {
      await send({ type: "markApplied", url: activeJob && activeJob.url });
      showMsg("Marked as applied in jobslop ✓");
      root.getElementById("applied").hidden = true;
    };
    send({ type: "getData" }).then((d) => {
      if (!d) return;
      if (d.error === "bad-code" || (!d.profile && d.error)) {
        showMsg(d.error === "bad-code" ? "Not connected — click the extension icon and enter the code shown top-right in jobslop."
          : "Open jobslop once so the extension can connect.");
      }
      if (d.active) {
        activeJob = d.active;
        root.getElementById("job").textContent = `${d.active.title} · ${d.active.company}`;
      }
    });
  }

  function showMsg(t, isHtml) {
    if (!ui) return;
    const m = ui.getElementById("msg");
    if (isHtml) m.innerHTML = t; else m.textContent = t;
    m.style.display = "block";
  }

  function showResult() {
    if (!ui) return;
    const parts = [`Filled ${total.n} field${total.n === 1 ? "" : "s"}`];
    if (total.cv) parts.push("attached your CV");
    const leftTxt = total.left ? ` ${total.left} required field${total.left === 1 ? " is" : "s are"} still empty (amber outline).` : "";
    showMsg(parts.join(" and ") + "." + leftTxt + " Check everything (green outlines), then submit yourself." +
      (total.n === 0 && !total.cv ? " Nothing matched here — if the form opens after clicking Apply, click Fill again then." : ""));
    ui.getElementById("applied").hidden = !(total.n || total.cv);
    ui.getElementById("undo").hidden = !(total.n || total.cv);
    ui.getElementById("next").hidden = !total.left;
  }

  chrome.runtime.onMessage.addListener((msg, sender, reply) => {
    if (msg.type === "fill") {
      fill().then((r) => { send({ type: "frameResult", n: r.n, cv: r.cv, left: r.left }); reply(r); });
      return true;
    }
    if (msg.type === "undo") { undoFill(); }
    if (msg.type === "showButton" && TOP) buildUi();
    if (msg.type === "result" && TOP) {
      buildUi();
      total.n += msg.n || 0;
      total.cv = total.cv || !!msg.cv;
      total.left = (total.left || 0) + (msg.left || 0);
      showResult();
    }
  });

  // Watch for forms (many sites open the form in a pop-up after clicking Apply)
  let told = false, timer = null;
  function check() {
    if (told) return;
    if (looksLikeApplication()) { told = true; send({ type: "formHere" }); }
  }
  setTimeout(check, 800);
  new MutationObserver(() => { clearTimeout(timer); timer = setTimeout(check, 1200); })
    .observe(document.documentElement, { childList: true, subtree: true });

  // ---- "Import from a LinkedIn link" in jobslop: the app opens your profile here, and this reads the page
  // you can see (you're signed in to LinkedIn in your own Chrome) and sends it to the app. Nothing else is read.
  const liClean = (arr) => arr.map((t) => (t || "").replace(/\s+/g, " ").trim()).filter(Boolean);
  const liAll = (el) => {
    const spans = [...el.querySelectorAll('span[aria-hidden="true"]')];
    return liClean(spans.length ? spans.map((s) => s.innerText || s.textContent) : (el.innerText || el.textContent || "").split("\n"));
  };
  const liOwn = (li) => {                       // the item's own text, not that of the items inside it
    const spans = [...li.querySelectorAll('span[aria-hidden="true"]')].filter((s) => s.closest("li") === li);
    if (spans.length) return liClean(spans.map((s) => s.innerText || s.textContent));
    const c = li.cloneNode(true);
    c.querySelectorAll("li").forEach((x) => x.remove());
    return liClean((c.innerText || c.textContent || "").split("\n"));
  };
  function liSection(id) {
    const a = document.getElementById(id);
    return (a && a.closest("section")) || [...document.querySelectorAll("main section")]
      .find((s) => new RegExp("^\\s*" + id + "\\b", "i").test(((s.querySelector("h2") || {}).innerText || "").trim())) || null;
  }
  function liItems(sec) {
    return sec ? [...sec.querySelectorAll("li")].filter((li) => { const up = li.parentElement.closest("li"); return !up || !sec.contains(up); }) : [];
  }
  function scrapeLinkedIn() {
    const h1 = document.querySelector("main h1") || document.querySelector("h1");
    if (!h1) return null;
    const topSec = h1.closest("section") || h1.parentElement;
    const experience = liItems(liSection("experience")).map((li) => ({
      lines: liOwn(li),
      roles: [...li.querySelectorAll("li")].filter((x) => x.parentElement.closest("li") === li).map(liAll),
    }));
    return {
      name: (h1.innerText || h1.textContent || "").trim(),
      top: liClean((topSec.innerText || topSec.textContent || "").split("\n")).slice(0, 20),
      experience,
      education: liItems(liSection("education")).map(liAll),
      skills: liItems(liSection("skills")).map((li) => liOwn(li)[0]).filter(Boolean),
    };
  }
  async function readLinkedIn() {
    for (let i = 0; i < 40 && !document.querySelector("main h1"); i++) await sleep(500);
    if (!document.querySelector("main h1")) return null;
    const y = window.scrollY;                    // the lower sections only load as you scroll
    for (let i = 1; i <= 8; i++) { window.scrollTo(0, document.body.scrollHeight * i / 8); await sleep(600); }
    window.scrollTo(0, y);
    await sleep(300);
    return scrapeLinkedIn();
  }
  function liBanner(text) {
    let host = document.getElementById("jobslop-li");
    if (!host) {
      host = document.createElement("div");
      host.id = "jobslop-li";
      host.style.cssText = "position:fixed;top:16px;right:16px;z-index:2147483647;max-width:340px;padding:12px 16px;border-radius:14px;" +
        "background:#1d1b18;color:#f4efe6;font:500 14px/1.4 system-ui,sans-serif;box-shadow:0 10px 30px rgba(0,0,0,.3)";
      document.documentElement.appendChild(host);
    }
    host.textContent = text;
  }
  async function liCheck() {
    const r = await send({ type: "liWanted" });
    if (!r || !r.url) return;
    if (/^\/(authwall|login|uas|checkpoint|signup)/.test(location.pathname)) {
      await send({ type: "liFound", error: "Sign in to LinkedIn in Chrome first, then press Import again in jobslop." });
      return liBanner("jobslop: sign in to LinkedIn, then press Import again in the app.");
    }
    const norm = (p) => decodeURIComponent(p).replace(/\/+$/, "").toLowerCase();
    if (norm(new URL(r.url).pathname) !== norm(location.pathname)) return;
    liBanner("jobslop is reading your profile… (keep this tab open a few seconds)");
    const page = await readLinkedIn();
    const ok = await send(page ? { type: "liFound", page: { ...page, url: location.href } }
      : { type: "liFound", error: "Couldn't find a profile on that LinkedIn page." });
    liBanner(ok ? "Sent to jobslop ✓ Switch back to the app to check it and add it to your profile."
      : "Couldn't reach jobslop — is the app open?");
  }
  if (TOP && /(^|\.)linkedin\.com$/.test(location.hostname)) setTimeout(liCheck, 1200);

  // Expose for testing in a page without the extension
  window.__jobFinderTest = { describe, keyFor, fields, fill, undoFill, looksLikeApplication, scrapeLinkedIn,
    // pure helpers, used by the automated tests (tests/extension.test.js)
    clean, optionScore, bestChoice, choiceKey, alternatives, days, range, jobFieldKey, dateFor };
})();
