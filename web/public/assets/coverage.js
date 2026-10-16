import { api, $, el, setText, countryName, compact } from "./site.js";

const ORIGIN = { official: "Official open data", library: "python-holidays", editorial: "Researched by Holibase", community: "Community" };
const fmtN = (n) => n.toLocaleString("en-US");

async function stats() {
  const c = await api("/v1/coverage");
  const ph = c.public_holidays, sh = c.school_holidays, us = c.us_districts;
  setText('[data-stat="ph-countries"]', fmtN(ph.countries));
  setText('[data-stat="ph-subdivisions"]', fmtN(ph.subdivisions));
  setText('[data-stat="ph-first-year"]', ph.first_date.slice(0, 4));
  setText('[data-stat="ph-last-year"]', ph.last_date.slice(0, 4));
  setText('[data-stat="sh-countries"]', fmtN(sh.countries));
  setText('[data-stat="sh-calendars"]', fmtN(sh.calendars));
  setText('[data-stat="us-directory"]', fmtN(us.directory));
  setText('[data-stat="us-verified"]', fmtN(us.verified));
  if (us.students) {
    setText('[data-stat="us-students-pct"]', `${((100 * us.students_verified) / us.students).toFixed(1)}%`);
    setText('[data-stat="us-students"]', compact(us.students_verified));
    setText('[data-stat="us-students-all"]', compact(us.students));
  }
  const rows = sh.by_country.map((x) => {
    const name = x.name || countryName(x.country_code);
    const level = x.country_code === "US" ? "School districts" : x.authorities && x.authorities === x.scopes ? "Local authorities and zones" : x.authorities ? "Regions and zones" : x.scopes > 1 ? "States and regions" : "Nationwide";
    const years = x.first_school_year === x.last_school_year ? x.last_school_year : `${x.first_school_year} to ${x.last_school_year}`;
    return el("tr", {},
      el("td", {}, el("a", { href: `/school-holidays/${x.country_code.toLowerCase()}/`, text: name }), " ", el("span", { class: "pill pill-code", text: x.country_code })),
      el("td", { text: level }),
      el("td", { class: "num", text: fmtN(x.scopes_verified) }),
      el("td", { class: "num muted", text: x.scopes > x.scopes_verified ? fmtN(x.scopes - x.scopes_verified) : "–" }),
      el("td", { class: "num", text: years }),
      el("td", { text: x.origins.map((o) => ORIGIN[o] || o).join(", ") }));
  });
  $("#school-table tbody").replaceChildren(...rows);
}

let all = [];
function renderCountries(filter = "") {
  const f = filter.trim().toLowerCase();
  const list = all.filter((c) => !f || c.name.toLowerCase().includes(f) || c.code.toLowerCase() === f);
  $("#country-list").replaceChildren(...(list.length
    ? list.map((c) => el("a", { class: "chip", href: `/public-holidays/${c.code.toLowerCase()}/`, text: c.name }))
    : [el("p", { class: "muted body-s", text: `No country matches “${filter}”.` })]));
}
async function countries() {
  const [data, pages] = await Promise.all([api("/v1/countries"), fetch("/assets/pages.json").then((r) => r.json()).catch(() => ({}))]);
  const hasPage = (cc) => !Object.keys(pages).length || pages[`public:${cc}`];
  all = data.countries.filter((c) => hasPage(c.code)).map((c) => ({ code: c.code, name: countryName(c.code) })).sort((a, b) => a.name.localeCompare(b.name));
  renderCountries();
  $("#country-filter").addEventListener("input", (e) => renderCountries(e.target.value));
}

stats().catch(() => $("#school-table tbody").replaceChildren(el("tr", {}, el("td", { colspan: "6", class: "muted", text: "The coverage figures could not be loaded. Please try again later." }))));
countries().catch(() => $("#country-list").replaceChildren(el("p", { class: "muted body-s", text: "The country list could not be loaded." })));
