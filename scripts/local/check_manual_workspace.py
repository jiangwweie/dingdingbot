#!/usr/bin/env python3
"""Read-only local project isolation check; never loads .env or contacts a server."""
import json
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit

root = Path(__file__).resolve().parents[2]
branch = subprocess.check_output(['git', '-C', str(root), 'branch', '--show-current'], text=True).strip()
issues = []
if root.name != 'final-manual':
    issues.append('manual work belongs in final-manual')
if branch != 'manual-dev' and not branch.startswith('codex/manual-') and branch != 'codex/app-manual-takeover-v1':
    issues.append('checkout is not a manual product branch')
if Path(sys.prefix).resolve() != (root / '.venv').resolve():
    issues.append('use the manual worktree .venv Python')
url = os.getenv('BRC_TEST_POSTGRES_ADMIN_URL')
if url:
    parsed = urlsplit(url)
    if parsed.hostname != '127.0.0.1' or parsed.port != 55434 or parsed.path != '/postgres':
        issues.append('test database override is outside manual loopback port 55434')
container = os.getenv('BRC_TEST_POSTGRES_CONTAINER_NAME')
if container and container != 'brc-manual-pg':
    issues.append('test container override belongs to another project')
project = os.getenv('COMPOSE_PROJECT_NAME')
if project and project != 'brc-manual-local':
    issues.append('Compose project override belongs to another project')
if any(os.getenv(key) for key in ('TRADING_KERNEL_DATABASE_URL', 'OWNER_CONSOLE_DATABASE_URL')):
    issues.append('unset runtime database variables before local project checks')
print(json.dumps({'workspace': str(root), 'branch': branch, 'status': 'blocked' if issues else 'pass', 'issues': issues}, ensure_ascii=False))
raise SystemExit(1 if issues else 0)
