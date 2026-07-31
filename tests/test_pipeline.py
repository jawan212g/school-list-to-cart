"""Model-free end-to-end tests for proposal pipeline composition."""

from agent.match import StructuredSuitabilityJudge
from agent.pipeline import (
    ListInput,
    PipelineSession,
    run_pipeline,
    run_pipeline_from_confirmed_extractions,
)
from agent.schema import ExtractionEnvelope, Requirement
from data.loader import Offer, Store


def _fake_extractor(
    source: str,
    *,
    child_id: str,
    mime_type: str | None,
    client: object,
) -> ExtractionEnvelope:
    del mime_type, client
    quantity = {"list-a": 2, "list-b": 3}[source]
    return ExtractionEnvelope(
        requirements=(
            Requirement(
                req_id=f"{child_id}-pencils",
                child_id=child_id,
                raw_text=f"{quantity} pencils",
                canonical_item="pencils",
                quantity=quantity,
                extraction_confidence=1.0,
            ),
        )
    )


def test_pipeline_wires_two_lists_through_one_optimized_cart() -> None:
    """FR-14–FR-25: extraction through optimization preserves exact units."""

    store = Store(
        store_id="S",
        name="Store",
        distance_miles=1.0,
        pickup_fee=0,
        pickup_minimum=0,
        delivery_fee=0,
        delivery_minimum=0,
        tax_applies=False,
    )
    offer = Offer(
        sku="PENCILS-5",
        store_id="S",
        brand="Generic",
        title="Five pencils",
        category="pencils",
        pack_size=5,
        unit_price=100,
        pack_price=500,
        stock_qty=1,
        is_returnable=True,
        attributes={},
    )
    session = PipelineSession(
        session_id="session",
        children=("child-a", "child-b"),
        budget_total=1_000,
        shopping_mode="budget",
        fulfillment_pref="pickup",
        tax_basis_points=0,
    )

    result = run_pipeline(
        session,
        [
            ListInput(child_id="child-a", source="list-a"),
            ListInput(child_id="child-b", source="list-b"),
        ],
        stores=[store],
        offers=[offer],
        suitability_judge=StructuredSuitabilityJudge(),
        extractor=_fake_extractor,
    )

    assert len(result.unit_needs) == 1
    assert result.unit_needs[0].quantity == 5
    assert result.unit_needs[0].allocated_to == {
        "child-a": 2,
        "child-b": 3,
    }
    assert result.unit_needs[0].source_requirement_ids == (
        "child-a:child-a-pencils",
        "child-b:child-b-pencils",
    )
    assert result.proposed_cart.plan.item_subtotal == 500
    assert result.proposed_cart.landed_cost == 500
    assert result.proposed_cart.plan.lines[0].sku == "PENCILS-5"
    assert result.proposed_cart.plan.lines[0].match_confidence == 1.0
    assert result.approval_flags == ()
    assert [decision.type for decision in result.decisions] == [
        "match",
        "substitution",
        "store_assignment",
        "budget_action",
    ]
    assert all(decision.actor == "agent" for decision in result.decisions)


