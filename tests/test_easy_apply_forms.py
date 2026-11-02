"""Easy apply on 12 different kinds of application form.

Each form below is a small practice page built the way a particular kind of jobs site builds its
forms (labels next to boxes, boxes inside labels, field names only, searchable drop-downs, pop-up
lists, tables, hidden steps, web components, other languages...). Every page is opened in Chrome
(headless, nothing appears on screen) with the real extension script and a test profile, "Fill" is
run, and the test checks what was typed, picked, ticked and attached - and what was left alone.

Each page takes about a second.
Skipped, with a note, if Chrome isn't installed.
"""
import base64
import html
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from support import ROOT, TMP
from test_extension import find_chrome

UK = {
    "first_name": "Sarah", "middle_name": "Jane", "last_name": "de Vries", "email": "sarah@example.com",
    "phone": "07911 123456", "address1": "12 Elm Grove", "address2": "Flat 3", "city": "Coventry",
    "postcode": "CV1 2AB", "county": "West Midlands", "country": "United Kingdom",
    "linkedin": "https://linkedin.com/in/sarah", "github": "https://github.com/sarahdv", "website": "",
    "right_to_work": "Yes", "needs_sponsorship": "No", "over_18": "Yes", "willing_to_relocate": "Yes",
    "driving_licence": "Yes", "years_experience": "4", "highest_qualification": "BSc", "notice_period": "1 month",
    "salary": "35000", "auto_consent": "yes",
    "jobs": [{"title": "Gameplay Programmer", "company": "Rare", "start": "Mar 2021", "end": "Present",
              "location": "Twycross", "description": "Built the combat systems"},
             {"title": "Junior Programmer", "company": "Codemasters", "start": "Jul 2018", "end": "Feb 2021"}],
}
US = {
    "first_name": "Jordan", "last_name": "Lee", "email": "jordan@example.com", "phone": "512 555 0134",
    "address1": "100 Congress Ave", "city": "Austin", "county": "TX", "postcode": "78701", "country": "United States",
    "right_to_work": "Yes", "needs_sponsorship": "No", "years_experience": "6", "highest_qualification": "Master's",
    "salary": "90000", "auto_consent": "",
}
CV = {"data": base64.b64encode(b"%PDF-1.4 test cv").decode(), "name": "CV.pdf", "type": "application/pdf"}

# a pop-up list: clicking the button (or typing in the box) shows options; clicking one picks it
LISTBOX_JS = """
function listbox(trigger, options, typed) {
  const list = document.createElement('div');
  trigger.insertAdjacentElement('afterend', list);
  const show = (filter) => {
    list.innerHTML = '';
    options.filter((o) => o.toLowerCase().includes((filter || '').toLowerCase())).forEach((o) => {
      const d = document.createElement('div');
      d.setAttribute('role', 'option');
      d.setAttribute('data-automation-id', 'promptOption');
      d.className = 'select__option';
      d.textContent = o;
      d.addEventListener('click', () => {
        list.innerHTML = '';
        if (typed) {           // react-select style: the box empties and the choice is shown next to it
          trigger.value = '';
          const sv = document.createElement('div');
          sv.className = 'select__single-value';
          sv.dataset.out = '';
          sv.dataset.t = trigger.id + '_chosen';
          sv.textContent = o;
          trigger.parentElement.prepend(sv);
        } else trigger.textContent = o;
      });
      list.appendChild(d);
    });
  };
  if (typed) { trigger.addEventListener('input', () => show(trigger.value)); trigger.addEventListener('focus', () => show('')); }
  else trigger.addEventListener('click', () => show(''));
}
"""

FORMS = {}

# 1. Greenhouse style: <label for>, field names like job_application[first_name], a searchable
#    country box (react-select), yes/no drop-downs, separate CV and cover letter uploads
FORMS["greenhouse"] = dict(profile=UK, html="""
<form id="application_form">
  <div class="field"><label for="first_name">First Name <span>*</span></label>
    <input type="text" id="first_name" name="job_application[first_name]" aria-required="true"></div>
  <div class="field"><label for="last_name">Last Name <span>*</span></label>
    <input type="text" id="last_name" name="job_application[last_name]" aria-required="true"></div>
  <div class="field"><label for="email">Email <span>*</span></label>
    <input type="text" id="email" name="job_application[email]"></div>
  <div class="field"><label for="phone">Phone</label><input type="text" id="phone" name="job_application[phone]"></div>
  <div class="field"><label for="resume">Resume/CV</label><input type="file" id="resume"></div>
  <div class="field"><label for="cover">Cover Letter</label><input type="file" id="cover"></div>
  <div class="field"><label for="q_company">Current Company</label><input type="text" id="q_company"></div>
  <div class="field"><label for="q_li">LinkedIn Profile</label><input type="text" id="q_li"></div>
  <div class="field"><label for="q_rtw">Are you legally authorized to work in the United Kingdom? *</label>
    <select id="q_rtw"><option value="">--</option><option value="1">Yes</option><option value="0">No</option></select></div>
  <div class="field"><label for="q_spon">Will you now or in the future require visa sponsorship? *</label>
    <select id="q_spon"><option value="">--</option><option value="1">Yes</option><option value="0">No</option></select></div>
  <div class="field"><label id="country_label" for="country">Country</label>
    <div class="select__control"><div class="select__value-container">
      <input id="country" role="combobox" aria-autocomplete="list" aria-labelledby="country_label"></div></div></div>
  <button type="submit">Submit Application</button>
</form>
<script>listbox(document.getElementById('country'), ['Ireland', 'Netherlands', 'United Kingdom', 'United States'], true);</script>
""")

