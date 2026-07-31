"""Fixed-fixture tests for matching and rule-derived classifications."""

from collections.abc import Sequence

from agent.aggregate import UnitNeed
from agent.match import (
    SuitabilityCase,
    SuitabilityDecision,
    match_offers,
)
from agent.optimize import OptimizationConfig, optimize_cart
from data.loader import Offer, Store


class FixedJudge:
    """Return predetermined confidence without making any model calls."""

    def __init__(self, confidence: float, suitable: bool = True) -> None:
        self.confidence = confidence
        self.suitable = suitable

    def judge(
        self,
        cases: Sequence[SuitabilityCase],
    ) -> tuple[SuitabilityDecision, ...]:
        return tuple(
            SuitabilityDecision(
                need_key=case.need_key,
                sku=case.offer.sku,
                suitable=self.suitable,
                confidence=self.confidence,
                reason="Fixed test judgment.",
            )
            for case in cases
        )


def _need(
    category: str,
    *,
    req_id: str = "req-1",
    brand_lock: str | None = None,
    exclusions: tuple[str, ...] = (),
    attributes: dict[str, object] | None = None,
) -> UnitNeed:
    return UnitNeed(
        canonical_item=category,
        quantity=1,
        brand_lock=brand_lock,
        unit_type="each",
        exclusions=exclusions,
        is_required=True,
        attributes=attributes or {},
        allocated_to={"child": 1},
        source_requirement_ids=(req_id,),
    )


def _offer(
    sku: str,
    store_id: str,
    category: str,
    *,
    brand: str = "Generic",
    stock_qty: int = 1,
    is_returnable: bool = True,
    attributes: dict[str, object] | None = None,
) -> Offer:
    return Offer(
        sku=sku,
        store_id=store_id,
        brand=brand,
        title=sku.replace("-", " "),
        category=category,
        pack_size=1,
        unit_price=100,
        pack_price=100,
        stock_qty=stock_qty,
        is_returnable=is_returnable,
        attributes=attributes or {},
    )


def _store(store_id: str, distance: float) -> Store:
    return Store(
        store_id=store_id,
        name=store_id,
        distance_miles=distance,
        pickup_fee=0,
        pickup_minimum=0,
        delivery_fee=0,
        delivery_minimum=0,
        tax_applies=False,
    )


def test_fr17_fr20_filters_store_radius_brand_exclusions_and_stock() -> None:
    """FR-17/20: only the in-scope, stocked, allowed-brand offer survives."""

    need = _need(
        "pencils",
        brand_lock="Ticonderoga",
        exclusions=("no mechanical pencils",),
    )
    stores = [_store("NEAR", 1.0), _store("FAR", 9.0)]
    offers = [
        _offer("GOOD", "NEAR", "pencils", brand="Ticonderoga"),
        _offer("WRONG-BRAND", "NEAR", "pencils", brand="Generic"),
        _offer("OUT", "NEAR", "pencils", brand="Ticonderoga", stock_qty=0),
        _offer(
            "MECHANICAL-PENCILS",
            "NEAR",
            "pencils",
            brand="Ticonderoga",
        ),
        _offer("TOO-FAR", "FAR", "pencils", brand="Ticonderoga"),
    ]

    result = match_offers(
        [need],
        offers,
        stores,
        store_radius_miles=5.0,
        fulfillment_preference="pickup",
    )

    assert tuple(
        candidate.offer.sku for candidate in result.needs[0].candidates
    ) == ("GOOD",)


def test_delivery_only_store_is_not_filtered_by_pickup_radius() -> None:
    """FR-04/17: a distant shipper remains matchable for delivery."""

    need = _need("pencils")
    store = Store(
        store_id="SHIP",
        name="Distant online store",
        distance_miles=100.0,
        pickup_fee=0,
        pickup_minimum=0,
        delivery_fee=500,
        delivery_minimum=0,
        tax_applies=False,
        pickup_available=False,
    )
    offer = _offer("SHIP-PENCILS", "SHIP", "pencils")

    result = match_offers(
        [need],
        [offer],
        [store],
        store_radius_miles=1.0,
        fulfillment_preference="either",
    )

    assert tuple(
        candidate.offer.sku for candidate in result.needs[0].candidates
    ) == ("SHIP-PENCILS",)


