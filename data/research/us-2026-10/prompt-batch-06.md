# Holibase research: US school district calendars, batch 06 of 10

You are researching official student calendars of US public school districts for Holibase, an open,
non-profit database of school holidays (data published under CC BY 4.0). Accuracy matters more than
completeness: a missing district is fine, a wrong date is not.

## Districts in this batch (50)

Each district is identified by its NCES LEAID. Use exactly these ids in your output.

| nces_leaid | district (NCES name) | city | state |
|---|---|---|---|
| 4822170 | Hallsville Independent School District | Hallsville | TX |
| 1731740 | Plainfield School District 202 | Plainfield | IL |
| 3700012 | Pitt County Schools | Greenville | NC |
| 0634590 | San Jose Unified School District | San Jose | CA |
| 4800010 | Hays Consolidated Independent School District | Kyle | TX |
| 3631920 | Yonkers City School District | Yonkers | NY |
| 3412690 | Paterson City School District | Paterson | NJ |
| 2928860 | Springfield R-XII School District | Springfield | MO |
| 0101800 | Huntsville City School District | Huntsville | AL |
| 4813050 | Carrollton-Farmers Branch Independent School District | Carrollton | TX |
| 3904676 | Olentangy Local School District | Lewis Center | OH |
| 4828500 | Lubbock Independent School District | Lubbock | TX |
| 0802580 | School District 27J | Brighton | CO |
| 5103640 | Spotsylvania County Public Schools | Fredericksburg | VA |
| 4821150 | Goose Creek Consolidated Independent School District | Baytown | TX |
| 4817700 | Eagle Mountain-Saginaw Independent School District | Fort Worth | TX |
| 0628650 | Orange Unified School District | Orange | CA |
| 2200090 | Ascension Parish School District | Donaldsonville | LA |
| 1200810 | Hernando County School District | Brooksville | FL |
| 2511130 | Springfield School District | Springfield | MA |
| 4020250 | Moore Public Schools | Moore | OK |
| 4824990 | Judson Independent School District | San Antonio | TX |
| 4829850 | McKinney Independent School District | McKinney | TX |
| 4824060 | Hurst-Euless-Bedford Independent School District | Bedford | TX |
| 3173740 | Millard Public Schools | Omaha | NE |
| 0600014 | Hesperia Unified School District | Hesperia | CA |
| 5400600 | Kanawha County School District | Charleston | WV |
| 0402690 | Dysart Unified District | Surprise | AZ |
| 0632370 | Rialto Unified School District | Rialto | CA |
| 1301500 | Coweta County School District | Newnan | GA |
| 5306960 | Puyallup School District | Puyallup | WA |
| 4826130 | La Joya Independent School District | La Joya | TX |
| 0804410 | Greeley School District 6 | Greeley | CO |
| 4500720 | Aiken County School District | Aiken | SC |
| 4842960 | Tomball Independent School District | Tomball | TX |
| 0616920 | Hemet Unified School District | Hemet | CA |
| 3501500 | Las Cruces Public Schools | Las Cruces | NM |
| 2400660 | Washington County Public Schools | Hagerstown | MD |
| 5305910 | Northshore School District | Bothell | WA |
| 0630660 | Placentia-Yorba Linda Unified School District | Placentia | CA |
| 0633860 | Saddleback Valley Unified School District | Mission Viejo | CA |
| 0512660 | Springdale School District | Springdale | AR |
| 3700030 | Alamance-Burlington Schools | Burlington | NC |
| 0611460 | Downey Unified School District | Downey | CA |
| 3700450 | Buncombe County Schools | Asheville | NC |
| 4810230 | Birdville Independent School District | Haltom City | TX |
| 2012000 | Blue Valley Unified School District 229 | Overland Park | KS |
| 5302820 | Federal Way School District | Federal Way | WA |
| 0608610 | Chula Vista Elementary School District | Chula Vista | CA |
| 0803060 | Colorado Springs School District 11 | Colorado Springs | CO |

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
