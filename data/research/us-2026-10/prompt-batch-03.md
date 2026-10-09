# Holibase research: US school district calendars, batch 03 of 10

You are researching official student calendars of US public school districts for Holibase, an open,
non-profit database of school holidays (data published under CC BY 4.0). Accuracy matters more than
completeness: a missing district is fine, a wrong date is not.

## Districts in this batch (50)

Each district is identified by its NCES LEAID. Use exactly these ids in your output.

| nces_leaid | district (NCES name) | city | state |
|---|---|---|---|
| 0200180 | Anchorage School District | Anchorage | AK |
| 3172840 | Lincoln Public Schools | Lincoln | NE |
| 2101860 | Fayette County School District | Lexington | KY |
| 1301110 | Cherokee County School District | Canton | GA |
| 4704530 | Williamson County School District | Franklin | TN |
| 0401870 | Chandler Unified District | Chandler | AZ |
| 3704620 | Union County Public Schools | Monroe | NC |
| 4843650 | United Independent School District | Laredo | TX |
| 5100810 | Chesapeake City Public Schools | Chesapeake | VA |
| 0607440 | Capistrano Unified School District | San Juan Capistrano | CA |
| 0408800 | Tucson Unified District | Tucson | AZ |
| 4814280 | Clear Creek Independent School District | League City | TX |
| 0634620 | San Juan Unified School District | Carmichael | CA |
| 4501170 | Berkeley County School District | Moncks Corner | SC |
| 4703030 | Clarksville-Montgomery County School System | Clarksville | TN |
| 2200540 | East Baton Rouge Parish School District | Baton Rouge | LA |
| 1200300 | Clay County School District | Green Cove Springs | FL |
| 1602100 | Meridian Joint School District 2 | Meridian | ID |
| 0802340 | Adams-Arapahoe School District 28J | Aurora | CO |
| 4807830 | Alief Independent School District | Houston | TX |
| 2703180 | Anoka-Hennepin Public School District | Anoka | MN |
| 0633150 | Riverside Unified School District | Riverside | CA |
| 0684500 | Irvine Unified School District | Irvine | CA |
| 4110820 | Salem-Keizer School District 24J | Salem | OR |
| 4830390 | Mesquite Independent School District | Mesquite | TX |
| 0633840 | Sacramento City Unified School District | Sacramento | CA |
| 4101920 | Beaverton School District 48J | Beaverton | OR |
| 2400390 | Harford County Public Schools | Bel Air | MD |
| 3702370 | Johnston County Schools | Smithfield | NC |
| 0614880 | Garden Grove Unified School District | Garden Grove | CA |
| 4837020 | Richardson Independent School District | Richardson | TX |
| 4901140 | Washington School District | St. George | UT |
| 1200510 | Escambia County School District | Pensacola | FL |
| 4811680 | Brownsville Independent School District | Brownsville | TX |
| 0635310 | Santa Ana Unified School District | Santa Ana | CA |
| 2201650 | St. Tammany Parish School District | Covington | LA |
| 3700530 | Cabarrus County Schools | Concord | NC |
| 1301020 | Chatham County School District | Savannah | GA |
| 0101920 | Jefferson County School District | Birmingham | AL |
| 4828920 | Mansfield Independent School District | Mansfield | TX |
| 2801320 | DeSoto County School District | Hernando | MS |
| 3904375 | Cincinnati City School District | Cincinnati | OH |
| 0806900 | Adams 12 Five Star Schools | Thornton | CO |
| 0406250 | Peoria Unified School District | Glendale | AZ |
| 0631530 | Poway Unified School District | San Diego | CA |
| 0638640 | Sweetwater Union High School District | Chula Vista | CA |
| 4846680 | Ysleta Independent School District | El Paso | TX |
| 1713710 | School District U-46 | Elgin | IL |
| 0628050 | Oakland Unified School District | Oakland | CA |
| 4818000 | Ector County Independent School District | Odessa | TX |

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
