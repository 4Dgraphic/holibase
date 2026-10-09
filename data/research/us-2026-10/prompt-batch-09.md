# Holibase research: US school district calendars, batch 09 of 10

You are researching official student calendars of US public school districts for Holibase, an open,
non-profit database of school holidays (data published under CC BY 4.0). Accuracy matters more than
completeness: a missing district is fine, a wrong date is not.

## Districts in this batch (50)

Each district is identified by its NCES LEAID. Use exactly these ids in your output.

| nces_leaid | district (NCES name) | city | state |
|---|---|---|---|
| 5303540 | Highline School District | Burien | WA |
| 3701140 | Davidson County Schools | Lexington | NC |
| 2931650 | Wentzville R-IV School District | Wentzville | MO |
| 0629580 | Palmdale Elementary School District | Palmdale | CA |
| 2929280 | St. Louis City School District | St Louis | MO |
| 3904611 | Lakota Local School District | Liberty Township | OH |
| 2918300 | Lee's Summit R-VII School District | Lee's Summit | MO |
| 0619260 | Jurupa Unified School District | Jurupa Valley | CA |
| 0628470 | Ontario-Montclair School District | Ontario | CA |
| 3704050 | Rowan-Salisbury Schools | Salisbury | NC |
| 0627240 | Newport-Mesa Unified School District | Costa Mesa | CA |
| 0601620 | ABC Unified School District | Cerritos | CA |
| 2201200 | Ouachita Parish School District | West Monroe | LA |
| 2802190 | Jackson Public School District | Jackson | MS |
| 0605580 | Santa Maria-Bonita Elementary School District | Santa Maria | CA |
| 0616740 | Hayward Unified School District | Hayward | CA |
| 2731800 | Rochester Public School District | Rochester | MN |
| 3704880 | Wayne County Public Schools | Goldsboro | NC |
| 4502820 | Lexington School District 5 | Irmo | SC |
| 2928950 | Francis Howell R-III School District | O'fallon | MO |
| 3404500 | Edison Township School District | Edison | NJ |
| 4815910 | Crowley Independent School District | Fort Worth | TX |
| 1200240 | Charlotte County School District | Port Charlotte | FL |
| 4108830 | North Clackamas School District 12 | Milwaukie | OR |
| 3904702 | Dublin City School District | Dublin | OH |
| 4205310 | Central Bucks School District | Doylestown | PA |
| 2400600 | St. Marys County Public Schools | Leonardtown | MD |
| 4101980 | Bend-La Pine Administrative School District 1 | Bend | OR |
| 2602820 | Ann Arbor Public Schools | Ann Arbor | MI |
| 4202280 | Allentown City School District | Allentown | PA |
| 5101830 | Hanover County Public Schools | Ashland | VA |
| 1730270 | Oswego Community Unit School District 308 | Oswego | IL |
| 2923580 | Parkway C-2 School District | Chesterfield | MO |
| 1805670 | Lawrence Township Metropolitan School District | Indianapolis | IN |
| 2908370 | Fort Zumwalt R-II School District | O'fallon | MO |
| 4220040 | Reading School District | Reading | PA |
| 1200930 | Indian River County School District | Vero Beach | FL |
| 0629490 | Pajaro Valley Joint Unified School District | Watsonville | CA |
| 5100120 | Alexandria City Public Schools | Alexandria | VA |
| 3500010 | Rio Rancho Public Schools | Rio Rancho | NM |
| 0102100 | Limestone County School District | Athens | AL |
| 0616230 | Grossmont Union High School District | El Cajon | CA |
| 4822530 | Harlingen Consolidated Independent School District | Harlingen | TX |
| 0602430 | Alvord Unified School District | Corona | CA |
| 0609620 | Compton Unified School District | Compton | CA |
| 0901920 | Hartford School District | Hartford | CT |
| 1300840 | Carroll County School District | Carrollton | GA |
| 2507110 | Lynn School District | Lynn | MA |
| 4809670 | Beaumont Independent School District | Beaumont | TX |
| 2913830 | Hazelwood School District | Florissant | MO |

