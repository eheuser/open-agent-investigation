from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from .core.database import get_db
from .core.security import get_token
from .auth import verify_jwt_token
from .crud.user import get_user_by_id
from .models.user import User


async def get_current_user(
    token: Optional[str] = Depends(get_token), db: AsyncSession = Depends(get_db)
) -> User:
    """
    Extracts and validates the currently authenticated user from a JWT token.

    Args:
        token (Optional[str]): The JWT token extracted from the `Authorization` header via the `get_token` dependency. If omitted, authentication fails.
        db (AsyncSession): An asynchronous SQLAlchemy session provided by the `get_db` dependency for database access.

    Returns:
        User: The authenticated user instance retrieved from the database.

    Raises:
        HTTPException:
            - 401 Unauthorized with a `WWW-Authenticate: Bearer` header when no token is supplied.
            - 401 Unauthorized when the token cannot be verified or does not correspond to an existing user.
    """
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = verify_jwt_token(token)
    user_id = int(payload["sub"])

    user = await get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication credentials"
        )

    return user


async def require_admin(user: User = Depends(get_current_user)) -> User:
    """
    Require administrator privileges for the current user.

    Args:
        user: The currently authenticated `User` instance provided by `get_current_user`.

    Returns:
        The same `User` object, guaranteed to have administrative rights.

    Raises:
        HTTPException: If `user.is_admin()` is false, a 403 Forbidden error is raised.
    """
    if not user.is_admin():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Administrator privileges required"
        )
    return user


async def get_current_user_optional(
    token: Optional[str] = Depends(get_token), db: AsyncSession = Depends(get_db)
) -> Optional[User]:
    """
    Optional FastAPI dependency that retrieves the currently authenticated user.

    Args:
        token (str | None): JWT extracted from the `Authorization` header via :func:`get_token`. If `None` or invalid, no user is returned.
        db (AsyncSession): Asynchronous SQLAlchemy session provided by :func:`get_db`.

    Returns:
        User | None: The authenticated :class:`User` instance when a valid token is present; otherwise `None`.

    Notes:
        - Returns `None` silently for missing, malformed, or expired tokens.
        - Any exception raised during token verification or user lookup is caught and results in `None`.
    """
    if not token:
        return None

    try:
        payload = verify_jwt_token(token)
        user_id = int(payload["sub"])
        return await get_user_by_id(db, user_id)
    except Exception:
        return None


__all__ = ["get_current_user", "require_admin", "get_current_user_optional", "get_db"]
