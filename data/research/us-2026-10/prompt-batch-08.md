# Holibase research: US school district calendars, batch 08 of 10

You are researching official student calendars of US public school districts for Holibase, an open,
non-profit database of school holidays (data published under CC BY 4.0). Accuracy matters more than
completeness: a missing district is fine, a wrong date is not.

## Districts in this batch (50)

Each district is identified by its NCES LEAID. Use exactly these ids in your output.

| nces_leaid | district (NCES name) | city | state |
|---|---|---|---|
| 0629550 | Palm Springs Unified School District | Palm Springs | CA |
| 5400060 | Berkeley County School District | Martinsburg | WV |
| 0611820 | East Side Union High School District | San Jose | CA |
| 3904348 | Akron City School District | Akron | OH |
| 0623340 | Madera Unified School District | Madera | CA |
| 4829670 | McAllen Independent School District | McAllen | TX |
| 4005490 | Broken Arrow Public Schools | Broken Arrow | OK |
| 1302130 | Fayette County School District | Fayetteville | GA |
| 0804350 | Mesa County Valley School District 51 | Grand Junction | CO |
| 2926850 | Rockwood R-VI School District | Eureka | MO |
| 2733810 | South Washington County School District | Cottage Grove | MN |
| 0503060 | Bentonville Public Schools | Bentonville | AR |
| 4219170 | Pittsburgh School District | Pittsburgh | PA |
| 0200510 | Matanuska-Susitna Borough School District | Palmer | AK |
| 5101800 | Hampton City Public Schools | Hampton | VA |
| 4832400 | New Caney Independent School District | New Caney | TX |
| 4846530 | Wylie Independent School District | Wylie | TX |
| 0606390 | Panama-Buena Vista School District | Bakersfield | CA |
| 0632070 | Redlands Unified School District | Redlands | CA |
| 0103390 | Tuscaloosa County School District | Tuscaloosa | AL |
| 2611600 | Dearborn City School District | Dearborn | MI |
| 4837650 | Rockwall Independent School District | Rockwall | TX |
| 0625470 | Montebello Unified School District | Montebello | CA |
| 5303750 | Issaquah School District | Issaquah | WA |
| 0691135 | Val Verde Unified School District | Perris | CA |
| 2201680 | Tangipahoa Parish School District | Amite | LA |
| 4900870 | Salt Lake City School District | Salt Lake City | UT |
| 5306570 | Pasco School District | Pasco | WA |
| 0634880 | San Marcos Unified School District | San Marcos | CA |
| 4025290 | Putnam City Public Schools | Warr Acres | OK |
| 5303930 | Kennewick School District | Kennewick | WA |
| 0902790 | New Haven School District | New Haven | CT |
| 0409060 | Washington Elementary District | Glendale | AZ |
| 4100023 | Hillsboro School District 1J | Hillsboro | OR |
| 0904830 | Waterbury School District | Waterbury | CT |
| 4843470 | Tyler Independent School District | Tyler | TX |
| 1303930 | Newton County School District | Covington | GA |
| 3628590 | Syracuse City School District | Syracuse | NY |
| 2901000 | Columbia 93 School District | Columbia | MO |
| 4819560 | Forney Independent School District | Forney | TX |
| 2105730 | Warren County School District | Bowling Green | KY |
| 3605280 | Brentwood Union Free School District | Brentwood | NY |
| 4503900 | York School District 4 | Fort Mill | SC |
| 0609390 | Colton Joint Unified School District | Colton | CA |
| 5505820 | Green Bay Area School District | Green Bay | WI |
| 1201290 | Martin County School District | Stuart | FL |
| 5507320 | Kenosha School District | Kenosha | WI |
| 2803830 | Rankin County School District | Brandon | MS |
| 5300300 | Auburn School District | Auburn | WA |
| 0641190 | Vista Unified School District | Vista | CA |

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
