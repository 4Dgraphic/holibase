-- Holibase schema (Postgres 15+ / Supabase)
-- Reconstructed 2026-10-09 from the live project "Holibase" so that the repository matches production.

create extension if not exists pg_trgm;

-- ------------------------------------------------------------------ helper functions used by defaults

CREATE OR REPLACE FUNCTION public.url_domain(p_url text)
 RETURNS text
 LANGUAGE sql
 IMMUTABLE PARALLEL SAFE
 SET search_path TO ''
AS $function$
  select lower(substring(p_url from '^(?:[a-z]+://)?(?:www\.)?([^/:?#]+)'))
$function$;

CREATE OR REPLACE FUNCTION public.touch_updated_at()
 RETURNS trigger
 LANGUAGE plpgsql
 SET search_path TO ''
AS $function$
begin
  new.updated_at := now();
  return new;
end $function$;

-- ------------------------------------------------------------------ reference data

create table public.sources (
  id text not null,
  name text not null,
  url text,
  license text not null,
  share_alike boolean default false not null,
  attribution text,
  notes text,
  created_at timestamp with time zone default now() not null,
  constraint sources_pkey PRIMARY KEY (id)
);

create table public.countries (
  code character(2) not null,
  alpha3 character(3),
  names jsonb default '{}'::jsonb not null,
  default_language text default 'en'::text not null,
  languages text[] default '{}'::text[] not null,
  holiday_categories text[] default '{}'::text[] not null,
  school_holiday_level text,
  updated_at timestamp with time zone default now() not null,
  constraint countries_pkey PRIMARY KEY (code),
  constraint countries_code_check CHECK ((code ~ '^[A-Z]{2}$'::text)),
  constraint countries_school_holiday_level_check CHECK ((school_holiday_level = ANY (ARRAY['national'::text, 'zone'::text, 'subdivision'::text, 'authority'::text, 'school'::text])))
);

create table public.subdivisions (
  code text not null,
  country_code character(2) not null,
  parent_code text,
  source_code text,
  name text not null,
  names jsonb default '{}'::jsonb not null,
  kind text,
  iso_verified boolean default false not null,
  updated_at timestamp with time zone default now() not null,
  constraint subdivisions_pkey PRIMARY KEY (code),
  constraint subdivisions_code_check CHECK ((code ~ '^[A-Z]{2}-[A-Z0-9-]+$'::text))
);

create table public.education_authorities (
  id uuid default gen_random_uuid() not null,
  country_code character(2) not null,
  subdivision_code text,
  kind text not null,
  name text not null,
  external_ids jsonb default '{}'::jsonb not null,
  website_url text,
  website_domain text generated always as (public.url_domain(website_url)) stored,
  city text,
  student_count integer,
  is_active boolean default true not null,
  source_id text,
  updated_at timestamp with time zone default now() not null,
  constraint education_authorities_pkey PRIMARY KEY (id),
  constraint education_authorities_kind_check CHECK ((kind = ANY (ARRAY['school_district'::text, 'local_authority'::text, 'school_board'::text, 'academy_trust'::text, 'other'::text])))
);

-- ------------------------------------------------------------------ public holidays

create table public.public_holidays (
  id bigint generated always as identity not null,
  country_code character(2) not null,
  subdivision_code text,
  date date not null,
  category text default 'public'::text not null,
  scope text default 'national'::text not null,
  local_name text not null,
  default_language text not null,
  names jsonb default '{}'::jsonb not null,
  is_observed boolean default false not null,
  is_estimated boolean default false not null,
  source_id text not null,
  source_version text,
  updated_at timestamp with time zone default now() not null,
  constraint public_holidays_natural_key UNIQUE NULLS NOT DISTINCT (country_code, subdivision_code, date, category, local_name, source_id),
  constraint public_holidays_pkey PRIMARY KEY (id),
  constraint public_holidays_scope_check CHECK ((scope = ANY (ARRAY['national'::text, 'regional'::text])))
);

-- ------------------------------------------------------------------ school holidays

