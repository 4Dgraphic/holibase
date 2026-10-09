/**
 * Holibase public read API (Cloudflare Worker in front of Supabase/PostgREST).
 *
 *   GET /v1/countries
 *   GET /v1/public-holidays/{CC}/{YYYY}?subdivision=US-CA&lang=de
 *   GET /v1/public-holidays/{CC}?from=2026-01-01&to=2026-12-31&subdivision=&lang=
 *   GET /v1/school-holidays/{CC}?subdivision=DE-NI&from=2026-08-01&to=2027-07-31
 *   GET /v1/public-holidays/{CC}.ics?subdivision=DE-BY        iCalendar feed (also ?format=ics)
 *   GET /v1/school-holidays/{CC}.ics?subdivision=DE-NI         iCalendar feed (also ?format=ics)
 *   GET /data/...json            static files from R2 (same layout as the repo's data/)
 *   GET /v1/health
 *
 * Every successful response is cached at the edge. Cache hits never reach Supabase
 * and never count against the rate limit.
 */

export interface Env {
  SUPABASE_URL: string;
  SUPABASE_KEY: string;
  TTL_PUBLIC_HOLIDAYS?: string;
  TTL_SCHOOL_HOLIDAYS?: string;
  TTL_REFERENCE?: string;
  DATA?: R2Bucket;
  RATE_LIMITER?: { limit(opts: { key: string }): Promise<{ success: boolean }> };
}

const API_VERSION = "v1";
const MAX_RANGE_DAYS = 3 * 366;

const RE_COUNTRY = /^[A-Z]{2}$/;
const RE_SUBDIVISION = /^[A-Z]{2}-[A-Z0-9]{1,3}$/;
const RE_LANG = /^[a-z]{2,3}(-[a-z]{2,4})?$/i;
const RE_DATE = /^\d{4}-\d{2}-\d{2}$/;
const RE_YEAR = /^\d{4}$/;
const RE_UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

class ApiError extends Error {
  constructor(public status: number, public code: string, message: string) {
    super(message);
  }
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    if (request.method === "OPTIONS") return new Response(null, { status: 204, headers: corsHeaders() });
    if (request.method !== "GET" && request.method !== "HEAD") {
      return errorResponse(new ApiError(405, "method_not_allowed", "Only GET is supported."));
    }

    try {
      const url = new URL(request.url);
      const route = matchRoute(url);

      if (route.kind === "index") return json(indexDoc(url), 200, 300);
      if (route.kind === "health") return json({ status: "ok" }, 200, 0);

      // Edge cache first: normalised URL as key, so ?lang=DE and ?lang=de share one entry.
      const cache = caches.default;
      const cacheKey = new Request(route.cacheKey, { method: "GET" });
      const cached = await cache.match(cacheKey);
      if (cached) return withConditional(request, cached, "HIT");

      // Rate limit only requests that would hit the origin.
      if (env.RATE_LIMITER) {
        const ip = request.headers.get("CF-Connecting-IP") ?? "unknown";
        const { success } = await env.RATE_LIMITER.limit({ key: ip });
        if (!success) throw new ApiError(429, "rate_limited", "Too many requests. Slow down or cache responses on your side.");
      }

      const response = await addEtag(await route.handle(env));
      if (response.status === 200) ctx.waitUntil(cache.put(cacheKey, response.clone()));
      return withConditional(request, response, "MISS");
    } catch (err) {
      if (err instanceof ApiError) return errorResponse(err);
      console.error("unhandled", err);
      return errorResponse(new ApiError(500, "internal_error", "Unexpected error."));
    }
  },
} satisfies ExportedHandler<Env>;

// ---------------------------------------------------------------- routing

type Route =
  | { kind: "index" }
  | { kind: "health" }
  | { kind: "data"; cacheKey: string; handle: (env: Env) => Promise<Response> };

