"""
Artifact parsers for Windows forensic artifacts.
"""
from .dispatcher import parse_artifact
from .utils import flatten_dict

__all__ = ["parse_artifact", "flatten_dict"]