create table public.school_calendars (
  id uuid default gen_random_uuid() not null,
  country_code character(2) not null,
  subdivision_code text,
  authority_id uuid,
  school_year text not null,
  title text,
  origin text not null,
  status text default 'pending'::text not null,
  source_id text not null,
  source_version text,
  source_url text,
  source_domain text generated always as (public.url_domain(source_url)) stored,
  source_retrieved_at timestamp with time zone,
  confirmations integer default 0 not null,
  supersedes uuid,
  created_at timestamp with time zone default now() not null,
  updated_at timestamp with time zone default now() not null,
  constraint school_calendars_natural_key UNIQUE NULLS NOT DISTINCT (country_code, subdivision_code, authority_id, school_year, source_id, source_url),
  constraint school_calendars_pkey PRIMARY KEY (id),
  constraint school_calendars_origin_check CHECK ((origin = ANY (ARRAY['library'::text, 'official'::text, 'community'::text, 'editorial'::text]))),
  constraint school_calendars_school_year_check CHECK ((school_year ~ '^\d{4}(-\d{2})?$'::text)),
  constraint school_calendars_status_check CHECK ((status = ANY (ARRAY['pending'::text, 'confirmed'::text, 'outdated'::text, 'rejected'::text])))
);

create table public.school_calendar_periods (
  id bigint generated always as identity not null,
  calendar_id uuid not null,
  start_date date not null,
  end_date date not null,
  kind text default 'break'::text not null,
  label text,
  names jsonb default '{}'::jsonb not null,
  constraint school_calendar_periods_natural_key UNIQUE NULLS NOT DISTINCT (calendar_id, start_date, end_date, label),
  constraint school_calendar_periods_pkey PRIMARY KEY (id),
  constraint school_calendar_periods_dates CHECK ((end_date >= start_date)),
  constraint school_calendar_periods_kind_check CHECK ((kind = ANY (ARRAY['break'::text, 'holiday'::text, 'teacher_day'::text, 'early_release'::text, 'other'::text])))
);

-- ------------------------------------------------------------------ ingest

create table public.api_clients (
  id uuid default gen_random_uuid() not null,
  name text not null,
  contact_email text,
  key_hash text not null,
  tier text default 'free'::text not null,
  can_submit boolean default true not null,
  is_active boolean default true not null,
  created_at timestamp with time zone default now() not null,
  constraint api_clients_key_hash_key UNIQUE (key_hash),
  constraint api_clients_pkey PRIMARY KEY (id),
  constraint api_clients_tier_check CHECK ((tier = ANY (ARRAY['free'::text, 'partner'::text, 'internal'::text])))
);

create table public.submissions (
  id uuid default gen_random_uuid() not null,
  client_id uuid,
  external_ref text,
  country_code character(2) not null,
  subdivision_code text,
  authority_id uuid,
  authority_name text,
  school_year text,
  source_type text not null,
  source_url text,
  source_domain text generated always as (public.url_domain(source_url)) stored,
  source_check text,
  storage_path text,
  status text default 'received'::text not null,
  rejection_reason text,
  extracted jsonb,
  calendar_id uuid,
  created_at timestamp with time zone default now() not null,
  processed_at timestamp with time zone,
  constraint submissions_client_ref UNIQUE (client_id, external_ref),
  constraint submissions_pkey PRIMARY KEY (id),
  constraint submissions_has_source CHECK (((source_url IS NOT NULL) OR (storage_path IS NOT NULL) OR (source_type = 'manual'::text))),
  constraint submissions_school_year_check CHECK ((school_year ~ '^\d{4}(-\d{2})?$'::text)),
  constraint submissions_source_type_check CHECK ((source_type = ANY (ARRAY['ics_url'::text, 'ics_file'::text, 'pdf_url'::text, 'pdf_file'::text, 'web_url'::text, 'manual'::text]))),
  constraint submissions_status_check CHECK ((status = ANY (ARRAY['received'::text, 'processing'::text, 'needs_review'::text, 'accepted'::text, 'rejected'::text, 'duplicate'::text, 'failed'::text])))
);

