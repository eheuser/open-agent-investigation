"""Agent tools for querying events and managing evidence timelines."""

from .event_tools import (
    search_events_by_type,
    search_events_by_timerange,
    search_events_by_content,
    get_event_by_id,
    count_events,
    query_jsonb_field,
    aggregate_jsonb_field,
)
from .timeline_tools import (
    register_timeline_entry,
    register_finding,
    link_to_event,
)
from .control_tools import (
    exit_early,
    complete_investigation,
)
from .analysis_tools import (
    query_analysis_module,
    list_analysis_modules,
)

__all__ = [
    "search_events_by_type",
    "search_events_by_timerange",
    "search_events_by_content",
    "get_event_by_id",
    "count_events",
    "query_jsonb_field",
    "aggregate_jsonb_field",
    "register_timeline_entry",
    "register_finding",
    "link_to_event",
    "exit_early",
    "complete_investigation",
    "query_analysis_module",
    "list_analysis_modules",
]
