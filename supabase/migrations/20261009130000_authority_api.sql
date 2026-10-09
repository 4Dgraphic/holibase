-- Public read functions for school authorities (districts, councils, zones) and calendar metadata.

CREATE OR REPLACE FUNCTION public.search_authorities(p_country text DEFAULT NULL, p_q text DEFAULT NULL, p_subdivision text DEFAULT NULL, p_limit integer DEFAULT 25)
 RETURNS TABLE(id uuid, country_code text, subdivision_code text, kind text, name text, external_ids jsonb, school_years text[], calendars_confirmed integer, calendars_pending integer)
 LANGUAGE sql
 STABLE
 SET search_path TO public, extensions
AS $function$
  select a.id, a.country_code::text, a.subdivision_code, a.kind, a.name, a.external_ids,
         coalesce(array_agg(distinct c.school_year order by c.school_year) filter (where c.status in ('confirmed','pending')), '{}'),
         count(distinct c.id) filter (where c.status = 'confirmed')::int,
         count(distinct c.id) filter (where c.status = 'pending')::int
    from public.education_authorities a
    left join public.school_calendars c on c.authority_id = a.id
   where a.is_active
     and (p_country is null or a.country_code = upper(p_country))
     and (p_subdivision is null or a.subdivision_code = upper(p_subdivision))
     and (p_q is null or a.name ilike '%' || p_q || '%' or a.name % p_q
          or a.external_ids ->> 'nces_leaid' = p_q or a.external_ids ->> 'nces_leaid_claimed' = p_q)
   group by a.id
   order by (p_q is not null and a.name ilike p_q || '%') desc,
            case when p_q is null then 0 else similarity(a.name, p_q) end desc,
            a.name
   limit least(greatest(coalesce(p_limit, 25), 1), 100)
$function$;

CREATE OR REPLACE FUNCTION public.get_school_calendars(p_country text, p_from date, p_to date, p_subdivision text DEFAULT NULL::text, p_authority uuid DEFAULT NULL::uuid, p_include_pending boolean DEFAULT false)
 RETURNS TABLE(calendar_id uuid, school_year text, origin text, status text, first_day date, last_day date, title text, source_url text, source_retrieved_at timestamptz, notes text)
 LANGUAGE sql
 STABLE
 SET search_path TO ''
AS $function$
  select c.id, c.school_year, c.origin, c.status, c.first_day, c.last_day, c.title, c.source_url, c.source_retrieved_at, c.notes
    from public.school_calendars c
   where c.country_code = upper(p_country)
     and (p_authority is null or c.authority_id = p_authority)
     and (p_authority is not null or (c.subdivision_code is not distinct from upper(p_subdivision) and c.authority_id is null))
     and (c.status = 'confirmed' or (p_include_pending and c.status = 'pending'))
     and (exists (select 1 from public.school_calendar_periods p where p.calendar_id = c.id and p.end_date >= p_from and p.start_date <= p_to)
          or c.first_day between p_from and p_to or c.last_day between p_from and p_to)
     and not (c.origin = 'library' and exists (
           select 1 from public.school_calendars o
            where o.origin <> 'library' and o.status = 'confirmed'
              and o.country_code = c.country_code
              and o.subdivision_code is not distinct from c.subdivision_code
              and o.authority_id is not distinct from c.authority_id
              and o.school_year = c.school_year))
   order by c.school_year
$function$;

grant execute on function public.search_authorities(text, text, text, integer) to anon, authenticated;
grant execute on function public.get_school_calendars(text, date, date, text, uuid, boolean) to anon, authenticated;
