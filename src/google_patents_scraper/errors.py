"""Errors raised by the scraper."""

from __future__ import annotations


class GooglePatentsError(Exception):
    """Base class for scraper errors."""


class NotFoundError(GooglePatentsError):
    """Google Patents has no document with that publication number (HTTP 404)."""


class ParseError(GooglePatentsError):
    """A response was not the search JSON or patent page the scraper expected."""


class QueryError(GooglePatentsError, ValueError):
    """A search option could not be turned into a Google Patents query."""
