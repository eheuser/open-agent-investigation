import logging
import json
from typing import Dict, Any, Optional, List
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from dateutil import parser as date_parser

logger = logging.getLogger(__name__)


async def search_events_by_type(
    db: AsyncSession,
    investigation_id: str,
    event_type: str,
    limit: int = 50,
    offset: int = 0,
    stats: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Search events of a given investigation by their type with optional wildcard support and pagination.

    Parameters
    ----------
    db : AsyncSession
        Asynchronous SQLAlchemy session used to execute queries against the database.
    investigation_id : str
        Identifier of the investigation whose events should be searched.
    event_type : str
        Event type filter. May contain `*` as a wildcard, which is translated to the SQL `LIKE` pattern `%`.
    limit : int, optional
        Maximum number of events to return (default 50). The value is coerced to an integer and capped at 50.
    offset : int, optional
        Number of events to skip before starting to collect results (default 0). The value is coerced to an integer.
    stats : dict[str, Any] | None, optional
        Optional mutable mapping that will be updated with a `events_analyzed` counter reflecting the number of events returned.

    Returns
    -------
    dict[str, Any]
        A dictionary containing pagination metadata and the list of matching events. Keys include:

        * `count` - Number of events in the current page.
        * `total_count` - Total number of events that match the filter across all pages.
        * `current_page` - One-based index of the current page calculated from `offset` and `limit`.
        * `total_pages` - Total number of pages available given `total_count` and `limit`.
        * `events` - List of event dictionaries, each with keys `event_id`, `event_ts` (ISO-8601 string), `event_type`, `artifact_id`, and `payload`.
        * `has_more` - Boolean indicating whether additional pages are available beyond the current one.
        * `limit` - The effective limit applied to the query.
        * `offset` - The offset used for the query.

    Notes
    -----
    * Wildcard characters in `event_type` are converted by replacing `*` with `%` before being passed to the SQL `LIKE` clause.
    * The function logs informational messages about the search parameters, result size, and pagination details.
    * If `stats` is provided, its `events_analyzed` entry is incremented by the number of events returned.
    """
    # Ensure limit and offset are integers (LLM may pass strings)
    limit = int(limit) if limit else 10
    offset = int(offset) if offset else 0
    limit = min(limit, 50)  # Cap at 50

    # Convert wildcard to SQL LIKE pattern
    pattern = event_type.replace("*", "%")

    logger.info(f"Searching events by type: pattern='{pattern}', limit={limit}, offset={offset}")

    result = await db.execute(
        text(
            """
            SELECT event_id, event_ts, event_type, artifact_id, payload
            FROM events
            WHERE investigation_id = :investigation_id
              AND event_type LIKE :pattern
            ORDER BY event_ts DESC
            LIMIT :limit OFFSET :offset
        """
        ),
        {
            "investigation_id": investigation_id,
            "pattern": pattern,
            "limit": limit,
            "offset": offset,
        },
    )

    rows = result.fetchall()
    events = [
        {
            "event_id": row[0],
            "event_ts": row[1].isoformat() if row[1] else None,
            "event_type": row[2],
            "artifact_id": row[3],
            "payload": row[4],
        }
        for row in rows
    ]

    if stats is not None:
        stats["events_analyzed"] = stats.get("events_analyzed", 0) + len(events)

    # Get total count for pagination info
    count_result = await db.execute(
        text(
            """
            SELECT COUNT(*)
            FROM events
            WHERE investigation_id = :investigation_id
              AND event_type LIKE :pattern
        """
        ),
        {"investigation_id": investigation_id, "pattern": pattern},
    )
    total_count = count_result.scalar() or 0

    # Calculate pagination info
    current_page = (offset // limit) + 1 if limit > 0 else 1
    total_pages = (total_count + limit - 1) // limit if limit > 0 else 1

    logger.info(
        f"search_events_by_type returned {len(events)} events (pattern='{pattern}'), "
        f"page {current_page}/{total_pages}, total={total_count}"
    )

    return {
        "count": len(events),
        "total_count": total_count,
        "current_page": current_page,
        "total_pages": total_pages,
        "events": events,
        "has_more": len(events) == limit,
        "limit": limit,
        "offset": offset,
    }


async def search_events_by_timerange(
    db: AsyncSession,
    investigation_id: str,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    event_type: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    stats: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Search events within an investigation filtered by optional time range and event type, returning paginated results.

    Parameters
    ----------
    db : AsyncSession
        Asynchronous SQLAlchemy session used to execute queries.
    investigation_id : str
        Identifier of the investigation whose events are being queried.
    start_time : Optional[str], default=None
        ISO-8601 formatted timestamp string defining the lower bound (inclusive) for `event_ts`. If provided, it is parsed to a datetime; parsing failures are logged and passed through to the database.
    end_time : Optional[str], default=None
        ISO-8601 formatted timestamp string defining the upper bound (inclusive) for `event_ts`. Handled analogously to *start_time*.
    event_type : Optional[str], default=None
        Event type filter supporting `*` as a wildcard, which is translated to SQL `LIKE` pattern syntax.
    limit : int, default=50
        Maximum number of events to return. The value is coerced to an integer, defaults to 10 when falsy, and is capped at 50.
    offset : int, default=0
        Number of rows to skip before returning results; coerced to an integer.
    stats : Optional[Dict[str, Any]], default=None
        Mutable mapping that will be updated with a key `events_analyzed` incremented by the number of events returned.

    Returns
    -------
    dict
        A dictionary containing pagination metadata and the list of matching events:

        - `count` (int): Number of events in the current page.
        - `total_count` (int): Total number of events that satisfy the filters.
        - `current_page` (int): 1-based index of the current page.
        - `total_pages` (int): Total pages available given *limit*.
        - `events` (list[dict]): List of event objects, each with keys `event_id`, `event_ts` (ISO string), `event_type`, `artifact_id`, and `payload`.
        - `has_more` (bool): True if another page may exist (i.e., the current page is full).
        - `limit` (int): Effective limit applied to the query.
        - `offset` (int): Offset used for the query.

    Side Effects
    ------------
    Logs informational messages about the search parameters, result counts, and pagination details. May modify the *stats* dictionary if provided.
    """
    # Ensure limit and offset are integers
    limit = int(limit) if limit else 10
    offset = int(offset) if offset else 0
    limit = min(limit, 50)

    conditions = []
    params: Dict[str, Any] = {"limit": limit, "offset": offset}

    if start_time:
        conditions.append("event_ts >= :start_time")
        # Parse ISO timestamp string to datetime object
        try:
            params["start_time"] = date_parser.parse(start_time)
        except (ValueError, TypeError) as e:
            logger.warning(f"Failed to parse start_time '{start_time}': {e}")
            params["start_time"] = start_time  # Let DB handle the error

    if end_time:
        conditions.append("event_ts <= :end_time")
        # Parse ISO timestamp string to datetime object
        try:
            params["end_time"] = date_parser.parse(end_time)
        except (ValueError, TypeError) as e:
            logger.warning(f"Failed to parse end_time '{end_time}': {e}")
            params["end_time"] = end_time  # Let DB handle the error

    if event_type:
        pattern = event_type.replace("*", "%")
        conditions.append("event_type LIKE :pattern")
        params["pattern"] = pattern

    where_clause = " AND ".join(conditions) if conditions else "TRUE"

    logger.info(f"Searching events by timerange: {params}")

    result = await db.execute(
        text(
            f"""
            SELECT event_id, event_ts, event_type, artifact_id, payload
            FROM events
            WHERE investigation_id = :investigation_id
              AND {where_clause}
            ORDER BY event_ts DESC
            LIMIT :limit OFFSET :offset
        """
        ),
        {"investigation_id": investigation_id, **params},
    )

    rows = result.fetchall()
    events = [
        {
            "event_id": row[0],
            "event_ts": row[1].isoformat() if row[1] else None,
            "event_type": row[2],
            "artifact_id": row[3],
            "payload": row[4],
        }
        for row in rows
    ]

    if stats is not None:
        stats["events_analyzed"] = stats.get("events_analyzed", 0) + len(events)

    # Get total count for pagination info
    count_result = await db.execute(
        text(
            f"""
            SELECT COUNT(*)
            FROM events
            WHERE investigation_id = :investigation_id
              AND {where_clause}
        """
        ),
        {"investigation_id": investigation_id, **params},
    )
    total_count = count_result.scalar() or 0

    # Calculate pagination info
    current_page = (offset // limit) + 1 if limit > 0 else 1
    total_pages = (total_count + limit - 1) // limit if limit > 0 else 1

    logger.info(
        f"search_events_by_timerange returned {len(events)} events, "
        f"page {current_page}/{total_pages}, total={total_count}"
    )

    return {
        "count": len(events),
        "total_count": total_count,
        "current_page": current_page,
        "total_pages": total_pages,
        "events": events,
        "has_more": len(events) == limit,
        "limit": limit,
        "offset": offset,
    }


async def search_events_by_content(
    db: AsyncSession,
    investigation_id: str,
    search_text: Optional[str] = None,  # Changed from search_term to match YAML
    search_term: Optional[str] = None,  # Keep for backward compatibility
    event_type: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    stats: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Search event payloads for a given text within an investigation.

    Parameters
    ----------
    db: AsyncSession
        Asynchronous SQLAlchemy session used to execute queries.
    investigation_id: str
        Identifier of the investigation whose events are being searched.
    search_text: Optional[str], default=None
        Text to search for in the `payload` field. Takes precedence over `search_term`.
    search_term: Optional[str], default=None
        Back-compatible alias for `search_text`; used only when `search_text` is not provided.
    event_type: Optional[str], default=None
        If supplied, filters events whose `event_type` matches the pattern. Wildcards using `*` are translated to SQL `%`.
    limit: int, default=50
        Maximum number of events to return (capped at 50). Values less than or equal to zero are treated as the default of 10.
    offset: int, default=0
        Number of rows to skip before returning results; used for pagination.
    stats: Optional[Dict[str, Any]], default=None
        Mutable mapping that will be updated with a `events_analyzed` counter reflecting how many events were processed.

    Returns
    -------
    Dict[str, Any]
        A dictionary containing pagination metadata and the matching events:

        - `count` (int): Number of events returned in this page.
        - `total_count` (int): Total number of events that match the criteria.
        - `current_page` (int): 1-based index of the current page.
        - `total_pages` (int): Total pages available given the limit.
        - `search_text` (str): The effective search string used.
        - `events` (list[dict]): List of event dictionaries with keys `event_id`, `event_ts` (ISO-8601 string), `event_type`, `artifact_id`, and `payload`.
        - `has_more` (bool): `True` if more results are available beyond this page.
        - `limit` (int): The limit applied to the query.
        - `offset` (int): The offset applied to the query.

    Raises
    ------
    ValueError
        If neither `search_text` nor `search_term` is provided.
    """
    # Support both parameter names (search_text from YAML, search_term for backward compat)
    search_value = search_text or search_term
    if not search_value:
        return {"error": "Missing required parameter: search_text"}

    # Ensure limit and offset are integers
    limit = int(limit) if limit else 10
    offset = int(offset) if offset else 0
    limit = min(limit, 50)

    conditions = ["payload::text ILIKE :search_pattern"]
    params: Dict[str, Any] = {
        "search_pattern": f"%{search_value}%",
        "limit": limit,
        "offset": offset,
    }

    if event_type:
        pattern = event_type.replace("*", "%")
        conditions.append("event_type LIKE :event_pattern")
        params["event_pattern"] = pattern

    where_clause = " AND ".join(conditions)

    logger.info(
        f"Searching events by content: search_text='{search_value}', event_type={event_type}"
    )

    result = await db.execute(
        text(
            f"""
            SELECT event_id, event_ts, event_type, artifact_id, payload
            FROM events
            WHERE investigation_id = :investigation_id
              AND {where_clause}
            ORDER BY event_ts DESC
            LIMIT :limit OFFSET :offset
        """
        ),
        {"investigation_id": investigation_id, **params},
    )

    rows = result.fetchall()
    events = [
        {
            "event_id": row[0],
            "event_ts": row[1].isoformat() if row[1] else None,
            "event_type": row[2],
            "artifact_id": row[3],
            "payload": row[4],
        }
        for row in rows
    ]

    if stats is not None:
        stats["events_analyzed"] = stats.get("events_analyzed", 0) + len(events)

    # Get total count for pagination info
    count_result = await db.execute(
        text(
            f"""
            SELECT COUNT(*)
            FROM events
            WHERE investigation_id = :investigation_id
              AND {where_clause}
        """
        ),
        {"investigation_id": investigation_id, **params},
    )
    total_count = count_result.scalar() or 0

    # Calculate pagination info
    current_page = (offset // limit) + 1 if limit > 0 else 1
    total_pages = (total_count + limit - 1) // limit if limit > 0 else 1

    logger.info(
        f"search_events_by_content returned {len(events)} events (search_text='{search_value}'), "
        f"page {current_page}/{total_pages}, total={total_count}"
    )

    return {
        "count": len(events),
        "total_count": total_count,
        "current_page": current_page,
        "total_pages": total_pages,
        "search_text": search_value,
        "events": events,
        "has_more": len(events) == limit,
        "limit": limit,
        "offset": offset,
    }


async def get_event_by_id(
    db: AsyncSession,
    investigation_id: str,
    event_id: int,
    stats: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Fetches a single security event record identified by its `event_id` within the specified investigation.

    Parameters
    ----------
    db : AsyncSession
        Asynchronous SQLAlchemy session used to execute the query.
    investigation_id : str
        Identifier of the investigation to which the event belongs.
    event_id : int
        Unique identifier of the event to retrieve.
    stats : dict[str, Any] | None, optional
        Optional mutable mapping that will be updated with a counter named `events_analyzed`. If provided, the function increments this counter each time an event is successfully retrieved.

    Returns
    -------
    dict[str, Any]
        A dictionary containing the event data with the following keys:

        - `event_id` (int): The ID of the event.
        - `event_ts` (str | None): ISO-8601 formatted timestamp of the event, or `None` if not available.
        - `event_type` (str | None): Type/category of the event.
        - `artifact_id` (int | None): Identifier of the associated artifact, if any.
        - `payload` (Any): Raw payload stored for the event.

        If no matching row is found, returns a dictionary with a single key `error` describing the missing event.
    """
    result = await db.execute(
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

    row = result.fetchone()

    if not row:
        return {"error": f"Event {event_id} not found"}

    if stats is not None:
        stats["events_analyzed"] = stats.get("events_analyzed", 0) + 1

    return {
        "event_id": row[0],
        "event_ts": row[1].isoformat() if row[1] else None,
        "event_type": row[2],
        "artifact_id": row[3],
        "payload": row[4],
    }


async def query_jsonb_field(
    db: AsyncSession,
    investigation_id: str,
    jsonb_path: str,
    operator: str = "=",
    value: Optional[str] = None,
    event_type: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    stats: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Query events using a JSONB path expression for deep inspection of the event payload.

    This function builds and executes a parameterized SQL query against the `events` table, allowing callers to filter on a specific field inside the JSONB `payload` column.  The field is identified by a dotted path (e.g., `system.Computer`) and can be compared with a variety of operators, including equality, inequality, range comparisons, pattern matching, and special string-matching helpers (CONTAINS, STARTS_WITH, ENDS_WITH).  If *value* is omitted the function performs an existence check for the specified path.

    The query also supports optional filtering by event type (wildcards are translated to SQL `LIKE` patterns) and pagination via *limit* and *offset*.  Statistics about processed events can be accumulated in a mutable *stats* dictionary passed by reference.

    Args:
        db: An active :class:`sqlalchemy.ext.asyncio.AsyncSession` used to execute the query.
        investigation_id: Identifier of the investigation whose events should be searched.
        jsonb_path: Dotted notation describing the JSONB field to filter (e.g., `system.Computer`).
        operator: Comparison operator.  Supported values are `=`, `!=`, `>`, `<`, `>=`,
            `<=`, `LIKE`, `ILIKE`, `CONTAINS`, `STARTS_WITH` and `ENDS_WITH`.
            The check is case-insensitive for the string-matching helpers.
        value: Value to compare against.  Required for all operators except existence checks
            (when *value* is `None`).
        event_type: Optional filter on the `event_type` column; wildcards (`*`) are converted
            to SQL `%` patterns.
        limit: Maximum number of events to return (capped at 50).  If falsy, defaults to 10.
        offset: Number of rows to skip before returning results.  If falsy, defaults to 0.
        stats: Optional mutable mapping that will be updated with a `events_analyzed` counter
            reflecting the number of events processed in this call.

    Returns:
        A dictionary containing pagination and result information:

        - `count` (int): Number of events returned in this response.
        - `total_count` (int): Total number of matching events across all pages.
        - `current_page` (int): 1-based index of the current page.
        - `total_pages` (int): Total number of pages given the *limit*.
        - `events` (list[dict]): List of event objects, each with keys
          `event_id`, `event_ts` (ISO-8601 string), `event_type`,
          `artifact_id` and `payload`.
        - `has_more` (bool): `True` if more results are available beyond the current page.
        - `limit` (int): Effective limit applied to the query.
        - `offset` (int): Offset used for the query.
        - `query` (dict): Echo of the JSONB search parameters (path, operator, value).

    Raises:
        No exceptions are propagated; any error encountered during execution is caught,
        logged, and returned as a dictionary with an `error` key containing the exception
        message.
    """
    # Ensure limit and offset are integers
    limit = int(limit) if limit else 10
    offset = int(offset) if offset else 0
    limit = min(limit, 50)

    # Validate operator
    valid_operators = [
        "=",
        "!=",
        ">",
        "<",
        ">=",
        "<=",
        "LIKE",
        "ILIKE",
        "CONTAINS",
        "STARTS_WITH",
        "ENDS_WITH",
    ]
    if operator.upper() not in [op.upper() for op in valid_operators]:
        return {
            "error": f"Invalid operator '{operator}'. Must be one of: {', '.join(valid_operators)}"
        }

    conditions = []
    params: Dict[str, Any] = {"limit": limit, "offset": offset}

    # Build JSONB query condition
    if value is not None:
        # Handle different operator types
        if operator.upper() in ["LIKE", "ILIKE"]:
            # Convert user-friendly * wildcards to SQL % wildcards
            sql_value = value.replace("*", "%")
            conditions.append(f"payload->>:jsonb_path {operator.upper()} :value")
            params["value"] = sql_value
            params["jsonb_path"] = jsonb_path
        elif operator.upper() == "CONTAINS":
            # Contains: case-insensitive substring match
            conditions.append("payload->>:jsonb_path ILIKE :value")
            params["value"] = f"%{value}%"
            params["jsonb_path"] = jsonb_path
        elif operator.upper() == "STARTS_WITH":
            # Starts with: case-insensitive prefix match
            conditions.append("payload->>:jsonb_path ILIKE :value")
            params["value"] = f"{value}%"
            params["jsonb_path"] = jsonb_path
        elif operator.upper() == "ENDS_WITH":
            # Ends with: case-insensitive suffix match
            conditions.append("payload->>:jsonb_path ILIKE :value")
            params["value"] = f"%{value}"
            params["jsonb_path"] = jsonb_path
        else:
            # For other operators, use ->> for text comparison
            conditions.append(f"payload->>:jsonb_path {operator} :value")
            params["value"] = value
            params["jsonb_path"] = jsonb_path
    else:
        # Check if field exists (use ? operator with parameterized key)
        conditions.append("payload ? :jsonb_path")
        params["jsonb_path"] = jsonb_path

    # Add event type filter if provided
    if event_type:
        pattern = event_type.replace("*", "%")
        conditions.append("event_type LIKE :event_pattern")
        params["event_pattern"] = pattern

    where_clause = " AND ".join(conditions) if conditions else "TRUE"

    logger.info(
        f"Querying JSONB field: path='{jsonb_path}', operator='{operator}', value='{value}'"
    )

    try:
        result = await db.execute(
            text(
                f"""
                SELECT event_id, event_ts, event_type, artifact_id, payload
                FROM events
                WHERE investigation_id = :investigation_id
                  AND {where_clause}
                ORDER BY event_ts DESC
                LIMIT :limit OFFSET :offset
            """
            ),
            {"investigation_id": investigation_id, **params},
        )

        rows = result.fetchall()
        events = [
            {
                "event_id": row[0],
                "event_ts": row[1].isoformat() if row[1] else None,
                "event_type": row[2],
                "artifact_id": row[3],
                "payload": row[4],
            }
            for row in rows
        ]

        if stats is not None:
            stats["events_analyzed"] = stats.get("events_analyzed", 0) + len(events)

        # Get total count for pagination info
        count_result = await db.execute(
            text(
                f"""
                SELECT COUNT(*)
                FROM events
                WHERE investigation_id = :investigation_id
                  AND {where_clause}
            """
            ),
            {"investigation_id": investigation_id, **params},
        )
        total_count = count_result.scalar() or 0

        # Calculate pagination info
        current_page = (offset // limit) + 1 if limit > 0 else 1
        total_pages = (total_count + limit - 1) // limit if limit > 0 else 1

        logger.info(
            f"query_jsonb_field returned {len(events)} events, "
            f"page {current_page}/{total_pages}, total={total_count}"
        )

        return {
            "count": len(events),
            "total_count": total_count,
            "current_page": current_page,
            "total_pages": total_pages,
            "events": events,
            "has_more": len(events) == limit,
            "limit": limit,
            "offset": offset,
            "query": {"jsonb_path": jsonb_path, "operator": operator, "value": value},
        }

    except Exception as e:
        logger.error(f"JSONB query failed: {e}", exc_info=True)
        return {"error": str(e)}


async def aggregate_jsonb_field(
    db: AsyncSession,
    investigation_id: str,
    jsonb_path: str,
    aggregation: str = "count",
    event_type: Optional[str] = None,
    limit: int = 20,
) -> Dict[str, Any]:
    """
    Aggregate values from a JSONB field in event records.

    This function queries the `events` table for a given investigation and performs one of three
    aggregations on a specified JSONB path:

    * **count** - Returns the total number of events that contain the field.
    * **distinct** - Returns the count of distinct values stored at the path.
    * **top_values** - Returns the most frequent values together with their occurrence counts,
      limited to `limit` results (capped at 50).

    The optional `event_type` argument allows further filtering by event type, using SQL
    wild-card semantics where `*` is translated to `%`.

    Parameters
    ----------
    db : AsyncSession
        An active asynchronous SQLAlchemy session used to execute the query.
    investigation_id : str
        Identifier of the investigation whose events are being examined.
    jsonb_path : str
        Dotted path (key) inside the JSONB `payload` column to aggregate on.
    aggregation : str, optional
        Type of aggregation to perform. Must be one of `"count"`, `"distinct"`, or
        `"top_values"`. Defaults to `"count"`.
    event_type : str | None, optional
        If provided, restricts the query to events whose `event_type` matches the pattern.
        The wildcard character `*` is converted to SQL's `%` for a LIKE comparison.
    limit : int, optional
        Maximum number of rows returned when `aggregation="top_values"`. Values greater than
        50 are truncated to 50. Defaults to 20.

    Returns
    -------
    dict
        A dictionary containing the aggregation result:

        * For `count`: `{"field": <jsonb_path>, "count": <int>}`
        * For `distinct`: `{"field": <jsonb_path>, "distinct_values": <int>}`
        * For `top_values`: `{"field": <jsonb_path>, "top_values": [{"value": <str>, "count": <int>}, ...]}`
        * If an unknown aggregation type is supplied or an error occurs, a dictionary with an
          `"error"` key describing the problem is returned.

    Raises
    ------
    None directly; any exception raised during query execution is caught, logged, and reported
    via the `"error"` entry in the returned dictionary.
    """
    params: Dict[str, Any] = {}

    # Add event type filter if provided
    event_filter = ""
    if event_type:
        pattern = event_type.replace("*", "%")
        event_filter = "AND event_type LIKE :event_pattern"
        params["event_pattern"] = pattern

    logger.info(f"Aggregating JSONB field: path='{jsonb_path}', aggregation='{aggregation}'")

    try:
        if aggregation == "count":
            # Count how many events have this field
            result = await db.execute(
                text(
                    f"""
                    SELECT COUNT(*)
                    FROM events
                    WHERE investigation_id = :investigation_id
                      AND payload ? :jsonb_path
                      {event_filter}
                """
                ),
                {"investigation_id": investigation_id, "jsonb_path": jsonb_path, **params},
            )
            count = result.scalar()
            return {"field": jsonb_path, "count": count}

        elif aggregation == "distinct":
            # Count distinct values
            result = await db.execute(
                text(
                    f"""
                    SELECT COUNT(DISTINCT payload->>:jsonb_path)
                    FROM events
                    WHERE investigation_id = :investigation_id
                      AND payload ? :jsonb_path
                      {event_filter}
                """
                ),
                {"investigation_id": investigation_id, "jsonb_path": jsonb_path, **params},
            )
            count = result.scalar()
            return {"field": jsonb_path, "distinct_values": count}

        elif aggregation == "top_values":
            # Get most common values
            limit = min(int(limit), 50)
            result = await db.execute(
                text(
                    f"""
                    SELECT 
                        payload->>:jsonb_path as value,
                        COUNT(*) as count
                    FROM events
                    WHERE investigation_id = :investigation_id
                      AND payload ? :jsonb_path
                      {event_filter}
                    GROUP BY payload->>:jsonb_path
                    ORDER BY count DESC
                    LIMIT :limit
                """
                ),
                {
                    "investigation_id": investigation_id,
                    "jsonb_path": jsonb_path,
                    "limit": limit,
                    **params,
                },
            )
            rows = result.fetchall()
            top_values = [{"value": row[0], "count": row[1]} for row in rows]
            return {"field": jsonb_path, "top_values": top_values}

        else:
            return {
                "error": f"Unknown aggregation type '{aggregation}'. Use: count, distinct, or top_values"
            }

    except Exception as e:
        logger.error(f"JSONB aggregation failed: {e}", exc_info=True)
        return {"error": str(e)}


async def get_available_jsonb_fields(
    db: AsyncSession,
    investigation_id: str,
    event_type: Optional[str] = None,
    sample_size: int = 5,
) -> List[str]:
    """
    Get a sorted list of unique JSONB field names present in event payloads for a given investigation.

    This function samples a configurable number of recent events per event type (default 5) and extracts all distinct keys from their `payload` column, which may be stored as a PostgreSQL JSONB object or a JSON-encoded string. Sampling multiple events helps discover fields that are not present in every record.

    Args:
        db: An active :class:`sqlalchemy.ext.asyncio.AsyncSession` used to execute the query.
        investigation_id: The UUID of the investigation whose events should be inspected.
        event_type: Optional glob-style filter (`*` as wildcard) to limit extraction to a specific event type. If omitted, fields are collected for all types.
        sample_size: Number of most recent events to sample per event type; defaults to 5.

    Returns:
        A list of unique field names sorted alphabetically. The list may be empty if no events match the criteria or payloads contain no extractable keys.
    """
    # Build query to get sample_size events per event_type
    # Using a window function to get top N per partition
    query = f"""
        SELECT event_type, payload
        FROM (
            SELECT event_type, payload,
                   ROW_NUMBER() OVER (PARTITION BY event_type ORDER BY event_ts DESC) as rn
            FROM events
            WHERE investigation_id = :investigation_id
    """
    params: Dict[str, Any] = {"investigation_id": investigation_id, "sample_size": sample_size}

    if event_type:
        pattern = event_type.replace("*", "%")
        query += " AND event_type LIKE :pattern"
        params["pattern"] = pattern

    query += f"""
        ) AS ranked
        WHERE rn <= :sample_size
        ORDER BY event_type, rn
    """

    result = await db.execute(text(query), params)
    rows = result.fetchall()

    # Extract all unique field names from payloads
    field_set = set()

    for row in rows:
        payload = row[1]  # payload is the second column

        if isinstance(payload, dict):
            # Payload is already a dict (JSONB)
            field_set.update(payload.keys())
        elif isinstance(payload, str):
            # Payload might be a JSON string
            try:
                payload_dict = json.loads(payload)
                if isinstance(payload_dict, dict):
                    field_set.update(payload_dict.keys())
            except (json.JSONDecodeError, TypeError):
                pass

    # Return sorted list of field names
    fields = sorted(list(field_set))

    logger.info(
        f"Extracted {len(fields)} unique JSONB fields from {len(rows)} sampled events "
        f"(~{sample_size} per event type) in investigation {investigation_id}"
    )

    return fields


async def count_events(
    db: AsyncSession,
    investigation_id: str,
    event_type: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Count events in an investigation that match optional filtering criteria.

    Parameters
    ----------
    db : AsyncSession
        Asynchronous SQLAlchemy session used to execute the query.
    investigation_id : str
        Identifier of the investigation whose events are being counted.
    event_type : Optional[str], default=None
        Event type filter supporting `*` as a wildcard. The value is converted to an SQL `LIKE` pattern where `*` becomes `%`. If omitted, no event-type filtering is applied.
    start_time : Optional[str], default=None
        ISO-8601 timestamp string defining the lower bound (inclusive) for `event_ts`. The function attempts to parse the string into a `datetime`; if parsing fails, the raw value is passed to the database and any resulting error will be raised there.
    end_time : Optional[str], default=None
        ISO-8601 timestamp string defining the upper bound (inclusive) for `event_ts`. Parsed in the same manner as `start_time`.

    Returns
    -------
    Dict[str, Any]
        Mapping containing a single key `"count"` whose value is the integer number of events that satisfy all supplied criteria.

    Raises
    ------
    Any exception raised by the underlying database driver or SQLAlchemy during query execution will propagate to the caller. Invalid timestamp strings may also cause database-level errors if they cannot be interpreted.
    """
    conditions = []
    params: Dict[str, Any] = {}

    if event_type:
        pattern = event_type.replace("*", "%")
        conditions.append("event_type LIKE :pattern")
        params["pattern"] = pattern

    if start_time:
        conditions.append("event_ts >= :start_time")
        # Parse ISO timestamp string to datetime object
        try:
            params["start_time"] = date_parser.parse(start_time)
        except (ValueError, TypeError) as e:
            logger.warning(f"Failed to parse start_time '{start_time}': {e}")
            params["start_time"] = start_time  # Let DB handle the error

    if end_time:
        conditions.append("event_ts <= :end_time")
        # Parse ISO timestamp string to datetime object
        try:
            params["end_time"] = date_parser.parse(end_time)
        except (ValueError, TypeError) as e:
            logger.warning(f"Failed to parse end_time '{end_time}': {e}")
            params["end_time"] = end_time  # Let DB handle the error

    where_clause = " AND ".join(conditions) if conditions else "TRUE"

    logger.info(f"Counting events: {params}")

    result = await db.execute(
        text(
            f"""
            SELECT COUNT(*) 
            FROM events
            WHERE investigation_id = :investigation_id
              AND {where_clause}
        """
        ),
        {"investigation_id": investigation_id, **params},
    )

    count = result.scalar()

    logger.info(f"count_events returned {count} events")

    return {"count": count}
