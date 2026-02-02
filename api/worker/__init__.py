# Register all tools on worker startup
from .tools import tool_wrappers  # noqa: F401 - import for side effects (tool registration)

# Only import main if not running in CLI harness mode
import os
if not os.environ.get('CLI_HARNESS_MODE'):
    from .main import main
    __all__ = ["main"]
else:
    __all__ = []
