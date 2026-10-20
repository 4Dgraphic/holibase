// Submission form: /submit/?country=DE&subdivision=DE-NI&authority=<id>&year=2027-28&lang=de
import { API, api, $, $$, el } from "./site.js";

const params = new URLSearchParams(location.search);
// English unless the link asks for German (/melden and the German region pages add ?lang=de).
const LANG = (params.get("lang") || "en").slice(0, 2).toLowerCase() === "de" ? "de" : "en";
const CALENDAR_YEAR = new Set(["AU", "NZ", "ZA", "BR", "AR", "CL"]);

const T = {
  en: {
    overline: "Submit holidays", h1: "Missing or wrong holidays? Tell us.",
    lead: "Send the school holidays of your region with a link to the official calendar. We check every date against that document before it appears on Holibase and in the API, usually within a day.",
    where: "1. Which calendar?", country: "Country", choose_country: "Choose a country",
    err_country: "Choose a country.", region: "State, region or canton", authority: "School or local variant",
    year: "School year", whole_country: "Whole country", whole_region: "Whole region (most schools)",
    dates: "2. All holidays of this school year",
    dates_help: "Enter every break and day off of the school year, including Christmas and summer. Correct the dates that are wrong.",
    prefilled: "We filled in what Holibase has for this school year. Correct what is wrong and add what is missing.",
    name: "Name", from: "First day off", to: "Last day off", add: "+ Add a holiday", remove: "Remove",
    name_ph: "e.g. Autumn break",
    first_day: "First day of school (optional)", last_day: "Last day of school (optional)",
    source: "3. Where is it published?", url: "Link to the official calendar",
    url_help: "The page or PDF of the ministry, canton, council or school district that publishes these dates. Holiday websites and news articles cannot be used.",
    note: "Anything else we should know? (optional)",
    note_help: "Please do not include personal data such as names or email addresses.",
    licence: "I agree that these dates are published as open data under CC BY 4.0.",
    submit: "Send", sending: "Sending…",
    how_title: "What happens next",
    how_1: "Every night we open the linked document and look for each date you entered.",
    how_2: "If all dates are in an official document, the calendar is published, usually the next morning.",
    how_3: "If something does not match, it stays unverified until a second source confirms it.",
    how_4: "Calendars from ministries and official open data always take precedence.",
    err_region: "Choose a region.", err_dates: "Enter at least two holidays with their dates.",
    err_order: "“{name}” ends before it starts.", err_url: "Add the link to the official calendar (starting with https://).",
    err_licence: "Please agree to the open licence.", err_send: "Sending failed: {msg}",
    thanks_title: "Thank you!", thanks: "We check the dates against the document tonight. Reference: {id}.",
    thanks_more: "Send another calendar", view: "View the calendar →",
  },
  de: {
    overline: "Ferien melden", h1: "Ferien fehlen oder sind falsch? Sag es uns.",
    lead: "Schick uns die Schulferien deiner Region mit einem Link zum offiziellen Ferienplan. Wir prüfen jedes Datum gegen dieses Dokument, bevor es auf Holibase und in der API erscheint, meist innerhalb eines Tages.",
    where: "1. Welcher Ferienplan?", country: "Land", choose_country: "Land wählen",
    err_country: "Wähle ein Land.", region: "Bundesland, Region oder Kanton", authority: "Schule oder Gemeinde-Variante",
    year: "Schuljahr", whole_country: "Ganzes Land", whole_region: "Ganze Region (die meisten Schulen)",
    dates: "2. Alle Ferien dieses Schuljahres",
    dates_help: "Trag alle Ferien und freien Tage des Schuljahres ein, auch Weihnachts- und Sommerferien. Korrigiere, was falsch ist.",
    prefilled: "Wir haben eingetragen, was Holibase für dieses Schuljahr hat. Korrigiere, was falsch ist, und ergänze, was fehlt.",
    name: "Bezeichnung", from: "Erster freier Tag", to: "Letzter freier Tag", add: "+ Ferien hinzufügen", remove: "Entfernen",
    name_ph: "z. B. Herbstferien",
    first_day: "Erster Schultag (optional)", last_day: "Letzter Schultag (optional)",
    source: "3. Wo ist das veröffentlicht?", url: "Link zum offiziellen Ferienplan",
    url_help: "Die Seite oder das PDF des Ministeriums, Kantons, Schulamts oder Schulbezirks, das diese Termine veröffentlicht. Ferienportale und Zeitungsartikel können wir nicht verwenden.",
    note: "Sonst noch etwas? (optional)",
    note_help: "Bitte keine persönlichen Daten wie Namen oder E-Mail-Adressen.",
    licence: "Ich bin einverstanden, dass diese Termine als offene Daten unter CC BY 4.0 veröffentlicht werden.",
    submit: "Senden", sending: "Wird gesendet …",
    how_title: "Wie es weitergeht",
    how_1: "Jede Nacht öffnen wir das verlinkte Dokument und suchen darin jedes Datum, das du eingetragen hast.",
    how_2: "Stehen alle Termine in einem offiziellen Dokument, wird der Ferienplan veröffentlicht, meist am nächsten Morgen.",
    how_3: "Passt etwas nicht, bleibt er unbestätigt, bis eine zweite Quelle ihn bestätigt.",
    how_4: "Ferienpläne aus Ministerien und offiziellen Daten haben immer Vorrang.",
    err_region: "Wähle eine Region.", err_dates: "Trag mindestens zwei Ferien mit Datum ein.",
    err_order: "„{name}“ endet, bevor es beginnt.", err_url: "Füge den Link zum offiziellen Ferienplan ein (beginnt mit https://).",
    err_licence: "Bitte stimme der offenen Lizenz zu.", err_send: "Senden fehlgeschlagen: {msg}",
    thanks_title: "Danke!", thanks: "Wir prüfen die Termine heute Nacht gegen das Dokument. Referenz: {id}.",
    thanks_more: "Weiteren Ferienplan melden", view: "Zum Ferienplan →",
  },
};
const t = (key, vars = {}) => (T[LANG][key] ?? T.en[key] ?? key).replace(/\{(\w+)\}/g, (_, k) => vars[k] ?? "");

