# User Management API

A simple user management system used as a test bed for the
self-healing documentation tool.

## Structure

```
src/
  auth.py       — password hashing and token generation/verification
  users.py      — user CRUD operations and role management
  config.py     — environment-based configuration

docs/
  authentication.md   — auth system documentation
  users.md            — user management documentation
  configuration.md    — configuration reference
```

## Quick Start

```bash
python -m pytest tests/
```

## Intentionally Breaking the Docs (for testing)

To test the self-healing tool, try making one of these changes
and see if the tool catches the staleness:

1. Change `TOKEN_EXPIRY_SECONDS` in `auth.py` from 3600 to 1800
   → docs say "1 hour", should now say "30 minutes"

2. Add a new `delete_user` function to `users.py`
   → docs don't mention it at all

3. Change `assign_role` valid roles to add `"moderator"`
   → docs list only viewer/editor/admin

4. Change `APP_PORT` default from 8000 to 8080 in `config.py`
   → configuration table will be wrong
