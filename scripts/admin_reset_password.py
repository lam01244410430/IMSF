"""Admin-only password reset (reform plan SS7.4).

NOT an HTTP endpoint and NOT wired into the API: run it on the server
over SSH by an admin. It resets a user's password given an email + new
password, using the same argon2id hash function as the API
(app.passwords.hash_password).

There is no self-service password reset in v1 (no email infrastructure
to send a reset link). Interim process: admin runs this script, then
gives the temporary password to the user over a channel already
authenticated outside the system; the user logs in and (once the
change-password endpoint exists) changes it.

Usage (from the repo root, env file sourced first):
    set -a; . /home/ubuntu/imsf.env; set +a
    .venv/bin/python scripts/admin_reset_password.py \\
        --email user@example.com --password 'TemporaryPass123'

Output on success is only: ``password reset for <normalised email>``.
The password and the hash are NEVER printed or logged.

Phase C (contract §1.2): the reset also bumps ``auth_version`` (+1)
so every existing session of that user dies immediately.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text  # noqa: E402

from app.db import get_engine  # noqa: E402
from app.passwords import hash_password  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Admin-only: reset a user's password by email.")
    parser.add_argument("--email", required=True,
                        help="user email (normalised: strip + lowercase)")
    parser.add_argument("--password", required=True,
                        help="new temporary password (8-128 chars)")
    args = parser.parse_args()
    email = args.email.strip().lower()
    if not 8 <= len(args.password) <= 128:
        print("error: password must be 8-128 characters", file=sys.stderr)
        return 2
    engine = get_engine()
    with engine.begin() as conn:
        result = conn.execute(
            text("UPDATE users SET password_hash = :h,"
                 " auth_version = auth_version + 1 WHERE email = :e"),
            {"h": hash_password(args.password), "e": email},
        )
        if result.rowcount == 0:
            print(f"error: no user with email {email}", file=sys.stderr)
            return 1
    print(f"password reset for {email}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
