"""Frozen end-to-end cart regressions for the two Maple Street lists."""

from __future__ import annotations

from collections.abc import Mapping
from itertools import combinations
from types import SimpleNamespace
from typing import Any

import app
from agent.budget_plans import evaluate_budget_actions
from agent.match import MatchResult, SuitabilityJudge
from agent.optimize import OptimizationConfig
from agent.pipeline import (
    PipelineResult,
    PipelineSession,
    _optimize_and_consolidate,
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
    frozen_maple_fixture: Any,
) -> None:
    """The durable fixture explains its one human-confirmed correction."""

    fixture = frozen_maple_fixture
    corrections = fixture.metadata["corrections"]
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
    frozen_maple_fixture: Any,
) -> None:
    """The frozen extraction and matching boundary gives one stable cart."""

    fixture = frozen_maple_fixture
    result = _run_maple(
        fixture.extractions,
        fixture.judge,
        budget_cents=15_000,
    )

    assert result.proposed_cart.plan.item_subtotal == 10_284
    assert result.proposed_cart.plan.tax == 720
    assert result.proposed_cart.plan.fulfillment_fees == 0
    assert result.proposed_cart.landed_cost == 11_004
    assert len(result.approval_batch.interrupts) == 2


def test_frozen_maple_85_dollar_recommended_plan_baseline(
    frozen_maple_fixture: Any,
) -> None:
    """The frozen over-budget cart produces one exact recommended plan."""

    fixture = frozen_maple_fixture
    result = _run_maple(
        fixture.extractions,
        fixture.judge,
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


def test_frozen_maple_single_stop_second_trip_is_not_unavailable(
    frozen_maple_fixture: Any,
) -> None:
    """FR-22: a completed second trip must not become an unavailable interrupt."""

    fixture = frozen_maple_fixture
    result = _run_maple(
        fixture.extractions,
        fixture.judge,
        budget_cents=15_000,
        shopping_mode="single_stop",
    )

    assert result.proposed_cart.landed_cost == 11_749
    assert result.proposed_cart.minimum_second_trip is not None
    assert result.proposed_cart.unfulfilled_gap_items == ()
    assert result.proposed_cart.is_complete is True
    assert all(
        interrupt.kind != "required_unavailable"
        for interrupt in result.approval_batch.interrupts
    )


def test_frozen_maple_all_custom_store_combinations_return_a_result(
    frozen_maple_fixture: Any,
) -> None:
    """FR-04: every discrete custom selection yields a plan or gap list."""

    fixture = frozen_maple_fixture
    baseline = _run_maple(
        fixture.extractions,
        fixture.judge,
        budget_cents=15_000,
    )
    stores = tuple(load_stores())
    offers = tuple(load_catalog())
    store_ids = tuple(store.store_id for store in stores)
    assert baseline.source_matches is not None

    # The full configuration domain is a routing guard, not a performance
    # benchmark. Use one production need and its real frozen candidate graph;
    # the full 14-case failure class is exercised below with every Maple need.
    smoke_matches = MatchResult(needs=(baseline.source_matches.needs[0],))
    smoke_needs = (baseline.unit_needs[0],)
    results = []
    for subset_size in range(1, len(store_ids) + 1):
        for allowed in combinations(store_ids, subset_size):
            for max_stores in range(1, len(store_ids) + 1):
                for fulfillment in ("either", "pickup", "delivery"):
                    result, _ = _optimize_and_consolidate(
                        smoke_needs,
                        smoke_matches,
                        offers,
                        stores,
                        OptimizationConfig(
                            shopping_mode="custom",
                            budget_cents=15_000,
                            allowed_store_ids=frozenset(allowed),
                            max_stores=max_stores,
                            store_radius_miles=10.0,
                            fulfillment_preference=fulfillment,
                            tax_basis_points=700,
                        ),
                    )
                    results.append(
                        (
                            frozenset(allowed),
                            max_stores,
                            fulfillment,
                            result,
                        )
                    )

    assert len(results) == 180


def test_frozen_maple_custom_one_store_supply_cloud_fallbacks_are_complete(
    frozen_maple_fixture: Any,
) -> None:
    """FR-04: all 14 formerly crashing full-cart choices use Supply Cloud."""

    fixture = frozen_maple_fixture
    baseline = _run_maple(
        fixture.extractions,
        fixture.judge,
        budget_cents=15_000,
    )
    stores = tuple(load_stores())
    offers = tuple(load_catalog())
    other_store_ids = tuple(
        store.store_id
        for store in stores
        if store.store_id != "SUPPLY_CLOUD"
    )
    results = []
    for extra_count in range(1, len(other_store_ids) + 1):
        for extras in combinations(other_store_ids, extra_count):
            for fulfillment in ("either", "delivery"):
                result, _ = _optimize_and_consolidate(
                    baseline.unit_needs,
                    baseline.source_matches,
                    offers,
                    stores,
                    OptimizationConfig(
                        shopping_mode="custom",
                        budget_cents=15_000,
                        allowed_store_ids=frozenset(
                            ("SUPPLY_CLOUD", *extras)
                        ),
                        max_stores=1,
                        store_radius_miles=10.0,
                        fulfillment_preference=fulfillment,
                        tax_basis_points=700,
                    ),
                )
                results.append(result)

    assert len(results) == 14
    assert all(result.is_complete for result in results)
    assert all(result.landed_cost == 15_089 for result in results)
    assert all(
        tuple(order.store_id for order in result.plan.store_orders)
        == ("SUPPLY_CLOUD",)
        for result in results
    )


def test_stockout_replans_the_current_budget_adjusted_maple_plan(
    frozen_maple_fixture: Any,
) -> None:
    """FR-32: a stockout acts on the displayed parent-adjusted cart."""

    fixture = frozen_maple_fixture
    result = _run_maple(
        fixture.extractions,
        fixture.judge,
        budget_cents=8_500,
    )
    assert result.budget_analysis is not None
    assert result.budget_analysis.recommended_plan is not None
    action_ids = result.budget_analysis.recommended_plan.action_ids
    offers = tuple(load_catalog())
    stores = tuple(load_stores())
    evaluation = evaluate_budget_actions(
        result.budget_analysis,
        action_ids,
        result.proposed_cart,
        result.matches,
        result.purchase_needs,
        offers,
        stores,
        OptimizationConfig(
            shopping_mode="budget",
            budget_cents=8_500,
            store_radius_miles=10.0,
            fulfillment_preference="either",
            tax_basis_points=700,
        ),
    )
    current = evaluation.optimization
    stocked_out_sku = "NM-TIS-HOM-003"
    assert stocked_out_sku not in {
        line.sku for line in result.proposed_cart.plan.lines
    }
    assert stocked_out_sku in {line.sku for line in current.plan.lines}
    presentations = app.build_approval_presentations(
        result,
        offers,
        stores,
        {"grade-2": "Grade 2", "grade-5": "Grade 5"},
    )
    outcomes = {
        presentation.interrupt.interrupt_id: next(
            option.alternative_id
            for option in presentation.options
            if option.is_recommended
        )
        for presentation in presentations
        if presentation.interrupt.kind != "budget_exceeded"
    }
    state = {
        "stockout_skus": frozenset(),
        "price_overrides": {},
        "approval_outcomes": outcomes,
        "budget_action_ids": action_ids,
        "approval_generation": 1,
        "replan_omitted_source_ids": frozenset(),
        "replan_forced_skus": {},
        "addon_evaluation": None,
    }
    st = SimpleNamespace(session_state=state)

    app._apply_stockout_replan(
        st,
        result,
        current,
        stocked_out_sku,
        offers,
        stores,
        {"grade-2": "Grade 2", "grade-5": "Grade 5"},
    )

    displayed = st.session_state["result"].proposed_cart
    assert stocked_out_sku not in {
        line.sku for plan in app._plans(displayed) for line in plan.lines
    }
    assert displayed.landed_cost != current.landed_cost
    stocked_out_action = next(
        action.action_id
        for action in result.budget_analysis.substitution_actions
        if action.replacement_sku == stocked_out_sku
    )
    assert st.session_state["budget_action_ids"] == tuple(
        action_id for action_id in action_ids if action_id != stocked_out_action
    )
    assert st.session_state["approval_outcomes"] == outcomes
    assert "went out of stock" in st.session_state["catalog_change_notice"]
