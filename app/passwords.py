"""Password hashing for email login (reform plan SS7.5).

argon2id via argon2-cffi, RFC 9106 first recommended parameter set:
time_cost=3, memory_cost=65536 (64 MiB), parallelism=4, hash_len=32,
salt_len=16. Measured on Oregon 2026-11-21 at ~133-170 ms per hash,
well under the 500 ms budget, so memory_cost stays at 65536.

Rules (plan SS7.5, absolute):
- Plaintext passwords are NEVER stored (only the full argon2 hash
  string, which embeds salt + parameters).
- Plaintext passwords and hashes are NEVER logged; login error logs
  carry only the normalised email + a reason code.
- Verification uses PasswordHasher.verify() (constant-time); no
  hand-rolled hash comparison.
- Parameter upgrades are handled by re-hash on the next successful
  login (needs_rehash), not by a data migration.
"""

from argon2 import PasswordHasher
from argon2.exceptions import Argon2Error

# RFC 9106 first recommended set for argon2id.
_HASHER = PasswordHasher(
    time_cost=3,
    memory_cost=65536,
    parallelism=4,
    hash_len=32,
    salt_len=16,
)


def hash_password(plaintext: str) -> str:
    """Hash a plaintext password; returns the full argon2 hash string."""
    return _HASHER.hash(plaintext)


def verify_password(password_hash: str, plaintext: str) -> bool:
    """Constant-time verification; False for a wrong password or a
    malformed stored hash (never raises on a bad password)."""
    try:
        return _HASHER.verify(password_hash, plaintext)
    except (Argon2Error, ValueError):
        # VerifyMismatchError (wrong password) is an Argon2Error;
        # InvalidHashError (malformed stored hash) is a ValueError in
        # argon2-cffi 25.1.0. Neither is an error the caller should see
        # as anything but "does not verify".
        return False


def needs_rehash(password_hash: str) -> bool:
    """True when the stored hash was made with older parameters; the
    caller re-hashes on the next successful login."""
    return _HASHER.check_needs_rehash(password_hash)
