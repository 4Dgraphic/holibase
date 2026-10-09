# Holibase research: US school district calendars, batch 04 of 10

You are researching official student calendars of US public school districts for Holibase, an open,
non-profit database of school holidays (data published under CC BY 4.0). Accuracy matters more than
completeness: a missing district is fine, a wrong date is not.

## Districts in this batch (50)

Each district is identified by its NCES LEAID. Use exactly these ids in your output.

| nces_leaid | district (NCES name) | city | state |
|---|---|---|---|
| 0638010 | Stockton Unified School District | Stockton | CA |
| 4030240 | Tulsa Public Schools | Tulsa | OK |
| 4841220 | Spring Independent School District | Houston | TX |
| 4818180 | Edinburg Consolidated Independent School District | Edinburg | TX |
| 4816740 | Denton Independent School District | Denton | TX |
| 3904378 | Cleveland Municipal School District | Cleveland | OH |
| 0614400 | Fremont Unified School District | Fremont | CA |
| 4815270 | Corpus Christi Independent School District | Corpus Christi | TX |
| 2733840 | St. Paul Public School District | Saint Paul | MN |
| 0613920 | Fontana Unified School District | Fontana | CA |
| 4022770 | Oklahoma City Public Schools | Oklahoma City | OK |
| 4900142 | Canyons School District | Sandy | UT |
| 4841100 | Spring Branch Independent School District | Houston | TX |
| 0407750 | Deer Valley Unified District | Phoenix | AZ |
| 2200300 | Caddo Parish School District | Shreveport | LA |
| 4833180 | Northwest Independent School District | Justin | TX |
| 4901200 | Weber School District | Ogden | UT |
| 1201380 | Okaloosa County School District | Fort Walton Beach | FL |
| 4825260 | Keller Independent School District | Keller | TX |
| 0100270 | Baldwin County School District | Bay Minette | AL |
| 3701260 | Durham Public Schools | Durham | NC |
| 5103660 | Stafford County Public Schools | Stafford | VA |
| 4836000 | Prosper Independent School District | Prosper | TX |
| 1201110 | Leon County School District | Tallahassee | FL |
| 0805370 | St. Vrain Valley School District RE 1J | Longmont | CO |
| 0403400 | Gilbert Unified District | Gilbert | AZ |
| 1304020 | Paulding County School District | Dallas | GA |
| 3701620 | Gaston County Schools | Gastonia | NC |
| 5304230 | Lake Washington School District | Redmond | WA |
| 1302880 | Houston County School District | Perry | GA |
| 0625800 | Moreno Valley Unified School District | Moreno Valley | CA |
| 4824420 | Irving Independent School District | Irving | TX |
| 4704020 | Sumner County School District | Gallatin | TN |
| 3605850 | Buffalo City School District | Buffalo | NY |
| 1908970 | Des Moines Independent Community School District | Des Moines | IA |
| 4808090 | Alvin Independent School District | Alvin | TX |
| 2721240 | Minneapolis Public School District | Minneapolis | MN |
| 4814730 | Comal Independent School District | New Braunfels | TX |
| 4830570 | Midland Independent School District | Midland | TX |
| 1201650 | Santa Rosa County School District | Milton | FL |
| 4834860 | Pharr-San Juan-Alamo Independent School District | Pharr | TX |
| 0626370 | Mount Diablo Unified School District | Concord | CA |
| 2200870 | Lafayette Parish School District | Lafayette | LA |
| 0803990 | Poudre School District R-1 | Fort Collins | CO |
| 1303870 | Muscogee County School District | Columbus | GA |
| 4808130 | Amarillo Independent School District | Amarillo | TX |
| 2732390 | Rosemount-Apple Valley-Eagan | Rosemount | MN |
| 1304380 | Richmond County School District | Augusta | GA |
| 5308250 | Spokane Public Schools | Spokane | WA |
| 5308700 | Tacoma Public Schools | Tacoma | WA |

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
