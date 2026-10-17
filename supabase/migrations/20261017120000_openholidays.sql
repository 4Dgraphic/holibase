-- OpenHolidays API data (openholidaysapi.org, ODbL 1.0) as an additional school holiday source.
--
-- Licence: OpenHolidays data is share-alike (ODbL). It is kept as its own, identifiable layer:
-- every calendar carries source_id 'openholidays', and the API returns the licence per calendar.
-- Everything else stays CC BY 4.0 (or the licence of its own source).
--
-- Precedence: for one scope and school year the API returns only the best calendar:
--   official > editorial > community > library, and within the same origin the source with the
--   lower priority number (python-holidays 10 before openholidays 20).

alter table public.sources add column if not exists priority integer not null default 50;
update public.sources set priority = 10 where id = 'python-holidays';

insert into public.sources (id, name, url, license, share_alike, attribution, notes, priority)
values ('openholidays', 'OpenHolidays API', 'https://www.openholidaysapi.org', 'ODbL-1.0', true,
        'School holidays from OpenHolidays API (openholidaysapi.org), ODbL 1.0',
        'Imported weekly from github.com/openpotato/openholidaysapi.data. Share-alike: calendars from this source stay under ODbL.',
        20)
on conflict (id) do update set name = excluded.name, url = excluded.url, license = excluded.license,
  share_alike = excluded.share_alike, attribution = excluded.attribution, notes = excluded.notes, priority = excluded.priority;

-- Lower is better.
CREATE OR REPLACE FUNCTION public.calendar_rank(p_origin text, p_source_id text)
 RETURNS integer
 LANGUAGE sql
 STABLE
 SET search_path TO ''
AS $function$
  select (case p_origin when 'official' then 1 when 'editorial' then 2 when 'community' then 3 else 4 end) * 1000
         + coalesce((select s.priority from public.sources s where s.id = p_source_id), 50)
$function$;

-- True when no confirmed calendar of a better rank exists for the same scope and school year.
CREATE OR REPLACE FUNCTION public.calendar_visible(p_id uuid)
 RETURNS boolean
 LANGUAGE sql
 STABLE
 SET search_path TO ''
AS $function$
  select not exists (
    select 1
      from public.school_calendars c
      join public.school_calendars o
        on o.id <> c.id and o.status = 'confirmed'
       and o.country_code = c.country_code
       and o.subdivision_code is not distinct from c.subdivision_code
       and o.authority_id is not distinct from c.authority_id
       and o.school_year = c.school_year
     where c.id = p_id
       and public.calendar_rank(o.origin, o.source_id) < public.calendar_rank(c.origin, c.source_id))
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
     and (p_authority is not null or (c.subdivision_code is not distinct from upper(p_subdivision) and c.authority_id is null))
     and (c.status = 'confirmed' or (p_include_pending and c.status = 'pending'))
     and p.end_date >= p_from and p.start_date <= p_to
     and public.calendar_visible(c.id)
   order by p.start_date, p.end_date
$function$;

DROP FUNCTION IF EXISTS public.get_school_calendars(text, date, date, text, uuid, boolean);
CREATE FUNCTION public.get_school_calendars(p_country text, p_from date, p_to date, p_subdivision text DEFAULT NULL::text, p_authority uuid DEFAULT NULL::uuid, p_include_pending boolean DEFAULT false)
 RETURNS TABLE(calendar_id uuid, school_year text, origin text, status text, first_day date, last_day date, title text, source_url text, source_retrieved_at timestamptz, notes text, source_id text, license text)
 LANGUAGE sql
 STABLE
 SET search_path TO ''
AS $function$
  select c.id, c.school_year, c.origin, c.status, c.first_day, c.last_day, c.title, c.source_url, c.source_retrieved_at, c.notes,
         c.source_id, s.license
    from public.school_calendars c
    left join public.sources s on s.id = c.source_id
   where c.country_code = upper(p_country)
     and (p_authority is null or c.authority_id = p_authority)
     and (p_authority is not null or (c.subdivision_code is not distinct from upper(p_subdivision) and c.authority_id is null))
     and (c.status = 'confirmed' or (p_include_pending and c.status = 'pending'))
     and (exists (select 1 from public.school_calendar_periods p where p.calendar_id = c.id and p.end_date >= p_from and p.start_date <= p_to)
          or c.first_day between p_from and p_to or c.last_day between p_from and p_to)
     and public.calendar_visible(c.id)
   order by c.school_year
$function$;
grant execute on function public.get_school_calendars(text, date, date, text, uuid, boolean) to anon, authenticated;

-- Coverage: count only the calendars the API actually returns, and list the sources per country.
CREATE OR REPLACE FUNCTION public.get_coverage()
 RETURNS jsonb
 LANGUAGE sql
 STABLE
 SET search_path TO ''
AS $function$
  with ph as (
    select count(distinct country_code) countries,
           count(distinct subdivision_code) subdivisions,
           min(date) first_date, max(date) last_date
      from public.public_holidays),
  cal as (
    select c.*, a.student_count
      from public.school_calendars c
      left join public.education_authorities a on a.id = c.authority_id
     where c.status in ('confirmed', 'pending') and public.calendar_visible(c.id)),
  per_country as (
    select cal.country_code,
           count(distinct coalesce(cal.authority_id::text, cal.subdivision_code, '-')) scopes,
           count(distinct coalesce(cal.authority_id::text, cal.subdivision_code, '-')) filter (where cal.status = 'confirmed') scopes_verified,
           count(distinct cal.authority_id) authorities,
           min(cal.school_year) filter (where cal.status = 'confirmed') first_year,
           max(cal.school_year) filter (where cal.status = 'confirmed') last_year,
           array_agg(distinct cal.origin order by cal.origin) origins,
           array_agg(distinct cal.source_id order by cal.source_id) sources
      from cal group by cal.country_code),
  us as (
    select count(*) districts,
           sum(student_count) students,
           sum(student_count) filter (where exists (
               select 1 from public.school_calendars c where c.authority_id = a.id and c.status = 'confirmed')) students_verified,
           count(*) filter (where exists (
               select 1 from public.school_calendars c where c.authority_id = a.id and c.status = 'confirmed')) districts_verified
      from public.education_authorities a
     where a.country_code = 'US' and a.is_active)
  select jsonb_build_object(
    'public_holidays', (select jsonb_build_object('countries', countries, 'subdivisions', subdivisions,
                                                  'first_date', first_date, 'last_date', last_date) from ph),
    'school_holidays', jsonb_build_object(
        'countries', (select count(*) from per_country),
        'calendars', (select count(*) from cal where status = 'confirmed'),
        'by_country', (select coalesce(jsonb_agg(jsonb_build_object(
              'country_code', p.country_code, 'name', co.names ->> 'en', 'scopes', p.scopes,
              'scopes_verified', p.scopes_verified, 'authorities', p.authorities,
              'first_school_year', p.first_year, 'last_school_year', p.last_year, 'origins', to_jsonb(p.origins),
              'sources', to_jsonb(p.sources))
              order by p.scopes_verified desc, p.country_code), '[]'::jsonb)
            from per_country p left join public.countries co on co.code = p.country_code)),
    'us_districts', (select jsonb_build_object('directory', districts, 'verified', districts_verified,
                                               'students', students, 'students_verified', students_verified) from us),
    'generated_at', now())
$function$;

grant execute on function public.calendar_rank(text, text) to anon, authenticated;
grant execute on function public.calendar_visible(uuid) to anon, authenticated;