# 2. Lever style: boxes inside <label>, recognised by their name= (name, org, urls[LinkedIn]...)
FORMS["lever"] = dict(profile=UK, html="""
<form id="application-form"><ul>
  <li><label><div class="application-label">Resume/CV ✱</div><input type="file" name="resume" data-t="resume"></label></li>
  <li><label><div class="application-label">Full name ✱</div><input type="text" name="name" data-t="name"></label></li>
  <li><label><div class="application-label">Email ✱</div><input type="email" name="email" data-t="email"></label></li>
  <li><label><div class="application-label">Phone</div><input type="text" name="phone" data-t="phone"></label></li>
  <li><label><div class="application-label">Current location</div><input type="text" name="location" data-t="location"></label></li>
  <li><label><div class="application-label">Current company</div><input type="text" name="org" data-t="org"></label></li>
  <li><label><div class="application-label">LinkedIn URL</div><input type="text" name="urls[LinkedIn]" data-t="linkedin"></label></li>
  <li><label><div class="application-label">GitHub URL</div><input type="text" name="urls[GitHub]" data-t="github"></label></li>
  <li><label><div class="application-label">Portfolio URL</div><input type="text" name="urls[Portfolio]" data-t="portfolio"></label></li>
  <li><label><div class="application-label">Additional information</div><textarea name="comments" data-t="comments"></textarea></label></li>
</ul><button type="submit">Submit application</button></form>
""")

# 3. Workday style: data-automation-id names and pop-up list buttons ("Select One")
FORMS["workday"] = dict(profile=UK, html="""
<form data-automation-id="applyFlowMyInfoPage">
  <label for="wd_fn">Given Name(s)*</label><input id="wd_fn" data-automation-id="legalNameSection_firstName" aria-required="true">
  <label for="wd_ln">Family Name*</label><input id="wd_ln" data-automation-id="legalNameSection_lastName" aria-required="true">
  <label for="wd_a1">Address Line 1</label><input id="wd_a1" data-automation-id="addressSection_addressLine1">
  <label for="wd_city">City</label><input id="wd_city" data-automation-id="addressSection_city">
  <label for="wd_pc">Postal Code</label><input id="wd_pc" data-automation-id="addressSection_postalCode">
  <label for="wd_email">Email Address</label><input id="wd_email" data-automation-id="email">
  <label for="wd_phone">Phone Number</label><input id="wd_phone" data-automation-id="phone-number">
  <label id="wd_country_lbl">Country*</label>
  <button type="button" id="wd_country" aria-haspopup="listbox" aria-labelledby="wd_country_lbl" data-out>Select One</button>
  <label id="wd_dev_lbl">Phone Device Type</label>
  <button type="button" id="wd_dev" aria-haspopup="listbox" aria-labelledby="wd_dev_lbl" data-out>Select One</button>
  <label id="wd_src_lbl">How Did You Hear About Us?</label>
  <button type="button" id="wd_src" aria-haspopup="listbox" aria-labelledby="wd_src_lbl" data-out>Select One</button>
  <button type="submit">Save and Continue</button>
</form>
<script>
listbox(document.getElementById('wd_country'), ['Netherlands', 'United Kingdom', 'United States of America']);
listbox(document.getElementById('wd_dev'), ['Landline', 'Mobile']);
listbox(document.getElementById('wd_src'), ['LinkedIn', 'Job board', 'Friend']);
</script>
""")

