"""Password hashing with the standard library (scrypt), so no extra dependency is needed."""

import hashlib
import hmac
import secrets

N, R, P = 2**14, 8, 1


def _scrypt(password: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    """Derive a 32-byte key from the password."""
    return hashlib.scrypt(password.encode(), salt=salt, n=n, r=r, p=p, dklen=32)


def hash_password(password: str) -> str:
    """Hash a password with a fresh random salt. The result carries its own parameters."""
    salt = secrets.token_bytes(16)
    digest = _scrypt(password, salt, N, R, P)
    return f"scrypt${N}${R}${P}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """Check a password against a stored hash in constant time. Malformed hashes never match."""
    try:
        scheme, n, r, p, salt_hex, digest_hex = stored.split("$")
        if scheme != "scrypt":
            return False
        candidate = _scrypt(password, bytes.fromhex(salt_hex), int(n), int(r), int(p))
        return hmac.compare_digest(candidate, bytes.fromhex(digest_hex))
    except ValueError:
        return False


# Verified against when an email is unknown, so "no such user" and "wrong password"
# take about the same time and the response does not reveal which accounts exist.
DUMMY_HASH = hash_password(secrets.token_hex(16))
