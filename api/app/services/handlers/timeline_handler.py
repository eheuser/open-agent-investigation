import json
from typing import Dict, Any, List
from uuid import UUID
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from ...crud.llm_config import get_active_llm_config
from ..llm_service import LLMService
from ..context_manager import TimelineContextManager

from app.utils.log_setup import get_logger

logger = get_logger(__name__)


# Timeline tools available to LLM
TIMELINE_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "query_timeline_entries",
            "description": "Search and filter timeline entries. Returns entries with their linked event data.",
            "parameters": {
                "type": "object",
                "properties": {
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Filter by tags (entries must have ALL specified tags)",
                    },
                    "start_time": {
                        "type": "string",
                        "description": "ISO 8601 timestamp - filter entries after this time",
                    },
                    "end_time": {
                        "type": "string",
                        "description": "ISO 8601 timestamp - filter entries before this time",
                    },
                    "search_text": {
                        "type": "string",
                        "description": "Search in title and description fields. Use this for keyword-based searches (e.g., 'powershell', 'suspicious', 'malware').",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of entries to return (default 50)",
                        "default": 50,
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_timeline_entry",
            "description": "Create a new timeline entry.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Entry title (required)",
                    },
                    "timestamp": {
                        "type": "string",
                        "description": "ISO 8601 timestamp for the entry",
                    },
                    "entry_type": {
                        "type": "string",
                        "description": "Entry type (default: 'event')",
                        "default": "event",
                    },
                    "description": {
                        "type": "string",
                        "description": "Detailed description",
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Tags for categorization",
                    },
                    "event_id": {
                        "type": "integer",
                        "description": "Link to an event ID (optional)",
                    },
                },
                "required": ["title"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_timeline_entry",
            "description": "Update an existing timeline entry.",
            "parameters": {
                "type": "object",
                "properties": {
                    "entry_id": {
                        "type": "integer",
                        "description": "ID of the entry to update (required)",
                    },
                    "title": {"type": "string"},
                    "timestamp": {"type": "string"},
                    "entry_type": {"type": "string"},
                    "description": {"type": "string"},
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
                "required": ["entry_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_timeline_entry",
            "description": "Delete a timeline entry by ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "entry_id": {
                        "type": "integer",
                        "description": "ID of the entry to delete (required)",
                    },
                },
                "required": ["entry_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_timeline_stats",
            "description": "Get statistics about the timeline (total entries, date range, tags, etc.).",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
]


async def handle_timeline_query(
    db: AsyncSession,
    investigation_id: UUID,
    user_query: str,
    user_id: int,
) -> Dict[str, Any]:
    """
    Handle timeline-specific user queries by orchestrating LLM-driven tool calls with retry and transaction safety.

    The function performs the following steps:

    1. Retrieve the active LLM configuration for the requesting user.
    2. If no configuration is found, return an error payload prompting the user to configure their LLM settings.
    3. Execute the LLM loop that may invoke timeline tools (query, add, update, delete, stats), automatically retrying failed tool calls and ensuring database consistency.
    4. Collect the tool results, let the LLM generate a concise answer to the original question, and produce a brief micro-summary of the operations performed.
    5. Return a dictionary containing either the successful answer and summary or an error description.

    Args:
        db: An asynchronous SQLAlchemy session used for all database interactions within the handler.
        investigation_id: The UUID identifying the investigation whose timeline is being queried.
        user_query: The natural-language query supplied by the user.
        user_id: The identifier of the user making the request; used to fetch the appropriate LLM configuration.

    Returns:
        dict: A mapping with at least two keys:
            - `type` (str): Either `"answer"` for successful processing or `"error"` when a problem occurs.
            - `message` (str): For `"answer"`, this is the generated response; for `"error"`, it explains the failure.
        When `type` is `"answer"`, additional keys may be present:
            - `summary` (str): A concise description of the operations performed by the LLM and tools.

    Raises:
        No exceptions are propagated to callers; all errors are caught, logged, and translated into an error-type dictionary. Transaction rollbacks are attempted on failure.
    """
    logger.debug(f"[TIMELINE_HANDLER] Processing query: {user_query[:100]}")

    try:
        # Get user's active LLM configuration
        llm_config = await get_active_llm_config(db, user_id)

        if not llm_config:
            return {
                "type": "error",
                "message": "No active LLM configuration found. Please configure your LLM settings.",
            }

        # Execute LLM loop with timeline tools
        result = await _execute_timeline_llm_loop(
            db=db,
            investigation_id=investigation_id,
            user_query=user_query,
            user_id=user_id,
            llm_config=llm_config,
        )

        return result

    except Exception as e:
        logger.error(f"[TIMELINE_HANDLER] Critical error: {e}", exc_info=True)
        # Ensure transaction is clean
        try:
            await db.rollback()
        except Exception as rollback_error:
            logger.error(f"[TIMELINE_HANDLER] Rollback failed: {rollback_error}")

        return {
            "type": "error",
            "message": f"Timeline handler error: {str(e)}",
        }


async def _execute_timeline_llm_loop(
    db: AsyncSession,
    investigation_id: UUID,
    user_query: str,
    user_id: int,
    llm_config,
) -> Dict[str, Any]:
    """
    Execute an asynchronous LLM-driven loop that processes a user’s timeline query by orchestrating tool calls and returning a concise answer with a micro-summary.

    Parameters
    ----------
    db: AsyncSession
        The async SQLAlchemy session used for database interactions within tool executions.
    investigation_id: UUID
        Identifier of the investigation whose timeline is being queried or modified.
    user_query: str
        The natural-language request submitted by the user.
    user_id: int
        Database identifier of the user issuing the query; passed to tools for permission checks and auditing.
    llm_config: Any
        Configuration object (or mapping) that can be converted into an :class:`LLMConfig` via `LLMConfig.from_db_config`. It contains model, endpoint, authentication, and other LLM settings.

    Returns
    -------
    dict[str, Any]
        A dictionary describing the outcome of the operation. The possible keys are:

        * `type` - One of `"timeline_answer"`, `"error"`, or other internal types.
        * `success` - Boolean indicating whether the overall process succeeded (present for successful answers).
        * `message` - Final answer generated by the LLM, or an error description.
        * `summary` - A short micro-summary generated from the tools that were invoked.
        * `tools_used` - Integer count of distinct tool calls executed during the loop.
        * `incomplete` - Optional boolean set to `True` when the maximum iteration limit was reached before a final answer could be produced.

    Raises
    ------
    Any exception raised inside the function is caught and transformed into an error-type response dictionary; therefore, the function does not propagate exceptions to callers.
    """
    # Create LLM service from config
    from ..llm_service import LLMConfig

    config = LLMConfig.from_db_config(llm_config)
    llm_service = LLMService(config)

    # Build initial conversation messages using context manager
    messages = TimelineContextManager.prepare_initial_context(
        user_query=user_query,
        max_tokens=2000,
    )

    tools_used = []
    max_iterations = 10  # Increased from 5 to allow more complex operations
    iteration = 0

    try:
        while iteration < max_iterations:
            iteration += 1

            # Call LLM with tools via centralized service
            # Use None for max_tokens and temperature to respect user's DB configuration
            data = await llm_service.call_llm(
                messages=messages,
                max_tokens=None,  # Use user's configured default
                temperature=None,  # Use user's configured temperature
                tools=TIMELINE_TOOLS,
                tool_choice="auto",
                enforce_context_limit=True,
            )

            # Extract assistant message
            if "choices" not in data or len(data["choices"]) == 0:
                return {
                    "type": "error",
                    "message": "LLM returned empty response",
                }

            choice = data["choices"][0]
            assistant_message = choice.get("message", {})

            # Add assistant message to conversation
            messages.append(assistant_message)

            # Check if LLM wants to call tools
            tool_calls = assistant_message.get("tool_calls")

            if not tool_calls:
                # LLM provided final answer
                final_answer = assistant_message.get("content", "")

                # If no answer provided, check for finish_reason
                if not final_answer:
                    finish_reason = choice.get("finish_reason")
                    if finish_reason == "length":
                        logger.warning(
                            f"[TIMELINE_HANDLER] LLM hit token limit after {iteration} iterations"
                        )
                        final_answer = "Timeline operation completed but response was truncated. Please try a more specific query."
                    else:
                        logger.warning(
                            f"[TIMELINE_HANDLER] LLM returned empty content after {iteration} iterations"
                        )
                        final_answer = "Timeline operation completed."

                # Generate micro-summary
                summary = _generate_timeline_summary(tools_used)

                logger.debug(
                    f"[TIMELINE_HANDLER] Completed in {iteration} iterations with {len(tools_used):,} tools"
                )

                # Determine operation type from tools used
                operation_types = []
                if any(t["name"] == "query_timeline_entries" for t in tools_used):
                    operation_types.append("query")
                if any(t["name"] == "add_timeline_entry" for t in tools_used):
                    operation_types.append("add")
                if any(t["name"] == "update_timeline_entry" for t in tools_used):
                    operation_types.append("update")
                if any(t["name"] == "delete_timeline_entry" for t in tools_used):
                    operation_types.append("delete")

                operation_type = "/".join(operation_types) if operation_types else "query"

                return {
                    "type": "timeline_answer",
                    "success": True,
                    "message": final_answer,
                    "summary": summary,
                    "tools_used": len(tools_used),
                    "routing_metadata": {
                        "handler_type": "timeline",
                        "handler_display_name": "Timeline Operations",
                        "operation_type": operation_type,
                        "entries_affected": len(tools_used),
                    },
                }

            # Execute tool calls
            for tool_call in tool_calls:
                function = tool_call.get("function", {})
                tool_name = function.get("name")
                arguments_str = function.get("arguments", "{}")
                tool_call_id = tool_call.get("id")

                try:
                    arguments = json.loads(arguments_str)
                except json.JSONDecodeError:
                    arguments = {}

                logger.debug(f"[TIMELINE_HANDLER] Calling tool: {tool_name} with args: {arguments}")

                # Execute tool with retry - wrap in try/except to ensure transaction stays clean
                try:
                    tool_result = await _execute_timeline_tool_with_retry(
                        db=db,
                        investigation_id=investigation_id,
                        tool_name=tool_name,
                        arguments=arguments,
                        user_id=user_id,
                        max_retries=3,
                    )
                except Exception as tool_error:
                    logger.error(
                        f"[TIMELINE_HANDLER] Tool execution failed critically: {tool_error}",
                        exc_info=True,
                    )
                    # Ensure transaction is clean after critical failure
                    try:
                        await db.rollback()
                    except:
                        pass
                    # Return error result to LLM
                    tool_result = {
                        "success": False,
                        "error": f"Critical tool failure: {str(tool_error)}",
                    }

                tools_used.append(
                    {
                        "name": tool_name,
                        "arguments": arguments,
                        "success": tool_result.get("success", False),
                    }
                )

                # Add tool result to conversation
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call_id,
                        "content": json.dumps(tool_result),
                    }
                )

        # Max iterations reached - provide partial results if we have any
        if tools_used:
            summary = _generate_timeline_summary(tools_used)
            logger.warning(
                f"[TIMELINE_HANDLER] Hit max iterations ({max_iterations}) with {len(tools_used):,} tools executed"
            )
            return {
                "type": "timeline_answer",
                "success": True,
                "message": f"Timeline operation completed {len(tools_used):,} operations but reached complexity limit. Results may be incomplete.",
                "summary": summary,
                "tools_used": len(tools_used),
                "incomplete": True,
            }
        else:
            return {
                "type": "error",
                "message": "Timeline operation took too many steps without completing any operations. Please simplify your request.",
            }

    except Exception as e:
        logger.error(f"Timeline LLM loop failed: {e}", exc_info=True)
        return {
            "type": "error",
            "message": f"Error processing timeline query: {str(e)}",
        }


