# Holibase research: US school district calendars, batch 07 of 10

You are researching official student calendars of US public school districts for Holibase, an open,
non-profit database of school holidays (data published under CC BY 4.0). Accuracy matters more than
completeness: a missing district is fine, a wrong date is not.

## Districts in this batch (50)

Each district is identified by its NCES LEAID. Use exactly these ids in your output.

| nces_leaid | district (NCES name) | city | state |
|---|---|---|---|
| 2200270 | Bossier Parish School District | Benton | LA |
| 1600360 | Boise City Independent School District 1 | Boise | ID |
| 0608160 | Chaffey Joint Union High School District | Ontario | CA |
| 0639420 | Torrance Unified School District | Torrance | CA |
| 3624750 | Rochester City School District | Rochester | NY |
| 3904480 | South-Western City School District | Grove City | OH |
| 4503360 | Richland School District 1 | Columbia | SC |
| 5309270 | Vancouver Public Schools | Vancouver | WA |
| 0613890 | Folsom-Cordova Unified School District | Rancho Cordova | CA |
| 0600029 | Murrieta Valley Unified School District | Murrieta | CA |
| 5302700 | Evergreen School District (Clark) | Vancouver | WA |
| 1803450 | Evansville-Vanderburgh School Corporation | Evansville | IN |
| 2007950 | Kansas City Unified School District 500 | Kansas City | KS |
| 5300480 | Bethel School District | Spanaway | WA |
| 0640150 | Tustin Unified School District | Tustin | CA |
| 2201290 | Rapides Parish School District | Alexandria | LA |
| 1300420 | Bibb County School District | Macon | GA |
| 3703930 | Robeson County Schools | Lumberton | NC |
| 3904490 | Toledo City School District | Toledo | OH |
| 2922800 | North Kansas City 74 School District | Kansas City | MO |
| 0602820 | Antelope Valley Union Joint High School District | Lancaster | CA |
| 2725200 | Osseo Public School District | Maple Grove | MN |
| 0509000 | Little Rock School District | Little Rock | AR |
| 1810650 | Hamilton Southeastern Schools | Fishers | IN |
| 1804770 | Indianapolis Public Schools | Indianapolis | IN |
| 4501110 | Beaufort County School District | Beaufort | SC |
| 3702310 | Iredell-Statesville Schools | Statesville | NC |
| 5103240 | Richmond City Public Schools | Richmond | VA |
| 5302400 | Edmonds School District | Lynnwood | WA |
| 0100390 | Birmingham City School District | Birmingham | AL |
| 4820250 | Galena Park Independent School District | Houston | TX |
| 4834440 | Pearland Independent School District | Pearland | TX |
| 4807890 | Allen Independent School District | Allen | TX |
| 1708550 | Community Unit School District 300 | Algonquin | IL |
| 4704550 | Wilson County School District | Lebanon | TN |
| 0102220 | Madison County School District | Huntsville | AL |
| 0407570 | Scottsdale Unified District | Scottsdale | AZ |
| 0103030 | Shelby County School District | Columbiana | AL |
| 0600027 | Lake Elsinore Unified School District | Lake Elsinore | CA |
| 2100510 | Boone County School District | Florence | KY |
| 0642510 | William S. Hart Union High School District | Santa Clarita | CA |
| 5302670 | Everett School District | Everett | WA |
| 0631320 | Pomona Unified School District | Pomona | CA |
| 0613360 | Fairfield-Suisun Unified School District | Fairfield | CA |
| 5300390 | Bellevue School District | Bellevue | WA |
| 4900120 | Cache School District | Logan | UT |
| 4826790 | Laredo Independent School District | Laredo | TX |
| 4400900 | Providence School District | Providence | RI |
| 3702010 | Harnett County Schools | Lillington | NC |
| 0900450 | Bridgeport School District | Bridgeport | CT |

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