function matchRoute(url: URL): Route {
  const parts = url.pathname.replace(/\/+$/, "").split("/").filter(Boolean);
  // iCalendar: "/v1/school-holidays/DE.ics" or "?format=ics". Calendar apps like a .ics ending.
  let ics = false;
  if (parts.length && parts[parts.length - 1].toLowerCase().endsWith(".ics")) {
    parts[parts.length - 1] = parts[parts.length - 1].slice(0, -4);
    ics = true;
  }
  const format = url.searchParams.get("format");
  if (format && format !== "json" && format !== "ics") throw new ApiError(400, "invalid_format", "format accepts json or ics.");
  if (format === "ics") ics = true;

  if (parts.length === 0) return { kind: "index" };
  if (parts[0] === "data") return staticFile(url, parts);
  if (parts[0] !== API_VERSION) throw new ApiError(404, "not_found", `Unknown path. Start at ${url.origin}/`);

  const [, resource, rawCountry, rawYear, ...rest] = parts;
  if (rest.length) throw new ApiError(404, "not_found", "Unknown path.");
  if (ics && resource !== "public-holidays" && resource !== "school-holidays") {
    throw new ApiError(400, "invalid_format", "iCalendar is available for public-holidays and school-holidays.");
  }

  switch (resource) {
    case "health":
      return { kind: "health" };

    case "countries": {
      if (rawCountry) throw new ApiError(404, "not_found", "Use /v1/countries without further segments.");
      return {
        kind: "data",
        cacheKey: `${url.origin}/v1/countries`,
        handle: async (env) => json(await countries(env), 200, ttl(env.TTL_REFERENCE, 86400)),
      };
    }

    case "public-holidays": {
      const country = parseCountry(rawCountry);
      const subdivision = parseSubdivision(url.searchParams.get("subdivision"), country);
      const lang = parseLang(url.searchParams.get("lang"));
      const categories = parseCategories(url.searchParams.get("categories"));
      let from: string, to: string;
      if (rawYear) {
        if (!RE_YEAR.test(rawYear)) throw new ApiError(400, "invalid_year", "Year must have four digits, e.g. 2026.");
        from = `${rawYear}-01-01`;
        to = `${rawYear}-12-31`;
      } else {
        const y = new Date().getUTCFullYear();
        // Feeds default to last year .. next year, so a subscription keeps rolling forward by itself.
        [from, to] = ics ? parseRange(url, `${y - 1}-01-01`, `${y + 1}-12-31`) : parseRange(url, `${y}-01-01`, `${y}-12-31`);
      }
      const key = canonical(url.origin, `/v1/public-holidays/${country}`, {
        from, to, subdivision, lang, categories: categories?.join(",") ?? null, format: ics ? "ics" : null,
      });
      return {
        kind: "data",
        cacheKey: key,
        handle: async (env) => {
          const rows = await rpc(env, "get_public_holidays", {
            p_country: country,
            p_subdivision: subdivision,
            p_from: from,
            p_to: to,
            p_lang: lang,
            p_categories: categories,
          });
          if (ics) {
            return calendar(
              publicHolidayFeed(rows as PublicHolidayRow[], { country, subdivision, lang, categories }),
              `holibase-public-${subdivision ?? country}`,
              ttl(env.TTL_PUBLIC_HOLIDAYS, 86400),
            );
          }
          return json(
            { country, subdivision, from, to, lang, categories: categories ?? ["public"], count: rows.length, holidays: rows, attribution: ATTRIBUTION, license: LICENSE },
            200,
            ttl(env.TTL_PUBLIC_HOLIDAYS, 86400),
          );
        },
      };
    }

    case "school-holidays": {
      if (rawYear) throw new ApiError(404, "not_found", "Use ?from=&to= for school holidays.");
      const country = parseCountry(rawCountry);
      const subdivision = parseSubdivision(url.searchParams.get("subdivision"), country);
      const authority = parseAuthority(url.searchParams.get("authority"));
      const includePending = parseInclude(url.searchParams.get("include"));
      const today = new Date().toISOString().slice(0, 10);
      const inAYear = new Date(Date.now() + 365 * 864e5).toISOString().slice(0, 10);
      const y = new Date().getUTCFullYear();
      const [from, to] = ics ? parseRange(url, `${y - 1}-01-01`, `${y + 1}-12-31`) : parseRange(url, today, inAYear);
      const lang = parseLang(url.searchParams.get("lang"));
      const key = canonical(url.origin, `/v1/school-holidays/${country}`, {
        from, to, subdivision, authority, lang, include: includePending ? "pending" : null, format: ics ? "ics" : null,
      });
      return {
        kind: "data",
        cacheKey: key,
        handle: async (env) => {
          const scope = { p_country: country, p_subdivision: subdivision, p_authority: authority, p_from: from, p_to: to };
          const [rows, calendars] = await Promise.all([
            rpc(env, "get_school_holidays", { ...scope, p_lang: lang, p_include_pending: includePending || null }),
            rpc(env, "get_school_calendars", { ...scope, p_include_pending: includePending || null }),
          ]);
          if (ics) {
            return calendar(
              schoolHolidayFeed(rows as SchoolPeriodRow[], calendars as SchoolCalendarRow[], { country, subdivision, authority, lang, from, to }),
              `holibase-school-${authority ?? subdivision ?? country}`,
              ttl(env.TTL_SCHOOL_HOLIDAYS, 21600),
            );
          }
          return json(
            {
              country, subdivision, authority, from, to, lang,
              include_pending: includePending,
              count: rows.length,
              calendars,
              periods: rows,
              attribution: ATTRIBUTION,
              license: LICENSE,
            },
            200,
            ttl(env.TTL_SCHOOL_HOLIDAYS, 21600),
          );
        },
      };
    }

    case "authorities": {
      // /v1/authorities?country=US&q=gwinnett&subdivision=US-GA&limit=25   or   /v1/authorities/{id}
      if (rawYear) throw new ApiError(404, "not_found", "Unknown path.");
      if (rawCountry) {
        const id = parseAuthority(rawCountry);
        return {
          kind: "data",
          cacheKey: `${url.origin}/v1/authorities/${id}`,
          handle: async (env) => {
            const res = await supabase(env, `/rest/v1/education_authorities?id=eq.${id}&select=id,country_code,subdivision_code,kind,name,city,student_count,website_url,external_ids`);
            const rows = (await res.json()) as unknown[];
            if (!rows.length) throw new ApiError(404, "not_found", "Authority not found.");
            const cals = await supabase(env, `/rest/v1/school_calendars?authority_id=eq.${id}&status=in.(confirmed,pending)&select=id,school_year,status,origin,first_day,last_day,source_url&order=school_year`);
            return json({ authority: rows[0], calendars: await cals.json() }, 200, ttl(env.TTL_REFERENCE, 86400));
          },
        };
      }
      const qCountry = url.searchParams.get("country");
      const country = qCountry ? parseCountry(qCountry) : null;
      const subdivision = country ? parseSubdivision(url.searchParams.get("subdivision"), country) : null;
      const q = (url.searchParams.get("q") ?? "").trim() || null;
      if (q && q.length > 80) throw new ApiError(400, "invalid_query", "q is too long.");
      if (!country && !q) throw new ApiError(400, "missing_filter", "Give at least ?country= or ?q=.");
      const limit = Math.min(Math.max(Number(url.searchParams.get("limit") ?? 25) || 25, 1), 100);
      const key = canonical(url.origin, "/v1/authorities", { country, subdivision, q: q?.toLowerCase() ?? null, limit: String(limit) });
      return {
        kind: "data",
        cacheKey: key,
        handle: async (env) => {
          const rows = await rpc(env, "search_authorities", { p_country: country, p_q: q, p_subdivision: subdivision, p_limit: limit });
          return json({ country, subdivision, q, count: rows.length, authorities: rows }, 200, ttl(env.TTL_REFERENCE, 86400));
        },
      };
    }
  }
  throw new ApiError(404, "not_found", "Unknown resource.");
}