create table public.calendar_confirmations (
  calendar_id uuid not null,
  client_id uuid,
  confirmer_hash text not null,
  created_at timestamp with time zone default now() not null,
  constraint calendar_confirmations_pkey PRIMARY KEY (calendar_id, confirmer_hash)
);

create table public.calendar_reports (
  id bigint generated always as identity not null,
  calendar_id uuid not null,
  client_id uuid,
  reporter_hash text,
  reason text not null,
  details text,
  resolved_at timestamp with time zone,
  created_at timestamp with time zone default now() not null,
  constraint calendar_reports_pkey PRIMARY KEY (id),
  constraint calendar_reports_reason_check CHECK ((reason = ANY (ARRAY['wrong_dates'::text, 'outdated'::text, 'private_data'::text, 'wrong_district'::text, 'duplicate'::text, 'other'::text])))
);

create table public.coverage_requests (
  id bigint generated always as identity not null,
  country_code character(2) not null,
  subdivision_code text,
  authority_id uuid,
  authority_name text,
  school_year text,
  client_id uuid,
  requester_hash text,
  created_at timestamp with time zone default now() not null,
  constraint coverage_requests_pkey PRIMARY KEY (id)
);

-- ------------------------------------------------------------------ foreign keys

alter table public.calendar_confirmations add constraint calendar_confirmations_calendar_id_fkey FOREIGN KEY (calendar_id) REFERENCES public.school_calendars(id) ON DELETE CASCADE;
alter table public.calendar_confirmations add constraint calendar_confirmations_client_id_fkey FOREIGN KEY (client_id) REFERENCES public.api_clients(id);
alter table public.calendar_reports add constraint calendar_reports_calendar_id_fkey FOREIGN KEY (calendar_id) REFERENCES public.school_calendars(id) ON DELETE CASCADE;
alter table public.calendar_reports add constraint calendar_reports_client_id_fkey FOREIGN KEY (client_id) REFERENCES public.api_clients(id);
alter table public.coverage_requests add constraint coverage_requests_authority_id_fkey FOREIGN KEY (authority_id) REFERENCES public.education_authorities(id);
alter table public.coverage_requests add constraint coverage_requests_client_id_fkey FOREIGN KEY (client_id) REFERENCES public.api_clients(id);
alter table public.coverage_requests add constraint coverage_requests_country_code_fkey FOREIGN KEY (country_code) REFERENCES public.countries(code);
alter table public.coverage_requests add constraint coverage_requests_subdivision_code_fkey FOREIGN KEY (subdivision_code) REFERENCES public.subdivisions(code);
alter table public.education_authorities add constraint education_authorities_country_code_fkey FOREIGN KEY (country_code) REFERENCES public.countries(code);
alter table public.education_authorities add constraint education_authorities_source_id_fkey FOREIGN KEY (source_id) REFERENCES public.sources(id);
alter table public.education_authorities add constraint education_authorities_subdivision_code_fkey FOREIGN KEY (subdivision_code) REFERENCES public.subdivisions(code);
alter table public.public_holidays add constraint public_holidays_country_code_fkey FOREIGN KEY (country_code) REFERENCES public.countries(code);
alter table public.public_holidays add constraint public_holidays_source_id_fkey FOREIGN KEY (source_id) REFERENCES public.sources(id);
alter table public.public_holidays add constraint public_holidays_subdivision_code_fkey FOREIGN KEY (subdivision_code) REFERENCES public.subdivisions(code);
alter table public.school_calendar_periods add constraint school_calendar_periods_calendar_id_fkey FOREIGN KEY (calendar_id) REFERENCES public.school_calendars(id) ON DELETE CASCADE;
alter table public.school_calendars add constraint school_calendars_authority_id_fkey FOREIGN KEY (authority_id) REFERENCES public.education_authorities(id);
alter table public.school_calendars add constraint school_calendars_country_code_fkey FOREIGN KEY (country_code) REFERENCES public.countries(code);
alter table public.school_calendars add constraint school_calendars_source_id_fkey FOREIGN KEY (source_id) REFERENCES public.sources(id);
alter table public.school_calendars add constraint school_calendars_subdivision_code_fkey FOREIGN KEY (subdivision_code) REFERENCES public.subdivisions(code);
alter table public.school_calendars add constraint school_calendars_supersedes_fkey FOREIGN KEY (supersedes) REFERENCES public.school_calendars(id);
alter table public.subdivisions add constraint subdivisions_country_code_fkey FOREIGN KEY (country_code) REFERENCES public.countries(code) ON UPDATE CASCADE;
alter table public.subdivisions add constraint subdivisions_parent_code_fkey FOREIGN KEY (parent_code) REFERENCES public.subdivisions(code);
alter table public.submissions add constraint submissions_authority_id_fkey FOREIGN KEY (authority_id) REFERENCES public.education_authorities(id);
alter table public.submissions add constraint submissions_calendar_id_fkey FOREIGN KEY (calendar_id) REFERENCES public.school_calendars(id);
alter table public.submissions add constraint submissions_client_id_fkey FOREIGN KEY (client_id) REFERENCES public.api_clients(id);
alter table public.submissions add constraint submissions_country_code_fkey FOREIGN KEY (country_code) REFERENCES public.countries(code);
alter table public.submissions add constraint submissions_subdivision_code_fkey FOREIGN KEY (subdivision_code) REFERENCES public.subdivisions(code);

