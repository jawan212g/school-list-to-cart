"""Tests for cross-child and classroom quantity aggregation."""

from agent.aggregate import aggregate_requirements
from agent.normalize import normalize_requirements
from agent.schema import Requirement


def test_classroom_student_count_multiplies_per_student_requirement() -> None:
    """FR-05: four students needing three folders produce twelve units."""

    normalized = normalize_requirements(
        [
            Requirement(
                req_id="folders",
                child_id="classroom",
                raw_text="3 folders per student",
                canonical_item="folders",
                quantity=3,
                extraction_confidence=1.0,
            )
        ]
    )
    needs = aggregate_requirements(
        normalized.budget_requirements,
        student_counts_by_child={"classroom": 4},
    )

    assert len(needs) == 1
    assert needs[0].quantity == 12
    assert needs[0].allocated_to == {"classroom": 12}
