-- Submissions from the form on holibase.org (POST /v1/submissions).
--
-- The API calls submit_school_calendar() with the publishable key. The function checks every field and
-- stores the submission as 'received'; the table itself stays closed (RLS, no policies). A daily job
-- (scripts/process_submissions.py) checks each submission against its source document and turns it
-- into a community calendar, or marks it as duplicate, rejected or needing review.
-- No personal data is stored: no name, email or IP address.

create or replace function public.submit_school_calendar(p jsonb)
returns jsonb
language plpgsql
security definer
set search_path to ''
as $function$
declare
  v_country text := upper(nullif(trim(p->>'country'), ''));
  v_sub text := upper(nullif(trim(p->>'subdivision'), ''));
  v_auth uuid;
  v_auth_name text;
  v_year text := nullif(trim(p->>'school_year'), '');
  v_url text := nullif(trim(p->>'source_url'), '');
  v_note text := left(nullif(trim(p->>'note'), ''), 1000);
  v_first date;
  v_last date;
  v_periods jsonb := '[]'::jsonb;
  v_item jsonb;
  v_start date;
  v_end date;
  v_kind text;
  v_name text;
  v_id uuid;
begin
  if v_country is null or not exists (select 1 from public.countries c where c.code = v_country) then
    raise exception 'Unknown country.' using errcode = '22023';
  end if;
  if v_sub is not null and not exists (select 1 from public.subdivisions s where s.code = v_sub and s.country_code = v_country) then
    raise exception 'Unknown region for this country.' using errcode = '22023';
  end if;
  if nullif(p->>'authority', '') is not null then
    begin
      v_auth := (p->>'authority')::uuid;
    exception when others then
      raise exception 'Unknown school authority.' using errcode = '22023';
    end;
    select a.name, coalesce(v_sub, a.subdivision_code) into v_auth_name, v_sub
      from public.education_authorities a where a.id = v_auth and a.country_code = v_country;
    if v_auth_name is null then
      raise exception 'Unknown school authority.' using errcode = '22023';
    end if;
  end if;
  if v_year is null or v_year !~ '^\d{4}(-\d{2})?$' then
    raise exception 'School year must look like 2026-27.' using errcode = '22023';
  end if;
  if v_year ~ '-' and right(v_year, 2)::int <> (left(v_year, 4)::int + 1) % 100 then
    raise exception 'School year must look like 2026-27.' using errcode = '22023';
  end if;
  if v_url is null or v_url !~* '^https?://[^\s/$.?#][^\s]*$' or length(v_url) > 1000 then
    raise exception 'A link to the official calendar is required.' using errcode = '22023';
  end if;
  begin
    v_first := nullif(p->>'first_day', '')::date;
    v_last := nullif(p->>'last_day', '')::date;
  exception when others then
    raise exception 'First and last day must be dates.' using errcode = '22023';
  end;

  if jsonb_typeof(p->'periods') <> 'array' or jsonb_array_length(p->'periods') = 0 then
    raise exception 'Add at least one holiday.' using errcode = '22023';
  end if;
  if jsonb_array_length(p->'periods') > 40 then
    raise exception 'At most 40 holidays per school year.' using errcode = '22023';
  end if;
  for v_item in select * from jsonb_array_elements(p->'periods') loop
    begin
      v_start := (v_item->>'start_date')::date;
      v_end := coalesce(nullif(v_item->>'end_date', '')::date, v_start);
    exception when others then
      raise exception 'Every holiday needs a valid date.' using errcode = '22023';
    end;
    if v_start is null or v_end < v_start or v_end - v_start > 120 then
      raise exception 'Every holiday needs a start date and an end date after it.' using errcode = '22023';
    end if;
    v_kind := coalesce(nullif(v_item->>'kind', ''), case when v_end = v_start then 'holiday' else 'break' end);
    if v_kind not in ('break', 'holiday', 'teacher_day', 'other') then
      raise exception 'Unknown kind of holiday.' using errcode = '22023';
    end if;
    v_name := left(nullif(trim(v_item->>'name'), ''), 120);
    v_periods := v_periods || jsonb_build_object('start_date', v_start, 'end_date', v_end, 'kind', v_kind, 'name', v_name);
  end loop;

  -- flood protection for the whole service: a real day sees a handful of submissions
  if (select count(*) from public.submissions s where s.created_at > now() - interval '1 day') >= 500 then
    raise exception 'Too many submissions today. Please try again tomorrow.' using errcode = '53400';
  end if;

  insert into public.submissions (country_code, subdivision_code, authority_id, authority_name, school_year,
                                  source_type, source_url, status, extracted)
  values (v_country, v_sub, v_auth, v_auth_name, v_year,
          case when v_url ~* '\.pdf($|[?#])' then 'pdf_url' else 'web_url' end, v_url, 'received',
          jsonb_build_object('channel', 'web', 'periods', v_periods, 'first_day', v_first, 'last_day', v_last,
                             'note', v_note, 'lang', left(nullif(p->>'lang', ''), 5)))
  returning id into v_id;
  return jsonb_build_object('id', v_id, 'status', 'received');
end
$function$;

revoke all on function public.submit_school_calendar(jsonb) from public;
grant execute on function public.submit_school_calendar(jsonb) to anon, authenticated;
