-- Data sources (required before any data load; rows reference sources.id)
insert into public.sources (id, name, url, license, share_alike, attribution, notes) values
  ('python-holidays', 'python-holidays (vacanza/holidays)', 'https://github.com/vacanza/holidays', 'MIT', false,
   'Holiday data © python-holidays contributors (MIT)', null),
  ('openholidays-api', 'OpenHolidays API', 'https://www.openholidaysapi.org', 'ODbL-1.0', true,
   'Contains data from OpenHolidays API (ODbL-1.0)', 'Share-Alike: öffentlich angebotene abgeleitete Datenbank muss ebenfalls ODbL sein'),
  ('nces-ccd', 'NCES Common Core of Data (LEA Directory)', 'https://nces.ed.gov/ccd/', 'LicenseRef-US-Gov-Public-Domain', false,
   'Source: U.S. Department of Education, NCES, Common Core of Data', 'U.S. federal government work, public domain (17 U.S.C. 105)'),
  ('community', 'Community-Einreichungen', 'https://holibase.org', 'CC-BY-4.0', false,
   'Holibase (holibase.org), CC BY 4.0', 'Einreichungen werden unter CC BY 4.0 veröffentlicht'),
  ('editorial', 'Redaktionell gepflegt', 'https://holibase.org', 'CC-BY-4.0', false,
   'Holibase (holibase.org), CC BY 4.0', 'Manuell recherchiert, z. B. Vorbefüllung Top-50-US-Bezirke')
on conflict (id) do nothing;
