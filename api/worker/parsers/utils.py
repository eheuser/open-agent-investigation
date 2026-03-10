from typing import Dict, Any, Optional
import json

from app.utils.log_setup import get_logger

logger = get_logger(__name__)

def flatten_dict(
    data: Dict[str, Any],
    parent_key: str = "",
    separator: str = ".",
    promote_keys: Optional[set[str]] = None,
) -> Dict[str, Any]:
    """
    Flatten a nested dictionary into a single-level dictionary using dotted notation.

    The function walks through *data* recursively. For each key/value pair it builds a new
    key by concatenating the current *parent_key*, the separator and the child key.
    If a value is itself a dictionary, the function recurses; if the key appears in
    *promote_keys* its contents are merged into the parent level instead of being
    prefixed with the key name. Lists are kept unchanged (they are not expanded).

    Args:
        data: The dictionary to flatten.
        parent_key: Prefix for keys during recursion. It is an internal argument and
            should be left as the default empty string when calling the function.
        separator: String used to join nested keys. Defaults to `"."`.
        promote_keys: Optional set of keys whose associated dictionaries are promoted
            to the current level rather than being nested under their own key name.

    Returns:
        A new dictionary where all nested structures have been collapsed into keys
        separated by *separator*. Keys listed in *promote_keys* will not appear in the
        result; instead, their inner items are merged at the root (or current) level.

    Examples:
        >>> flatten_dict({"a": {"b": 1, "c": 2}})
        {'a.b': 1, 'a.c': 2}

        >>> flatten_dict({"a": {"b": 1}, "c": 2}, promote_keys={"a"})
        {'b': 1, 'c': 2}
    """
    if promote_keys is None:
        promote_keys = set()

    items = []

    for key, value in data.items():
        # Build the new key
        if parent_key:
            new_key = f"{parent_key}{separator}{key}"
        else:
            new_key = key

        # Check if this key should be promoted (contents moved to parent level)
        if key in promote_keys and isinstance(value, dict):
            # Recursively flatten the promoted dict without adding the key prefix
            items.extend(flatten_dict(value, parent_key, separator, promote_keys).items())
        elif isinstance(value, dict):
            # Recursively flatten nested dicts
            items.extend(flatten_dict(value, new_key, separator, promote_keys).items())
        elif isinstance(value, list):
            # For lists, convert to JSON-serializable format
            # Keep lists as-is rather than expanding them
            items.append((new_key, value))
        else:
            # Base case: add the key-value pair
            items.append((new_key, value))

    return dict(items)


def sanitize_for_jsonb(obj: Any) -> Any:
    """
    Recursively sanitize an object for PostgreSQL JSONB storage.
    
    PostgreSQL JSONB does not support:
    - Null bytes (\u0000) in strings
    - Invalid Unicode sequences
    - Certain control characters
    - Surrogate pairs (unpaired UTF-16 surrogates)
    
    This function:
    - Removes null bytes from strings
    - Handles invalid Unicode sequences
    - Removes problematic control characters
    - Converts non-serializable types to strings
    - Recursively processes dicts and lists
    
    Args:
        obj: The object to sanitize (can be dict, list, str, or primitive)
        
    Returns:
        A sanitized version of the object safe for JSONB storage
    """
    if isinstance(obj, dict):
        return {k: sanitize_for_jsonb(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [sanitize_for_jsonb(item) for item in obj]
    elif isinstance(obj, str):
        # Remove null bytes
        cleaned = obj.replace('\x00', '')
        
        # Encode to UTF-8 and decode with error handling to remove invalid sequences
        # This handles surrogate pairs and other invalid Unicode
        try:
            cleaned = cleaned.encode('utf-8', errors='ignore').decode('utf-8', errors='ignore')
        except (UnicodeDecodeError, UnicodeEncodeError):
            # If encoding/decoding fails, convert to safe representation
            cleaned = repr(obj)
        
        # Remove control characters except newline, carriage return, and tab
        cleaned = ''.join(char for char in cleaned if ord(char) >= 32 or char in '\n\r\t')
        
        return cleaned
    elif isinstance(obj, bytes):
        # Try to decode as UTF-8 first, fall back to hex representation
        try:
            decoded = obj.decode('utf-8', errors='ignore')
            # Recursively sanitize the decoded string
            return sanitize_for_jsonb(decoded)
        except Exception as e:
            logger.debug(f"sanitize_for_jsonb raised {e}")
            # If decoding fails, return hex representation
            return obj.hex()
    elif obj is None or isinstance(obj, (bool, int, float)):
        # Primitives are safe
        return obj
    else:
        # Convert unknown types to string and sanitize
        return sanitize_for_jsonb(str(obj))


def safe_json_dumps(obj: Any) -> str:
    """
    Safely serialize an object to JSON string for JSONB storage.
    
    This function combines sanitization with JSON serialization to ensure
    the resulting string can be stored in PostgreSQL JSONB columns.
    
    Args:
        obj: The object to serialize
        
    Returns:
        A JSON string safe for JSONB storage
    """
    sanitized = sanitize_for_jsonb(obj)
    return json.dumps(sanitized, ensure_ascii=False)


__all__ = ["flatten_dict", "sanitize_for_jsonb", "safe_json_dumps"]
