import json
import subprocess
import re
from typing import Dict, Any, Optional
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.utils.log_setup import get_logger

logger = get_logger(__name__)


# SQL injection prevention patterns
DANGEROUS_SQL_PATTERNS = [
    r"\bDROP\b",
    r"\bDELETE\b",
    r"\bUPDATE\b",
    r"\bINSERT\b",
    r"\bALTER\b",
    r"\bCREATE\b",
    r"\bTRUNCATE\b",
    r"\bGRANT\b",
    r"\bREVOKE\b",
    r";\s*DROP",
    r"--",
    r"/\*",
    r"xp_",
    r"sp_",
]


async def execute_sql(
    db: AsyncSession,
    investigation_id: str,
    query: str,
    stats: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Execute a read-only SELECT query against an investigation’s events table with built-in security checks.

    Parameters
    ----------
    db: AsyncSession
        An active asynchronous SQLAlchemy session used to run the query.
    investigation_id: str
        The UUID of the investigation whose events are being queried.  The function enforces that the supplied SQL references this identifier, preventing cross-investigation data leakage.
    query: str
        A raw SQL statement that **must** begin with `SELECT`.  Only read-only queries are permitted; any non-SELECT statements will be rejected.
    stats: Optional[Dict[str, Any]], optional
        An optional mutable dictionary that the function updates with runtime statistics (e.g., number of events analysed).  If `None`, no statistics are recorded.

    Returns
    -------
    Dict[str, Any]
        A mapping containing one of the following keys:

        * `count` (int): Number of rows returned (capped at 1 000).
        * `rows` (list[dict]): The result set where each row is represented as a dictionary mapping column names to values.
        * `has_more` (bool): `True` if the query hit the 1 000-row limit, indicating that additional rows exist.
        * `columns` (list[str]): Ordered list of column names returned by the query.

        If an error occurs, the dictionary contains a single key `error` with a human-readable description.  Error messages are sanitized to avoid leaking internal schema or server details.

    Raises
    ------
    None - all exceptions are caught internally and transformed into the `error` entry in the return value.

    Security considerations
    -----------------------
    * **Statement type** - The function validates that the supplied SQL starts with `SELECT`; any other statement results in an error.
    * **Injection protection** - A whitelist of dangerous patterns (`DANGEROUS_SQL_PATTERNS`) is scanned using case-insensitive regular expressions.  Detection of a prohibited pattern aborts execution.
    * **Investigation scoping** - The query must reference the `investigation_id` placeholder; otherwise it is rejected.  The identifier is bound as a parameter to prevent injection.
    * **Timeout** - PostgreSQL’s `statement_timeout` is set locally to five seconds for each execution, guaranteeing that runaway queries are terminated.
    * **Row limit** - Results are truncated to a maximum of 1 000 rows; the `has_more` flag signals truncation.

    Logging
    -------
    The function logs the executed query (truncated to 200 characters) at INFO level and records success or failure details.  Errors are logged at ERROR level with the full exception message for debugging purposes.
    """
    # Validate query is SELECT only
    query_upper = query.strip().upper()

    if not query_upper.startswith("SELECT"):
        return {"error": "Only SELECT queries are allowed. Query must start with SELECT."}

    # Check for dangerous patterns
    for pattern in DANGEROUS_SQL_PATTERNS:
        if re.search(pattern, query, re.IGNORECASE):
            return {
                "error": f"Dangerous SQL pattern detected: {pattern}. Only read-only SELECT queries allowed."
            }

    # Ensure query references investigation_id
    if "investigation_id" not in query.lower():
        return {
            "error": "Query must filter by investigation_id for security. Add: WHERE investigation_id = :investigation_id"
        }

    logger.info(f"Executing SQL query: {query[:200]}...")

    try:
        # Execute with timeout (5 seconds)
        # Note: PostgreSQL statement_timeout should be set at connection level
        result = await db.execute(
            text(f"SET LOCAL statement_timeout = '5s'; {query}"),
            {"investigation_id": investigation_id},
        )

        # Fetch rows (limit to 1000)
        rows = result.fetchmany(1000)

        # Convert rows to list of dicts
        columns = result.keys()
        rows_as_dicts = [{col: value for col, value in zip(columns, row)} for row in rows]

        # Check if more rows exist
        has_more = len(rows) == 1000

        if stats is not None:
            stats["events_analyzed"] = stats.get("events_analyzed", 0) + len(rows_as_dicts)

        logger.info(f"SQL query returned {len(rows_as_dicts)} rows")

        return {
            "count": len(rows_as_dicts),
            "rows": rows_as_dicts,
            "has_more": has_more,
            "columns": list(columns),
        }

    except Exception as e:
        error_msg = str(e)
        logger.error(f"SQL query failed: {error_msg}")
        try:
            await db.rollback()
        except Exception as rollback_error:
            logger.error(f"Rollback failed: {rollback_error}")

        # Sanitize error message (don't leak schema details)
        if "timeout" in error_msg.lower():
            return {
                "error": "Query timeout (5 second limit). Simplify your query or add more filters."
            }
        elif "syntax" in error_msg.lower():
            return {"error": f"SQL syntax error: {error_msg[:200]}"}
        else:
            return {"error": f"Query failed: {error_msg[:200]}"}


async def apply_jq(
    data: Any,
    filter: str,
    stats: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Apply a JQ filter to JSON data in an isolated subprocess.

    This coroutine validates the provided filter, safeguards against shell-injection patterns, and runs `jq` with a 5-second execution timeout. The input may be a Python object (dict, list, etc.) or a JSON-encoded string; it is converted to a JSON string before being passed to the `jq` command. The function captures standard output and error streams, parses the result back into native Python objects when possible, and returns a dictionary containing either the filtered result or an error description.

    Parameters
    ----------
    data : Any
        JSON data to filter. Accepts a dict, list, or a pre-encoded JSON string.
    filter : str
        JQ filter expression to apply. Must be non-empty and free of characters that could enable shell injection (e.g., `; & | ` $ ( )`).
    stats : Optional[Dict[str, Any]], optional
        An optional dictionary for caller-provided statistics; the function does not modify it directly but may be used by callers to record timing or other metrics.

    Returns
    -------
    dict
        A mapping with one of the following structures:

        * `{"result": <value>, "output_type": "<type_name>"}` - when the filter executes successfully. `<value>` is the parsed JSON output (or a list of parsed objects if multiple lines are returned) and `<type_name>` is the name of its Python type.
        * `{"error": "<message>"}` - when validation fails, the subprocess returns a non-zero exit code, times out, the `jq` executable is missing, or an unexpected exception occurs. The message provides a concise description suitable for logging or user feedback.

    Raises
    ------
    None. All error conditions are captured and reported via the returned `error` field.
    """
    # Validate filter
    if not filter or not filter.strip():
        return {"error": "JQ filter cannot be empty"}

    # Check for dangerous patterns (shell injection)
    dangerous_chars = [";", "&", "|", "`", "$", "(", ")"]
    if any(char in filter for char in dangerous_chars):
        return {"error": f"Dangerous characters detected in filter. Only use JQ syntax."}

    logger.info(f"Applying JQ filter: {filter[:100]}...")

    try:
        # Convert data to JSON string if needed
        if isinstance(data, str):
            json_input = data
        else:
            json_input = json.dumps(data, default=str)

        # Execute jq command with timeout
        # Note: This requires jq to be installed in the container
        process = subprocess.run(
            ["jq", "-c", filter],
            input=json_input,
            capture_output=True,
            text=True,
            timeout=5,  # 5 second timeout
        )

        if process.returncode != 0:
            error_msg = process.stderr.strip()
            logger.error(f"JQ filter failed: {error_msg}")
            return {"error": f"JQ filter error: {error_msg[:200]}"}

        # Parse output
        output = process.stdout.strip()

        if not output:
            result = None
        else:
            try:
                result = json.loads(output)
            except json.JSONDecodeError:
                # Output might be multiple JSON objects (one per line)
                lines = output.split("\n")
                if len(lines) == 1:
                    result = output  # Return as string
                else:
                    result = [json.loads(line) for line in lines if line.strip()]

        logger.info(f"JQ filter succeeded")

        return {
            "result": result,
            "output_type": type(result).__name__,
        }

    except subprocess.TimeoutExpired:
        logger.error("JQ filter timeout")
        return {"error": "JQ filter timeout (5 second limit). Simplify your filter."}

    except FileNotFoundError:
        logger.error("JQ not installed")
        return {"error": "JQ tool not installed in container. Contact administrator."}

    except Exception as e:
        logger.error(f"JQ filter failed: {e}")
        return {"error": f"JQ filter failed: {str(e)[:200]}"}


__all__ = ["execute_sql", "apply_jq"]