async def _execute_timeline_tool_with_retry(
    db: AsyncSession,
    investigation_id: UUID,
    tool_name: str,
    arguments: Dict[str, Any],
    user_id: int,
    max_retries: int = 3,
) -> Dict[str, Any]:
    """
    Execute a timeline tool with retry and transaction-savepoint handling.

    This coroutine attempts to run the specified timeline tool up to `max_retries` times. Each attempt is wrapped in a nested database transaction (a savepoint) so that any modifications made by the tool are isolated from the outer transaction. If the tool reports success, the savepoint is committed and the result is returned immediately. When the tool reports an error or raises an exception, the savepoint is rolled back, the failure is logged, and the next retry is attempted.

    Parameters
    ----------
    db : AsyncSession
        The asynchronous SQLAlchemy session used for database operations.
    investigation_id : UUID
        Identifier of the investigation whose timeline is being manipulated.
    tool_name : str
        Name of the timeline tool to invoke (e.g., `query`, `add`, `update`, `delete` or `stats`).
    arguments : dict[str, Any]
        Keyword arguments passed directly to the underlying tool implementation.
    user_id : int
        Identifier of the user requesting the operation; propagated to the tool for permission checks or auditing.
    max_retries : int, optional
        Maximum number of retry attempts (default is 3). The function will try at most this many times before giving up.

    Returns
    -------
    dict[str, Any]
        A dictionary containing at least a `success` key. If `success` is `True`, the tool completed successfully and any additional data returned by the tool is included. If `success` is `False`, an `error` key provides a human-readable description of the failure after all retries have been exhausted.

    Notes
    -----
    * The LLM orchestrating these calls is not informed about intermediate failures; only the final result (successful or error) is returned.
    * Savepoint rollbacks are performed even when exceptions occur during the tool execution, ensuring that partial changes do not leak into the outer transaction.
    """
    last_error = None

    for attempt in range(max_retries):
        savepoint = None
        try:
            # Create a nested transaction (savepoint) for each attempt
            savepoint = await db.begin_nested()

            result = await _execute_timeline_tool(
                db=db,
                investigation_id=investigation_id,
                tool_name=tool_name,
                arguments=arguments,
                user_id=user_id,
            )

            if result.get("success"):
                # Success - commit the savepoint
                await savepoint.commit()
                return result
            else:
                # Tool returned error - rollback the savepoint
                last_error = result.get("error", "Unknown error")
                logger.warning(
                    f"[TIMELINE_HANDLER] Tool {tool_name} failed (attempt {attempt + 1}/{max_retries}): {last_error}"
                )
                await savepoint.rollback()

        except Exception as e:
            last_error = str(e)
            logger.warning(
                f"[TIMELINE_HANDLER] Tool {tool_name} exception (attempt {attempt + 1}/{max_retries}): {e}"
            )
            # Rollback the savepoint if it exists
            if savepoint is not None:
                try:
                    await savepoint.rollback()
                except Exception as rollback_error:
                    logger.error(f"[TIMELINE_HANDLER] Savepoint rollback failed: {rollback_error}")
            # Continue to next retry attempt

    # All retries failed - return error
    return {
        "success": False,
        "error": f"Tool failed after {max_retries} attempts: {last_error}",
    }


