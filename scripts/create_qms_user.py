"""Create or update an AI-QMS login account.

Credentials live in the git-ignored credential store (default
``data/auth/users.json``, override with ``QMS_AUTH_STORE``). Passwords are
never stored or echoed in plaintext — only an scrypt hash is written.

Usage:
    python scripts/create_qms_user.py <username> [--role admin|auditor|editor|viewer]
    python scripts/create_qms_user.py --list

The password is read interactively (hidden). For unattended setup use the
``QMS_AUTH_SEED`` environment variable instead — see src/utils/auth_store.py.
"""

import argparse
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.utils.auth_store import (  # noqa: E402
    DEFAULT_ROLE,
    VALID_ROLES,
    load_users,
    store_path,
    upsert_user,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Create or update an AI-QMS login account.")
    parser.add_argument("username", nargs="?", help="Login name (case-insensitive)")
    parser.add_argument(
        "--role",
        default=DEFAULT_ROLE,
        choices=VALID_ROLES,
        help=f"Account role (default: {DEFAULT_ROLE})",
    )
    parser.add_argument("--list", action="store_true", help="List existing accounts and exit")
    args = parser.parse_args()

    if args.list:
        users = load_users()
        print(f"Credential store: {store_path()}")
        if not users:
            print("(no accounts)")
        for name, rec in sorted(users.items()):
            print(f"  {name}  role={rec.get('role', DEFAULT_ROLE)}")
        return 0

    if not args.username:
        parser.error("username is required (or use --list)")

    password = getpass.getpass("Password: ")
    if not password:
        print("ERROR: password must not be empty", file=sys.stderr)
        return 1
    if password != getpass.getpass("Confirm password: "):
        print("ERROR: passwords do not match", file=sys.stderr)
        return 1

    uname = upsert_user(args.username, password, args.role)
    print(f"Saved account '{uname}' (role={args.role}) to {store_path()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
