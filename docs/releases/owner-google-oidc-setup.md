# Owner Google OIDC setup

## Boundary

This changes only Owner API authentication and the V2 login interface. Google
identity must match the configured, verified email and fixed Google `sub`.
No public registration is provided. Existing strategy/global Resume, Selection
and flatten step-up TOTP checks remain unchanged. The original password/TOTP
login remains available. No database migration or Kernel deployment is needed.

OAuth uses Authorization Code + S256 PKCE, a ten-minute, bounded, one-use state
registry, nonce validation and an HttpOnly Secure SameSite=Lax correlation
cookie. The authenticated Owner cookie remains HttpOnly/Secure/SameSite=Strict.
Only `openid email` is requested. Tokens and refresh credentials are not stored.
The single existing Owner Session still expires after four idle hours or twelve
absolute hours, and an API process restart invalidates it.

## Owner-managed secret

The downloaded Google Web client JSON must never enter Git or chat. Owner runs
the following locally, replacing the download path:

```bash
install -d -m 700 "$HOME/.config/brc"
.venv/bin/python scripts/owner_console/prepare_google_credential.py \
  --download "/actual/downloaded/google-web-client.json" \
  --output "$HOME/.config/brc/google_oidc" \
  --owner-email "jiangwei4wh@gmail.com"
scp -J niu "$HOME/.config/brc/google_oidc" tokyo:/tmp/brc-google-oidc
ssh -J niu tokyo 'sudo install -o root -g root -m 0600 /tmp/brc-google-oidc /etc/brc/owner-console-credentials/google_oidc && rm /tmp/brc-google-oidc'
```

The helper is offline, checks the exact callback, refuses output in the
repository, refuses to overwrite an existing file and creates it mode0600.
It does not print credential values. Initial `owner_subject` is null: Google
login is disabled, while the authenticated binding interface is enabled.

## Release order

1. Certify the exact R2 API and R1 static commit with the existing official
   certifiers; preserve the previous API/static symlinks and Nginx configuration.
2. Install `google-oidc.conf.example` as the service drop-in
   `/etc/systemd/system/brc-owner-console-api.service.d/google-oidc.conf` only
   after Owner installs the credential. Installing the drop-in does not restart
   any service. Do not add Google secrets to the unit or environment.
3. Install the updated Owner Nginx locations include and run `nginx -t` before
   reload. The exact Google callback location disables access logging so that
   authorization codes/state do not enter proxy logs. The API's access log
   filter independently strips that query. The start endpoint is rate limited.
4. Deploy only the Owner API through R2 (one API restart), then V2 through R1.
   Do not restart Kernel workers or change trading controls.
5. Owner signs in with the original credentials and completes the binding
   panel with TOTP and Google. A verified candidate `sub` is shown only in that
   original authenticated browser, and expires with the ten-minute flow.
6. Owner runs the offline helper again with a new output path and
   `--owner-subject "verified-sub-from-binding-panel"`, then installs the new
   credential as above. Restart only Owner API to load the fixed identity.
   Google login is now enabled and the bootstrap binding route is disabled.
7. Owner completes the genuine Google consent/login. Verify session GET,
   readonly pages, logout and rejection of an unbound account. Do not execute a
   trading control operation as a login smoke.

## Rollback

Before rollback to an API version that does not recognize `google_oidc`, remove
the Google systemd drop-in, daemon-reload and use the official previous API
release. The original credential set and password/TOTP login remain intact.
Restore the previous static symlink if necessary. Restore the backed-up Nginx
include and validate before reload. Secrets remain Owner-managed; never rotate
or delete Google credentials automatically as part of rollback.

## Evidence limits

Mock-signed JWT, HTTP, credential-permission and frontend tests do not prove
Google network access, the genuine consent redirect or production login. Those
remain untested until Owner supplies the secret and completes the live flow.
