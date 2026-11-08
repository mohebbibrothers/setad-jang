#!/usr/bin/env python
# ============================================================================
#  media_audit.py - does every file the database points at actually exist?
#
#  WHY THIS EXISTS
#  ---------------
#  After the host migration some sponsored logos, an LMS course cover and a
#  criminal-profile photo returned 404 while their rows were still in the
#  database. Nothing in the app notices: `<img src>` just renders broken. The
#  site therefore needs a tool that walks EVERY FileField/ImageField, checks the
#  file on disk, and can put missing files back from a media backup.
#
#  WHAT IT CHECKS
#      - every model field that is a FileField/ImageField (via Django's meta,
#        so new apps/models are covered automatically)
#      - referenced -> exists? (through the model's own storage, so S3/whatever
#        would work too)
#      - reports per-model counts, total missing, and the first N examples
#      - --orphans: files on disk that NO row references (safe cleanup source)
#
#  USAGE (from the app root)
#      <venv>/python scripts/media_audit.py
#      <venv>/python scripts/media_audit.py --limit 30 --json /tmp/media.json
#      <venv>/python scripts/media_audit.py --restore-from ~/backups/media-2026-11-01.tar.gz
#      <venv>/python scripts/media_audit.py --orphans
#
#  RESTORE SAFETY
#      - never overwrites an existing file
#      - never deletes anything
#      - only extracts paths that a database row actually references
#      - dry-run unless --apply is given together with --restore-from
# ============================================================================
"""Media integrity audit + restore (Django-native)."""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import sys
import tarfile
from collections import defaultdict
from pathlib import Path

DEFAULT_SETTINGS = "config.settings.production"


# --------------------------------------------------------------------------- setup
def project_root() -> str:
    here = Path(__file__).resolve().parent
    for candidate in [here, *here.parents]:
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


def file_fields() -> list[tuple[object, object]]:
    """Every concrete model field that stores a file (auto-discovered)."""
    from django.apps import apps
    from django.db.models import FileField

    pairs = []
    for model in apps.get_models():
        for field in model._meta.get_fields():
            if isinstance(field, FileField) and getattr(field, "concrete", False):
                pairs.append((model, field))
    return pairs


def referenced(pairs) -> dict[str, list[str]]:
    """{model.field: [names that the DB references]}, deduplicated."""
    out: dict[str, list[str]] = defaultdict(list)
    for model, field in pairs:
        key = f"{model._meta.label}.{field.name}"
        try:
            qs = model._default_manager.exclude(**{field.name: ""}).exclude(
                **{f"{field.name}__isnull": True}
            )
            names = qs.values_list(field.name, flat=True).iterator(chunk_size=1000)
            seen = set()
            for name in names:
                if name and name not in seen:
                    seen.add(name)
                    out[key].append(name)
        except Exception as exc:  # table missing / db error: report, do not crash
            print(f"  [!!] {key}: cannot read rows ({exc})", file=sys.stderr)
    return dict(out)


# ------------------------------------------------------------------------- audit
def audit(settings: str, limit: int, want_orphans: bool) -> tuple[int, dict]:
    boot_django(settings)
    from django.conf import settings as dj_settings

    media_root = getattr(dj_settings, "MEDIA_ROOT", None)
    print(f"  media root: {media_root}", file=sys.stderr)

    pairs = file_fields()
    print(
        f"  scanned    : {len(pairs)} file field(s) across {len({m._meta.label for m, _ in pairs})} model(s)",
        file=sys.stderr,
    )

    refs = referenced(pairs)
    field_by_key = {f"{m._meta.label}.{f.name}": f for m, f in pairs}

    total_refs = 0
    missing_by_field: dict[str, list[str]] = {}
    for key, names in refs.items():
        field = field_by_key[key]
        storage = field.storage
        miss = []
        for name in names:
            total_refs += 1
            try:
                if not storage.exists(name):
                    miss.append(name)
            except Exception:  # unreadable path -> treat as missing
                miss.append(name)
        if miss:
            missing_by_field[key] = miss

    missing_total = sum(len(v) for v in missing_by_field.values())
    print("", file=sys.stderr)
    for key in sorted(refs):
        n = len(refs[key])
        m = len(missing_by_field.get(key, []))
        flag = "[OK]" if m == 0 else "[!!]"
        print(f"  {flag} {key:<52} {n:>5} referenced, {m:>3} missing", file=sys.stderr)
        if m and limit:
            for name in missing_by_field[key][:limit]:
                print(f"         missing: {name}", file=sys.stderr)

    orphans: list[str] = []
    if want_orphans and media_root and Path(media_root).is_dir():
        all_referenced = {n for names in refs.values() for n in names}
        root = Path(media_root)
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            rel = path.relative_to(root).as_posix()
            if rel not in all_referenced:
                orphans.append(rel)
        print("", file=sys.stderr)
        print(f"  [--] orphan files on disk: {len(orphans)}", file=sys.stderr)
        for name in orphans[:limit]:
            print(f"         orphan : {name}", file=sys.stderr)

    print("", file=sys.stderr)
    print(f"  TOTAL: {total_refs} referenced file(s), {missing_total} missing", file=sys.stderr)
    if missing_total:
        print(
            "  next: <venv>/python scripts/media_audit.py --restore-from <media-backup.tar.gz> --apply",
            file=sys.stderr,
        )
    else:
        print("  [ok] every referenced file exists on disk", file=sys.stderr)

    summary = {
        "media_root": str(media_root),
        "referenced": total_refs,
        "missing": {k: v for k, v in missing_by_field.items()},
        "orphans": orphans,
    }
    return (1 if missing_total else 0), summary


