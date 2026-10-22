"""Owner-run offline preparation of the downloaded Google Web client credential.

Never prints the secret. Does not connect to Google, a server or the database.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.trading_kernel.interfaces.owner_console_http.google_oidc import (
    GoogleOidcSettings,
)

CALLBACK = "https://jiaoyingpan.cloud/api/owner/v1/auth/google/callback"


def prepare(
    download: Path, output: Path, *, email: str, subject: str | None = None
) -> None:
    destination = output.resolve()
    if destination.is_relative_to(REPO_ROOT):
        raise ValueError("credential output must be outside the repository")
    try:
        if download.stat().st_size > 16_384:
            raise ValueError
        web = json.loads(download.read_text(encoding="utf-8"))["web"]
        if CALLBACK not in web["redirect_uris"]:
            raise ValueError
        settings = GoogleOidcSettings(
            client_id=web["client_id"],
            client_secret=web["client_secret"],
            owner_email=email,
            owner_subject=subject,
        )
        content = (
            json.dumps(
                {
                    "client_id": settings.client_id,
                    "client_secret": settings.client_secret.get_secret_value(),
                    "owner_email": settings.owner_email,
                    "owner_subject": settings.owner_subject,
                }
            )
            + "\n"
        )
    except (OSError, ValueError, KeyError, TypeError):
        raise ValueError(
            "Google download is invalid or callback is not configured"
        ) from None
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(destination, flags, 0o600)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
    except BaseException:
        destination.unlink(missing_ok=True)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--owner-email", required=True)
    parser.add_argument("--owner-subject")
    args = parser.parse_args()
    try:
        prepare(
            args.download,
            args.output,
            email=args.owner_email,
            subject=args.owner_subject,
        )
    except (OSError, ValueError):
        parser.exit(
            1,
            "Credential preparation failed; check input, callback and unused output path.\n",
        )
    print("Credential written with mode 0600. Secret contents were not printed.")


if __name__ == "__main__":
    main()