## What to find, per district

1. The **official student calendar** for school year **2026-27**, and for **2027-28** if the board has already
   adopted (or published a draft of) it.
2. Only use sources published by the district itself: its website, its board documents (BoardDocs, Simbli,
   eSchoolView, Finalsite, Edlio, Google Drive/Docs linked from the district site). **Never** use calendar
   aggregator sites (publicholidays, schoolcalendarinfo, officeholidays, calendarlabs, kidscalendar, local news
   summaries or similar). If only an aggregator has it, report the district as not found.
3. The **calendar feed** if the district offers one: an iCal/ICS or webcal link, or a public Google Calendar
   (its ICS address). Only a feed for the district-wide calendar, not a single school's or athletics calendar.
4. Whether the calendar is **board approved**, a **draft/proposed** version, or **tentative**.

## Rules for dates

- Dates are ISO `YYYY-MM-DD`, inclusive, and describe days on which **students do not attend school**.
- Multi-day breaks: first and last weekday students are out, excluding the weekends around them
  (e.g. Winter Break 2026-12-21 to 2027-01-01).
- Kinds:
  - `break`: two or more consecutive weekdays without school (Fall, Thanksgiving, Winter, Mid-Winter, Spring Break).
  - `holiday`: a single weekday without school (Labor Day, Veterans Day, MLK Day, Presidents' Day, Memorial Day, Juneteenth...).
  - `teacher_day`: no school for students, staff work (Teacher Workday, Professional Learning, Student Holiday, Records Day).
  - `early_release`: students attend but are dismissed early. Only district-wide early release days.
  - `other`: anything else students are out for (Election Day closure, Conference Day), say what it is in `notes`.
- Leave out weather make-up days, possible/contingency days, exam days and events that are not closures.
- If dates differ by school level (elementary/middle/high), give the elementary dates and mention the
  difference in `notes`.
- Do not guess, interpolate, or copy dates from another year. If a date is unclear, leave the row out and say so in `notes`
  of the calendar row.

## Output: one CSV, nothing else

Standard CSV (comma separated, double quotes around any field that contains a comma), UTF-8, with this header:

```
nces_leaid,district_name,school_year,row_type,kind,label,start_date,end_date,board_status,source_url,feed_url,feed_format,website,notes
```

- One `row_type=calendar` row per district and school year:
  `start_date` = first day of school for students, `end_date` = last day of school for students,
  `board_status` = `approved` | `draft` | `tentative` | `not_found`, `source_url` = the exact document or page you read,
  `feed_url` / `feed_format` (`ics` | `google` | `webcal`) if a district-wide feed exists, `website` = district homepage.
  `kind` and `label` stay empty.
- One `row_type=period` row per break, holiday, teacher day, early release or other closure, with `kind`, `label`
  (the district's own wording), `start_date`, `end_date`. `board_status`, `source_url` etc. may stay empty.
- `school_year` is written `2026-27` or `2027-28`.
- If you find nothing for a district, still write one calendar row with `board_status=not_found` and a short note.

Example (fictional district, format only):

```
nces_leaid,district_name,school_year,row_type,kind,label,start_date,end_date,board_status,source_url,feed_url,feed_format,website,notes
0000000,Example County School District,2026-27,calendar,,,2026-08-05,2027-05-26,approved,https://www.example-district.org/calendar/2026-27-student-calendar.pdf,https://www.example-district.org/calendar.ics,ics,https://www.example-district.org,
0000000,Example County School District,2026-27,period,holiday,Labor Day,2026-09-07,2026-09-07,,,,,,
0000000,Example County School District,2026-27,period,break,Fall Break,2026-10-12,2026-10-16,,,,,,
0000000,Example County School District,2026-27,period,early_release,Early Release (K-8 conferences),2026-10-28,2026-10-29,,,,,,
```

Work through all 50 districts. If you run out of room, stop after a complete district and list the
nces_leaid values you did not reach in a final calendar row `notes` field of the last district.
