"""Frozen end-to-end cart regressions for the two Maple Street lists."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace
from itertools import combinations
from types import SimpleNamespace
from typing import Any

import app
from agent.budget_plans import evaluate_budget_actions
from agent.gate import GateContext, evaluate_gate
from agent.match import MatchResult, NeedMatches, SuitabilityJudge
from agent.optimize import OptimizationConfig
from agent.pipeline import (
    PipelineResult,
    PipelineSession,
    _optimize_and_consolidate,
    replan_after_catalog_change,
    run_pipeline_from_confirmed_extractions,
)
from agent.schema import ExtractionEnvelope
from data.loader import Offer, load_catalog, load_stores


def _run_maple(
    extractions: Mapping[str, ExtractionEnvelope],
    judge: SuitabilityJudge,
    *,
    budget_cents: int,
    shopping_mode: str = "budget",
    fulfillment: str = "either",
    allowed_stores: frozenset[str] | None = None,
    max_stores: int | None = None,
    offers: Sequence[Offer] | None = None,
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
        offers=tuple(load_catalog() if offers is None else offers),
        suitability_judge=judge,
    )


def _gate_context(
    result: PipelineResult,
    *,
    matches: MatchResult | None = None,
) -> GateContext:
    """Build the exact gate input used by the confirmed-input pipeline."""

    return GateContext(
        optimization=result.proposed_cart,
        matches=result.matches if matches is None else matches,
        normalization=result.normalization,
        extractions=result.extractions,
        offers=tuple(load_catalog()),
        stores=tuple(load_stores()),
        tax_basis_points=result.session.tax_basis_points,
        unit_needs=result.purchase_needs,
        optimization_config=OptimizationConfig(
            shopping_mode=result.session.shopping_mode,
            budget_cents=result.session.budget_total,
            allowed_store_ids=result.session.allowed_stores,
            max_stores=result.session.max_stores,
            store_radius_miles=result.session.store_radius_miles,
            fulfillment_preference=result.session.fulfillment_pref,
            tax_basis_points=result.session.tax_basis_points,
        ),
    )


def _selected_candidate_variant(
    result: PipelineResult,
    *,
    substitution_reasons: tuple[str, ...] | None = None,
    confidence_review: bool = False,
) -> MatchResult:
    """Vary one real selected Maple candidate without inventing object shapes."""

    selected_line = result.proposed_cart.plan.lines[0]
    varied_needs: list[NeedMatches] = []
    changed = False
    for need_matches in result.matches.needs:
        if (
            need_matches.unit_need.source_requirement_ids
            != selected_line.source_requirement_ids
        ):
            varied_needs.append(need_matches)
            continue
        selected = next(
            candidate
            for candidate in need_matches.candidates
            if candidate.offer.sku == selected_line.sku
        )
        if confidence_review:
            blocked = replace(
                selected,
                match_confidence=0.65,
                suitability_reason=(
                    "Near-variant evidence is deliberately ambiguous."
                ),
            )
            varied_needs.append(
                replace(
                    need_matches,
                    candidates=(),
                    review_blocked_candidates=(blocked,),
                )
            )
        else:
            assert substitution_reasons is not None
            varied = replace(
                selected,
                substitution_type="major",
                substitution_reasons=substitution_reasons,
                attribute_status=(
                    "different"
                    if any(
                        reason.startswith("attribute_change:")
                        for reason in substitution_reasons
                    )
                    else selected.attribute_status
                ),
                requires_approval=True,
            )
            varied_needs.append(
                replace(
                    need_matches,
                    candidates=tuple(
                        varied
                        if candidate.offer.sku == selected_line.sku
                        else candidate
                        for candidate in need_matches.candidates
                    ),
                )
            )
        changed = True
    assert changed is True
    return MatchResult(needs=tuple(varied_needs))


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

    # BR-13 now combines the spelling-only duplicates before package choice,
    # saving 20 item cents plus one tax cent from the prior frozen plan.
    assert result.proposed_cart.plan.item_subtotal == 10_264
    assert result.proposed_cart.plan.tax == 719
    assert result.proposed_cart.plan.fulfillment_fees == 0
    assert result.proposed_cart.landed_cost == 10_983
    assert len(result.approval_batch.interrupts) == 0


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

    assert result.proposed_cart.landed_cost == 10_983
    assert len(result.approval_batch.interrupts) == 1
    assert result.budget_analysis is not None
    assert result.budget_analysis.recommended_plan is not None
    assert (
        result.budget_analysis.recommended_plan.resulting_landed_cost_cents
        == 6_924
    )


def test_frozen_gate_condition_1_budget_exceeded_still_fires(
    frozen_maple_fixture: Any,
) -> None:
    """FR-26: one cent below the exact frozen total triggers the budget gate."""

    result = _run_maple(
        frozen_maple_fixture.extractions,
        frozen_maple_fixture.judge,
        budget_cents=10_982,
    )

    assert tuple(
        interrupt.kind for interrupt in result.approval_batch.interrupts
    ) == ("budget_exceeded",)


def test_frozen_gate_condition_2_major_substitution_still_fires(
    frozen_maple_fixture: Any,
) -> None:
    """FR-26: a stockout can expose one genuine size substitution."""

    result = _run_maple(
        frozen_maple_fixture.extractions,
        frozen_maple_fixture.judge,
        budget_cents=15_000,
    )
    changed_sku = "VD-GLU-VB-006"
    changed_offers = tuple(
        replace(offer, stock_qty=0)
        if offer.sku == changed_sku
        else offer
        for offer in load_catalog()
    )
    transition = replan_after_catalog_change(
        result,
        changed_offers,
        tuple(load_stores()),
        change_kind="stockout",
        changed_sku=changed_sku,
    )

    assert tuple(
        interrupt.kind
        for interrupt in transition.result.approval_batch.interrupts
    ) == ("major_substitution",)
    assert transition.result.approval_batch.interrupts[0].sku == (
        "CL-GLU-CC-012"
    )


def test_frozen_gate_condition_3_accepts_brand_break_evidence(
    frozen_maple_fixture: Any,
) -> None:
    """FR-26: the gate branch fires, although matching filters this evidence."""

    result = _run_maple(
        frozen_maple_fixture.extractions,
        frozen_maple_fixture.judge,
        budget_cents=15_000,
    )
    matches = _selected_candidate_variant(
        result,
        substitution_reasons=("brand_lock_break",),
    )

    assert tuple(
        interrupt.kind
        for interrupt in evaluate_gate(
            _gate_context(result, matches=matches)
        ).interrupts
    ) == ("brand_lock_break",)


def test_frozen_gate_condition_4_attribute_choice_still_fires(
    frozen_maple_fixture: Any,
) -> None:
    """FR-26: preference-sensitive color evidence gets its own interrupt."""

    result = _run_maple(
        frozen_maple_fixture.extractions,
        frozen_maple_fixture.judge,
        budget_cents=15_000,
    )
    matches = _selected_candidate_variant(
        result,
        substitution_reasons=("attribute_change:color",),
    )

    assert tuple(
        interrupt.kind
        for interrupt in evaluate_gate(
            _gate_context(result, matches=matches)
        ).interrupts
    ) == ("attribute_choice",)


def test_frozen_gate_condition_5_low_confidence_still_fires(
    frozen_maple_fixture: Any,
) -> None:
    """FR-26/BR-11: a sub-floor near variant cannot reach the cart silently."""

    result = _run_maple(
        frozen_maple_fixture.extractions,
        frozen_maple_fixture.judge,
        budget_cents=15_000,
    )
    matches = _selected_candidate_variant(
        result,
        confidence_review=True,
    )

    assert tuple(
        interrupt.kind
        for interrupt in evaluate_gate(
            _gate_context(result, matches=matches)
        ).interrupts
    ) == ("low_confidence",)


def test_frozen_required_unavailable_is_visible_without_an_interrupt(
    frozen_maple_fixture: Any,
) -> None:
    """E-12: pickup-only leaves headphones visibly unavailable."""

    result = _run_maple(
        frozen_maple_fixture.extractions,
        frozen_maple_fixture.judge,
        budget_cents=15_000,
        fulfillment="pickup",
    )

    assert result.approval_batch.interrupts == ()
    assert "headphones" in result.proposed_cart.gap_items
    assert result.proposed_cart.is_complete is False


def test_frozen_retired_br08_remains_inactive(
    frozen_maple_fixture: Any,
) -> None:
    """Retired BR-08 does not revive for the expensive headphones line."""

    result = _run_maple(
        frozen_maple_fixture.extractions,
        frozen_maple_fixture.judge,
        budget_cents=15_000,
    )
    offers_by_sku = {offer.sku: offer for offer in load_catalog()}
    headphones = offers_by_sku["CL-HDP-CLS-001"]

    assert headphones.is_returnable is False
    assert headphones.pack_price > 1_500
    assert result.approval_batch.interrupts == ()


def test_frozen_brand_lock_stockout_stays_unavailable_not_a_decision(
    frozen_maple_fixture: Any,
) -> None:
    """Document the current FR-17/FR-26 reachability gap without fixing it."""

    changed_offers = tuple(
        replace(offer, stock_qty=0)
        if offer.brand.casefold() == "ticonderoga"
        else offer
        for offer in load_catalog()
    )
    result = _run_maple(
        frozen_maple_fixture.extractions,
        frozen_maple_fixture.judge,
        budget_cents=15_000,
        offers=changed_offers,
    )

    assert result.approval_batch.interrupts == ()
    assert "pencils (Ticonderoga)" in result.proposed_cart.gap_items
    assert all(
        interrupt.kind != "brand_lock_break"
        for interrupt in result.approval_batch.interrupts
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

    # With ruling spellings consolidated, Supply Cloud covers one more complete
    # need than the other primary stores; single-stop therefore chooses it and
    # closes the remaining glue-stick gap with the minimum second trip.
    assert result.proposed_cart.landed_cost == 15_099
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
    assert all(result.landed_cost == 14_511 for result in results)
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
    selected_optional_ids = tuple(
        item.requirement_id for item in result.addon_proposal.items[:1]
    )
    state = {
        "stockout_skus": frozenset(),
        "price_overrides": {},
        "approval_outcomes": outcomes,
        "budget_action_ids": action_ids,
        "approval_generation": 1,
        "replan_omitted_source_ids": frozenset(),
        "replan_forced_skus": {},
        "addon_evaluation": SimpleNamespace(
            selected_requirement_ids=selected_optional_ids
        ),
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
    assert (
        st.session_state["replan_selected_addon_ids"]
        == selected_optional_ids
    )
    assert "went out of stock" in st.session_state["catalog_change_notice"]
