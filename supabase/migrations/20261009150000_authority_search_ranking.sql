-- Authority search for a directory with ~19,000 US agencies (NCES import):
-- returns city and student count, also finds by city, and ranks real districts and districts with calendars first.

DROP FUNCTION IF EXISTS public.search_authorities(text, text, text, integer);

CREATE FUNCTION public.search_authorities(p_country text DEFAULT NULL, p_q text DEFAULT NULL, p_subdivision text DEFAULT NULL, p_limit integer DEFAULT 25)
 RETURNS TABLE(id uuid, country_code text, subdivision_code text, kind text, name text, city text, student_count integer,
               external_ids jsonb, school_years text[], calendars_confirmed integer, calendars_pending integer)
 LANGUAGE sql
 STABLE
 SET search_path TO public, extensions
AS $function$
  with hits as (
    select a.*
      from public.education_authorities a
     where a.is_active
       and (p_country is null or a.country_code = upper(p_country))
       and (p_subdivision is null or a.subdivision_code = upper(p_subdivision))
       and (p_q is null
            or a.name ilike '%' || p_q || '%'
            or a.name % p_q
            or a.city ilike p_q || '%'
            or a.external_ids ->> 'nces_leaid' = p_q
            or a.external_ids ->> 'nces_name' ilike '%' || p_q || '%')
  )
  select h.id, h.country_code::text, h.subdivision_code, h.kind, h.name, h.city, h.student_count, h.external_ids,
         coalesce(array_agg(distinct c.school_year order by c.school_year) filter (where c.status in ('confirmed','pending')), '{}'),
         count(distinct c.id) filter (where c.status = 'confirmed')::int,
         count(distinct c.id) filter (where c.status = 'pending')::int
    from hits h
    left join public.school_calendars c on c.authority_id = h.id
   group by h.id, h.country_code, h.subdivision_code, h.kind, h.name, h.city, h.student_count, h.external_ids
   order by (p_q is not null and h.external_ids ->> 'nces_leaid' = p_q) desc,
            (p_q is not null and h.name ilike p_q || '%') desc,
            case when p_q is null then 0 else round(similarity(h.name, p_q)::numeric, 1) end desc,
            (count(c.id) filter (where c.status = 'confirmed') > 0) desc,
            (h.kind = 'school_district') desc,
            h.student_count desc nulls last,
            h.name
   limit least(greatest(coalesce(p_limit, 25), 1), 100)
$function$;

grant execute on function public.search_authorities(text, text, text, integer) to anon, authenticated;
