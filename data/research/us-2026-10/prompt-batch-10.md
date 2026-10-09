# Holibase research: US school district calendars, batch 10 of 10

You are researching official student calendars of US public school districts for Holibase, an open,
non-profit database of school holidays (data published under CC BY 4.0). Accuracy matters more than
completeness: a missing district is fine, a wrong date is not.

## Districts in this batch (49)

Each district is identified by its NCES LEAID. Use exactly these ids in your output.

| nces_leaid | district (NCES name) | city | state |
|---|---|---|---|
| 4503330 | Pickens County School District | Easley | SC |
| 4844960 | Weslaco Independent School District | Weslaco | TX |
| 3904701 | Hilliard City School District | Columbus | OH |
| 1808820 | Perry Township Metropolitan School District | Indianapolis | IN |
| 0904320 | Stamford School District | Stamford | CT |
| 1812810 | Wayne Township Metropolitan School District | Indianapolis | IN |
| 1801200 | Carmel Clay Schools | Carmel | IN |
| 0626640 | Napa Valley Unified School District | Napa | CA |
| 0403450 | Glendale Union High School District | Glendale | AZ |
| 4901050 | Tooele School District | Tooele | UT |
| 2628560 | Plymouth-Canton Community Schools | Plymouth | MI |
| 4021720 | Norman Public Schools | Norman | OK |
| 1727710 | Naperville Community Unit District 203 | Naperville | IL |
| 4811790 | Bryan Independent School District | Bryan | TX |
| 0629270 | Oxnard Union High School District | Oxnard | CA |
| 4503870 | York School District 3 | Rock Hill | SC |
| 3700690 | Catawba County Schools | Newton | NC |
| 0606810 | Cajon Valley Union Elementary School District | El Cajon | CA |
| 3416290 | Trenton City School District | Trenton | NJ |
| 0607970 | Central Unified School District | Fresno | CA |
| 4104740 | Eugene School District 4J | Eugene | OR |
| 4502130 | Florence School District 1 | Florence | SC |
| 0609070 | Coachella Valley Unified School District | Thermal | CA |
| 0633980 | Salinas Union High School District | Salinas | CA |
| 5512360 | Racine School District | Racine | WI |
| 0609640 | Conejo Valley Unified School District | Thousand Oaks | CA |
| 0511970 | Rogers Public Schools | Rogers | AR |
| 2400690 | Wicomico County Public Schools | Salisbury | MD |
| 1200270 | Citrus County School District | Inverness | FL |
| 5310110 | Yakima School District | Yakima | WA |
| 0616325 | Hacienda La Puente Unified School District | City Of Industry | CA |
| 0636840 | Simi Valley Unified School District | Simi Valley | CA |
| 0625150 | Modesto City High School District | Modesto | CA |
| 4502580 | Lancaster County School District | Lancaster | SC |
| 1304410 | Rockdale County School District | Conyers | GA |
| 1300290 | Barrow County School District | Winder | GA |
| 1734740 | Schaumburg Community Consolidated School District 54 | Schaumburg | IL |
| 2503090 | Brockton School District | Brockton | MA |
| 0602850 | Antioch Unified School District | Antioch | CA |
| 1906540 | Cedar Rapids Community School District | Cedar Rapids | IA |
| 5305430 | Mukilteo School District | Everett | WA |
| 5305850 | North Thurston Public Schools | Lacey | WA |
| 2916400 | Kansas City 33 School District | Kansas City | MO |
| 0406810 | Queen Creek Unified District | Queen Creek | AZ |
| 5301110 | Central Valley School District | Liberty Lake | WA |
| 1914700 | Iowa City Community School District | Iowa City | IA |
| 0408850 | Vail Unified District | Vail | AZ |
| 3703780 | Randolph County Schools | Asheboro | NC |
| 5500390 | Appleton Area School District | Appleton | WI |

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

Work through all 49 districts. If you run out of room, stop after a complete district and list the
nces_leaid values you did not reach in a final calendar row `notes` field of the last district.
