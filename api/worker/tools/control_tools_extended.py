import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


async def request_additional_turns(
    turns_requested: int = 3,
    justification: str = "",
) -> Dict[str, Any]:
    """
    Request additional investigation turns beyond the initial budget.

    The agent may request extra turns when it determines that further investigation is required. This function validates the request, logs the details, and returns a structured response indicating approval or an error. The system will enforce a hard ceiling of ten additional turns.

    Parameters
    ----------
    turns_requested : int, optional
        Desired number of extra turns (clamped to the range 1-10). Default is `3`.
    justification : str, optional
        Explanation for why more turns are needed; must contain at least 20 non-whitespace characters. Default is an empty string.

    Returns
    -------
    dict
        A dictionary containing:

        - `status` (str): Either `"approved"` or `"error"`.
        - If `status` is `"approved"`, the dict also includes:
            * `turns_requested` (int): The validated number of turns granted.
            * `justification` (str): The original justification text.
            * `message` (str): Human-readable confirmation message.
        - If `status` is `"error"`, the dict includes:
            * `error` (str): Description of why validation failed.
    """
    # Validate turns_requested
    turns_requested = min(max(int(turns_requested), 1), 10)

    if not justification or len(justification.strip()) < 20:
        return {
            "status": "error",
            "error": "Justification must be at least 20 characters explaining why additional turns are needed",
        }

    logger.info(
        f"Agent requested {turns_requested} additional turns. "
        f"Justification: {justification[:100]}..."
    )

    # Return approval with metadata
    # The agent execution framework will handle incrementing the turn limit
    return {
        "status": "approved",
        "turns_requested": turns_requested,
        "justification": justification,
        "message": f"Request approved: {turns_requested} additional turns granted. Continue investigation.",
    }


__all__ = ["request_additional_turns"]