function staticFile(url: URL, parts: string[]): Route {
  const path = parts.slice(1).join("/");
  if (!/^[A-Za-z0-9_\-\/]+\.json$/.test(path) || path.includes("..")) {
    throw new ApiError(404, "not_found", "Unknown data file.");
  }
  return {
    kind: "data",
    cacheKey: `${url.origin}/data/${path}`,
    handle: async (env) => {
      if (!env.DATA) throw new ApiError(503, "unavailable", "Static data is not configured.");
      const obj = await env.DATA.get(path);
      if (!obj) throw new ApiError(404, "not_found", "Data file not found.");
      return new Response(obj.body, {
        status: 200,
        headers: {
          "Content-Type": "application/json; charset=utf-8",
          "Cache-Control": `public, max-age=${ttl(env.TTL_PUBLIC_HOLIDAYS, 86400)}`,
          ETag: obj.httpEtag,
          ...corsHeaders(),
        },
      });
    },
  };
}

// ---------------------------------------------------------------- upstream

const ATTRIBUTION =
  "Public holidays © python-holidays contributors (MIT). School calendars © Holibase contributors (CC BY 4.0). https://holibase.org";
const LICENSE = { data: "CC-BY-4.0", url: "https://creativecommons.org/licenses/by/4.0/", attribution_required: true };

