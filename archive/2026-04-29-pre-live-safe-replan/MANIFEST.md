# Archive Manifest

Date: 2026-04-29

Purpose:
- Preserve pre-live-safe planning, tests, scripts, and generated artifacts.
- Reset the workspace so new planning starts from `docs/gpt/` and the current codebase.

Git anchors:
- Pre-merge tag: `dev-before-pg-merge-20260429`
- Post-merge baseline tag: `dev-live-safe-baseline-20260429`
- Merge result: `codex/pg-full-migration` was already contained in `dev`, so the merge was a no-op.

Moved into this archive:
- `docs/` contents except `docs/gpt/`
- entire `tests/`
- entire `scripts/`
- generated artifacts and logs:
  - `htmlcov/`
  - `logs/`
  - `reports/`
  - `.coverage`
  - `.pytest_cache/`
  - `.DS_Store`
  - `.backend.pid`
  - `.frontend.pid`
  - `backend.log`
  - `frontend.log`
  - `config_backup_20260414_230534.yaml`
  - `run_tests.sh`

Notes:
- Files were moved, not deleted, so historical material remains searchable under this archive path.
- No tests were executed as part of this reset.
