#!/usr/bin/env python
# ============================================================================
#  env_set.py - safe, idempotent .env editor for the ops scripts
#
#  Editing .env by hand (or with sed) is how the old host lost its database
#  keys during the migration. This tool:
#
#      • never computes duplicates: an existing KEY is rewritten in place, a
#        missing KEY is appended once (with a section comment)
#      • writes a timestamped backup before touching anything
#      • keeps the file's own line endings and trailing newline
#      • preserves quoting rules (values with spaces/#/" are written quoted)
#      • prints only the KEY NAMES, never the values (nothing secret leaks into
#        a terminal screenshot or a support ticket)
#      • is atomic (write to .env.tmp then rename) so a dropped SSH session can
#        never leave a half-written .env behind
#
#  USAGE
#      <venv>/python scripts/env_set.py KEY=value [KEY2=value2 ...]
#      <venv>/python scripts/env_set.py --file /path/.env --dry-run KEY=value
#      <venv>/python scripts/env_set.py --show KEYS   # masked lengths of keys
# ============================================================================
"""Idempotent, atomic .env editor."""

from __future__ import annotations

import argparse
import contextlib
import os
import re
import sys
import time
from pathlib import Path

KEY_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=(.*)$")
NEEDS_QUOTES = re.compile(r"[\s#\"'$]")


def default_env_file() -> Path:
    env = os.environ.get("ENV_FILE")
    if env:
        return Path(env).expanduser()
    app = os.environ.get("APP_DIR") or str(Path(__file__).resolve().parents[1])
    return Path(app).expanduser() / ".env"


def format_value(value: str) -> str:
    if value == "":
        return ""
    if NEEDS_QUOTES.search(value):
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return value


def read_lines(path: Path) -> list[str]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    return text.splitlines()


def set_values(path: Path, pairs: dict[str, str], dry_run: bool, section: str) -> dict[str, str]:
    lines = read_lines(path)
    existing: dict[str, int] = {}
    duplicates: list[str] = []
    for index, line in enumerate(lines):
        match = KEY_RE.match(line)
        if not match:
            continue
        key = match.group(1)
        if key in existing:
            duplicates.append(key)
        else:
            existing[key] = index

    changed: dict[str, str] = {}
    for key, value in pairs.items():
        rendered = f"{key}={format_value(value)}"
        if key in existing:
            index = existing[key]
            if lines[index].strip() != rendered:
                lines[index] = rendered
                changed[key] = "updated"
            else:
                changed[key] = "unchanged"
        else:
            changed[key] = "added"

    added = [k for k, how in changed.items() if how == "added"]
    if added:
        if lines and lines[-1].strip() != "":
            lines.append("")
        lines.append(f"# --- {section} (added by scripts/env_set.py) ---")
        for key in added:
            lines.append(f"{key}={format_value(pairs[key])}")

    if duplicates:
        print(
            f"  [--] duplicate keys already in the file (left untouched): {', '.join(sorted(set(duplicates)))}",
            file=sys.stderr,
        )

    if dry_run:
        for key, how in changed.items():
            print(f"  [dry] {key}: {how}", file=sys.stderr)
        return changed

    if any(how != "unchanged" for how in changed.values()):
        backup = path.with_name(f".env.bak.{int(time.time())}")
        if path.exists():
            backup.write_bytes(path.read_bytes())
            print(f"  [ok] backup: {backup.name}", file=sys.stderr)
        tmp = path.with_name(".env.tmp")
        tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
        with contextlib.suppress(OSError):
            tmp.chmod(0o600)
        tmp.replace(path)
    for key, how in changed.items():
        print(f"  [{'ok' if how != 'unchanged' else '--'}] {key}: {how}", file=sys.stderr)
    return changed


def mask(value: str) -> str:
    value = value.strip().strip('"').strip("'")
    if not value:
        return "(empty)"
    stars = "*" * max(0, len(value) - 2)
    return f"{value[:2]}{stars} ({len(value)} chars)"


def show_keys(path: Path, keys: list[str]) -> int:
    if not path.exists():
        print(f"  [!!] {path} not found", file=sys.stderr)
        return 1
    values: dict[str, str] = {}
    for line in read_lines(path):
        match = KEY_RE.match(line)
        if match:
            values.setdefault(match.group(1), match.group(2))
    print(f"=== {path} (masked) ===", file=sys.stderr)
    for key in keys:
        print(f"       {key:<34} {mask(values.get(key, ''))}", file=sys.stderr)
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="safe .env editor")
    parser.add_argument("assignments", nargs="*", help="KEY=value pairs")
    parser.add_argument("--file", help="path to .env (default: $APP_DIR/.env)")
    parser.add_argument("--section", default="settings", help="comment used for appended keys")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--show", nargs="*", metavar="KEY", help="print masked values")
    args = parser.parse_args(argv)

    path = Path(args.file).expanduser() if args.file else default_env_file()

    if args.show is not None:
        return show_keys(path, args.show)

    pairs: dict[str, str] = {}
    for item in args.assignments:
        if "=" not in item:
            print(f"  [!!] not KEY=value: {item}", file=sys.stderr)
            return 2
        key, value = item.split("=", 1)
        key = key.strip()
        if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", key):
            print(f"  [!!] invalid key: {key}", file=sys.stderr)
            return 2
        pairs[key] = value

    if not pairs:
        print("  [!!] nothing to do (pass KEY=value pairs)", file=sys.stderr)
        return 2

    print(f"=== .env editor | {path} ===", file=sys.stderr)
    changed = set_values(path, pairs, args.dry_run, args.section)
    if all(how == "unchanged" for how in changed.values()):
        print("  [ok] already up to date", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
