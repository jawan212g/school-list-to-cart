"""Exact, model-free tests for every active FR-26 approval condition."""

from collections.abc import Sequence
from dataclasses import replace

from agent.aggregate import UnitNeed
from agent.decisions import DecisionLog
from agent.gate import GateContext, evaluate_gate
from agent.match import (
    CandidateMatch,
    MatchResult,
    NeedMatches,
    SuitabilityCase,
    SuitabilityDecision,
    match_offers,
)
from agent.normalize import NormalizationResult
from agent.optimize import (
    CartLine,
    CartPlan,
    OptimizationResult,
    StoreOrder,
)
from data.loader import Offer, Store
from agent.schema import ExtractionEnvelope


class AmbiguousJudge:
    """Return a fixed ambiguous score without a model call."""

    def judge(
        self,
        cases: Sequence[SuitabilityCase],
    ) -> tuple[SuitabilityDecision, ...]:
        return tuple(
            SuitabilityDecision(
                need_key=case.need_key,
                sku=case.offer.sku,
                suitable=True,
                confidence=0.65,
                reason="The requirement wording is deliberately ambiguous.",
            )
            for case in cases
        )


def _store() -> Store:
    return Store(
        store_id="S",
        name="Store",
        distance_miles=1.0,
        pickup_fee=0,
        pickup_minimum=0,
        delivery_fee=0,
        delivery_minimum=0,
        tax_applies=False,
    )


def _offer(
    *,
    price: int = 500,
    returnable: bool = True,
) -> Offer:
    return Offer(
        sku="SKU",
        store_id="S",
        brand="Exact Brand",
        title="Exact Brand folder",
        category="folders",
        pack_size=1,
        unit_price=price,
        pack_price=price,
        stock_qty=1,
        is_returnable=returnable,
        attributes={"color": "blue"},
    )


def _need(
    *,
    attributes: dict[str, object] | None = None,
) -> UnitNeed:
    return UnitNeed(
        canonical_item="folders",
        quantity=1,
        brand_lock="Exact Brand",
        unit_type="each",
        exclusions=(),
        is_required=True,
        attributes=attributes or {},
        allocated_to={"child": 1},
        source_requirement_ids=("req-1",),
    )


def _candidate(
    need: UnitNeed,
    offer: Offer,
    *,
    substitution_type: str = "none",
    reasons: tuple[str, ...] = (),
    confidence: float = 0.95,
) -> CandidateMatch:
    return CandidateMatch(
        need_key="req-1",
        offer=offer,
        match_confidence=confidence,
        suitability_reason="Fixed test match.",
        substitution_type=substitution_type,  # type: ignore[arg-type]
        substitution_reasons=reasons,
        attribute_status=(
            "different"
            if any(reason.startswith("attribute_change:") for reason in reasons)
            else "exact"
        ),
        line_notes=(),
        approval_reasons=(),
        requires_approval=substitution_type == "major",
    )


def _optimization(
    offer: Offer,
    *,
    line_cost: int | None = None,
    within_budget: bool | None = True,
    shortfall: int = 0,
    gap_items: tuple[str, ...] = (),
    include_line: bool = True,
) -> OptimizationResult:
    cost = offer.pack_price if line_cost is None else line_cost
    lines = (
        (
            CartLine(
                line_id="line-1",
                canonical_item=offer.category,
                sku=offer.sku,
                store_id=offer.store_id,
                packs_purchased=1,
                units_purchased=1,
                units_needed=1,
                overage_units=0,
                allocated_to={"child": 1},
                line_cost=cost,
                substitution_type="none",
                approval_status="not_required",
                source_requirement_ids=("req-1",),
                match_confidence=0.95,
            ),
        )
        if include_line
        else ()
    )
    orders = (
        (
            StoreOrder(
                store_id="S",
                fulfillment_method="pickup",
                lines=lines,
                item_subtotal=cost,
                tax=0,
                fulfillment_fee=0,
                landed_cost=cost,
            ),
        )
        if include_line
        else ()
    )
    plan = CartPlan(
        lines=lines,
        store_orders=orders,
        item_subtotal=cost if include_line else 0,
        tax=0,
        fulfillment_fees=0,
        landed_cost=cost if include_line else 0,
        comparison_cost=cost if include_line else 0,
    )
    return OptimizationResult(
        plan=plan,
        gap_items=gap_items,
        minimum_second_trip=None,
        landed_cost=plan.landed_cost,
        comparison_cost=plan.comparison_cost,
        budget_cents=(
            plan.landed_cost - shortfall
            if within_budget is False
            else 10_000
        ),
        within_budget=within_budget,
        shortfall_cents=shortfall,
    )


def _context(
    need: UnitNeed,
    offer: Offer,
    candidate: CandidateMatch | None,
    optimization: OptimizationResult,
    *,
    blocked: tuple[CandidateMatch, ...] = (),
) -> GateContext:
    return GateContext(
        optimization=optimization,
        matches=MatchResult(
            needs=(
                NeedMatches(
                    unit_need=need,
                    candidates=(
                        () if candidate is None else (candidate,)
                    ),
                    review_blocked_candidates=blocked,
                ),
            )
        ),
        normalization=NormalizationResult(requirements=()),
        extractions={},
        offers=(offer,),
        stores=(_store(),),
        tax_basis_points=0,
    )


