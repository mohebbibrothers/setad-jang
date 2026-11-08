#!/usr/bin/env python
# ============================================================================
#  db_dump.py - logical database dump that uses the SAME connection as the app
#
#  WHY THIS EXISTS
#  ---------------
#  On this cPanel host the `mariadb-dump` CLI answered
#      ERROR 1045 (28000): Access denied for user 'besatme_besat'@'localhost'
#  while the Django site itself was reading the very same database happily with
#  the very same user/password. Any external client brings its own baggage:
#  option files (~/.my.cnf), a different driver, a different socket, a different
#  password precedence. A backup tool must not re-implement authentication.
#
#  So this dumper asks Django for the connection, uses that cursor, and writes a
#  portable SQL file itself: schema + data, gzip, with a self-verification pass.
#
#  WHAT IT PRODUCES
#      SET FOREIGN_KEY_CHECKS=0;
#      DROP TABLE IF EXISTS `x`;  CREATE TABLE `x` (...);
#      INSERT INTO `x` VALUES (...),(...);
#      ...
#      SET FOREIGN_KEY_CHECKS=1;
#      -- end of dump
#
#  USAGE (from the app root)
#      <venv>/python scripts/db_dump.py --out ~/backups/db-2026-11-08.sql.gz
#      <venv>/python scripts/db_dump.py --verify --out <file>   # integrity pass
#      <venv>/python scripts/db_dump.py --no-gzip --out /tmp/x.sql
#
#  SAFETY
#      - read-only on the source database (single consistent snapshot)
#      - per-table failures are reported and make the exit code non-zero
#      - the written file is re-read and checked (tables, end marker, gzip CRC)
# ============================================================================
"""Django-native logical dump (MySQL/MariaDB + SQLite)."""

from __future__ import annotations

import argparse
import gzip
import io
import os
import sys
import time
from pathlib import Path

DEFAULT_SETTINGS = "config.settings.production"
ROWS_PER_STATEMENT = 200
BYTES_PER_STATEMENT = 1_000_000
END_MARKER = "-- end of dump"


# --------------------------------------------------------------------------- setup
def project_root() -> str:
    """Directory that holds manage.py.

    When this file is executed directly (`python scripts/db_dump.py`) Python
    puts `scripts/` on sys.path, not the project root, so `config.settings` is
    not importable. Walk up from the script location and fall back to the
    current working directory.
    """
    candidates = []
    here = Path(__file__).resolve().parent
    for parent in [here, *here.parents]:
        candidates.append(parent)
    candidates.append(Path.cwd())
    for candidate in candidates:
        if (candidate / "manage.py").exists():
            return str(candidate)
    return str(Path.cwd())


def boot_django(settings: str) -> None:
    root = project_root()
    if root not in sys.path:
        sys.path.insert(0, root)
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", settings)
    import django

    django.setup()


def redact(text: str) -> str:
    """Never echo secrets (driver errors can embed the connection string)."""
    lowered = text.lower()
    if "password" in lowered or "pwd" in lowered:
        return "*** connection error redacted (credentials) ***"
    return text


# ---------------------------------------------------------------------- escaping
def sql_literal(value, engine: str) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, (bytes, bytearray, memoryview)):
        blob = bytes(value)
        if engine == "sqlite":
            return "X'%s'" % blob.hex()
        return "0x%s" % blob.hex() if blob else "''"
    if isinstance(value, (dict, list, tuple)):
        import json

        value = json.dumps(value, ensure_ascii=False, default=str)
    text = str(value)
    if engine == "sqlite":
        return "'" + text.replace("'", "''") + "'"
    # MySQL/MariaDB: backslash escapes are active, escape them all.
    text = (
        text.replace("\\", "\\\\")
        .replace("'", "\\'")
        .replace("\0", "\\0")
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\x1a", "\\Z")
    )
    return "'" + text + "'"


