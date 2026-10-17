import {
  api, $, $$, el, iso, today, addDays, parseIso, fmtDay, fmtDayShort, fmtRange, fmtWeekday, fmtMonthYear, inDays, daysBetween,
  countryName, compact, monthGrid, markDays, feedLinks, debounce, LANG,
} from "./site.js";

const ORIGIN = {
  official: "Official open data",
  library: "python-holidays",
  editorial: "Researched by Holibase",
  community: "Community submission",
};
const sourceLabel = (c) => (c.source_id === "openholidays" ? "OpenHolidays (ODbL)" : ORIGIN[c.origin] || c.origin);
const KIND = {
  break: ["School holiday", "pill-school"],
  holiday: ["Day off school", "pill-school"],
  teacher_day: ["No school for students", "pill-school"],
  early_release: ["Early release", "pill-neutral"],
  other: ["No school", "pill-school"],
};

// English names for regions stored under their local name, so "Bavaria" finds Bayern.
const EN_ALIAS = {
  "DE-BY": "Bavaria", "DE-NI": "Lower Saxony", "DE-NW": "North Rhine-Westphalia", "DE-HE": "Hesse",
  "DE-RP": "Rhineland-Palatinate", "DE-SN": "Saxony", "DE-ST": "Saxony-Anhalt", "DE-TH": "Thuringia",
  "DE-MV": "Mecklenburg-Western Pomerania", "AT-2": "Carinthia", "AT-3": "Lower Austria", "AT-4": "Upper Austria",
  "AT-6": "Styria", "AT-7": "Tyrol", "AT-9": "Vienna", "CH-ZH": "Zurich", "CH-BE": "Bern", "CH-GE": "Geneva",
  "FR-971": "Guadeloupe", "FR-972": "Martinique", "FR-973": "French Guiana", "FR-974": "Réunion", "FR-976": "Mayotte",
};
const q = $("#q");
const results = $("#results");
let countriesCache = null;

// ---------------------------------------------------------------- search

async function loadCountries() {
  if (countriesCache) return countriesCache;
  try {
    const cached = sessionStorage.getItem("hb-countries-v2");
    if (cached) return (countriesCache = JSON.parse(cached));
  } catch { /* storage unavailable */ }
  const data = await api("/v1/countries");
  const name = (names, fallback) => (names && (names.en || names["en-US"] || names["en-GB"])) || fallback;
  countriesCache = {
    countries: data.countries.map((c) => ({ code: c.code, name: name(c.names, countryName(c.code)) })),
    subdivisions: data.subdivisions.map((s) => {
      let n = name(s.names, s.name || s.code);
      if (/^[A-Z]{2}$/.test(n)) n = EN_ALIAS[s.code] || countryName(n); // French overseas regions are stored by their ISO code
      return { code: s.code, country: s.country_code, name: n, alias: EN_ALIAS[s.code] || "" };
    }),
  };
  try { sessionStorage.setItem("hb-countries-v2", JSON.stringify(countriesCache)); } catch { /* ignore */ }
  return countriesCache;
}

const norm = (s) => (s || "").normalize("NFKD").replace(/[̀-ͯ]/g, "").toLowerCase();