# 4. LinkedIn Easy Apply style: a pop-up with a phone country code list, an email drop-down,
#    screener questions as drop-downs and radio buttons, and a "Follow the company" box
FORMS["linkedin"] = dict(profile=UK, html="""
<div role="dialog" class="easy-apply-modal"><form>
  <h3>Contact info</h3>
  <div><label for="li_fn">First name</label><input id="li_fn" required></div>
  <div><label for="li_ln">Last name</label><input id="li_ln" required></div>
  <div><label for="li_cc">Phone country code</label>
    <select id="li_cc" required><option>Select an option</option><option>Netherlands (+31)</option>
      <option>United Kingdom (+44)</option><option>United States (+1)</option></select></div>
  <div><label for="li_phone">Mobile phone number</label><input id="li_phone" required></div>
  <div><label for="li_email">Email address</label>
    <select id="li_email"><option>Select an option</option><option>sarah@example.com</option></select></div>
  <h3>Additional questions</h3>
  <div><label for="li_years">How many years of work experience do you have with C++?</label><input id="li_years" type="text"></div>
  <div><label for="li_lic">Do you have a valid driver's license?</label>
    <select id="li_lic"><option>Select an option</option><option>Yes</option><option>No</option></select></div>
  <fieldset><legend>Will you now or in the future require sponsorship for employment visa status?</legend>
    <input type="radio" name="li_spon" id="li_spon_y" value="Yes"><label for="li_spon_y">Yes</label>
    <input type="radio" name="li_spon" id="li_spon_n" value="No"><label for="li_spon_n">No</label></fieldset>
  <fieldset><legend>Are you comfortable commuting to this job's location?</legend>
    <input type="radio" name="li_comm" id="li_comm_y" value="Yes"><label for="li_comm_y">Yes</label>
    <input type="radio" name="li_comm" id="li_comm_n" value="No"><label for="li_comm_n">No</label></fieldset>
  <input type="checkbox" id="li_follow"><label for="li_follow">Follow Rare to stay up to date with their page.</label>
  <button type="submit">Submit application</button>
</form></div>
""")

# 5. Indeed style: placeholders and autocomplete= only (no labels), screener questions whose only
#    label is the text above them, and a second step that's still hidden
FORMS["indeed"] = dict(profile=UK, html="""
<form>
  <div id="step1">
    <input placeholder="First name" autocomplete="given-name" data-t="fn">
    <input placeholder="Last name" autocomplete="family-name" data-t="ln">
    <input type="email" placeholder="Email" autocomplete="email" data-t="email">
    <input type="tel" placeholder="Phone number (optional)" autocomplete="tel" data-t="phone">
    <input placeholder="City, County" autocomplete="address-level2" data-t="city">
    <input placeholder="Postcode" autocomplete="postal-code" data-t="pc">
    <div class="q">What is your notice period?<input name="question_1" data-t="notice"></div>
    <div class="q">How many years of Unreal Engine experience do you have?<input name="question_2" data-t="years"></div>
    <div class="q">Tell us about a project you are proud of.<textarea name="question_3" data-t="project"></textarea></div>
    <div class="q">Do you hold a full UK driving licence?
      <select name="question_4" data-t="licence"><option value="">Select</option><option>Yes</option><option>No</option></select></div>
    <div class="q"><p>Are you willing to relocate?</p>
      <label><input type="radio" name="question_5" value="1" data-t="reloc_yes"> Yes</label>
      <label><input type="radio" name="question_5" value="0" data-t="reloc_no"> No</label></div>
  </div>
  <div id="step2" style="display:none">
    <label>Job title <input data-t="hidden_title"></label>
    <label>Company <input data-t="hidden_company"></label>
  </div>
  <button type="submit">Continue</button>
</form>
""")

# 6. iCIMS / Taleo style: an old-fashioned table layout, a "Confirm email" box and "-- Select --"
FORMS["table"] = dict(profile=UK, html="""
<form><table>
  <tr><td><label for="t_fn">First Name:</label></td><td><input id="t_fn"></td></tr>
  <tr><td><label for="t_ln">Last Name:</label></td><td><input id="t_ln"></td></tr>
  <tr><td><label for="t_em">Email Address:</label></td><td><input id="t_em"></td></tr>
  <tr><td><label for="t_em2">Confirm Email Address:</label></td><td><input id="t_em2"></td></tr>
  <tr><td><label for="t_a1">Address 1:</label></td><td><input id="t_a1"></td></tr>
  <tr><td><label for="t_a2">Address 2:</label></td><td><input id="t_a2"></td></tr>
  <tr><td><label for="t_city">City:</label></td><td><input id="t_city"></td></tr>
  <tr><td><label for="t_cty">County / Region:</label></td><td><input id="t_cty"></td></tr>
  <tr><td><label for="t_pc">Postal Code:</label></td><td><input id="t_pc"></td></tr>
  <tr><td><label for="t_tel">Telephone:</label></td><td><input id="t_tel"></td></tr>
  <tr><td><label for="t_country">Country:</label></td><td><select id="t_country"><option value="-1">-- Select --</option>
    <option value="US">United States</option><option value="UK">United Kingdom</option></select></td></tr>
</table><input type="submit" value="Submit"></form>
""")

