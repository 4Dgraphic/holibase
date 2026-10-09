# US district research, October 2026

The 499 largest US school districts (by students, NCES CCD 2024-25) that have no verified calendar yet,
in 10 batches of 50. Together with the districts already covered this is about 44 % of US public school students.

1. Paste `prompt-batch-NN.md` into a deep research run (ChatGPT recommended; a second model is optional and used
   as a cross-check).
2. Save the CSV it returns as `results/batch-NN-<model>.csv`, e.g. `results/batch-01-gpt.csv`.
3. Commit and push. The editorial import workflow converts all results (`scripts/research_to_editorial.py`),
   writes `REPORT.md` into the job summary and imports the calendars.

Confirmed only when board approved, from an official district source, complete (first/last day, Thanksgiving,
winter break, at least 6 periods) and, with two models, without conflicting dates. Everything else is imported
as pending (API: `include=pending`). Calendar feed URLs found by the research are stored on the district
(`external_ids.calendar_feed_url`) for a later automatic feed import.