document.documentElement.lang = LANG;
for (const node of $$("[data-t]")) node.textContent = t(node.dataset.t);
if (LANG === "de") document.title = "Ferien melden · Holibase";

const displayNames = (() => { try { return new Intl.DisplayNames([LANG], { type: "region" }); } catch { return null; } })();
const countryLabel = (cc) => displayNames?.of(cc) || cc;
const form = $("#submit-form");
const fCountry = $("#f-country"), fRegion = $("#f-region"), fAuthority = $("#f-authority"), fYear = $("#f-year");
const started = Date.now();
let ref = { countries: [], subdivisions: [] };

// ---------------------------------------------------------------- choices

function schoolYears(cc) {
  const d = new Date();
  if (CALENDAR_YEAR.has(cc)) return [0, 1, 2, 3].map((i) => String(d.getFullYear() + i));
  const y = d.getMonth() >= 7 ? d.getFullYear() : d.getFullYear() - 1;
  return [0, 1, 2, 3].map((i) => `${y + i}-${String((y + i + 1) % 100).padStart(2, "0")}`);
}

function yearWindow(sy) {
  if (sy.length === 4) return [`${sy}-01-01`, `${sy}-12-31`];
  const y = Number(sy.slice(0, 4));
  return [`${y}-08-01`, `${y + 1}-07-31`];
}

function options(select, items, selected) {
  select.replaceChildren(...items.map(([value, label]) => el("option", { value, text: label, selected: value === selected })));
}

function fillCountries() {
  const list = ref.countries.map((c) => [c.code, countryLabel(c.code)]).sort((a, b) => a[1].localeCompare(b[1], LANG));
  const wanted = (params.get("country") || "").toUpperCase();
  options(fCountry, [["", t("choose_country")], ...list], wanted);
  fCountry.querySelector('option[value=""]').disabled = true;
}

function fillRegions(selected) {
  const cc = fCountry.value;
  if (!cc) { fRegion.replaceChildren(); fYear.replaceChildren(); return; }
  const subs = ref.subdivisions.filter((s) => s.country_code === cc && !s.parent_code)
    .map((s) => [s.code, s.name || s.code]).sort((a, b) => a[1].localeCompare(b[1], LANG));
  options(fRegion, [["", t("whole_country")], ...subs], selected);
  options(fYear, schoolYears(cc).map((y) => [y, y]), params.get("year") || params.get("school_year") || "");
}

async function fillAuthorities(selected) {
  const cc = fCountry.value, sub = fRegion.value;
  $("#f-authority-wrap").hidden = true;
  fAuthority.replaceChildren();
  if (!cc) return;
  if (!sub && cc === "US") return; // ~19,000 districts: choose a state first
  try {
    const q = new URLSearchParams({ country: cc, limit: "60" });
    if (sub) q.set("subdivision", sub);
    const data = await api(`/v1/authorities?${q}`);
    const list = data.authorities.filter((a) => !sub || a.subdivision_code === sub);
    if (!list.length || list.length >= 60) return;
    options(fAuthority, [["", t("whole_region")], ...list.map((a) => [a.id, a.name])], selected);
    $("#f-authority-wrap").hidden = false;
  } catch { /* no variants */ }
}

// ---------------------------------------------------------------- holidays

function periodRow(p = {}) {
  const row = el("div", { class: "period-row" },
    el("input", { class: "input plain", type: "text", maxlength: "120", placeholder: t("name_ph"), "aria-label": t("name"), value: p.name || "" }),
    el("input", { class: "input plain", type: "date", "aria-label": t("from"), value: p.start_date || "" }),
    el("input", { class: "input plain", type: "date", "aria-label": t("to"), value: p.end_date || "" }),
    el("button", { class: "btn btn-secondary btn-sm remove", type: "button", "aria-label": t("remove"), title: t("remove"), text: "×",
      onclick: () => { row.remove(); if (!$("#f-periods").children.length) addRows(1); } }));
  return row;
}
function addRows(n, items = []) {
  const box = $("#f-periods");
  for (let i = 0; i < n; i++) box.append(periodRow(items[i]));
}

