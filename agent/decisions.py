"""Append-only decision records for the auditable agent workflow."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal


DecisionType = Literal[
    "match",
    "substitution",
    "store_assignment",
    "budget_action",
    "approval_request",
    "approval_response",
]
DecisionActor = Literal["agent", "parent"]
Clock = Callable[[], datetime]


@dataclass(frozen=True)
class Decision:
    """One Section 8 decision with its rationale and accountable actor."""

    decision_id: str
    timestamp: datetime
    type: DecisionType
    rationale: str
    actor: DecisionActor
    affected_lines: tuple[str, ...]


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp for a decision record."""

    return datetime.now(timezone.utc)


class DecisionLog:
    """Append decisions in the order they occur during one session."""

    def __init__(
        self,
        session_id: str,
        *,
        clock: Clock = utc_now,
    ) -> None:
        if not session_id:
            raise ValueError("Decision logs require a session_id")
        self._session_id = session_id
        self._clock = clock
        self._entries: list[Decision] = []

    @property
    def entries(self) -> tuple[Decision, ...]:
        """Return an immutable view of the complete decision history."""

        return tuple(self._entries)

    def record(
        self,
        decision_type: DecisionType,
        rationale: str,
        *,
        actor: DecisionActor,
        affected_lines: Sequence[str] = (),
    ) -> Decision:
        """Append one plain-language Section 8 decision."""

        if not rationale.strip():
            raise ValueError("Decision rationale cannot be blank")
        timestamp = self._clock()
        if timestamp.tzinfo is None:
            raise ValueError("Decision timestamps must include a timezone")
        decision = Decision(
            decision_id=(
                f"{self._session_id}-decision-{len(self._entries) + 1}"
            ),
            timestamp=timestamp,
            type=decision_type,
            rationale=rationale.strip(),
            actor=actor,
            affected_lines=tuple(dict.fromkeys(affected_lines)),
        )
        self._entries.append(decision)
        return decision

    def record_approval_response(
        self,
        rationale: str,
        *,
        affected_lines: Sequence[str] = (),
    ) -> Decision:
        """Append a parent's approval response (FR-30)."""

        return self.record(
            "approval_response",
            rationale,
            actor="parent",
            affected_lines=affected_lines,
        )
