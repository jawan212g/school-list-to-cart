"""Presentation-option tests that leave the seven-condition gate unchanged."""

from types import SimpleNamespace

import pytest

import app
from agent.aggregate import UnitNeed
from agent.approval_options import (
    build_catalog_approval_choices,
    removal_cost_context,
)
from agent.decisions import DecisionLog
from agent.gate import ApprovalBatch, GateContext, evaluate_gate
from agent.match import MatchResult, match_offers
from agent.normalize import NormalizationResult
from agent.optimize import (
    OptimizationConfig,
    OptimizationResult,
    optimize_cart,
)
from agent.pipeline import PipelineSession
from data.loader import Offer, Store


def _store(
    store_id: str,
    name: str,
    *,
    delivery_fee: int = 0,
    delivery_minimum: int = 0,
    tax_applies: bool = False,
) -> Store:
    return Store(
        store_id=store_id,
        name=name,
        distance_miles=1.0,
        pickup_fee=0,
        pickup_minimum=0,
        delivery_fee=delivery_fee,
        delivery_minimum=delivery_minimum,
        tax_applies=tax_applies,
        pickup_available=True,
    )


def _offer(
    sku: str,
    store_id: str,
    title: str,
    category: str,
    pack_size: int,
    pack_price: int,
    *,
    is_returnable: bool = True,
    attributes: dict[str, object] | None = None,
) -> Offer:
    return Offer(
        sku=sku,
        store_id=store_id,
        brand=title.split()[0],
        title=title,
        category=category,
        pack_size=pack_size,
        unit_price=pack_price // pack_size,
        pack_price=pack_price,
        stock_qty=20,
        is_returnable=is_returnable,
        attributes=attributes or {},
    )


def _need(
    category: str,
    quantity: int,
    allocated_to: dict[str, int],
    attributes: dict[str, object],
    req_id: str,
) -> UnitNeed:
    return UnitNeed(
        canonical_item=category,
        quantity=quantity,
        brand_lock=None,
        unit_type="each",
        exclusions=(),
        is_required=True,
        attributes=attributes,
        allocated_to=allocated_to,
        source_requirement_ids=(req_id,),
    )


def _approval_fixture(
    needs: tuple[UnitNeed, ...],
    offers: tuple[Offer, ...],
    stores: tuple[Store, ...],
    config: OptimizationConfig,
) -> tuple[MatchResult, OptimizationResult, ApprovalBatch]:
    matches = match_offers(needs, offers, stores)
    optimization = optimize_cart(
        needs,
        offers,
        stores,
        config,
        candidate_skus_by_need=matches.candidate_skus_by_need,
    )
    batch = evaluate_gate(
        GateContext(
            optimization=optimization,
            matches=matches,
            normalization=NormalizationResult(requirements=()),
            extractions={},
            offers=offers,
            stores=stores,
            tax_basis_points=config.tax_basis_points,
            unit_needs=needs,
            optimization_config=config,
        )
    )
    return matches, optimization, batch


