# Owner Console Deployment Assets

## Boundary

The Owner Console is a same-origin HTTPS surface with read-only analysis and a
bounded Owner control plane. It has its own
PostgreSQL login, Python virtual environment, systemd service, resource slice,
Unix Socket, and Nginx locations. It does not load exchange credentials and it
does not change the four Trading Kernel worker units.

Task 25 owns actual Tokyo installation. Do not apply these assets merely by
checking out this directory.

## PostgreSQL Read Role

Apply the role file as the database owner against the exact BRC database:

```bash
psql --dbname "$TARGET_DATABASE" --file deploy/owner-console/postgresql/owner-console-read-role.sql
psql --dbname "$TARGET_DATABASE"
```

Inside `psql`, set the password interactively so it does not enter shell
history:

```text
\password brc_owner_console
```

Verify the final login through the Owner Console identity:

```sql
SHOW transaction_read_only;
SHOW statement_timeout;
SELECT current_user;
```

Expected values are `on`, `3s`, and `brc_owner_console`. Build the
`postgresql+asyncpg://` DSN with a URL-encoded password, then enter that DSN
only through the encrypted-credential prompt described below.

## Independent Python Environment And Frontend

From the reviewed release directory:

```bash
python3 -m venv .venv-owner-console
.venv-owner-console/bin/pip install --requirement requirements-owner-console.txt
pnpm --dir frontend/owner-console install --frozen-lockfile
pnpm --dir frontend/owner-console build
```

The four Kernel workers continue to use `.venv`. Nginx serves only the built
`frontend/owner-console/dist` directory, so Node.js is not a runtime process.

## systemd Credentials

Create `/etc/brc/owner-console-credentials` as root with mode `0700` and store
exactly these seven root-owned mode-`0600` values. Tokyo uses systemd 249, so
the unit consumes them with `LoadCredential=` and never places them in an
environment file or process arguments.

| Credential name | Source file |
| --- | --- |
| `owner_username` | `owner_username` |
| `owner_password_hash` | `owner_password_hash` |
| `owner_totp_seed` | `owner_totp_seed` |
| `session_signing_key` | `session_signing_key` |
| `database_dsn` | `database_dsn` |
| `control_database_dsn` | `control_database_dsn` |
| `account_id` | `account_id` |

The password hash
must be Argon2id, the TOTP seed must be valid Base32, and the Session signing
key must be independently generated random material. Never place any of these
values in the repository, an environment file, process arguments, or logs.

## systemd Installation

Install only the Owner Console units:

```bash
sudo install -o root -g root -m 0644 deploy/owner-console/systemd/brc-owner-console.slice /etc/systemd/system/brc-owner-console.slice
sudo install -o root -g root -m 0644 deploy/owner-console/systemd/brc-owner-console-api.service /etc/systemd/system/brc-owner-console-api.service
sudo systemd-analyze verify /etc/systemd/system/brc-owner-console.slice /etc/systemd/system/brc-owner-console-api.service
sudo systemctl daemon-reload
sudo systemctl enable --now brc-owner-console-api.service
```

The API listens only on `/run/brc-owner-console/api.sock` and is bounded to
25% CPU, 256 MiB memory, and 32 tasks.

## Nginx Installation

Install `00-brc-owner-console-limit.conf` in the Nginx `http` context and
include `owner-console.locations.conf` only inside the existing HTTPS server
block for the public Owner Console domain. Do not create a second cleartext
application server.

```bash
sudo nginx -t
sudo systemctl reload nginx
```

The locations serve the SPA with `no-store`, serve fingerprinted assets with a
one-year immutable cache, proxy `/api/` through the Unix Socket, and apply the
login rate limit only to the login endpoint.

## Release Preservation

Regular Kernel release installation conditionally copies these two untracked
runtime artifacts from `/opt/brc/current` into the new release before the
current symlink changes:

```text
.venv-owner-console
frontend/owner-console/dist
```

If neither artifact exists, a Kernel-only release continues normally. This
preservation rule does not add the Owner Console unit to the four-worker
deployment membership and does not start or reload Owner Console services.

## Production DML Snapshot For Local Acceptance

The snapshot path is read-only on Tokyo and destructive only inside a guarded
localhost database named `brc_owner_console_test_<12 lowercase hex>`. It does
not stop PostgreSQL or any Trading Kernel worker.

Export the exact production database through the configured SSH alias:

```bash
.venv/bin/python scripts/owner_console/export_server_dml_snapshot.py \
  --ssh-host tokyo \
  --remote-database brc_trading_kernel
```

The exporter performs a credential-column preflight, one single-process
serializable data-only `pg_dump` restricted to the authoritative `public`
Schema, local gzip streaming, SHA-256 generation, and before/after parity
counts. The internal `claim_token` column is an allowed
runtime lease identity rather than an authentication credential; password,
secret, API key, TOTP, and credential columns remain hard stops.

Restore the emitted `.sql.gz` and `.json` pair into a fresh disposable local
database:

```bash
.venv/bin/python scripts/owner_console/restore_local_dml_snapshot.py \
  --snapshot .local/owner-console-snapshots/<snapshot>.sql.gz \
  --metadata .local/owner-console-snapshots/<snapshot>.json \
  --database-name brc_owner_console_test_<12-lowercase-hex>
```

The restore verifies SHA-256 before PostgreSQL access, migrates a fresh local
database to the exact current head, restores DML through `psql` in one
transaction, compares five parity counts, and writes a mode-0600 local read-role
DSN beside the snapshot. By default `psql` runs inside the attested local
`dingdingbot-pg` container; `--postgres-container` may select another explicitly
scoped local container. During the trusted DML transaction only, PostgreSQL
trigger execution is disabled through `session_replication_role=replica` to
avoid replaying runtime triggers before their referenced rows are loaded; it is
restored to `origin` before commit. The command prints the exact `dropdb`
cleanup command.

Run the three bounded list probes through that read-only role:

```bash
.venv/bin/python scripts/owner_console/probe_local_snapshot.py \
  --database-name brc_owner_console_test_<12-lowercase-hex> \
  --snapshot-metadata .local/owner-console-snapshots/<snapshot>.json
```

The probe prints no rows, SQL parameters, DSN, account identity, Ticket
identity, or credentials. It records only snapshot checksum, aggregate source
count, planning time, execution time, end-to-end repository time, returned row
count, sequential-scan presence, external-sort presence, and pass/fail. Signal,
Trade, and Review each require EXPLAIN execution below 2400 ms and repository
elapsed time below 3000 ms.

## Rollback

Stop and disable `brc-owner-console-api.service`, remove the Nginx include, and
reload Nginx. No database migration or Trading Kernel rollback is required.
