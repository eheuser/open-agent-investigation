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
    analysis_tools,
)

from app.utils.log_setup import get_logger

logger = get_logger(__name__)


async def search_events_by_type_wrapper(
    db: AsyncSession,
    investigation_id: str,
    stats: Dict[str, Any],
    event_type: str,
    limit: int = 50,
    offset: int = 0,
    description: str = "",
) -> Dict[str, Any]:
    """
    Search events by type.

    Parameters
    ----------
    db: AsyncSession
        Asynchronous database session.
    investigation_id: str
        Investigation identifier.
    stats: Dict[str, Any]
        Statistics dictionary.
    event_type: str
        Event type pattern (supports * wildcards).
    limit: int, default 50
        Maximum number of events to return.
    offset: int, default 0
        Pagination offset.
    description: str, default ""
        Brief description shown in UI.

    Returns
    -------
    Dict[str, Any]
        Search results with events list.
    """
    return await event_tools.search_events_by_type(
        db, investigation_id, event_type, limit, offset, stats
    )


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
) -> Dict[str, Any]:
    """
    Search events within a time range.

    Parameters
    ----------
    db: AsyncSession
        Asynchronous database session.
    investigation_id: str
        Investigation identifier.
    stats: Dict[str, Any]
        Statistics dictionary.
    start_time: Optional[str], default None
        Start time (ISO-8601 format).
    end_time: Optional[str], default None
        End time (ISO-8601 format).
    event_type: Optional[str], default None
        Optional event type filter.
    limit: int, default 50
        Maximum number of events to return.
    offset: int, default 0
        Pagination offset.
    description: str, default ""
        Brief description shown in UI.

    Returns
    -------
    Dict[str, Any]
        Search results with events list.
    """
    return await event_tools.search_events_by_timerange(
        db, investigation_id, start_time, end_time, event_type, limit, offset, stats
    )


async def search_events_by_content_wrapper(
    db: AsyncSession,
    investigation_id: str,
    stats: Dict[str, Any],
    search_text: str,
    event_type: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    description: str = "",
) -> Dict[str, Any]:
    """
    Search event payloads for text content.

    Parameters
    ----------
    db: AsyncSession
        Asynchronous database session.
    investigation_id: str
        Investigation identifier.
    stats: Dict[str, Any]
        Statistics dictionary.
    search_text: str
        Text to search for in payloads.
    event_type: Optional[str], default None
        Optional event type filter.
    limit: int, default 50
        Maximum number of events to return.
    offset: int, default 0
        Pagination offset.
    description: str, default ""
        Brief description shown in UI.

    Returns
    -------
    Dict[str, Any]
        Search results with events list.
    """
    return await event_tools.search_events_by_content(
        db,
        investigation_id,
        search_text=search_text,
        event_type=event_type,
        limit=limit,
        offset=offset,
        stats=stats,
    )


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
) -> Dict[str, Any]:
    """
    Query events using JSONB path expressions.

    Parameters
    ----------
    db: AsyncSession
        Asynchronous database session.
    investigation_id: str
        Investigation identifier.
    stats: Dict[str, Any]
        Statistics dictionary.
    jsonb_path: str
        JSONB path expression (e.g., 'event_data.TargetUserName').
    operator: str, default "="
        Comparison operator (=, !=, >, <, >=, <=, LIKE, ILIKE, CONTAINS).
    value: Optional[str], default None
        Value to compare against.
    event_type: Optional[str], default None
        Optional event type filter.
    limit: int, default 50
        Maximum number of events to return.
    offset: int, default 0
        Pagination offset.
    description: str, default ""
        Brief description shown in UI.

    Returns
    -------
    Dict[str, Any]
        Query results with events list.
    """
    return await event_tools.query_jsonb_field(
        db, investigation_id, jsonb_path, operator, value, event_type, limit, offset, stats
    )


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


