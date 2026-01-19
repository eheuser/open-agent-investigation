from typing import Any, Awaitable, Callable, Dict, List, Optional
from pydantic import BaseModel, ConfigDict

from app.utils.log_setup import get_logger

logger = get_logger(__name__)


class ToolSpec(BaseModel):
    """Tool specification."""

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid")

    name: str
    description: str
    parameters: Dict[str, Any]  # JSON Schema
    impl: Callable[..., Awaitable[Dict[str, Any]]]


class ToolRegistry:
    """Registry of available tools."""

    def __init__(self):
        """
        Initializes a new thread-safe tool registry.

        Creates an internal dictionary `_tools` that maps tool names (strings) to their corresponding :class:`ToolSpec` instances. The dictionary starts empty, ready for tools to be registered via the public API.
        """
        self._tools: Dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        """
        Register a new tool specification in the registry.

        Args:
            spec: The :class:`ToolSpec` instance containing the tool's name, description,
                  JSON schema for its parameters, and async implementation.

        The method adds `spec` to the internal mapping keyed by its `name`.
        If a tool with the same name already exists, a warning is logged and the
        existing entry is overwritten. A debug message is emitted after successful
        registration.
        """
        if spec.name in self._tools:
            logger.warning(f"Tool {spec.name} already registered, overwriting")
        self._tools[spec.name] = spec
        logger.debug(f"Registered tool: {spec.name}")

    def get(self, name: str) -> Optional[ToolSpec]:
        """
        Retrieve a registered tool specification by its name.

        Args:
            name: The unique identifier of the tool to look up.

        Returns:
            The :class:`ToolSpec` instance associated with `name` if it exists,
            otherwise `None`.
        """
        return self._tools.get(name)

    def get_all(self) -> List[ToolSpec]:
        """
        Retrieve a list of all tool specifications currently stored in the registry.

        Returns:
            List[ToolSpec]: A shallow copy of the internal collection of registered tools, preserving insertion order. Each element is a ToolSpec instance representing a single tool's metadata and implementation.
        """
        return list(self._tools.values())

    def get_openai_format(self) -> List[Dict[str, Any]]:
        """
        Retrieve all registered tool specifications formatted for OpenAI function calling.

        Returns:
            List[Dict[str, Any]]: A list where each element is a dictionary representing a tool in the required OpenAI schema:
                {
                    "type": "function",
                    "function": {
                        "name": <tool name>,
                        "description": <tool description>,
                        "parameters": <JSON schema of parameters>
                    }
                }
        """
        return [
            {
                "type": "function",
                "function": {
                    "name": spec.name,
                    "description": spec.description,
                    "parameters": spec.parameters,
                },
            }
            for spec in self._tools.values()
        ]


# Global singleton
tool_registry = ToolRegistry()