def test_two_lists_for_one_student_merge_equal_requirement_once() -> None:
    """BR-20/BR-22: separate lists merge by production requirement identity."""

    store = Store(
        store_id="S",
        name="Store",
        distance_miles=1.0,
        pickup_fee=0,
        pickup_minimum=0,
        delivery_fee=0,
        delivery_minimum=0,
        tax_applies=False,
    )
    offer = Offer(
        sku="BACKPACK",
        store_id="S",
        brand="Generic",
        title="Backpack",
        category="backpacks",
        pack_size=1,
        unit_price=2_000,
        pack_price=2_000,
        stock_qty=2,
        is_returnable=True,
        attributes={},
    )

    def extractor(
        source: str,
        *,
        child_id: str,
        mime_type: str | None,
        client: object,
    ) -> ExtractionEnvelope:
        del mime_type, client
        return ExtractionEnvelope(
            requirements=(
                Requirement(
                    req_id="backpack",
                    child_id=child_id,
                    raw_text="1 backpack",
                    canonical_item="backpacks",
                    quantity=1,
                    source_section=source,
                    extraction_confidence=1.0,
                ),
            )
        )

    result = run_pipeline(
        PipelineSession(
            session_id="same-student-two-lists",
            children=("child-a",),
            budget_total=5_000,
            fulfillment_pref="pickup",
            tax_basis_points=0,
        ),
        (
            ListInput(
                child_id="child-a",
                source="Grade 5",
                document_name="grade-five.txt",
            ),
            ListInput(
                child_id="child-a",
                source="Highly Capable",
                document_name="highly-capable.txt",
            ),
        ),
        stores=(store,),
        offers=(offer,),
        suitability_judge=StructuredSuitabilityJudge(),
        extractor=extractor,
    )

    assert len(result.extractions["child-a"].requirements) == 1
    merged = result.extractions["child-a"].requirements[0]
    assert merged.quantity == 1
    assert tuple(source.document_name for source in merged.sources) == (
        "grade-five.txt",
        "highly-capable.txt",
    )
    assert result.unit_needs[0].quantity == 1
    assert result.proposed_cart.landed_cost == 2_000


def test_per_entry_budgets_reach_cost_attribution_and_budget_review() -> None:
    """FR-03/BR-09: mixed-entry allocations survive through the budget gate."""

    store = Store(
        store_id="S",
        name="Store",
        distance_miles=1.0,
        pickup_fee=0,
        pickup_minimum=0,
        delivery_fee=0,
        delivery_minimum=0,
        tax_applies=False,
    )
    offer = Offer(
        sku="PENCILS-5",
        store_id="S",
        brand="Generic",
        title="Five pencils",
        category="pencils",
        pack_size=5,
        unit_price=100,
        pack_price=500,
        stock_qty=1,
        is_returnable=True,
        attributes={},
    )
    session = PipelineSession(
        session_id="per-entry-budgets",
        children=("student", "classroom"),
        budget_total=400,
        budget_mode="per_child",
        budget_allocations={
            "student": 150,
            "classroom": 250,
        },
        shopping_mode="budget",
        fulfillment_pref="pickup",
        tax_basis_points=0,
    )

    result = run_pipeline(
        session,
        (
            ListInput(child_id="student", source="list-a"),
            ListInput(child_id="classroom", source="list-b"),
        ),
        stores=(store,),
        offers=(offer,),
        suitability_judge=StructuredSuitabilityJudge(),
        extractor=_fake_extractor,
    )

    assert result.session.budget_allocations == {
        "student": 150,
        "classroom": 250,
    }
    assert result.proposed_cart.plan.per_child_item_costs == {
        "student": 200,
        "classroom": 300,
    }
    assert result.proposed_cart.plan.per_child_landed_costs == {
        "student": 200,
        "classroom": 300,
    }
    assert result.proposed_cart.landed_cost == 500
    assert result.proposed_cart.shortfall_cents == 100
    assert tuple(
        interrupt.kind for interrupt in result.approval_batch.interrupts
    ) == ("budget_exceeded",)


def test_confirmed_extraction_boundary_builds_without_reextracting() -> None:
    """FR-12: only the reviewed envelope enters plan generation."""

    store = Store(
        store_id="S",
        name="Store",
        distance_miles=1.0,
        pickup_fee=0,
        pickup_minimum=0,
        delivery_fee=0,
        delivery_minimum=0,
        tax_applies=False,
    )
    offer = Offer(
        sku="PENCILS-2",
        store_id="S",
        brand="Generic",
        title="Two pencils",
        category="pencils",
        pack_size=2,
        unit_price=50,
        pack_price=100,
        stock_qty=1,
        is_returnable=True,
        attributes={},
    )
    session = PipelineSession(
        session_id="confirmed",
        children=("child-a",),
        budget_total=500,
        fulfillment_pref="pickup",
        tax_basis_points=0,
    )
    reviewed = {
        "child-a": ExtractionEnvelope(
            requirements=(
                Requirement(
                    req_id="confirmed-pencil",
                    child_id="child-a",
                    raw_text="2 pencils",
                    canonical_item="pencils",
                    quantity=2,
                    extraction_confidence=1.0,
                ),
            )
        )
    }

    result = run_pipeline_from_confirmed_extractions(
        session,
        reviewed,
        stores=[store],
        offers=[offer],
        suitability_judge=StructuredSuitabilityJudge(),
    )

    assert result.unit_needs[0].quantity == 2
    assert result.proposed_cart.plan.lines[0].sku == "PENCILS-2"