@pytest.mark.parametrize(
    (
        "category",
        "attributes",
        "current_offer",
        "alternative_offer",
        "expected_heading",
    ),
    [
        (
            "binders",
            {"size": "1.5 inch"},
            _offer(
                "BINDER-ONE",
                "VALUE",
                "Value Basics 1-Inch Binder",
                "binders",
                1,
                240,
                attributes={"capacity_inches": 1},
            ),
            _offer(
                "BINDER-TWO",
                "VALUE",
                "Avery Durable 2-Inch Binder",
                "binders",
                1,
                520,
                attributes={"capacity_inches": 2},
            ),
            "Binder — choose an acceptable size",
        ),
        (
            "dividers",
            {"tab_count": 5},
            _offer(
                "DIVIDER-EIGHT",
                "VALUE",
                "Avery 8-Tab Dividers",
                "dividers",
                1,
                180,
                attributes={"tabs_per_set": 8},
            ),
            _offer(
                "DIVIDER-EIGHT-FOUR",
                "VALUE",
                "Cloud Choice 8-Tab Dividers, 4 Sets",
                "dividers",
                4,
                600,
                attributes={"tabs_per_set": 8},
            ),
            "Dividers — choose an acceptable tab count",
        ),
    ],
)
def test_no_exact_match_keeps_catalog_choices_and_self_source_last(
    category: str,
    attributes: dict[str, object],
    current_offer: Offer,
    alternative_offer: Offer,
    expected_heading: str,
) -> None:
    """FR-28/29: real products lead and parent self-sourcing ranks last."""

    stores = (_store("VALUE", "Value Depot"),)
    need = _need(
        category,
        1,
        {"grade5": 1},
        attributes,
        f"grade5:{category}",
    )
    offers = (current_offer, alternative_offer)
    config = OptimizationConfig(
        shopping_mode="budget",
        fulfillment_preference="pickup",
        tax_basis_points=0,
    )
    matches, optimization, batch = _approval_fixture(
        (need,),
        offers,
        stores,
        config,
    )
    interrupt = batch.interrupts[0]

    choices = build_catalog_approval_choices(
        interrupt,
        optimization,
        matches,
        (need,),
        offers,
        stores,
        config,
    )
    assert tuple(choice.cost_delta_cents for choice in choices) == (
        0,
        alternative_offer.pack_price - current_offer.pack_price,
    )

    result = SimpleNamespace(
        session=PipelineSession(
            session_id="approval-test",
            children=("grade5",),
            budget_total=10_000,
            fulfillment_pref="pickup",
            tax_basis_points=0,
        ),
        proposed_cart=optimization,
        matches=matches,
        purchase_needs=(need,),
        approval_batch=batch,
        normalization=NormalizationResult(requirements=()),
    )
    presentation = app.build_approval_presentations(
        result,
        offers,
        stores,
        {"grade5": "Grade 5"},
    )[0]

    assert presentation.heading == expected_heading
    assert presentation.affected_children == ("Grade 5",)
    assert len(presentation.options) == 3
    assert current_offer.title in presentation.options[0].label
    assert alternative_offer.title in presentation.options[1].label
    assert presentation.options[1].explanation is not None
    assert presentation.options[1].explanation == (
        f"Adds {app.format_money(alternative_offer.pack_price - current_offer.pack_price)} "
        "landed "
        f"({app.format_money(alternative_offer.pack_price - current_offer.pack_price)} item)"
    )
    assert presentation.options[-1].label == (
        "Do not buy this — I will source it myself "
        f"(leaves required {presentation.item_name.lower()} unmet)"
    )
    assert presentation.options[-1].leaves_required_unmet is True
    assert "source it myself" not in presentation.recommendation
    assert all(
        offer.sku not in presentation.heading
        + presentation.message
        + presentation.recommendation
        + " ".join(option.label for option in presentation.options)
        for offer in offers
    )


