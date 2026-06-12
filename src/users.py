"""User management — create, fetch, update, and delete users."""

from dataclasses import dataclass, field
from typing import Optional
from src.auth import hash_password


# In-memory store (stands in for a real database)
_users: dict[int, "User"] = {}
_next_id: int = 1


@dataclass
class User:
    """Represents a user in the system."""
    id: int
    username: str
    email: str
    hashed_password: str
    is_active: bool = True
    roles: list[str] = field(default_factory=lambda: ["viewer"])


def create_user(username: str, email: str, password: str) -> User:
    """
    Creates a new user and stores them in the database.

    Automatically hashes the password before storing.
    The new user is assigned the default role of 'viewer'.

    Args:
        username: A unique username for the user.
        email: The user's email address.
        password: The plain-text password (will be hashed).

    Returns:
        The newly created User object.

    Raises:
        ValueError: If the username is already taken.
    """
    global _next_id
    for user in _users.values():
        if user.username == username:
            raise ValueError(f"Username '{username}' is already taken.")
    user = User(
        id=_next_id,
        username=username,
        email=email,
        hashed_password=hash_password(password),
    )
    _users[_next_id] = user
    _next_id += 1
    return user


def get_user(user_id: int) -> Optional[User]:
    """
    Fetches a user by their ID.

    Args:
        user_id: The integer ID of the user.

    Returns:
        The User object if found, None otherwise.
    """
    return _users.get(user_id)


def get_user_by_username(username: str) -> Optional[User]:
    """
    Fetches a user by their username.

    Args:
        username: The username to search for.

    Returns:
        The User object if found, None otherwise.
    """
    for user in _users.values():
        if user.username == username:
            return user
    return None


def update_email(user_id: int, new_email: str) -> Optional[User]:
    """
    Updates the email address of an existing user.

    Args:
        user_id: The ID of the user to update.
        new_email: The new email address.

    Returns:
        The updated User object, or None if the user does not exist.
    """
    user = _users.get(user_id)
    if not user:
        return None
    user.email = new_email
    return user


def deactivate_user(user_id: int) -> bool:
    """
    Deactivates a user account. Deactivated users cannot log in.

    Args:
        user_id: The ID of the user to deactivate.

    Returns:
        True if the user was found and deactivated, False otherwise.
    """
    user = _users.get(user_id)
    if not user:
        return False
    user.is_active = False
    return True


def assign_role(user_id: int, role: str) -> Optional[User]:
    """
    Assigns an additional role to a user.

    Valid roles are: 'viewer', 'editor', 'admin'.
    Duplicate roles are ignored.

    Args:
        user_id: The ID of the user.
        role: The role to assign.

    Returns:
        The updated User object, or None if the user does not exist.

    Raises:
        ValueError: If the role is not one of the valid roles.
    """
    valid_roles = {"viewer", "editor", "admin"}
    if role not in valid_roles:
        raise ValueError(f"Invalid role '{role}'. Must be one of {valid_roles}.")
    user = _users.get(user_id)
    if not user:
        return None
    if role not in user.roles:
        user.roles.append(role)
    return user