def test_nonpurchasable_reminder_cannot_make_plan_incomplete() -> None:
    """FR-10: an incorrectly required reminder stays outside plan completeness."""

    def extractor(
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
                    req_id="pencils",
                    child_id=child_id,
                    raw_text="1 pencil",
                    canonical_item="pencils",
                    quantity=1,
                    extraction_confidence=1.0,
                ),
                Requirement.model_validate(
                    {
                        "req_id": "label-reminder",
                        "child_id": child_id,
                        "raw_text": "Reminder: label everything.",
                        "canonical_item": "non_purchasable",
                        "quantity": 1,
                        "is_required": True,
                        "is_purchasable": False,
                        "requirement_type": "required",
                        "extraction_confidence": 0.0,
                    }
                ),
            )
        )

    store = Store(
        store_id="S",
        name="Store",
        distance_miles=1.0,
        pickup_fee=0,
        pickup_minimum=0,
        delivery_fee=0,
        delivery_minimum=0,
        tax_applies=False,
    )
    offer = Offer(
        sku="PENCIL",
        store_id="S",
        brand="Generic",
        title="One pencil",
        category="pencils",
        pack_size=1,
        unit_price=100,
        pack_price=100,
        stock_qty=1,
        is_returnable=True,
        attributes={},
    )
    result = run_pipeline(
        PipelineSession(
            session_id="display-only-reminder",
            children=("child",),
            budget_total=500,
            fulfillment_pref="pickup",
            tax_basis_points=0,
        ),
        [ListInput(child_id="child", source="list")],
        stores=[store],
        offers=[offer],
        suitability_judge=StructuredSuitabilityJudge(),
        extractor=extractor,
    )

    display_only = result.normalization.display_only_requirements
    assert len(display_only) == 1
    assert display_only[0].source.is_required is False
    assert result.proposed_cart.is_complete is True
    assert result.approval_flags == ()


def test_pipeline_reports_required_item_with_no_equivalent_as_a_gap() -> None:
    """E-12: a missing catalog category stays visible without an interrupt."""

    def headphones_extractor(
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
                    req_id="headphones",
                    child_id=child_id,
                    raw_text="1 pair headphones",
                    canonical_item="headphones",
                    quantity=1,
                    extraction_confidence=1.0,
                ),
            )
        )

    session = PipelineSession(
        session_id="session",
        children=("child-a",),
        budget_total=1_000,
        fulfillment_pref="pickup",
        tax_basis_points=0,
    )
    store = Store(
        store_id="S",
        name="Store",
        distance_miles=1.0,
        pickup_fee=0,
        pickup_minimum=0,
        delivery_fee=0,
        delivery_minimum=0,
        tax_applies=False,
    )

    result = run_pipeline(
        session,
        [ListInput(child_id="child-a", source="list")],
        stores=[store],
        offers=[],
        suitability_judge=StructuredSuitabilityJudge(),
        extractor=headphones_extractor,
    )

    assert result.proposed_cart.gap_items == ("headphones",)
    assert result.proposed_cart.is_complete is False
    assert result.approval_flags == ()


