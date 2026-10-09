# Holibase research: US school district calendars, batch 05 of 10

You are researching official student calendars of US public school districts for Holibase, an open,
non-profit database of school holidays (data published under CC BY 4.0). Accuracy matters more than
completeness: a missing district is fine, a wrong date is not.

## Districts in this batch (50)

Each district is identified by its NCES LEAID. Use exactly these ids in your output.

| nces_leaid | district (NCES name) | city | state |
|---|---|---|---|
| 4503390 | Richland School District 2 | Columbia | SC |
| 0641160 | Visalia Unified School District | Visalia | CA |
| 0635130 | San Ramon Valley Unified School District | Danville | CA |
| 1301410 | Columbia County School District | Evans | GA |
| 1803630 | Fort Wayne Community Schools | Fort Wayne | IN |
| 1734510 | Rockford School District 205 | Rockford | IL |
| 3404590 | Elizabeth City School District | Elizabeth | NJ |
| 0603630 | Bakersfield City School District | Bakersfield | CA |
| 1200030 | Alachua County School District | Gainesville | FL |
| 2010140 | Olathe Unified School District 233 | Olathe | KS |
| 2400270 | Charles County Public Schools | La Plata | MD |
| 0802490 | Boulder Valley School District RE-2 | Boulder | CO |
| 5100270 | Arlington County Public Schools | Arlington | VA |
| 2200330 | Calcasieu Parish School District | Lake Charles | LA |
| 1200090 | Bay County School District | Panama City | FL |
| 3703450 | Onslow County Schools | Jacksonville | NC |
| 1302610 | Hall County School District | Gainesville | GA |
| 0622230 | Lodi Unified School District | Lodi | CA |
| 4502700 | Lexington School District 1 | Lexington | SC |
| 5102670 | Norfolk City Public Schools | Norfolk | VA |
| 2011640 | Shawnee Mission Public Schools Unified School District | Shawnee Mission | KS |
| 2201020 | Livingston Parish School District | Livingston | LA |
| 0102430 | Montgomery County School District | Montgomery | AL |
| 0600028 | Temecula Valley Unified School District | Temecula | CA |
| 0405930 | Paradise Valley Unified District | Phoenix | AZ |
| 2400210 | Carroll County Public Schools | Westminster | MD |
| 4821420 | Grand Prairie Independent School District | Grand Prairie | TX |
| 0602630 | Anaheim Union High School District | Anaheim | CA |
| 1741690 | Indian Prairie Community Unit School District 204 | Aurora | IL |
| 3407830 | Jersey City School District | Jersey City | NJ |
| 4502010 | Dorchester School District 2 | Summerville | SC |
| 5102640 | Newport News City Public Schools | Newport News | VA |
| 0406330 | Phoenix Union High School District | Phoenix | AZ |
| 4010590 | Edmond Public Schools | Edmond | OK |
| 0803870 | School District 49 | Peyton | CO |
| 0611110 | Desert Sands Unified School District | La Quinta | CA |
| 0801920 | Academy School District 20 | Colorado Springs | CO |
| 0608460 | Chino Valley Unified School District | Chino | CA |
| 1301860 | Douglas County School District | Douglasville | GA |
| 4834830 | Pflugerville Independent School District | Pflugerville | TX |
| 5303960 | Kent School District | Kent | WA |
| 0615240 | Glendale Unified School District | Glendale | CA |
| 2634470 | Utica Community Schools | Sterling Heights | MI |
| 0623610 | Manteca Unified School District | Manteca | CA |
| 0632550 | West Contra Costa Unified School District | Richmond | CA |
| 5508520 | Madison Metropolitan School District | Madison | WI |
| 3703330 | New Hanover County Schools | Wilmington | NC |
| 4666270 | Sioux Falls School District 49-5 | Sioux Falls | SD |
| 0601332 | Twin Rivers Unified School District | McClellan | CA |
| 2513230 | Worcester School District | Worcester | MA |

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