-- ------------------------------------------------------------------ indexes

CREATE INDEX calendar_confirmations_client_idx ON public.calendar_confirmations USING btree (client_id);
CREATE INDEX calendar_reports_calendar_idx ON public.calendar_reports USING btree (calendar_id);
CREATE INDEX calendar_reports_client_idx ON public.calendar_reports USING btree (client_id);
CREATE INDEX coverage_requests_authority_idx ON public.coverage_requests USING btree (authority_id);
CREATE INDEX coverage_requests_client_idx ON public.coverage_requests USING btree (client_id);
CREATE INDEX coverage_requests_subdivision_idx ON public.coverage_requests USING btree (subdivision_code);
CREATE INDEX coverage_requests_target_idx ON public.coverage_requests USING btree (country_code, subdivision_code, authority_id);
CREATE INDEX education_authorities_domain_idx ON public.education_authorities USING btree (website_domain);
CREATE INDEX education_authorities_name_trgm ON public.education_authorities USING gin (name gin_trgm_ops);
CREATE UNIQUE INDEX education_authorities_nces_uidx ON public.education_authorities USING btree (((external_ids ->> 'nces_leaid'::text))) WHERE (external_ids ? 'nces_leaid'::text);
CREATE INDEX education_authorities_region_idx ON public.education_authorities USING btree (country_code, subdivision_code);
CREATE INDEX education_authorities_source_idx ON public.education_authorities USING btree (source_id);
CREATE INDEX education_authorities_subdiv_idx ON public.education_authorities USING btree (subdivision_code);
CREATE INDEX public_holidays_date_idx ON public.public_holidays USING btree (date);
CREATE INDEX public_holidays_lookup_idx ON public.public_holidays USING btree (country_code, subdivision_code, date);
CREATE INDEX school_calendar_periods_calendar_idx ON public.school_calendar_periods USING btree (calendar_id, start_date);
CREATE INDEX school_calendars_authority_idx ON public.school_calendars USING btree (authority_id, school_year);
CREATE INDEX school_calendars_scope_idx ON public.school_calendars USING btree (country_code, subdivision_code, school_year);
CREATE INDEX school_calendars_source_idx ON public.school_calendars USING btree (source_id);
CREATE INDEX school_calendars_subdivision_idx ON public.school_calendars USING btree (subdivision_code);
CREATE INDEX school_calendars_supersedes_idx ON public.school_calendars USING btree (supersedes);
CREATE INDEX subdivisions_country_idx ON public.subdivisions USING btree (country_code);
CREATE INDEX subdivisions_parent_idx ON public.subdivisions USING btree (parent_code);
CREATE INDEX submissions_authority_idx ON public.submissions USING btree (authority_id);
CREATE INDEX submissions_calendar_idx ON public.submissions USING btree (calendar_id);
CREATE INDEX submissions_country_idx ON public.submissions USING btree (country_code);
CREATE INDEX submissions_queue_idx ON public.submissions USING btree (status, created_at);
CREATE INDEX submissions_subdivision_idx ON public.submissions USING btree (subdivision_code);