def test_e33_one_failed_extraction_does_not_block_the_other_list() -> None:
    """E-33: a failed list is reported while successful lists continue."""

    def partial_extractor(
        source: str,
        *,
        child_id: str,
        mime_type: str | None,
        client: object,
    ) -> ExtractionEnvelope:
        del mime_type, client
        if source == "bad":
            raise ValueError("Unreadable document")
        return ExtractionEnvelope(
            requirements=(
                Requirement(
                    req_id="pencils",
                    child_id=child_id,
                    raw_text="1 pencil",
                    canonical_item="pencils",
                    quantity=1,
                    extraction_confidence=1.0,
                ),
            )
        )

    store = Store(
        store_id="S",
        name="Store",
        distance_miles=1.0,
        pickup_fee=0,
        pickup_minimum=0,
        delivery_fee=0,
        delivery_minimum=0,
        tax_applies=False,
    )
    offer = Offer(
        sku="PENCIL",
        store_id="S",
        brand="Generic",
        title="Pencil",
        category="pencils",
        pack_size=1,
        unit_price=100,
        pack_price=100,
        stock_qty=1,
        is_returnable=True,
        attributes={},
    )
    result = run_pipeline(
        PipelineSession(
            session_id="session",
            children=("good", "bad"),
            budget_total=1_000,
            fulfillment_pref="pickup",
            tax_basis_points=0,
        ),
        [
            ListInput(child_id="good", source="good"),
            ListInput(child_id="bad", source="bad"),
        ],
        stores=[store],
        offers=[offer],
        suitability_judge=StructuredSuitabilityJudge(),
        extractor=partial_extractor,
    )

    assert result.proposed_cart.landed_cost == 100
    assert tuple(result.extractions) == ("good",)
    assert result.extraction_failures == {
        "bad": "ValueError: Unreadable document"
    }


def test_e33_empty_extraction_is_explicit_and_other_list_continues() -> None:
    """E-33: a silent empty model response fails only its source list."""

    def empty_for_one_child(
        source: str,
        *,
        child_id: str,
        mime_type: str | None,
        client: object,
    ) -> ExtractionEnvelope:
        del mime_type, client
        if source == "empty-result":
            return ExtractionEnvelope(requirements=())
        return ExtractionEnvelope(
            requirements=(
                Requirement(
                    req_id="pencils",
                    child_id=child_id,
                    raw_text="1 pencil",
                    canonical_item="pencils",
                    quantity=1,
                    extraction_confidence=1.0,
                ),
            )
        )

    store = Store(
        store_id="S",
        name="Store",
        distance_miles=1.0,
        pickup_fee=0,
        pickup_minimum=0,
        delivery_fee=0,
        delivery_minimum=0,
        tax_applies=False,
    )
    offer = Offer(
        sku="PENCIL",
        store_id="S",
        brand="Generic",
        title="Pencil",
        category="pencils",
        pack_size=1,
        unit_price=100,
        pack_price=100,
        stock_qty=1,
        is_returnable=True,
        attributes={},
    )

    result = run_pipeline(
        PipelineSession(
            session_id="empty-extraction",
            children=("good", "missing"),
            budget_total=1_000,
            fulfillment_pref="pickup",
            tax_basis_points=0,
        ),
        (
            ListInput(child_id="good", source="one pencil"),
            ListInput(child_id="missing", source="empty-result"),
        ),
        stores=(store,),
        offers=(offer,),
        suitability_judge=StructuredSuitabilityJudge(),
        extractor=empty_for_one_child,
    )

    assert result.proposed_cart.landed_cost == 100
    assert tuple(result.extractions) == ("good",)
    assert result.extraction_failures == {
        "missing": (
            "EmptyExtractionError: No supply requirements were found in this "
            "non-empty list. This list was not included in the plan. Check "
            "that the correct uploaded file or typed entry was provided, then try "
            "again."
        )
    }