async function search(term) {
  term = term.trim();
  if (term.length < 2) { closeResults(); return; }
  const t = norm(term);
  const [ref, auth] = await Promise.all([
    loadCountries().catch(() => ({ countries: [], subdivisions: [] })),
    api(`/v1/authorities?q=${encodeURIComponent(term)}&limit=8`).catch(() => ({ authorities: [] })),
  ]);
  const score = (name, code) => (norm(name).startsWith(t) || norm(code) === t ? 0 : norm(name).includes(t) ? 1 : 9);
  const regions = ref.subdivisions
    .map((s) => ({ ...s, s: Math.min(score(s.name, s.code), s.alias ? score(s.alias, s.code) : 9) })).filter((s) => s.s < 9)
    .sort((a, b) => a.s - b.s || a.name.localeCompare(b.name)).slice(0, 6);
  const countries = ref.countries
    .map((c) => ({ ...c, s: score(c.name, c.code) })).filter((c) => c.s < 9)
    .sort((a, b) => a.s - b.s).slice(0, 3);
  const items = [];
  if (auth.authorities?.length) {
    items.push({ group: "School authorities" });
    for (const a of auth.authorities) {
      const where = [a.city, a.subdivision_code?.split("-")[1], countryName(a.country_code)].filter(Boolean).join(", ");
      const has = a.calendars_confirmed > 0 ? "Calendar" : a.calendars_pending > 0 ? "Unverified" : "No calendar yet";
      items.push({ title: a.name, sub: where, tag: has, href: `?country=${a.country_code}&authority=${a.id}` });
    }
  }
  if (regions.length) {
    items.push({ group: "Regions" });
    for (const r of regions) items.push({ title: r.alias && r.alias !== r.name ? `${r.name} (${r.alias})` : r.name, sub: countryName(r.country), tag: r.code, href: `?country=${r.country}&subdivision=${r.code}` });
  }
  if (countries.length) {
    items.push({ group: "Countries" });
    for (const c of countries) items.push({ title: c.name, sub: "Nationwide", tag: c.code, href: `?country=${c.code}` });
  }
  renderResults(items, term);
}

let active = -1;
function renderResults(items, term) {
  results.replaceChildren();
  active = -1;
  if (!items.length) {
    results.append(el("li", { class: "group", text: `Nothing found for “${term}”` }));
  }
  items.forEach((it, i) => {
    if (it.group) { results.append(el("li", { class: "group", role: "presentation", text: it.group })); return; }
    const li = el("li", { role: "option", id: `opt-${i}`, "data-href": it.href, "aria-selected": "false" },
      el("div", {}, el("div", { class: "title", text: it.title }), el("div", { class: "sub", text: it.sub })),
      el("span", { class: "pill pill-code", text: it.tag }));
    li.addEventListener("mousedown", (e) => { e.preventDefault(); go(it.href); });
    results.append(li);
  });
  results.hidden = false;
  q.setAttribute("aria-expanded", "true");
}
function closeResults() { results.hidden = true; q.setAttribute("aria-expanded", "false"); }
function go(href) { location.search = href; }

q.addEventListener("input", debounce(() => search(q.value), 200));
q.addEventListener("focus", () => { if (q.value.trim().length >= 2) search(q.value); });
q.addEventListener("blur", () => setTimeout(closeResults, 100));
q.addEventListener("keydown", (e) => {
  const opts = $$('[role="option"]', results);
  if (!opts.length) return;
  if (e.key === "ArrowDown" || e.key === "ArrowUp") {
    e.preventDefault();
    active = (active + (e.key === "ArrowDown" ? 1 : -1) + opts.length) % opts.length;
    opts.forEach((o, i) => o.setAttribute("aria-selected", String(i === active)));
    q.setAttribute("aria-activedescendant", opts[active].id);
    opts[active].scrollIntoView({ block: "nearest" });
  } else if (e.key === "Enter") {
    e.preventDefault();
    go((opts[active] || opts[0]).dataset.href);
  } else if (e.key === "Escape") closeResults();
});
for (const chip of $$("#examples .chip")) chip.addEventListener("click", () => { q.value = chip.dataset.q; q.focus(); search(chip.dataset.q); });

// ---------------------------------------------------------------- view

const params = new URLSearchParams(location.search);
const country = (params.get("country") || "").toUpperCase();
const subdivision = params.get("subdivision");
const authority = params.get("authority");
const showPending = params.get("include") === "pending";

if (params.get("q")) { q.value = params.get("q"); search(q.value); q.focus(); }
if (/^[A-Z]{2}$/.test(country)) show().catch((e) => {
  $("#view").hidden = false;
  $("#v-title").textContent = "Something went wrong";
  $("#v-notice").replaceChildren(el("div", { class: "notice coral", text: `The calendar could not be loaded (${e.message}). Please try again later.` }));
});

