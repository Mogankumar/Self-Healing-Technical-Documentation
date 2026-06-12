"""Authentication utilities for the User Management API."""

import hashlib
import hmac
import time
from typing import Optional


SECRET_KEY = "supersecret123"
TOKEN_EXPIRY_SECONDS = 7200  # 1 hour


def hash_password(password: str) -> str:
    """
    Hashes a plain-text password using SHA-256.

    Args:
        password: The plain-text password to hash.

    Returns:
        A hex string of the hashed password.
    """
    return hashlib.sha256(password.encode()).hexdigest()


def verify_password(plain: str, hashed: str) -> bool:
    """
    Checks whether a plain-text password matches a stored hash.

    Args:
        plain: The plain-text password to verify.
        hashed: The previously hashed password to compare against.

    Returns:
        True if the password matches, False otherwise.
    """
    return hmac.compare_digest(hash_password(plain), hashed)


def generate_token(user_id: int) -> str:
    """
    Generates a simple auth token for a given user ID.

    The token encodes the user_id and an expiry timestamp,
    separated by a colon. Tokens expire after TOKEN_EXPIRY_SECONDS.

    Args:
        user_id: The ID of the user to generate a token for.

    Returns:
        A string token in the format "user_id:expiry:signature".
    """
    expiry = int(time.time()) + TOKEN_EXPIRY_SECONDS
    payload = f"{user_id}:{expiry}"
    signature = hmac.new(SECRET_KEY.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}:{signature}"


def verify_token(token: str) -> Optional[int]:
    """
    Verifies an auth token and returns the user ID if valid.

    Checks both the signature and the expiry time.

    Args:
        token: The token string to verify.

    Returns:
        The user_id if the token is valid and not expired, None otherwise.
    """
    try:
        user_id, expiry, signature = token.split(":")
        payload = f"{user_id}:{expiry}"
        expected = hmac.new(SECRET_KEY.encode(), payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            return None
        if int(expiry) < int(time.time()):
            return None
        return int(user_id)
    except Exception:
        return None
