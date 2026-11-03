// Tests for the Chrome extension's form logic (which profile value goes in which box, and which
// choice to pick in drop-downs / radio buttons). Run with:  node --test tests
// The extension script is loaded into a small fake browser, so no Chrome is needed.
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

function loadExtension(lang = "en") {
  const window = {};
  window.window = window;
  window.top = window;
  const sandbox = {
    window,
    document: { documentElement: { lang }, querySelector: () => null, querySelectorAll: () => [], getElementById: () => null },
    navigator: { language: lang },
    location: { hostname: "example.com", pathname: "/", href: "https://example.com/" },
    chrome: { runtime: { sendMessage: () => {}, onMessage: { addListener: () => {} } } },
    MutationObserver: class { observe() {} },
    setTimeout: () => 0, clearTimeout: () => {},
    CSS: { escape: (s) => s },
  };
  vm.createContext(sandbox);
  vm.runInContext(fs.readFileSync(path.join(__dirname, "..", "chrome-extension", "content.js"), "utf8"), sandbox);
  return sandbox.window.__jobFinderTest;
}

const ext = loadExtension();
// a stand-in form field: just the attributes keyFor() looks at
const field = (attrs = {}) => ({ getAttribute: (k) => attrs[k] ?? null });
const keyOf = (label, attrs) => ext.keyFor(field(attrs), ext.clean(label).toLowerCase());

test("labels map to the right profile fields", () => {
  const cases = {
    "First name": "first_name", "Given name": "first_name", "Voornaam": "first_name", "Prénom": "first_name",
    "Middle name": "middle_name", "Last name": "last_name", "Surname": "last_name", "Achternaam": "last_name",
    "Tussenvoegsel": "name_prefix", "Email address": "email", "Mobile phone": "phone", "Telefoonnummer": "phone",
    "Country dialing code": "phone_country", "Postcode": "postcode", "ZIP code": "postcode", "Town / City": "city",
    "County": "county", "State": "county", "Country": "country", "Address line 1": "address1",
    "Address line 2": "address2", "LinkedIn profile": "linkedin", "Portfolio website": "website",
    "Current employer": "current_company", "Job title": "current_title", "Expected salary": "salary",
    "Notice period": "notice_period", "Years of experience": "years_experience",
    "Highest level of education": "highest_qualification", "Field of study": "degree_subject",
    "University": "university", "Do you have the right to work in the UK?": "right_to_work",
    "Will you require visa sponsorship?": "needs_sponsorship", "Are you willing to relocate?": "willing_to_relocate",
    "Do you hold a full driving licence?": "driving_licence", "Full name": "full_name", "Cover letter": "cover_letter",
    "Are you 18 years or older?": "over_18",
    "E-Mail": "email", "Phone country code": "phone_country", "Highest degree": "highest_qualification",
  };
  for (const [label, key] of Object.entries(cases)) assert.equal(keyOf(label), key, label);
});

test("personal and diversity questions are left for you", () => {
  for (const label of ["Gender", "Ethnicity", "Date of birth", "Do you have a disability?", "Veteran status",
    "How did you hear about us?", "Password", "Geslacht", "Search jobs"]) {
    assert.equal(keyOf(label), null, label);
  }
});

test("known form systems are recognised by field name", () => {
  assert.equal(keyOf("anything", { name: "urls[LinkedIn]" }), "linkedin");               // Lever
  assert.equal(keyOf("x", { "data-automation-id": "legalNameSection_firstName" }), "first_name"); // Workday
  assert.equal(keyOf("x", { autocomplete: "section-1 family-name" }), "last_name");      // standard autocomplete
  assert.equal(keyOf("x", { autocomplete: "off" }), null);
});