def test_identical_cross_child_decision_is_returned_once() -> None:
    """BR-10: one SKU and one question produce one session decision."""

    def headphones_extractor(
        source: str,
        *,
        child_id: str,
        mime_type: str | None,
        client: object,
    ) -> ExtractionEnvelope:
        del mime_type, client
        attributes = (
            {"connector": "3.5 mm"}
            if source == "connector"
            else {"acceptable_colors": ["black"]}
        )
        return ExtractionEnvelope(
            requirements=(
                Requirement(
                    req_id="headphones",
                    child_id=child_id,
                    raw_text="1 pair headphones",
                    canonical_item="headphones",
                    quantity=1,
                    attributes=attributes,
                    extraction_confidence=1.0,
                ),
            )
        )

    store = Store(
        store_id="S",
        name="Store",
        distance_miles=1.0,
        pickup_fee=0,
        pickup_minimum=0,
        delivery_fee=0,
        delivery_minimum=0,
        tax_applies=False,
    )
    offer = Offer(
        sku="HEADPHONES",
        store_id="S",
        brand="Generic",
        title="Black 3.5 mm headphones",
        category="headphones",
        pack_size=1,
        unit_price=1_800,
        pack_price=1_800,
        stock_qty=2,
        is_returnable=False,
        attributes={"connector": "3.5 mm", "color": "black"},
    )
    result = run_pipeline(
        PipelineSession(
            session_id="session",
            children=("a", "b"),
            budget_total=10_000,
            fulfillment_pref="pickup",
            tax_basis_points=0,
        ),
        [
            ListInput(child_id="a", source="connector"),
            ListInput(child_id="b", source="color"),
        ],
        stores=[store],
        offers=[offer],
        suitability_judge=StructuredSuitabilityJudge(),
        extractor=headphones_extractor,
    )

    assert len(result.proposed_cart.plan.lines) == 1
    shared_line = result.proposed_cart.plan.lines[0]
    assert shared_line.packs_purchased == 2
    assert shared_line.units_needed == 2
    assert shared_line.allocated_to == {"a": 1, "b": 1}
    assert shared_line.source_requirement_ids == (
        "a:headphones",
        "b:headphones",
    )
    assert result.approval_flags == ()
    assert all(
        decision.type != "approval_request"
        for decision in result.decisions
    )


def test_e23_optional_item_is_never_added_to_cross_delivery_threshold() -> None:
    """E-23: deferred threshold suggestions cannot mutate the base cart."""

    def threshold_extractor(
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
                    req_id="optional",
                    child_id=child_id,
                    raw_text="Optional pencils",
                    canonical_item="pencils",
                    quantity=1,
                    is_required=False,
                    requirement_type="optional",
                    extraction_confidence=1.0,
                ),
            )
        )

    store = Store(
        store_id="D",
        name="Delivery",
        distance_miles=1.0,
        pickup_fee=0,
        pickup_minimum=0,
        delivery_fee=749,
        delivery_minimum=4_900,
        tax_applies=False,
        pickup_available=False,
    )
    offers = [
        Offer(
            sku="BACKPACK",
            store_id="D",
            brand="Generic",
            title="Backpack",
            category="backpacks",
            pack_size=1,
            unit_price=4_800,
            pack_price=4_800,
            stock_qty=1,
            is_returnable=True,
            attributes={},
        ),
        Offer(
            sku="PENCILS",
            store_id="D",
            brand="Generic",
            title="Pencils",
            category="pencils",
            pack_size=1,
            unit_price=200,
            pack_price=200,
            stock_qty=1,
            is_returnable=True,
            attributes={},
        ),
    ]
    result = run_pipeline(
        PipelineSession(
            session_id="session",
            children=("child",),
            budget_total=10_000,
            fulfillment_pref="delivery",
            tax_basis_points=0,
        ),
        [ListInput(child_id="child", source="list")],
        stores=[store],
        offers=offers,
        suitability_judge=StructuredSuitabilityJudge(),
        extractor=threshold_extractor,
    )

    assert len(result.proposed_cart.plan.lines) == 1
    assert result.proposed_cart.plan.lines[0].sku == "BACKPACK"
    assert result.proposed_cart.plan.item_subtotal == 4_800
    assert result.proposed_cart.plan.fulfillment_fees == 749
    assert result.proposed_cart.landed_cost == 5_549
