"""
Domain layer for the Personal Budget App.
Contains pure, deterministic business logic independent of frameworks, databases, and network protocols.
"""

from .dates import determine_month_range

__all__ = ["determine_month_range"]
