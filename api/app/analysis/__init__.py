"""
Analysis module for forensic artifact analysis.

This package provides modular analysis capabilities for Windows forensic artifacts.
Each analysis module is self-contained and configurable.
"""

from .autoruns import AutorunsAnalyzer, AutorunEntry

__all__ = ["AutorunsAnalyzer", "AutorunEntry"]