# 7. Ashby / SmartRecruiters style: required fields marked *, a drag-and-drop CV upload area,
#    questions with no profile answer (left empty and outlined), then Undo
FORMS["required"] = dict(profile=UK, undo=True, html="""
<form>
  <label for="r_name">Name *</label><input id="r_name" required>
  <label for="r_email">Email *</label><input id="r_email" type="email" required>
  <label for="r_site">Portfolio or website *</label><input id="r_site" required>
  <label for="r_why">Why do you want to join us? *</label><textarea id="r_why" required></textarea>
  <label for="r_pron">Pronouns</label><input id="r_pron">
  <div class="file-upload-dropzone" id="r_zone"><label for="r_cv">Upload your resume</label>
    <input type="file" id="r_cv" accept=".pdf"><span id="r_dropped" data-out></span></div>
  <button type="submit">Submit Application</button>
</form>
<script>
document.getElementById('r_zone').addEventListener('drop', (e) => {
  document.getElementById('r_dropped').textContent = e.dataTransfer.files[0].name;
});
</script>
""")

# 8. A Dutch form: voornaam / tussenvoegsel / achternaam, Ja/Nee answers, opleidingsniveau
FORMS["dutch"] = dict(profile=UK, lang="nl", html="""
<form>
  <label for="nl_fn">Voornaam</label><input id="nl_fn">
  <label for="nl_tv">Tussenvoegsel</label><input id="nl_tv">
  <label for="nl_ln">Achternaam</label><input id="nl_ln">
  <label for="nl_em">E-mailadres</label><input id="nl_em">
  <label for="nl_tel">Telefoonnummer</label><input id="nl_tel">
  <label for="nl_str">Straat en huisnummer</label><input id="nl_str">
  <label for="nl_pc">Postcode</label><input id="nl_pc">
  <label for="nl_wp">Woonplaats</label><input id="nl_wp">
  <label for="nl_opl">Opleidingsniveau</label>
  <select id="nl_opl"><option value="">Kies...</option><option value="mbo">MBO</option><option value="hbo">HBO</option>
    <option value="wo">WO (universitair)</option></select>
  <label for="nl_rb">Heb je rijbewijs B?</label>
  <select id="nl_rb"><option value="">Kies...</option><option value="j">Ja</option><option value="n">Nee</option></select>
  <fieldset><legend>Heb je een werkvergunning voor Nederland?</legend>
    <label><input type="radio" name="nl_wv" id="nl_wv_ja"> Ja</label>
    <label><input type="radio" name="nl_wv" id="nl_wv_nee"> Nee</label></fieldset>
  <label for="nl_mot">Motivatie</label><textarea id="nl_mot"></textarea>
  <label for="nl_gesl">Geslacht</label><select id="nl_gesl"><option value="">Kies...</option><option>Man</option><option>Vrouw</option></select>
  <label><input type="checkbox" id="nl_priv"> Ik ga akkoord met de privacyverklaring</label>
  <label><input type="checkbox" id="nl_news"> Ja, stuur mij de nieuwsbrief</label>
  <button type="submit">Solliciteer</button>
</form>
""")

# 9. A German form: Vorname / Nachname / PLZ / Ort, a country list in German, notice period in
#    months, salary, Anschreiben, and three uploads (only the Lebenslauf gets the CV)
FORMS["german"] = dict(profile=UK, lang="de", html="""
<form>
  <label for="de_anr">Anrede</label><select id="de_anr"><option value="">Bitte wählen</option><option>Frau</option><option>Herr</option></select>
  <label for="de_fn">Vorname</label><input id="de_fn">
  <label for="de_ln">Nachname</label><input id="de_ln">
  <label for="de_em">E-Mail</label><input id="de_em">
  <label for="de_tel">Telefonnummer</label><input id="de_tel">
  <label for="de_str">Straße und Hausnummer</label><input id="de_str">
  <label for="de_plz">PLZ</label><input id="de_plz">
  <label for="de_ort">Ort</label><input id="de_ort">
  <label for="de_land">Land</label><select id="de_land"><option value="">Bitte wählen</option><option value="de">Deutschland</option>
    <option value="at">Österreich</option><option value="gb">Vereinigtes Königreich</option></select>
  <label for="de_kf">Kündigungsfrist</label><select id="de_kf"><option value="">Bitte wählen</option><option value="0">Sofort</option>
    <option value="1">1 Monat</option><option value="3">3 Monate</option></select>
  <label for="de_geh">Gehaltsvorstellung (brutto pro Jahr)</label><input id="de_geh">
  <label for="de_an">Anschreiben</label><textarea id="de_an"></textarea>
  <label for="de_foto">Foto</label><input type="file" id="de_foto">
  <label for="de_lv">Lebenslauf</label><input type="file" id="de_lv">
  <label for="de_zeug">Zeugnisse</label><input type="file" id="de_zeug">
  <label><input type="checkbox" id="de_ds"> Ich stimme der Datenschutzerklärung zu</label>
  <button type="submit">Bewerbung absenden</button>
</form>
""")

