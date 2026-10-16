import { API } from "./site.js";

// Redoc themed with the Holibase light tokens.
const theme = {
  spacing: { unit: 5, sectionHorizontal: 32, sectionVertical: 24 },
  breakpoints: { small: "50rem", medium: "75rem", large: "105rem" },
  colors: {
    primary: { main: "#0b7a54" },
    success: { main: "#0b7a54" },
    warning: { main: "#8a5a00" },
    error: { main: "#c0402d" },
    text: { primary: "#0f2d3a", secondary: "#4a6572" },
    border: { dark: "#7d939d", light: "#d5dee3" },
    http: { get: "#0b7a54", post: "#0f2d3a" },
  },
  typography: {
    fontSize: "15px",
    lineHeight: "1.6",
    fontFamily: "Inter, system-ui, sans-serif",
    headings: { fontFamily: "Outfit, system-ui, sans-serif", fontWeight: "600" },
    code: { fontFamily: "'JetBrains Mono', ui-monospace, monospace", fontSize: "13px", color: "#0f2d3a", backgroundColor: "#eef2f4" },
    links: { color: "#0b7a54", visited: "#0b7a54", hover: "#0f2d3a" },
  },
  sidebar: { width: "260px", backgroundColor: "#ffffff", textColor: "#0f2d3a", activeTextColor: "#0b7a54" },
  rightPanel: { backgroundColor: "#0f2d3a", textColor: "#eaf3f0", width: "40%" },
  codeBlock: { backgroundColor: "#071419" },
};

const s = document.createElement("script");
s.src = "https://cdn.jsdelivr.net/npm/redoc@2.1.5/bundles/redoc.standalone.js";
s.onload = () => {
  window.Redoc.init(`${API}/openapi.json`, {
    theme, hideDownloadButton: false, pathInMiddlePanel: true, expandResponses: "200", nativeScrollbars: true,
    scrollYOffset: 96, hideHostname: false, sortPropsAlphabetically: false,
  }, document.getElementById("redoc"));
};
s.onerror = () => {
  document.getElementById("redoc").innerHTML =
    '<p class="muted" style="padding: 32px">The reference viewer could not be loaded. The spec is at <a href="https://api.holibase.org/openapi.json">api.holibase.org/openapi.json</a>.</p>';
};
document.head.append(s);