def test_fr19_any_acceptable_color_is_an_exact_attribute_match() -> None:
    """FR-19: blue satisfies {black, blue} without attribute approval."""

    need = _need(
        "pens",
        attributes={"acceptable_colors": ("black", "blue")},
    )
    offer = _offer(
        "BLUE-PENS",
        "S",
        "pens",
        attributes={"ink_color": "blue"},
    )

    candidate = match_offers(
        [need],
        [offer],
        [_store("S", 1.0)],
    ).needs[0].candidates[0]

    assert candidate.substitution_type == "minor"
    assert candidate.requires_approval is False
    assert not any(
        reason.startswith("attribute_change:")
        for reason in candidate.substitution_reasons
    )


def test_fr19_color_outside_acceptable_set_is_major() -> None:
    """FR-19: red cannot replace an explicit black-or-blue requirement."""

    need = _need(
        "pens",
        attributes={"acceptable_colors": ("black", "blue")},
    )
    offer = _offer(
        "RED-PENS",
        "S",
        "pens",
        attributes={"ink_color": "red"},
    )

    candidate = match_offers(
        [need],
        [offer],
        [_store("S", 1.0)],
    ).needs[0].candidates[0]

    assert candidate.substitution_type == "major"
    assert candidate.requires_approval is True
    assert candidate.substitution_reasons == (
        "attribute_change:acceptable_colors",
    )


def test_equivalent_tip_and_eraser_style_vocabulary_matches_exactly() -> None:
    """BR-13/FR-19: safe source/catalog synonyms do not invent changes."""

    cases = (
        (
            _need(
                "permanent_markers",
                req_id="marker",
                attributes={"tip_style": "fine tip"},
            ),
            _offer(
                "FINE-MARKER",
                "S",
                "permanent_markers",
                attributes={"tip": "fine"},
            ),
        ),
        (
            _need(
                "erasers",
                req_id="eraser",
                attributes={"style": "pencil top"},
            ),
            _offer(
                "CAP-ERASER",
                "S",
                "erasers",
                attributes={"style": "cap"},
            ),
        ),
    )

    for need, offer in cases:
        candidate = match_offers(
            [need],
            [offer],
            [_store("S", 1.0)],
        ).needs[0].candidates[0]
        assert candidate.attribute_status == "exact"
        assert candidate.requires_approval is False
        assert not any(
            reason.startswith("attribute_change:")
            for reason in candidate.substitution_reasons
        )


def test_genuine_tip_and_eraser_style_changes_remain_major() -> None:
    """FR-19: canonicalization does not erase real product differences."""

    cases = (
        (
            _need(
                "permanent_markers",
                req_id="marker",
                attributes={"tip_style": "fine"},
            ),
            _offer(
                "CHISEL-MARKER",
                "S",
                "permanent_markers",
                attributes={"tip": "chisel"},
            ),
            "attribute_change:tip_style",
        ),
        (
            _need(
                "erasers",
                req_id="eraser",
                attributes={"style": "cap"},
            ),
            _offer(
                "BLOCK-ERASER",
                "S",
                "erasers",
                attributes={"style": "block"},
            ),
            "attribute_change:style",
        ),
    )

    for need, offer, expected_reason in cases:
        candidate = match_offers(
            [need],
            [offer],
            [_store("S", 1.0)],
        ).needs[0].candidates[0]
        assert candidate.attribute_status == "different"
        assert candidate.requires_approval is True
        assert expected_reason in candidate.substitution_reasons


