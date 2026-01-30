"""
Artifact parsers for Windows forensic artifacts.
"""
from .dispatcher import parse_artifact
from .utils import flatten_dict
from .base_parser import BaseParser
from .evtx_parser import EvtxParser
from .registry_parser import RegistryParser
from .prefetch_parser import PrefetchParser
from .lnk_parser import LnkParser
from .mft_parser import MftParser
from .jumplist_parser import JumplistParser
from .browser_history_parser import BrowserHistoryParser
from .windows_artifacts_parser import WindowsArtifactsParser

__all__ = [
    "parse_artifact",
    "flatten_dict",
    "BaseParser",
    "EvtxParser",
    "RegistryParser",
    "PrefetchParser",
    "LnkParser",
    "MftParser",
    "JumplistParser",
    "BrowserHistoryParser",
    "WindowsArtifactsParser",
]