async function show() {
  $("#view").hidden = false;
  $("#finder-title").textContent = "Search another calendar";
  $("#finder-title").style.marginBottom = "24px";
  $("#finder").querySelector(".body-l").hidden = true;
  $("#examples").hidden = true;
  $("#finder").closest("section").style.paddingTop = "32px";

  const from = iso(today());
  const to = iso(addDays(today(), 365));
  let title = subdivision ? subdivision : countryName(country);
  let region = subdivision;
  let authorityInfo = null;
  if (authority) {
    authorityInfo = await api(`/v1/authorities/${authority}`);
    title = authorityInfo.authority.name;
    region = authorityInfo.authority.subdivision_code;
  } else if (subdivision) {
    const ref = await loadCountries().catch(() => null);
    const sub = ref?.subdivisions.find((s) => s.code === subdivision);
    if (sub) title = sub.name;
  }
  document.title = `${title} school holidays · Holibase`;
  $("#v-title").textContent = title;

  const scope = authority ? `authority=${authority}` : subdivision ? `subdivision=${subdivision}` : "";
  const pending = showPending ? "&include=pending" : "";
  const [school, pub] = await Promise.all([
    api(`/v1/school-holidays/${country}?from=${from}&to=${to}&lang=${LANG}${scope ? "&" + scope : ""}${pending}`),
    api(`/v1/public-holidays/${country}?from=${from}&to=${to}&lang=${LANG}${region ? "&subdivision=" + region : ""}`),
  ]);

  // pills
  const pills = $("#v-pills");
  const where = [authorityInfo?.authority.city, EN_ALIAS[region], countryName(country)].filter(Boolean);
  pills.append(el("span", { class: "pill pill-code", text: region || country }), el("span", { class: "muted body-s", text: where.join(" · ") }));
  const origins = [...new Set(school.calendars.map(sourceLabel))];
  for (const o of origins) pills.append(el("span", { class: "pill pill-neutral", text: o }));
  if (school.calendars.some((c) => c.status === "pending")) pills.append(el("span", { class: "pill pill-estimated", text: "Unverified" }));

  // coverage notice
  const notice = $("#v-notice");
  const cov = school.coverage;
  if (cov.status === "none") {
    const issue = `https://github.com/4Dgraphic/holibase/issues/new?title=${encodeURIComponent(`School calendar for ${title}`)}&body=${encodeURIComponent(`Calendar page: ${location.href}\nLink to the official school calendar: `)}`;
    notice.append(el("div", { class: "notice coral" },
      el("p", { style: "margin: 0 0 8px", text: `There is no school calendar for ${title} in Holibase yet. Public holidays are shown below.` }),
      el("div", { class: "actions" },
        cov.pending_available ? el("a", { class: "btn btn-secondary btn-sm", href: `?${new URLSearchParams({ ...Object.fromEntries(params), include: "pending" })}`, text: "Show the unverified calendar" }) : null,
        el("a", { class: "link-arrow", href: issue, text: "Send us the official calendar →" }))));
  } else if (cov.unverified) {
    notice.append(el("div", { class: "notice", text: "This calendar has not been verified against a second source yet. Check important dates with the school or district." }));
  }

  permalink(title);
  renderNext(school.periods);
  renderFacts(school, pub, region);
  renderFeeds(title, scope, region, cov.status !== "none");
  renderAgenda(school.periods, pub.holidays, from, to);
  renderMonths(school.periods, pub.holidays);
  renderSources(school, pub);
}

function upcomingBreak(periods) {
  const t = iso(today());
  return periods.filter((p) => p.kind !== "early_release" && p.end_date >= t).sort((a, b) => a.start_date.localeCompare(b.start_date))[0];
}

