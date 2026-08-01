"""Tests for operational diagnostics that do not affect cart behavior."""

from __future__ import annotations

import logging

from agent import telemetry


def test_peak_rss_is_logged_at_warning_level(monkeypatch, caplog) -> None:
    """Plan diagnostics remain visible in Streamlit Community Cloud logs."""

    monkeypatch.setattr(
        telemetry,
        "_process_peak_rss_bytes",
        lambda: 512 * 1024 * 1024,
    )

    with caplog.at_level(logging.WARNING):
        telemetry.log_process_peak_rss(
            logging.getLogger("test.plan-memory"),
            "after_matching",
        )

    assert (
        "PLAN_BUILD_MEMORY stage=after_matching peak_rss_mib=512.0"
        in caplog.text
    )
