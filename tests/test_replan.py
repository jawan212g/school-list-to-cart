"""Deterministic coverage for FR-32/FR-33 and E-29/E-30."""

from dataclasses import replace
from types import SimpleNamespace

import app
import pytest
from agent.match import StructuredSuitabilityJudge
from agent.pipeline import (
    ListInput,
    PipelineResult,
    PipelineSession,
    detect_cart_staleness,
    replan_after_catalog_change,
    run_pipeline,
)
from agent.schema import ExtractionEnvelope, Requirement
from data.loader import Offer, Store


def _store() -> Store:
    return Store(
        store_id="S",
        name="Fixture Store",
        distance_miles=1.0,
        pickup_fee=0,
        pickup_minimum=0,
        delivery_fee=0,
        delivery_minimum=0,
        tax_applies=False,
    )


def _offer(
    sku: str,
    category: str,
    price: int,
    *,
    returnable: bool = True,
) -> Offer:
    return Offer(
        sku=sku,
        store_id="S",
        brand="Fixture",
        title=sku.replace("-", " ").title(),
        category=category,
        pack_size=1,
        unit_price=price,
        pack_price=price,
        stock_qty=10,
        is_returnable=returnable,
        attributes={},
    )


def _pipeline(
    requirements: tuple[Requirement, ...],
    offers: tuple[Offer, ...],
    *,
    budget: int,
) -> PipelineResult:
    def extractor(
        source: str,
        *,
        child_id: str,
        mime_type: str | None,
        client: object | None,
    ) -> ExtractionEnvelope:
        del source, mime_type, client
        return ExtractionEnvelope(
            requirements=tuple(
                requirement.model_copy(update={"child_id": child_id})
                for requirement in requirements
            )
        )

    return run_pipeline(
        PipelineSession(
            session_id="replan-session",
            children=("child",),
            budget_total=budget,
            fulfillment_pref="pickup",
            tax_basis_points=0,
        ),
        (ListInput(child_id="child", source="fixture"),),
        stores=(_store(),),
        offers=offers,
        suitability_judge=StructuredSuitabilityJudge(),
        extractor=extractor,
    )


def _requirement(req_id: str, category: str) -> Requirement:
    return Requirement(
        req_id=req_id,
        child_id="model-child",
        raw_text=f"1 {category}",
        canonical_item=category,
        quantity=1,
        extraction_confidence=1.0,
    )


def _interrupt_ids_by_kind(result: PipelineResult) -> dict[str, str]:
    return {
        child.kind: child.interrupt_id
        for interrupt in result.approval_batch.interrupts
        for child in (
            interrupt.grouped_interrupts
            if interrupt.grouped_interrupts
            else (interrupt,)
        )
    }


def test_e29_stockout_before_approval_replans_selected_requirement() -> None:
    """FR-32/FR-33: stockout replaces the line before any response exists."""

    pencil_a = _offer("PENCIL-A", "pencils", 100)
    pencil_b = _offer("PENCIL-B", "pencils", 150)
    prior = _pipeline(
        (_requirement("pencils", "pencils"),),
        (pencil_a, pencil_b),
        budget=1_000,
    )
    assert prior.proposed_cart.plan.lines[0].sku == "PENCIL-A"
    changed_offers = (replace(pencil_a, stock_qty=0), pencil_b)
    assert detect_cart_staleness(
        prior.proposed_cart,
        changed_offers,
    )[0].kind == "stock"

    transition = replan_after_catalog_change(
        prior,
        changed_offers,
        (_store(),),
        change_kind="stockout",
        changed_sku="PENCIL-A",
    )

    assert transition.result.proposed_cart.plan.lines[0].sku == "PENCIL-B"
    assert transition.result.proposed_cart.landed_cost == 150
    assert transition.preserved_approval_outcomes == {}
    assert transition.invalidated_approval_ids == ()
    assert any(
        "cached extraction and suitability judgments were retained"
        in decision.rationale
        for decision in transition.result.decisions
    )


