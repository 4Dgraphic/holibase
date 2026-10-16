// Shared helpers for holibase.org. No framework. Analytics only after consent (consent.js).
import "./consent.js";

const params = new URLSearchParams(location.search);
// ?api=http://localhost:8787 points the site at a local API (development only).
const devApi = params.get("api");
export const API = devApi && /^http:\/\/(localhost|127\.0\.0\.1)(:\d+)?$/.test(devApi) ? devApi : "https://api.holibase.org";
export const API_PUBLIC = "https://api.holibase.org"; // shown in code samples and feed links

export async function api(path) {
  const res = await fetch(API + path, { headers: { Accept: "application/json" } });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data?.error?.message || `HTTP ${res.status}`);
  return data;
}

// ---------------------------------------------------------------- DOM

export const $ = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

export function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === false || v === null || v === undefined) continue;
    if (k === "class") node.className = v;
    else if (k === "text") node.textContent = v;
    else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
    else node.setAttribute(k, v === true ? "" : v);
  }
  for (const c of children.flat()) if (c !== null && c !== undefined && c !== false) node.append(c.nodeType ? c : String(c));
  return node;
}

export function setText(sel, text) {
  for (const node of $$(sel)) { node.textContent = text; node.classList.remove("skeleton"); }
}

// ---------------------------------------------------------------- dates

export const LOCALE = navigator.language || "en";
export const LANG = (navigator.language || "en").split("-")[0];

export function iso(d) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}
export function parseIso(s) {
  const [y, m, d] = s.split("-").map(Number);
  return new Date(y, m - 1, d);
}
export function addDays(d, n) { const x = new Date(d); x.setDate(x.getDate() + n); return x; }
export const today = () => { const d = new Date(); d.setHours(0, 0, 0, 0); return d; };

const fmt = (opts) => new Intl.DateTimeFormat("en-GB", opts);
export const fmtDay = (s) => fmt({ day: "numeric", month: "short", year: "numeric" }).format(parseIso(s));
export const fmtDayShort = (s) => fmt({ day: "numeric", month: "short" }).format(parseIso(s));
export const fmtWeekday = (s) => fmt({ weekday: "short" }).format(parseIso(s));
export const fmtMonthYear = (d) => fmt({ month: "long", year: "numeric" }).format(d);
export function fmtRange(a, b) {
  if (a === b) return fmtDay(a);
  const A = parseIso(a), B = parseIso(b);
  if (A.getFullYear() === B.getFullYear()) return `${fmtDayShort(a)} – ${fmtDay(b)}`;
  return `${fmtDay(a)} – ${fmtDay(b)}`;
}
export function daysBetween(a, b) { return Math.round((parseIso(b) - parseIso(a)) / 864e5); }
export function inDays(s) {
  const n = daysBetween(iso(today()), s);
  if (n <= 0) return "today";
  if (n === 1) return "tomorrow";
  return `in ${n} days`;
}

export const countryName = (cc) => {
  try { return new Intl.DisplayNames(["en"], { type: "region" }).of(cc) || cc; } catch { return cc; }
};

export function compact(n) {
  if (n === null || n === undefined) return "–";
  if (n >= 1e6) return `${(n / 1e6).toFixed(1)}M`;
  if (n >= 1e4) return `${Math.round(n / 1e3)}k`;
  return n.toLocaleString("en-US");
}

// ---------------------------------------------------------------- month grid

/**
 * Round day cells. marks: Map iso -> "public" | "school" | "estimated".
 * Weeks start on Monday.
 */
export function monthGrid(year, month, marks, { labels = true } = {}) {
  const grid = el("div", { class: "month", role: "grid" });
  if (labels) for (const d of ["M", "T", "W", "T", "F", "S", "S"]) grid.append(el("div", { class: "dow", "aria-hidden": "true", text: d }));
  const first = new Date(year, month, 1);
  const pad = (first.getDay() + 6) % 7;
  for (let i = 0; i < pad; i++) grid.append(el("div", { class: "day empty", "aria-hidden": "true" }));
  const days = new Date(year, month + 1, 0).getDate();
  const t = iso(today());
  for (let d = 1; d <= days; d++) {
    const date = new Date(year, month, d);
    const key = iso(date);
    const kind = marks.get(key);
    const cls = ["day", kind, key === t ? "today" : "", date.getDay() % 6 === 0 ? "weekend" : ""].filter(Boolean).join(" ");
    const label = `${fmtDay(key)}${kind ? `, ${kind === "public" ? "public holiday" : kind === "school" ? "school holiday" : "estimated date"}` : ""}`;
    grid.append(el("div", { class: cls, role: "gridcell", "aria-label": label, text: String(d) }));
  }
  return grid;
}

/** Expand periods into a day map. School wins over public on the same day. */
export function markDays(publicHolidays = [], schoolPeriods = []) {
  const marks = new Map();
  for (const h of publicHolidays) marks.set(h.date, h.is_estimated ? "estimated" : "public");
  for (const p of schoolPeriods) {
    if (p.kind === "early_release") continue;
    for (let d = parseIso(p.start_date); iso(d) <= p.end_date; d = addDays(d, 1)) {
      const k = iso(d);
      if (marks.get(k) !== "public") marks.set(k, "school");
    }
  }
  return marks;
}

// ---------------------------------------------------------------- feeds

export function feedLinks(feedPath, name) {
  const https = `${API_PUBLIC}${feedPath}`;
  const webcal = https.replace(/^https:/, "webcal:");
  return {
    https,
    apple: webcal,
    google: `https://calendar.google.com/calendar/render?cid=${encodeURIComponent(webcal)}`,
    outlook: `https://outlook.live.com/calendar/0/addfromweb?url=${encodeURIComponent(https)}&name=${encodeURIComponent(name)}`,
  };
}

// ---------------------------------------------------------------- code samples

export function highlightJson(obj) {
  const json = JSON.stringify(obj, null, 2);
  const frag = document.createDocumentFragment();
  const re = /("(?:\\.|[^"\\])*")(\s*:)?|\b(true|false|null)\b|(-?\d+(?:\.\d+)?)/g;
  let last = 0, m;
  while ((m = re.exec(json))) {
    frag.append(json.slice(last, m.index));
    if (m[1]) frag.append(el("span", { class: m[2] ? "k" : "s", text: m[1] }), m[2] || "");
    else frag.append(el("span", { class: "n", text: m[0] }));
    last = re.lastIndex;
  }
  frag.append(json.slice(last));
  return frag;
}

export function copyButtons() {
  for (const btn of $$(".copy-btn")) {
    btn.addEventListener("click", async () => {
      const target = document.getElementById(btn.dataset.copy);
      const text = target?.dataset.copyText || target?.textContent || "";
      try { await navigator.clipboard.writeText(text); btn.textContent = "Copied"; setTimeout(() => (btn.textContent = "Copy"), 1500); } catch { /* ignore */ }
    });
  }
}

export function debounce(fn, ms) {
  let t;
  return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); };
}

// ---------------------------------------------------------------- chrome

const header = $(".site-header");
if (header) {
  const onScroll = () => header.classList.toggle("scrolled", window.scrollY > 8);
  addEventListener("scroll", onScroll, { passive: true });
  onScroll();
}
const toggle = $(".nav-toggle");
if (toggle) {
  toggle.addEventListener("click", () => {
    const open = $("#nav-links").classList.toggle("open");
    toggle.setAttribute("aria-expanded", String(open));
  });
}
copyButtons();
