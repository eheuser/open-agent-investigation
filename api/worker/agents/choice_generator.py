import json
from typing import List, Dict, Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.utils.log_setup import get_logger

logger = get_logger(__name__)


async def generate_investigation_choices(
    llm_client,
    investigation_id: str,
    job_id: int,
    question: str,
    investigation_context: str,
    tools_executed: int,
    timeline_entries_created: int,
    evidence_summary: str,
    db: AsyncSession,
) -> List[Dict[str, Any]]:
    """
    Generate a list of actionable forensic investigation path suggestions using an LLM.

    This coroutine builds a prompt that describes the current investigation state-including the original user question, tools executed, timeline entries created, evidence summary, and overall context-and asks the language model to return 3-4 specific next steps in JSON format. The response is streamed, cleaned of any markdown fences, parsed as JSON, and each choice is enriched with metadata such as the investigation ID, job ID, and default fields.

    If the LLM returns no choices, or if JSON parsing fails for any reason, a predefined fallback set of suggestions is returned instead.

    Parameters
    ----------
    llm_client : Any
        An asynchronous client capable of streaming chat completions from the target language model. It must expose an `async stream_chat` method accepting `messages`, `tools`, `temperature` and `max_tokens` arguments.
    investigation_id : str
        The UUID of the investigation to which the generated choices belong.
    job_id : int
        Identifier of the current job within the investigation workflow.
    question : str
        The original question posed by the user that drives the investigation.
    investigation_context : str
        A textual summary of all relevant findings and actions performed up to this point.
    tools_executed : int
        Count of forensic tools that have already been run in this investigation.
    timeline_entries_created : int
        Number of timeline entries generated so far.
    evidence_summary : str
        Concise description of the evidence collected to date.
    db : AsyncSession
        An active asynchronous SQLAlchemy session used by fallback logic (if needed).

    Returns
    -------
    list[dict[str, Any]]
        A list of dictionaries, each representing a suggested investigative path. Every dictionary contains at least the following keys:

        * `title` - short actionable title (<50 characters)
        * `description` - brief description (<150 characters)
        * `rationale` - why this path is relevant given the current evidence
        * `suggested_query` - natural-language query to be issued next
        * `suggested_effort` - estimated effort level (\"low\", \"medium\", or \"high\")
        * `display_order` - integer indicating presentation order (default 0)
        * `investigation_id` - the supplied investigation UUID
        * `job_id` - the supplied job identifier
        * `tool_suggestions` - optional field, default `None`

    Raises
    ------
    json.JSONDecodeError
        Propagated only internally; the function catches this exception and returns fallback choices instead.
    Exception
        Any unexpected error during LLM interaction or response handling is caught, logged, and results in fallback suggestions being returned.
    """
    prompt = f"""You are a forensic investigation assistant. The current investigation has reached its turn limit without completing.

**Original Question**: "{question}"

**Investigation Progress**:
- Tools executed: {tools_executed}
- Timeline entries created: {timeline_entries_created}
- Evidence found: {evidence_summary}

**Context**:
{investigation_context}

**Your Task**:
Generate 3-4 suggested next investigative paths that would help answer the user's question or explore the evidence further.

For each suggestion, provide:
1. **title**: Short, actionable title (e.g., "Analyze logon patterns", "Investigate process execution")
2. **description**: 1-2 sentences describing what this path will investigate
3. **rationale**: Why this path is worth exploring based on the evidence so far
4. **suggested_query**: The exact question to ask (natural language, specific)
5. **suggested_effort**: Recommended effort level (low, medium, or high)

**CRITICAL RULES**:
- Suggestions must be SPECIFIC and ACTIONABLE
- Each query should explore a different aspect
- Prioritize paths most likely to answer the original question
- Base suggestions on actual evidence found, not speculation
- Keep titles under 50 characters
- Keep descriptions under 150 characters

**Output Format** (JSON only, no markdown):
{{
  "choices": [
    {{
      "title": "Analyze lateral movement patterns",
      "description": "Examine network logon events to identify potential lateral movement between systems",
      "rationale": "Found 18 failed logons from single source - may indicate reconnaissance before lateral movement",
      "suggested_query": "Find network logon events (Type 3) from the source IP 192.168.1.100 and identify which systems were accessed",
      "suggested_effort": "medium",
      "display_order": 0
    }},
    {{
      "title": "Investigate user account activity",
      "description": "Review all activity for the targeted admin account to identify compromise indicators",
      "rationale": "Admin account was targeted 18 times - need to verify if compromise was successful",
      "suggested_query": "Show all events for user 'admin' including successful logons, privilege use, and process executions",
      "suggested_effort": "medium",
      "display_order": 1
    }}
  ]
}}

Generate the JSON now:"""

    try:
        # Call LLM for choice generation
        messages = [
            {
                "role": "system",
                "content": "You are a forensic investigation assistant that generates specific, actionable investigation paths. Always respond with valid JSON only.",
            },
            {"role": "user", "content": prompt},
        ]

        # Use streaming to get response
        accumulated_content = ""
        async for chunk in llm_client.stream_chat(
            messages=messages,
            tools=[],  # No tools for choice generation
            max_tokens=None,  # Use user's configured default
            temperature=None,  # Use user's configured temperature
        ):
            if "choices" in chunk and len(chunk["choices"]) > 0:
                delta = chunk["choices"][0].get("delta", {})
                if "content" in delta and delta["content"]:
                    accumulated_content += delta["content"]

        # Parse JSON response
        # Remove markdown code fences if present
        content = accumulated_content.strip()
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()

        response_data = json.loads(content)
        choices = response_data.get("choices", [])

        if not choices:
            logger.warning("LLM returned no choices, using fallback")
            return _generate_fallback_choices(question, evidence_summary)

        # Add investigation_id and job_id to each choice
        for choice in choices:
            choice["investigation_id"] = investigation_id
            choice["job_id"] = job_id
            # Ensure all required fields exist
            choice.setdefault("tool_suggestions", None)
            choice.setdefault("display_order", 0)

        logger.info(f"Generated {len(choices):,} investigation choices")
        return choices

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse LLM response as JSON: {e}")
        logger.error(f"Response content: {accumulated_content[:500]}")
        return _generate_fallback_choices(question, evidence_summary)
    except Exception as e:
        logger.error(f"Failed to generate choices: {e}", exc_info=True)
        return _generate_fallback_choices(question, evidence_summary)


