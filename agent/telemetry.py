"""Operational timing helpers that never participate in cart calculations."""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field
from time import perf_counter


@dataclass(frozen=True)
class ElapsedTimer:
    """Measure wall-clock duration for logs without affecting business logic."""

    started_at: float = field(default_factory=perf_counter)

    def elapsed_seconds(self) -> float:
        """Return elapsed wall-clock seconds."""

        return perf_counter() - self.started_at


def _process_peak_rss_bytes() -> int | None:
    """Return the process high-water RSS using the host operating system."""

    try:
        import resource
    except ImportError:
        return None
    peak_rss = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    return peak_rss if sys.platform == "darwin" else peak_rss * 1024


def log_process_peak_rss(
    logger: logging.Logger,
    stage: str,
) -> None:
    """Log peak resident memory without participating in plan calculations."""

    peak_rss_bytes = _process_peak_rss_bytes()
    if peak_rss_bytes is None:
        logger.warning(
            "PLAN_BUILD_MEMORY stage=%s peak_rss=unavailable platform=%s",
            stage,
            sys.platform,
        )
        return
    logger.warning(
        "PLAN_BUILD_MEMORY stage=%s peak_rss_mib=%.1f peak_rss_bytes=%d",
        stage,
        peak_rss_bytes / (1024 * 1024),
        peak_rss_bytes,
    )


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
