"""Frozen end-to-end cart regressions for the two Maple Street lists."""

from __future__ import annotations

from collections.abc import Mapping

from agent.match import SuitabilityJudge
from agent.pipeline import (
    PipelineResult,
    PipelineSession,
    run_pipeline_from_confirmed_extractions,
)
from agent.schema import ExtractionEnvelope
from data.loader import load_catalog, load_stores


def _run_maple(
    extractions: Mapping[str, ExtractionEnvelope],
    judge: SuitabilityJudge,
    *,
    budget_cents: int,
    shopping_mode: str = "budget",
    fulfillment: str = "either",
    allowed_stores: frozenset[str] | None = None,
    max_stores: int | None = None,
) -> PipelineResult:
    """Run the same confirmed-input pipeline used after Personalize."""

    return run_pipeline_from_confirmed_extractions(
        PipelineSession(
            session_id=(
                f"frozen-maple-{shopping_mode}-{fulfillment}-"
                f"{budget_cents}"
            ),
            children=("grade-2", "grade-5"),
            budget_total=budget_cents,
            shopping_mode=shopping_mode,  # type: ignore[arg-type]
            store_radius_miles=10.0,
            allowed_stores=allowed_stores,
            fulfillment_pref=fulfillment,  # type: ignore[arg-type]
            tax_basis_points=700,
            max_stores=max_stores,
        ),
        extractions,
        stores=tuple(load_stores()),
        offers=tuple(load_catalog()),
        suitability_judge=judge,
    )


def test_frozen_maple_fixture_records_the_human_binding_correction(
    frozen_maple_fixture: object,
) -> None:
    """The durable fixture explains its one human-confirmed correction."""

    fixture = frozen_maple_fixture
    corrections = fixture.metadata["corrections"]  # type: ignore[attr-defined]
    assert corrections == [
        {
            "child_id": "grade-2",
            "req_id": "req-006",
            "field": "attributes.binding",
            "raw_value": "spiral",
            "confirmed_value": None,
            "reason": (
                "The source explicitly says NOT spiral bound; the exclusion "
                "remains on the requirement."
            ),
        }
    ]


def test_frozen_maple_150_dollar_baseline(
    frozen_maple_fixture: object,
) -> None:
    """The frozen extraction and matching boundary gives one stable cart."""

    fixture = frozen_maple_fixture
    result = _run_maple(
        fixture.extractions,  # type: ignore[attr-defined]
        fixture.judge,  # type: ignore[attr-defined]
        budget_cents=15_000,
    )

    assert result.proposed_cart.plan.item_subtotal == 10_284
    assert result.proposed_cart.plan.tax == 720
    assert result.proposed_cart.plan.fulfillment_fees == 0
    assert result.proposed_cart.landed_cost == 11_004
    assert len(result.approval_batch.interrupts) == 2


def test_frozen_maple_85_dollar_recommended_plan_baseline(
    frozen_maple_fixture: object,
) -> None:
    """The frozen over-budget cart produces one exact recommended plan."""

    fixture = frozen_maple_fixture
    result = _run_maple(
        fixture.extractions,  # type: ignore[attr-defined]
        fixture.judge,  # type: ignore[attr-defined]
        budget_cents=8_500,
    )

    assert result.proposed_cart.landed_cost == 11_004
    assert len(result.approval_batch.interrupts) == 3
    assert result.budget_analysis is not None
    assert result.budget_analysis.recommended_plan is not None
    assert (
        result.budget_analysis.recommended_plan.resulting_landed_cost_cents
        == 7_697
    )
