import json
from typing import Dict, Any, Optional, List
from datetime import datetime
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.utils.log_setup import get_logger
from app.utils.security import sanitize_log_message

logger = get_logger(__name__)


# Import embedding service (but handle gracefully if not available)
try:
    import sys
    import os

    # Add parent directory to path for imports when running as worker
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
    from app.services.rag.embedding_service import (
        generate_embedding_for_timeline_entry,
        generate_embeddings_for_timeline_entries,
    )

    EMBEDDINGS_AVAILABLE = True
except ImportError:
    logger.warning("Embedding service not available - embeddings will not be generated")
    EMBEDDINGS_AVAILABLE = False
    generate_embedding_for_timeline_entry = None  # type: ignore
    generate_embeddings_for_timeline_entries = None  # type: ignore


async def register_timeline_entry(
    db: AsyncSession,
    investigation_id: str,
    event_id: int,
    title: str,
    entry_type: str = "event",
    description: Optional[str] = None,
    tags: Optional[List[str]] = None,
    stats: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Register an evidence entry on the investigation timeline by event identifier.

    This function retrieves the full event record (timestamp, type, payload) from the `events` table and creates a corresponding entry in `timeline_entries`. It guarantees that each event appears at most once per investigation; if a duplicate is detected it returns the existing entry instead of creating a new one. Optional tags, description, and statistics updates are applied, and an embedding may be generated when the optional embedding utilities are available.

    Args:
        db: An active `AsyncSession` used to execute database queries.
        investigation_id: The UUID string identifying the investigation to which the entry belongs.
        event_id: Primary key of the source event in the `events` table (required).
        title: Human-readable short title for the timeline entry.
        entry_type: Category of the entry; must be one of `'event'`, `'finding'`, `'observation'` or `'note'`. Invalid values are coerced to `'event'`.
        description: Optional longer text describing the entry.
        tags: Optional list (or comma-separated string) of tag identifiers for categorisation.
        stats: Optional mutable mapping that will be updated with counters such as `timeline_entries_created` and tag usage.

    Returns:
        A dictionary containing at least the following keys:
            * `entry_id` - Primary key of the timeline entry (new or existing).
            * `title` - Title supplied to the function.
            * `timestamp` - ISO-8601 string of the event’s timestamp.
            * `entry_type` - Normalised type of the entry.
            * `event_id` - The source event identifier.
            * `is_duplicate` - Boolean flag indicating whether an existing entry was returned.
        Additional keys may be present:
            * `message` - Human-readable note when a duplicate is detected or an error occurs.
            * `error` - Error description if the operation fails (e.g., missing event).

    Raises:
        No exceptions are propagated; all errors are captured and reported in the returned dictionary.
    """
    # Check if this event is already on the timeline (enforce unique constraint)
    logger.info(f"Checking for existing timeline entry for event {event_id}")

    existing_entry_result = await db.execute(
        text(
            """
            SELECT entry_id, title, timestamp, entry_type
            FROM timeline_entries
            WHERE investigation_id = :investigation_id
              AND event_id = :event_id
        """
        ),
        {"investigation_id": investigation_id, "event_id": event_id},
    )

    existing_entry = existing_entry_result.fetchone()

    if existing_entry:
        logger.info(
            f"Event {event_id} already on timeline as entry {existing_entry[0]}: '{existing_entry[1]}'. "
            "Returning existing entry."
        )
        return {
            "entry_id": existing_entry[0],
            "title": existing_entry[1],
            "timestamp": existing_entry[2].isoformat(),
            "entry_type": existing_entry[3],
            "event_id": event_id,
            "is_duplicate": True,
            "message": f"Event {event_id} is already on the timeline",
        }

    # Fetch the complete event data from the events table
    logger.info(f"Fetching event {event_id} for timeline entry")

    event_result = await db.execute(
        text(
            """
            SELECT event_id, event_ts, event_type, artifact_id, payload
            FROM events
            WHERE investigation_id = :investigation_id
              AND event_id = :event_id
        """
        ),
        {"investigation_id": investigation_id, "event_id": event_id},
    )

    event_row = event_result.fetchone()

    if not event_row:
        logger.error(f"Event {event_id} not found in investigation {sanitize_log_message(investigation_id)}")
        return {"error": f"Event {event_id} not found"}

    # Extract event data
    event_timestamp = event_row[1]
    event_type = event_row[2]
    artifact_id = event_row[3]
    event_payload = event_row[4]

    # Validate entry_type
    valid_types = ["event", "finding", "observation", "note"]
    if entry_type not in valid_types:
        logger.warning(f"Invalid entry_type '{sanitize_log_message(entry_type)}', defaulting to 'event'")
        entry_type = "event"

    # Build the data field with complete event information
    # This includes the full payload so analysts can see all forensic context
    parsed_data: Dict[str, Any] = {
        "source_event_id": event_id,
        "event_type": event_type,
        "artifact_id": artifact_id,
        "payload": event_payload,  # Complete raw event data
    }

    # Handle tags parameter
    parsed_tags: List[str]
    if isinstance(tags, str):
        parsed_tags = [tag.strip() for tag in tags.split(",") if tag.strip()]
    elif tags is None:
        parsed_tags = []
    else:
        parsed_tags = tags

    logger.info(
        f"Registering timeline entry: event_id={event_id}, timestamp={event_timestamp.isoformat()}, "
        f"type='{entry_type}', title='{title}', description={description is not None}, tags={parsed_tags}"
    )

    # Insert timeline entry with ON CONFLICT handling
    # This is a safety net in case the unique constraint check above missed a concurrent insert
    try:
        result = await db.execute(
            text(
                """
                INSERT INTO timeline_entries
                (investigation_id, event_id, timestamp, entry_type, title, description, data, tags, is_visible)
                VALUES (:investigation_id, :event_id, :timestamp, :entry_type, :title, :description,
                        CAST(:data AS jsonb), CAST(:tags AS TEXT[]), true)
                ON CONFLICT (investigation_id, event_id) DO NOTHING
                RETURNING entry_id
            """
            ),
            {
                "investigation_id": investigation_id,
                "event_id": event_id,
                "timestamp": event_timestamp,
                "entry_type": entry_type,
                "title": title,
                "description": description,
                "data": json.dumps(parsed_data),
                "tags": parsed_tags,
            },
        )

        entry_id = result.scalar()

        # If entry_id is None, it means ON CONFLICT triggered (duplicate)
        if entry_id is None:
            await db.rollback()
            logger.warning(
                f"Concurrent insert detected for event {event_id}, fetching existing entry"
            )

            # Fetch the existing entry
            existing_result = await db.execute(
                text(
                    """
                    SELECT entry_id, title, timestamp, entry_type
                    FROM timeline_entries
                    WHERE investigation_id = :investigation_id
                      AND event_id = :event_id
                """
                ),
                {"investigation_id": investigation_id, "event_id": event_id},
            )

            existing_row = existing_result.fetchone()

            if existing_row:
                return {
                    "entry_id": existing_row[0],
                    "title": existing_row[1],
                    "timestamp": existing_row[2].isoformat(),
                    "entry_type": existing_row[3],
                    "event_id": event_id,
                    "is_duplicate": True,
                    "message": f"Event {event_id} is already on the timeline (concurrent insert)",
                }
            else:
                return {"error": "Failed to create or retrieve timeline entry"}

        await db.commit()

    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to insert timeline entry: {sanitize_log_message(str(e))}")
        return {"error": f"Failed to create timeline entry: {sanitize_log_message(str(e))}"}

    # Update stats if provided
    if stats is not None:
        stats["timeline_entries_created"] = stats.get("timeline_entries_created", 0) + 1
        if "tags_applied" in stats:
            stats["tags_applied"].update(parsed_tags)

    logger.info(
        f"✓ Created timeline entry {entry_id}: '{title}' at {event_timestamp.isoformat()} "
        f"(type={entry_type}, event_id={event_id}, description={description is not None}, tags={parsed_tags})"
    )

    # NOTE: Embeddings are now generated in batch at the end of each iteration
    # See batch_generate_embeddings() - called after all timeline entries are registered

    return {
        "entry_id": entry_id,
        "title": title,
        "timestamp": event_timestamp.isoformat(),
        "entry_type": entry_type,
        "event_id": event_id,
        "is_duplicate": False,
    }


async def register_finding(
    db: AsyncSession,
    investigation_id: str,
    title: str,
    description: str,
    timestamp: Optional[str] = None,
    severity: str = "medium",
    evidence_event_ids: Optional[List[int]] = None,
    tags: Optional[List[str]] = None,
    stats: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Register an investigative finding in the timeline.

    This function creates a new timeline entry of type `finding` that represents a high-level conclusion derived from one or more source events. Findings are not tied to a single event_id; instead they may reference multiple evidence events and include severity, tags, and optional statistical updates. If embeddings are available, an asynchronous embedding is generated for the newly created finding.

    Args:
        db: An active `AsyncSession` used to execute database statements.
        investigation_id: The UUID of the investigation to which the finding belongs.
        title: A concise title summarising the finding.
        description: A detailed narrative describing the finding and its context.
        timestamp: ISO-8601 formatted string indicating when the finding was identified. If omitted, the current UTC time is used.
        severity: Severity level for the finding; one of `'low'`, `'medium'`, `'high'` or `'critical'`. Defaults to `'medium'`.
        evidence_event_ids: Optional list of event identifiers that provide supporting evidence for the finding.
        tags: Optional list of tag strings to associate with the finding. The function ensures that a `'finding'` tag and a severity-specific tag (e.g., `'severity_high'`) are always present.
        stats: Optional dictionary used to accumulate statistics such as the number of timeline entries created or tags applied.

    Returns:
        A dictionary containing:
            entry_id: The primary key of the newly inserted timeline entry.
            title: The title supplied to the function.
            timestamp: ISO-8601 string representation of the stored timestamp.
            entry_type: Literal `'finding'` indicating the type of entry created.
            severity: The severity level that was recorded.

    Side Effects:
        * Inserts a row into the `timeline_entries` table.
        * Commits the transaction on the provided session.
        * May update the `stats` dictionary in-place when supplied.
        * If embeddings are enabled, triggers asynchronous generation of an embedding for the finding and logs the outcome.
    """
    # Use current time if timestamp not provided
    if timestamp is None:
        parsed_timestamp = datetime.utcnow()
    else:
        try:
            parsed_timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            parsed_timestamp = datetime.utcnow()

    # Build finding data
    finding_data: Dict[str, Any] = {
        "severity": severity,
        "finding_type": "agent_generated",
    }

    if evidence_event_ids:
        finding_data["evidence_event_ids"] = evidence_event_ids
        finding_data["evidence_count"] = len(evidence_event_ids)

    # Prepare tags
    finding_tags = tags or []
    if "finding" not in finding_tags:
        finding_tags.append("finding")
    if severity:
        finding_tags.append(f"severity_{severity}")

    # Handle tags parameter
    parsed_tags: List[str]
    if isinstance(finding_tags, str):
        parsed_tags = [tag.strip() for tag in finding_tags.split(",") if tag.strip()]
    elif finding_tags is None:
        parsed_tags = []
    else:
        parsed_tags = finding_tags

    logger.info(
        f"Registering finding: '{title}' (severity={severity}, "
        f"evidence_count={len(evidence_event_ids) if evidence_event_ids else 0})"
    )

    # Insert finding directly (findings don't have a single source event_id)
    try:
        result = await db.execute(
            text(
                """
                INSERT INTO timeline_entries
                (investigation_id, event_id, timestamp, entry_type, title, description, data, tags, is_visible)
                VALUES (:investigation_id, NULL, :timestamp, 'finding', :title, :description,
                        CAST(:data AS jsonb), CAST(:tags AS TEXT[]), true)
                RETURNING entry_id
            """
            ),
            {
                "investigation_id": investigation_id,
                "timestamp": parsed_timestamp,
                "title": title,
                "description": description,
                "data": json.dumps(finding_data),
                "tags": parsed_tags,
            },
        )

        entry_id = result.scalar()
        await db.commit()
    except Exception as e:
        logger.error(f"Failed to register finding: {sanitize_log_message(str(e))}", exc_info=True)
        try:
            await db.rollback()
        except Exception as rollback_error:
            logger.error(f"Rollback failed: {sanitize_log_message(str(rollback_error))}")
        return {"error": f"Failed to register finding: {sanitize_log_message(str(e))}"}

    # Update stats if provided
    if stats is not None:
        stats["timeline_entries_created"] = stats.get("timeline_entries_created", 0) + 1
        if "tags_applied" in stats:
            stats["tags_applied"].update(parsed_tags)

    logger.info(
        f"✓ Created finding {entry_id}: '{title}' at {parsed_timestamp.isoformat()} "
        f"(severity={severity}, evidence_count={len(evidence_event_ids) if evidence_event_ids else 0})"
    )

    # NOTE: Embeddings are now generated in batch at the end of each iteration
    # See batch_generate_embeddings() - called after all timeline entries are registered

    return {
        "entry_id": entry_id,
        "title": title,
        "timestamp": parsed_timestamp.isoformat(),
        "entry_type": "finding",
        "severity": severity,
    }


async def batch_generate_embeddings(
    db: AsyncSession,
    investigation_id: str,
    user_id: int = 1,
) -> int:
    """
    Generate embeddings for all timeline entries without embeddings in batch.

    Called at the end of each iteration to batch-process all newly created
    timeline entries, which is much more efficient than generating embeddings
    serially during registration.

    Parameters
    ----------
    db: AsyncSession
        Database session.
    investigation_id: str
        Investigation identifier.
    user_id: int, default 1
        User ID for LLM configuration.

    Returns
    -------
    int
        Number of embeddings successfully created.
    """
    if not EMBEDDINGS_AVAILABLE or not generate_embeddings_for_timeline_entries:
        return 0

    try:
        # Find all timeline entries without embeddings for this investigation
        result = await db.execute(
            text(
                """
                SELECT entry_id
                FROM timeline_entries
                WHERE investigation_id = :investigation_id
                AND embedding_id IS NULL
                ORDER BY entry_id
            """
            ),
            {"investigation_id": investigation_id},
        )
        rows = result.fetchall()
        entry_ids = [row[0] for row in rows]

        if not entry_ids:
            return 0

        logger.info(
            f"Batch generating embeddings for {len(entry_ids)} timeline entries "
            f"in investigation {investigation_id}"
        )

        # Generate embeddings in batch
        count = await generate_embeddings_for_timeline_entries(
            db=db,
            entry_ids=entry_ids,
            user_id=user_id,
        )

        logger.info(f"Successfully generated {count} embeddings in batch")
        return count

    except Exception as e:
        logger.error(f"Failed to batch generate embeddings: {sanitize_log_message(str(e))}", exc_info=True)
        try:
            await db.rollback()
        except Exception as rollback_error:
            logger.error(f"Rollback failed: {sanitize_log_message(str(rollback_error))}")
        return 0


async def link_to_event(
    db: AsyncSession,
    entry_id: int,
    event_id: int,
) -> Dict[str, Any]:
    """
    Link a timeline entry to its source event in the database.

    This coroutine updates the specified timeline entry so that it references the given
    event identifier.  The `event_id` is stored both in the dedicated `event_id`
    column and inside the JSONB `data` field under the key `source_event_id`.
    If the entry does not exist, an error dictionary is returned.

    Args:
        db: An active :class:`sqlalchemy.ext.asyncio.AsyncSession` used to execute
            the update query.
        entry_id: The primary-key identifier of the timeline entry to be linked.
        event_id: The identifier of the source event that should be associated with
            the timeline entry.

    Returns:
        dict: A mapping containing:

            - `entry_id` (int): Echoes the provided `entry_id` when linking succeeds.
            - `event_id` (int): Echoes the provided `event_id` when linking succeeds.
            - `status` (str): The string `"linked"` indicating a successful operation.

        If no entry matches `entry_id`, the dictionary contains an `error` key
        with a descriptive message instead of the success fields.
    """
    logger.info(f"Linking timeline entry {entry_id} to event {event_id}")

    try:
        # Update the entry to reference the event
        result = await db.execute(
            text(
                """
                UPDATE timeline_entries
                SET event_id = :event_id,
                    data = jsonb_set(
                        COALESCE(data, '{}'::jsonb),
                        '{source_event_id}',
                        to_jsonb(:event_id::bigint)
                    )
                WHERE entry_id = :entry_id
                RETURNING entry_id
            """
            ),
            {
                "entry_id": entry_id,
                "event_id": event_id,
            },
        )

        updated_row = result.fetchone()
        await db.commit()

        if not updated_row:
            logger.error(f"Failed to link entry {sanitize_log_message(str(entry_id))} to event {sanitize_log_message(str(event_id))}")
            return {"error": "Timeline entry not found"}

        logger.info(f"✓ Linked timeline entry {entry_id} to event {event_id}")

        return {"entry_id": entry_id, "event_id": event_id, "status": "linked"}
    except Exception as e:
        logger.error(f"Failed to link timeline entry: {sanitize_log_message(str(e))}", exc_info=True)
        try:
            await db.rollback()
        except Exception as rollback_error:
            logger.error(f"Rollback failed: {sanitize_log_message(str(rollback_error))}")
        return {"error": f"Failed to link timeline entry: {sanitize_log_message(str(e))}"}
