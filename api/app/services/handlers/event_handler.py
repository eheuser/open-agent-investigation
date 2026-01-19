import json
import csv
import yaml
import io
from typing import Dict, Any, List
from uuid import UUID
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from ..llm_service import LLMService

from app.utils.log_setup import get_logger

logger = get_logger(__name__)


async def handle_event_insertion(
    db: AsyncSession,
    investigation_id: UUID,
    user_query: str,
    user_id: int,
) -> Dict[str, Any]:
    """
    Parse user-provided event data and insert the resulting events into the database.

    The function first attempts to interpret `user_query` as structured data (JSON, CSV, or YAML) using :func:`parse_structured_events`. If this yields no events, it falls back to a language model via :func:`llm_extract_events` to derive event objects from natural-language descriptions.

    After obtaining a list of event dictionaries, the function bulk-inserts them into the `events` table for the specified investigation using :func:`insert_events`. It then builds a summary message that includes the total number of inserted events and a breakdown by `event_type`.

    If parsing fails entirely, or if an exception occurs during insertion, an error response is returned.

    Args:
        db: An active asynchronous SQLAlchemy session used for database operations.
        investigation_id: The UUID identifying the investigation to which the events belong.
        user_query: Raw input from the user containing event data in JSON, CSV, YAML, or free-form text.
        user_id: Identifier of the user making the request; passed to the LLM extraction step.

    Returns:
        dict: A response dictionary with the following keys:
            - `type` (str): Either `"events_inserted"` on success or `"error"` on failure.
            - `success` (bool): Indicates whether the operation succeeded.
            - `count` (int, optional): Number of events successfully inserted (present only on success).
            - `message` (str): Human-readable description of the outcome, including a summary of event types on success or an error explanation on failure.
    """
    # Try parsing as structured data first
    events = await parse_structured_events(user_query)

    if not events:
        # Use LLM to extract events from natural language
        events = await llm_extract_events(db, user_id, user_query)

    if not events:
        return {
            "type": "error",
            "success": False,
            "message": "Could not parse event data. Please provide JSON, CSV, YAML, or a clear description.",
        }

    # Insert into events table
    try:
        inserted_count = await insert_events(db, investigation_id, events)

        # Build success message
        event_types = {}
        for event in events:
            event_type = event.get("event_type", "unknown")
            event_types[event_type] = event_types.get(event_type, 0) + 1

        type_summary = ", ".join([f"{count} {etype}" for etype, count in event_types.items()])

        return {
            "type": "events_inserted",
            "success": True,
            "count": inserted_count,
            "message": f"✅ Successfully inserted {inserted_count} event(s): {type_summary}",
        }
    except Exception as e:
        return {"type": "error", "success": False, "message": f"Failed to insert events: {str(e)}"}


async def parse_structured_events(raw_text: str) -> List[Dict[str, Any]]:
    """
    Parse structured event data from a raw text input.

    The function attempts to interpret the provided `raw_text` as one of several common
    structured formats-JSON, YAML, or CSV-in that order.  For each format it loads the
    data, normalises it into a list of dictionaries representing individual events,
    and validates every dictionary with :func:`_is_valid_event`.  If a format is parsed
    successfully and all events are valid, the resulting list is returned immediately.
    If none of the formats can be parsed or any event fails validation, an empty list
    is returned.

    Args:
        raw_text: The unprocessed text that may contain event data in JSON, YAML,
            or CSV format.

    Returns:
        A list of dictionaries, each representing a validated event.  If parsing
        fails for all supported formats or validation does not succeed, the function
        returns an empty list.
    """
    events = []

    # Try JSON first
    try:
        data = json.loads(raw_text)
        if isinstance(data, list):
            events = data
        elif isinstance(data, dict):
            events = [data]

        # Validate events have required fields
        if events and all(_is_valid_event(e) for e in events):
            return events
    except json.JSONDecodeError:
        pass

    # Try YAML
    try:
        data = yaml.safe_load(raw_text)
        if isinstance(data, list):
            events = data
        elif isinstance(data, dict):
            events = [data]

        if events and all(_is_valid_event(e) for e in events):
            return events
    except yaml.YAMLError:
        pass

    # Try CSV
    try:
        reader = csv.DictReader(io.StringIO(raw_text))
        events = list(reader)

        if events and all(_is_valid_event(e) for e in events):
            return events
    except Exception:
        pass

    return []


def _is_valid_event(event: Dict[str, Any]) -> bool:
    """
    Validate that an event dictionary contains the required fields.

    Args:
        event: A mapping representing a single event.

    Returns:
        True if the `event` includes the mandatory `"event_type"` key; otherwise False.
    """
    return "event_type" in event