def quote_table(name: str, engine: str) -> str:
    if engine == "sqlite":
        return '"' + name.replace('"', '""') + '"'
    return "`" + name.replace("`", "``") + "`"


# ------------------------------------------------------------------------- dump
def table_names(cursor, engine: str) -> list[str]:
    if engine == "sqlite":
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")
    else:
        cursor.execute("SHOW FULL TABLES")
    return [row[0] for row in cursor.fetchall() if row[0]]


def create_statement(cursor, table: str, engine: str) -> str:
    if engine == "sqlite":
        cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=%s", [table])
        row = cursor.fetchone()
        return (row[0] or "") + ";"
    cursor.execute(f"SHOW CREATE TABLE {quote_table(table, engine)}")
    row = cursor.fetchone()
    ddl = row[1].rstrip().rstrip(";")
    return ddl + ";"


def write_rows(out, cursor, table: str, engine: str) -> int:
    """Stream the table in chunks; returns the row count written."""
    qt = quote_table(table, engine)
    total = 0
    buffered: list[str] = []
    buffered_bytes = 0

    def flush() -> None:
        nonlocal buffered, buffered_bytes
        if not buffered:
            return
        out.write(f"INSERT INTO {qt} VALUES\n")
        out.write(",\n".join(buffered))
        out.write(";\n")
        buffered = []
        buffered_bytes = 0

    try:
        stream = cursor.chunked_cursor()
    except AttributeError:  # pragma: no cover - non-Django cursor
        stream = cursor
    stream.execute(f"SELECT * FROM {qt}")
    while True:
        rows = stream.fetchmany(500)
        if not rows:
            break
        for row in rows:
            literal = "(" + ",".join(sql_literal(v, engine) for v in row) + ")"
            buffered.append(literal)
            buffered_bytes += len(literal)
            total += 1
            if len(buffered) >= ROWS_PER_STATEMENT or buffered_bytes >= BYTES_PER_STATEMENT:
                flush()
    flush()
    return total


def dump(settings: str, out_path: Path, gzip_output: bool, tables: list[str] | None) -> int:
    boot_django(settings)
    from django.db import connection

    engine = "sqlite" if "sqlite" in connection.settings_dict["ENGINE"] else "mysql"
    name = connection.settings_dict.get("NAME") or "?"
    host = connection.settings_dict.get("HOST") or "local"
    user = connection.settings_dict.get("USER") or "-"

    out_path.parent.mkdir(parents=True, exist_ok=True)
    failures = 0
    counts: dict[str, int] = {}

    raw = open(out_path, "wb")
    binary = gzip.GzipFile(filename="", mode="wb", fileobj=raw, compresslevel=9) if gzip_output else raw
    text = io.TextIOWrapper(binary, encoding="utf-8", newline="\n", write_through=True)

    started = time.strftime("%Y-%m-%d %H:%M:%S")
    text.write(f"-- besat logical dump v1 (scripts/db_dump.py)\n")
    text.write(f"-- engine : {engine}\n")
    text.write(f"-- db     : {name}\n")
    text.write(f"-- user   : {user} @ {host}\n")
    text.write(f"-- started: {started}\n")

    with connection.cursor() as cursor:
        if engine != "sqlite":
            # one consistent snapshot, no locking of the live site
            try:
                cursor.execute("SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ")
                cursor.execute("START TRANSACTION WITH CONSISTENT SNAPSHOT")
                text.write("-- snapshot: REPEATABLE READ / consistent\n")
            except Exception as exc:  # noqa: BLE001
                text.write(f"-- snapshot: unavailable ({exc})\n")
            text.write("SET NAMES utf8mb4;\nSET FOREIGN_KEY_CHECKS=0;\n\n")
        else:
            text.write("PRAGMA foreign_keys=OFF;\n\n")

        names = table_names(cursor, engine)
        if tables:
            wanted = {t.lower() for t in tables}
            names = [n for n in names if n.lower() in wanted]
        text.write(f"-- tables: {len(names)}\n\n")

        for table in names:
            try:
                ddl = create_statement(cursor, table, engine)
                text.write(f"\n-- table {table}\n")
                text.write(f"DROP TABLE IF EXISTS {quote_table(table, engine)};\n")
                text.write(ddl + "\n")
                rows = write_rows(text, cursor, table, engine)
                counts[table] = rows
                print(f"  [ok]   {table:<40} {rows} row(s)", file=sys.stderr)
            except Exception as exc:  # noqa: BLE001
                failures += 1
                print(f"  [FAIL] {table}: {redact(str(exc))}", file=sys.stderr)

        if engine != "sqlite":
            text.write("\nSET FOREIGN_KEY_CHECKS=1;\n")
        else:
            text.write("\nPRAGMA foreign_keys=ON;\n")
        text.write(f"-- tables: {len(counts)} | rows: {sum(counts.values())}\n")
        text.write(END_MARKER + "\n")

    text.flush()
    text.detach()  # do not close the gzip stream through the wrapper
    if gzip_output:
        binary.close()  # writes the gzip trailer (CRC)
    raw.close()

    size = out_path.stat().st_size
    print(f"  [ok] wrote {out_path} ({size/1048576:.2f} MB, {len(counts)} tables, {sum(counts.values())} rows)", file=sys.stderr)
    if failures:
        print(f"  [!!] {failures} table(s) failed - the dump is INCOMPLETE", file=sys.stderr)
        return 1
    return 0


