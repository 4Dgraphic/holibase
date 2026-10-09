-- First / last day of instruction belong to the calendar, not to its free periods.
alter table public.school_calendars
  add column if not exists first_day date,
  add column if not exists last_day date,
  add column if not exists notes text;

-- Editorial / official / community calendars take precedence over library calendars
-- (python-holidays) for the same scope and school year, so the API never returns both.
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
     and not (c.origin = 'library' and exists (
           select 1 from public.school_calendars o
            where o.origin <> 'library' and o.status = 'confirmed'
              and o.country_code = c.country_code
              and o.subdivision_code is not distinct from c.subdivision_code
              and o.authority_id is not distinct from c.authority_id
              and o.school_year = c.school_year))
   order by p.start_date, p.end_date
$function$;