def test_headphones_removal_keeps_gate_delta_and_explains_delivery_threshold() -> None:
    """FR-28: shared headphones show both children and the $31.01 rationale."""

    store = _store(
        "CLOUD",
        "Supply Cloud",
        delivery_fee=749,
        delivery_minimum=4_900,
        tax_applies=True,
    )
    headphones = _need(
        "headphones",
        2,
        {"grade2": 1, "grade5": 1},
        {},
        "shared:headphones",
    )
    pencils = _need(
        "pencils",
        1,
        {"grade5": 1},
        {},
        "grade5:pencils",
    )
    headphone_offer = _offer(
        "CLOUD-HEADPHONES",
        "CLOUD",
        "ClassSound Volume-Limited Student Headphones",
        "headphones",
        1,
        1_799,
        is_returnable=False,
    )
    pencil_offer = _offer(
        "CLOUD-PENCILS",
        "CLOUD",
        "Cloud Choice Pencils",
        "pencils",
        1,
        1_364,
    )
    needs = (headphones, pencils)
    offers = (headphone_offer, pencil_offer)
    stores = (store,)
    config = OptimizationConfig(
        shopping_mode="budget",
        fulfillment_preference="delivery",
        tax_basis_points=700,
    )
    matches, optimization, batch = _approval_fixture(
        needs,
        offers,
        stores,
        config,
    )
    interrupt = next(
        item
        for item in batch.interrupts
        if item.kind == "non_returnable_threshold"
    )
    removal = next(
        option
        for option in interrupt.alternatives
        if option.alternative_id.endswith("-omit")
    )

    assert optimization.landed_cost == 5_309
    assert removal.cost_delta_cents == -3_101
    context = removal_cost_context(
        interrupt,
        optimization,
        stores,
    )
    assert context is not None
    assert context.line_cost_cents == 3_598
    assert context.fee_returns_cents == 749
    assert context.fee_threshold_cents == 4_900

    result = SimpleNamespace(
        session=PipelineSession(
            session_id="approval-headphones",
            children=("grade2", "grade5"),
            budget_total=15_000,
            fulfillment_pref="delivery",
            tax_basis_points=700,
        ),
        proposed_cart=optimization,
        matches=matches,
        purchase_needs=needs,
        approval_batch=batch,
        normalization=NormalizationResult(requirements=()),
        decisions=(),
    )
    presentation = app.build_approval_presentations(
        result,
        offers,
        stores,
        {"grade2": "Grade 2", "grade5": "Grade 5"},
    )[0]

    assert presentation.heading == (
        "Headphones — non-returnable, over $15.00"
    )
    assert presentation.affected_children == ("Grade 2", "Grade 5")
    assert tuple(
        option.cost_delta_cents for option in presentation.options
    ) == (0, -3_101)
    assert presentation.options[1].label == (
        "Do not buy this — I will source it myself "
        "(leaves required headphones unmet)"
    )
    assert presentation.options[1].explanation == (
        "No other stocked catalog match is available. This saves the item "
        "and its tax, but Supply Cloud's $7.49 delivery fee returns because "
        "the remaining item subtotal falls below $49.00."
    )
    visible_text = " ".join(
        (
            presentation.heading,
            presentation.message,
            presentation.recommendation,
            *(option.label for option in presentation.options),
        )
    )
    assert "CLOUD-HEADPHONES" not in visible_text
    assert "3598 cents" not in visible_text
    assert "non_returnable_threshold" not in visible_text

    outcomes = {
        presentation.interrupt.interrupt_id: (
            presentation.options[1].alternative_id
        )
    }
    adjusted = app._apply_approval_outcomes(
        optimization,
        matches,
        needs,
        (presentation,),
        outcomes,
        offers,
        stores,
        config,
    )
    assert adjusted.landed_cost == 2_208
    assert tuple(line.canonical_item for line in adjusted.plan.lines) == (
        "pencils",
    )
    assert app._self_sourced_decisions(
        (presentation,),
        outcomes,
    ) == (presentation,)
    summary = app.build_text_summary(
        result,
        adjusted,
        matches,
        stores,
        {"grade2": "Grade 2", "grade5": "Grade 5"},
        {
            presentation.heading: presentation.options[1].label,
        },
        (presentation,),
        (),
    )
    assert "STATUS: INCOMPLETE" in summary
    assert "ITEMS YOU CHOSE TO SOURCE YOURSELF" in summary
    assert "Headphones | Grade 2 and Grade 5" in summary
    assert "UNFULFILLED BY PARENT CHOICE" in summary
    assert "LANDED COST: $22.08" in summary
    assert "\\$" not in summary
    decision_log = DecisionLog("parent-self-source")
    decision_log.record_approval_response(
        presentation.options[1].label,
        affected_lines=presentation.interrupt.affected_lines,
    )
    assert decision_log.entries[0].actor == "parent"
    assert "source it myself" in decision_log.entries[0].rationale


def test_radio_option_uses_escaped_label_and_attached_caption() -> None:
    """Streamlit receives separate escaped radio labels and captions."""

    option = app.ApprovalDisplayOption(
        alternative_id="binder-two",
        label="Choose Avery 2-Inch Binder — Value Depot",
        cost_delta_cents=300,
        explanation="Adds $3.00 landed ($2.80 item, $0.20 tax)",
    )

    label = app.approval_option_label(option)
    caption = app.approval_option_caption(option)

    assert label == (
        "Choose Avery 2-Inch Binder — Value Depot "
        "(adds \\$3.00)"
    )
    assert caption == (
        "Adds \\$3.00 landed (\\$2.80 item, \\$0.20 tax)"
    )
    assert "$" not in (label + caption).replace("\\$", "")


def test_self_source_option_is_visually_separated() -> None:
    """The parent-sourcing option is distinguished from product choices."""

    option = app.ApprovalDisplayOption(
        alternative_id="binder-parent-remove",
        label="Do not buy this — I will source it myself",
        cost_delta_cents=-300,
        explanation="No exact catalog match is available. Saves $3.00.",
        leaves_required_unmet=True,
    )

    label = app.approval_option_label(option)
    caption = app.approval_option_caption(option)

    assert label.startswith("────────  \nDo not buy this")
    assert caption.startswith("Source-it-yourself choice")
    assert "Saves \\$3.00" in caption
