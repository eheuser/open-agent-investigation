import logging
from typing import Any, Dict, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from ..core.tool_registry import ToolSpec, tool_registry
from . import (
    event_tools,
    timeline_tools,
    control_tools,
    websearch_tool,
    hybrid_search,
    control_tools_extended,
    advanced_query_tools,
    diagram_tools,
)

logger = logging.getLogger(__name__)


async def search_events_by_type_wrapper(
    db: AsyncSession,
    investigation_id: str,
    stats: Dict[str, Any],
    event_type: str,
    limit: int = 50,
    offset: int = 0,
    description: str = "",
    auto_register: bool = False,
) -> Dict[str, Any]:
    """
    Search events by type with optional automatic timeline registration.

    Parameters
    ----------
    db : AsyncSession
        Asynchronous database session used for queries and registrations.
    investigation_id : str
        Identifier of the investigation context in which to search.
    stats : Dict[str, Any]
        Dictionary for collecting statistics about the operation (e.g., execution time).
    event_type : str
        Event type pattern to match; supports wildcard characters such as `*`.
    limit : int, optional
        Maximum number of events to return. Defaults to 50.
    offset : int, optional
        Number of matching events to skip before returning results. Defaults to 0.
    description : str, optional
        Optional description applied to automatically created timeline entries. If omitted,
        a generic description based on the search pattern is used.
    auto_register : bool, optional
        When `True` and at least one event is found, each event is registered as a timeline
        entry using `timeline_tools.register_timeline_entry`. Failures during registration are
        logged but do not abort the search. Defaults to `False`.

    Returns
    -------
    Dict[str, Any]
        A dictionary containing the search results under the key `"events"`. If
        `auto_register` is enabled and registrations succeed, additional keys
        `"auto_registered"` (the number of events registered) and
        `"auto_registration_description"` (the description used for registration) are added.

    Raises
    ------
    None explicitly; any exception raised during timeline registration is caught,
    logged as a warning, and the function proceeds to return the search result.
    """
    result = await event_tools.search_events_by_type(
        db, investigation_id, event_type, limit, offset, stats
    )

    # OPTIONAL AUTOMATIC TIMELINE REGISTRATION (only if auto_register=True)
    if auto_register and result.get("events") and len(result["events"]) > 0:
        # Extract event IDs
        event_ids = [e["event_id"] for e in result["events"]]

        # Auto-register each event to timeline
        for event_id in event_ids:
            try:
                await timeline_tools.register_timeline_entry(
                    db=db,
                    investigation_id=investigation_id,
                    event_id=event_id,
                    title=f"{event_type} event",
                    entry_type="event",
                    description=description or f"Registered from search: {event_type}",
                    tags=["agent-registered", event_type.replace("*", "all")],
                    stats=stats,
                )
            except Exception as e:
                # Don't fail the search if timeline registration fails
                logger.warning(f"Failed to register event {event_id}: {e}")

        # Add metadata about registration
        result["auto_registered"] = len(event_ids)
        result["auto_registration_description"] = description

    return result


async def search_events_by_timerange_wrapper(
    db: AsyncSession,
    investigation_id: str,
    stats: Dict[str, Any],
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    event_type: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    description: str = "",
    auto_register: bool = False,
) -> Dict[str, Any]:
    """
    Searches for events within a given time range and optionally registers each found event in the investigation timeline.

    Args:
        db: Asynchronous SQLAlchemy session used for database operations.
        investigation_id: Identifier of the investigation to which the search belongs.
        stats: Dictionary used to collect statistical information about the operation.
        start_time: ISO-8601 formatted timestamp marking the beginning of the time range; if `None` the lower bound is unbounded.
        end_time: ISO-8601 formatted timestamp marking the end of the time range; if `None` the upper bound is unbounded.
        event_type: Optional filter to restrict results to a specific type of event.
        limit: Maximum number of events to return (default 50).
        offset: Number of events to skip before starting to collect results (default 0).
        description: Textual description used when automatically registering timeline entries; defaults to an empty string.
        auto_register: When `True` each returned event is added to the investigation timeline via :func:`timeline_tools.register_timeline_entry`. Failures are logged but do not abort the search.

    Returns:
        A dictionary containing the raw result from :func:`event_tools.search_events_by_timerange`. If `auto_register` is enabled and events were found, the dictionary is augmented with:
            - `auto_registered`: Count of events successfully added to the timeline.
            - `auto_registration_description`: The description supplied for the registration.

    Raises:
        Propagates any exception raised by the underlying search operation; exceptions occurring during automatic timeline registration are caught and logged.
    """
    result = await event_tools.search_events_by_timerange(
        db, investigation_id, start_time, end_time, event_type, limit, offset, stats
    )

    # OPTIONAL timeline registration (only if auto_register=True)
    if auto_register and result.get("events") and len(result["events"]) > 0:
        event_ids = [e["event_id"] for e in result["events"]]

        for event_id in event_ids:
            try:
                await timeline_tools.register_timeline_entry(
                    db=db,
                    investigation_id=investigation_id,
                    event_id=event_id,
                    title=f"Event in timerange {start_time or 'start'} to {end_time or 'end'}",
                    entry_type="event",
                    description=description or f"Registered from timerange search",
                    tags=["agent-registered", "timerange"],
                    stats=stats,
                )
            except Exception as e:
                logger.warning(f"Failed to register event {event_id}: {e}")

        result["auto_registered"] = len(event_ids)
        result["auto_registration_description"] = description

    return result


