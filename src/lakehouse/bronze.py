"""Bronze: faithfully store what arrives.

What is here: load ONE file (`load_file`), walk through all of them skipping the ones already loaded (`load_all`),
set broken files aside in quarantine (`move_to_quarantine`) and load the reference tables (`load_reference`).
`run()` puts it all together: it is what `make bronze` runs (`python -m lakehouse.bronze`).
"""

from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path

import duckdb

from lakehouse.paths import bronze_dir, quarantine_dir, raw_dir


def destination_of(path: Path) -> Path:
    """Where the Parquet of a raw file must end up. Same file -> same destination.

    It lives in its own function because two places need it: `load_file` (to write) and `load_all` (to know whether it
    already exists). If the computation were copied in both, one day you would change one and not the other.
    """
    folder = bronze_dir() / "readings" / path.parent.name  # e.g. readings/date=2026-05-01/
    return folder / (path.name.removesuffix(".csv.gz") + ".parquet")


def load_file(path: Path) -> Path:
    """Read a historian .csv.gz (everything as text) and write it as Parquet in bronze/readings/."""
    path = Path(path)

    destination = destination_of(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = destination.with_name(destination.name + ".tmp")  # does not end in .parquet: nobody mistakes it for a result

    # Traceability: which file each row comes from and when it reached bronze.
    source = path.relative_to(raw_dir()).as_posix()
    ingested = datetime.now(UTC).isoformat()

    # Read EVERYTHING as text (bronze does not interpret) and by column name (header=true).
    # Named parameters ($source...) instead of `?`: with several `?` DuckDB may assign them in a different order
    # than the text. With names there is no possible confusion.
    try:
        duckdb.execute(
            """
            copy (
                select timestamp, tag, value, unit, quality,
                       $source as _source_file,
                       $ingested as _ingested_at
                from read_csv($input, all_varchar = true, header = true)
            ) to $output (format parquet)
            """,
            {"source": source, "ingested": ingested, "input": str(path), "output": str(temp)},
        )
    except Exception:
        temp.unlink(missing_ok=True)  # leave no half-written garbage; the error continues on its way to the caller
        raise

    # Atomic write: it was written under a temporary name and only now appears with the final name.
    # If the process dies before this line, there is no half-written Parquet with a good-looking name.
    temp.replace(destination)
    return destination


def move_to_quarantine(path: Path, error: Exception) -> None:
    """Set aside a file that could not be read: copy the original and leave a note with the reason.

    It is not thrown away (you would lose the evidence) and not ignored (nobody would find out): it is set aside and
    someone is told. The original in data/raw/ is not touched; it is COPIED.
    """
    destination = quarantine_dir() / path.parent.name
    destination.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, destination / path.name)
    note = destination / (path.name + ".reason.txt")
    note.write_text(
        f"file: {path.relative_to(raw_dir()).as_posix()}\n"
        f"when: {datetime.now(UTC).isoformat()}\n"
        f"error: {type(error).__name__}\n"
        f"detail: {str(error).strip()[:500]}\n"
    )


def load_all() -> tuple[int, int, int]:
    """Walk through all the historian files and load only those that do not have their Parquet yet.

    A broken file does NOT stop the others: it is set aside in quarantine with its reason and the run continues.
    Returns (loaded, skipped, quarantined).
    """
    files = sorted((raw_dir() / "historian").glob("date=*/*.csv.gz"))  # sorted: always the same order

    loaded = skipped = quarantined = 0
    for path in files:
        if destination_of(path).exists():  # already loaded: not done again (this is what gives idempotency)
            skipped += 1
            continue
        try:
            load_file(path)
        except duckdb.Error as error:
            # Only DuckDB errors while reading (unreadable file): not a programming error such as a NameError.
            # A quarantined file is retried on every run, in case the provider re-sends it fixed.
            move_to_quarantine(path, error)
            quarantined += 1
            print(f"  WARNING: {path.name} could not be read ({type(error).__name__}); moved to quarantine")
            continue
        loaded += 1
        print(f"  loaded: {path.name}")

    print(f"Summary: {loaded} loaded, {skipped} skipped, {quarantined} in quarantine, out of {len(files)} files.")
    return loaded, skipped, quarantined


REFERENCE_TABLES = ("assets", "work_orders")


def load_reference(name: str) -> Path:
    """Load a reference table (`assets` or `work_orders`) into bronze/<name>/<name>.parquet.

    Unlike the historian, there is no new file every day here: there is ONE snapshot of the current state that can
    change (a new order, a corrected pump). That is why it is NOT skipped if it already exists: today's CSV is read and
    the whole Parquet is REWRITTEN. It is still idempotent (same CSV, same result, no duplicated rows).
    The price: the previous version is not kept.
    """
    source_file = raw_dir() / "reference" / f"{name}.csv"
    destination = bronze_dir() / name / f"{name}.parquet"
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = destination.with_name(destination.name + ".tmp")

    try:
        duckdb.execute(
            """
            copy (
                select *,
                       $source as _source_file,
                       $ingested as _ingested_at
                from read_csv($input, all_varchar = true, header = true)
            ) to $output (format parquet)
            """,
            {
                "source": source_file.relative_to(raw_dir()).as_posix(),
                "ingested": datetime.now(UTC).isoformat(),
                "input": str(source_file),
                "output": str(temp),
            },
        )
    except Exception:
        temp.unlink(missing_ok=True)
        raise

    temp.replace(destination)  # replaces the previous Parquet in one go (on macOS/Linux renaming over an existing file is atomic)
    print(f"  reference loaded: {name}")
    return destination


def run() -> None:
    """Entry point of `make bronze`: historian first, then reference tables.

    Exits with code 0 even if there are files in quarantine: a broken file is a warning, not a failure of the run.
    (A programming error does make the program crash, and that is what we want.)
    """
    print("Bronze: historian")
    _, _, quarantined = load_all()

    print("Bronze: reference tables")
    for name in REFERENCE_TABLES:
        load_reference(name)

    if quarantined:
        print(f"ATTENTION: {quarantined} file(s) in quarantine in {quarantine_dir()}. Check the .reason.txt files.")


if __name__ == "__main__":
    run()