-- ------------------------------------------------------------------ functions

CREATE OR REPLACE FUNCTION public.pick_name(p_names jsonb, p_lang text, p_fallback text)
 RETURNS text
 LANGUAGE sql
 IMMUTABLE PARALLEL SAFE
 SET search_path TO ''
AS $function$
  select coalesce(
    p_names ->> p_lang,
    (select value from jsonb_each_text(p_names)
      where split_part(key, '-', 1) = split_part(p_lang, '-', 1) order by key limit 1),
    p_names ->> 'en',
    (select value from jsonb_each_text(p_names) where key like 'en-%' order by key limit 1),
    p_fallback)
$function$;

CREATE OR REPLACE FUNCTION public.get_public_holidays(p_country text, p_from date, p_to date, p_subdivision text DEFAULT NULL::text, p_lang text DEFAULT 'en'::text, p_categories text[] DEFAULT ARRAY['public'::text])
 RETURNS TABLE(date date, name text, local_name text, category text, scope text, is_observed boolean, is_estimated boolean, subdivision_code text, source_id text)
 LANGUAGE sql
 STABLE
 SET search_path TO ''
AS $function$
  with region as (
    select case when p_subdivision is not null and exists (
             select 1 from public.public_holidays h
              where h.country_code = upper(p_country) and h.subdivision_code = upper(p_subdivision))
           then upper(p_subdivision) end as code
  )
  select h.date, public.pick_name(h.names, p_lang, h.local_name), h.local_name, h.category, h.scope,
         h.is_observed, h.is_estimated, h.subdivision_code, h.source_id
    from public.public_holidays h, region r
   where h.country_code = upper(p_country)
     and h.subdivision_code is not distinct from r.code
     and h.date between p_from and p_to
     and h.category = any (p_categories)
   order by h.date, h.local_name
$function$;

CREATE OR REPLACE FUNCTION public.get_school_holidays(p_country text, p_from date, p_to date, p_subdivision text DEFAULT NULL::text, p_authority uuid DEFAULT NULL::uuid, p_lang text DEFAULT 'en'::text, p_include_pending boolean DEFAULT false)
 RETURNS TABLE(start_date date, end_date date, name text, kind text, school_year text, calendar_id uuid, origin text, status text, confirmations integer, source_url text)
 LANGUAGE sql
 STABLE
 SET search_path TO ''
AS $function$
  select p.start_date, p.end_date, public.pick_name(p.names, p_lang, p.label), p.kind, c.school_year,
         c.id, c.origin, c.status, c.confirmations, c.source_url
    from public.school_calendars c
    join public.school_calendar_periods p on p.calendar_id = c.id
   where c.country_code = upper(p_country)
     and (p_authority is null or c.authority_id = p_authority)
     and (p_authority is not null or c.subdivision_code is not distinct from upper(p_subdivision))
     and (c.status = 'confirmed' or (p_include_pending and c.status = 'pending'))
     and p.end_date >= p_from and p.start_date <= p_to
   order by p.start_date
$function$;

CREATE OR REPLACE FUNCTION public.check_source_url(p_url text, p_authority uuid DEFAULT NULL::uuid)
 RETURNS text
 LANGUAGE sql
 STABLE
 SET search_path TO ''
AS $function$
  select case
    when p_url is null then 'unknown'
    when p_url ~* 'calendar\.google\.com/calendar/ical/[^/]+/private-' then 'private'
    when p_url ~* '(caldav|calendar)\.icloud\.com' then 'private'
    when p_url ~* 'outlook\.(live|office|office365)\.com/owa/calendar/' then 'private'
    when p_authority is not null and exists (
      select 1 from public.education_authorities a
       where a.id = p_authority and a.website_domain is not null
         and (public.url_domain(p_url) = a.website_domain
              or public.url_domain(p_url) like '%.' || a.website_domain)) then 'authority_domain'
    when p_url ~* 'calendar\.google\.com/calendar/ical/[^/]+/public/' then 'public_calendar'
    else 'unknown'
  end
