"""Presentation-option tests for the active approval gate."""

from dataclasses import replace

import pytest

import app
from agent.addons import AddOnItem, AddOnProposal
from agent.aggregate import UnitNeed
from agent.approval_options import (
    build_catalog_approval_choices,
    removal_cost_context,
)
from agent.budget_plans import (
    build_budget_analysis,
    evaluate_budget_actions,
)
from agent.decisions import DecisionLog
from agent.gate import (
    ApprovalAlternative,
    ApprovalBatch,
    ApprovalInterrupt,
    GateContext,
    evaluate_gate,
)
from agent.match import MatchResult, match_offers
from agent.normalize import NormalizationResult
from agent.optimize import (
    OptimizationConfig,
    OptimizationResult,
    optimize_cart,
)
from agent.pipeline import PipelineResult, PipelineSession
from agent.review import organize_extractions
from agent.schema import ExtractionEnvelope, Requirement
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


def _pipeline_result(
    *,
    session: PipelineSession,
    needs: tuple[UnitNeed, ...],
    matches: MatchResult,
    optimization: OptimizationResult,
    batch: ApprovalBatch,
) -> PipelineResult:
    """Build the real pipeline result contract used by app presentation code."""

    normalization = NormalizationResult(requirements=())
    return PipelineResult(
        session=session,
        extractions={},
        normalization=normalization,
        unit_needs=needs,
        purchase_needs=needs,
        matches=matches,
        proposed_cart=optimization,
        approval_batch=batch,
        approval_flags=(),
        decisions=(),
        extraction_failures={},
        addon_proposal=AddOnProposal(
            eligible=False,
            reason="No optional or donation items were found.",
            items=(),
        ),
    )


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
            "Binder — substitution",
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
            "Dividers — substitution",
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

    result = _pipeline_result(
        session=PipelineSession(
            session_id="approval-test",
            children=("grade5",),
            budget_total=10_000,
            fulfillment_pref="pickup",
            tax_basis_points=0,
        ),
        needs=(need,),
        matches=matches,
        optimization=optimization,
        batch=batch,
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
    assert presentation.options[0].purchase_price_cents == (
        current_offer.pack_price
    )
    assert presentation.options[1].purchase_price_cents == (
        alternative_offer.pack_price
    )
    assert presentation.options[1].explanation is None
    assert presentation.options[-1].label == (
        "Source this item myself — no purchase in this cart"
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


def test_approval_confirmation_records_only_the_visible_selection() -> None:
    """FR-27: cart-stage approval records the selected product, not edits."""

    state: dict[str, object] = {"selection": "catalog-choice"}

    app._approval_confirm_selection(
        state,
        "confirmed-selection",
        "selection",
    )

    assert state == {
        "selection": "catalog-choice",
        "confirmed-selection": "catalog-choice",
    }


def test_substitution_removal_keeps_internal_delta_but_shows_no_purchase() -> None:
    """FR-28: internal repricing stays exact while the parent sees no purchase."""

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
        {"connector": "usb"},
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
        attributes={"connector": "3.5 mm"},
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
        if item.kind == "major_substitution"
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

    result = _pipeline_result(
        session=PipelineSession(
            session_id="approval-headphones",
            children=("grade2", "grade5"),
            budget_total=15_000,
            fulfillment_pref="delivery",
            tax_basis_points=700,
        ),
        needs=needs,
        matches=matches,
        optimization=optimization,
        batch=batch,
    )
    presentation = app.build_approval_presentations(
        result,
        offers,
        stores,
        {"grade2": "Grade 2", "grade5": "Grade 5"},
    )[0]

    assert presentation.heading == "Headphones — substitution"
    assert presentation.affected_children == ("Grade 2", "Grade 5")
    assert (
        "The list asks for usb connector; this option has 3.5 mm connector. "
        "Is that acceptable?"
    ) in presentation.message
    assert tuple(
        option.cost_delta_cents for option in presentation.options
    ) == (0, -3_101)
    assert presentation.options[1].label == (
        "Source this item myself — no purchase in this cart"
    )
    assert presentation.options[1].purchase_price_cents is None
    assert app.approval_option_label(presentation.options[1]).casefold().count(
        "no purchase in this cart"
    ) == 1
    assert presentation.options[1].explanation == (
        "No other stocked catalog match is available. No product will be "
        "purchased for this item in this cart."
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
    assert "major_substitution" not in visible_text

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
    self_sourced = app._self_sourced_decisions(
        (presentation,),
        outcomes,
    )
    assert len(self_sourced) == 1
    assert self_sourced[0].presentation is presentation
    assert self_sourced[0].item_name == "Headphones"
    assert self_sourced[0].affected_children == ("Grade 2", "Grade 5")
    summary = app.build_text_summary(
        result,
        adjusted,
        matches,
        stores,
        {"grade2": "Grade 2", "grade5": "Grade 5"},
        {
            presentation.heading: presentation.options[1].label,
        },
        self_sourced,
        (),
    )
    assert "STATUS: REQUIRED ITEMS OR LISTS ARE MISSING" in summary
    assert "ITEMS YOU CHOSE TO SOURCE YOURSELF" in summary
    assert "Headphones | Grade 2 and Grade 5" in summary
    assert "UNFULFILLED BY PARENT CHOICE" in summary
    assert "TOTAL COST: $22.08" in summary
    assert "\\$" not in summary
    decision_log = DecisionLog("parent-self-source")
    decision_log.record_approval_response(
        presentation.options[1].label,
        affected_lines=presentation.interrupt.affected_lines,
    )
    assert decision_log.entries[0].actor == "parent"
    assert "Source this item myself" in decision_log.entries[0].rationale


def test_radio_option_uses_escaped_label_and_attached_caption() -> None:
    """Streamlit receives separate escaped radio labels and captions."""

    option = app.ApprovalDisplayOption(
        alternative_id="binder-two",
        label="Choose Avery 2-Inch Binder — Value Depot",
        cost_delta_cents=300,
        purchase_price_cents=520,
    )

    label = app.approval_option_label(option)
    caption = app.approval_option_caption(option)

    assert label == "Choose Avery 2-Inch Binder — Value Depot — \\$5.20"
    assert caption == "Alternative."
    assert "$" not in (label + caption).replace("\\$", "")


def test_self_source_option_uses_the_same_spacing_as_other_options() -> None:
    """Parent-sourcing uses captions rather than a horizontal separator."""

    option = app.ApprovalDisplayOption(
        alternative_id="binder-parent-remove",
        label="Do not buy this — I will source it myself",
        cost_delta_cents=-300,
        explanation="No exact catalog match is available. Saves $3.00.",
        leaves_required_unmet=True,
    )

    label = app.approval_option_label(option)
    caption = app.approval_option_caption(option)

    assert label.startswith("Do not buy this")
    assert "────────" not in label
    assert caption.startswith("Source-it-yourself choice")
    assert "Saves \\$3.00" in caption


def test_budget_interrupt_has_ranked_item_choices_and_applies_selection() -> None:
    """BR-04: an item-specific budget choice rebuilds the effective cart."""

    stores = (_store("VALUE", "Value Depot"),)
    headphones = _need(
        "headphones",
        1,
        {"grade2": 1},
        {},
        "grade2:headphones",
    )
    pens = _need(
        "pens",
        1,
        {"grade5": 1},
        {"acceptable_colors": ("blue",)},
        "grade5:pens",
    )
    headphone_offer = _offer(
        "HEADPHONES",
        "VALUE",
        "Classroom Headphones",
        "headphones",
        1,
        500,
    )
    exact_pens = _offer(
        "BLUE-PENS",
        "VALUE",
        "Blue Ballpoint Pens",
        "pens",
        1,
        500,
        attributes={"ink_color": "blue"},
    )
    cheaper_substitution = _offer(
        "RED-PENS",
        "VALUE",
        "Red Ballpoint Pens",
        "pens",
        1,
        300,
        attributes={"ink_color": "red"},
    )
    needs = (headphones, pens)
    offers = (headphone_offer, exact_pens, cheaper_substitution)
    config = OptimizationConfig(
        shopping_mode="budget",
        budget_cents=850,
        fulfillment_preference="pickup",
        tax_basis_points=0,
    )
    matches, optimization, batch = _approval_fixture(
        needs,
        offers,
        stores,
        config,
    )

    assert optimization.landed_cost == 1_000
    assert optimization.shortfall_cents == 150
    assert tuple(interrupt.kind for interrupt in batch.interrupts) == (
        "budget_exceeded",
    )

    result = _pipeline_result(
        session=PipelineSession(
            session_id="tight-budget",
            children=("grade2", "grade5"),
            budget_total=850,
            fulfillment_pref="pickup",
            tax_basis_points=0,
        ),
        needs=needs,
        matches=matches,
        optimization=optimization,
        batch=batch,
    )
    presentation = app.build_approval_presentations(
        result,
        offers,
        stores,
        {"grade2": "Grade 2", "grade5": "Grade 5"},
    )[0]

    assert presentation.affected_children == ("Grade 2", "Grade 5")
    assert "Minimum achievable total cost: $10.00." in presentation.message
    assert "Shortfall: $1.50." in presentation.message
    assert (
        "1. Headphones for Grade 2 — $5.00 marginal total-cost contribution."
        in presentation.message
    )
    assert (
        "Red Ballpoint Pens from Value Depot, saving $2.00 from total"
        in presentation.message
    )
    assert sum(
        option.is_recommended for option in presentation.options
    ) == 1
    recommended = next(
        option
        for option in presentation.options
        if option.is_recommended
    )
    assert recommended.label == "Raise the budget by $1.50"
    assert recommended.leaves_required_unmet is False
    assert app.approval_default_index(presentation.options) == 0
    assert sum(
        "Recommended." in app.approval_option_caption(option)
        for option in presentation.options
    ) == 1

    cheaper = next(
        option
        for option in presentation.options
        if option.sku == "RED-PENS"
    )
    assert cheaper.cost_delta_cents == -200
    assert cheaper.source_requirement_ids == ("grade5:pens",)
    assert app.approval_option_label(cheaper).endswith("\\$3.00")

    self_source = next(
        option
        for option in presentation.options
        if (
            option.leaves_required_unmet
            and option.item_name == "Headphones"
        )
    )
    assert "Do not buy Headphones for Grade 2" in self_source.label
    assert self_source.cost_delta_cents == -500
    assert self_source.source_requirement_ids == ("grade2:headphones",)
    assert presentation.options[-1].leaves_required_unmet is True
    assert all(
        not option.leaves_required_unmet
        for option in presentation.options[
            : next(
                index
                for index, option in enumerate(presentation.options)
                if option.leaves_required_unmet
            )
        ]
    )
    over_budget_summary = app.build_text_summary(
        result,
        optimization,
        matches,
        stores,
        {"grade2": "Grade 2", "grade5": "Grade 5"},
        {presentation.heading: recommended.label},
        (),
        (),
    )
    assert over_budget_summary.splitlines()[1] == (
        "BUDGET SHORTFALL: $1.50"
    )

    outcomes = {
        presentation.interrupt.interrupt_id: self_source.alternative_id
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
    assert adjusted.landed_cost == 500
    assert adjusted.shortfall_cents == 0
    assert tuple(
        line.canonical_item for line in adjusted.plan.lines
    ) == ("pens",)

    self_sourced = app._self_sourced_decisions(
        (presentation,),
        outcomes,
    )
    assert len(self_sourced) == 1
    assert self_sourced[0].item_name == "Headphones"
    assert self_sourced[0].affected_children == ("Grade 2",)
    summary = app.build_text_summary(
        result,
        adjusted,
        matches,
        stores,
        {"grade2": "Grade 2", "grade5": "Grade 5"},
        {presentation.heading: self_source.label},
        self_sourced,
        (),
    )
    summary_lines = summary.splitlines()
    assert summary_lines[1] == "BUDGET REMAINING: $3.50"
    assert "Headphones | Grade 2 | UNFULFILLED BY PARENT CHOICE" in summary
    assert "TOTAL COST: $5.00" in summary


def test_raise_budget_choice_funds_cart_and_clears_shortfall() -> None:
    """BR-04: parent authorization changes the budget, not only the outcome."""

    stores = (_store("VALUE", "Value Depot"),)
    need = _need(
        "headphones",
        1,
        {"grade2": 1},
        {},
        "grade2:headphones",
    )
    offers = (
        _offer(
            "HEADPHONES",
            "VALUE",
            "Classroom Headphones",
            "headphones",
            1,
            1_000,
        ),
    )
    config = OptimizationConfig(
        shopping_mode="budget",
        budget_cents=850,
        fulfillment_preference="pickup",
        tax_basis_points=0,
    )
    matches, optimization, batch = _approval_fixture(
        (need,),
        offers,
        stores,
        config,
    )
    result = _pipeline_result(
        session=PipelineSession(
            session_id="raise-budget",
            children=("grade2",),
            budget_total=850,
            fulfillment_pref="pickup",
            tax_basis_points=0,
        ),
        needs=(need,),
        matches=matches,
        optimization=optimization,
        batch=batch,
    )
    presentation = app.build_approval_presentations(
        result,
        offers,
        stores,
        {"grade2": "Grade 2"},
    )[0]
    raise_option = next(
        option
        for option in presentation.options
        if option.alternative_id.endswith("-raise")
    )
    assert raise_option.label == "Raise the budget by $1.50"
    assert app.budget_increase_was_selected(
        (presentation,),
        {presentation.interrupt.interrupt_id: raise_option},
    )

    decision_log = DecisionLog("raise-budget-parent")
    funded_result, funded_cart = app.authorize_budget_increase(
        result,
        optimization,
        decision_log,
    )

    assert funded_result.session.budget_total == 1_000
    assert funded_result.proposed_cart.budget_cents == 1_000
    assert funded_result.proposed_cart.within_budget is True
    assert funded_result.proposed_cart.shortfall_cents == 0
    assert funded_cart.budget_cents == 1_000
    assert funded_cart.within_budget is True
    assert funded_cart.shortfall_cents == 0
    assert len(decision_log.entries) == 1
    assert decision_log.entries[0].type == "budget_action"
    assert decision_log.entries[0].actor == "parent"
    assert "850 cents to 1000 cents" in decision_log.entries[0].rationale
    summary = app.build_text_summary(
        funded_result,
        funded_cart,
        matches,
        stores,
        {"grade2": "Grade 2"},
        {presentation.heading: raise_option.label},
        (),
        decision_log.entries,
    )
    assert summary.splitlines()[1] == "BUDGET REMAINING: $0.00"
    assert "BUDGET SHORTFALL" not in summary


@pytest.mark.parametrize(
    "kind",
    (
        "major_substitution",
        "brand_lock_break",
        "attribute_choice",
        "low_confidence",
    ),
)
def test_each_non_budget_interrupt_marks_one_safe_recommendation(
    kind: str,
) -> None:
    """FR-26: every interrupt defaults to one covered recommendation."""

    stores = (_store("VALUE", "Value Depot"),)
    need = _need(
        "pencils",
        1,
        {"grade2": 1},
        {},
        "grade2:pencils",
    )
    offer = _offer(
        "PENCILS",
        "VALUE",
        "Classroom Pencils",
        "pencils",
        1,
        500,
    )
    config = OptimizationConfig(
        shopping_mode="budget",
        budget_cents=1_000,
        fulfillment_preference="pickup",
        tax_basis_points=0,
    )
    matches = match_offers((need,), (offer,), stores)
    optimization = optimize_cart(
        (need,),
        (offer,),
        stores,
        config,
        candidate_skus_by_need=matches.candidate_skus_by_need,
    )
    interrupt = ApprovalInterrupt(
        interrupt_id=f"approval-{kind}",
        kind=kind,  # type: ignore[arg-type]
        message="Constructed approval.",
        recommendation="Keep the covered item.",
        alternatives=(
            ApprovalAlternative(
                alternative_id=f"approval-{kind}-approve",
                label="Approve the recommended product",
                cost_delta_cents=0,
            ),
            ApprovalAlternative(
                alternative_id=f"approval-{kind}-omit",
                label="Parent chooses not to buy pencils",
                cost_delta_cents=-500,
            ),
        ),
        cost_impact_cents=500,
        affected_lines=(optimization.plan.lines[0].line_id,),
        source_requirement_ids=need.source_requirement_ids,
        sku=offer.sku,
    )
    result = _pipeline_result(
        session=PipelineSession(
            session_id=f"recommendation-{kind}",
            children=("grade2",),
            budget_total=1_000,
            fulfillment_pref="pickup",
            tax_basis_points=0,
        ),
        needs=(need,),
        matches=matches,
        optimization=optimization,
        batch=ApprovalBatch(
            interrupts=(interrupt,),
            raw_interrupt_count=1,
        ),
    )

    presentation = app.build_approval_presentations(
        result,
        (offer,),
        stores,
        {"grade2": "Grade 2"},
    )[0]
    recommended_options = tuple(
        option
        for option in presentation.options
        if option.is_recommended
    )

    assert presentation.affected_children == ("Grade 2",)
    assert app._join_names(presentation.affected_children) == "Grade 2"
    assert len(recommended_options) == 1
    assert recommended_options[0].leaves_required_unmet is False
    assert (
        presentation.options[
            app.approval_default_index(presentation.options)
        ]
        is recommended_options[0]
    )
    assert sum(
        "Recommended." in app.approval_option_caption(option)
        for option in presentation.options
    ) == 1


def test_budget_omission_resolves_and_reactivates_headphones_interrupt() -> None:
    """A current budget omission cannot coexist with a hidden Keep decision."""

    stores = (_store("VALUE", "Value Depot"),)
    needs = (
        _need(
            "headphones",
            1,
            {"grade2": 1},
            {"connector": "usb"},
            "grade2:headphones",
        ),
        _need(
            "pencils",
            1,
            {"grade2": 1},
            {},
            "grade2:pencils",
        ),
    )
    offers = (
        _offer(
            "HEADPHONES",
            "VALUE",
            "Classroom Headphones",
            "headphones",
            1,
            2_000,
            is_returnable=False,
            attributes={"connector": "3.5 mm"},
        ),
        _offer(
            "PENCILS",
            "VALUE",
            "Classroom Pencils",
            "pencils",
            1,
            500,
        ),
    )
    config = OptimizationConfig(
        shopping_mode="budget",
        budget_cents=1_000,
        fulfillment_preference="pickup",
        tax_basis_points=0,
    )
    matches, optimization, batch = _approval_fixture(
        needs,
        offers,
        stores,
        config,
    )
    analysis = build_budget_analysis(
        optimization,
        matches,
        needs,
        offers,
        stores,
        config,
    )
    assert analysis is not None
    result = replace(
        _pipeline_result(
            session=PipelineSession(
                session_id="linked-interrupts",
                children=("grade2",),
                budget_total=1_000,
                fulfillment_pref="pickup",
                tax_basis_points=0,
            ),
            needs=needs,
            matches=matches,
            optimization=optimization,
            batch=batch,
        ),
        budget_analysis=analysis,
    )
    presentations = app.build_approval_presentations(
        result,
        offers,
        stores,
        {"grade2": "Grade 2"},
    )
    headphones = next(
        presentation
        for presentation in presentations
        if presentation.interrupt.kind == "major_substitution"
    )
    keep = next(
        option for option in headphones.options if option.is_recommended
    )
    omission_id = next(
        action.action_id
        for action in analysis.omission_actions
        if action.canonical_item == "headphones"
    )
    requested_outcomes = {
        headphones.interrupt.interrupt_id: keep.alternative_id
    }
    budget_saving, _ = app._evaluate_budget_action_margin(
        result,
        (),
        analysis.actions_by_id[omission_id],
        offers,
        stores,
    )
    current = app._apply_approval_outcomes(
        optimization,
        matches,
        needs,
        presentations,
        requested_outcomes,
        offers,
        stores,
        config,
        budget_analysis=analysis,
    )
    repriced_headphones = app._reprice_approval_presentation(
        headphones,
        result,
        presentations,
        requested_outcomes,
        (),
        current,
        offers,
        stores,
    )
    headphones_removal = next(
        option
        for option in repriced_headphones.options
        if option.leaves_required_unmet
    )
    assert budget_saving == abs(
        headphones_removal.cost_delta_cents
    )

    resolved = app.reconcile_interrupt_selections(
        presentations,
        analysis,
        (omission_id,),
        requested_outcomes,
        offers,
    )
    assert headphones.interrupt.interrupt_id in resolved.resolutions
    assert headphones.interrupt.interrupt_id not in resolved.active_outcomes
    assert resolved.resolutions[
        headphones.interrupt.interrupt_id
    ].message == (
        "Resolved by your budget choice — headphones will not be purchased."
    )

    reactivated = app.reconcile_interrupt_selections(
        presentations,
        analysis,
        (),
        requested_outcomes,
        offers,
    )
    assert reactivated.resolutions == {}
    assert reactivated.active_outcomes == requested_outcomes

    submitted = app._apply_approval_outcomes(
        optimization,
        matches,
        needs,
        presentations,
        resolved.active_outcomes,
        offers,
        stores,
        config,
        budget_analysis=analysis,
        budget_action_ids=(omission_id,),
    )
    assert tuple(
        line.canonical_item for line in submitted.plan.lines
    ) == ("pencils",)
    assert app.approval_selection_contradictions(
        submitted,
        presentations,
        resolved.active_outcomes,
    ) == ()
    assert app.approval_selection_contradictions(
        submitted,
        presentations,
        requested_outcomes,
    ) == (headphones.interrupt.interrupt_id,)


def test_approval_choices_apply_br06_before_forcing_one_sku() -> None:
    """BR-06: a forced approval SKU cannot invent an only-option exception."""

    stores = (_store("VALUE", "Value Depot"),)
    need = _need(
        "pencils",
        5,
        {"grade2": 5},
        {},
        "grade2:pencils",
    )
    offers = (
        _offer(
            "PACK-5",
            "VALUE",
            "Five Pencils",
            "pencils",
            5,
            500,
        ),
        _offer(
            "PACK-48",
            "VALUE",
            "Forty-Eight Pencils",
            "pencils",
            48,
            100,
        ),
    )
    config = OptimizationConfig(
        shopping_mode="budget",
        fulfillment_preference="pickup",
        tax_basis_points=0,
    )
    matches = match_offers((need,), offers, stores)
    optimization = optimize_cart(
        (need,),
        offers,
        stores,
        config,
        candidate_skus_by_need=matches.candidate_skus_by_need,
    )
    interrupt = ApprovalInterrupt(
        interrupt_id="overage-choice",
        kind="major_substitution",
        message="Choose",
        recommendation="Keep",
        alternatives=(),
        cost_impact_cents=0,
        affected_lines=(optimization.plan.lines[0].line_id,),
        source_requirement_ids=need.source_requirement_ids,
        sku=optimization.plan.lines[0].sku,
    )

    choices = build_catalog_approval_choices(
        interrupt,
        optimization,
        matches,
        (need,),
        offers,
        stores,
        config,
    )
    assert tuple(choice.sku for choice in choices) == ("PACK-5",)

    only_large_matches = match_offers(
        (need,),
        (offers[1],),
        stores,
    )
    only_large_optimization = optimize_cart(
        (need,),
        (offers[1],),
        stores,
        config,
        candidate_skus_by_need=(
            only_large_matches.candidate_skus_by_need
        ),
    )
    only_large_interrupt = replace(
        interrupt,
        affected_lines=(
            only_large_optimization.plan.lines[0].line_id,
        ),
        sku="PACK-48",
    )
    only_large_choices = build_catalog_approval_choices(
        only_large_interrupt,
        only_large_optimization,
        only_large_matches,
        (need,),
        (offers[1],),
        stores,
        config,
    )
    assert tuple(choice.sku for choice in only_large_choices) == (
        "PACK-48",
    )

    binder_need = _need(
        "binders",
        1,
        {"grade5": 1},
        {"size": 1.5},
        "grade5:binders",
    )
    binder_offers = (
        _offer(
            "BINDER-ONE",
            "VALUE",
            "Single Binder",
            "binders",
            1,
            300,
            attributes={"capacity_inches": 1},
        ),
        _offer(
            "BINDER-FOUR",
            "VALUE",
            "Binders, 4 Pack",
            "binders",
            4,
            1_000,
            attributes={"capacity_inches": 1},
        ),
    )
    binder_matches = match_offers(
        (binder_need,),
        binder_offers,
        stores,
    )
    binder_optimization = optimize_cart(
        (binder_need,),
        binder_offers,
        stores,
        config,
        candidate_skus_by_need=binder_matches.candidate_skus_by_need,
    )
    binder_interrupt = replace(
        interrupt,
        affected_lines=(binder_optimization.plan.lines[0].line_id,),
        source_requirement_ids=binder_need.source_requirement_ids,
        sku=binder_optimization.plan.lines[0].sku,
    )
    binder_choices = build_catalog_approval_choices(
        binder_interrupt,
        binder_optimization,
        binder_matches,
        (binder_need,),
        binder_offers,
        stores,
        config,
    )
    assert tuple(choice.sku for choice in binder_choices) == (
        "BINDER-ONE",
        "BINDER-FOUR",
    )


def test_attribute_equivalent_approval_options_collapse_to_cheapest() -> None:
    """FR-28: one cheapest binder per size stays visible with exact matches."""

    stores = (_store("VALUE", "Value Depot"),)
    need = _need(
        "binders",
        1,
        {"grade5": 1},
        {"size": 1.5},
        "grade5:binders",
    )
    offers = (
        _offer(
            "EXACT-15",
            "VALUE",
            "Exact 1.5-Inch Binder",
            "binders",
            1,
            400,
            attributes={"capacity_inches": 1.5},
        ),
        _offer(
            "ONE-CHEAP",
            "VALUE",
            "Value 1-Inch Binder",
            "binders",
            1,
            240,
            attributes={"capacity_inches": 1},
        ),
        _offer(
            "ONE-MID",
            "VALUE",
            "Mid 1-Inch Binder",
            "binders",
            1,
            349,
            attributes={"capacity_inches": 1},
        ),
        _offer(
            "ONE-PREMIUM",
            "VALUE",
            "Premium 1-Inch Binder",
            "binders",
            1,
            599,
            attributes={"capacity_inches": 1},
        ),
        _offer(
            "TWO",
            "VALUE",
            "Durable 2-Inch Binder",
            "binders",
            1,
            520,
            attributes={"capacity_inches": 2},
        ),
    )
    config = OptimizationConfig(
        shopping_mode="budget",
        fulfillment_preference="pickup",
        tax_basis_points=0,
    )
    matches = match_offers((need,), offers, stores)
    optimization = optimize_cart(
        (need,),
        offers,
        stores,
        config,
        candidate_skus_by_need=matches.candidate_skus_by_need,
    )
    interrupt = ApprovalInterrupt(
        interrupt_id="binder-size",
        kind="major_substitution",
        message="Choose a binder size",
        recommendation="Keep the exact binder",
        alternatives=(),
        cost_impact_cents=0,
        affected_lines=(optimization.plan.lines[0].line_id,),
        source_requirement_ids=need.source_requirement_ids,
        sku=optimization.plan.lines[0].sku,
    )
    result = _pipeline_result(
        session=PipelineSession(
            session_id="group-binders",
            children=("grade5",),
            budget_total=10_000,
        ),
        needs=(need,),
        matches=matches,
        optimization=optimization,
        batch=ApprovalBatch(
            interrupts=(interrupt,),
            raw_interrupt_count=1,
        ),
    )
    presentation = app.build_approval_presentations(
        result,
        offers,
        stores,
        {"grade5": "Grade 5"},
    )[0]

    primary, other = app.group_approval_options(
        result,
        presentation,
        offers,
    )
    assert tuple(option.sku for option in primary) == (
        "EXACT-15",
        "ONE-CHEAP",
        "TWO",
    )
    assert tuple(option.sku for option in other) == (
        "ONE-MID",
        "ONE-PREMIUM",
    )


def test_tier_one_strategy_maps_to_its_exact_tier_two_actions() -> None:
    """The recommended whole plan and its pre-ticked boxes have one result."""

    stores = (_store("VALUE", "Value Depot"),)
    needs = (
        _need(
            "headphones",
            1,
            {"grade2": 1},
            {},
            "grade2:headphones",
        ),
        _need(
            "pencils",
            1,
            {"grade2": 1},
            {},
            "grade2:pencils",
        ),
    )
    offers = (
        _offer(
            "HEADPHONES",
            "VALUE",
            "Headphones",
            "headphones",
            1,
            1_000,
        ),
        _offer(
            "PENCILS",
            "VALUE",
            "Pencils",
            "pencils",
            1,
            500,
        ),
    )
    config = OptimizationConfig(
        shopping_mode="budget",
        budget_cents=700,
        fulfillment_preference="pickup",
        tax_basis_points=0,
    )
    matches, optimization, _ = _approval_fixture(
        needs,
        offers,
        stores,
        config,
    )
    analysis = build_budget_analysis(
        optimization,
        matches,
        needs,
        offers,
        stores,
        config,
    )
    assert analysis is not None
    assert analysis.recommended_plan is not None
    strategy = app.ApprovalDisplayOption(
        alternative_id=analysis.recommended_plan.plan_id,
        label="Recommended plan",
        cost_delta_cents=0,
        budget_action_ids=analysis.recommended_plan.action_ids,
    )
    checkbox_values = app.budget_strategy_checkbox_values(
        strategy,
        analysis.actions,
    )
    selected_ids = tuple(
        action.action_id
        for action in analysis.actions
        if checkbox_values[action.action_id]
    )
    evaluation = evaluate_budget_actions(
        analysis,
        selected_ids,
        optimization,
        matches,
        needs,
        offers,
        stores,
        config,
    )

    assert selected_ids == analysis.recommended_plan.action_ids
    assert evaluation.landed_cost_cents == (
        analysis.recommended_plan.resulting_landed_cost_cents
    )


def test_ineligible_addons_render_no_empty_heading() -> None:
    """BR-05: an above-threshold add-on proposal is entirely hidden."""

    stores = (_store("VALUE", "Value Depot"),)
    need = _need(
        "pencils",
        1,
        {"grade2": 1},
        {},
        "grade2:pencils",
    )
    offer = _offer(
        "PENCILS",
        "VALUE",
        "Classroom Pencils",
        "pencils",
        1,
        500,
    )
    config = OptimizationConfig(
        shopping_mode="budget",
        budget_cents=500,
        fulfillment_preference="pickup",
        tax_basis_points=0,
    )
    matches, optimization, batch = _approval_fixture(
        (need,),
        (offer,),
        stores,
        config,
    )
    result = replace(
        _pipeline_result(
            session=PipelineSession(
                session_id="no-addon-heading",
                children=("grade2",),
                budget_total=500,
            ),
            needs=(need,),
            matches=matches,
            optimization=optimization,
            batch=batch,
        ),
        addon_proposal=AddOnProposal(
            eligible=False,
            reason="The required-item cart is above the threshold.",
            items=(
                AddOnItem(
                    requirement_id="grade2:tissues",
                    child_id="grade2",
                    raw_text="Optional tissues",
                    requirement_type="donation",
                    canonical_item="tissues",
                    quantity=1,
                ),
            ),
        ),
    )

    class NoHeadingStreamlit:
        def __init__(self) -> None:
            self.session_state = {"include_addons": True}

        def subheader(self, value: str) -> None:
            raise AssertionError(f"Unexpected heading: {value}")

    st = NoHeadingStreamlit()

    app._render_addons(st, result, {"grade2": "Grade 2"})

    assert st.session_state["include_addons"] is False