async def search_events_by_content_wrapper(
    db: AsyncSession,
    investigation_id: str,
    stats: Dict[str, Any],
    search_text: str,
    event_type: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    description: str = "",
    auto_register: bool = False,
) -> Dict[str, Any]:
    """
    Search event payloads for content and optionally register matching events in the investigation timeline.

    Parameters
    ----------
    db: AsyncSession
        Asynchronous database session used for all queries.
    investigation_id: str
        Identifier of the investigation to which the search belongs.
    stats: Dict[str, Any]
        Dictionary for collecting statistical information about the operation; passed through to underlying tools.
    search_text: str
        Text pattern to look for inside event payloads.
    event_type: Optional[str], optional
        Filter results by a specific event type. If `None` (default), all types are considered.
    limit: int, optional
        Maximum number of events to return. Defaults to 50.
    offset: int, optional
        Number of events to skip before returning results. Defaults to 0.
    description: str, optional
        Human-readable description used when automatically registering timeline entries. If omitted,
        a default description based on `search_text` is generated.
    auto_register: bool, optional
        When `True`, each event found by the search is registered as a timeline entry. Defaults to `False`.

    Returns
    -------
    Dict[str, Any]
        The raw result from :func:`event_tools.search_events_by_content`.  If `auto_register` is enabled and events are found,
        the dictionary also contains:

        - `auto_registered` (int): Number of events that were successfully added to the timeline.
        - `auto_registration_description` (str): Description used for the automatic registrations.

    Raises
    ------
    Exception
        Any exception raised by the underlying search or registration calls is propagated, except for registration failures,
        which are logged as warnings and do not abort the function.
    """
    result = await event_tools.search_events_by_content(
        db,
        investigation_id,
        search_text=search_text,
        event_type=event_type,
        limit=limit,
        offset=offset,
        stats=stats,
    )

    # OPTIONAL timeline registration (only if auto_register=True)
    if auto_register and result.get("events") and len(result["events"]) > 0:
        event_ids = [e["event_id"] for e in result["events"]]

        for event_id in event_ids:
            try:
                await timeline_tools.register_timeline_entry(
                    db=db,
                    investigation_id=investigation_id,
                    event_id=event_id,
                    title=f"Event containing '{search_text[:50]}'",
                    entry_type="event",
                    description=description or f"Registered from content search: {search_text}",
                    tags=["agent-registered", "content-match"],
                    stats=stats,
                )
            except Exception as e:
                logger.warning(f"Failed to register event {event_id}: {e}")

        result["auto_registered"] = len(event_ids)
        result["auto_registration_description"] = description

    return result


async def get_event_by_id_wrapper(
    db: AsyncSession,
    investigation_id: str,
    stats: Dict[str, Any],
    event_id: int,
    description: str = "",
) -> Dict[str, Any]:
    """
    Retrieve a single event identified by its unique ID within a given investigation.

    :param db: Asynchronous SQLAlchemy session used for database access.
    :param investigation_id: Identifier of the investigation to which the event belongs.
    :param stats: Dictionary collecting statistics or metadata about the operation; passed through to the underlying tool.
    :param event_id: Unique integer identifier of the event to retrieve.
    :param description: Optional textual description of the request (currently unused but retained for interface compatibility).
    :return: A dictionary containing the event data as returned by `event_tools.get_event_by_id`. The exact structure depends on the implementation of the underlying tool.
    """
    return await event_tools.get_event_by_id(db, investigation_id, event_id, stats)


async def count_events_wrapper(
    db: AsyncSession,
    investigation_id: str,
    stats: Dict[str, Any],
    event_type: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    description: str = "",
) -> Dict[str, Any]:
    """
    Count events matching given criteria.

    Parameters
    ----------
    db : AsyncSession
        Asynchronous database session used for queries.
    investigation_id : str
        Identifier of the investigation whose events are being counted.
    stats : dict[str, Any]
        Dictionary to be populated with statistical results (currently unused by this wrapper).
    event_type : str, optional
        Filter to include only events of this type. If `None`, all event types are considered.
    start_time : str, optional
        ISO-8601 formatted start timestamp; events occurring before this time are excluded.
    end_time : str, optional
        ISO-8601 formatted end timestamp; events occurring after this time are excluded.
    description : str, default ''
        Human-readable description of the count operation (currently unused).

    Returns
    -------
    dict[str, Any]
        The result returned by `event_tools.count_events`, typically a mapping containing the total count and any additional metadata.
    """
    return await event_tools.count_events(db, investigation_id, event_type, start_time, end_time)