test("yes/no answers in several languages", () => {
  assert.equal(ext.optionScore("right_to_work", "Yes", "Yes"), 10);
  assert.equal(ext.optionScore("right_to_work", "Yes", "No"), 0);
  assert.equal(ext.optionScore("right_to_work", "Ja", "Ja"), 10);
  assert.equal(ext.optionScore("needs_sponsorship", "No", "Nee"), 10);
  assert.ok(ext.optionScore("right_to_work", "Yes", "Yes, I have the right to work") >= 7);
  assert.equal(ext.optionScore("right_to_work", "Yes", "No, I don't"), 0);
  assert.equal(ext.optionScore("right_to_work", "Yes", "Please select"), 0);
});

test("ranges: years of experience and salary", () => {
  const pick = (key, value, options) => {
    const best = ext.bestChoice(key, value, options.map((o) => [o, o]));
    return best;
  };
  assert.equal(pick("years_experience", "4", ["Less than 1 year", "1-3 years", "3-5 years", "5+ years"]), "3-5 years");
  assert.equal(pick("years_experience", "7", ["0-2", "3-5", "6-10", "10+"]), "6-10");
  assert.equal(pick("years_experience", "12", ["0-2", "3-5", "6-10", "10+"]), "10+");
  assert.equal(pick("salary", "35000", ["£20k-£30k", "£30k-£40k", "£40k+"]), "£30k-£40k");
  assert.deepEqual(Array.from(ext.range("3-5 years")), [3, 5]);
  assert.deepEqual(Array.from(ext.range("10+")), [10, Infinity]);
  assert.deepEqual(Array.from(ext.range("less than 1")), [0, 1]);
  assert.deepEqual(Array.from(ext.range("No experience")), [0, 0.5]);
});

test("notice periods", () => {
  assert.equal(ext.days("Immediately"), 0);
  assert.equal(ext.days("1 month"), 30);
  assert.equal(ext.days("4 weeks"), 28);
  const best = ext.bestChoice("notice_period", "1 month", ["Immediately", "1 week", "2 weeks", "1 month", "3 months"].map((o) => [o, o]));
  assert.equal(best, "1 month");
  const near = ext.bestChoice("notice_period", "4 weeks", ["Immediately", "1 month", "3 months"].map((o) => [o, o]));
  assert.equal(near, "1 month", "closest option wins");
});

test("qualifications", () => {
  const opts = ["GCSE", "A-Level", "Bachelor's degree", "Master's degree", "PhD"].map((o) => [o, o]);
  assert.equal(ext.bestChoice("highest_qualification", "BSc", opts), "Bachelor's degree");
  assert.equal(ext.bestChoice("highest_qualification", "MSc", opts), "Master's degree");
  assert.equal(ext.bestChoice("highest_qualification", "HBO", [["HBO", "HBO"], ["WO", "WO"]]), "HBO");
});

test("countries, states and dialling codes", () => {
  const countries = ["Netherlands", "United Kingdom", "United States"].map((o) => [o, o]);
  assert.equal(ext.bestChoice("country", "UK", countries), "United Kingdom");
  assert.equal(ext.bestChoice("country", "United Kingdom", [["Verenigd Koninkrijk", "Verenigd Koninkrijk"], ["België", "België"]]),
    "Verenigd Koninkrijk");
  assert.equal(ext.bestChoice("county", "FL", [["Florida", "Florida"], ["Georgia", "Georgia"]]), "Florida");
  assert.equal(ext.bestChoice("county", "Texas", [["TX", "TX"], ["FL", "FL"]]), "TX");
  assert.equal(ext.bestChoice("phone_country", "United Kingdom", [["+1 United States", "+1 United States"],
    ["+44 United Kingdom", "+44 United Kingdom"], ["+31 Netherlands", "+31 Netherlands"]]), "+44 United Kingdom");
  assert.deepEqual(Array.from(ext.alternatives("country", "gb").slice(0, 2)), ["united kingdom", "uk"]);
});