def _assert_one(
    context: GateContext,
    expected_kind: str,
    expected_cost_deltas: tuple[int, int],
) -> None:
    log = DecisionLog("test-session")
    batch = evaluate_gate(context, decision_log=log)

    assert len(batch.interrupts) == 1
    assert batch.interrupts[0].kind == expected_kind
    assert batch.interrupts[0].recommendation
    assert len(batch.interrupts[0].alternatives) == 2
    assert tuple(
        alternative.cost_delta_cents
        for alternative in batch.interrupts[0].alternatives
    ) == expected_cost_deltas
    assert [decision.type for decision in log.entries] == [
        "approval_request"
    ]


def test_condition_1_budget_exceeded_fires_once() -> None:
    offer = _offer()
    need = _need()
    _assert_one(
        _context(
            need,
            offer,
            _candidate(need, offer),
            _optimization(
                offer,
                within_budget=False,
                shortfall=125,
            ),
        ),
        "budget_exceeded",
        (0, -500),
    )


def test_no_budget_never_fires_the_budget_interrupt() -> None:
    """FR-26: an absent ceiling cannot create a budget breach."""

    offer = _offer()
    need = _need()
    batch = evaluate_gate(
        _context(
            need,
            offer,
            _candidate(need, offer),
            _optimization(offer, within_budget=None),
        )
    )

    assert all(
        interrupt.kind != "budget_exceeded"
        for interrupt in batch.interrupts
    )


def test_no_budget_does_not_restore_retired_returnability_interrupt() -> None:
    """Retired BR-08 stays inactive even without a budget ceiling."""

    offer = _offer(price=1_600, returnable=False)
    need = _need()
    batch = evaluate_gate(
        _context(
            need,
            offer,
            _candidate(need, offer),
            _optimization(offer, within_budget=None),
        )
    )

    assert tuple(
        interrupt.kind for interrupt in batch.interrupts
    ) == ()


def test_condition_2_major_substitution_fires_once() -> None:
    offer = _offer()
    need = _need()
    _assert_one(
        _context(
            need,
            offer,
            _candidate(
                need,
                offer,
                substitution_type="major",
                reasons=("attribute_change:size",),
            ),
            _optimization(offer),
        ),
        "major_substitution",
        (0, -500),
    )


def test_condition_3_brand_lock_break_fires_once() -> None:
    offer = _offer()
    need = _need()
    _assert_one(
        _context(
            need,
            offer,
            _candidate(
                need,
                offer,
                substitution_type="major",
                reasons=("brand_lock_break",),
            ),
            _optimization(offer),
        ),
        "brand_lock_break",
        (0, -500),
    )


def test_condition_4_preference_attribute_choice_fires_once() -> None:
    offer = _offer()
    need = _need(attributes={"acceptable_colors": ("red",)})
    matches = match_offers([need], [offer], [_store()])
    assert matches.needs[0].candidates[0].substitution_reasons == (
        "attribute_change:acceptable_colors",
    )
    _assert_one(
        GateContext(
            optimization=_optimization(offer),
            matches=matches,
            normalization=NormalizationResult(requirements=()),
            extractions={},
            offers=(offer,),
            stores=(_store(),),
            tax_basis_points=0,
        ),
        "attribute_choice",
        (0, -500),
    )


def test_equivalent_tip_and_eraser_style_create_no_interrupt() -> None:
    """BR-13/FR-19: equivalent source/catalog words are exact matches."""

    cases = (
        (
            replace(
                _need(),
                canonical_item="permanent_markers",
                attributes={"tip_style": "fine tip"},
            ),
            replace(
                _offer(),
                category="permanent_markers",
                attributes={"tip": "fine"},
            ),
        ),
        (
            replace(
                _need(),
                canonical_item="erasers",
                attributes={"style": "pencil top"},
            ),
            replace(
                _offer(),
                category="erasers",
                attributes={"style": "cap"},
            ),
        ),
    )

    for need, offer in cases:
        matches = match_offers([need], [offer], [_store()])
        batch = evaluate_gate(
            GateContext(
                optimization=_optimization(offer),
                matches=matches,
                normalization=NormalizationResult(requirements=()),
                extractions={},
                offers=(offer,),
                stores=(_store(),),
                tax_basis_points=0,
            )
        )
        assert matches.needs[0].candidates[0].attribute_status == "exact"
        assert batch.interrupts == ()


