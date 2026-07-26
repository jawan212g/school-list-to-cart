"""Model-free coverage for BR-05 add-on proposals."""

from agent.match import StructuredSuitabilityJudge
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
