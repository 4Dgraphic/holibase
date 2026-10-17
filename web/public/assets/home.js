import { api, $, el, setText, iso, today, addDays, parseIso, fmtWeekday, inDays, countryName, compact, monthGrid, markDays, highlightJson, LANG } from "./site.js";

const ORIGIN_LABEL = { official: "Official open data", library: "python-holidays", editorial: "Researched by Holibase", community: "Community" };

// Visitor's country from the browser language (no IP lookup, no cookies). Falls back to the US.
function visitorCountry() {
  for (const tag of navigator.languages || [navigator.language]) {
    const region = (tag || "").split("-")[1];
    if (region && /^[A-Z]{2}$/i.test(region)) return region.toUpperCase();
  }
  return "US";
}

async function nextHoliday() {
  const cc = visitorCountry();
  const from = iso(today());
  const to = iso(addDays(today(), 366));
  try {
    const data = await api(`/v1/public-holidays/${cc}?from=${from}&to=${to}&lang=${LANG}`);
    const h = data.holidays.find((x) => !x.is_observed) || data.holidays[0];
    if (!h) throw new Error("none");
    const d = parseIso(h.date);
    setText("#next-caption", `Next public holiday in ${countryName(cc)}`);
    setText("#next-month", new Intl.DateTimeFormat("en-GB", { month: "short", year: "numeric" }).format(d).toUpperCase());
    setText("#next-weekday", fmtWeekday(h.date).toUpperCase());
    setText("#next-day", String(d.getDate()));
    setText("#next-name", h.name);
    setText("#next-local", h.local_name !== h.name ? h.local_name : "");
    setText("#next-code", cc);
    setText("#next-in", inDays(h.date));
  } catch {
    $("#next-card").replaceChildren(el("p", { class: "muted", text: "The holiday preview could not be loaded." }));
  }
}

async function coverage() {
  try {
    const c = await api("/v1/coverage");
    const ph = c.public_holidays;
    setText('[data-stat="ph-countries"]', String(ph.countries));
    setText('[data-stat="ph-subdivisions"]', String(ph.subdivisions));
    setText('[data-stat="ph-first-year"]', ph.first_date.slice(0, 4));
    setText('[data-stat="ph-last-year"]', ph.last_date.slice(0, 4));
    const sh = c.school_holidays;
    setText('[data-stat="sh-countries"]', String(sh.countries));
    setText('[data-stat="sh-scopes"]', sh.by_country.reduce((n, x) => n + x.scopes_verified, 0).toLocaleString("en-US"));
    const us = c.us_districts;
    setText('[data-stat="us-directory"]', us.directory.toLocaleString("en-US"));
    setText('[data-stat="us-verified"]', us.verified.toLocaleString("en-US"));
    if (us.students) {
      setText('[data-stat="us-students-pct"]', `${((100 * us.students_verified) / us.students).toFixed(1)}%`);
      setText('[data-stat="us-students"]', compact(us.students_verified));
    }
    const list = $("#source-list");
    list.replaceChildren(
      ...sh.by_country.slice(0, 8).map((x) =>
        el("div", { class: "status-row" },
          el("div", {},
            el("div", { class: "name", text: `${x.name || countryName(x.country_code)}, ${x.scopes_verified} ${x.authorities ? (x.country_code === "US" ? "districts" : "calendars") : "regions"}` }),
            el("div", { class: "meta", text: `${[...new Set([...(x.sources || []).filter((s) => s === "openholidays" || s === "python-holidays").map((s) => (s === "openholidays" ? "OpenHolidays" : "python-holidays")), ...x.origins.filter((o) => o !== "library" || !(x.sources || []).length).map((o) => ORIGIN_LABEL[o] || o)])].join(" · ")} · ${x.first_school_year === x.last_school_year ? x.last_school_year : `${x.first_school_year} to ${x.last_school_year}`}` })),
          el("span", { class: "pill pill-public", text: "Live" }))),
      el("a", { class: "link-arrow", href: "/coverage/", style: "margin-top: 8px", text: `All ${sh.countries} countries →` }));
  } catch {
    /* keep the figures baked into the page */
  }
}

async function demoMonth() {
  const t = today();
  const year = t.getMonth() === 11 ? t.getFullYear() : t.getFullYear();
  const from = `${year}-12-01`, to = `${year}-12-31`;
  try {
    const [ph, sh] = await Promise.all([
      api(`/v1/public-holidays/DE?from=${from}&to=${to}&subdivision=DE-NI`),
      api(`/v1/school-holidays/DE?from=${from}&to=${to}&subdivision=DE-NI`),
    ]);
    setText("#demo-title", `December ${year}`);
    $("#demo-grid").replaceChildren(monthGrid(year, 11, markDays(ph.holidays, sh.periods)));
  } catch {
    $("#demo-grid").replaceChildren(monthGrid(year, 11, new Map()));
  }
}

async function names() {
  const y = today().getFullYear();
  try {
    const [de, en] = await Promise.all([
      api(`/v1/public-holidays/DE?from=${y}-12-25&to=${y}-12-25&lang=de`),
      api(`/v1/public-holidays/DE?from=${y}-12-25&to=${y}-12-25&lang=en`),
    ]);
    if (de.holidays[0]) setText('[data-name="de"]', de.holidays[0].name);
    if (en.holidays[0]) setText('[data-name="en"]', en.holidays[0].name);
  } catch { /* static fallback */ }
}

async function sample() {
  const y = today().getFullYear();
  try {
    const data = await api(`/v1/public-holidays/DE/${y}?subdivision=DE-NI`);
    $("#req").replaceChildren(
      el("span", { class: "c", text: `# Public holidays in Lower Saxony, ${y}` }), "\ncurl ",
      el("span", { class: "s", text: `https://api.holibase.org/v1/public-holidays/DE/${y}?subdivision=DE-NI` }));
    if (data.holidays[0]) $("#res").replaceChildren(highlightJson(data.holidays[0]));
  } catch { /* static sample */ }
}

// Hero search: send people to the calendar page with their query.
$("#hero-q")?.closest("form").addEventListener("submit", (e) => {
  if (!$("#hero-q").value.trim()) { e.preventDefault(); location.href = "/calendar/"; }
});

nextHoliday();
coverage();
demoMonth();
names();
sample();
