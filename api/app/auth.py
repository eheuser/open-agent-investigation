from datetime import datetime, timedelta, timezone
from typing import Optional
import jwt
from passlib.context import CryptContext
from fastapi import HTTPException, status

from .core.config import settings

# Password hashing context
pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

# JWT algorithm
ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    """
    Hash a plain-text password using Argon2.

    Args:
        password (str): The password to be hashed.

    Returns:
        str: The Argon2 hash of the provided password.
    """
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    """
    Verify a plain-text password against an Argon2 hash.

    Args:
        plain (str): The password provided by the user.
        hashed (str): The stored Argon2 hash retrieved from the database.

    Returns:
        bool: `True` if the password matches the hash, otherwise `False`.
    """
    return pwd_context.verify(plain, hashed)


def create_access_token(
    user_id: int, username: str, role: int, expires_delta: Optional[timedelta] = None
) -> str:
    """
    Create a JWT access token containing user identification and role information.

    Args:
        user_id (int): The unique identifier of the user in the database.
        username (str): The user's login name.
        role (int): The user's role, where 0 denotes a regular user and 1 denotes an administrator.
        expires_delta (timedelta, optional): Custom time delta after which the token should expire. If omitted, defaults to eight hours.

    Returns:
        str: A JWT-encoded string that can be used for authentication and authorization.
    """
    to_encode = {
        "sub": str(user_id),
        "username": username,
        "role": role,
    }
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(hours=8))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.jwt_secret, algorithm=ALGORITHM)


def verify_jwt_token(token: str) -> dict:
    """
    Verify and decode a JSON Web Token (JWT).

    Parameters
    ----------
    token: str
        The JWT string to be validated and decoded.

    Returns
    -------
    dict
        The payload contained in the token if verification succeeds.

    Raises
    ------
    HTTPException
        Raised with a 401 status code when the token is expired or cannot be validated,
        providing an appropriate error detail message.
    """
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has expired")
    except jwt.PyJWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate credentials"
        )


__all__ = [
    "hash_password",
    "verify_password",
    "create_access_token",
    "verify_jwt_token",
]
