# Step 2 — Design decisions for bronze (reference version)

1. **How does your ingestion know that a file was already loaded?** What would happen if the same file changes later?

The output Parquet has a name derived from the input file (`date=2026-05-03/readings_20260503.csv.gz` →
`readings/date=2026-05-03/readings_20260503.parquet`). Before loading a file I ask whether that Parquet exists: if it does,
I skip it. So "the data is stored" and "the file is marked as loaded" are the same thing and cannot get out of sync (with a separate
log, a crash between saving and writing the note would load the file twice).

**Honest limit:** this design does NOT detect that an already-loaded file changed. It only checks whether its Parquet exists,
not whether the content is the same. If the provider re-sends May 3rd corrected, I skip it silently. To detect it I would store a
fingerprint (size or hash) next to the Parquet and compare it on every run. I did not, because the historian does not re-edit
closed days, but it is a conscious decision, not an oversight. Reference tables do change, and for them I do the opposite: I never
skip them, I rewrite the whole Parquet on every run.

2. **Why Parquet and not leave the CSVs? Why not clean already in bronze?**

Parquet is columnar (for an average of `value` I read only that column, not all five), stores the type of each column, is compressed
(much smaller than CSV) and is read by DuckDB, pandas, Spark and dbt. A CSV is untyped text that must be read in full.

I do not clean in bronze because bronze is the evidence: what arrived, as it arrived. If tomorrow I find a cleaning rule was wrong
(for example, that the `UNCERTAIN` readings were useful), I go back to the raw data and rebuild silver; had I deleted the `-9999`,
the copies or the `BAD` rows in bronze, that data would be lost. It also allows auditing: when someone asks where a `NULL` comes
from, I can reach the original row. That is why bronze stores everything as text and keeps duplicates and `BAD` readings.

3. **What happens if your process dies halfway through writing a file?**

I always write to a temporary file (`readings_20260503.parquet.tmp`) and only when it is complete do I rename it to the final name.
Renaming is atomic: either the Parquet appears complete or it does not appear. If the process dies halfway, at most a `.tmp`
remains that no reader confuses with a result (it does not end in `.parquet`), and the next run sees the final Parquet does not
exist and redoes it. If the write raises an error, I delete the `.tmp` before letting the error rise.

4. **What did you do with the corrupt file and why did you not simply ignore it? Who should find out, and how?**

The 2026-07-01 file has a cut gzip (only ~55 % of its rows can be read). I set the WHOLE file aside in quarantine
(`data/quarantine/date=2026-07-01/`): I copy the original and leave a `.reason.txt` note with the file, date and time, and the error. I do not load the
readable rows, because half data that looks good is worse than a known gap, and nothing from that file enters bronze. The load of
the other 149 files continues.

I did not ignore it (`except: pass`) because the data would vanish without anyone knowing. I catch only `duckdb.Error` (read errors), not any exception,
so that my own programming mistake is not disguised as a "broken file". The program prints a `WARNING` per file and an `ATTENTION`
at the end, and exits with code 0. Who should find out is whoever operates the ingestion and, above all, whoever claims the data from the
provider; the Dagster asset check of step 6 makes it visible outside the terminal. Since the quarantined file is retried on
every run, if the provider re-sends it complete it loads by itself.

5. **What metadata did you add to each row and what is it for when someone asks "where did this number come from"?**

`_source_file` (path of the raw file the row came from, relative to `data/raw`) and `_ingested_at` (when it reached bronze, in UTC).
With them, from any gold number I can go down to silver, bronze and the exact file, and know which run loaded it. A metadata field
that is missing and would be worth adding: the line number inside the file, to reach the exact row.
