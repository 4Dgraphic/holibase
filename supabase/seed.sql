-- Data sources (required before any data load; rows reference sources.id)
insert into public.sources (id, name, url, license, share_alike, attribution, notes) values
  ('python-holidays', 'python-holidays (vacanza/holidays)', 'https://github.com/vacanza/holidays', 'MIT', false,
   'Holiday data © python-holidays contributors (MIT)', null),
  ('openholidays-api', 'OpenHolidays API', 'https://www.openholidaysapi.org', 'ODbL-1.0', true,
   'Contains data from OpenHolidays API (ODbL-1.0)', 'Share-Alike: öffentlich angebotene abgeleitete Datenbank muss ebenfalls ODbL sein'),
  ('nces-ccd', 'NCES Common Core of Data (LEA Directory)', 'https://nces.ed.gov/ccd/', 'LicenseRef-US-Gov-Public', false,
   'Source: U.S. Department of Education, NCES, Common Core of Data', 'Nutzungsbedingungen (statistical purposes) vor Produktivnutzung prüfen'),
  ('community', 'Community-Einreichungen', null, 'LicenseRef-TBD', false, null,
   'Lizenz für eigene Daten noch festlegen (z. B. ODbL oder CC-BY-4.0)'),
  ('editorial', 'Redaktionell gepflegt', null, 'LicenseRef-TBD', false, null,
   'Manuell recherchiert, z. B. Vorbefüllung Top-50-US-Bezirke')
on conflict (id) do nothing;