async function rpc(env: Env, fn: string, params: Record<string, unknown>): Promise<unknown[]> {
  // Omit null params so the SQL defaults apply (e.g. p_categories = {public}).
  const body = Object.fromEntries(Object.entries(params).filter(([, v]) => v !== null && v !== undefined));
  const res = await supabase(env, `/rest/v1/rpc/${fn}`, { method: "POST", body: JSON.stringify(body) });
  const data = await res.json();
  return Array.isArray(data) ? data : [];
}

async function countries(env: Env): Promise<unknown> {
  const [c, s] = await Promise.all([
    supabase(env, "/rest/v1/countries?select=*").then((r) => r.json()),
    supabase(env, "/rest/v1/subdivisions?select=*").then((r) => r.json()),
  ]);
  return { countries: c, subdivisions: s };
}

async function supabase(env: Env, path: string, init: RequestInit = {}): Promise<Response> {
  if (!env.SUPABASE_URL || env.SUPABASE_URL.includes("REPLACE_ME") || !env.SUPABASE_KEY) {
    throw new ApiError(503, "not_configured", "Upstream database is not configured.");
  }
  let res: Response;
  try {
    res = await fetch(env.SUPABASE_URL.replace(/\/$/, "") + path, {
      ...init,
      headers: { apikey: env.SUPABASE_KEY, "Content-Type": "application/json", Accept: "application/json" },
    });
  } catch (e) {
    console.error("supabase unreachable", path, e);
    throw new ApiError(502, "upstream_unreachable", "The database could not be reached.");
  }
  if (!res.ok) {
    console.error("supabase", res.status, path, await res.text());
    throw new ApiError(502, "upstream_error", "The database did not answer as expected.");
  }
  return res;
}

// ---------------------------------------------------------------- params

function parseCountry(raw?: string): string {
  const c = (raw ?? "").toUpperCase();
  if (!RE_COUNTRY.test(c)) throw new ApiError(400, "invalid_country", "Country must be an ISO 3166-1 alpha-2 code, e.g. DE.");
  return c;
}

function parseSubdivision(raw: string | null, country: string): string | null {
  if (!raw) return null;
  const s = raw.toUpperCase();
  if (!RE_SUBDIVISION.test(s) || !s.startsWith(country + "-")) {
    throw new ApiError(400, "invalid_subdivision", `Subdivision must be an ISO 3166-2 code within ${country}, e.g. ${country}-XX.`);
  }
  return s;
}

function parseAuthority(raw: string | null): string | null {
  if (!raw) return null;
  if (!RE_UUID.test(raw)) throw new ApiError(400, "invalid_authority", "authority must be an id from /v1/authorities.");
  return raw.toLowerCase();
}

function parseInclude(raw: string | null): boolean {
  if (!raw) return false;
  if (raw === "pending") return true;
  throw new ApiError(400, "invalid_include", "include accepts only 'pending'.");
}

function parseLang(raw: string | null): string | null {
  if (!raw) return null;
  if (!RE_LANG.test(raw)) throw new ApiError(400, "invalid_lang", "lang must be a language tag such as de or pt-BR.");
  const [base, region] = raw.split("-");
  return region ? `${base.toLowerCase()}-${region.length === 2 ? region.toUpperCase() : region}` : base.toLowerCase();
}

function parseCategories(raw: string | null): string[] | null {
  if (!raw) return null;
  const list = [...new Set(raw.toLowerCase().split(",").map((c) => c.trim()).filter(Boolean))].sort();
  if (!list.length || list.length > 10 || list.some((c) => !/^[a-z_]{2,32}$/.test(c))) {
    throw new ApiError(400, "invalid_categories", "categories must be a comma list such as public,catholic.");
  }
  return list;
}

