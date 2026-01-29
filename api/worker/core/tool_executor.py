from typing import Any, Dict, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from ..models import ToolResult
from .tool_registry import tool_registry

from app.utils.log_setup import get_logger

logger = get_logger(__name__)


class ToolExecutor:
    """Executes tools with validation."""

    def __init__(
        self,
        db: AsyncSession,
        investigation_id: str,
        stats: Dict[str, Any],
        user_id: Optional[int] = None,
    ):
        """
        Initializes the tool manager with required context and optional user information.

        Parameters
        ----------
        db : AsyncSession
            Asynchronous SQLAlchemy session used for database interactions.
        investigation_id : str
            Identifier of the investigation under which tools are executed; included in logging and statistics.
        stats : dict[str, Any]
            Mutable dictionary that will be populated with usage statistics such as execution counts,
            durations, and error occurrences for each registered tool.
        user_id : int, optional
            Identifier of the user invoking the tool actions. If provided, it is attached to log entries
            and may be used for permission checks; defaults to `None` when no user context is available.
        """
        self.db = db
        self.investigation_id = investigation_id
        self.stats = stats
        self.user_id = user_id

    def _validate_and_clean_arguments(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        spec: Any,
    ) -> Dict[str, Any]:
        """
        Validate and clean tool arguments, removing unknown parameters.
        
        Args:
            tool_name: Name of the tool
            arguments: Raw arguments from LLM
            spec: Tool specification
            
        Returns:
            Cleaned arguments dictionary with only valid parameters
        """
        # Get valid parameters from spec
        params_schema = spec.parameters.get("properties", {})
        valid_params = set(params_schema.keys())
        
        # Check for invalid arguments
        provided_params = set(arguments.keys())
        invalid_params = provided_params - valid_params
        
        if invalid_params:
            logger.warning(
                f"Tool {tool_name} received invalid parameters: {invalid_params}. "
                f"Valid parameters are: {valid_params}. Stripping invalid parameters."
            )
        
        # Return cleaned arguments
        cleaned = {k: v for k, v in arguments.items() if k in valid_params}
        
        # Log what was removed
        if invalid_params:
            removed = {k: arguments[k] for k in invalid_params}
            logger.info(f"Removed invalid parameters from {tool_name}: {removed}")
        
        return cleaned

    async def execute(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
    ) -> ToolResult:
        """
        Execute a registered tool asynchronously and return a standardized :class:`ToolResult`.

        Args:
            tool_name: The identifier of the tool to invoke. Must correspond to an entry in the global `tool_registry`.
            arguments: A dictionary of pre-validated parameters required by the selected tool. Additional context such as `user_id` may be injected automatically for specific tools (e.g., `hybrid_search`).

        Returns:
            ToolResult: An object encapsulating the execution outcome.
                * If `status` is `"ok"`, the `result` attribute contains the successful payload returned by the tool implementation.
                * If `status` is `"error"`, the `error_msg` attribute provides a human-readable description of what went wrong (e.g., unknown tool, tool-level error, or unexpected exception).

        Side Effects:
            * Updates `self.stats["tools_called"]` to record how many times each tool has been invoked.
            * Emits log messages at INFO level for successful dispatches and at WARNING/ERROR levels for failures.
        """
        # Get tool spec
        spec = tool_registry.get(tool_name)
        if not spec:
            logger.error(f"Unknown tool: {tool_name}")
            return ToolResult(status="error", error_msg=f"Unknown tool: {tool_name}")

        # Validate and clean arguments
        arguments = self._validate_and_clean_arguments(tool_name, arguments, spec)

        # Track tool usage
        self.stats.setdefault("tools_called", {})
        self.stats["tools_called"][tool_name] = self.stats["tools_called"].get(tool_name, 0) + 1

        try:
            # Execute tool implementation
            logger.info(f"Executing tool: {tool_name} with args: {arguments}")

            # Add user_id to arguments if tool accepts it and we have it
            if self.user_id is not None and tool_name == "hybrid_search":
                arguments = {**arguments, "user_id": self.user_id}

            result = await spec.impl(
                db=self.db, investigation_id=self.investigation_id, stats=self.stats, **arguments
            )

            # Check if result indicates error
            if isinstance(result, dict) and "error" in result:
                logger.warning(f"Tool {tool_name} returned error: {result['error']}")
                return ToolResult(status="error", error_msg=result["error"])

            return ToolResult(status="ok", result=result)

        except Exception as e:
            logger.error(f"Tool {tool_name} failed: {e}", exc_info=True)
            return ToolResult(status="error", error_msg=str(e))