def test_genuine_tip_and_style_changes_keep_their_gate_conditions() -> None:
    """FR-19/26: safe aliases do not suppress real attribute differences."""

    cases = (
        (
            replace(
                _need(),
                canonical_item="permanent_markers",
                attributes={"tip_style": "fine"},
            ),
            replace(
                _offer(),
                category="permanent_markers",
                attributes={"tip": "chisel"},
            ),
            "major_substitution",
        ),
        (
            replace(
                _need(),
                canonical_item="erasers",
                attributes={"style": "cap"},
            ),
            replace(
                _offer(),
                category="erasers",
                attributes={"style": "block"},
            ),
            "attribute_choice",
        ),
    )

    for need, offer, expected_kind in cases:
        matches = match_offers([need], [offer], [_store()])
        batch = evaluate_gate(
            GateContext(
                optimization=_optimization(offer),
                matches=matches,
                normalization=NormalizationResult(requirements=()),
                extractions={},
                offers=(offer,),
                stores=(_store(),),
                tax_basis_points=0,
            )
        )
        assert tuple(item.kind for item in batch.interrupts) == (
            expected_kind,
        )
def test_retired_br08_ignores_legacy_returnability_data() -> None:
    offer = _offer(price=1_501, returnable=False)
    need = _need()
    matches = match_offers([need], [offer], [_store()])
    candidate = matches.needs[0].candidates[0]

    assert candidate.substitution_type == "none"
    assert candidate.requires_approval is False
    assert evaluate_gate(
        GateContext(
            optimization=_optimization(offer),
            matches=matches,
            normalization=NormalizationResult(requirements=()),
            extractions={},
            offers=(offer,),
            stores=(_store(),),
            tax_basis_points=0,
        )
    ).interrupts == ()


def test_condition_5_ambiguous_sub_07_match_routes_to_review_once() -> None:
    offer = _offer()
    need = _need(
        attributes={"other_details": "ambiguous classroom item"}
    )


def test_low_confidence_extraction_stays_in_personalize_not_gate() -> None:
    """FR-12/FR-26: source-reading uncertainty is not re-asked at checkout."""

    offer = _offer()
    need = _need()
    context = _context(
        need,
        offer,
        _candidate(need, offer),
        _optimization(offer),
    )
    context = GateContext(
        optimization=context.optimization,
        matches=context.matches,
        normalization=context.normalization,
        extractions={
            "child": ExtractionEnvelope(
                requirements=(),
                manual_review_required=True,
                review_reasons=("The source line may be unclear.",),
            )
        },
        offers=context.offers,
        stores=context.stores,
        tax_basis_points=context.tax_basis_points,
    )

    assert evaluate_gate(context).interrupts == ()
    matches = match_offers(
        [need],
        [offer],
        [_store()],
        judge=AmbiguousJudge(),
    )

    assert matches.needs[0].candidates == ()
    assert matches.needs[0].review_blocked_candidates[0].match_confidence == 0.65
    _assert_one(
        GateContext(
            optimization=_optimization(
                offer,
                gap_items=(need.label,),
                include_line=False,
            ),
            matches=matches,
            normalization=NormalizationResult(requirements=()),
            extractions={},
            offers=(offer,),
        ),
        "low_confidence",
        (0, 0),
    )


def test_required_item_unavailable_stays_outside_the_decision_gate() -> None:
    offer = _offer()
    need = _need()
    batch = evaluate_gate(
        _context(
            need,
            offer,
            None,
            _optimization(
                offer,
                gap_items=(need.label,),
                include_line=False,
            ),
        )
    )

    assert batch.interrupts == ()


def test_clean_cart_has_zero_interrupts() -> None:
    offer = _offer()
    need = _need()
    batch = evaluate_gate(
        _context(
            need,
            offer,
            _candidate(need, offer),
            _optimization(offer),
        )
    )

    assert batch.interrupts == ()
    assert batch.raw_interrupt_count == 0


def test_more_than_six_interrupts_are_grouped_by_type() -> None:
    offer = _offer()
    needs = tuple(
        UnitNeed(
            canonical_item="folders",
            quantity=1,
            brand_lock=f"Exact Brand {index}",
            unit_type="each",
            exclusions=(),
            is_required=True,
            attributes={},
            allocated_to={f"child-{index}": 1},
            source_requirement_ids=(f"req-{index}",),
        )
        for index in range(7)
    )
    batch = evaluate_gate(
        GateContext(
            optimization=_optimization(
                offer,
                within_budget=False,
                shortfall=125,
                gap_items=tuple(need.label for need in needs),
            ),
            matches=MatchResult(
                needs=tuple(
                        NeedMatches(
                            unit_need=need,
                            candidates=(),
                            review_blocked_candidates=(
                                _candidate(need, offer, confidence=0.65),
                            ),
                        )
                    for need in needs
                )
            ),
            normalization=NormalizationResult(requirements=()),
            extractions={},
            offers=(offer,),
        )
    )

    assert batch.raw_interrupt_count == 8
    assert batch.grouped_by_type is True
    assert len(batch.interrupts) == 2
    assert [interrupt.kind for interrupt in batch.interrupts] == [
        "budget_exceeded",
        "low_confidence",
    ]
    assert batch.interrupts[0].cost_impact_cents == 125
    assert len(batch.interrupts[1].grouped_interrupts) == 7
    assert batch.interrupts[1].source_requirement_ids == tuple(
        f"req-{index}" for index in range(7)
    )
