#!/usr/bin/env python3
"""Step 1: Scan all .md files in docs/ and extract metadata."""

import json
import os
import re
import sys
from pathlib import Path
from datetime import datetime, timezone


PROJECT_ROOT = Path(__file__).resolve().parents[4]  # .claude/skills/doc-manager/scripts/ → project root
DOCS_DIR = PROJECT_ROOT / "docs"

# Regex patterns
SRC_PATH_RE = re.compile(r'(?:src/[a-zA-Z0-9_/\-]+\.py)')
CLASS_RE = re.compile(r'(?:class|Class)\s+([A-Z][a-zA-Z0-9_]+)')
FUNC_RE = re.compile(r'(?:def|function)\s+([a-z_][a-zA-Z0-9_]+)')
DOC_REF_RE = re.compile(r'[\w\-]+\.md')
DATE_RE = re.compile(r'(\d{4}[-/.]\d{2}[-/.]\d{2})')

CONSTRAINT_KEYWORDS = ['规范', '必须', '禁止', '红线', '约束', 'mandatory', 'constraint', 'rule', 'template', '模板']

# Permanent paths - always constraints
PERMANENT_PATHS = [
    'CLAUDE.md',
    'README.md',
]

# Files that are the active planning trio
PLANNING_FILES = [
    'docs/planning/task_plan.md',
    'docs/planning/findings.md',
    'docs/planning/progress.md',
]


def extract_metadata(file_path: Path) -> dict:
    """Extract metadata from a single .md file without reading full content."""
    rel_path = str(file_path.relative_to(PROJECT_ROOT))
    stat = file_path.stat()

    try:
        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
            # Read first 200 lines for metadata extraction
            preview = []
            for i, line in enumerate(f):
                if i >= 200:
                    break
                preview.append(line)
            content_preview = ''.join(preview)
    except Exception:
        content_preview = ''

    # Extract references
    src_paths = list(set(SRC_PATH_RE.findall(content_preview)))
    class_names = list(set(CLASS_RE.findall(content_preview)))
    func_names = list(set(FUNC_RE.findall(content_preview)))
    doc_refs = list(set(DOC_REF_RE.findall(content_preview)))
    dates = DATE_RE.findall(content_preview)

    # Check constraint keywords
    is_constraint = any(kw in content_preview for kw in CONSTRAINT_KEYWORDS)

    # Check if it's a permanent file
    is_permanent = rel_path in PLANNING_FILES or file_path.name in PERMANENT_PATHS

    # Check if in known constraint directories
    in_constraint_dir = any(
        rel_path.startswith(prefix)
        for prefix in ['docs/templates/', 'docs/arch/', 'docs/workflows/']
    )

    # File size
    size_kb = stat.st_size / 1024

    # Modification time
    mtime = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)

    # Extract headings for topic indexing
    headings = re.findall(r'^(#{1,3})\s+(.+)$', content_preview, re.MULTILINE)
    topics = [h[1].strip() for h in headings[:10]]

    return {
        'path': rel_path,
        'name': file_path.name,
        'size_kb': round(size_kb, 1),
        'mtime': mtime.isoformat(),
        'mtime_days_ago': (datetime.now(tz=timezone.utc) - mtime).days,
        'src_paths': src_paths,
        'class_names': class_names,
        'func_names': func_names,
        'doc_refs': doc_refs,
        'dates': dates,
        'is_constraint': is_constraint or in_constraint_dir or is_permanent,
        'is_permanent': is_permanent or in_constraint_dir,
        'topics': topics,
        'headings': [h[1].strip() for h in headings[:5]],
    }


def main():
    print(f"Scanning {DOCS_DIR} ...")

    md_files = list(DOCS_DIR.rglob('*.md'))
    print(f"Found {len(md_files)} markdown files")

    results = []
    for fp in md_files:
        # Skip archive dirs, INDEX.json, and internal files
        rel = str(fp.relative_to(PROJECT_ROOT))
        if '/.scan-result' in rel or '/.validate-result' in rel or '/.move-log' in rel:
            continue
        if rel == 'docs/INDEX.json':
            continue

        try:
            meta = extract_metadata(fp)
            results.append(meta)
        except Exception as e:
            print(f"  WARN: failed to scan {rel}: {e}")
            results.append({
                'path': rel,
                'name': fp.name,
                'error': str(e),
                'mtime_days_ago': 999,
                'src_paths': [],
                'class_names': [],
                'func_names': [],
                'is_constraint': False,
                'is_permanent': False,
            })

    output = DOCS_DIR / '.scan-result.json'
    with open(output, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"Scan complete: {len(results)} files → {output}")
    return results


if __name__ == '__main__':
    main()
