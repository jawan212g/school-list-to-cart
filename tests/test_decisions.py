"""Tests for the auditable Section 8 decision log."""

from datetime import datetime, timezone

from agent.decisions import DecisionLog


def test_decision_log_records_agent_request_and_parent_response() -> None:
    """FR-30: approval responses retain actor, rationale, and timestamp."""

    timestamp = datetime(2026, 7, 25, 12, 0, tzinfo=timezone.utc)
    log = DecisionLog("session", clock=lambda: timestamp)

    request = log.record(
        "approval_request",
        "The backpack is non-returnable; approve only if it is wanted.",
        actor="agent",
        affected_lines=("line-1",),
    )
    response = log.record_approval_response(
        "Approved because the requested model is exact.",
        affected_lines=("line-1",),
    )

    assert request.decision_id == "session-decision-1"
    assert request.timestamp == timestamp
    assert request.type == "approval_request"
    assert request.actor == "agent"
    assert request.affected_lines == ("line-1",)
    assert response.decision_id == "session-decision-2"
    assert response.timestamp == timestamp
    assert response.type == "approval_response"
    assert response.actor == "parent"
    assert response.rationale == (
        "Approved because the requested model is exact."
    )
