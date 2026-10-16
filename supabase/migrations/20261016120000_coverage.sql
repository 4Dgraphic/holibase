-- Live coverage figures for the website and /v1/coverage. Cached at the edge for a day.
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
     where c.status in ('confirmed', 'pending')),
  per_country as (
    select cal.country_code,
           count(distinct coalesce(cal.authority_id::text, cal.subdivision_code, '-')) scopes,
           count(distinct coalesce(cal.authority_id::text, cal.subdivision_code, '-')) filter (where cal.status = 'confirmed') scopes_verified,
           count(distinct cal.authority_id) authorities,
           min(cal.school_year) filter (where cal.status = 'confirmed') first_year,
           max(cal.school_year) filter (where cal.status = 'confirmed') last_year,
           array_agg(distinct cal.origin order by cal.origin) origins
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
              'first_school_year', p.first_year, 'last_school_year', p.last_year, 'origins', to_jsonb(p.origins))
              order by p.scopes_verified desc, p.country_code), '[]'::jsonb)
            from per_country p left join public.countries co on co.code = p.country_code)),
    'us_districts', (select jsonb_build_object('directory', districts, 'verified', districts_verified,
                                               'students', students, 'students_verified', students_verified) from us),
    'generated_at', now())
$function$;

grant execute on function public.get_coverage() to anon, authenticated;
