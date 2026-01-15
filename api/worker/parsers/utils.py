from typing import Dict, Any, Optional


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


__all__ = ["flatten_dict"]
