"""Operational timing helpers that never participate in cart calculations."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from time import perf_counter


@dataclass(frozen=True)
class ElapsedTimer:
    """Measure wall-clock duration for logs without affecting business logic."""

    started_at: float = field(default_factory=perf_counter)

    def elapsed_seconds(self) -> float:
        """Return elapsed wall-clock seconds."""

        return perf_counter() - self.started_at


def log_operation_success(
    logger: logging.Logger,
    operation: str,
    timer: ElapsedTimer,
    *,
    limit_seconds: float | None = None,
    detail: str = "",
) -> None:
    """Record a successful operational duration."""

    limit_text = (
        ""
        if limit_seconds is None
        else f" against a {limit_seconds:.1f}-second request limit"
    )
    detail_text = "" if not detail else f" ({detail})"
    logger.info(
        "%s completed in %.3f seconds%s%s",
        operation,
        timer.elapsed_seconds(),
        limit_text,
        detail_text,
    )


def log_operation_failure(
    logger: logging.Logger,
    operation: str,
    timer: ElapsedTimer,
    *,
    limit_seconds: float | None = None,
    detail: str = "",
) -> None:
    """Record a failed operational duration with the active traceback."""

    limit_text = (
        ""
        if limit_seconds is None
        else f" against a {limit_seconds:.1f}-second request limit"
    )
    detail_text = "" if not detail else f" ({detail})"
    logger.exception(
        "%s failed after %.3f seconds%s%s",
        operation,
        timer.elapsed_seconds(),
        limit_text,
        detail_text,
    )
