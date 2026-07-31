"""Tests for cross-child and classroom quantity aggregation."""

import pytest

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
                supply_scope="individual",
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


def test_classroom_shared_item_is_not_multiplied() -> None:
    """BR-33: one shared tissue box remains one classroom requirement."""

    normalized = normalize_requirements(
        [
            Requirement(
                req_id="tissues",
                child_id="classroom",
                raw_text="1 shared box of tissues",
                canonical_item="tissues",
                quantity=1,
                unit_type="box",
                supply_scope="shared",
                extraction_confidence=1.0,
            )
        ]
    )

    needs = aggregate_requirements(
        normalized.budget_requirements,
        student_counts_by_child={"classroom": 20},
    )

    assert needs[0].quantity == 1
    assert needs[0].allocated_to == {"classroom": 1}


def test_classroom_unspecified_scope_cannot_reach_quantity_math() -> None:
    """BR-33: a classroom requires the parent's quantity interpretation."""

    with pytest.raises(
        ValueError,
        match="Choose whether classroom quantities apply",
    ):
        aggregate_requirements(
            (
                Requirement(
                    req_id="folders",
                    child_id="classroom",
                    raw_text="2 folders",
                    canonical_item="folders",
                    quantity=2,
                    supply_scope="unspecified",
                    extraction_confidence=1.0,
                ),
            ),
            student_counts_by_child={"classroom": 20},
        )
