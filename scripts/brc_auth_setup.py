#!/usr/bin/env python3
from __future__ import annotations

import argparse
import getpass
import secrets

from src.interfaces.operator_auth import (
    DEFAULT_SESSION_TTL_SECONDS,
    build_otpauth_uri,
    create_password_hash,
    generate_totp_secret,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate local BRC operator auth env values.")
    parser.add_argument("--username", default="owner")
    parser.add_argument("--issuer", default="BRC Operator Console")
    parser.add_argument("--ttl-seconds", type=int, default=DEFAULT_SESSION_TTL_SECONDS)
    args = parser.parse_args()

    password = getpass.getpass("Operator password: ")
    confirm = getpass.getpass("Confirm password: ")
    if password != confirm:
        raise SystemExit("Password confirmation did not match.")
    if not password:
        raise SystemExit("Password must not be empty.")

    totp_secret = generate_totp_secret()
    session_secret = secrets.token_urlsafe(48)
    password_hash = create_password_hash(password)

    print("\nAdd these values to your local environment file:")
    print(f"BRC_OPERATOR_USERNAME={args.username}")
    print(f"BRC_OPERATOR_PASSWORD_HASH={password_hash}")
    print(f"BRC_OPERATOR_TOTP_SECRET={totp_secret}")
    print(f"BRC_OPERATOR_SESSION_SECRET={session_secret}")
    print(f"BRC_OPERATOR_SESSION_TTL_SECONDS={args.ttl_seconds}")
    print("\nGoogle Authenticator URI:")
    print(build_otpauth_uri(username=args.username, secret=totp_secret, issuer=args.issuer))


if __name__ == "__main__":
    main()