function parseRange(url: URL, defFrom: string, defTo: string): [string, string] {
  const from = url.searchParams.get("from") ?? defFrom;
  const to = url.searchParams.get("to") ?? defTo;
  for (const [name, v] of [["from", from], ["to", to]] as const) {
    if (!RE_DATE.test(v) || isNaN(Date.parse(v))) throw new ApiError(400, "invalid_date", `${name} must be a date like 2026-08-01.`);
  }
  const days = (Date.parse(to) - Date.parse(from)) / 864e5;
  if (days < 0) throw new ApiError(400, "invalid_range", "from must not be after to.");
  if (days > MAX_RANGE_DAYS) throw new ApiError(400, "range_too_large", "Maximum range is three years per request.");
  return [from, to];
}

function canonical(origin: string, path: string, params: Record<string, string | null>): string {
  const q = new URLSearchParams();
  for (const k of Object.keys(params).sort()) if (params[k]) q.set(k, params[k]!);
  return `${origin}${path}?${q}`;
}

function ttl(raw: string | undefined, fallback: number): number {
  const n = Number(raw);
  return Number.isFinite(n) && n >= 0 ? n : fallback;
}

// ---------------------------------------------------------------- responses

function corsHeaders(): Record<string, string> {
  return {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, If-None-Match",
    "Access-Control-Expose-Headers": "ETag, X-Cache",
    "Access-Control-Max-Age": "86400",
  };
}

function json(data: unknown, status: number, maxAge: number): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": maxAge > 0 ? `public, max-age=${maxAge}` : "no-store",
      ...corsHeaders(),
    },
  });
}

function errorResponse(err: ApiError): Response {
  const res = json({ error: { code: err.code, message: err.message } }, err.status, 0);
  if (err.status === 429) res.headers.set("Retry-After", "60");
  return res;
}

/** Adds a content-hash ETag to a 200 response that has none (computed once, before caching). */
async function addEtag(response: Response): Promise<Response> {
  if (response.status !== 200 || response.headers.get("ETag")) return response;
  const body = await response.arrayBuffer();
  const hash = await crypto.subtle.digest("SHA-1", body);
  const headers = new Headers(response.headers);
  headers.set("ETag", `"${[...new Uint8Array(hash)].map((b) => b.toString(16).padStart(2, "0")).join("")}"`);
  return new Response(body, { status: 200, headers });
}