function renderNext(periods) {
  const card = $("#v-next");
  const p = upcomingBreak(periods.filter((x) => x.kind === "break")) || upcomingBreak(periods);
  if (!p) {
    card.className = "card stat";
    card.replaceChildren(el("p", { class: "label", text: "Next school holiday" }), el("div", { class: "h2", text: "No dates yet" }),
      el("p", { class: "body-s muted", style: "margin: 0", text: "Holibase has no school holidays for this scope in the next twelve months." }));
    return;
  }
  const t = iso(today());
  const ongoing = p.start_date <= t;
  const d = parseIso(ongoing ? p.end_date : p.start_date);
  card.replaceChildren(
    el("div", { class: "top overline", style: "margin: 0" },
      el("span", { text: new Intl.DateTimeFormat("en-GB", { month: "short", year: "numeric" }).format(d).toUpperCase() }),
      el("span", { text: fmtWeekday(iso(d)).toUpperCase() })),
    el("div", { class: "numeral-xl", text: String(d.getDate()) }),
    el("h3", { class: "h3", text: p.name }),
    el("p", { class: "body-s muted", style: "margin: 0", text: ongoing ? `Until ${fmtDay(p.end_date)}` : fmtRange(p.start_date, p.end_date) }),
    el("div", { class: "pills" },
      el("span", { class: "pill pill-school", text: ongoing ? "Now" : "Next school holiday" }),
      el("span", { class: "pill pill-neutral", text: ongoing ? `${daysBetween(t, p.end_date) + 1} days left` : inDays(p.start_date) })));
}

function renderFacts(school, pub, region) {
  const cal = school.calendars.find((c) => c.first_day || c.last_day) || school.calendars[0];
  const box = $("#v-facts");
  box.className = "card stat";
  const lines = [];
  if (cal?.first_day) lines.push(["First day of school", fmtDay(cal.first_day)]);
  if (cal?.last_day) lines.push(["Last day of school", fmtDay(cal.last_day)]);
  const days = new Set();
  for (const p of school.periods) if (p.kind !== "early_release") for (let d = parseIso(p.start_date); iso(d) <= p.end_date; d = addDays(d, 1)) if (d.getDay() % 6) days.add(iso(d));
  box.replaceChildren(
    el("p", { class: "label", text: cal ? `School year ${cal.school_year}` : "Public holidays" }),
    el("div", {},
      school.calendars.length ? el("div", { class: "numeral", style: "color: var(--coral-ink)", text: String(days.size) }) : null,
      school.calendars.length ? el("p", { class: "body-s muted", style: "margin: 4px 0 16px", text: "weekdays off school in the next 12 months" }) : null,
      el("div", { class: "numeral", style: "color: var(--mint-ink)", text: String(pub.holidays.filter((h) => !h.is_observed).length) }),
      el("p", { class: "body-s muted", style: "margin: 4px 0 0", text: `public holidays${region ? ` in ${region}` : ""}` })),
    el("div", {}, ...lines.map(([k, v]) => el("p", { class: "body-s", style: "margin: 0" }, el("span", { class: "muted", text: `${k}: ` }), v))));
}

function feedRow(label, path, name) {
  const l = feedLinks(path, name);
  const copy = el("button", { class: "btn btn-secondary btn-sm", type: "button", text: "Copy link" });
  copy.addEventListener("click", async () => {
    try { await navigator.clipboard.writeText(l.https); copy.textContent = "Copied"; setTimeout(() => (copy.textContent = "Copy link"), 1500); } catch { /* ignore */ }
  });
  return el("div", {},
    el("p", { class: "body-s muted", style: "margin: 0 0 8px", text: label }),
    el("div", { class: "row" },
      el("a", { class: "btn btn-primary btn-sm", href: l.apple, text: "Apple Calendar" }),
      el("a", { class: "btn btn-secondary btn-sm", href: l.google, target: "_blank", rel: "noopener", text: "Google Calendar" }),
      el("a", { class: "btn btn-secondary btn-sm", href: l.outlook, target: "_blank", rel: "noopener", text: "Outlook" }),
      copy,
      el("a", { class: "btn btn-secondary btn-sm", href: l.https, download: "", text: "Download .ics" })));
}

function renderFeeds(title, scope, region, hasSchool) {
  const lang = `lang=${LANG}`;
  const schoolPath = `/v1/school-holidays/${country}.ics?${scope ? scope + "&" : ""}${lang}${showPending ? "&include=pending" : ""}`;
  const pubPath = `/v1/public-holidays/${country}.ics?${region ? `subdivision=${region}&` : ""}${lang}`;
  $("#v-feeds").replaceChildren(...[
    hasSchool ? feedRow("School holidays", schoolPath, `School holidays ${title}`) : null,
    feedRow(`Public holidays${region ? ` (${region})` : ""}`, pubPath, `Public holidays ${region || country}`)].filter(Boolean));
}

