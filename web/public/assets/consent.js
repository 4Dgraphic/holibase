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

// Banner text in the page's language: [text, privacy, accept, decline]
const CONSENT_TEXT = {
  en: ["Holibase uses Google Analytics to count visits, only if you agree. It sets cookies and sends usage data to Google.", "Privacy", "Accept", "Decline"],
  de: ["Holibase nutzt Google Analytics, um Besuche zu zählen, nur wenn du zustimmst. Dabei werden Cookies gesetzt und Nutzungsdaten an Google gesendet.", "Datenschutz", "Zustimmen", "Ablehnen"],
  fr: ["Holibase utilise Google Analytics pour compter les visites, seulement avec votre accord. Des cookies sont déposés et des données d'utilisation envoyées à Google.", "Confidentialité", "Accepter", "Refuser"],
  nl: ["Holibase gebruikt Google Analytics om bezoeken te tellen, alleen als je akkoord gaat. Daarbij worden cookies geplaatst en gebruiksgegevens naar Google gestuurd.", "Privacy", "Akkoord", "Weigeren"],
  es: ["Holibase usa Google Analytics para contar visitas, solo si lo aceptas. Instala cookies y envía datos de uso a Google.", "Privacidad", "Aceptar", "Rechazar"],
  it: ["Holibase usa Google Analytics per contare le visite, solo se accetti. Imposta cookie e invia dati di utilizzo a Google.", "Privacy", "Accetta", "Rifiuta"],
  pl: ["Holibase korzysta z Google Analytics do liczenia odwiedzin, tylko za Twoją zgodą. Zapisuje pliki cookie i wysyła dane o korzystaniu do Google.", "Prywatność", "Akceptuję", "Odrzucam"],
  pt: ["O Holibase usa o Google Analytics para contar visitas, só com o seu consentimento. Guarda cookies e envia dados de utilização à Google.", "Privacidade", "Aceitar", "Recusar"],
  cs: ["Holibase používá Google Analytics k počítání návštěv, jen s vaším souhlasem. Ukládá cookies a posílá údaje o používání společnosti Google.", "Soukromí", "Souhlasím", "Odmítnout"],
  sk: ["Holibase používa Google Analytics na počítanie návštev, len s vaším súhlasom. Ukladá cookies a posiela údaje o používaní spoločnosti Google.", "Súkromie", "Súhlasím", "Odmietnuť"],
  ro: ["Holibase folosește Google Analytics pentru a număra vizitele, doar cu acordul tău. Setează cookie-uri și trimite date de utilizare către Google.", "Confidențialitate", "Accept", "Refuz"],
};

let banner;
function showBanner() {
  if (banner) { banner.hidden = false; banner.querySelector("button").focus(); return; }
  banner = document.createElement("div");
  banner.className = "consent";
  banner.setAttribute("role", "dialog");
  banner.setAttribute("aria-label", "Cookie settings");
  const [text, privacy, accept, decline] = CONSENT_TEXT[(document.documentElement.lang || "en").slice(0, 2)] || CONSENT_TEXT.en;
  banner.innerHTML = `
    <p>${text}
      <a href="/privacy/#analytics">${privacy}</a></p>
    <div class="row">
      <button class="btn btn-primary btn-sm" type="button" data-choice="granted">${accept}</button>
      <button class="btn btn-secondary btn-sm" type="button" data-choice="denied">${decline}</button>
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
