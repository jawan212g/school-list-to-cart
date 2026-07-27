"""Deterministic tests for the mandatory organized-list review boundary."""

import pytest

from agent.review import (
    confirmed_requirements,
    organize_extractions,
    reviewed_envelopes,
    unresolved_required_items,
)
from agent.schema import ExtractionEnvelope, Requirement


def _requirement(
    req_id: str,
    item: str,
    *,
    confidence: float = 1.0,
) -> Requirement:
    return Requirement(
        req_id=req_id,
        child_id="child-1",
        raw_text=f"2 {item}",
        canonical_item=item,
        quantity=2,
        extraction_confidence=confidence,
    )


def test_organize_extractions_sorts_and_preserves_source_text() -> None:
    extraction = ExtractionEnvelope(
        requirements=(
            _requirement("z", "tissues"),
            _requirement("a", "pencils", confidence=0.6),
        )
    )

    rows = organize_extractions({"child-1": extraction})

    assert [row.item_name for row in rows] == ["pencils", "tissues"]
    assert rows[0].source_text == "2 pencils"
    assert rows[0].issue_codes == ("low_confidence",)
    assert all(row.review_status == "pending" for row in rows)


def test_required_rows_must_be_confirmed_before_planning() -> None:
    rows = organize_extractions(
        {
            "child-1": ExtractionEnvelope(
                requirements=(_requirement("a", "pencils"),)
            )
        }
    )

    assert unresolved_required_items(rows) == rows
    with pytest.raises(ValueError, match="Required items remain unresolved"):
        confirmed_requirements(rows)
    assert len(
        confirmed_requirements(rows, allow_unresolved=True)
    ) == 1


def test_only_confirmed_active_rows_reach_cart_contract() -> None:
    rows = list(
        organize_extractions(
            {
                "child-1": ExtractionEnvelope(
                    requirements=(
                        _requirement("a", "pencils"),
                        _requirement("b", "tissues"),
                    )
                )
            }
        )
    )
    rows[0] = rows[0].model_copy(
        update={"review_status": "confirmed"}
    )
    rows[1] = rows[1].model_copy(
        update={
            "review_status": "confirmed",
            "already_owned": True,
        }
    )

    requirements = confirmed_requirements(rows)

    assert [item.canonical_item for item in requirements] == ["pencils"]


def test_reviewed_envelopes_preserve_document_metadata() -> None:
    original = {
        "child-1": ExtractionEnvelope(
            stated_grades=("2",),
            stated_teachers=("Ms. Rivera",),
            requirements=(_requirement("a", "pencils"),),
        )
    }
    rows = [
        row.model_copy(update={"review_status": "confirmed"})
        for row in organize_extractions(original)
    ]

    reviewed = reviewed_envelopes(original, rows)

    assert reviewed["child-1"].stated_grades == ("2",)
    assert reviewed["child-1"].stated_teachers == ("Ms. Rivera",)
    assert len(reviewed["child-1"].requirements) == 1