# 10. A US form: State, ZIP code, salary bands, degree list, and equal-opportunity (EEO) questions
#     that are always left for you; this profile hasn't allowed ticking consent boxes
FORMS["us"] = dict(profile=US, lang="en-US", html="""
<form>
  <label for="us_fn">First Name</label><input id="us_fn">
  <label for="us_ln">Last Name</label><input id="us_ln">
  <label for="us_em">Email</label><input id="us_em" type="email">
  <label for="us_ph">Phone</label><input id="us_ph" type="tel">
  <label for="us_a1">Street Address</label><input id="us_a1">
  <label for="us_city">City</label><input id="us_city">
  <label for="us_state">State</label><select id="us_state"><option value="">Select...</option><option value="CA">California</option>
    <option value="TX">Texas</option><option value="WA">Washington</option></select>
  <label for="us_zip">ZIP Code</label><input id="us_zip">
  <label for="us_country">Country</label><select id="us_country"><option value="">Select...</option><option>Canada</option>
    <option>Mexico</option><option>United States of America</option></select>
  <label for="us_sal">Desired Salary</label><select id="us_sal"><option value="">Select...</option>
    <option>$60,000 - $80,000</option><option>$80,000 - $100,000</option><option>$100,000+</option></select>
  <label for="us_deg">Highest Degree</label><select id="us_deg"><option value="">Select...</option><option>High school diploma</option>
    <option>Associate degree</option><option>Bachelor's degree</option><option>Master's degree</option><option>Doctorate</option></select>
  <fieldset><legend>Are you legally authorized to work in the United States?</legend>
    <label><input type="radio" name="us_auth" id="us_auth_y"> Yes</label>
    <label><input type="radio" name="us_auth" id="us_auth_n"> No</label></fieldset>
  <fieldset><legend>Are you a protected veteran?</legend>
    <label><input type="radio" name="us_vet" id="us_vet_y"> I identify as a protected veteran</label>
    <label><input type="radio" name="us_vet" id="us_vet_n"> I am not a protected veteran</label></fieldset>
  <fieldset><legend>Disability status</legend>
    <label><input type="radio" name="us_dis" id="us_dis_y"> Yes, I have a disability</label>
    <label><input type="radio" name="us_dis" id="us_dis_n"> No, I do not have a disability</label></fieldset>
  <label for="us_race">Race/Ethnicity</label><select id="us_race"><option value="">Select...</option><option>Asian</option>
    <option>White</option><option>Decline to self-identify</option></select>
  <label><input type="checkbox" id="us_terms"> I agree to the terms and conditions</label>
  <button type="submit">Apply</button>
</form>
""")

# 11. Employment history: one block per past job (title, company, from/to as month boxes or
#     month + year drop-downs), filled in profile order; a spare third block is left empty
MONTH_OPTS = '<option value="">Month</option>' + "".join(
    f'<option value="{i}">{m}</option>' for i, m in enumerate(
        ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
         "November", "December"], 1))
YEAR_OPTS = '<option value="">Year</option>' + "".join(f"<option>{y}</option>" for y in range(2026, 2009, -1))
FORMS["history"] = dict(profile=UK, html=f"""
<form>
  <label>First name <input data-t="fn"></label>
  <h3>Work experience</h3>
  <div class="job">
    <label>Job title <input data-t="t1"></label><label>Company <input data-t="c1"></label>
    <label>Location <input data-t="l1"></label>
    <label>From <input type="month" data-t="s1"></label><label>To <input type="month" data-t="e1"></label>
    <label><input type="checkbox" data-t="now1"> I currently work here</label>
    <label>Description <textarea data-t="d1"></textarea></label>
  </div>
  <div class="job">
    <label>Job title <input data-t="t2"></label><label>Company <input data-t="c2"></label>
    <label>Start month <select data-t="sm2">{MONTH_OPTS}</select></label>
    <label>Start year <select data-t="sy2">{YEAR_OPTS}</select></label>
    <label>End month <select data-t="em2">{MONTH_OPTS}</select></label>
    <label>End year <select data-t="ey2">{YEAR_OPTS}</select></label>
    <label>Description <textarea data-t="d2"></textarea></label>
  </div>
  <div class="job">
    <label>Job title <input data-t="t3"></label><label>Company <input data-t="c3"></label>
  </div>
  <button type="submit">Next</button>
</form>
""")

