from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..models.user import User, UserRole
from ..auth import hash_password


async def get_user_by_username(db: AsyncSession, username: str) -> Optional[User]:
    """
    Retrieve a user record matching the given username.

    Args:
        db: An active asynchronous SQLAlchemy session.
        username: The unique username to look up.

    Returns:
        The `User` instance if found; otherwise `None`.
    """
    result = await db.execute(select(User).where(User.username == username))
    return result.scalars().first()


async def get_user_by_id(db: AsyncSession, user_id: int) -> Optional[User]:
    """
    Retrieve a user instance from the database by its primary key.

    Args:
        db (AsyncSession): An active asynchronous SQLAlchemy session used to execute queries.
        user_id (int): The unique identifier of the user to retrieve.

    Returns:
        Optional[User]: The matching `User` object if found; otherwise `None`.

    Raises:
        None.
    """
    result = await db.execute(select(User).where(User.user_id == user_id))
    return result.scalars().first()


async def create_user(
    db: AsyncSession, username: str, password: str, role: UserRole = UserRole.REGULAR
) -> User:
    """
    Create a new user record in the database.

    Parameters
    ----------
    db : AsyncSession
        An active asynchronous SQLAlchemy session used for persisting the user.
    username : str
        The desired unique username for the new account.
    password : str
        Plain-text password which will be securely hashed before storage.
    role : UserRole, optional
        Role assigned to the user; defaults to `UserRole.REGULAR`.

    Returns
    -------
    User
        The newly created :class:`~app.models.User` instance, refreshed from the database with its primary key populated.
    """
    password_hash = hash_password(password)

    user = User(username=username, password_hash=password_hash, role=role)

    db.add(user)
    await db.commit()
    await db.refresh(user)

    return user


__all__ = ["get_user_by_username", "get_user_by_id", "create_user"]