async def query_jsonb_field_wrapper(
    db: AsyncSession,
    investigation_id: str,
    stats: Dict[str, Any],
    jsonb_path: str,
    operator: str = "=",
    value: Optional[str] = None,
    event_type: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    description: str = "",
    auto_register: bool = False,
) -> Dict[str, Any]:
    """
    Query events using JSONB path expressions and optionally register matching events in the investigation timeline.

    Parameters
    ----------
    db: AsyncSession
        Asynchronous SQLAlchemy session used for database operations.
    investigation_id: str
        Identifier of the investigation to which the query belongs.
    stats: Dict[str, Any]
        Dictionary collecting statistics about the operation (e.g., execution time, counts).
    jsonb_path: str
        JSONB path expression targeting a field inside the `data` column of events.
    operator: str, optional
        Comparison operator to apply between the extracted value and `value`. Defaults to `"="`.
    value: Optional[str], optional
        Value to compare against the extracted JSONB field. If omitted, the query checks for existence of the path.
    event_type: Optional[str], optional
        Filter results by a specific event type; if `None` all types are included.
    limit: int, optional
        Maximum number of events to return. Defaults to `50`.
    offset: int, optional
        Number of events to skip before returning results. Defaults to `0`.
    description: str, optional
        Human-readable description used when automatically registering timeline entries. If empty, a default description is generated.
    auto_register: bool, optional
        When `True`, each event returned by the query is registered as a timeline entry using :func:`timeline_tools.register_timeline_entry`. Defaults to `False`.

    Returns
    -------
    Dict[str, Any]
        The raw result from :func:`event_tools.query_jsonb_field`.  When `auto_register` is enabled and events are found, additional keys are added:

        * `"auto_registered"` - the number of events successfully registered.
        * `"auto_registration_description"` - the description supplied (or generated) for the registration.

    Raises
    ------
    Exception
        Any exception raised by :func:`event_tools.query_jsonb_field` propagates to the caller. Exceptions occurring during automatic timeline registration are caught and logged; they do not interrupt the main query result.
    """
    result = await event_tools.query_jsonb_field(
        db, investigation_id, jsonb_path, operator, value, event_type, limit, offset, stats
    )

    # OPTIONAL timeline registration (only if auto_register=True)
    if auto_register and result.get("events") and len(result["events"]) > 0:
        event_ids = [e["event_id"] for e in result["events"]]

        for event_id in event_ids:
            try:
                await timeline_tools.register_timeline_entry(
                    db=db,
                    investigation_id=investigation_id,
                    event_id=event_id,
                    title=f"Event with {jsonb_path} {operator} {value or 'exists'}",
                    entry_type="event",
                    description=description
                    or f"Registered from field query: {jsonb_path} {operator} {value}",
                    tags=["agent-registered", "field-match"],
                    stats=stats,
                )
            except Exception as e:
                logger.warning(f"Failed to register event {event_id}: {e}")

        result["auto_registered"] = len(event_ids)
        result["auto_registration_description"] = description

    return result


async def aggregate_jsonb_field_wrapper(
    db: AsyncSession,
    investigation_id: str,
    stats: Dict[str, Any],
    jsonb_path: str,
    aggregation: str = "count",
    event_type: Optional[str] = None,
    limit: int = 20,
    description: str = "",
) -> Dict[str, Any]:
    """
    Aggregate values from a JSONB field within events of an investigation.

    Parameters
    ----------
    db : AsyncSession
        Asynchronous database session used to execute the query.
    investigation_id : str
        Identifier of the investigation whose events are being queried.
    stats : Dict[str, Any]
        Dictionary containing statistical metadata (currently unused by the wrapper but retained for signature compatibility).
    jsonb_path : str
        JSONB path expression indicating which field within the event payload should be aggregated.
    aggregation : str, optional
        Type of aggregation to perform; defaults to `"count"`. Other supported values depend on the underlying implementation (e.g., `"sum"`, `"avg"`).
    event_type : Optional[str], optional
        If provided, restricts aggregation to events of this specific type.
    limit : int, optional
        Maximum number of distinct aggregated results to return; defaults to 20.
    description : str, optional
        Human-readable description of the aggregation request (not used by the function logic).

    Returns
    -------
    Dict[str, Any]
        A mapping containing the aggregation result as produced by `event_tools.aggregate_jsonb_field`. The exact structure depends on the chosen aggregation type.

    Raises
    ------
    Any exception raised by `event_tools.aggregate_jsonb_field` may propagate to the caller (e.g., database errors or invalid JSONB paths).
    """
    return await event_tools.aggregate_jsonb_field(
        db, investigation_id, jsonb_path, aggregation, event_type, limit
    )


