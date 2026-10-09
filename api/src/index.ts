/**
 * Holibase public read API (Cloudflare Worker in front of Supabase/PostgREST).
 *
 *   GET /v1/countries
 *   GET /v1/public-holidays/{CC}/{YYYY}?subdivision=US-CA&lang=de
 *   GET /v1/public-holidays/{CC}?from=2026-01-01&to=2026-12-31&subdivision=&lang=
 *   GET /v1/school-holidays/{CC}?subdivision=DE-NI&from=2026-08-01&to=2027-07-31
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

  if (parts.length === 0) return { kind: "index" };
  if (parts[0] === "data") return staticFile(url, parts);
  if (parts[0] !== API_VERSION) throw new ApiError(404, "not_found", `Unknown path. Start at ${url.origin}/`);

  const [, resource, rawCountry, rawYear, ...rest] = parts;
  if (rest.length) throw new ApiError(404, "not_found", "Unknown path.");

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
        [from, to] = parseRange(url, `${y}-01-01`, `${y}-12-31`);
      }
      const key = canonical(url.origin, `/v1/public-holidays/${country}`, { from, to, subdivision, lang, categories: categories?.join(",") ?? null });
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
          return json(
            { country, subdivision, from, to, lang, categories: categories ?? ["public"], count: rows.length, holidays: rows, attribution: ATTRIBUTION },
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
      const [from, to] = parseRange(url, today, inAYear);
      const lang = parseLang(url.searchParams.get("lang"));
      const key = canonical(url.origin, `/v1/school-holidays/${country}`, {
        from, to, subdivision, authority, lang, include: includePending ? "pending" : null,
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
          return json(
            {
              country, subdivision, authority, from, to, lang,
              include_pending: includePending,
              count: rows.length,
              calendars,
              periods: rows,
              attribution: ATTRIBUTION,
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
            const res = await supabase(env, `/rest/v1/education_authorities?id=eq.${id}&select=id,country_code,subdivision_code,kind,name,external_ids,website_url,city`);
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

const ATTRIBUTION = "Public holiday data © python-holidays contributors (MIT). https://holibase.org";

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
      static_file: `${o}/data/public-holidays/DE/2026.json`,
    },
    attribution: ATTRIBUTION,
  };
}