/** Answers If-None-Match with 304 and marks the cache state. */
function withConditional(request: Request, response: Response, cacheState: "HIT" | "MISS"): Response {
  const headers = new Headers(response.headers);
  headers.set("X-Cache", cacheState);
  const etag = headers.get("ETag");
  const inm = request.headers.get("If-None-Match");
  if (etag && inm && inm.split(",").some((t) => t.trim().replace(/^W\//, "") === etag.replace(/^W\//, ""))) {
    return new Response(null, { status: 304, headers });
  }
  return new Response(request.method === "HEAD" ? null : response.body, { status: response.status, headers });
}

function indexDoc(url: URL) {
  const o = url.origin;
  return {
    name: "Holibase API",
    version: API_VERSION,
    docs: "https://holibase.org",
    endpoints: {
      countries: `${o}/v1/countries`,
      public_holidays_year: `${o}/v1/public-holidays/DE/2026?subdivision=DE-BY&lang=de&categories=public,catholic`,
      public_holidays_range: `${o}/v1/public-holidays/US?from=2026-01-01&to=2026-12-31&subdivision=US-CA`,
      school_holidays: `${o}/v1/school-holidays/DE?subdivision=DE-NI&from=2026-08-01&to=2027-07-31`,
      authorities_search: `${o}/v1/authorities?country=US&q=gwinnett`,
      authority: `${o}/v1/authorities/{id}`,
      school_holidays_authority: `${o}/v1/school-holidays/US?authority={id}&from=2026-08-01&to=2027-07-31`,
      school_holidays_including_unverified: `${o}/v1/school-holidays/US?authority={id}&include=pending`,
      public_holidays_ical: `${o}/v1/public-holidays/DE.ics?subdivision=DE-BY&lang=de`,
      school_holidays_ical: `${o}/v1/school-holidays/DE.ics?subdivision=DE-NI&lang=de`,
      school_holidays_authority_ical: `${o}/v1/school-holidays/US.ics?authority={id}`,
      static_file: `${o}/data/public-holidays/DE/2026.json`,
    },
    attribution: ATTRIBUTION,
    license: LICENSE,
  };
}

// ---------------------------------------------------------------- iCalendar (RFC 5545)

type PublicHolidayRow = {
  date: string; name: string; local_name: string; category: string; scope: string;
  is_observed: boolean; is_estimated: boolean; subdivision_code: string | null; source_id: string;
};
type SchoolPeriodRow = {
  start_date: string; end_date: string; name: string; kind: string; school_year: string;
  calendar_id: string; origin: string; status: string; source_url: string | null;
};
type SchoolCalendarRow = {
  calendar_id: string; school_year: string; title: string | null; status: string; source_url: string | null;
  first_day: string | null; last_day: string | null;
};

type FeedLabels = { public: string; school: string; observed: string; estimated: string; unverified: string; first: string; last: string };
const FEED_LABELS: Record<string, FeedLabels> = {
  en: { public: "Public holidays", school: "School holidays", observed: "observed", estimated: "date estimated", unverified: "unverified", first: "First day of school", last: "Last day of school" },
  de: { public: "Feiertage", school: "Schulferien", observed: "Ersatztag", estimated: "Datum geschätzt", unverified: "unbestätigt", first: "Erster Schultag", last: "Letzter Schultag" },
  fr: { public: "Jours fériés", school: "Vacances scolaires", observed: "jour de remplacement", estimated: "date estimée", unverified: "non vérifié", first: "Rentrée scolaire", last: "Dernier jour d'école" },
  es: { public: "Días festivos", school: "Vacaciones escolares", observed: "trasladado", estimated: "fecha estimada", unverified: "sin verificar", first: "Primer día de clases", last: "Último día de clases" },
  it: { public: "Festività", school: "Vacanze scolastiche", observed: "recupero", estimated: "data stimata", unverified: "non verificato", first: "Primo giorno di scuola", last: "Ultimo giorno di scuola" },
  nl: { public: "Feestdagen", school: "Schoolvakanties", observed: "vervangende dag", estimated: "datum geschat", unverified: "niet bevestigd", first: "Eerste schooldag", last: "Laatste schooldag" },
  pt: { public: "Feriados", school: "Férias escolares", observed: "transferido", estimated: "data estimada", unverified: "não verificado", first: "Primeiro dia de aulas", last: "Último dia de aulas" },
};

function labels(lang: string | null) {
  return FEED_LABELS[(lang ?? "en").split("-")[0]] ?? FEED_LABELS.en;
}

function publicHolidayFeed(
  rows: PublicHolidayRow[],
  o: { country: string; subdivision: string | null; lang: string | null; categories: string[] | null },
): string {
  const l = labels(o.lang);
  const scope = o.subdivision ?? o.country;
  const extra = o.categories && o.categories.join(",") !== "public" ? ` (${o.categories.join(", ")})` : "";
  const events = rows.map((r) => {
    const notes = [r.is_observed ? l.observed : null, r.is_estimated ? l.estimated : null].filter(Boolean);
    return vevent({
      uid: `ph-${scope}-${r.date}-${hash(r.category + "|" + r.local_name)}`,
      start: r.date,
      end: r.date,
      summary: r.name + (notes.length ? ` (${notes.join(", ")})` : ""),
      description: r.name !== r.local_name ? r.local_name : null,
      categories: r.category,
      url: null,
    });
  });
  return vcalendar(`${l.public} ${scope}${extra}`, events);
}

function schoolHolidayFeed(
  rows: SchoolPeriodRow[],
  calendars: SchoolCalendarRow[],
  o: { country: string; subdivision: string | null; authority: string | null; lang: string | null; from: string; to: string },
): string {
  const l = labels(o.lang);
  const title = (o.authority && calendars.find((c) => c.title)?.title) || o.subdivision || o.country;
  const events = rows.map((r) =>
    vevent({
      uid: `sh-${r.calendar_id}-${r.start_date}-${hash(r.kind + "|" + r.name)}`,
      start: r.start_date,
      end: r.end_date,
      summary: r.name + (r.status === "pending" ? ` (${l.unverified})` : ""),
      description: r.source_url,
      categories: r.kind,
      url: r.source_url,
    }),
  );
  // First and last day of instruction, from the calendar metadata.
  for (const c of calendars) {
    for (const [day, label] of [[c.first_day, l.first], [c.last_day, l.last]] as const) {
      if (!day || day < o.from || day > o.to) continue;
      events.push(
        vevent({
          uid: `sh-${c.calendar_id}-${label === l.first ? "first" : "last"}-day`,
          start: day,
          end: day,
          summary: label + (c.status === "pending" ? ` (${l.unverified})` : ""),
          description: c.source_url,
          categories: "school_day",
          url: c.source_url,
        }),
      );
    }
  }
  return vcalendar(`${l.school} ${title}`, events);
}

function vcalendar(name: string, events: string[][]): string {
  const lines = [
    "BEGIN:VCALENDAR",
    "VERSION:2.0",
    "PRODID:-//Holibase//holibase.org//EN",
    "CALSCALE:GREGORIAN",
    "METHOD:PUBLISH",
    `NAME:${esc(name)}`,
    `X-WR-CALNAME:${esc(name)}`,
    `X-WR-CALDESC:${esc(ATTRIBUTION)}`,
    "REFRESH-INTERVAL;VALUE=DURATION:P1D",
    "X-PUBLISHED-TTL:P1D",
    ...events.flat(),
    "END:VCALENDAR",
  ];
  return lines.map(fold).join("\r\n") + "\r\n";
}

function vevent(e: { uid: string; start: string; end: string; summary: string; description: string | null; categories: string; url: string | null }): string[] {
  const out = [
    "BEGIN:VEVENT",
    `UID:${e.uid}@holibase.org`,
    `DTSTAMP:${dtstamp()}`,
    `DTSTART;VALUE=DATE:${icsDate(e.start)}`,
    `DTEND;VALUE=DATE:${icsDate(addDay(e.end))}`, // DTEND is exclusive for all-day events
    `SUMMARY:${esc(e.summary)}`,
    `CATEGORIES:${esc(e.categories)}`,
    "TRANSP:TRANSPARENT",
  ];
  if (e.description) out.push(`DESCRIPTION:${esc(e.description)}`);
  if (e.url && /^https?:\/\//.test(e.url)) out.push(`URL:${e.url}`);
  out.push("END:VEVENT");
  return out;
}

function calendar(body: string, filename: string, maxAge: number): Response {
  return new Response(body, {
    status: 200,
    headers: {
      "Content-Type": "text/calendar; charset=utf-8",
      "Content-Disposition": `inline; filename="${filename.replace(/[^A-Za-z0-9_.-]/g, "-")}.ics"`,
      "Cache-Control": `public, max-age=${maxAge}`,
      ...corsHeaders(),
    },
  });
}

/** Same value for a whole UTC day, so the body (and its ETag) only changes when the data does or once a day. */
function dtstamp(): string {
  return new Date().toISOString().slice(0, 10).replace(/-/g, "") + "T000000Z";
}

function icsDate(d: string): string {
  return d.replace(/-/g, "");
}

function addDay(d: string): string {
  return new Date(Date.parse(d + "T00:00:00Z") + 864e5).toISOString().slice(0, 10);
}

function esc(s: string): string {
  return s.replace(/\\/g, "\\\\").replace(/;/g, "\;").replace(/,/g, "\\,").replace(/\r?\n/g, "\\n");
}

/** Folds lines longer than 75 octets (RFC 5545 3.1) without splitting UTF-8 characters. */
function fold(line: string): string {
  const enc = new TextEncoder();
  if (enc.encode(line).length <= 75) return line;
  const parts: string[] = [];
  let cur = "";
  let size = 0;
  for (const ch of line) {
    const n = enc.encode(ch).length;
    if (size + n > (parts.length ? 74 : 75)) {
      parts.push(cur);
      cur = "";
      size = 0;
    }
    cur += ch;
    size += n;
  }
  parts.push(cur);
  return parts.join("\r\n ");
}

/** FNV-1a, 32 bit, hex. Stable event UIDs across rebuilds. */
function hash(s: string): string {
  let h = 0x811c9dc5;
  for (const b of new TextEncoder().encode(s)) {
    h ^= b;
    h = Math.imul(h, 0x01000193) >>> 0;
  }
  return h.toString(16).padStart(8, "0");
}