async def _execute_timeline_tool(
    db: AsyncSession,
    investigation_id: UUID,
    tool_name: str,
    arguments: Dict[str, Any],
    user_id: int,
) -> Dict[str, Any]:
    """
    Execute a single timeline tool based on its name and arguments.

    Args:
        db: An asynchronous SQLAlchemy session used for all database interactions.
        investigation_id: The UUID of the investigation whose timeline is being manipulated.
        tool_name: Identifier of the tool to invoke. Supported values are
            `query_timeline_entries`, `add_timeline_entry`,
            `update_timeline_entry`, `delete_timeline_entry` and
            `get_timeline_stats`.
        arguments: A dictionary containing the parameters required by the selected
            tool. The exact schema depends on the tool; for example, query tools may
            include filters while add/update tools require entry data.
        user_id: Identifier of the user performing the operation. Required for
            `add_timeline_entry` to attribute ownership.

    Returns:
        A dictionary with at least a `success` boolean key. On success, additional
        keys contain tool-specific results (e.g., queried entries, statistics, or
        confirmation messages). If the tool name is unknown, returns
        `{"success": False, "error": "..."}`.

    Raises:
        No exceptions are raised directly; errors are captured in the returned
        dictionary. Unexpected runtime errors from underlying helper functions will
        propagate as normal asyncio exceptions.
    """
    if tool_name == "query_timeline_entries":
        return await _tool_query_timeline(db, investigation_id, arguments)

    elif tool_name == "add_timeline_entry":
        return await _tool_add_timeline_entry(db, investigation_id, arguments, user_id)

    elif tool_name == "update_timeline_entry":
        return await _tool_update_timeline_entry(db, investigation_id, arguments)

    elif tool_name == "delete_timeline_entry":
        return await _tool_delete_timeline_entry(db, investigation_id, arguments)

    elif tool_name == "get_timeline_stats":
        return await _tool_get_timeline_stats(db, investigation_id)

    else:
        return {
            "success": False,
            "error": f"Unknown tool: {tool_name}",
        }