def test_e29_stockout_after_approval_preserves_unaffected_response() -> None:
    """FR-32: an unrelated stockout keeps a still-valid parent approval."""

    pencil_a = _offer("PENCIL-A", "pencils", 100)
    pencil_b = _offer("PENCIL-B", "pencils", 150)
    headphones = _offer(
        "HEADPHONES",
        "headphones",
        1_800,
        returnable=False,
    )
    prior = _pipeline(
        (
            _requirement("pencils", "pencils"),
            _requirement("headphones", "headphones"),
        ),
        (pencil_a, pencil_b, headphones),
        budget=5_000,
    )
    non_returnable_id = _interrupt_ids_by_kind(prior)[
        "non_returnable_threshold"
    ]
    presentation = next(
        presentation
        for presentation in app.build_approval_presentations(
            prior,
            (pencil_a, pencil_b, headphones),
            (_store(),),
            {"child": "Grade 2"},
        )
        if presentation.interrupt.interrupt_id == non_returnable_id
    )
    approved_option = next(
        option
        for option in presentation.options
        if option.is_recommended
    )
    prior_outcomes = {
        non_returnable_id: approved_option.alternative_id
    }

    changed_offers = (
        replace(pencil_a, stock_qty=0),
        pencil_b,
        headphones,
    )
    transition = replan_after_catalog_change(
        prior,
        changed_offers,
        (_store(),),
        change_kind="stockout",
        changed_sku="PENCIL-A",
        approval_outcomes=prior_outcomes,
    )

    assert {
        line.sku for line in transition.result.proposed_cart.plan.lines
    } == {"PENCIL-B", "HEADPHONES"}
    assert transition.preserved_approval_outcomes == prior_outcomes
    assert transition.invalidated_approval_ids == ()
    assert transition.new_interrupt_ids == ()

    st = SimpleNamespace(session_state={"approval_generation": 1})
    app._store_replan_transition(
        st,
        transition,
        changed_offers,
        (_store(),),
        {"child": "Grade 2"},
        "Stock changed.",
    )
    assert st.session_state["approval_outcomes"] == prior_outcomes
    assert st.session_state["replan_preserved_approval_ids"] == frozenset(
        {non_returnable_id}
    )
    assert st.session_state["approved_optimization"] is None


def test_e30_price_rise_after_approval_reopens_budget_gate() -> None:
    """BR-12/E-30: a price rise creates a new budget decision."""

    headphones = _offer(
        "HEADPHONES",
        "headphones",
        1_600,
        returnable=False,
    )
    prior = _pipeline(
        (_requirement("headphones", "headphones"),),
        (headphones,),
        budget=2_000,
    )
    assert prior.proposed_cart.within_budget is True
    non_returnable_id = _interrupt_ids_by_kind(prior)[
        "non_returnable_threshold"
    ]
    prior_outcomes = {
        non_returnable_id: f"{non_returnable_id}-approve"
    }
    changed_headphones = replace(
        headphones,
        pack_price=2_200,
        unit_price=2_200,
    )
    stale = detect_cart_staleness(
        prior.proposed_cart,
        (changed_headphones,),
    )
    assert len(stale) == 1
    assert stale[0].kind == "price"
    assert stale[0].prior_line_cost_cents == 1_600
    assert stale[0].active_line_cost_cents == 2_200

    transition = replan_after_catalog_change(
        prior,
        (changed_headphones,),
        (_store(),),
        change_kind="price_change",
        changed_sku="HEADPHONES",
        approval_outcomes=prior_outcomes,
    )

    replanned = transition.result
    assert replanned.proposed_cart.landed_cost == 2_200
    assert replanned.proposed_cart.within_budget is False
    assert replanned.proposed_cart.shortfall_cents == 200
    assert _interrupt_ids_by_kind(replanned)["budget_exceeded"] in (
        transition.new_interrupt_ids
    )
    assert transition.preserved_approval_outcomes == prior_outcomes
    assert detect_cart_staleness(
        replanned.proposed_cart,
        (changed_headphones,),
    ) == ()
    assert any(
        decision.type == "approval_request"
        and "budget" in decision.rationale.casefold()
        for decision in replanned.decisions
    )


def test_price_change_injection_updates_the_active_pack_price(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """E-30: the app catalog overlay carries the entered integer-cent price."""

    headphones = _offer("HEADPHONES", "headphones", 1_600)
    monkeypatch.setattr(app, "load_catalog", lambda: [headphones])

    active = app._active_catalog_offers(
        frozenset(),
        {"HEADPHONES": 2_200},
    )

    assert active[0].pack_price == 2_200
    assert active[0].unit_price == 1_600
