# Holibase research: US school district calendars, batch 02 of 10

You are researching official student calendars of US public school districts for Holibase, an open,
non-profit database of school holidays (data published under CC BY 4.0). Accuracy matters more than
completeness: a missing district is fine, a wrong date is not.

## Districts in this batch (50)

Each district is identified by its NCES LEAID. Use exactly these ids in your output.

| nces_leaid | district (NCES name) | city | state |
|---|---|---|---|
| 1201230 | Manatee County School District | Bradenton | FL |
| 4808700 | Arlington Independent School District | Arlington | TX |
| 3174820 | Omaha Public Schools | Omaha | NE |
| 4825740 | Klein Independent School District | Klein | TX |
| 3701500 | Forsyth County Schools | Winston Salem | NC |
| 1201740 | St. Johns County School District | St Augustine | FL |
| 4703690 | Rutherford County School District | Murfreesboro | TN |
| 0802910 | Cherry Creek School District 5 | Greenwood Village | CO |
| 1100030 | District of Columbia Public Schools | Washington | DC |
| 1301230 | Clayton County School District | Jonesboro | GA |
| 4820340 | Garland Independent School District | Garland | TX |
| 5101890 | Henrico County Public Schools | Henrico | VA |
| 4501440 | Charleston County School District | Charleston | SC |
| 5307710 | Seattle Public Schools | Seattle | WA |
| 0102370 | Mobile County School District | Mobile | AL |
| 1300120 | Atlanta City School District | Atlanta | GA |
| 0609850 | Corona-Norco Unified School District | Norco | CA |
| 1201770 | St. Lucie County School District | Port St Lucie | FL |
| 3700011 | Cumberland County Schools | Fayetteville | NC |
| 0634410 | San Francisco Unified School District | San Francisco | CA |
| 2601103 | Detroit Public Schools Community District | Detroit | MI |
| 4502490 | Horry County School District | Conway | SC |
| 4823910 | Humble Independent School District | Humble | TX |
| 1200330 | Collier County School District | Naples | FL |
| 4818300 | El Paso Independent School District | El Paso | TX |
| 2400330 | Frederick County Public Schools | Frederick | MD |
| 1201050 | Lake County School District | Tavares | FL |
| 4827300 | Lewisville Independent School District | Lewisville | TX |
| 4838080 | Round Rock Independent School District | Round Rock | TX |
| 2200840 | Jefferson Parish School District | Harvey | LA |
| 4826580 | Lamar Consolidated Independent School District | Rosenberg | TX |
| 4840710 | Socorro Independent School District | El Paso | TX |
| 4835100 | Plano Independent School District | Plano | TX |
| 3904380 | Columbus City School District | Columbus | OH |
| 4834320 | Pasadena Independent School District | Pasadena | TX |
| 1201260 | Marion County School District | Ocala | FL |
| 2502790 | Boston School District | Roxbury | MA |
| 2012990 | Wichita Unified School District 259 | Wichita | KS |
| 4701590 | Hamilton County School District | Chattanooga | TN |
| 1201680 | Sarasota County School District | Sarasota | FL |
| 3411340 | Newark City School District | Newark | NJ |
| 0634170 | San Bernardino City Unified School District | San Bernardino | CA |
| 4838730 | San Antonio Independent School District | San Antonio | TX |
| 4900630 | Nebo School District | Spanish Fork | UT |
| 0609030 | Clovis Unified School District | Clovis | CA |
| 4110040 | Portland School District 1J | Portland | OR |
| 0619540 | Kern High School District | Bakersfield | CA |
| 1302820 | Henry County School District | McDonough | GA |
| 4825660 | Killeen Independent School District | Killeen | TX |
| 4827030 | Leander Independent School District | Leander | TX |

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
