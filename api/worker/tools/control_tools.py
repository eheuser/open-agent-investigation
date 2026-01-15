import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


def exit_early(reason: str = "Agent completed task", status: str = "success") -> Dict[str, Any]:
    """
    Signal an early termination of the agent’s processing loop.

    Parameters
    ----------
    reason : str, optional
        Human-readable explanation for why the agent is exiting early. Defaults to `"Agent completed task"`.
    status : str, optional
        Machine-oriented status indicator (e.g., `"success"`, `"error"`, etc.) that describes the outcome of the execution. Defaults to `"success"`.

    Returns
    -------
    dict
        A dictionary containing two keys:

        - `"status"`: the provided status string.
        - `"reason"`: the explanatory reason for early exit.
    """
    return {"status": status, "reason": reason}


def complete_investigation(
    summary: str, key_findings: str = "", timeline_entries_count: int = 0, recommendations: str = ""
) -> Dict[str, Any]:
    """
    Mark the investigation as complete and provide a final summary.

    This function must be called when the agent has finished answering the user's question and has registered all important findings to the timeline.

    Args:
        summary (str): Brief summary of what was discovered (2-3 sentences).
        key_findings (str, optional): Main findings from the investigation. Defaults to an empty string.
        timeline_entries_count (int, optional): Number of timeline entries that were created. Defaults to `0`.
        recommendations (str, optional): Recommendations for further investigation or next steps. Defaults to an empty string.

    Returns:
        dict: A dictionary containing the completion status and provided information with keys:
            - `status` (str): Always set to `"completed"`.
            - `summary` (str): The summary passed in.
            - `key_findings` (str): The key findings passed in.
            - `timeline_entries_count` (int): The count of timeline entries.
            - `recommendations` (str): Any recommendations supplied.
            - `message` (str): Confirmation message indicating successful completion.
    """
    return {
        "status": "completed",
        "summary": summary,
        "key_findings": key_findings,
        "timeline_entries_count": timeline_entries_count,
        "recommendations": recommendations,
        "message": "Investigation completed successfully",
    }


def skip_timeline_registration(reason: str) -> Dict[str, Any]:
    """
    Skip timeline registration for the current search results.

    This function should be used only when the events discovered are purely exploratory and do not directly contribute to answering the user's question. It returns a structured confirmation indicating that the timeline registration step was intentionally omitted, along with the provided rationale.

    Args:
        reason (str): A concise explanation for skipping the registration (e.g., "Events are exploratory, need more analysis").

    Returns:
        dict: A dictionary containing:
            - `status` (str): Fixed value `"skipped"` indicating the action taken.
            - `reason` (str): The caller-provided rationale.
            - `message` (str): Human-readable confirmation message, `"Timeline registration skipped"`.
    """
    return {"status": "skipped", "reason": reason, "message": "Timeline registration skipped"}