async def register_timeline_entry_wrapper(
    db: AsyncSession,
    investigation_id: str,
    stats: Dict[str, Any],
    event_id: int,
    title: str,
    entry_type: str = "event",
    description: Optional[str] = None,
    tags: Optional[list] = None,
) -> Dict[str, Any]:
    """
    Register an event or custom entry in the investigation timeline.

    Parameters
    ----------
    db : AsyncSession
        Asynchronous SQLAlchemy session used to interact with the database.
    investigation_id : str
        Identifier of the investigation to which the timeline entry belongs.
    stats : Dict[str, Any]
        Dictionary containing statistical metadata associated with the entry (e.g., timestamps,
        severity scores, or other quantitative attributes).
    event_id : int
        Unique identifier of the event that this timeline entry references. Ignored for non-event
        entries but kept for API compatibility.
    title : str
        Human-readable title for the timeline entry.
    entry_type : str, optional
        Type of the timeline entry; defaults to `"event"`. Other possible values might include
        `"note"`, `"alert"`, etc., depending on the application’s taxonomy.
    description : Optional[str], optional
        Longer free-form description providing additional context for the entry. If omitted,
        no description is stored.
    tags : Optional[list], optional
        List of tags or labels to associate with the entry for categorisation and later filtering.

    Returns
    -------
    Dict[str, Any]
        The newly created timeline entry as a dictionary, typically containing fields such as
        `id`, `investigation_id`, `event_id`, `title`, `type`, `description`,
        `tags` and any statistical metadata supplied in `stats`.

    Raises
    ------
    Exception
        Propagates any exception raised by the underlying `timeline_tools.register_timeline_entry`
        call, such as database integrity errors or validation failures.
    """
    return await timeline_tools.register_timeline_entry(
        db, investigation_id, event_id, title, entry_type, description, tags, stats
    )


async def register_finding_wrapper(
    db: AsyncSession,
    investigation_id: str,
    stats: Dict[str, Any],
    title: str,
    description: str = "",
    severity: str = "medium",
    evidence_event_ids: Optional[list] = None,
    tags: Optional[list] = None,
) -> Dict[str, Any]:
    """
    Register a finding for an investigation in the timeline.

    This coroutine forwards the supplied information to :func:`timeline_tools.register_finding` and returns its result.

    Args:
        db: An active `AsyncSession` used for database operations.
        investigation_id: The unique identifier of the investigation to which the finding belongs.
        stats: A dictionary containing statistical data or metrics associated with the finding.
        title: A short, human-readable title summarising the finding.
        description: Optional longer text describing the context and details of the finding. Defaults to an empty string.
        severity: The severity level of the finding (e.g., `"low"`, `"medium"`, `"high"`). Defaults to `"medium"`.
        evidence_event_ids: An optional list of event identifiers that serve as evidence for this finding. If omitted, no explicit evidence is recorded.
        tags: An optional list of tag strings used to categorise or filter the finding.

    Returns:
        A dictionary representing the newly created finding record as returned by `timeline_tools.register_finding`.
    """
    return await timeline_tools.register_finding(
        db=db,
        investigation_id=investigation_id,
        title=title,
        description=description,
        severity=severity,
        evidence_event_ids=evidence_event_ids,
        tags=tags,
        stats=stats,
    )


