# Holibase research: US school district calendars, batch 01 of 10

You are researching official student calendars of US public school districts for Holibase, an open,
non-profit database of school holidays (data published under CC BY 4.0). Accuracy matters more than
completeness: a missing district is fine, a wrong date is not.

## Districts in this batch (50)

Each district is identified by its NCES LEAID. Use exactly these ids in your output.

| nces_leaid | district (NCES name) | city | state |
|---|---|---|---|
| 1200390 | Dade County School District | Miami | FL |
| 1709930 | Chicago Public School District 299 | Chicago | IL |
| 3200060 | Clark County School District | Las Vegas | NV |
| 7200030 | Puerto Rico Department of Education | Hato Rey | PR |
| 1200870 | Hillsborough County School District | Tampa | FL |
| 1201440 | Orange County School District | Orlando | FL |
| 1201500 | Palm Beach County School District | West Palm Beach | FL |
| 5101260 | Fairfax County Public Schools | Falls Church | VA |
| 4823640 | Houston Independent School District | Houston | TX |
| 1500030 | Hawaii Department of Education | Honolulu | HI |
| 3704720 | Wake County Schools | Cary | NC |
| 2400480 | Montgomery County Public Schools | Rockville | MD |
| 3702970 | Charlotte-Mecklenburg Schools | Charlotte | NC |
| 4816230 | Dallas Independent School District | Dallas | TX |
| 4218990 | Philadelphia City School District | Philadelphia | PA |
| 1201590 | Polk County School District | Bartow | FL |
| 4700148 | Shelby County School District | Memphis | TN |
| 2400120 | Baltimore County Public Schools | Towson | MD |
| 2102990 | Jefferson County School District | Louisville | KY |
| 1301740 | DeKalb County School District | Stone Mountain | GA |
| 0803360 | Denver County School District 1 | Denver | CO |
| 4900030 | Alpine School District | American Fork | UT |
| 1201530 | Pasco County School District | Land O Lakes | FL |
| 2400060 | Anne Arundel County Public Schools | Annapolis | MD |
| 2400090 | Baltimore City Public Schools | Baltimore | MD |
| 1201470 | Osceola County School District | Kissimmee | FL |
| 4815000 | Conroe Independent School District | Conroe | TX |
| 4900210 | Davis School District | Farmington | UT |
| 1200150 | Brevard County School District | Viera | FL |
| 4819700 | Fort Worth Independent School District | Fort Worth | TX |
| 0614550 | Fresno Unified School District | Fresno | CA |
| 3701920 | Guilford County Schools | Greensboro | NC |
| 5509600 | Milwaukee School District | Milwaukee | WI |
| 4820010 | Frisco Independent School District | Frisco | TX |
| 5103840 | Virginia Beach City Public Schools | Virginia Beach | VA |
| 5100840 | Chesterfield County Public Schools | Chesterfield | VA |
| 1201710 | Seminole County School District | Sanford | FL |
| 3200480 | Washoe County School District | Reno | NV |
| 0612330 | Elk Grove Unified School District | Elk Grove | CA |
| 0622500 | Long Beach Unified School District | Long Beach | CA |
| 1201920 | Volusia County School District | Deland | FL |
| 0803450 | Douglas County School District RE-1 | Castle Rock | CO |
| 4702220 | Knox County School District | Knoxville | TN |
| 4900360 | Granite School District | Salt Lake City | UT |
| 4900420 | Jordan School District | West Jordan | UT |
| 2400420 | Howard County Public Schools | Ellicott City | MD |
| 4832940 | North East Independent School District | San Antonio | TX |
| 4807710 | Aldine Independent School District | Houston | TX |
| 0404970 | Mesa Unified District | Mesa | AZ |
| 1302220 | Forsyth County School District | Cumming | GA |

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