# 12. A form built as a web component (its boxes sit inside a shadow root)
FORMS["shadow"] = dict(profile=UK, html="""
<apply-form></apply-form>
<script>
customElements.define('apply-form', class extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' }).innerHTML = `
      <form>
        <label>First name <input data-t="fn"></label>
        <label>Last name <input data-t="ln"></label>
        <label>Email <input type="email" data-t="email"></label>
        <label for="x">Postcode <input data-t="pc"></label>
        <select data-t="country" aria-label="Country"><option value="">Select</option><option value="NL">Netherlands</option>
          <option value="GB">United Kingdom</option></select>
        <label><input type="checkbox" data-t="privacy"> I accept the privacy policy</label>
        <label>Resume <input type="file" data-t="cv"></label>
        <button type="submit">Apply</button>
      </form>`;
  }
});
</script>
""")

RUN_JS = """
const deep = (root, sel) => {
  const o = [...root.querySelectorAll(sel)];
  root.querySelectorAll('*').forEach((e) => { if (e.shadowRoot) o.push(...deep(e.shadowRoot, sel)); });
  return o;
};
const snap = () => {
  const o = {};
  deep(document, 'input, select, textarea, [data-out]').forEach((e) => {
    const k = e.dataset.t || e.id;
    if (!k || k === 'out') return;
    o[k] = e.matches('[data-out]') ? e.textContent.trim()
      : e.type === 'checkbox' || e.type === 'radio' ? e.checked
      : e.type === 'file' ? [...e.files].map((f) => f.name).join(',') : e.value;
  });
  return o;
};
let submitted = false;
document.addEventListener('submit', (e) => { submitted = true; e.preventDefault(); }, true);
window.addEventListener('load', async () => {
  const T = window.__jobFinderTest;
  const out = {};
  try {
    out.result = await T.fill();
    out.filled = snap();
    out.amber = deep(document, 'input, select, textarea').filter((e) => e.style.outline.includes('dashed'))
      .map((e) => e.dataset.t || e.id);
    if (UNDO) { T.undoFill(); out.undone = snap(); }
  } catch (e) { out.error = String(e && e.stack || e); }
  out.submitted = submitted;
  document.getElementById('out').textContent = JSON.stringify(out);
});
"""


def run_form(chrome, name, spec):
    work = Path(TMP) / "easy-apply" / name
    work.mkdir(parents=True, exist_ok=True)
    shutil.copy(ROOT / "chrome-extension" / "content.js", work / "content.js")
    data = {"profile": spec["profile"], "full_name": f'{spec["profile"]["first_name"]} {spec["profile"]["last_name"]}',
            "cover_letter": "Dear hiring team, ..."}
    stub = ("window.chrome={runtime:{lastError:null,onMessage:{addListener(){}},sendMessage(msg,cb){"
            f"const r=msg.type==='getData'?{json.dumps(data)}:msg.type==='getCv'?{json.dumps(CV)}:null;"
            "setTimeout(()=>cb&&cb(r),0)}}};")
    run = f"const UNDO={'true' if spec.get('undo') else 'false'};" + RUN_JS
    page = (f"<!doctype html><html lang='{spec.get('lang', 'en-GB')}'><head><meta charset='utf-8'>"
            f"<script>{stub}{LISTBOX_JS}</script></head><body>{spec['html']}"
            f"<pre id='out'></pre><script src='content.js'></script><script>{run}</script></body></html>")
    (work / "form.html").write_text(page, encoding="utf-8")
    proc = subprocess.run([chrome, "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
                           f"--user-data-dir={work / 'chrome-profile'}", "--allow-file-access-from-files",
                           "--window-size=1280,2000", "--virtual-time-budget=30000", "--dump-dom",
                           (work / "form.html").as_uri()], capture_output=True, timeout=120)
    m = re.search(r'<pre id="out">(.*?)</pre>', proc.stdout.decode("utf-8", "replace"), re.S)
    if not m or not m.group(1).strip():
        return {"error": "the page didn't report back; Chrome said: " + proc.stderr.decode("utf-8", "replace")[-800:]}
    return json.loads(html.unescape(m.group(1)))