def _generate_fallback_choices(question: str, evidence_summary: str) -> List[Dict[str, Any]]:
    """
    Generate a list of fallback investigation choices to be used when the LLM fails to produce valid suggestions.

    Parameters
    ----------
    question : str
        The original forensic question or query that prompted the generation of investigation paths.
    evidence_summary : str
        A brief textual summary of the evidence collected so far, incorporated into rationale messages for some fallback options.

    Returns
    -------
    list[dict[str, Any]]
        A list containing three dictionaries, each representing a basic investigative choice.  Each dictionary includes the following keys:

        * `title` (str): Human-readable name of the suggestion.
        * `description` (str): Short explanation of what the suggestion entails.
        * `rationale` (str): Reason why this fallback is offered, optionally referencing the supplied `question` or `evidence_summary`.
        * `suggested_query` (str): Example query or action that a user could execute to follow the suggestion.
        * `suggested_effort` (str): Approximate effort required; one of `"low"`, `"medium"`, or `"high"`.
        * `display_order` (int): Position index for UI ordering, starting at 0.
        * `tool_suggestions` (None or any): Placeholder for future tool integration; currently set to `None`.
    """
    return [
        {
            "title": "Continue with broader search",
            "description": "Expand the search to include related event types and time ranges",
            "rationale": "Initial investigation found evidence but may have missed related events",
            "suggested_query": f"Continue investigating: {question} (broader scope)",
            "suggested_effort": "medium",
            "display_order": 0,
            "tool_suggestions": None,
        },
        {
            "title": "Analyze timeline patterns",
            "description": "Review temporal patterns in the timeline to identify sequences",
            "rationale": f"Created {evidence_summary} - temporal analysis may reveal attack progression",
            "suggested_query": "Analyze the temporal sequence of events on the timeline to identify patterns",
            "suggested_effort": "low",
            "display_order": 1,
            "tool_suggestions": None,
        },
        {
            "title": "Deep dive into specific events",
            "description": "Examine specific high-value events in detail for additional context",
            "rationale": "Some events may contain additional fields or context worth exploring",
            "suggested_query": "Show detailed information for the most significant events found",
            "suggested_effort": "low",
            "display_order": 2,
            "tool_suggestions": None,
        },
    ]


__all__ = ["generate_investigation_choices"]
