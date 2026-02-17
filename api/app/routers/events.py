from fastapi import APIRouter, Depends, HTTPException, status, Body, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import Table, MetaData, select, text, func
from uuid import UUID
from datetime import datetime
from typing import Optional, Dict, Any
import json
import yaml
import csv
import io
from pathlib import Path

from ..deps import get_db, get_current_user
from ..models.user import User
from ..crud.investigation import check_investigation_access
from ..utils.security import validate_path_within_base, sanitize_filename

router = APIRouter()


@router.get("/{investigation_id}")
async def list_events(
    investigation_id: UUID,
    request: Request,
    limit: int = 100,
    offset: int = 0,
    event_type: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    search: Optional[str] = None,
    order: str = "desc",
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    List events for a given investigation with pagination, filtering, and advanced JSONB querying.

    Parameters
    ----------
    investigation_id: UUID
        Identifier of the investigation whose events are being queried.
    request: Request
        FastAPI request object used to extract raw query parameters for dynamic JSONB filters.
    limit: int, optional
        Maximum number of events to return. Defaults to 100.
    offset: int, optional
        Number of events to skip before starting to collect the result set. Defaults to 0.
    event_type: str, optional
        Filter results by exact event type.
    start_date: str, optional
        ISO-8601 datetime string; include only events occurring on or after this timestamp.
    end_date: str, optional
        ISO-8601 datetime string; include only events occurring on or before this timestamp.
    search: str, optional
        Case-insensitive free-text search applied to the `payload` (as text) and `event_type` fields.
    order: str, optional
        Sort direction for the event timestamp. Accepts `'desc'` (default) or `'asc'`.
    db: AsyncSession, injected by FastAPI Depends
        Asynchronous SQLAlchemy session used to execute queries.
    user: User, injected by FastAPI Depends
        The authenticated user; access is validated against the investigation.

    Returns
    -------
    dict
        A dictionary containing:
            * `events` - list of event dictionaries with keys `event_id`, `event_ts`,
              `artifact_id`, `event_type` and `payload`.
            * `count` - number of events returned in this page.
            * `total` - total number of matching events across all pages.
            * `limit` - the limit value used for pagination.
            * `offset` - the offset value used for pagination.

    Raises
    ------
    HTTPException
        * 400 - if any supplied date string cannot be parsed or an invalid JSONB operator is provided.
        * 403 - if the current user lacks access to the specified investigation (raised by `check_investigation_access`).
        * 500 - on unexpected database execution errors.
    """
    # Check access
    await check_investigation_access(db, investigation_id, user)

    # Extract JSONB query parameters from request query params
    # They come as jsonb_path_0, jsonb_operator_0, jsonb_value_0, etc.
    query_params = dict(request.query_params)
    jsonb_queries = []

    # Parse JSONB queries from numbered parameters
    i = 0
    while f"jsonb_path_{i}" in query_params:
        path = query_params.get(f"jsonb_path_{i}")
        operator = query_params.get(f"jsonb_operator_{i}", "=")
        value = query_params.get(f"jsonb_value_{i}")

        if path:
            jsonb_queries.append({"path": path, "operator": operator, "value": value})
        i += 1

    # Build query
    query = """
        SELECT event_id, event_ts, artifact_id, event_type, payload
        FROM events
        WHERE investigation_id = :investigation_id
    """
    params: Dict[str, Any] = {"investigation_id": str(investigation_id), "limit": limit, "offset": offset}

    if event_type:
        query += " AND event_type = :event_type"
        params["event_type"] = event_type

    if start_date:
        query += " AND event_ts >= :start_date"
        # Parse datetime string to datetime object
        try:
            from dateutil import parser as date_parser

            params["start_date"] = date_parser.parse(start_date)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid start_date format: {str(e)}")

    if end_date:
        query += " AND event_ts <= :end_date"
        # Parse datetime string to datetime object
        try:
            from dateutil import parser as date_parser

            params["end_date"] = date_parser.parse(end_date)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid end_date format: {str(e)}")

    if search:
        query += " AND (payload::text ILIKE :search OR event_type ILIKE :search)"
        params["search"] = f"%{search}%"

    # Add JSONB queries if provided
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
    for idx, jsonb_query in enumerate(jsonb_queries):
        path = jsonb_query["path"]
        operator = jsonb_query["operator"]
        value = jsonb_query["value"]

        # Validate operator
        if operator.upper() not in [op.upper() for op in valid_operators]:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid JSONB operator '{operator}'. Must be one of: {', '.join(valid_operators)}",
            )

        param_path = f"jsonb_path_{idx}"
        param_value = f"jsonb_value_{idx}"

        if value is not None and value != "":
            # Handle different operator types
            if operator.upper() in ["LIKE", "ILIKE"]:
                # For LIKE/ILIKE operators, convert * wildcards to SQL %
                sql_value = value.replace("*", "%")
                query += f" AND payload->>:{param_path} {operator.upper()} :{param_value}"
                params[param_value] = sql_value
            elif operator.upper() == "CONTAINS":
                # Contains: case-insensitive substring match
                query += f" AND payload->>:{param_path} ILIKE :{param_value}"
                params[param_value] = f"%{value}%"
            elif operator.upper() == "STARTS_WITH":
                # Starts with: case-insensitive prefix match
                query += f" AND payload->>:{param_path} ILIKE :{param_value}"
                params[param_value] = f"{value}%"
            elif operator.upper() == "ENDS_WITH":
                # Ends with: case-insensitive suffix match
                query += f" AND payload->>:{param_path} ILIKE :{param_value}"
                params[param_value] = f"%{value}"
            else:
                # Standard comparison operators
                query += f" AND payload->>:{param_path} {operator} :{param_value}"
                params[param_value] = value
            params[param_path] = path
        else:
            # Check if field exists
            query += f" AND payload ? :{param_path}"
            params[param_path] = path

    # Validate and apply sort order
    sort_direction = "DESC" if order.lower() == "desc" else "ASC"
    query += f" ORDER BY event_ts {sort_direction} LIMIT :limit OFFSET :offset"

    try:
        result = await db.execute(text(query), params)
        rows = result.fetchall()
        # Convert rows to dicts
        events_list = []
        for row in rows:
            events_list.append(
                {
                    "event_id": row[0],
                    "event_ts": row[1].isoformat() if row[1] else None,
                    "artifact_id": row[2],
                    "event_type": row[3],
                    "payload": row[4],
                }
            )
        rows = events_list
    except Exception as e:
        import logging

        logging.error(f"Error executing events query: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

    # Get total count
    count_query = "SELECT COUNT(*) FROM events WHERE investigation_id = :investigation_id"
    count_params: Dict[str, Any] = {"investigation_id": str(investigation_id)}
    if event_type:
        count_query += " AND event_type = :event_type"
        count_params["event_type"] = event_type
    if start_date:
        count_query += " AND event_ts >= :start_date"
        # Parse datetime string to datetime object
        try:
            from dateutil import parser as date_parser

            count_params["start_date"] = date_parser.parse(start_date)
        except:
            pass  # Already validated above
    if end_date:
        count_query += " AND event_ts <= :end_date"
        # Parse datetime string to datetime object
        try:
            from dateutil import parser as date_parser

            count_params["end_date"] = date_parser.parse(end_date)
        except:
            pass  # Already validated above
    if search:
        count_query += " AND (payload::text ILIKE :search OR event_type ILIKE :search)"
        count_params["search"] = f"%{search}%"

    # Add JSONB queries to count query
    for idx, jsonb_query in enumerate(jsonb_queries):
        path = jsonb_query["path"]
        operator = jsonb_query["operator"]
        value = jsonb_query["value"]

        param_path = f"jsonb_path_{idx}"
        param_value = f"jsonb_value_{idx}"

        if value is not None and value != "":
            # Handle different operator types
            if operator.upper() in ["LIKE", "ILIKE"]:
                sql_value = value.replace("*", "%")
                count_query += f" AND payload->>:{param_path} {operator.upper()} :{param_value}"
                count_params[param_value] = sql_value
            elif operator.upper() == "CONTAINS":
                count_query += f" AND payload->>:{param_path} ILIKE :{param_value}"
                count_params[param_value] = f"%{value}%"
            elif operator.upper() == "STARTS_WITH":
                count_query += f" AND payload->>:{param_path} ILIKE :{param_value}"
                count_params[param_value] = f"{value}%"
            elif operator.upper() == "ENDS_WITH":
                count_query += f" AND payload->>:{param_path} ILIKE :{param_value}"
                count_params[param_value] = f"%{value}"
            else:
                count_query += f" AND payload->>:{param_path} {operator} :{param_value}"
                count_params[param_value] = value
            count_params[param_path] = path
        else:
            count_query += f" AND payload ? :{param_path}"
            count_params[param_path] = path

    try:
        count_result = await db.execute(text(count_query), count_params)
        total = count_result.scalar() or 0
    except Exception as e:
        import logging

        logging.error(f"Error executing count query: {e}", exc_info=True)
        total = 0

    return {"events": rows, "count": len(rows), "total": total, "limit": limit, "offset": offset}


@router.get("/{investigation_id}/event-types")
async def get_event_types(
    investigation_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Get all unique event types for a given investigation.

    Args:
        investigation_id (UUID): Identifier of the investigation whose events are being queried.
        db (AsyncSession, optional): Asynchronous SQLAlchemy session injected by FastAPI's dependency system.
        user (User, optional): The currently authenticated user, provided via dependency injection.

    Returns:
        dict: A dictionary containing:
            - "event_types" (list[dict]): List of dictionaries each with:
                * "event_type" (str | None): The distinct event type value.
                * "count" (int): Number of events that have this type.
            - "total_types" (int): Total number of unique event types found.

    Raises:
        HTTPException: If the user does not have access to the specified investigation.
    """
    # Check access
    await check_investigation_access(db, investigation_id, user)

    # Get all unique event types with counts
    query = """
        SELECT event_type, COUNT(*) as count
        FROM events
        WHERE investigation_id = :investigation_id
        GROUP BY event_type
        ORDER BY count DESC, event_type ASC
    """

    result = await db.execute(text(query), {"investigation_id": str(investigation_id)})

    rows = result.fetchall()

    event_types = [{"event_type": row[0], "count": row[1]} for row in rows]

    return {"event_types": event_types, "total_types": len(event_types)}


@router.get("/{investigation_id}/fields")
async def get_event_fields(
    investigation_id: UUID,
    event_type: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Get a sorted list of unique JSONB field names present in events for a given investigation.

    The function retrieves a sample of events - either 10 events per event type (if no filter) 
    or 10 events for a specific event type - and extracts the keys from their `payload` column. 
    It returns those keys alphabetically, together with metadata about the operation.

    Args:
        investigation_id (UUID): Identifier of the investigation whose events are queried.
        event_type (str, optional): If provided, limits the sample to 10 events of this type; 
            otherwise samples 10 events per distinct event type.
        db (AsyncSession): Asynchronous SQLAlchemy session injected by FastAPI's dependency system.
        user (User): The current authenticated user, also injected via dependency.

    Returns:
        dict: A mapping with three entries:
            `fields` (list[str]): Alphabetically sorted list of unique payload field names found in the sampled events.
            `count` (int): Number of distinct fields returned.
            `event_types_sampled` (int): Number of event rows examined to derive the field set.

    Raises:
        HTTPException: Propagated from `check_investigation_access` if the user lacks permission to view the investigation.
    """
    # Check access
    await check_investigation_access(db, investigation_id, user)

    # Build query based on whether event_type filter is provided
    if event_type:
        # Get sample of 10 events for specific event type
        query = """
            SELECT event_type, payload
            FROM events
            WHERE investigation_id = :investigation_id
              AND event_type = :event_type
            ORDER BY event_ts DESC
            LIMIT 10
        """
        params = {"investigation_id": str(investigation_id), "event_type": event_type}
    else:
        # Get 10 events per event_type using window function (more efficient)
        # ROW_NUMBER() partitions by event_type and orders by event_ts
        query = """
            SELECT event_type, payload
            FROM (
                SELECT 
                    event_type, 
                    payload,
                    ROW_NUMBER() OVER (PARTITION BY event_type ORDER BY event_ts DESC) as rn
                FROM events
                WHERE investigation_id = :investigation_id
            ) AS ranked
            WHERE rn <= 10
        """
        params = {"investigation_id": str(investigation_id)}

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

    return {"fields": fields, "count": len(fields), "event_types_sampled": len(rows)}


@router.post("/paste")
async def paste_events(
    investigation_id: UUID,
    payload: str = Body(..., media_type="text/plain"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Paste raw CSV/JSON/YAML event data directly into an investigation.

    This endpoint validates that the requesting user has access to the specified investigation,
    detects the format of the supplied `payload` (JSON, YAML, or CSV), parses it into a
    list of record dictionaries, saves the original text as a timestamped file under the
    investigation's `raw_files` directory, and inserts each record into the `events`
    table.

    Args:
        investigation_id: UUID of the investigation to which the events belong.
        payload: Raw event data supplied in the request body. The content type must be
            `text/plain`; the function attempts to interpret it as JSON, falling back to
            YAML and finally CSV.
        db: Asynchronous SQLAlchemy session provided by FastAPI's dependency injection.
        user: Currently authenticated user object obtained via `get_current_user`.

    Raises:
        HTTPException 400: If the payload cannot be parsed as JSON, YAML, or CSV; if the
            resulting data is not a list or dictionary; if no records are found; or if any
            other validation error occurs.
        Any exception raised by `check_investigation_access` when the user lacks permission.

    Returns:
        dict: A summary of the operation containing:
            - `status` (str): Always `"ok"` on success.
            - `format` (str): Detected format of the input data (`"json"`, `"yaml"`, or `"csv"`).
            - `inserted` (int): Number of event records successfully inserted.
            - `file_saved` (str): Filesystem path to the saved raw paste file.
    """
    # Check access
    await check_investigation_access(db, investigation_id, user)

    # Detect format and parse
    data = None
    fmt = None

    try:
        data = json.loads(payload)
        fmt = "json"
    except json.JSONDecodeError:
        try:
            data = yaml.safe_load(payload)
            fmt = "yaml"
        except Exception:
            # Try CSV
            try:
                reader = csv.DictReader(io.StringIO(payload))
                data = list(reader)
                fmt = "csv"
            except Exception as e:
                raise HTTPException(
                    status_code=400, detail=f"Unable to parse as JSON, YAML, or CSV: {str(e)}"
                )

    if not isinstance(data, (list, dict)):
        raise HTTPException(status_code=400, detail="Data must be a list or dictionary")

    # Normalize to list of dicts
    records = data if isinstance(data, list) else [data]

    if not records:
        raise HTTPException(status_code=400, detail="No records found")

    # Save raw paste file
    base_investigations_dir = Path("/data/investigations")
    inv_dir = validate_path_within_base(
        Path(str(investigation_id)) / "raw_files",
        base_investigations_dir
    )
    inv_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.utcnow().isoformat(timespec="seconds").replace(":", "-")
    ext = {"json": ".json", "yaml": ".yaml", "csv": ".csv"}[fmt]
    filename = sanitize_filename(f"paste_{timestamp}{ext}")
    file_path = inv_dir / filename
    file_path.write_text(payload)

    # Insert records into events table
    inserted = 0
    async with db.begin():
        for rec in records:
            # Extract fields with defaults
            event_ts = rec.get("event_ts") or rec.get("timestamp") or datetime.utcnow()
            event_type = rec.get("event_type", "pasted")
            artifact_id = rec.get("artifact_id")

            # Convert event_ts to datetime if it's a string
            if isinstance(event_ts, str):
                try:
                    event_ts = datetime.fromisoformat(event_ts.replace("Z", "+00:00"))
                except:
                    event_ts = datetime.utcnow()

            insert_query = """
                INSERT INTO events (investigation_id, event_ts, artifact_id, event_type, payload)
                VALUES (:investigation_id, :event_ts, :artifact_id, :event_type, :payload)
            """

            await db.execute(
                text(insert_query),
                {
                    "investigation_id": str(investigation_id),
                    "event_ts": event_ts,
                    "artifact_id": artifact_id,
                    "event_type": event_type,
                    "payload": json.dumps(rec),
                },
            )
            inserted += 1

    return {"status": "ok", "format": fmt, "inserted": inserted, "file_saved": str(file_path)}