@pytest.fixture(scope="module")
def forms():
    chrome = find_chrome()
    if not chrome:
        pytest.skip("Chrome isn't installed, so the Easy apply form tests can't run")
    # one at a time: several headless Chromes starting together can stall each other
    return {name: run_form(chrome, name, spec) for name, spec in FORMS.items()}


def get(forms, name):
    out = forms[name]
    assert "error" not in out, f"{name}: {out.get('error')}"
    assert not out["submitted"], f"{name}: the extension must never submit the form"
    return out["filled"]


def test_every_form_was_filled_and_never_submitted(forms):
    assert len(FORMS) == 12
    for name in FORMS:
        get(forms, name)
        assert forms[name]["result"]["n"] > 0, f"{name}: nothing was filled"


def test_greenhouse_style(forms):
    o = get(forms, "greenhouse")
    assert (o["first_name"], o["last_name"], o["email"], o["phone"]) == ("Sarah", "de Vries", "sarah@example.com", "07911 123456")
    assert o["q_company"] == "Rare", "current company comes from your most recent job"
    assert o["q_li"] == "https://linkedin.com/in/sarah"
    assert (o["q_rtw"], o["q_spon"]) == ("1", "0"), "right to work: Yes, sponsorship: No"
    assert o["country_chosen"] == "United Kingdom", "searchable country box: typed, then the match clicked"
    assert (o["resume"], o["cover"]) == ("CV.pdf", ""), "the CV goes in the CV upload, not the cover letter one"
    assert forms["greenhouse"]["result"]["cv"] is True


def test_lever_style(forms):
    o = get(forms, "lever")
    assert o["name"] == "Sarah Jane de Vries", "a full name box gets your middle name too"
    assert (o["email"], o["phone"], o["location"], o["org"]) == ("sarah@example.com", "07911 123456", "Coventry", "Rare")
    assert (o["linkedin"], o["github"]) == ("https://linkedin.com/in/sarah", "https://github.com/sarahdv")
    assert o["portfolio"] == "", "no website in the profile: left empty"
    assert o["comments"] == "", "free-text questions aren't guessed"
    assert o["resume"] == "CV.pdf"


def test_workday_style(forms):
    o = get(forms, "workday")
    assert (o["wd_fn"], o["wd_ln"]) == ("Sarah", "de Vries")
    assert (o["wd_a1"], o["wd_city"], o["wd_pc"]) == ("12 Elm Grove", "Coventry", "CV1 2AB")
    assert (o["wd_email"], o["wd_phone"]) == ("sarah@example.com", "07911 123456")
    assert o["wd_country"] == "United Kingdom", "pop-up list: opened and the right option clicked"
    assert o["wd_dev"] == "Select One", "no matching option: left as it was"
    assert o["wd_src"] == "Select One", "'How did you hear about us?' is left for you"


def test_linkedin_easy_apply_style(forms):
    o = get(forms, "linkedin")
    assert (o["li_fn"], o["li_ln"], o["li_phone"]) == ("Sarah", "de Vries", "07911 123456")
    assert o["li_cc"] == "United Kingdom (+44)", "phone country code picked from your country"
    assert o["li_email"] == "sarah@example.com", "email chosen from the drop-down"
    assert o["li_years"] == "4"
    assert o["li_lic"] == "Yes"
    assert (o["li_spon_y"], o["li_spon_n"]) == (False, True)
    assert not (o["li_comm_y"] or o["li_comm_n"]), "questions the profile can't answer are left for you"
    assert o["li_follow"] is False, "'Follow the company' is never ticked"


def test_indeed_style(forms):
    o = get(forms, "indeed")
    assert (o["fn"], o["ln"], o["email"], o["phone"]) == ("Sarah", "de Vries", "sarah@example.com", "07911 123456")
    assert (o["city"], o["pc"]) == ("Coventry", "CV1 2AB"), "recognised by autocomplete= when there's no label"
    assert o["notice"] == "1 month", "question text above an unnamed box is read"
    assert o["years"] == "4"
    assert o["project"] == ""
    assert o["licence"] == "Yes"
    assert (o["reloc_yes"], o["reloc_no"]) == (True, False)
    assert (o["hidden_title"], o["hidden_company"]) == ("", ""), "boxes on a hidden step aren't touched"


def test_table_layout(forms):
    o = get(forms, "table")
    assert (o["t_fn"], o["t_ln"]) == ("Sarah", "de Vries")
    assert o["t_em"] == o["t_em2"] == "sarah@example.com", "'Confirm email' gets the same address"
    assert (o["t_a1"], o["t_a2"], o["t_city"], o["t_cty"], o["t_pc"]) == (
        "12 Elm Grove", "Flat 3", "Coventry", "West Midlands", "CV1 2AB")
    assert o["t_tel"] == "07911 123456"
    assert o["t_country"] == "UK"


