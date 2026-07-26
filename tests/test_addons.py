"""Model-free coverage for BR-05 add-on proposals."""

from agent.addons import evaluate_addon_selection
from agent.match import StructuredSuitabilityJudge
from agent.optimize import OptimizationConfig
from agent.pipeline import ListInput, PipelineSession, run_pipeline
from agent.schema import ExtractionEnvelope, Requirement
from data.loader import Offer, Store


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
    sku: str,
    category: str,
    price: int,
) -> Offer:
    return Offer(
        sku=sku,
        store_id="S",
        brand="Generic",
        title=sku,
        category=category,
        pack_size=1,
        unit_price=price,
        pack_price=price,
        stock_qty=10,
        is_returnable=True,
        attributes={},
    )


def _extractor(
    source: str,
    *,
    child_id: str,
    mime_type: str | None,
    client: object,
) -> ExtractionEnvelope:
    del source, mime_type, client
    return ExtractionEnvelope(
        requirements=(
            Requirement(
                req_id="required",
                child_id=child_id,
                raw_text="1 backpack",
                canonical_item="backpacks",
                quantity=1,
                extraction_confidence=1.0,
            ),
            Requirement(
                req_id="donation",
                child_id=child_id,
                raw_text="Donation pencils",
                canonical_item="pencils",
                quantity=1,
                is_required=False,
                requirement_type="donation",
                extraction_confidence=1.0,
            ),
        )
    )


def test_br05_prices_addons_below_ninety_percent_without_mutating_base() -> None:
    """BR-05: $80 base against $100 exposes a separate $90 proposal."""

    result = run_pipeline(
        PipelineSession(
            session_id="session",
            children=("child",),
            budget_total=10_000,
            fulfillment_pref="pickup",
            tax_basis_points=0,
        ),
        [ListInput(child_id="child", source="list")],
        stores=[_store()],
        offers=[
            _offer("BACKPACK", "backpacks", 8_000),
            _offer("PENCILS", "pencils", 1_000),
        ],
        suitability_judge=StructuredSuitabilityJudge(),
        extractor=_extractor,
    )

    assert result.proposed_cart.landed_cost == 8_000
    assert result.addon_proposal.eligible is True
    assert tuple(
        item.requirement_id for item in result.addon_proposal.items
    ) == ("child:donation",)
    assert result.addon_proposal.resulting_landed_cost_cents == 9_000
    assert result.addon_proposal.incremental_landed_cost_cents == 1_000
    assert result.proposed_cart.plan.lines[0].sku == "BACKPACK"


def test_br05_hides_addons_when_base_is_above_ninety_percent() -> None:
    """BR-05: $91 base against $100 has insufficient add-on headroom."""

    result = run_pipeline(
        PipelineSession(
            session_id="session",
            children=("child",),
            budget_total=10_000,
            fulfillment_pref="pickup",
            tax_basis_points=0,
        ),
        [ListInput(child_id="child", source="list")],
        stores=[_store()],
        offers=[
            _offer("BACKPACK", "backpacks", 9_100),
            _offer("PENCILS", "pencils", 100),
        ],
        suitability_judge=StructuredSuitabilityJudge(),
        extractor=_extractor,
    )

    assert result.proposed_cart.landed_cost == 9_100
    assert result.addon_proposal.eligible is False
    assert result.addon_proposal.optimization is None


def test_br05_hides_donations_while_a_required_item_is_unmet() -> None:
    """BR-04/BR-05: optional giving waits until required coverage is complete."""

    result = run_pipeline(
        PipelineSession(
            session_id="required-gap",
            children=("child",),
            budget_total=10_000,
            fulfillment_pref="pickup",
            tax_basis_points=0,
        ),
        [ListInput(child_id="child", source="list")],
        stores=[_store()],
        offers=[_offer("PENCILS", "pencils", 100)],
        suitability_judge=StructuredSuitabilityJudge(),
        extractor=_extractor,
    )

    assert result.proposed_cart.is_complete is False
    assert result.proposed_cart.gap_items == ("backpacks",)
    assert result.addon_proposal.eligible is False
    assert result.addon_proposal.reason == (
        "Optional items stay hidden until every required item is covered."
    )


