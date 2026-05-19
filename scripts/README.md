# Scripts Reset

Historical scripts were archived on 2026-04-29 to reduce research and migration noise.

Archived material:
- `archive/2026-04-29-pre-live-safe-replan/scripts/`

Only reintroduce scripts here when they serve the new baseline directly.

## Runtime Safety Seeding

- `seed_gks_state.py`: creates or updates the single PG Global Kill Switch row.
  It defaults to `active=True`, so seeding does not accidentally allow new
  entries. Use `--inactive` only for non-live/testnet smoke after explicit Owner
  approval and with the startup trading guard/manual arm process still in place.
