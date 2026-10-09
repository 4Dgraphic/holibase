-- Holibase's own data is published under CC BY 4.0.
update public.sources
   set license = 'CC-BY-4.0',
       share_alike = false,
       url = 'https://holibase.org',
       attribution = 'Holibase (holibase.org), CC BY 4.0'
 where id in ('editorial', 'community');

update public.sources
   set license = 'LicenseRef-US-Gov-Public-Domain',
       notes = 'U.S. federal government work, public domain (17 U.S.C. 105)'
 where id = 'nces-ccd';
