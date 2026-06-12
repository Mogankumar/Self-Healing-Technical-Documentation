# User Management

This document covers creating, fetching, updating, and managing users.

## Creating a User

Use `create_user` to register a new user. You must provide a username,
email, and plain-text password. The password is hashed automatically.

```python
user = create_user(
    username="alice",
    email="alice@example.com",
    password="securepassword"
)
```

New users are assigned the default role of **'viewer'** automatically.
Raises `ValueError` if the username is already taken.

## Fetching Users

Fetch a user by their integer ID using `get_user`:

```python
user = get_user(user_id=1)
```

Returns `None` if no user exists with that ID.

You can also look up a user by username using `get_user_by_username`:

```python
user = get_user_by_username("alice")
```

## Updating a User

### Changing Email

Use `update_email` to change a user's email address:

```python
updated_user = update_email(user_id=1, new_email="newemail@example.com")
```

Returns the updated `User` object, or `None` if the user doesn't exist.

## Deactivating a User

Use `deactivate_user` to disable a user account.
Deactivated users cannot log in.

```python
success = deactivate_user(user_id=1)
```

Returns `True` if the user was found and deactivated, `False` otherwise.

## Roles

Users can have one or more roles. The available roles are:

- `viewer` — read-only access (default)
- `editor` — can create and edit content
- `admin` — full access

Use `assign_role` to add a role to a user:

```python
user = assign_role(user_id=1, role="editor")
```

Raises `ValueError` if an invalid role is provided.
Duplicate role assignments are silently ignored.
