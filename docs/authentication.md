# Authentication

This document describes how authentication works in the User Management API,
including password hashing, token generation, and token verification.

## Password Hashing

Passwords are never stored in plain text. The `hash_password` function
takes a plain-text password and returns a SHA-256 hex digest.

```python
hashed = hash_password("mysecretpassword")
```

To verify a password against a stored hash, use `verify_password`:

```python
is_valid = verify_password("mysecretpassword", hashed)
```

This uses `hmac.compare_digest` internally to prevent timing attacks.

## Token Generation

Use `generate_token` to create an auth token for a logged-in user.
Pass the user's integer ID and you'll get back a token string.

```python
token = generate_token(user_id=42)
```

Tokens are valid for **1 hour** (3600 seconds) by default.
The token format is `user_id:expiry:signature`, where the signature
is an HMAC-SHA256 of the payload.

## Token Verification

Use `verify_token` to validate an incoming token. It checks both
the HMAC signature and the expiry timestamp.

```python
user_id = verify_token(token)
if user_id is None:
    # token is invalid or expired
    raise PermissionError("Unauthorized")
```

Returns the `user_id` as an integer if valid, or `None` if the token
is expired or tampered with.

## Token Expiry

The default token expiry is **3600 seconds (1 hour)**. This is controlled
by the `TOKEN_EXPIRY_SECONDS` constant in `src/auth.py`.

To change the expiry, update the `TOKEN_EXPIRY` environment variable
in your `AppConfig`.