async def llm_extract_events(
    db: AsyncSession, user_id: int, description: str
) -> List[Dict[str, Any]]:
    """
    Extract structured event data from a natural-language description using a user-specific LLM configuration.

    Args:
        db (AsyncSession): An asynchronous SQLAlchemy session used to retrieve the user's LLM settings.
        user_id (int): Identifier of the user whose LLM configuration should be loaded.
        description (str): The free-form text describing one or more events to be extracted.

    Returns:
        List[Dict[str, Any]]: A list of dictionaries, each representing an event with the keys
            `event_type` (str), `event_ts` (ISO-8601 timestamp string), and `payload`
            (dict) containing event-specific details. Returns an empty list if no LLM is
            configured, the LLM response cannot be parsed, or an error occurs during processing.

    Raises:
        None directly; any exceptions are caught internally, logged, and result in an empty list being returned.
    """
    # Create LLM service from user config
    llm_service = await LLMService.from_user_config(db, user_id)

    if not llm_service:
        # No LLM configured, return empty
        return []

    prompt = f"""Extract structured event data from the following description.

Description: {description}

Respond with a JSON array of events. Each event should have:
- event_type: string (e.g., "login", "file_created", "network_connection")
- event_ts: ISO 8601 timestamp (use current time if not specified)
- payload: object with event details

Example:
[
  {{
    "event_type": "login",
    "event_ts": "2025-01-15T10:30:00Z",
    "payload": {{"user": "admin", "source_ip": "192.168.1.100"}}
  }}
]

Respond with ONLY the JSON array, no other text."""

    try:
        # Call LLM via centralized service
        data = await llm_service.call_llm(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1000,
            temperature=0.1,
            enforce_context_limit=False,
        )

        # Extract response text
        response_text = await llm_service.extract_text_response(data)

        if not response_text:
            return []

        response_text = str(response_text).strip()

        # Extract JSON from response (handle markdown code blocks)
        if response_text.startswith("```json"):
            response_text = response_text[7:]
        if response_text.startswith("```"):
            response_text = response_text[3:]
        if response_text.endswith("```"):
            response_text = response_text[:-3]
        response_text = response_text.strip()

        # Try to parse JSON from response
        events = json.loads(response_text)
        if isinstance(events, list):
            return events
        elif isinstance(events, dict):
            return [events]

        return []
    except Exception as e:
        logger.error(f"LLM extraction failed: {e}")
        return []


async def insert_events(
    db: AsyncSession, investigation_id: UUID, events: List[Dict[str, Any]]
) -> int:
    """
    Insert a collection of event records into the unified events table for a specific investigation.

    This coroutine iterates over each provided event dictionary, normalizes its timestamp,
    determines the event type, and separates any additional fields into a JSON payload.
    Each event is inserted with a single parameterised SQL statement; after all inserts
    are executed the transaction is committed. The function returns the total number of
    events successfully written.

    Args:
        db: An active asynchronous SQLAlchemy session used to execute statements and commit
            the transaction.
        investigation_id: The UUID identifying the investigation to which the events belong.
        events: A list of dictionaries, each representing an event. Expected keys include
            `event_type` (defaults to `"unknown"` if absent), `event_ts` (a datetime or
            ISO-8601 string; falls back to the current UTC time on parsing failure), and
            `artifact_id`. All other key/value pairs are stored in the `payload` column
            as JSON.

    Returns:
        The count of events that were inserted into the database.

    Raises:
        Any exception raised by the underlying database driver or SQLAlchemy during execution
        (e.g., connection errors, constraint violations) will propagate to the caller.
    """
    if not events:
        return 0

    inserted = 0
    for event in events:
        # Extract fields
        event_type = event.get("event_type", "unknown")
        event_ts_raw = event.get("event_ts")
        artifact_id = event.get("artifact_id")

        # Parse timestamp
        if event_ts_raw:
            if isinstance(event_ts_raw, str):
                try:
                    event_ts = datetime.fromisoformat(event_ts_raw.replace("Z", "+00:00"))
                except ValueError:
                    event_ts = datetime.now(timezone.utc)
            elif isinstance(event_ts_raw, datetime):
                event_ts = event_ts_raw
            else:
                event_ts = datetime.now(timezone.utc)
        else:
            event_ts = datetime.now(timezone.utc)

        # Build payload (everything except known fields)
        payload = {
            k: v for k, v in event.items() if k not in ("event_type", "event_ts", "artifact_id")
        }

        # Insert query
        query = text(
            """
            INSERT INTO events (investigation_id, event_ts, artifact_id, event_type, payload)
            VALUES (:investigation_id, :event_ts, :artifact_id, :event_type, CAST(:payload AS jsonb))
        """
        )

        await db.execute(
            query,
            {
                "investigation_id": str(investigation_id),
                "event_ts": event_ts,
                "artifact_id": artifact_id,
                "event_type": event_type,
                "payload": json.dumps(payload),
            },
        )
        inserted += 1

    await db.commit()
    return inserted


__all__ = ["handle_event_insertion"]
