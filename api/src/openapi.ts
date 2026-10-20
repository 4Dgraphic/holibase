/**
 * OpenAPI 3.1 description of the Holibase API. Served at /openapi.json and rendered at /docs.
 * Keep it in step with index.ts: scripts/check_openapi.py validates live responses against it after
 * every deploy, so a field that changes in code without changing here fails the deploy workflow.
 */

const nullable = (schema: Record<string, unknown>) => ({ ...schema, type: [schema.type as string, "null"] });
const date = { type: "string", format: "date", examples: ["2026-12-21"] };
const ref = (name: string) => ({ $ref: `#/components/schemas/${name}` });

const attribution = {
  attribution: { type: "string", description: "Credit line to show where the data is displayed." },
  license: ref("License"),
};

const icsNote =
  "Append `.ics` to the country (`/DE.ics`) or add `format=ics` to get an iCalendar feed instead of JSON. " +
  "Without `from`/`to` a feed covers January 1 of last year to December 31 of next year, so a subscription moves forward by itself.";

export const openapi = {
  openapi: "3.1.0",
  info: {
    title: "Holibase API",
    version: "1.0.0",
    summary: "Public holidays and school holidays worldwide, free and open.",
    description:
      "Holibase is an open, non-profit database of public holidays and school holidays.\n\n" +
      "* **Public holidays** for 247 countries and their regions, 2020 to ten years ahead, names in every language the source offers.\n" +
      "* **School holidays** per region (German states, French zones, Dutch regions, ...) and per school authority " +
      "(all ~19,600 US school districts are searchable; calendars exist for the largest ones).\n" +
      "* **Calendar feeds** (iCalendar) for every query, ready to subscribe to in Apple Calendar, Google Calendar or Outlook.\n\n" +
      "No key, no sign-up. Responses are cached at the edge; please cache on your side too. " +
      "Requests that miss the cache are limited to 120 per minute per IP.\n\n" +
      "**Licence:** Holibase's own data is CC BY 4.0, holiday data from python-holidays is MIT, the US district directory " +
      "is public domain (NCES). Credit \"Holibase (holibase.org), CC BY 4.0\" where you show the data; every response " +
      "carries the exact `attribution` line.",
    contact: { name: "Holibase", url: "https://holibase.org" },
    license: { name: "Data: CC BY 4.0 (own data), MIT (python-holidays)", url: "https://creativecommons.org/licenses/by/4.0/" },
  },
  servers: [{ url: "https://api.holibase.org" }],
  tags: [
    { name: "Public holidays" },
    { name: "School holidays" },
    { name: "School authorities", description: "School districts, councils, zones and other bodies that set their own school calendar." },
    { name: "Submissions", description: "Send missing or wrong school holidays." },
    { name: "Reference" },
  ],
  paths: {
    "/v1/countries": {
      get: {
        tags: ["Reference"],
        operationId: "listCountries",
        summary: "Countries and subdivisions",
        description: "Every country and subdivision (state, province, canton, region) Holibase knows, with codes and names.",
        responses: {
          "200": {
            description: "Countries and subdivisions.",
            content: { "application/json": { schema: ref("CountriesResponse") } },
          },
          "429": ref_response("RateLimited"),
          "502": ref_response("Upstream"),
        },
      },
    },
    "/v1/coverage": {
      get: {
        tags: ["Reference"],
        operationId: "getCoverage",
        summary: "What Holibase covers",
        description: "Live coverage figures: public holiday countries and date range, school holiday coverage per country, US district directory.",
        responses: {
          "200": { description: "Coverage figures.", content: { "application/json": { schema: ref("CoverageResponse") } } },
          "429": ref_response("RateLimited"),
          "502": ref_response("Upstream"),
        },
      },
    },
    "/v1/public-holidays/{country}/{year}": {
      get: {
        tags: ["Public holidays"],
        operationId: "getPublicHolidaysYear",
        summary: "Public holidays of one calendar year",
        description:
          "Public holidays of a country, or of one of its regions, for one calendar year. " +
          "A region returns its complete set, nationwide holidays included (`scope` tells them apart).",
        parameters: [p("country"), p("year"), p("subdivision"), p("lang"), p("categories"), p("format")],
        responses: holidayResponses("PublicHolidaysResponse"),
      },
    },
    "/v1/public-holidays/{country}": {
      get: {
        tags: ["Public holidays"],
        operationId: "getPublicHolidays",
        summary: "Public holidays in a date range",
        description:
          "Public holidays in a date range (at most three years). Without `from`/`to`: the current calendar year. " + icsNote,
        parameters: [p("country"), p("from"), p("to"), p("subdivision"), p("lang"), p("categories"), p("format")],
        responses: holidayResponses("PublicHolidaysResponse"),
      },
    },
    "/v1/school-holidays/{country}": {
      get: {
        tags: ["School holidays"],
        operationId: "getSchoolHolidays",
        summary: "School holidays of a region or school authority",
        description:
          "School holidays (breaks, single days off, teacher days, early release days) for a region (`subdivision`) or a " +
          "school authority (`authority`, see /v1/authorities). Without either: the nationwide calendar, where one exists.\n\n" +
          "`calendars` describes the school years found (first and last day of school, source, status); `periods` lists the days off. " +
          "`coverage` says whether data exists at all, so an empty list is never mistaken for \"no holidays\".\n\n" +
          "Without `from`/`to`: today to twelve months ahead. " + icsNote,
        parameters: [p("country"), p("subdivision"), p("authority"), p("from"), p("to"), p("lang"), p("include"), p("format")],
        responses: holidayResponses("SchoolHolidaysResponse"),
      },
    },
    "/v1/authorities": {
      get: {
        tags: ["School authorities"],
        operationId: "searchAuthorities",
        summary: "Search school authorities",
        description:
          "Find a school district or other school authority by name, city or official id (e.g. the US NCES LEAID). " +
          "Matches by exact id first, then name prefix, then similarity; authorities with calendars and larger ones rank higher. " +
          "Give at least `country` or `q`.",
        parameters: [
          { name: "country", in: "query", schema: { type: "string", pattern: "^[A-Za-z]{2}$" }, example: "US", description: "ISO 3166-1 alpha-2 code." },
          { name: "q", in: "query", schema: { type: "string", maxLength: 80 }, example: "gwinnett", description: "Name, city or official id." },
          p("subdivision"),
          { name: "limit", in: "query", schema: { type: "integer", minimum: 1, maximum: 100, default: 25 } },
        ],
        responses: {
          "200": { description: "Matching authorities.", content: { "application/json": { schema: ref("AuthoritySearchResponse") } } },
          "400": ref_response("BadRequest"),
          "429": ref_response("RateLimited"),
          "502": ref_response("Upstream"),
        },
      },
    },
    "/v1/authorities/{id}": {
      get: {
        tags: ["School authorities"],
        operationId: "getAuthority",
        summary: "One school authority",
        description: "An authority with the school calendars Holibase has for it.",
        parameters: [{ name: "id", in: "path", required: true, schema: { type: "string", format: "uuid" } }],
        responses: {
          "200": { description: "The authority and its calendars.", content: { "application/json": { schema: ref("AuthorityResponse") } } },
          "400": ref_response("BadRequest"),
          "404": ref_response("NotFound"),
          "429": ref_response("RateLimited"),
          "502": ref_response("Upstream"),
        },
      },
    },
    "/v1/submissions": {
      post: {
        tags: ["Submissions"],
        operationId: "submitSchoolCalendar",
        summary: "Send a school calendar",
        description:
          "Missing or wrong school holidays for a region or school authority, with a link to the official calendar. " +
          "Used by the form at https://holibase.org/submit/. Every submission is checked against the linked document " +
          "before it appears in the API (usually within a day). Submitted data is published under CC BY 4.0. " +
          "Limited to 5 requests per minute per IP.",
        requestBody: {
          required: true,
          content: { "application/json": { schema: ref("SubmissionRequest") } },
        },
        responses: {
          "201": {
            description: "Received; it is checked against the source before it is published.",
            content: { "application/json": { schema: {
              type: "object", required: ["id", "status"],
              properties: { id: { type: "string", format: "uuid" }, status: { const: "received" } },
            } } },
          },
          "400": ref_response("BadRequest"),
          "429": ref_response("RateLimited"),
          "502": ref_response("Upstream"),
        },
      },
    },
    "/v1/health": {
      get: {
        tags: ["Reference"],
        operationId: "health",
        summary: "Liveness",
        responses: {
          "200": {
            description: "The API is up.",
            content: { "application/json": { schema: { type: "object", properties: { status: { const: "ok" } }, required: ["status"] } } },
          },
        },
      },
    },
  },
  components: {
    parameters: {
      country: {
        name: "country", in: "path", required: true,
        description: "ISO 3166-1 alpha-2 country code, case-insensitive. Append `.ics` for an iCalendar feed.",
        schema: { type: "string", pattern: "^[A-Za-z]{2}(\\.ics)?$" }, example: "DE",
      },
      year: { name: "year", in: "path", required: true, schema: { type: "string", pattern: "^\\d{4}(\\.ics)?$" }, example: "2026" },
      from: { name: "from", in: "query", schema: date, description: "First day of the range (inclusive)." },
      to: { name: "to", in: "query", schema: date, description: "Last day of the range (inclusive). At most three years after `from`." },
      subdivision: {
        name: "subdivision", in: "query", example: "DE-BY",
        description: "ISO 3166-2 code within the country (case-insensitive). Named areas without an ISO code use slugs such as `DE-AUGSBURG`.",
        schema: { type: "string" },
      },
      authority: {
        name: "authority", in: "query", schema: { type: "string", format: "uuid" },
        description: "Id of a school authority from /v1/authorities. Takes precedence over `subdivision`.",
      },
      lang: {
        name: "lang", in: "query", example: "de", schema: { type: "string" },
        description: "Language for names (`de`, `en-US`, `pt-BR` ...). Falls back to the base language, then English, then the local name.",
      },
      categories: {
        name: "categories", in: "query", example: "public,catholic", schema: { type: "string" },
        description: "Comma-separated holiday categories. Default `public`. Others, depending on the country: `bank`, `government`, `optional`, and religious categories such as `catholic`.",
      },
      include: {
        name: "include", in: "query", schema: { type: "string", enum: ["pending"] },
        description: "`pending` also returns calendars that are not verified yet (marked `status: pending`).",
      },
      format: { name: "format", in: "query", schema: { type: "string", enum: ["json", "ics"], default: "json" }, description: "`ics` returns an iCalendar feed." },
    },
    responses: {
      BadRequest: { description: "A parameter is invalid.", content: { "application/json": { schema: ref("Error") } } },
      NotFound: { description: "Unknown path or id.", content: { "application/json": { schema: ref("Error") } } },
      RateLimited: {
        description: "Too many requests that missed the cache (120 per minute per IP). Retry after the `Retry-After` seconds.",
        headers: { "Retry-After": { schema: { type: "integer" } } },
        content: { "application/json": { schema: ref("Error") } },
      },
      Upstream: { description: "The database could not be reached. Retry later.", content: { "application/json": { schema: ref("Error") } } },
    },
    schemas: {
      SubmissionRequest: {
        type: "object",
        required: ["country", "school_year", "source_url", "periods"],
        properties: {
          country: { type: "string", pattern: "^[A-Za-z]{2}$", examples: ["DE"] },
          subdivision: { type: "string", examples: ["DE-NI"], description: "ISO 3166-2 region, if the calendar is for a region." },
          authority: { type: "string", format: "uuid", description: "School authority id from /v1/authorities, if the calendar is for one." },
          school_year: { type: "string", pattern: "^\\d{4}(-\\d{2})?$", examples: ["2027-28"] },
          source_url: { type: "string", format: "uri", description: "Link to the official calendar (page or PDF)." },
          first_day: { ...date, description: "First day of school, if known." },
          last_day: { ...date, description: "Last day of school, if known." },
          periods: {
            type: "array", minItems: 1, maxItems: 40,
            items: {
              type: "object", required: ["start_date"],
              properties: {
                name: { type: "string", maxLength: 120, examples: ["Herbstferien"] },
                start_date: date,
                end_date: { ...date, description: "Last day off; the start date if omitted." },
                kind: { type: "string", enum: ["break", "holiday", "teacher_day", "other"] },
              },
            },
          },
          note: { type: "string", maxLength: 1000, description: "Anything we should know. Please no personal data." },
          lang: { type: "string", examples: ["de"], description: "Language of the names." },
        },
      },
      Error: {
        type: "object",
        properties: {
          error: {
            type: "object",
            properties: {
              code: { type: "string", examples: ["invalid_country", "invalid_date", "range_too_large", "rate_limited"] },
              message: { type: "string" },
            },
            required: ["code", "message"],
          },
        },
        required: ["error"],
      },
      License: {
        type: "object",
        properties: {
          data: { type: "string", examples: ["CC-BY-4.0"] },
          url: { type: "string", format: "uri" },
          attribution_required: { type: "boolean" },
        },
        required: ["data", "url", "attribution_required"],
      },
      PublicHoliday: {
        type: "object",
        properties: {
          date,
          name: { type: "string", description: "Name in the requested language (with fallback)." },
          local_name: { type: "string", description: "Name in the country's default language." },
          category: { type: "string", examples: ["public"] },
          scope: { type: "string", enum: ["national", "regional"], description: "Nationwide holiday or one of this region only." },
          is_observed: { type: "boolean", description: "A substitute or moved day off (e.g. a holiday on a Sunday observed on Monday)." },
          is_estimated: { type: "boolean", description: "The date depends on moon sighting and can still move." },
          subdivision_code: nullable({ type: "string" }),
          source_id: { type: "string", examples: ["python-holidays"] },
        },
        required: ["date", "name", "local_name", "category", "scope", "is_observed", "is_estimated", "subdivision_code", "source_id"],
      },
      PublicHolidaysResponse: {
        type: "object",
        properties: {
          country: { type: "string" },
          subdivision: nullable({ type: "string" }),
          from: date, to: date,
          lang: nullable({ type: "string" }),
          categories: { type: "array", items: { type: "string" } },
          count: { type: "integer" },
          holidays: { type: "array", items: ref("PublicHoliday") },
          ...attribution,
        },
        required: ["country", "subdivision", "from", "to", "lang", "categories", "count", "holidays", "attribution", "license"],
      },
      SchoolPeriod: {
        type: "object",
        properties: {
          start_date: date,
          end_date: { ...date, description: "Inclusive." },
          name: { type: "string" },
          kind: {
            type: "string", enum: ["break", "holiday", "teacher_day", "early_release", "other"],
            description: "`break`: several days off. `holiday`: a single day off. `teacher_day`: no school for students. " +
              "`early_release`: school ends early. `other`: another closure.",
          },
          school_year: { type: "string", examples: ["2026-27", "2027"] },
          calendar_id: { type: "string", format: "uuid" },
          origin: { type: "string", enum: ["official", "editorial", "community", "library"] },
          status: { type: "string", enum: ["confirmed", "pending"] },
          confirmations: { type: "integer" },
          source_url: nullable({ type: "string" }),
        },
        required: ["start_date", "end_date", "name", "kind", "school_year", "calendar_id", "origin", "status", "confirmations", "source_url"],
      },
      SchoolCalendar: {
        type: "object",
        properties: {
          calendar_id: { type: "string", format: "uuid" },
          school_year: { type: "string" },
          origin: {
            type: "string", enum: ["official", "editorial", "community", "library"],
            description: "`official`: government open data. `editorial`: researched by Holibase. `community`: submitted. `library`: a maintained dataset, python-holidays or OpenHolidays (see `source_id`).",
          },
          status: { type: "string", enum: ["confirmed", "pending"] },
          first_day: nullable(date),
          last_day: nullable(date),
          title: nullable({ type: "string" }),
          source_url: nullable({ type: "string" }),
          source_retrieved_at: nullable({ type: "string", format: "date-time" }),
          notes: nullable({ type: "string" }),
          source_id: {
            type: "string",
            description: "Where the calendar comes from, e.g. `python-holidays`, `openholidays`, `education-gouv-fr`, `editorial`.",
          },
          license: {
            ...nullable({ type: "string" }),
            description: "Licence of this calendar's data (SPDX id). Calendars from OpenHolidays are `ODbL-1.0` (share-alike); the response `attribution` then credits OpenHolidays.",
          },
        },
        required: ["calendar_id", "school_year", "origin", "status", "first_day", "last_day", "title", "source_url", "source_retrieved_at", "notes", "source_id", "license"],
      },
      Coverage: {
        oneOf: [
          {
            title: "available",
            type: "object",
            properties: {
              status: { const: "available" },
              school_years: { type: "array", items: { type: "string" } },
              unverified: { type: "boolean", description: "At least one returned calendar is pending." },
            },
            required: ["status", "school_years", "unverified"],
          },
          {
            title: "none",
            type: "object",
            properties: {
              status: { const: "none" },
              school_years: { type: "array", maxItems: 0 },
              message: { type: "string" },
              pending_available: { type: "boolean", description: "Unverified calendars exist; request them with `include=pending`." },
              public_holidays: { type: "string", format: "uri", description: "The public holidays of the same region and range." },
            },
            required: ["status", "school_years", "message", "pending_available", "public_holidays"],
          },
        ],
      },
      SchoolHolidaysResponse: {
        type: "object",
        properties: {
          country: { type: "string" },
          subdivision: nullable({ type: "string" }),
          authority: nullable({ type: "string", format: "uuid" }),
          from: date, to: date,
          lang: nullable({ type: "string" }),
          include_pending: { type: "boolean" },
          coverage: ref("Coverage"),
          count: { type: "integer" },
          calendars: { type: "array", items: ref("SchoolCalendar") },
          periods: { type: "array", items: ref("SchoolPeriod") },
          ...attribution,
        },
        required: ["country", "subdivision", "authority", "from", "to", "lang", "include_pending", "coverage", "count", "calendars", "periods", "attribution", "license"],
      },
      AuthoritySummary: {
        type: "object",
        properties: {
          id: { type: "string", format: "uuid" },
          country_code: { type: "string" },
          subdivision_code: nullable({ type: "string" }),
          kind: { type: "string", enum: ["school_district", "local_authority", "school_board", "academy_trust", "other"] },
          name: { type: "string" },
          city: nullable({ type: "string" }),
          student_count: nullable({ type: "integer" }),
          external_ids: {
            type: "object", additionalProperties: true,
            description: "Official ids and facts, e.g. `nces_leaid`, `nces_name`, `county`, `lat`, `lon`, `grades`, `calendar_feed_url`.",
          },
          school_years: { type: "array", items: { type: "string" }, description: "School years with a calendar (confirmed or pending)." },
          calendars_confirmed: { type: "integer" },
          calendars_pending: { type: "integer" },
        },
        required: ["id", "country_code", "subdivision_code", "kind", "name", "city", "student_count", "external_ids", "school_years", "calendars_confirmed", "calendars_pending"],
      },
      AuthoritySearchResponse: {
        type: "object",
        properties: {
          country: nullable({ type: "string" }),
          subdivision: nullable({ type: "string" }),
          q: nullable({ type: "string" }),
          count: { type: "integer" },
          authorities: { type: "array", items: ref("AuthoritySummary") },
        },
        required: ["country", "subdivision", "q", "count", "authorities"],
      },
      AuthorityResponse: {
        type: "object",
        properties: {
          authority: {
            type: "object",
            properties: {
              id: { type: "string", format: "uuid" },
              country_code: { type: "string" },
              subdivision_code: nullable({ type: "string" }),
              kind: { type: "string" },
              name: { type: "string" },
              city: nullable({ type: "string" }),
              student_count: nullable({ type: "integer" }),
              website_url: nullable({ type: "string" }),
              external_ids: { type: "object", additionalProperties: true },
            },
            required: ["id", "country_code", "subdivision_code", "kind", "name", "city", "student_count", "website_url", "external_ids"],
          },
          calendars: {
            type: "array",
            items: {
              type: "object",
              properties: {
                id: { type: "string", format: "uuid" },
                school_year: { type: "string" },
                status: { type: "string", enum: ["confirmed", "pending"] },
                origin: { type: "string" },
                first_day: nullable(date),
                last_day: nullable(date),
                source_url: nullable({ type: "string" }),
              },
              required: ["id", "school_year", "status", "origin", "first_day", "last_day", "source_url"],
            },
          },
        },
        required: ["authority", "calendars"],
      },
      Country: {
        type: "object",
        properties: {
          code: { type: "string" },
          alpha3: nullable({ type: "string" }),
          names: { type: "object", additionalProperties: { type: "string" }, description: "Name per language tag." },
          default_language: nullable({ type: "string" }),
          languages: nullable({ type: "array", items: { type: "string" } }),
          holiday_categories: nullable({ type: "array", items: { type: "string" } }),
          school_holiday_level: nullable({ type: "string" }),
          updated_at: { type: "string", format: "date-time" },
        },
        required: ["code", "names"],
      },
      Subdivision: {
        type: "object",
        properties: {
          code: { type: "string", examples: ["DE-BY"] },
          country_code: { type: "string" },
          parent_code: nullable({ type: "string" }),
          source_code: nullable({ type: "string" }),
          name: nullable({ type: "string" }),
          names: nullable({ type: "object", additionalProperties: { type: "string" } }),
          kind: nullable({ type: "string" }),
          iso_verified: nullable({ type: "boolean" }),
          updated_at: { type: "string", format: "date-time" },
        },
        required: ["code", "country_code"],
      },
      CoverageResponse: {
        type: "object",
        properties: {
          public_holidays: {
            type: "object",
            properties: { countries: { type: "integer" }, subdivisions: { type: "integer" }, first_date: date, last_date: date },
            required: ["countries", "subdivisions", "first_date", "last_date"],
          },
          school_holidays: {
            type: "object",
            properties: {
              countries: { type: "integer" },
              calendars: { type: "integer", description: "Verified school calendars (one per scope and school year)." },
              by_country: {
                type: "array",
                items: {
                  type: "object",
                  properties: {
                    country_code: { type: "string" },
                    name: nullable({ type: "string" }),
                    scopes: { type: "integer", description: "Regions and authorities with a calendar." },
                    scopes_verified: { type: "integer" },
                    authorities: { type: "integer" },
                    first_school_year: nullable({ type: "string" }),
                    last_school_year: nullable({ type: "string" }),
                    origins: { type: "array", items: { type: "string", enum: ["official", "editorial", "community", "library"] } },
                    sources: { type: "array", items: { type: "string" }, description: "Source ids of the calendars, e.g. python-holidays, openholidays." },
                  },
                  required: ["country_code", "name", "scopes", "scopes_verified", "authorities", "first_school_year", "last_school_year", "origins"],
                },
              },
            },
            required: ["countries", "calendars", "by_country"],
          },
          us_districts: {
            type: "object",
            properties: {
              directory: { type: "integer", description: "Active US school districts and agencies (NCES)." },
              verified: { type: "integer", description: "Districts with a verified calendar." },
              students: nullable({ type: "integer" }),
              students_verified: nullable({ type: "integer" }),
            },
            required: ["directory", "verified", "students", "students_verified"],
          },
          generated_at: { type: "string", format: "date-time" },
        },
        required: ["public_holidays", "school_holidays", "us_districts", "generated_at"],
      },
      CountriesResponse: {
        type: "object",
        properties: {
          countries: { type: "array", items: ref("Country") },
          subdivisions: { type: "array", items: ref("Subdivision") },
        },
        required: ["countries", "subdivisions"],
      },
    },
  },
} as const;

// ---------------------------------------------------------------- helpers (hoisted function declarations)

function p(name: string) {
  return { $ref: `#/components/parameters/${name}` };
}

function ref_response(name: string) {
  return { $ref: `#/components/responses/${name}` };
}

function holidayResponses(schema: string) {
  return {
    "200": {
      description: "JSON by default; an iCalendar feed with `.ics` or `format=ics`.",
      headers: { ETag: { schema: { type: "string" } }, "X-Cache": { schema: { type: "string", enum: ["HIT", "MISS"] } } },
      content: {
        "application/json": { schema: { $ref: `#/components/schemas/${schema}` } },
        "text/calendar": { schema: { type: "string" }, example: "BEGIN:VCALENDAR\r\nVERSION:2.0\r\n...\r\nEND:VCALENDAR\r\n" },
      },
    },
    "304": { description: "Not modified (If-None-Match matched the ETag)." },
    "400": ref_response("BadRequest"),
    "404": ref_response("NotFound"),
    "429": ref_response("RateLimited"),
    "502": ref_response("Upstream"),
  };
}
