"""Create an API key.

Usage:
    python scripts/create_api_key.py "my client name"

Prints the plaintext key once — store it now, only its hash is persisted.
"""
import secrets
import sys

from app.core.auth import hash_key
from app.db.database import session_scope
from app.db.models import ApiKey


def main() -> None:
    if len(sys.argv) < 2:
        print("usage: python scripts/create_api_key.py <name>", file=sys.stderr)
        raise SystemExit(1)

    name = sys.argv[1]
    raw = secrets.token_urlsafe(32)
    with session_scope() as db:
        db.add(ApiKey(key_hash=hash_key(raw), name=name, is_active=True))

    print(f"API key for '{name}':\n{raw}\n(store this now — it cannot be recovered)")


if __name__ == "__main__":
    main()