def test_exact_attribute_match_is_selected_over_cheaper_substitution() -> None:
    """FR-19: price cannot silently displace an available exact attribute."""

    need = _need(
        "pens",
        attributes={"acceptable_colors": ("black", "blue")},
    )
    exact = _offer(
        "BLUE-PENS",
        "S",
        "pens",
        attributes={"ink_color": "blue"},
    )
    exact = Offer(**{**exact.__dict__, "pack_price": 200})
    cheaper_substitution = _offer(
        "RED-PENS",
        "S",
        "pens",
        attributes={"ink_color": "red"},
    )
    matches = match_offers(
        [need],
        [exact, cheaper_substitution],
        [_store("S", 1.0)],
    )

    assert {
        candidate.offer.sku for candidate in matches.needs[0].candidates
    } == {"BLUE-PENS", "RED-PENS"}
    assert matches.candidate_skus_by_need == {
        ("req-1",): frozenset({"BLUE-PENS"})
    }

    optimized = optimize_cart(
        [need],
        [exact, cheaper_substitution],
        [_store("S", 1.0)],
        OptimizationConfig(
            fulfillment_preference="pickup",
            tax_basis_points=0,
        ),
        candidate_skus_by_need=matches.candidate_skus_by_need,
    )
    assert optimized.plan.lines[0].sku == "BLUE-PENS"
    assert optimized.plan.item_subtotal == 200


def test_unknown_catalog_attribute_becomes_line_note_not_approval() -> None:
    """FR-19: missing evidence is noted rather than posed as a decision."""

    need = _need("pencil_boxes", attributes={"size": "approx. 8 inches"})
    candidate = match_offers(
        [need],
        [_offer("BOX", "S", "pencil_boxes")],
        [_store("S", 1.0)],
    ).needs[0].candidates[0]

    assert candidate.attribute_status == "unknown"
    assert candidate.line_notes == ("catalog_attribute_unknown:size",)
    assert candidate.requires_approval is False


def test_numeric_catalog_dimension_matches_normalized_source_dimension() -> None:
    """FR-19/BR-13: approximate prose and numeric inches are one value."""

    need = _need("pencil_boxes", attributes={"size": "8 inch"})
    candidate = match_offers(
        [need],
        [
            _offer(
                "BOX-8",
                "S",
                "pencil_boxes",
                attributes={"length_inches": 8},
            )
        ],
        [_store("S", 1.0)],
    ).needs[0].candidates[0]

    assert candidate.attribute_status == "exact"
    assert "attribute_change:size" not in candidate.substitution_reasons
    assert candidate.requires_approval is False


def test_retired_br08_does_not_filter_non_returnable_offer() -> None:
    """BR-08: legacy returnability data has no matching effect."""

    need = _need("tissues")
    returnable = _offer("RETURNABLE", "S", "tissues")
    returnable = Offer(**{**returnable.__dict__, "pack_price": 200})
    non_returnable = _offer(
        "NON-RETURNABLE",
        "S",
        "tissues",
        is_returnable=False,
    )
    non_returnable = Offer(
        **{**non_returnable.__dict__, "pack_price": 1_800}
    )
    matches = match_offers(
        [need],
        [returnable, non_returnable],
        [_store("S", 1.0)],
    )

    assert matches.candidate_skus_by_need == {
        ("req-1",): frozenset({"RETURNABLE", "NON-RETURNABLE"})
    }
    assert all(
        not candidate.requires_approval
        for candidate in matches.needs[0].candidates
    )


def test_br11_below_floor_match_is_blocked_for_review() -> None:
    """BR-11: a 0.69 match cannot proceed into optimization."""

    result = match_offers(
        [_need("pencils")],
        [_offer("PENCILS", "S", "pencils")],
        [_store("S", 1.0)],
        judge=FixedJudge(0.69),
    )
    need_matches = result.needs[0]

    assert need_matches.candidates == ()
    assert len(need_matches.review_blocked_candidates) == 1
    assert need_matches.requires_confidence_review is True
    assert result.candidate_skus_by_need == {("req-1",): frozenset()}


def test_e12_no_catalog_equivalent_is_unfulfillable() -> None:
    """E-12: absence is reported and no offer is fabricated."""

    result = match_offers(
        [_need("headphones")],
        [_offer("PENCILS", "S", "pencils")],
        [_store("S", 1.0)],
    )

    assert result.needs[0].candidates == ()
    assert result.needs[0].review_blocked_candidates == ()
    assert result.needs[0].unfulfillable is True