function renderAgenda(periods, holidays, from, to) {
  $("#v-range").textContent = `${fmtDay(from)} to ${fmtDay(to)}`;
  const t = iso(today());
  const items = [
    ...periods.filter((p) => p.end_date >= t).map((p) => ({ start: p.start_date, end: p.end_date, name: p.name, kind: p.kind, school: true })),
    ...holidays.map((h) => ({ start: h.date, end: h.date, name: h.name, local: h.local_name !== h.name ? h.local_name : "", estimated: h.is_estimated, observed: h.is_observed })),
  ].sort((a, b) => a.start.localeCompare(b.start) || (a.school ? -1 : 1));
  const list = $("#v-agenda");
  const render = (n) => list.replaceChildren(...items.slice(0, n).map((it) => {
    const [label, cls] = it.school ? KIND[it.kind] || KIND.other : it.estimated ? ["Estimated date", "pill-estimated"] : ["Public holiday", "pill-public"];
    const days = daysBetween(it.start, it.end) + 1;
    return el("li", {},
      el("div", { class: "when" }, it.start === it.end ? fmtDayShort(it.start) : `${fmtDayShort(it.start)} –`,
        el("small", { text: it.start === it.end ? fmtWeekday(it.start) : `${fmtDayShort(it.end)}, ${days} days` })),
      el("div", { class: "what" }, el("b", { text: it.name }), it.local || it.observed ? el("span", { text: [it.local, it.observed ? "observed day off" : ""].filter(Boolean).join(" · ") }) : null),
      el("span", { class: `pill ${cls}`, text: label }));
  }));
  if (!items.length) { list.replaceChildren(el("li", {}, el("div", { class: "what", text: "Nothing in the next twelve months." }))); return; }
  render(12);
  const more = $("#v-more");
  if (items.length > 12) { more.hidden = false; more.onclick = () => { render(items.length); more.hidden = true; }; }
}


function renderMonths(periods, holidays) {
  const marks = markDays(holidays, periods);
  const box = $("#v-months");
  const t = today();
  box.replaceChildren(...Array.from({ length: 6 }, (_, i) => {
    const d = new Date(t.getFullYear(), t.getMonth() + i, 1);
    return el("div", {}, el("p", { class: "label", style: "margin: 0 0 12px; font-weight: 600; color: var(--ink)", text: fmtMonthYear(d) }), monthGrid(d.getFullYear(), d.getMonth(), marks));
  }));
}

function renderSources(school, pub) {
  const table = $("#v-sources");
  const head = el("tr", {}, ...["School year", "Source", "Status", "First day", "Last day", "Document"].map((h) => el("th", { scope: "col", text: h })));
  const rows = school.calendars.map((c) => el("tr", {},
    el("td", { class: "num", text: c.school_year }),
    el("td", { text: sourceLabel(c) }),
    el("td", {}, el("span", { class: `pill ${c.status === "confirmed" ? "pill-public" : "pill-estimated"}`, text: c.status === "confirmed" ? "Verified" : "Unverified" })),
    el("td", { class: "num", text: c.first_day ? fmtDay(c.first_day) : "–" }),
    el("td", { class: "num", text: c.last_day ? fmtDay(c.last_day) : "–" }),
    el("td", {}, c.source_url && /^https?:\/\//.test(c.source_url) ? el("a", { href: c.source_url, rel: "noopener nofollow", target: "_blank", text: new URL(c.source_url).hostname }) : "–")));
  table.replaceChildren(el("thead", {}, head), el("tbody", {}, ...(rows.length ? rows : [el("tr", {}, el("td", { colspan: "6", class: "muted", text: "No school calendar in this range." }))])));
  $("#v-attribution").textContent = school.attribution;
}

// Link to the static page for this calendar (shareable, printable, indexed by search engines).
async function permalink(title) {
  try {
    const pages = await (await fetch("/assets/pages.json")).json();
    const url = pages[authority ? `auth:${authority}` : subdivision || country] || (!subdivision && !authority ? pages[`public:${country}`] : null);
    if (url) $("#v-pills").append(el("a", { class: "link-arrow body-s", href: url, text: "All dates on one page →" }));
  } catch { /* no page map */ }
}
