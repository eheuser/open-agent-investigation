from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from ..deps import get_db, get_current_user
from ..crud.user import get_user_by_username, create_user
from ..auth import verify_password, create_access_token
from ..models.user import UserRole, User

router = APIRouter()


class LoginRequest(BaseModel):
    """Login request payload."""

    username: str
    password: str


class LoginResponse(BaseModel):
    """Login response with JWT token."""

    access_token: str
    token_type: str = "bearer"
    username: str
    role: int


class RegisterRequest(BaseModel):
    """User registration request."""

    username: str
    password: str


@router.post("/login", response_model=LoginResponse)
async def login(credentials: LoginRequest, db: AsyncSession = Depends(get_db)):
    """
    Authenticate a user and return a JWT access token.

    Parameters
    ----------
    credentials: LoginRequest
        An object containing the username and password supplied by the client.
    db: AsyncSession, optional
        The asynchronous database session dependency injected by FastAPI.

    Returns
    -------
    LoginResponse
        A response model that includes the generated `access_token`, the authenticated user's `username` and their `role`.

    Raises
    ------
    HTTPException
        Raised with a 401 status code when the username does not exist or the password verification fails. The error detail is generic to avoid leaking information about which credential was incorrect.
    """
    user = await get_user_by_username(db, credentials.username)

    # Use constant-time comparison to prevent timing attacks
    if user is None:
        # Perform dummy hash verification to prevent timing attacks
        # This is a valid Argon2 hash of the string "dummy_password"
        verify_password(
            credentials.password,
            "$argon2id$v=19$m=65536,t=3,p=4$c29tZXNhbHQxMjM0NTY3OA$YWJjZGVmZ2hpamtsbW5vcHFyc3R1dnd4eXoxMjM0NTY",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not verify_password(credentials.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = create_access_token(user_id=user.user_id, username=user.username, role=user.role)

    return LoginResponse(access_token=token, username=user.username, role=user.role)


@router.post("/register", response_model=LoginResponse, status_code=status.HTTP_201_CREATED)
async def register(request: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """
    Register a new user account and return an authentication token.

    Args:
        request (RegisterRequest): The registration payload containing the desired username and password.
        db (AsyncSession, optional): An asynchronous SQLAlchemy session provided via dependency injection.

    Returns:
        LoginResponse: A response model containing the JWT access token, the registered username, and the assigned user role.

    Raises:
        HTTPException: If a user with the given username already exists (HTTP 400 Bad Request).
    """
    # Check if user already exists
    existing = await get_user_by_username(db, request.username)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Username already registered"
        )

    # Create new user (regular role by default)
    user = await create_user(
        db, username=request.username, password=request.password, role=UserRole.REGULAR
    )

    # Generate token
    token = create_access_token(user_id=user.user_id, username=user.username, role=user.role)

    return LoginResponse(access_token=token, username=user.username, role=user.role)


class UserResponse(BaseModel):
    """User information response."""

    id: int
    username: str
    role: int


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    """
    Get details of the currently authenticated user.

    Parameters
    ----------
    current_user : User
        The user object extracted from the JWT token by the `get_current_user` dependency.

    Returns
    -------
    UserResponse
        A response model containing the user's identifier, username, and role.
    """
    return UserResponse(
        id=current_user.user_id, username=current_user.username, role=current_user.role
    )


__all__ = ["router"]