$function$;

CREATE OR REPLACE FUNCTION public.confirmation_threshold()
 RETURNS integer
 LANGUAGE sql
 IMMUTABLE
 SET search_path TO ''
AS $function$ select 3 $function$;

CREATE OR REPLACE FUNCTION public.on_confirmation_change()
 RETURNS trigger
 LANGUAGE plpgsql
 SET search_path TO ''
AS $function$
declare v_id uuid := coalesce(new.calendar_id, old.calendar_id);
begin
  update public.school_calendars c
     set confirmations = (select count(*) from public.calendar_confirmations where calendar_id = v_id),
         status = case
                    when c.status = 'pending'
                     and (select count(*) from public.calendar_confirmations where calendar_id = v_id)
                         >= public.confirmation_threshold()
                    then 'confirmed' else c.status end
   where c.id = v_id;
  return null;
end $function$;

revoke execute on function public.on_confirmation_change() from public, anon, authenticated;

-- ------------------------------------------------------------------ triggers

CREATE TRIGGER calendar_confirmations_count AFTER INSERT OR DELETE ON public.calendar_confirmations FOR EACH ROW EXECUTE FUNCTION public.on_confirmation_change();
CREATE TRIGGER countries_touch BEFORE UPDATE ON public.countries FOR EACH ROW EXECUTE FUNCTION public.touch_updated_at();
CREATE TRIGGER subdivisions_touch BEFORE UPDATE ON public.subdivisions FOR EACH ROW EXECUTE FUNCTION public.touch_updated_at();
CREATE TRIGGER education_authorities_touch BEFORE UPDATE ON public.education_authorities FOR EACH ROW EXECUTE FUNCTION public.touch_updated_at();
CREATE TRIGGER public_holidays_touch BEFORE UPDATE ON public.public_holidays FOR EACH ROW EXECUTE FUNCTION public.touch_updated_at();
CREATE TRIGGER school_calendars_touch BEFORE UPDATE ON public.school_calendars FOR EACH ROW EXECUTE FUNCTION public.touch_updated_at();

-- ------------------------------------------------------------------ row level security
-- Reference data, holidays and non-rejected calendars are public. Everything else is service-role only.

alter table public.api_clients enable row level security;
alter table public.calendar_confirmations enable row level security;
alter table public.calendar_reports enable row level security;
alter table public.countries enable row level security;
alter table public.coverage_requests enable row level security;
alter table public.education_authorities enable row level security;
alter table public.public_holidays enable row level security;
alter table public.school_calendar_periods enable row level security;
alter table public.school_calendars enable row level security;
alter table public.sources enable row level security;
alter table public.subdivisions enable row level security;
alter table public.submissions enable row level security;

create policy "public read" on public.countries as PERMISSIVE for SELECT to anon, authenticated using (true);
create policy "public read" on public.education_authorities as PERMISSIVE for SELECT to anon, authenticated using (true);
create policy "public read" on public.public_holidays as PERMISSIVE for SELECT to anon, authenticated using (true);
create policy "public read" on public.school_calendar_periods as PERMISSIVE for SELECT to anon, authenticated using ((EXISTS ( SELECT 1
   FROM public.school_calendars c
  WHERE ((c.id = school_calendar_periods.calendar_id) AND (c.status = ANY (ARRAY['confirmed'::text, 'pending'::text, 'outdated'::text]))))));
create policy "public read" on public.school_calendars as PERMISSIVE for SELECT to anon, authenticated using ((status = ANY (ARRAY['confirmed'::text, 'pending'::text, 'outdated'::text])));
create policy "public read" on public.sources as PERMISSIVE for SELECT to anon, authenticated using (true);
create policy "public read" on public.subdivisions as PERMISSIVE for SELECT to anon, authenticated using (true);
