#!/usr/bin/env python3
"""Step 2: Validate document references against codebase and git history."""

import json
import subprocess
from collections import defaultdict
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[4]  # .claude/skills/doc-manager/scripts/ → project root
DOCS_DIR = PROJECT_ROOT / "docs"
SRC_DIR = PROJECT_ROOT / "src"


def file_exists(path: str) -> bool:
    """Check if a relative path (from project root) exists."""
    full = PROJECT_ROOT / path
    return full.is_file()


def fuzzy_match(filename: str) -> str | None:
    """Try to find a file with similar name (for renamed files)."""
    if not filename.startswith('src/'):
        filename = 'src/' + filename
    # Try basename match
    base = Path(filename).name
    for f in SRC_DIR.rglob('*.py'):
        if f.name == base or f.name.replace('_', '') == base.replace('_', ''):
            return str(f.relative_to(PROJECT_ROOT))
    # Try partial match
    for f in SRC_DIR.rglob('*.py'):
        rel = str(f.relative_to(PROJECT_ROOT))
        if base in rel or rel in filename:
            return rel
    return None


def get_git_last_modified(file_path: str) -> str | None:
    """Get last modification date from git for a file."""
    try:
        result = subprocess.run(
            ['git', 'log', '-1', '--format=%ai', '--', file_path],
            capture_output=True, text=True, timeout=5, cwd=str(PROJECT_ROOT)
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception:
        pass
    return None


def validate_entry(entry: dict) -> dict:
    """Validate a single document entry."""
    if 'error' in entry:
        entry['alive_ratio'] = 0.0
        entry['git_sync_score'] = 0.0
        entry['final_score'] = 0.0
        entry['refs_alive'] = []
        entry['refs_dead'] = []
        entry['refs_fuzzy'] = []
        return entry

    src_paths = entry.get('src_paths', [])
    class_names = entry.get('class_names', [])
    func_names = entry.get('func_names', [])
    all_refs = src_paths + class_names + func_names

    if not all_refs:
        # No code references - can't validate by code
        # Use age as sole signal
        days = entry.get('mtime_days_ago', 999)
        age_score = max(0, 1.0 - (days / 7.0))  # 7-day decay
        entry['alive_ratio'] = 0.0
        entry['git_sync_score'] = age_score
        entry['final_score'] = age_score
        entry['refs_alive'] = []
        entry['refs_dead'] = []
        entry['refs_fuzzy'] = []
        return entry

    alive = []
    dead = []
    fuzzy = []

    for ref in all_refs:
        if ref.startswith('src/') and file_exists(ref):
            alive.append(ref)
        elif file_exists(ref):
            alive.append(ref)
        else:
            # Try fuzzy match
            matched = fuzzy_match(ref)
            if matched:
                fuzzy.append({'original': ref, 'matched': matched})
                alive.append(ref)  # Count as alive
            else:
                dead.append(ref)

    total = len(all_refs)
    alive_count = len(alive)
    alive_ratio = alive_count / total if total > 0 else 0.0

    # Git sync score: check if code was modified after doc
    doc_mtime = get_git_last_modified(entry['path'])
    code_newer = 0
    code_checked = 0
    for ref in src_paths[:10]:  # Limit to first 10 for speed
        code_mtime = get_git_last_modified(ref)
        if doc_mtime and code_mtime:
            code_checked += 1
            if code_mtime > doc_mtime:
                code_newer += 1

    if code_checked > 0:
        # Lower score = more code changes after doc = more stale
        git_sync_score = 1.0 - (code_newer / code_checked)
    else:
        git_sync_score = 0.5  # Unknown

    # Age decay: 7-day half-life
    days = entry.get('mtime_days_ago', 999)
    age_decay = max(0, 1.0 - (days / 7.0))

    # Final score
    final_score = (0.4 * alive_ratio) + (0.4 * git_sync_score) + (0.2 * age_decay)

    entry['alive_ratio'] = round(alive_ratio, 2)
    entry['git_sync_score'] = round(git_sync_score, 2)
    entry['age_decay'] = round(age_decay, 2)
    entry['final_score'] = round(final_score, 2)
    entry['refs_alive'] = alive
    entry['refs_dead'] = dead
    entry['refs_fuzzy'] = fuzzy

    return entry


def main():
    print("Validating document references ...")

    scan_file = DOCS_DIR / '.scan-result.json'
    if not scan_file.exists():
        print("ERROR: .scan-result.json not found. Run scan.py first.")
        return

    with open(scan_file, 'r', encoding='utf-8') as f:
        results = json.load(f)

    print(f"Validating {len(results)} documents ...")
    validated = []
    for i, entry in enumerate(results):
        v = validate_entry(entry)
        validated.append(v)
        if (i + 1) % 50 == 0:
            print(f"  {i + 1}/{len(results)} done")

    output = DOCS_DIR / '.validate-result.json'
    with open(output, 'w', encoding='utf-8') as f:
        json.dump(validated, f, ensure_ascii=False, indent=2)

    # Summary
    alive_count = sum(1 for v in validated if v.get('final_score', 0) >= 0.3)
    constraint_count = sum(1 for v in validated if v.get('is_constraint'))
    dead_count = len(validated) - alive_count

    print(f"Validation complete: {alive_count} alive, {dead_count} likely stale, {constraint_count} constraints")
    print(f"Results → {output}")


if __name__ == '__main__':
    main()