async def complete_investigation_wrapper(
    db: AsyncSession,
    investigation_id: str,
    stats: Dict[str, Any],
    summary: str,
    timeline_entries_count: int = 0,
    key_findings: Optional[str] = None,
    recommendations: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Complete an investigation by recording its final summary and related metrics.

    Parameters
    ----------
    db : AsyncSession
        Asynchronous database session used for any required persistence operations.
    investigation_id : str
        Unique identifier of the investigation being completed.
    stats : dict[str, Any]
        Dictionary containing statistical data gathered during the investigation.
    summary : str
        Narrative summary describing the overall outcome of the investigation.
    timeline_entries_count : int, optional
        Number of entries that were added to the investigation timeline. Defaults to `0`.
    key_findings : str, optional
        Highlighted key findings from the investigation. If omitted, an empty string is used.
    recommendations : str, optional
        Suggested next steps or recommendations based on the investigation results. If omitted, an empty string is used.

    Returns
    -------
    dict[str, Any]
        Result returned by `control_tools.complete_investigation` containing confirmation details of the completed investigation.
    """
    return control_tools.complete_investigation(
        summary=summary,
        timeline_entries_count=timeline_entries_count,
        key_findings=key_findings or "",
        recommendations=recommendations or "",
    )


async def request_additional_turns_wrapper(
    db: AsyncSession,
    investigation_id: str,
    stats: Dict[str, Any],
    turns_requested: int = 3,
    justification: str = "",
) -> Dict[str, Any]:
    """
    Request additional investigation turns.

    Parameters
    ----------
    db : AsyncSession
        Asynchronous database session used for any required data access.
    investigation_id : str
        Identifier of the investigation for which extra turns are being requested.
    stats : Dict[str, Any]
        Dictionary containing statistical information about the current investigation state.
    turns_requested : int, optional
        Number of additional turns to request. Defaults to `3`.
    justification : str, optional
        Reason why extra turns are needed. Empty string if no justification is provided.

    Returns
    -------
    Dict[str, Any]
        The response from the control tool containing details about the granted or denied turn extension.
    """
    return await control_tools_extended.request_additional_turns(
        turns_requested=turns_requested,
        justification=justification,
    )


async def retrieve_and_parse_url_wrapper(
    db: AsyncSession,
    investigation_id: str,
    stats: Dict[str, Any],
    url: str,
) -> Dict[str, Any]:
    """
    Retrieve and parse article content from a URL.

    Parameters
    ----------
    db : AsyncSession
        Asynchronous database session (unused in this wrapper but kept for signature consistency).
    investigation_id : str
        Identifier of the investigation context (unused in this wrapper).
    stats : Dict[str, Any]
        Dictionary for collecting statistics or metrics (unused in this wrapper).
    url : str
        The URL pointing to the article to be retrieved and parsed.

    Returns
    -------
    Dict[str, Any]
        A dictionary containing the parsed article data as returned by `websearch_tool.retrieve_and_parse_url`.
    """
    return await websearch_tool.retrieve_and_parse_url(url)


async def hybrid_search_wrapper(
    db: AsyncSession,
    investigation_id: str,
    stats: Dict[str, Any],
    query: str,
    bm25_weight: float = 0.5,
    limit: int = 50,
    offset: int = 0,
    description: str = "",
    user_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Hybrid search that combines BM25 scoring with vector similarity to retrieve relevant records.

    Parameters
    ----------
    db : AsyncSession
        Asynchronous database session used for executing queries.
    investigation_id : str
        Identifier of the investigation context in which the search is performed.
    stats : Dict[str, Any]
        Mutable mapping that will be populated with statistics about the execution (e.g., timing, result counts).
    query : str
        The textual query string supplied by the user.
    bm25_weight : float, optional
        Weight assigned to the BM25 component of the hybrid scoring. Must be between 0 and 1; defaults to `0.5` which gives equal importance to BM25 and vector similarity.
    limit : int, optional
        Maximum number of results to return. Defaults to `50`.
    offset : int, optional
        Number of results to skip before starting to collect the response set. Useful for pagination; defaults to `0`.
    description : str, optional
        Human-readable description of the search operation; currently unused but retained for API compatibility.
    user_id : Optional[int], optional
        Identifier of the user performing the search, used for permission checks or audit logging.

    Returns
    -------
    Dict[str, Any]
        A dictionary containing the search results and associated metadata. Typical keys include `"hits"`, a list of matching records, and `"total"`, the total number of matches before pagination.

    Notes
    -----
    The function is asynchronous and should be awaited. It forwards all arguments to :func:`hybrid_search.hybrid_search` which implements the actual retrieval logic. The `stats` dictionary is updated in-place with performance metrics such as execution time.
    """
    return await hybrid_search.hybrid_search(
        db=db,
        investigation_id=investigation_id,
        query=query,
        bm25_weight=bm25_weight,
        limit=limit,
        offset=offset,
        user_id=user_id,
        stats=stats,
    )


async def execute_sql_wrapper(
    db: AsyncSession,
    investigation_id: str,
    stats: Dict[str, Any],
    query: str,
) -> Dict[str, Any]:
    """
    Execute a read-only SQL query within an investigation context.

    Parameters
    ----------
    db: AsyncSession
        Asynchronous database session used to run the query.
    investigation_id: str
        Identifier of the investigation for which the query is executed.
    stats: Dict[str, Any]
        Dictionary for collecting execution statistics such as timing or row counts; may be updated by the underlying tool.
    query: str
        The SQL statement to execute. Must be a read-only query (e.g., SELECT).

    Returns
    -------
    Dict[str, Any]
        A dictionary containing the query results and any additional metadata returned by `advanced_query_tools.execute_sql`.
    """
    return await advanced_query_tools.execute_sql(
        db=db,
        investigation_id=investigation_id,
        query=query,
        stats=stats,
    )


async def apply_jq_wrapper(
    db: AsyncSession,
    investigation_id: str,
    stats: Dict[str, Any],
    data: Any,
    filter: str,
) -> Dict[str, Any]:
    """
    Apply a JQ filter to JSON data within an investigation context.

    Parameters
    ----------
    db : AsyncSession
        Asynchronous database session (currently unused but retained for signature consistency).
    investigation_id : str
        Identifier of the investigation associated with the query.
    stats : Dict[str, Any]
        Dictionary used to collect statistical information about the operation; it is passed through to the underlying tool.
    data : Any
        The JSON-compatible data structure to which the JQ filter will be applied.
    filter : str
        The JQ expression that defines how `data` should be transformed.

    Returns
    -------
    Dict[str, Any]
        The result of applying the JQ filter, as returned by `advanced_query_tools.apply_jq`.

    Raises
    ------
    Exception
        Propagates any exception raised by `advanced_query_tools.apply_jq`.
    """
    return await advanced_query_tools.apply_jq(
        data=data,
        filter=filter,
        stats=stats,
    )


async def render_diagram_wrapper(
    db: AsyncSession,
    investigation_id: str,
    stats: Dict[str, Any],
    source: str,
    format: str = "mermaid",
    description: str = "",
) -> Dict[str, Any]:
    """
    Render a diagram based on the provided source description.

    Parameters
    ----------
    db : AsyncSession
        Asynchronous database session used for any required data access during rendering.
    investigation_id : str
        Identifier of the investigation context in which the diagram is being generated.
    stats : dict[str, Any]
        Statistics or metadata related to the current investigation; may be used by the rendering process.
    source : str
        The raw description of the diagram (e.g., Mermaid syntax) to be rendered.
    format : str, optional
        Desired output format for the diagram. Defaults to `"mermaid"`, but other formats supported by the underlying tool can be specified.
    description : str, optional
        Additional human-readable description or title for the diagram.

    Returns
    -------
    dict[str, Any]
        A dictionary containing the rendered diagram data, typically including keys such as `"content"` with the diagram markup and `"type"` indicating the format.
    """
    return await diagram_tools.render_diagram(
        source=source,
        format=format,
        description=description,
    )



def register_all_tools():
    """
    Register all investigative tools with the global tool registry.

    This function creates :class:`ToolSpec` instances for each supported operation-event queries, timeline management, control actions, web and hybrid searches, advanced SQL/JQ queries, and diagram rendering-and registers them via `tool_registry.register`. After registration it logs the total number of tools available. No arguments are required and the function does not return a value.
    """

    # Event query tools
    tool_registry.register(
        ToolSpec(
            name="search_events_by_type",
            description="Search events by type (supports * wildcards). Returns paginated results (default 50 events). Use offset for pagination to explore more results. Set auto_register=true to register ALL results to timeline.",
            parameters={
                "type": "object",
                "properties": {
                    "event_type": {
                        "type": "string",
                        "description": "Event type pattern (e.g., 'evtx_security_4624', 'evtx_*', 'registry_*')",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of events to return (default 50, max 50)",
                        "default": 50,
                    },
                    "offset": {"type": "integer", "description": "Pagination offset", "default": 0},
                    "description": {
                        "type": "string",
                        "description": "Brief description of what you're searching for (shown in UI and used for timeline entries)",
                    },
                    "auto_register": {
                        "type": "boolean",
                        "description": "If true, automatically register ALL matching events to timeline (use when user asks to 'find and register')",
                        "default": False,
                    },
                },
                "required": ["event_type", "description"],
            },
            impl=search_events_by_type_wrapper,
        )
    )

    tool_registry.register(
        ToolSpec(
            name="search_events_by_timerange",
            description="Search events within a time range. Returns paginated results (default 50 events). Use offset for pagination to explore more results. Set auto_register=true to register ALL results to timeline.",
            parameters={
                "type": "object",
                "properties": {
                    "start_time": {
                        "type": "string",
                        "description": "Start time (ISO format)",
                    },
                    "end_time": {
                        "type": "string",
                        "description": "End time (ISO format)",
                    },
                    "event_type": {
                        "type": "string",
                        "description": "Optional event type filter (supports wildcards)",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of events to return",
                        "default": 50,
                    },
                    "description": {
                        "type": "string",
                        "description": "Brief description of what you're searching for (shown in UI and used for timeline entries)",
                    },
                    "auto_register": {
                        "type": "boolean",
                        "description": "If true, automatically register ALL matching events to timeline",
                        "default": False,
                    },
                },
                "required": ["description"],
            },
            impl=search_events_by_timerange_wrapper,
        )
    )

    tool_registry.register(
        ToolSpec(
            name="search_events_by_content",
            description="Full-text search in event payloads. Returns paginated results (default 50 events). Use offset for pagination to explore more results. Set auto_register=true to register ALL results to timeline.",
            parameters={
                "type": "object",
                "properties": {
                    "search_text": {
                        "type": "string",
                        "description": "Text to search for in event payloads",
                    },
                    "event_type": {"type": "string", "description": "Optional event type filter"},
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of events to return",
                        "default": 50,
                    },
                    "description": {
                        "type": "string",
                        "description": "Brief description of what you're searching for (shown in UI and used for timeline entries)",
                    },
                    "auto_register": {
                        "type": "boolean",
                        "description": "If true, automatically register ALL matching events to timeline",
                        "default": False,
                    },
                },
                "required": ["search_text", "description"],
            },
            impl=search_events_by_content_wrapper,
        )
    )

    tool_registry.register(
        ToolSpec(
            name="get_event_by_id",
            description="Retrieve a specific event by its ID.",
            parameters={
                "type": "object",
                "properties": {
                    "event_id": {"type": "integer", "description": "Event ID to retrieve"},
                    "description": {
                        "type": "string",
                        "description": "Brief description of why you're retrieving this event (shown in UI)",
                    },
                },
                "required": ["event_id", "description"],
            },
            impl=get_event_by_id_wrapper,
        )
    )

    tool_registry.register(
        ToolSpec(
            name="count_events",
            description="Count events matching criteria.",
            parameters={
                "type": "object",
                "properties": {
                    "event_type": {"type": "string", "description": "Optional event type filter"},
                    "start_time": {"type": "string", "description": "Optional start time filter"},
                    "end_time": {"type": "string", "description": "Optional end time filter"},
                    "description": {
                        "type": "string",
                        "description": "Brief description of what you're counting (shown in UI)",
                    },
                },
                "required": ["description"],
            },
            impl=count_events_wrapper,
        )
    )

    tool_registry.register(
        ToolSpec(
            name="query_jsonb_field",
            description="Query specific JSONB fields in event payloads. Returns paginated results (default 50 events). Use offset for pagination to explore more results. Set auto_register=true to register ALL results to timeline.",
            parameters={
                "type": "object",
                "properties": {
                    "jsonb_path": {
                        "type": "string",
                        "description": "Dotted path to field (e.g., 'TargetUserName', 'system.Computer')",
                    },
                    "operator": {
                        "type": "string",
                        "description": "Comparison operator (=, !=, >, <, >=, <=, LIKE, ILIKE, CONTAINS)",
                        "default": "=",
                    },
                    "value": {"type": "string", "description": "Value to compare against"},
                    "event_type": {"type": "string", "description": "Optional event type filter"},
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of events to return",
                        "default": 50,
                    },
                    "description": {
                        "type": "string",
                        "description": "Brief description of what you're searching for (shown in UI and used for timeline entries)",
                    },
                    "auto_register": {
                        "type": "boolean",
                        "description": "If true, automatically register ALL matching events to timeline",
                        "default": False,
                    },
                },
                "required": ["jsonb_path", "description"],
            },
            impl=query_jsonb_field_wrapper,
        )
    )

    tool_registry.register(
        ToolSpec(
            name="aggregate_jsonb_field",
            description="Aggregate values from a JSONB field to find patterns.",
            parameters={
                "type": "object",
                "properties": {
                    "jsonb_path": {
                        "type": "string",
                        "description": "Dotted path to field to aggregate",
                    },
                    "aggregation": {
                        "type": "string",
                        "description": "Aggregation type (count, distinct, top_values)",
                        "default": "count",
                    },
                    "event_type": {"type": "string", "description": "Optional event type filter"},
                    "limit": {
                        "type": "integer",
                        "description": "Maximum results for top_values",
                        "default": 20,
                    },
                    "description": {
                        "type": "string",
                        "description": "Brief description of what you're aggregating (shown in UI)",
                    },
                },
                "required": ["jsonb_path", "description"],
            },
            impl=aggregate_jsonb_field_wrapper,
        )
    )

    # Timeline tools
    tool_registry.register(
        ToolSpec(
            name="register_timeline_entry",
            description="Add an event to the evidence timeline. System auto-fetches complete event data.",
            parameters={
                "type": "object",
                "properties": {
                    "event_id": {"type": "integer", "description": "Event ID to add to timeline"},
                    "title": {
                        "type": "string",
                        "description": "Brief title for this timeline entry",
                    },
                    "entry_type": {
                        "type": "string",
                        "description": "Entry type (event, pattern, anomaly)",
                        "default": "event",
                    },
                    "description": {
                        "type": "string",
                        "description": "Description of what happened (factual observation)",
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Tags for categorization (neutral terms)",
                    },
                },
                "required": ["event_id", "title"],
            },
            impl=register_timeline_entry_wrapper,
        )
    )

    tool_registry.register(
        ToolSpec(
            name="register_finding",
            description="Record an investigation finding with supporting evidence.",
            parameters={
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Finding title"},
                    "description": {"type": "string", "description": "Detailed description"},
                    "severity": {
                        "type": "string",
                        "description": "Severity level (low, medium, high)",
                        "default": "medium",
                    },
                    "evidence_event_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "Event IDs supporting this finding",
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Tags for categorization",
                    },
                },
                "required": ["title"],
            },
            impl=register_finding_wrapper,
        )
    )

    # Control tools
    tool_registry.register(
        ToolSpec(
            name="complete_investigation",
            description="Signal investigation completion with summary. MUST be called when finished.",
            parameters={
                "type": "object",
                "properties": {
                    "summary": {
                        "type": "string",
                        "description": "Brief summary of findings (2-3 sentences)",
                    },
                    "timeline_entries_count": {
                        "type": "integer",
                        "description": "Number of timeline entries created",
                        "default": 0,
                    },
                    "key_findings": {"type": "string", "description": "Key findings (optional)"},
                    "recommendations": {
                        "type": "string",
                        "description": "Recommendations (optional)",
                    },
                },
                "required": ["summary"],
            },
            impl=complete_investigation_wrapper,
        )
    )

    tool_registry.register(
        ToolSpec(
            name="request_additional_turns",
            description="Request additional investigation turns beyond initial budget. Use when more investigation is needed to reach a conclusion. Requires detailed justification.",
            parameters={
                "type": "object",
                "properties": {
                    "turns_requested": {
                        "type": "integer",
                        "description": "Number of additional turns needed (1-10)",
                        "default": 3,
                    },
                    "justification": {
                        "type": "string",
                        "description": "Detailed explanation of why additional turns are needed (minimum 20 characters). Explain what you've discovered so far and what additional investigation is needed.",
                    },
                },
                "required": ["justification"],
            },
            impl=request_additional_turns_wrapper,
        )
    )

    # Web search tool
    tool_registry.register(
        ToolSpec(
            name="retrieve_and_parse_url",
            description="Retrieve and parse article content from a URL (for research/context).",
            parameters={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to retrieve and parse"}
                },
                "required": ["url"],
            },
            impl=retrieve_and_parse_url_wrapper,
        )
    )

    # Hybrid search tool (BM25 + Vector)
    tool_registry.register(
        ToolSpec(
            name="hybrid_search",
            description="Advanced hybrid search combining BM25 full-text ranking with vector similarity. Returns events ranked by weighted fusion of both methods. Ideal for semantic queries.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Free-text search query"},
                    "bm25_weight": {
                        "type": "number",
                        "description": "Weight for BM25 score (0.0 to 1.0). Default 0.5 balances both methods. Higher values favor keyword matching.",
                        "default": 0.5,
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of events to return (default 50, max 100)",
                        "default": 50,
                    },
                    "offset": {"type": "integer", "description": "Pagination offset", "default": 0},
                    "description": {
                        "type": "string",
                        "description": "Brief description of what you're searching for (shown in UI)",
                    },
                },
                "required": ["query"],
            },
            impl=hybrid_search_wrapper,
        )
    )

    # Advanced query tools (SQL/JQ)
    tool_registry.register(
        ToolSpec(
            name="execute_sql",
            description="Execute a read-only SQL SELECT query against the events table. Queries are scoped to this investigation and have a 5-second timeout. Max 1000 rows returned. Must include 'WHERE investigation_id = :investigation_id' for security.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "SQL SELECT query. Must filter by investigation_id. Example: SELECT event_type, COUNT(*) FROM events WHERE investigation_id = :investigation_id GROUP BY event_type",
                    }
                },
                "required": ["query"],
            },
            impl=execute_sql_wrapper,
        )
    )

    tool_registry.register(
        ToolSpec(
            name="apply_jq",
            description="Apply a JQ filter to JSON data for complex transformations and queries. Useful for extracting nested fields, filtering arrays, or reshaping data. Has a 5-second timeout.",
            parameters={
                "type": "object",
                "properties": {
                    "data": {
                        "type": "string",
                        "description": "JSON data to filter (as JSON string)",
                    },
                    "filter": {
                        "type": "string",
                        "description": "JQ filter expression. Examples: '.[] | select(.status == \"ok\")', '[.events[] | {id: .event_id, type: .event_type}]', '.payload.TargetUserName'",
                    },
                },
                "required": ["data", "filter"],
            },
            impl=apply_jq_wrapper,
        )
    )

    # Diagram generation tool
    tool_registry.register(
        ToolSpec(
            name="render_diagram",
            description="Generate GraphViz or Mermaid diagram from a high-level description. Useful for visualizing process trees, network relationships, timelines, or interaction flows. The tool parses your description and generates appropriate diagram syntax.",
            parameters={
                "type": "object",
                "properties": {
                    "source": {
                        "type": "string",
                        "description": "High-level description of the diagram. Examples: 'process tree: explorer.exe→cmd.exe→powershell.exe', 'timeline: 2024-03-20 14:30 User login, 14:35 File created', 'sequence: User calls API, API queries Database, Database responds'",
                    },
                    "format": {
                        "type": "string",
                        "enum": ["graphviz", "mermaid"],
                        "description": "Diagram format: 'graphviz' for complex graphs, 'mermaid' for flowcharts/sequences/timelines",
                        "default": "mermaid",
                    },
                    "description": {
                        "type": "string",
                        "description": "Brief description of what the diagram shows (shown in UI)",
                    },
                },
                "required": ["source", "description"],
            },
            impl=render_diagram_wrapper,
        )
    )

    logger.info(f"Registered {len(tool_registry.get_all())} tools")


# Auto-register on import
register_all_tools()
