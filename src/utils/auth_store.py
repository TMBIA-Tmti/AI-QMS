"""Local credential store for the AI-QMS login gate.

Backs ``@cl.password_auth_callback`` in ``src/chainlit_app/app.py`` so that
every RA action carried out through the UI (and therefore every write to
``/api/report/...``) is attributable to a real, verified identity as required
by 21 CFR Part 11 §11.10(d)/(g) and ISO 13485 §4.2.5.

Storage
-------
JSON file, path from the ``QMS_AUTH_STORE`` environment variable, default
``data/auth/users.json`` (``data/`` is git-ignored — credentials never enter
version control)::

    {
      "users": {
        "<username>": {
          "password_hash": "scrypt$16384$8$1$<salt_hex>$<key_hex>",
          "role": "ra"
        }
      }
    }

Hashing uses ``hashlib.scrypt`` from the standard library — no new dependency
(``bcrypt`` is present in requirements.txt only as a commented-out server-mode
extra, so it cannot be relied on for a local install).

Seeding
-------
No credentials are hardcoded here. Populate the store either with::

    python scripts/create_qms_user.py <username> --role ra

or, for unattended/container startup, by setting ``QMS_AUTH_SEED`` to
``user:password:role`` (comma-separated for several accounts). The seed is
applied only when the store does not yet contain that username.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import secrets
from pathlib import Path
from typing import Optional

from src.utils.safe_io import atomic_write_json

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).parent.parent.parent
_DEFAULT_STORE = _PROJECT_ROOT / "data" / "auth" / "users.json"

# scrypt work factors — interactive-login profile (~100ms, ~16MB RAM).
_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1
_SALT_BYTES = 16
_KEY_LEN = 32

# Roles reuse the existing permission matrix in src/config.py rather than
# inventing a parallel vocabulary. "auditor" is the RA reviewer role that may
# override verdicts / add notes / restore originals.
try:
    from src import config as _config

    VALID_ROLES = tuple(_config.PERMISSIONS.keys())
except Exception:  # pragma: no cover — config import must never block login
    VALID_ROLES = ("admin", "auditor", "editor", "viewer")

DEFAULT_ROLE = "auditor"

# Dummy hash used to keep the failure path roughly constant-time so an
# attacker cannot enumerate valid usernames from response timing.
_DUMMY_HASH = (
    "scrypt$16384$8$1$"
    "00000000000000000000000000000000$"
    "0000000000000000000000000000000000000000000000000000000000000000"
)


def store_path() -> Path:
    """Resolve the credential store path (``QMS_AUTH_STORE`` override)."""
    env_path = os.environ.get("QMS_AUTH_STORE", "").strip()
    return Path(env_path) if env_path else _DEFAULT_STORE


def jwt_secret_path() -> Path:
    """Resolve the persisted Chainlit JWT secret path."""
    return store_path().parent / "jwt_secret"


def ensure_jwt_secret() -> str:
    """Guarantee ``CHAINLIT_AUTH_SECRET`` is set before Chainlit starts.

    Chainlit refuses to boot with an auth callback registered but no JWT
    secret. If the operator has not supplied one, generate a random secret
    once and persist it next to the credential store (git-ignored ``data/``)
    so that issued session cookies survive an application restart.
    """
    existing = os.environ.get("CHAINLIT_AUTH_SECRET", "").strip()
    if existing:
        return existing

    path = jwt_secret_path()
    try:
        if path.exists():
            secret = path.read_text(encoding="utf-8").strip()
            if secret:
                os.environ["CHAINLIT_AUTH_SECRET"] = secret
                return secret

        secret = secrets.token_urlsafe(48)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(secret, encoding="utf-8")
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass  # Best effort — Windows ACLs are not POSIX modes.
        logger.warning(
            "CHAINLIT_AUTH_SECRET was not set; generated one and stored it at %s. "
            "Set the environment variable explicitly for multi-host deployments.",
            path,
        )
        os.environ["CHAINLIT_AUTH_SECRET"] = secret
        return secret
    except OSError as e:
        # Last resort: an ephemeral secret still enforces auth, but sessions
        # are invalidated on restart.
        logger.error("Could not persist JWT secret at %s: %s", path, e)
        secret = secrets.token_urlsafe(48)
        os.environ["CHAINLIT_AUTH_SECRET"] = secret
        return secret


def normalize_username(username: str) -> str:
    """Usernames are case-insensitive and whitespace-trimmed."""
    return (username or "").strip().lower()


def hash_password(password: str) -> str:
    """Hash a password with scrypt, returning a self-describing string."""
    if not password:
        raise ValueError("Password must not be empty")
    salt = secrets.token_bytes(_SALT_BYTES)
    key = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=_KEY_LEN,
    )
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${salt.hex()}${key.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    """Constant-time verification of a password against a stored hash."""
    try:
        scheme, n_s, r_s, p_s, salt_hex, key_hex = (encoded or "").split("$")
        if scheme != "scrypt":
            return False
        candidate = hashlib.scrypt(
            (password or "").encode("utf-8"),
            salt=bytes.fromhex(salt_hex),
            n=int(n_s),
            r=int(r_s),
            p=int(p_s),
            dklen=len(bytes.fromhex(key_hex)),
        )
        return hmac.compare_digest(candidate, bytes.fromhex(key_hex))
    except (ValueError, TypeError, MemoryError):
        return False


def load_users() -> dict:
    """Load the ``{username: {password_hash, role}}`` mapping."""
    path = store_path()
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        users = data.get("users", {})
        return users if isinstance(users, dict) else {}
    except (json.JSONDecodeError, OSError) as e:
        # Fail closed: an unreadable store must not silently allow logins.
        logger.error("Unable to read credential store %s: %s", path, e)
        return {}


def save_users(users: dict) -> None:
    """Persist the credential store atomically."""
    path = store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(path, {"users": users})


def upsert_user(username: str, password: str, role: str = DEFAULT_ROLE) -> str:
    """Create or update an account. Returns the normalized username."""
    uname = normalize_username(username)
    if not uname:
        raise ValueError("Username must not be empty")
    if role not in VALID_ROLES:
        raise ValueError(f"Invalid role '{role}'. Must be one of {VALID_ROLES}")

    users = load_users()
    users[uname] = {"password_hash": hash_password(password), "role": role}
    save_users(users)
    return uname


def _apply_seed() -> dict:
    """Apply ``QMS_AUTH_SEED`` for accounts not already in the store."""
    seed = os.environ.get("QMS_AUTH_SEED", "").strip()
    if not seed:
        return load_users()

    users = load_users()
    changed = False
    for entry in seed.split(","):
        entry = entry.strip()
        if not entry:
            continue
        parts = entry.split(":")
        if len(parts) < 2:
            logger.warning("Ignoring malformed QMS_AUTH_SEED entry (expected user:password[:role])")
            continue
        uname = normalize_username(parts[0])
        password = parts[1]
        role = parts[2].strip() if len(parts) > 2 and parts[2].strip() else DEFAULT_ROLE
        if role not in VALID_ROLES:
            role = DEFAULT_ROLE
        if not uname or not password or uname in users:
            continue
        users[uname] = {"password_hash": hash_password(password), "role": role}
        changed = True
        logger.info("Seeded credential-store account '%s' (role=%s)", uname, role)

    if changed:
        save_users(users)
    return users


def authenticate(username: str, password: str) -> Optional[dict]:
    """Validate credentials.

    Returns ``{"username": ..., "role": ...}`` on success, ``None`` otherwise.
    """
    uname = normalize_username(username)
    users = _apply_seed()

    if not users:
        logger.error(
            "Credential store %s is empty — no logins are possible. "
            "Create an account with: python scripts/create_qms_user.py <username>",
            store_path(),
        )

    record = users.get(uname)
    if not record:
        # Burn equivalent work so missing users are not distinguishable by timing.
        verify_password(password, _DUMMY_HASH)
        return None

    if not verify_password(password, record.get("password_hash", "")):
        return None

    role = record.get("role", DEFAULT_ROLE)
    return {"username": uname, "role": role if role in VALID_ROLES else DEFAULT_ROLE}
