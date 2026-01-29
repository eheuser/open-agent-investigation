from typing import Dict, List, Any

# Data query tools (Phase 1 - Tool Execution)
# NOTE: search_events_by_type and search_events_by_timerange are disabled
# to encourage focused JSONB field queries instead of broad searches
DATA_QUERY_TOOLS = {
    # "search_events_by_type",        # DISABLED - too broad, use query_jsonb_field instead
    "query_jsonb_field",
    "aggregate_jsonb_field",
    # "search_events_by_timerange",   # DISABLED - too broad, use query_jsonb_field with time filters
    "search_events_by_content",
    "get_event_by_id",
    "get_event_details",
    "count_events",
    "hybrid_search",
    "execute_sql",
    "apply_jq",
}

# Analysis tools (Phase 2 - Result Analysis)
ANALYSIS_TOOLS = {
    "register_timeline_entry",
    "complete_investigation",
    "render_diagram",
}

# Control tools (can be used in Phase 1)
CONTROL_TOOLS = {
    "request_additional_turns",
}


def filter_tools_for_phase(all_tools: List[Dict[str, Any]], phase: str) -> List[Dict[str, Any]]:
    """
    Filter tools based on the current execution phase.

    Args:
        all_tools (List[Dict[str, Any]]): A list of tool specifications in the OpenAI function-calling format.
        phase (str): The workflow phase for which tools are required. Must be either `"tool_execution"` (phase 1) or `"analysis"` (phase 2).

    Returns:
        List[Dict[str, Any]]: A subset of `all_tools` containing only the tools that are permitted in the specified phase.

    Raises:
        ValueError: If `phase` is not one of the recognized values (`"tool_execution"` or `"analysis"`).
    """
    if phase == "tool_execution":
        # Phase 1: Data query tools + control tools
        allowed_tools = DATA_QUERY_TOOLS | CONTROL_TOOLS
        return [tool for tool in all_tools if tool.get("function", {}).get("name") in allowed_tools]
    elif phase == "analysis":
        # Phase 2: Only analysis tools
        return [
            tool for tool in all_tools if tool.get("function", {}).get("name") in ANALYSIS_TOOLS
        ]
    else:
        raise ValueError(f"Unknown phase: {phase}")


def is_data_query_tool(tool_name: str) -> bool:
    """
    Check whether the given tool name belongs to the set of data-query tools used in Phase 1.

    Args:
        tool_name: The name of the tool to test.

    Returns:
        True if *tool_name* is present in `DATA_QUERY_TOOLS`, otherwise False.
    """
    return tool_name in DATA_QUERY_TOOLS


def is_analysis_tool(tool_name: str) -> bool:
    """
    Check whether the given tool name belongs to the set of analysis tools used in phase 2.

    Args:
        tool_name: The name of the tool to check.

    Returns:
        True if *tool_name* is present in `ANALYSIS_TOOLS`, otherwise False.
    """
    return tool_name in ANALYSIS_TOOLS


__all__ = [
    "DATA_QUERY_TOOLS",
    "ANALYSIS_TOOLS",
    "filter_tools_for_phase",
    "is_data_query_tool",
    "is_analysis_tool",
]
