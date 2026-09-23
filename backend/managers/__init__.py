"""
Manager layer for the Personal Budget App.
Coordinates use-case workflows across ResourceAccess and domain Engines.
"""

from .budget_summary_manager import get_budget_summary

__all__ = ["get_budget_summary"]
