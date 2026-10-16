// Google Analytics only after explicit consent (TTDSG § 25 / GDPR). Nothing is loaded or stored before.
const GA_ID = "G-QJ94W9ZYHP";
const KEY = "hb-consent"; // "granted" | "denied", kept in localStorage on this device only

const read = () => { try { return localStorage.getItem(KEY); } catch { return null; } };
const write = (v) => { try { localStorage.setItem(KEY, v); } catch { /* storage blocked: ask again next time */ } };

function loadAnalytics() {
  if (window.gtag) return;
  window.dataLayer = window.dataLayer || [];
  window.gtag = function gtag() { window.dataLayer.push(arguments); };
  window.gtag("js", new Date());
  window.gtag("config", GA_ID);
  const s = document.createElement("script");
  s.async = true;
  s.src = `https://www.googletagmanager.com/gtag/js?id=${GA_ID}`;
  document.head.append(s);
}

function clearAnalyticsCookies() {
  const host = location.hostname.replace(/^www\./, "");
  for (const c of document.cookie.split(";")) {
    const name = c.split("=")[0].trim();
    if (!/^_ga/.test(name)) continue;
    for (const domain of ["", `; domain=${host}`, `; domain=.${host}`]) document.cookie = `${name}=; Max-Age=0; path=/${domain}`;
  }
}

let banner;
function showBanner() {
  if (banner) { banner.hidden = false; banner.querySelector("button").focus(); return; }
  banner = document.createElement("div");
  banner.className = "consent";
  banner.setAttribute("role", "dialog");
  banner.setAttribute("aria-label", "Cookie settings");
  banner.innerHTML = `
    <p>Holibase uses Google Analytics to count visits, only if you agree. It sets cookies and sends usage data to Google.
      <a href="/privacy/#analytics">Privacy</a></p>
    <div class="row">
      <button class="btn btn-primary btn-sm" type="button" data-choice="granted">Accept</button>
      <button class="btn btn-secondary btn-sm" type="button" data-choice="denied">Decline</button>
    </div>`;
  banner.addEventListener("click", (e) => {
    const choice = e.target.closest("[data-choice]")?.dataset.choice;
    if (!choice) return;
    const before = read();
    write(choice);
    banner.hidden = true;
    if (choice === "granted") loadAnalytics();
    else if (before === "granted") { clearAnalyticsCookies(); location.reload(); }
  });
  document.body.append(banner);
}

const state = read();
if (state === "granted") loadAnalytics();
else if (state !== "denied") showBanner();
for (const b of document.querySelectorAll("[data-consent-open]")) b.addEventListener("click", showBanner);