test("plain text choices", () => {
  assert.equal(ext.bestChoice("city", "Birmingham", [["London", "London"], ["Birmingham", "Birmingham"]]), "Birmingham");
  assert.equal(ext.bestChoice("city", "Birmingham", [["London", "London"], ["Leeds", "Leeds"]]), null, "no weak guesses");
});

test("radio-button questions", () => {
  assert.equal(ext.choiceKey("are you legally authorised to work in the uk?"), "right_to_work");
  assert.equal(ext.choiceKey("are you 18 or over?"), "over_18");
  assert.equal(ext.choiceKey("what is your gender?"), null);
  assert.equal(ext.choiceKey("what is your favourite colour?"), null);
});

test("past jobs: dates and which box is which", () => {
  assert.equal(ext.dateFor({ type: "month" }, "Jul 2022"), "2022-07");
  assert.equal(ext.dateFor({ type: "date" }, "March 2021"), "2021-03-01");
  assert.equal(ext.dateFor({ type: "text", placeholder: "MM/YYYY" }, "Jun 2019"), "06/2019");
  assert.equal(ext.dateFor({ type: "month" }, "Present"), "");
  assert.equal(ext.jobFieldKey("start date", { tagName: "INPUT" }, null), "job_start");
  assert.equal(ext.jobFieldKey("end date", { tagName: "INPUT" }, null), "job_end");
  assert.equal(ext.jobFieldKey("anything", { tagName: "TEXTAREA" }, null), "job_description");
  assert.equal(ext.jobFieldKey("job title", { tagName: "INPUT" }, "current_title"), "current_title");
  // a long question with "to" in it isn't a job's end date
  assert.equal(ext.jobFieldKey("are you legally authorized to work in the united kingdom?", { tagName: "SELECT" }, null), null);
});

test("the extension's manifest is valid", () => {
  const m = JSON.parse(fs.readFileSync(path.join(__dirname, "..", "chrome-extension", "manifest.json"), "utf8"));
  assert.equal(m.manifest_version, 3);
  assert.match(m.version, /^\d+\.\d+\.\d+$/);
  for (const f of ["content.js", "background.js", "popup.html", "popup.js"])
    assert.ok(fs.existsSync(path.join(__dirname, "..", "chrome-extension", f)), f);
});

test("the app screen's scripts have no syntax errors", () => {
  const ui = path.join(__dirname, "..", "ui");
  const html = fs.readFileSync(path.join(ui, "index.html"), "utf8");
  const files = [...html.matchAll(/<script src="\/ui\/(js\/[\w-]+\.js)"><\/script>/g)].map((m) => m[1]);
  assert.ok(files.length >= 10, "index.html loads the screen's scripts");
  for (const f of fs.readdirSync(path.join(ui, "js"))) assert.ok(files.includes("js/" + f), `${f} is loaded by index.html`);
  for (const f of files) assert.doesNotThrow(() => new vm.Script(fs.readFileSync(path.join(ui, f), "utf8")), f);
  for (const f of ["background.js", "popup.js"]) {
    assert.doesNotThrow(() => new vm.Script(fs.readFileSync(path.join(__dirname, "..", "chrome-extension", f), "utf8")), f);
  }
});

test("profile fields from plugins fill their own questions", () => {
  ext.setExtraFields([{ key: "acca_number", patterns: ["acca.{0,30}(membership|registration).{0,10}(number|no\b|id)"] },
                      { key: "showreel", patterns: ["(show|demo)[- ]?reel"] }, { key: "bad", patterns: ["("] }]);
  assert.equal(keyOf("ACCA membership number"), "acca_number");
  assert.equal(keyOf("Link to your showreel"), "showreel");
  assert.equal(keyOf("First name"), "first_name", "the normal fields still work");
  assert.equal(keyOf("Gender"), null, "personal questions are still left for you");
  ext.setExtraFields([]);
  assert.equal(keyOf("ACCA membership number"), null, "without the plugin the box is left alone");
});
