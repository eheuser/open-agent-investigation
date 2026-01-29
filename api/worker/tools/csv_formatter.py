import csv
import io
import json
from typing import List, Dict, Any


def events_to_csv(events: List[Dict[str, Any]]) -> str:
    """
    Convert a list of heterogeneous event dictionaries into a CSV-formatted string.

    The function inspects all dictionaries in *events* to determine the complete set of keys that appear across the collection. It then creates a CSV with one column per unique key, ordering the columns alphabetically while ensuring that an `event_id` column (if present) appears first. Nested structures such as dictionaries or lists are serialized to compact JSON strings; all other values are converted to plain strings. Missing values are represented by empty fields.

    Args:
        events: A list of dictionaries, each representing a single event. The dictionaries may contain different keys and may include nested `dict` or `list` objects.

    Returns:
        A string containing the CSV representation of the supplied events, including a header row. An empty string is returned when *events* is empty.
    """
    if not events:
        return ""

    # Collect all unique keys across all events
    all_keys = set()
    for event in events:
        all_keys.update(event.keys())

    # Sort keys for consistent column order (event_id first, then alphabetical)
    sorted_keys = sorted(all_keys)
    if "event_id" in sorted_keys:
        sorted_keys.remove("event_id")
        sorted_keys.insert(0, "event_id")

    # Build CSV
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=sorted_keys, extrasaction="ignore")

    # Write header
    writer.writeheader()

    # Write rows
    for event in events:
        # Flatten nested dicts/lists to strings for CSV compatibility
        flattened_event = {}
        for key in sorted_keys:
            value = event.get(key)
            if value is None:
                flattened_event[key] = ""
            elif isinstance(value, (dict, list)):
                # Convert complex types to compact JSON strings
                flattened_event[key] = json.dumps(value, separators=(",", ":"))
            else:
                flattened_event[key] = str(value)

        writer.writerow(flattened_event)

    return output.getvalue()


__all__ = ["events_to_csv"]