def test_individual_donations_reoptimize_exactly_and_stay_separate() -> None:
    """BR-05: each classroom donation has an exact threshold-aware result."""

    store = Store(
        store_id="ONLINE",
        name="Online",
        distance_miles=50.0,
        pickup_fee=0,
        pickup_minimum=0,
        delivery_fee=700,
        delivery_minimum=5_000,
        tax_applies=False,
        pickup_available=False,
    )

    def extractor(
        source: str,
        *,
        child_id: str,
        mime_type: str | None,
        client: object,
    ) -> ExtractionEnvelope:
        del source, mime_type, client
        required = (
            Requirement(
                req_id="required",
                child_id=child_id,
                raw_text="1 backpack",
                canonical_item="backpacks",
                quantity=1,
                extraction_confidence=1.0,
            ),
        ) if child_id == "grade2" else ()
        return ExtractionEnvelope(
            requirements=required
            + (
                Requirement(
                    req_id="donation",
                    child_id=child_id,
                    raw_text="Donation pencils",
                    canonical_item="pencils",
                    quantity=1,
                    is_required=False,
                    requirement_type="donation",
                    extraction_confidence=1.0,
                ),
            )
        )

    offers = (
        Offer(
            sku="BACKPACK",
            store_id="ONLINE",
            brand="Generic",
            title="Backpack",
            category="backpacks",
            pack_size=1,
            unit_price=4_900,
            pack_price=4_900,
            stock_qty=10,
            is_returnable=True,
            attributes={},
        ),
        Offer(
            sku="PENCILS",
            store_id="ONLINE",
            brand="Generic",
            title="Pencils",
            category="pencils",
            pack_size=1,
            unit_price=1_000,
            pack_price=1_000,
            stock_qty=10,
            is_returnable=True,
            attributes={},
        ),
    )
    result = run_pipeline(
        PipelineSession(
            session_id="individual-donations",
            children=("grade2", "grade5"),
            budget_total=10_000,
            fulfillment_pref="delivery",
            tax_basis_points=0,
        ),
        (
            ListInput(child_id="grade2", source="list"),
            ListInput(child_id="grade5", source="list"),
        ),
        stores=(store,),
        offers=offers,
        suitability_judge=StructuredSuitabilityJudge(),
        extractor=extractor,
    )

    proposal = result.addon_proposal
    config = OptimizationConfig(
        shopping_mode="budget",
        budget_cents=10_000,
        fulfillment_preference="delivery",
        tax_basis_points=0,
    )
    assert result.proposed_cart.landed_cost == 5_600
    assert proposal.eligible is True
    assert len(proposal.optional_needs) == 2
    assert tuple(
        tuple(need.allocated_to)
        for need in proposal.optional_needs
    ) == (("grade2",), ("grade5",))

    one = evaluate_addon_selection(
        proposal,
        ("grade2:donation",),
        result.proposed_cart,
        result.purchase_needs,
        result.matches,
        offers,
        (store,),
        config,
    )
    all_items = evaluate_addon_selection(
        proposal,
        ("grade2:donation", "grade5:donation"),
        result.proposed_cart,
        result.purchase_needs,
        result.matches,
        offers,
        (store,),
        config,
    )

    assert one.resulting_landed_cost_cents == 5_900
    assert one.incremental_landed_cost_cents == 300
    assert all_items.resulting_landed_cost_cents == 6_900
    assert all_items.incremental_landed_cost_cents == 1_300
    assert (
        all_items.resulting_landed_cost_cents
        == all_items.optimization.landed_cost
    )
    pencil_lines = tuple(
        line
        for line in all_items.optimization.plan.lines
        if line.canonical_item == "pencils"
    )
    assert len(pencil_lines) == 2
    assert tuple(tuple(line.allocated_to) for line in pencil_lines) == (
        ("grade2",),
        ("grade5",),
    )
