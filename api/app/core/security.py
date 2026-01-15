from fastapi import Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional

# Bearer token scheme
bearer_scheme = HTTPBearer(auto_error=False)


async def get_token(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> Optional[str]:
    """
    Extracts a JWT token from an optional HTTP Bearer authorization header.

    Parameters
    ----------
    credentials: Optional[HTTPAuthorizationCredentials], optional
        The credentials provided by the `bearer_scheme` dependency, representing the value of the `Authorization` header. If the header is missing or malformed, this argument will be `None`.

    Returns
    -------
    Optional[str]
        The raw JWT token string if a valid bearer token was supplied; otherwise `None`.
    """
    if credentials:
        return credentials.credentials
    return None


__all__ = ["bearer_scheme", "get_token"]
