#!/usr/bin/env python3
"""Step 3: Classify documents and move them to active/constraints/archive."""

import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[4]  # .claude/skills/doc-manager/scripts/ → project root
DOCS_DIR = PROJECT_ROOT / "docs"

ACTIVE_DIR = DOCS_DIR / "active"
CONSTRAINTS_DIR = DOCS_DIR / "constraints"
ARCHIVE_DIR = DOCS_DIR / "archive"

# Directories that already have their own archive/ subdirs
# We skip these to avoid double-moving
SKIP_ARCHIVE_DIRS = {
    'docs/planning/archive',
    'docs/tasks/archive',
    'docs/arch/archive',
    'docs/designs/archive',
    'docs/reports/archive',
    'docs/reviews/archive',
    'docs/diagnostic-reports/archive',
    'docs/v3/archive',
}

# Files that should always be treated as constraints
CONSTRAINT_PATHS = {
    'docs/arch/系统开发规范与红线.md',
}


def ensure_dirs():
    ACTIVE_DIR.mkdir(parents=True, exist_ok=True)
    CONSTRAINTS_DIR.mkdir(parents=True, exist_ok=True)
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)


def get_archive_subdir() -> Path:
    """Get today's archive subdir, create if needed."""
    today = datetime.now(tz=timezone.utc).strftime('%Y-%m-%d')
    subdir = ARCHIVE_DIR / today
    subdir.mkdir(parents=True, exist_ok=True)
    return subdir


def should_skip(path: str) -> bool:
    """Check if file is in a skip list or already in active/constraints."""
    # Already in target dirs
    if path.startswith('docs/active/') or path.startswith('docs/constraints/'):
        return True
    if path.startswith('docs/archive/'):
        return True
    # Skip known archive subdirs
    for skip in SKIP_ARCHIVE_DIRS:
        if path.startswith(skip + '/') or path == skip:
            return True
    return False


def classify(entry: dict) -> str:
    """Return 'active', 'constraints', or 'archive'."""
    if 'error' in entry:
        return 'archive'

    path = entry['path']

    # Permanent constraints
    if entry.get('is_permanent'):
        return 'constraints'

    # Explicit constraint paths
    if path in CONSTRAINT_PATHS:
        return 'constraints'

    # Already marked as constraint in metadata
    if entry.get('is_constraint') and entry.get('final_score', 0) >= 0.1:
        return 'constraints'

    # Score-based classification
    score = entry.get('final_score', 0)
    if score >= 0.3:
        return 'active'
    elif score >= 0.1 and entry.get('alive_ratio', 0) > 0.5:
        # Some refs still alive, keep active
        return 'active'
    else:
        return 'archive'


def move_file(entry: dict, destination: str) -> dict:
    """Move a file and return the move record."""
    src = PROJECT_ROOT / entry['path']
    dst = PROJECT_ROOT / destination

    if not src.exists():
        return {'path': entry['path'], 'status': 'skipped', 'reason': 'file not found'}

    try:
        # If destination exists, add suffix to avoid collision
        if dst.exists():
            stem = dst.stem
            suffix = dst.suffix
            counter = 1
            while dst.exists():
                dst = dst.parent / f"{stem}_{counter}{suffix}"
                counter += 1

        shutil.move(str(src), str(dst))
        return {
            'path': entry['path'],
            'status': 'moved',
            'destination': str(dst.relative_to(PROJECT_ROOT)),
        }
    except Exception as e:
        return {
            'path': entry['path'],
            'status': 'error',
            'reason': str(e),
        }


def main():
    print("Classifying and moving documents ...")
    ensure_dirs()

    validate_file = DOCS_DIR / '.validate-result.json'
    if not validate_file.exists():
        print("ERROR: .validate-result.json not found. Run validate.py first.")
        return

    with open(validate_file, 'r', encoding='utf-8') as f:
        results = json.load(f)

    archive_subdir = get_archive_subdir()
    move_log = []
    counts = {'active': 0, 'constraints': 0, 'archive': 0, 'skipped': 0, 'error': 0}

    for entry in results:
        path = entry['path']

        if should_skip(path):
            counts['skipped'] += 1
            continue

        classification = classify(entry)

        if classification == 'constraints':
            dst = str((CONSTRAINTS_DIR / entry['name']).relative_to(PROJECT_ROOT))
            result = move_file(entry, dst)
            result['classification'] = 'constraints'
            move_log.append(result)
            if result['status'] == 'moved':
                counts['constraints'] += 1
            elif result['status'] == 'error':
                counts['error'] += 1

        elif classification == 'active':
            dst = str((ACTIVE_DIR / entry['name']).relative_to(PROJECT_ROOT))
            result = move_file(entry, dst)
            result['classification'] = 'active'
            move_log.append(result)
            if result['status'] == 'moved':
                counts['active'] += 1
            elif result['status'] == 'error':
                counts['error'] += 1

        else:  # archive
            dst_name = entry['name']
            dst = str((archive_subdir / dst_name).relative_to(PROJECT_ROOT))
            result = move_file(entry, dst)
            result['classification'] = 'archive'
            move_log.append(result)
            if result['status'] == 'moved':
                counts['archive'] += 1
            elif result['status'] == 'error':
                counts['error'] += 1

    # Write move log
    move_log_file = DOCS_DIR / '.move-log.json'
    with open(move_log_file, 'w', encoding='utf-8') as f:
        json.dump({
            'timestamp': datetime.now(tz=timezone.utc).isoformat(),
            'counts': counts,
            'moves': move_log,
        }, f, ensure_ascii=False, indent=2)

    # Print summary
    total_moved = counts['active'] + counts['constraints'] + counts['archive']
    print(f"Classification complete:")
    print(f"  active:       {counts['active']}")
    print(f"  constraints:  {counts['constraints']}")
    print(f"  archived:     {counts['archive']}")
    print(f"  skipped:      {counts['skipped']}")
    print(f"  errors:       {counts['error']}")
    print(f"  total moved:  {total_moved}")
    print(f"Move log → {move_log_file}")


if __name__ == '__main__':
    main()