def test_required_fields_upload_area_and_undo(forms):
    out = forms["required"]
    o = get(forms, "required")
    assert (o["r_name"], o["r_email"]) == ("Sarah Jane de Vries", "sarah@example.com")
    assert o["r_pron"] == "", "pronouns are personal: left for you"
    assert o["r_cv"] == "CV.pdf" and o["r_dropped"] == "CV.pdf", "the CV is also dropped on the upload area"
    assert out["result"]["left"] == 2
    assert sorted(out["amber"]) == ["r_site", "r_why"], "required boxes still empty are outlined"
    u = out["undone"]
    assert (u["r_name"], u["r_email"], u["r_cv"]) == ("", "", ""), "Undo empties what was filled"


def test_dutch_form(forms):
    o = get(forms, "dutch")
    assert (o["nl_fn"], o["nl_tv"], o["nl_ln"]) == ("Sarah", "de", "Vries")
    assert (o["nl_em"], o["nl_tel"], o["nl_str"]) == ("sarah@example.com", "07911 123456", "12 Elm Grove")
    assert (o["nl_pc"], o["nl_wp"]) == ("CV1 2AB", "Coventry")
    assert o["nl_opl"] == "hbo", "BSc is HBO in the Dutch system"
    assert o["nl_rb"] == "j"
    assert (o["nl_wv_ja"], o["nl_wv_nee"]) == (True, False)
    assert o["nl_mot"] == "Dear hiring team, ..."
    assert o["nl_gesl"] == ""
    assert (o["nl_priv"], o["nl_news"]) == (True, False)


def test_german_form(forms):
    o = get(forms, "german")
    assert o["de_anr"] == "", "Frau / Herr isn't guessed"
    assert (o["de_fn"], o["de_ln"], o["de_em"], o["de_tel"]) == ("Sarah", "de Vries", "sarah@example.com", "07911 123456")
    assert (o["de_str"], o["de_plz"], o["de_ort"]) == ("12 Elm Grove", "CV1 2AB", "Coventry")
    assert o["de_land"] == "gb", "United Kingdom found as 'Vereinigtes Königreich'"
    assert o["de_kf"] == "1", "1 month = 1 Monat"
    assert o["de_geh"] == "35000"
    assert o["de_an"] == "Dear hiring team, ..."
    assert (o["de_foto"], o["de_lv"], o["de_zeug"]) == ("", "CV.pdf", ""), "the CV goes in Lebenslauf only"
    assert o["de_ds"] is True


def test_us_form(forms):
    o = get(forms, "us")
    assert (o["us_fn"], o["us_ln"], o["us_em"], o["us_ph"]) == ("Jordan", "Lee", "jordan@example.com", "512 555 0134")
    assert (o["us_a1"], o["us_city"], o["us_zip"]) == ("100 Congress Ave", "Austin", "78701")
    assert o["us_state"] == "TX", "TX in the profile picks Texas"
    assert o["us_country"] == "United States of America"
    assert o["us_sal"] == "$80,000 - $100,000"
    assert o["us_deg"] == "Master's degree"
    assert (o["us_auth_y"], o["us_auth_n"]) == (True, False)
    assert not any(o[k] for k in ("us_vet_y", "us_vet_n", "us_dis_y", "us_dis_n")), "EEO questions are left for you"
    assert o["us_race"] == ""
    assert o["us_terms"] is False, "consent boxes stay unticked unless your profile allows it"


def test_employment_history(forms):
    o = get(forms, "history")
    assert o["fn"] == "Sarah"
    assert (o["t1"], o["c1"], o["l1"]) == ("Gameplay Programmer", "Rare", "Twycross")
    assert (o["s1"], o["e1"]) == ("2021-03", ""), "a job you're still in has no end date"
    assert o["d1"] == "Built the combat systems"
    assert (o["t2"], o["c2"]) == ("Junior Programmer", "Codemasters")
    assert (o["sm2"], o["sy2"], o["em2"], o["ey2"]) == ("7", "2018", "2", "2021"), "month + year drop-downs"
    assert o["d2"] == ""
    assert (o["t3"], o["c3"]) == ("", ""), "more job blocks than jobs: the spare one is left empty"
    assert o["now1"] is False


def test_web_component_form(forms):
    o = get(forms, "shadow")
    assert (o["fn"], o["ln"], o["email"], o["pc"]) == ("Sarah", "de Vries", "sarah@example.com", "CV1 2AB")
    assert o["country"] == "GB"
    assert o["privacy"] is True
    assert o["cv"] == "CV.pdf"