def _generate_timeline_summary(tools_used: List[Dict[str, Any]]) -> str:
    """
    Generate a concise human-readable summary of the timeline operations performed during an interaction.

    :param tools_used: A list of dictionaries describing each tool invocation. Each dictionary must contain at least the keys `"name"` (the tool identifier) and `"success"` (a boolean indicating whether the call succeeded).
    :type tools_used: List[Dict[str, Any]]

    :return: A short sentence summarising successful operations, e.g. `"Timeline: 2 queries, 1 addition"`; if no tools were used it returns `"No timeline operations performed."`; if all invocations failed it returns `"All timeline operations failed."`.
    :rtype: str

    :raises TypeError: If *tools_used* is not iterable or its elements are not mappings with the required keys.
    """
    if not tools_used:
        return "No timeline operations performed."

    summary_parts = []

    # Count operations by type
    queries = sum(1 for t in tools_used if t["name"] == "query_timeline_entries" and t["success"])
    adds = sum(1 for t in tools_used if t["name"] == "add_timeline_entry" and t["success"])
    updates = sum(1 for t in tools_used if t["name"] == "update_timeline_entry" and t["success"])
    deletes = sum(1 for t in tools_used if t["name"] == "delete_timeline_entry" and t["success"])
    stats = sum(1 for t in tools_used if t["name"] == "get_timeline_stats" and t["success"])

    if queries > 0:
        summary_parts.append(f"{queries} " + ("query" if queries == 1 else "queries"))
    if adds > 0:
        summary_parts.append(f"{adds} addition" + ("" if adds == 1 else "s"))
    if updates > 0:
        summary_parts.append(f"{updates} update" + ("" if updates == 1 else "s"))
    if deletes > 0:
        summary_parts.append(f"{deletes} deletion" + ("" if deletes == 1 else "s"))
    if stats > 0:
        summary_parts.append(f"{stats} stats request" + ("" if stats == 1 else "s"))

    if not summary_parts:
        return "All timeline operations failed."

    return "Timeline: " + ", ".join(summary_parts)