# ----------------------------------------------------------------------- verify
def verify(path: Path) -> int:
    """Re-read the archive: gzip CRC, table count, end marker, sanity."""
    problems = 0
    try:
        opener = gzip.open if path.suffix == ".gz" else open
        with opener(path, "rt", encoding="utf-8") as fh:
            creates = 0
            inserts = 0
            end = False
            declared_tables = None
            for line in fh:
                if line.upper().startswith("CREATE TABLE"):
                    creates += 1
                elif line.startswith("INSERT INTO"):
                    inserts += 1
                elif line.startswith("-- tables:") and declared_tables is None:
                    try:
                        declared_tables = int(line.split(":")[1].split("|")[0])
                    except (IndexError, ValueError):
                        declared_tables = None
                elif line.startswith(END_MARKER):
                    end = True
    except Exception as exc:  # noqa: BLE001
        print(f"  [!!] cannot read {path}: {exc}", file=sys.stderr)
        return 1

    print(f"  [..] verify: {path.name} -> {creates} CREATE TABLE, {inserts} INSERT statement(s)", file=sys.stderr)
    if declared_tables is None or creates != declared_tables:
        print(f"  [!!] table count mismatch (header says {declared_tables}, file has {creates})", file=sys.stderr)
        problems += 1
    if not end:
        print("  [!!] end marker missing - the file is truncated", file=sys.stderr)
        problems += 1
    if creates == 0:
        print("  [!!] no schema found - this is not a usable backup", file=sys.stderr)
        problems += 1
    if problems == 0:
        print("  [ok] archive is complete and readable", file=sys.stderr)
    return 1 if problems else 0


# ------------------------------------------------------------------------- main
def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Django-native logical database dump")
    parser.add_argument("--out", help="output file (default: stdout)")
    parser.add_argument("--no-gzip", action="store_true", help="write plain SQL")
    parser.add_argument("--tables", nargs="*", help="only these tables")
    parser.add_argument("--settings", default=os.environ.get("DJANGO_SETTINGS_MODULE", DEFAULT_SETTINGS))
    parser.add_argument("--verify", action="store_true", help="only verify an existing dump")
    args = parser.parse_args(argv)

    if args.verify:
        if not args.out:
            print("--verify needs --out <file>", file=sys.stderr)
            return 2
        return verify(Path(args.out).expanduser())

    if not args.out:
        print("--out <file> is required", file=sys.stderr)
        return 2
    out_path = Path(args.out).expanduser()
    return dump(args.settings, out_path, not args.no_gzip, args.tables)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
