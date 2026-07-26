"""Presentation-option tests that leave the seven-condition gate unchanged."""

from dataclasses import replace

import pytest

import app
from agent.addons import AddOnItem, AddOnProposal
from agent.aggregate import UnitNeed
from agent.approval_options import (
    build_catalog_approval_choices,
    removal_cost_context,
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
    assert "Minimum achievable landed cost: $10.00." in presentation.message
    assert "Shortfall: $1.50." in presentation.message
    assert (
        "1. Headphones for Grade 2 — $5.00 marginal landed contribution."
        in presentation.message
    )
    assert (
        "Red Ballpoint Pens from Value Depot, saving $2.00 landed"
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
    assert "saves \\$2.00" in app.approval_option_label(cheaper)

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
    assert "LANDED COST: $5.00" in summary


@pytest.mark.parametrize(
    "kind",
    (
        "major_substitution",
        "brand_lock_break",
        "attribute_choice",
        "non_returnable_threshold",
        "low_confidence",
        "required_unavailable",
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