async def _tool_query_timeline(
    db: AsyncSession,
    investigation_id: UUID,
    params: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Execute a timeline query against the database for a specific investigation.

    Args:
        db (AsyncSession): An asynchronous SQLAlchemy session used to run the query.
        investigation_id (UUID): The identifier of the investigation whose timeline entries are being requested.
        params (Dict[str, Any]): A dictionary of optional filter and pagination parameters. Supported keys include:
            - `entry_type` (str): Filter results to a specific entry type.
            - `tags` (list[str]): Return only entries that contain any of the supplied tags.
            - `start_time` (str or datetime): ISO-8601 timestamp or datetime object defining the lower bound for entry timestamps.
            - `end_time` (str or datetime): ISO-8601 timestamp or datetime object defining the upper bound for entry timestamps.
            - `search_text` (str): Case-insensitive substring match against both title and description fields.
            - `limit` (int, optional): Maximum number of entries to return; defaults to 50.

    Returns:
        Dict[str, Any]: A result dictionary containing:
            - `success` (bool): Indicates whether the query completed without error.
            - If `success` is True:
                - `entries` (list[dict]): List of timeline entry dictionaries with keys `entry_id`, `event_id`, `timestamp` (ISO string), `entry_type`, `title`, `description`, `data` (dict), and `tags` (list).
                - `total` (int): Number of entries returned.
            - If `success` is False:
                - `error` (str): String representation of the exception that occurred.

    Raises:
        No exceptions are propagated; any error encountered during query execution is caught, logged, and reported in the returned dictionary.
    """
    # Build query - join with events table to get full event data
    query_parts = [
        "SELECT te.entry_id, te.event_id, te.timestamp, te.entry_type, te.title, te.description, te.data, te.tags,",
        "       e.event_type, e.event_ts, e.payload, e.artifact_id",
        "FROM timeline_entries te",
        "LEFT JOIN events e ON te.event_id = e.event_id",
        "WHERE te.investigation_id = :investigation_id AND te.is_visible = true",
    ]
    query_params: Dict[str, Any] = {"investigation_id": str(investigation_id)}

    # Apply filters
    if "entry_type" in params:
        query_parts.append("AND entry_type = :entry_type")
        query_params["entry_type"] = params["entry_type"]

    if "tags" in params and params["tags"]:
        query_parts.append("AND tags && :tags")
        query_params["tags"] = params["tags"]

    if "start_time" in params:
        query_parts.append("AND timestamp >= :start_time")
        # Convert ISO string to datetime object
        start_time = params["start_time"]
        if isinstance(start_time, str):
            start_time = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
        query_params["start_time"] = start_time

    if "end_time" in params:
        query_parts.append("AND timestamp <= :end_time")
        # Convert ISO string to datetime object
        end_time = params["end_time"]
        if isinstance(end_time, str):
            end_time = datetime.fromisoformat(end_time.replace("Z", "+00:00"))
        query_params["end_time"] = end_time

    if "search_text" in params:
        query_parts.append("AND (title ILIKE :search OR description ILIKE :search)")
        query_params["search"] = f"%{params['search_text']}%"

    # Order and limit
    query_parts.append("ORDER BY timestamp DESC")
    limit = params.get("limit", 50)
    query_parts.append(f"LIMIT {limit}")

    query = text(" ".join(query_parts))

    try:
        result = await db.execute(query, query_params)
        rows = result.fetchall()

        # Format results with event data
        entries = []
        for row in rows:
            entry = {
                "entry_id": row[0],
                "event_id": row[1],
                "timestamp": row[2].isoformat() if row[2] else None,
                "entry_type": row[3],
                "title": row[4],
                "description": row[5],
                "data": row[6] or {},
                "tags": row[7] or [],
            }

            # Include full event data if available (from LEFT JOIN)
            if row[1] and row[8]:  # event_id exists and event_type exists
                entry["event"] = {
                    "event_id": row[1],
                    "event_type": row[8],
                    "timestamp": str(row[9]) if row[9] else "unknown time",
                    "payload": row[10],
                    "artifact_id": row[11],
                }

            entries.append(entry)

        return {
            "success": True,
            "entries": entries,
            "total": len(entries),
        }
    except Exception as e:
        logger.error(f"Query timeline failed: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
        }


async def _tool_add_timeline_entry(
    db: AsyncSession,
    investigation_id: UUID,
    params: Dict[str, Any],
    user_id: int,
) -> Dict[str, Any]:
    """
    Add a new timeline entry to the database.

    Parameters
    ----------
    db: AsyncSession
        Asynchronous SQLAlchemy session used to execute the INSERT statement.
    investigation_id: UUID
        Identifier of the investigation to which the timeline entry belongs.
    params: dict[str, Any]
        Dictionary containing the fields for the new entry. Expected keys:

        * `title` (str, required) - Title of the entry.
        * `entry_type` (str, optional) - Type of the entry; defaults to `"event"`.
        * `timestamp` (datetime | str, optional) - Timestamp of the event; if omitted the current UTC time is used. ISO-8601 strings are parsed automatically.
        * `description` (str, optional) - Free-form description.
        * `tags` (list[str], optional) - List of tags associated with the entry.
        * `data` (dict, optional) - Arbitrary JSON-serialisable payload.
        * `event_id` (int | None, optional) - Identifier of a related event, if any.
    user_id: int
        Identifier of the user creating the entry; stored as `created_by_user_id`.

    Returns
    -------
    dict[str, Any]
        A result dictionary with the following keys:

        * `success` (bool) - `True` if the entry was created successfully, otherwise `False`.
        * On success:
            - `entry_id` (int) - Primary key of the newly created timeline entry.
            - `timestamp` (str | None) - ISO-8601 representation of the stored timestamp.
            - `title` (str) - Title of the created entry.
        * On failure:
            - `error` (str) - Human-readable error message describing why creation failed.

    Notes
    -----
    * If the required `title` field is missing, the function returns early with `success=False` and an appropriate error message.
    * The `timestamp` value may be supplied as a string; it will be converted to a `datetime` object, handling trailing `Z` UTC designators.
    * All JSON payloads are stored using PostgreSQL's `jsonb` type via `CAST(:data AS jsonb)`.
    """
    # Validate required fields
    if "title" not in params:
        return {
            "success": False,
            "error": "Missing required field: title",
        }

    # Default values
    entry_type = params.get("entry_type", "event")
    timestamp = params.get("timestamp", datetime.utcnow())
    # Convert ISO string to datetime object if needed
    if isinstance(timestamp, str):
        timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    description = params.get("description", "")
    tags = params.get("tags", [])
    data = params.get("data", {})
    event_id = params.get("event_id")

    # Insert entry
    query = text(
        """
        INSERT INTO timeline_entries
        (investigation_id, event_id, timestamp, entry_type, title, description, data, tags, created_by_user_id, is_visible)
        VALUES (:investigation_id, :event_id, :timestamp, :entry_type, :title, :description,
                CAST(:data AS jsonb), :tags, :user_id, true)
        RETURNING entry_id, timestamp, title
    """
    )

    try:
        result = await db.execute(
            query,
            {
                "investigation_id": str(investigation_id),
                "event_id": event_id,
                "timestamp": timestamp,
                "entry_type": entry_type,
                "title": params["title"],
                "description": description,
                "data": json.dumps(data),
                "tags": tags,
                "user_id": user_id,
            },
        )
        row = result.fetchone()

        if not row:
            return {
                "success": False,
                "error": "Failed to create timeline entry",
            }

        return {
            "success": True,
            "entry_id": row[0],
            "timestamp": row[1].isoformat() if row[1] else None,
            "title": row[2],
        }
    except Exception as e:
        logger.error(f"Add timeline entry failed: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
        }


async def _tool_update_timeline_entry(
    db: AsyncSession,
    investigation_id: UUID,
    params: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Update an existing timeline entry in the database.

    Parameters
    ----------
    db : AsyncSession
        Asynchronous SQLAlchemy session used to execute the update query.
    investigation_id : UUID
        Identifier of the investigation to which the timeline entry belongs.
    params : dict[str, Any]
        Mapping containing the fields to be updated. Must include `entry_id` and may contain any of the following keys:

        - `timestamp` (str or datetime): ISO-8601 string or datetime object representing the new timestamp.
        - `entry_type` (str): New type of the entry.
        - `title` (str): Updated title.
        - `description` (str): Updated description.
        - `tags` (list[str] | str): Updated tags.
        - `data` (dict): Arbitrary JSON-serialisable data; will be stored as `jsonb`.

    Returns
    -------
    dict
        A result dictionary with the following keys:

        - `success` (bool): Indicates whether the update succeeded.
        - If `success` is `True`, includes:
            - `entry_id`: The identifier of the updated entry.
            - `title`: The title of the updated entry.
        - If `success` is `False`, includes:
            - `error` (str): Description of the failure reason (e.g., missing `entry_id`, no fields to update, entry not found, or exception message).

    Notes
    -----
    - The function dynamically builds the SQL UPDATE statement based on the supplied keys in *params*.
    - If `timestamp` is provided as a string, it is parsed from ISO-8601 format, accepting a trailing `Z` for UTC.
    - The `data` field is JSON-encoded before being cast to `jsonb` in PostgreSQL.
    - Any exception raised during query execution is caught, logged, and reported via the `error` key.
    """
    # Validate entry_id
    if "entry_id" not in params:
        return {
            "success": False,
            "error": "Missing required field: entry_id",
        }

    entry_id = params["entry_id"]

    # Build update query dynamically
    update_parts = []
    query_params: Dict[str, Any] = {"investigation_id": str(investigation_id), "entry_id": entry_id}

    if "timestamp" in params:
        update_parts.append("timestamp = :timestamp")
        # Convert ISO string to datetime object
        timestamp = params["timestamp"]
        if isinstance(timestamp, str):
            timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        query_params["timestamp"] = timestamp

    if "entry_type" in params:
        update_parts.append("entry_type = :entry_type")
        query_params["entry_type"] = params["entry_type"]

    if "title" in params:
        update_parts.append("title = :title")
        query_params["title"] = params["title"]

    if "description" in params:
        update_parts.append("description = :description")
        query_params["description"] = params["description"]

    if "tags" in params:
        update_parts.append("tags = :tags")
        query_params["tags"] = params["tags"]

    if "data" in params:
        update_parts.append("data = CAST(:data AS jsonb)")
        query_params["data"] = json.dumps(params["data"])

    if not update_parts:
        return {
            "success": False,
            "error": "No fields to update",
        }

    query = text(
        f"""
        UPDATE timeline_entries
        SET {', '.join(update_parts)}, updated_at = NOW()
        WHERE investigation_id = :investigation_id AND entry_id = :entry_id
        RETURNING entry_id, title
    """
    )

    try:
        result = await db.execute(query, query_params)
        row = result.fetchone()

        if not row:
            return {
                "success": False,
                "error": f"Timeline entry {entry_id} not found",
            }

        return {
            "success": True,
            "entry_id": row[0],
            "title": row[1],
        }
    except Exception as e:
        logger.error(f"Update timeline entry failed: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
        }


async def _tool_delete_timeline_entry(
    db: AsyncSession,
    investigation_id: UUID,
    params: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Delete a timeline entry from the investigation database.

    Parameters
    ----------
    db: AsyncSession
        The asynchronous SQLAlchemy session used to execute queries.
    investigation_id: UUID
        Identifier of the investigation containing the timeline entry.
    params: dict[str, Any]
        Dictionary of parameters required for deletion. Must include:
        - `entry_id` (str or UUID): The identifier of the timeline entry to delete.

    Returns
    -------
    dict[str, Any]
        A result dictionary with the following keys:

        * `success` (bool) - `True` if the entry was deleted successfully; otherwise `False`.
        * `entry_id` (optional, str) - The ID of the deleted entry when successful.
        * `title` (optional, str) - The title of the deleted entry when successful.
        * `error` (optional, str) - Human-readable error message when `success` is `False`.

    Raises
    ------
    None. All errors are caught and reported in the returned dictionary.
    """
    # Validate entry_id
    if "entry_id" not in params:
        return {
            "success": False,
            "error": "Missing required field: entry_id",
        }

    entry_id = params["entry_id"]

    # Get entry title before deleting
    check_query = text(
        """
        SELECT title FROM timeline_entries
        WHERE investigation_id = :investigation_id AND entry_id = :entry_id
    """
    )

    try:
        check_result = await db.execute(
            check_query, {"investigation_id": str(investigation_id), "entry_id": entry_id}
        )
        check_row = check_result.fetchone()

        if not check_row:
            return {
                "success": False,
                "error": f"Timeline entry {entry_id} not found",
            }

        title = check_row[0]

        # Delete entry
        query = text(
            """
            DELETE FROM timeline_entries
            WHERE investigation_id = :investigation_id AND entry_id = :entry_id
            RETURNING entry_id
        """
        )

        result = await db.execute(
            query, {"investigation_id": str(investigation_id), "entry_id": entry_id}
        )
        row = result.fetchone()

        if not row:
            return {
                "success": False,
                "error": f"Failed to delete timeline entry {entry_id}",
            }

        return {
            "success": True,
            "entry_id": entry_id,
            "title": title,
        }
    except Exception as e:
        logger.error(f"Delete timeline entry failed: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
        }


async def _tool_get_timeline_stats(
    db: AsyncSession,
    investigation_id: UUID,
) -> Dict[str, Any]:
    """
    Fetches aggregated statistics for visible timeline entries belonging to a specific investigation.

    :param db: Asynchronous SQLAlchemy session used to execute raw SQL queries.
    :type db: AsyncSession
    :param investigation_id: Unique identifier of the investigation whose timeline is being analysed.
    :type investigation_id: UUID

    :return: A dictionary containing:
        - `success` (bool): `True` if all queries executed without error, otherwise `False`.
        - `total_entries` (int): Count of visible entries for the investigation.
        - `entries_by_type` (dict[str, int]): Mapping of each entry type to its occurrence count.
        - `date_range` (dict): Contains ISO-8601 strings for the earliest and latest timestamps under keys `earliest` and `latest`; values may be `None` if no entries exist.
        - `tags` (list[str]): List of unique tags extracted from all visible entries.
        - `error` (str, optional): Error message when `success` is `False`.

    :raises: No exception is propagated; any error is caught, logged, and reported in the returned dictionary.
    """
    try:
        # Total entries
        total_query = text(
            """
            SELECT COUNT(*) FROM timeline_entries
            WHERE investigation_id = :investigation_id AND is_visible = true
        """
        )
        total_result = await db.execute(total_query, {"investigation_id": str(investigation_id)})
        total_entries = total_result.scalar() or 0

        # Entries by type
        type_query = text(
            """
            SELECT entry_type, COUNT(*) as count
            FROM timeline_entries
            WHERE investigation_id = :investigation_id AND is_visible = true
            GROUP BY entry_type
        """
        )
        type_result = await db.execute(type_query, {"investigation_id": str(investigation_id)})
        entries_by_type = {row[0]: row[1] for row in type_result.fetchall()}

        # Date range
        range_query = text(
            """
            SELECT MIN(timestamp) as earliest, MAX(timestamp) as latest
            FROM timeline_entries
            WHERE investigation_id = :investigation_id AND is_visible = true
        """
        )
        range_result = await db.execute(range_query, {"investigation_id": str(investigation_id)})
        range_row = range_result.fetchone()

        # Unique tags
        tags_query = text(
            """
            SELECT DISTINCT unnest(tags) as tag
            FROM timeline_entries
            WHERE investigation_id = :investigation_id AND is_visible = true
        """
        )
        tags_result = await db.execute(tags_query, {"investigation_id": str(investigation_id)})
        tags = [row[0] for row in tags_result.fetchall()]

        return {
            "success": True,
            "total_entries": total_entries,
            "entries_by_type": entries_by_type,
            "date_range": {
                "earliest": range_row[0].isoformat() if range_row and range_row[0] else None,
                "latest": range_row[1].isoformat() if range_row and range_row[1] else None,
            },
            "tags": tags,
        }
    except Exception as e:
        logger.error(f"Get timeline stats failed: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
        }


__all__ = ["handle_timeline_query"]
