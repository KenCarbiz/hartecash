"""Password hashing. Bcrypt via the standalone `bcrypt` package (no
passlib — passlib broke the bcrypt<=4 boundary in late 2023)."""

import bcrypt


def hash_password(password: str) -> str:
    if not password:
        raise ValueError("password cannot be empty")
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()


def verify_password(password: str, stored_hash: str) -> bool:
    if not password or not stored_hash:
        return False
    try:
        return bcrypt.checkpw(password.encode(), stored_hash.encode())
    except ValueError:
        # Happens on malformed hashes — treat as auth failure.
        return False