async def discover_jsonb_fields_wrapper(
    db: AsyncSession,
    investigation_id: str,
    stats: Dict[str, Any],
    event_type: Optional[str] = None,
    sample_size: int = 10,
    limit: int = 50,
    description: str = "",
) -> Dict[str, Any]:
    """
    Discover available JSONB fields for a specific event type with sample values.
    
    This is a Tier 2 just-in-time field discovery tool that allows agents to explore
    what fields are available in specific event types when they need more detail than
    the initial context provides.
    
    Parameters
    ----------
    db : AsyncSession
        Asynchronous database session.
    investigation_id : str
        Investigation identifier.
    stats : Dict[str, Any]
        Statistics dictionary.
    event_type : Optional[str], default None
        Event type pattern to inspect (supports wildcards like 'evtx_security_*').
        If omitted, discovers fields across all event types.
    sample_size : int, default 10
        Number of events to sample per event type.
    limit : int, default 50
        Maximum number of fields to return.
    description : str, default ""
        Brief description of what you're investigating (shown in UI).
    
    Returns
    -------
    Dict[str, Any]
        Field discovery results with paths, frequencies, and sample values.
    """
    return await event_tools.discover_jsonb_fields(
        db=db,
        investigation_id=investigation_id,
        event_type=event_type,
        sample_size=sample_size,
        limit=limit,
        stats=stats,
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


async def query_analysis_module_wrapper(
    db: AsyncSession,
    investigation_id: str,
    stats: Dict[str, Any],
    module_id: str,
    page: int = 1,
    page_size: int = 50,
    filters: Optional[Dict[str, list]] = None,
    description: str = "",
) -> Dict[str, Any]:
    """
    Query a forensic analysis module for high-level insights.

    Parameters
    ----------
    db : AsyncSession
        Asynchronous database session.
    investigation_id : str
        Investigation identifier.
    stats : Dict[str, Any]
        Statistics dictionary.
    module_id : str
        Analysis module ID (autoruns, execution_evidence, browsed_urls, logons).
    page : int, optional
        Page number (1-indexed), defaults to 1.
    page_size : int, optional
        Results per page (max 50), defaults to 50.
    filters : Optional[Dict[str, list]], optional
        Module-specific filters (e.g., {"categories": ["Logon", "Services"]}).
    description : str, optional
        Description of what you're looking for.

    Returns
    -------
    Dict[str, Any]
        Analysis results with entries, pagination info, and summary statistics.
    """
    return await analysis_tools.query_analysis_module(
        db=db,
        investigation_id=investigation_id,
        module_id=module_id,
        page=page,
        page_size=page_size,
        filters=filters,
        description=description,
    )


async def list_analysis_modules_wrapper(
    db: AsyncSession,
    investigation_id: str,
    stats: Dict[str, Any],
) -> Dict[str, Any]:
    """
    List available forensic analysis modules.

    Parameters
    ----------
    db : AsyncSession
        Asynchronous database session.
    investigation_id : str
        Investigation identifier.
    stats : Dict[str, Any]
        Statistics dictionary (unused, kept for signature compatibility).

    Returns
    -------
    Dict[str, Any]
        List of available modules with metadata.
    """
    # Note: stats parameter is unused but kept for wrapper signature consistency
    return await analysis_tools.list_analysis_modules(
        db=db,
        investigation_id=investigation_id,
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
            description="Search events by event type only (supports * wildcards). For time-based filtering, use search_events_by_timerange instead. Returns paginated results (default 50 events). Use offset for pagination.",
            parameters={
                "type": "object",
                "properties": {
                    "event_type": {
                        "type": "string",
                        "description": "Event type pattern (e.g., 'evtx_security_4624', 'evtx_*', 'registry_*'). This is the ONLY filter - no time filtering available.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of events to return (default 50, max 50)",
                        "default": 50,
                    },
                    "offset": {"type": "integer", "description": "Pagination offset", "default": 0},
                    "description": {
                        "type": "string",
                        "description": "Brief description of what you're searching for (shown in UI)",
                    },
                },
                "required": ["event_type", "description"],
                "additionalProperties": False,
            },
            impl=search_events_by_type_wrapper,
        )
    )

    tool_registry.register(
        ToolSpec(
            name="search_events_by_timerange",
            description="Search events within a time range. Optionally filter by event type. Returns paginated results (default 50 events). Use offset for pagination to explore more results.",
            parameters={
                "type": "object",
                "properties": {
                    "start_time": {
                        "type": "string",
                        "description": "Start time (ISO-8601 format, e.g., '2021-05-08T08:18:53+00:00')",
                    },
                    "end_time": {
                        "type": "string",
                        "description": "End time (ISO-8601 format, e.g., '2023-03-08T03:19:30+00:00')",
                    },
                    "event_type": {
                        "type": "string",
                        "description": "Optional event type filter (supports wildcards like 'evtx_sysmon_*')",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of events to return",
                        "default": 50,
                    },
                    "offset": {"type": "integer", "description": "Pagination offset", "default": 0},
                    "description": {
                        "type": "string",
                        "description": "Brief description of what you're searching for (shown in UI)",
                    },
                },
                "required": ["description"],
                "additionalProperties": False,
            },
            impl=search_events_by_timerange_wrapper,
        )
    )

    tool_registry.register(
        ToolSpec(
            name="search_events_by_content",
            description="Full-text search in event payloads. Returns paginated results (default 50 events). Use offset for pagination to explore more results.",
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
                    "offset": {"type": "integer", "description": "Pagination offset", "default": 0},
                    "description": {
                        "type": "string",
                        "description": "Brief description of what you're searching for (shown in UI)",
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
            description="Query specific JSONB fields in event payloads. Returns paginated results (default 50 events). Use offset for pagination. NOTE: Does NOT support time filtering (start_time/end_time) - use count_events for time-based queries or filter results manually.",
            parameters={
                "type": "object",
                "properties": {
                    "jsonb_path": {
                        "type": "string",
                        "description": "Dotted path to field (e.g., 'event_data.TargetUserName', 'event_data.LogonType'). Use exact field names from available JSONB fields.",
                    },
                    "operator": {
                        "type": "string",
                        "description": "Comparison operator (=, !=, >, <, >=, <=, LIKE, ILIKE, CONTAINS)",
                        "default": "=",
                    },
                    "value": {"type": "string", "description": "Value to compare against (e.g., '3' for LogonType 3)"},
                    "event_type": {"type": "string", "description": "OPTIONAL event type filter (e.g., 'evtx_security_4624'). This is the ONLY filter - NO time filtering."},
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of events to return",
                        "default": 50,
                    },
                    "offset": {"type": "integer", "description": "Pagination offset", "default": 0},
                    "description": {
                        "type": "string",
                        "description": "Brief description of what you're searching for (shown in UI)",
                    },
                },
                "required": ["jsonb_path", "description"],
                "additionalProperties": False,
            },
            impl=query_jsonb_field_wrapper,
        )
    )

    tool_registry.register(
        ToolSpec(
            name="aggregate_jsonb_field",
            description="Aggregate values from a JSONB field to find patterns and distributions. NOTE: This tool does NOT support time filtering (start_time/end_time). Use event_type filter if needed, or use query_jsonb_field for time-based filtering.",
            parameters={
                "type": "object",
                "properties": {
                    "jsonb_path": {
                        "type": "string",
                        "description": "Dotted path to field to aggregate (e.g., 'event_data.TargetUserName', 'event_data.IpAddress')",
                    },
                    "aggregation": {
                        "type": "string",
                        "description": "Aggregation type (count, distinct, top_values)",
                        "default": "count",
                    },
                    "event_type": {"type": "string", "description": "OPTIONAL event type filter (e.g., 'evtx_security_4624'). This is the ONLY filter available - NO time filtering."},
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
                "additionalProperties": False,
            },
            impl=aggregate_jsonb_field_wrapper,
        )
    )

    tool_registry.register(
        ToolSpec(
            name="discover_jsonb_fields",
            description="Discover available JSONB fields for specific event types with frequency and sample values. Use this when you need to know what fields exist in a particular event type before querying. Shows field paths, how often they appear, and example values. This helps you build accurate query_jsonb_field queries.",
            parameters={
                "type": "object",
                "properties": {
                    "event_type": {
                        "type": "string",
                        "description": "Event type pattern to inspect (e.g., 'evtx_security_4624', 'evtx_sysmon_*'). If omitted, discovers fields across all event types.",
                    },
                    "sample_size": {
                        "type": "integer",
                        "description": "Number of events to sample per event type (default 10)",
                        "default": 10,
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of fields to return (default 50)",
                        "default": 50,
                    },
                    "description": {
                        "type": "string",
                        "description": "Brief description of what you're investigating (shown in UI)",
                    },
                },
                "required": ["description"],
                "additionalProperties": False,
            },
            impl=discover_jsonb_fields_wrapper,
        )
    )

    # Timeline tools
    tool_registry.register(
        ToolSpec(
            name="register_timeline_entry",
            description="Register FORENSICALLY SIGNIFICANT events to timeline. ONLY use for: malicious activity, security incidents, attack indicators, compromise evidence, or user-requested events. DO NOT register routine system operations, benign tasks, or normal maintenance activities. Quality over quantity - be highly selective.",
            parameters={
                "type": "object",
                "properties": {
                    "event_id": {
                        "type": "integer", 
                        "description": "Event ID to register. MUST be forensically significant - not routine system activity."
                    },
                    "title": {
                        "type": "string",
                        "description": "Brief forensic title explaining WHY this event is significant (not just what happened)",
                    },
                    "entry_type": {
                        "type": "string",
                        "description": "Entry type (event, pattern, anomaly)",
                        "default": "event",
                    },
                    "description": {
                        "type": "string",
                        "description": "Detailed forensic analysis: WHY is this significant? What does it indicate? How does it relate to the investigation?",
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Forensic tags (e.g., 'malware', 'lateral-movement', 'privilege-escalation', 'suspicious', 'persistence')",
                    },
                },
                "required": ["event_id", "title", "description"],
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
            description="Execute a read-only SQL SELECT query against the events table. Queries are scoped to this investigation and have a 30-second timeout. Max 1000 rows returned. Must include 'WHERE investigation_id = :investigation_id' for security. \n\nEVENTS TABLE SCHEMA:\n- event_id (BIGINT): Unique event identifier\n- investigation_id (UUID): Investigation identifier (REQUIRED in WHERE clause)\n- event_ts (TIMESTAMPTZ): Event timestamp (NOT 'timestamp')\n- artifact_id (BIGINT): Source artifact ID\n- event_type (TEXT): Event type (e.g., 'evtx_security_4624')\n- payload (JSONB): Full event data\n\nIMPORTANT: Use 'event_ts' for timestamps, NOT 'timestamp'. Use JSONB operators for payload queries: ->, ->>, @>, etc.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "SQL SELECT query. Must filter by investigation_id. Use 'event_ts' for timestamps. Examples: SELECT event_type, COUNT(*) FROM events WHERE investigation_id = :investigation_id GROUP BY event_type | SELECT * FROM events WHERE investigation_id = :investigation_id AND event_ts BETWEEN '2022-11-15T21:00:00Z' AND '2022-11-15T22:00:00Z' ORDER BY event_ts ASC",
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

    # Analysis module tools
    tool_registry.register(
        ToolSpec(
            name="query_analysis_module",
            description="Query forensic analysis modules for high-level insights from processed artifacts. Use this instead of querying raw events for: persistence mechanisms (autoruns), program execution evidence (execution_evidence), browser history (browsed_urls), or logon activity (logons). Results are pre-processed and paginated (max 50 per page).",
            parameters={
                "type": "object",
                "properties": {
                    "module_id": {
                        "type": "string",
                        "enum": ["autoruns", "execution_evidence", "browsed_urls", "logons", "user_activity"],
                        "description": "Analysis module: 'autoruns' (persistence), 'execution_evidence' (program execution), 'browsed_urls' (browser history), 'logons' (logon/logoff events), 'user_activity' (ShellBags, RecentDocs, OpenSaveMRU, TypedPaths, RunMRU, WordWheelQuery)",
                    },
                    "page": {
                        "type": "integer",
                        "description": "Page number (1-indexed, default: 1)",
                        "default": 1,
                    },
                    "page_size": {
                        "type": "integer",
                        "description": "Results per page (max 50, default: 50)",
                        "default": 50,
                    },
                    "filters": {
                        "type": "object",
                        "description": "Module-specific filters. For autoruns/execution_evidence/user_activity: {\"categories\": [\"Logon\", \"Services\"]} or {\"categories\": [\"shellbags\", \"recentdocs\", \"runmru\"]}. For browsed_urls: {\"browsers\": [\"chrome_chromium\"]}. For logons: {\"logon_types\": [\"Interactive\"], \"source_ips\": [\"192.168.1.100\"], \"usernames\": [\"admin\"]}",
                        "additionalProperties": True,
                    },
                    "description": {
                        "type": "string",
                        "description": "What you're investigating (shown in UI)",
                    },
                },
                "required": ["module_id", "description"],
                "additionalProperties": False,
            },
            impl=query_analysis_module_wrapper,
        )
    )

    tool_registry.register(
        ToolSpec(
            name="list_analysis_modules",
            description="List available forensic analysis modules to discover what high-level insights are available. Call this first to see what modules exist and what filters they support before querying them.",
            parameters={
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
            impl=list_analysis_modules_wrapper,
        )
    )

    logger.info(f"Registered {len(tool_registry.get_all())} tools")


# Auto-register on import
register_all_tools()
