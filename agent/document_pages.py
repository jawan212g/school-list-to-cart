"""Operational page selection helpers with no model or business logic."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TypeVar


PageValue = TypeVar("PageValue")


def selected_page_indexes(
    page_count: int,
    page_numbers: tuple[int, ...],
) -> tuple[int, ...]:
    """Convert parent-facing one-based page numbers to document indexes."""

    return (
        tuple(page_number - 1 for page_number in page_numbers)
        if page_numbers
        else tuple(range(page_count))
    )


def selected_numbered_pages(
    pages: Sequence[PageValue],
    page_numbers: tuple[int, ...],
) -> tuple[tuple[int, PageValue], ...]:
    """Pair valid requested page numbers with rendered page values."""

    active_numbers = (
        page_numbers
        or tuple(range(1, len(pages) + 1))
    )
    return tuple(
        (page_number, pages[page_number - 1])
        for page_number in active_numbers
        if 1 <= page_number <= len(pages)
    )