# ----------------------------------------------------------------------- restore
def build_index(archive: Path) -> dict[str, str]:
    """Map 'relative/path' -> tar member name, tolerating a leading media/ dir."""
    index: dict[str, str] = {}
    with tarfile.open(archive, "r:*") as tar:
        for member in tar.getmembers():
            if not member.isfile():
                continue
            name = member.name.lstrip("./")
            # strip a leading "media/" or "public/" wrapper if present
            parts = name.split("/")
            for start in range(len(parts)):
                candidate = "/".join(parts[start:])
                index.setdefault(candidate, name)
    return index


def restore(settings: str, archive: Path, apply_changes: bool, limit: int = 0) -> int:
    boot_django(settings)
    from django.conf import settings as dj_settings

    media_root = Path(dj_settings.MEDIA_ROOT)
    if not media_root.is_dir():
        print(f"  [!!] MEDIA_ROOT not found: {media_root}", file=sys.stderr)
        return 2
    if not archive.is_file():
        print(f"  [!!] archive not found: {archive}", file=sys.stderr)
        return 2

    pairs = file_fields()
    refs = referenced(pairs)
    field_by_key = {f"{m._meta.label}.{f.name}": f for m, f in pairs}
    missing: list[tuple[str, str]] = []  # (name, model.field)
    for key, names in refs.items():
        storage = field_by_key[key].storage
        for name in names:
            try:
                exists = storage.exists(name)
            except Exception:
                exists = False
            if not exists:
                missing.append((name, key))

    print(f"  missing referenced files: {len(missing)}", file=sys.stderr)
    if not missing:
        return 0

    index = build_index(archive)
    print(f"  archive index: {len(index)} file(s) in {archive.name}", file=sys.stderr)

    restored = 0
    not_in_archive = 0
    for name, key in missing:
        member = index.get(name)
        if not member:
            not_in_archive += 1
            print(f"  [--] not in archive: {name}  ({key})", file=sys.stderr)
            continue
        target = media_root / name
        if target.exists():
            continue
        print(f"  [{'restore' if apply_changes else 'dry-run'}] {name}", file=sys.stderr)
        if apply_changes:
            target.parent.mkdir(parents=True, exist_ok=True)
            with tarfile.open(archive, "r:*") as tar:
                src = tar.extractfile(member)
                if src is None:
                    print(f"  [!!] cannot read {member} from archive", file=sys.stderr)
                    continue
                target.write_bytes(src.read())
            with contextlib.suppress(OSError):
                target.chmod(0o644)
        restored += 1
        if limit and restored >= limit:
            print(f"  [..] stopped after {limit} (limit)", file=sys.stderr)
            break

    verb = "restored" if apply_changes else "restorable"
    print("", file=sys.stderr)
    print(f"  {verb}: {restored} | not found in archive: {not_in_archive}", file=sys.stderr)
    if not apply_changes and restored:
        print("  re-run with --apply to write the files", file=sys.stderr)
    if not_in_archive:
        print(
            "  those files must come from the old host (they are not in this backup)",
            file=sys.stderr,
        )
    return 0 if not_in_archive == 0 else 1


# -------------------------------------------------------------------------- main
def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="media integrity audit / restore")
    parser.add_argument(
        "--settings", default=os.environ.get("DJANGO_SETTINGS_MODULE", DEFAULT_SETTINGS)
    )
    parser.add_argument("--limit", type=int, default=10, help="examples printed per model")
    parser.add_argument("--json", help="write the report as JSON to this path")
    parser.add_argument("--orphans", action="store_true", help="also list files no row references")
    parser.add_argument("--restore-from", help="media tar.gz to restore missing files from")
    parser.add_argument(
        "--apply", action="store_true", help="with --restore-from: really write files"
    )
    args = parser.parse_args(argv)

    if args.restore_from:
        return restore(args.settings, Path(args.restore_from).expanduser(), args.apply)

    code, summary = audit(args.settings, args.limit, args.orphans)
    if args.json:
        Path(args.json).expanduser().write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"  json report: {args.json}", file=sys.stderr)
    return code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
