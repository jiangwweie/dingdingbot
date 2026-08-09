# Owner Console Deployment Assets

## Boundary

The Owner Console is a read-only, same-origin HTTPS surface. It has its own
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

## Encrypted Credentials

Create `/etc/credstore.encrypted` as root and encrypt exactly these six values:

| Credential name | Encrypted file |
| --- | --- |
| `owner_username` | `brc-owner-console-owner-username` |
| `owner_password_hash` | `brc-owner-console-owner-password-hash` |
| `owner_totp_seed` | `brc-owner-console-owner-totp-seed` |
| `session_signing_key` | `brc-owner-console-session-signing-key` |
| `database_dsn` | `brc-owner-console-database-dsn` |
| `account_id` | `brc-owner-console-account-id` |

Use `systemd-ask-password` so the plaintext value is not stored in the command
line or shell history. Example for one credential:

```bash
systemd-ask-password "Owner Console database DSN" | sudo systemd-creds encrypt --name=database_dsn - /etc/credstore.encrypted/brc-owner-console-database-dsn
```

Repeat with the exact credential name and destination above. The password hash
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

## Rollback

Stop and disable `brc-owner-console-api.service`, remove the Nginx include, and
reload Nginx. No database migration or Trading Kernel rollback is required.
