import logging
from typing import Dict, Any

import aiohttp
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


async def retrieve_and_parse_url(
    url: str, **kwargs  # Accept and ignore extra params like db, investigation_id, stats
) -> Dict[str, Any]:
    """
    Retrieve and parse article content from a given URL asynchronously.

    This function fetches the HTML at *url* using an HTTP GET request with a
    browser-like `User-Agent` header.  It follows redirects up to three times,
    extracts the final URL, strips non-content elements (script, style, navigation,
    header and footer tags) with **BeautifulSoup**, normalises whitespace, and
    returns the plain-text body.  If the extracted text exceeds 10 000 characters,
    it is truncated to that length and a `[Content truncated...]` marker is added.

    The function accepts arbitrary keyword arguments (e.g., *db*, *investigation_id*,
    *stats*) which are ignored; they exist solely for compatibility with callers
    that pass extra context parameters.

    Parameters
    ----------
    url: str
        The URL to retrieve.  Must be a string that can be resolved by `aiohttp`.
    **kwargs: dict
        Additional keyword arguments accepted for compatibility but not used.

    Returns
    -------
    dict
        A dictionary containing:

        - `url` (str): The final URL after following redirects.
        - `content` (str): The cleaned plain-text content extracted from the page,
          possibly truncated to 10 000 characters.
        - `status` (str): `"ok"` when retrieval and parsing succeed.

        If an error occurs, the dictionary contains:

        - `error` (str): A description of the failure.
        - `url` (str): The URL that was being processed when the error occurred.

    Raises
    ------
    aiohttp.ClientError
        Propagated when a network-level error prevents retrieval.  The function
        catches this exception and returns an error dictionary instead of raising.

    Exception
        Any other unexpected exception during parsing is caught, logged, and an
        error dictionary is returned.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    try:
        async with aiohttp.ClientSession() as session:
            # Follow redirects
            final_url = url
            for attempt in range(3):
                async with session.get(
                    final_url,
                    timeout=aiohttp.ClientTimeout(total=30),
                    headers=headers,
                    allow_redirects=True,
                ) as resp:
                    resp.raise_for_status()
                    final_url = str(resp.url)

                    # If URL changed, follow one more time
                    if final_url != url and attempt < 2:
                        url = final_url
                        continue

                    html = await resp.text()
                    break

            # Parse HTML
            soup = BeautifulSoup(html, "html.parser")

            # Remove script and style elements
            for script in soup(["script", "style", "nav", "header", "footer"]):
                script.decompose()

            # Get text
            text = soup.get_text(separator="\n", strip=True)

            # Clean up whitespace
            lines = [line.strip() for line in text.split("\n") if line.strip()]
            content = "\n".join(lines)

            # Truncate if too long (keep first 10k chars)
            if len(content) > 10000:
                content = content[:10000] + "\n\n[Content truncated...]"

            logger.info(f"Retrieved {len(content)} chars from {final_url}")

            return {"url": final_url, "content": content, "status": "ok"}

    except aiohttp.ClientError as e:
        logger.warning(f"Failed to retrieve {url}: {e}")
        return {"error": f"Failed to retrieve URL: {str(e)}", "url": url}

    except Exception as e:
        logger.error(f"Error parsing {url}: {e}", exc_info=True)
        return {"error": f"Failed to parse content: {str(e)}", "url": url}