async function prefill() {
  const cc = fCountry.value, sy = fYear.value;
  if (!cc) { $("#f-periods").replaceChildren(); addRows(5); return; }
  const [from, to] = yearWindow(sy);
  const scope = fAuthority.value ? `&authority=${fAuthority.value}` : fRegion.value ? `&subdivision=${fRegion.value}` : "";
  $("#f-periods").replaceChildren();
  $("#f-first").value = ""; $("#f-last").value = "";
  $("#f-prefill-note").textContent = t("dates_help");
  try {
    const data = await api(`/v1/school-holidays/${cc}?from=${from}&to=${to}&lang=${LANG}${scope}`);
    const items = data.periods.filter((p) => p.school_year === sy && ["break", "holiday", "teacher_day"].includes(p.kind))
      .map((p) => ({ name: p.name, start_date: p.start_date, end_date: p.end_date }));
    const cal = data.calendars.find((c) => c.school_year === sy);
    if (cal?.first_day) $("#f-first").value = cal.first_day;
    if (cal?.last_day) $("#f-last").value = cal.last_day;
    if (items.length) {
      addRows(items.length, items);
      $("#f-prefill-note").textContent = t("prefilled");
      return;
    }
  } catch { /* nothing to prefill */ }
  addRows(5);
}

// ---------------------------------------------------------------- submit

function message(kind, ...children) {
  $("#f-message").replaceChildren(el("div", { class: `notice ${kind}`, style: "margin-bottom: 16px" }, ...children));
}

function collect() {
  if (!fCountry.value) throw new Error(t("err_country"));
  const periods = [];
  for (const row of $$(".period-row")) {
    const [name, start, end] = $$("input", row).map((i) => i.value.trim());
    if (!start && !end && !name) continue;
    if (!start) continue;
    if (end && end < start) throw new Error(t("err_order", { name: name || start }));
    periods.push({ name, start_date: start, end_date: end || start });
  }
  if (periods.length < 2) throw new Error(t("err_dates"));
  const url = $("#f-url").value.trim();
  if (!/^https?:\/\/\S+\.\S+/.test(url)) throw new Error(t("err_url"));
  if (!$("#f-licence").checked) throw new Error(t("err_licence"));
  return {
    country: fCountry.value, subdivision: fRegion.value || null, authority: fAuthority.value || null,
    school_year: fYear.value, source_url: url, periods,
    first_day: $("#f-first").value || null, last_day: $("#f-last").value || null,
    note: $("#f-note").value.trim() || null, lang: LANG,
    website: $("#f-website").value, elapsed_ms: Date.now() - started,
  };
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  let body;
  try { body = collect(); } catch (err) { message("coral", err.message); return; }
  const button = $("#f-submit");
  button.disabled = true; button.textContent = t("sending");
  try {
    const res = await fetch(`${API}/v1/submissions`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data?.error?.message || `HTTP ${res.status}`);
    const view = new URLSearchParams({ country: body.country });
    if (body.authority) view.set("authority", body.authority); else if (body.subdivision) view.set("subdivision", body.subdivision);
    form.replaceChildren(el("div", { class: "notice mint" },
      el("h2", { class: "h3", style: "margin-bottom: 8px", text: t("thanks_title") }),
      el("p", { text: t("thanks", { id: (data.id || "").slice(0, 8) }) }),
      el("div", { class: "actions" },
        el("a", { class: "btn btn-secondary btn-sm", href: location.pathname + (LANG === "de" ? "?lang=de" : ""), text: t("thanks_more") }),
        el("a", { class: "link-arrow", href: `/calendar/?${view}`, text: t("view") }))));
    window.scrollTo({ top: 0, behavior: "smooth" });
  } catch (err) {
    message("coral", t("err_send", { msg: err.message }));
    button.disabled = false; button.textContent = t("submit");
  }
});

// ---------------------------------------------------------------- start

$("#f-add").addEventListener("click", () => addRows(1));
fCountry.addEventListener("change", async () => { fillRegions(""); await fillAuthorities(""); prefill(); });
fRegion.addEventListener("change", async () => { await fillAuthorities(""); prefill(); });
fAuthority.addEventListener("change", prefill);
fYear.addEventListener("change", prefill);

(async () => {
  try { ref = await api("/v1/countries"); } catch { ref = { countries: [], subdivisions: [] }; }
  let sub = (params.get("subdivision") || "").toUpperCase();
  if (params.get("authority") && !sub) {
    try { sub = (await api(`/v1/authorities/${params.get("authority")}`)).authority.subdivision_code || ""; } catch { /* unknown */ }
  }
  fillCountries();
  fillRegions(sub);
  await fillAuthorities(params.get("authority") || "");
  await prefill();
})();
