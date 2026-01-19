from typing import Dict, Optional, Tuple

from ..utils.log_setup import get_logger

logger = get_logger(__name__)


def prepare_llm_auth(api_key: Optional[str]) -> Tuple[Dict[str, str], Dict[str, str]]:
    """
    Prepare authentication headers and cookies for LLM API calls.

    The function inspects `api_key` to determine whether it represents a bearer token or a cookie string and returns dictionaries suitable for use with HTTP requests.

    **Authentication detection**
    - **Cookie format** - contains an `=` character or starts with common cookie prefixes (e.g., `session`, `auth`, `token`, `__`). The value may be a single `name=value` pair or multiple pairs separated by semicolons.
    - **Bearer token format** - any string without an `=` character. Treated as a standard bearer token for services such as OpenAI or OpenRouter.

    **Parameters**
    - `api_key` (Optional[str]): The API key, bearer token, or raw cookie header string. If `None` or empty, no authentication information is added.

    **Returns**
    - Tuple[Dict[str, str], Dict[str, str]]: A pair `(headers, cookies)` where:
      - `headers` always includes `"Content-Type": "application/json"` and, for bearer tokens, an `Authorization` header with the value `Bearer <api_key>`.
      - `cookies` contains parsed cookie name/value pairs when a cookie string is supplied; otherwise it remains empty.
    """
    headers = {"Content-Type": "application/json"}
    cookies = {}

    if not api_key:
        logger.debug("No API key provided - unauthenticated request")
        return headers, cookies

    # Detect authentication method
    if "=" in api_key or api_key.startswith(("session", "auth", "token", "__")):
        # Cookie-based authentication
        # Parse cookie string (format: "name=value" or "name1=value1; name2=value2")
        for cookie_pair in api_key.split(";"):
            cookie_pair = cookie_pair.strip()
            if "=" in cookie_pair:
                name, value = cookie_pair.split("=", 1)
                cookies[name.strip()] = value.strip()

        logger.debug(
            f"Using cookie-based authentication with {len(cookies)} cookie(s): {list(cookies.keys())}"
        )
    else:
        # Bearer token authentication (OpenAI, OpenRouter, etc.)
        headers["Authorization"] = f"Bearer {api_key}"
        logger.debug("Using Bearer token authentication")

    return headers, cookies


__all__ = ["prepare_llm_auth"]
