"""Model-free tests for deterministic requirement normalization."""

from agent.normalize import (
    canonicalize_item_name,
    normalize_requirement,
    normalize_requirements,
)
from agent.schema import Requirement


def _requirement(
    raw_text: str,
    canonical_item: str,
    quantity: int,
    *,
    req_id: str = "req-1",
    quantity_is_range: bool = False,
    quantity_max: int | None = None,
    unit_type: str = "each",
    is_required: bool = True,
    is_purchasable: bool = True,
    requirement_type: str = "required",
    attributes: (
        dict[str, str | int | float | bool | list[str] | tuple[str, ...] | None]
        | None
    ) = None,
    extraction_confidence: float = 1.0,
) -> Requirement:
    return Requirement(
        req_id=req_id,
        child_id="child-a",
        raw_text=raw_text,
        canonical_item=canonical_item,
        quantity=quantity,
        quantity_is_range=quantity_is_range,
        quantity_max=quantity_max,
        unit_type=unit_type,  # type: ignore[arg-type]
        brand_lock=None,
        exclusions=(),
        is_required=is_required,
        is_purchasable=is_purchasable,
        requirement_type=requirement_type,  # type: ignore[arg-type]
        attributes=attributes or {},
        extraction_confidence=extraction_confidence,
    )


def test_canonical_item_aliases_resolve_to_allowlist_names() -> None:
    """Canonicalization maps ordinary list wording deterministically."""

    assert canonicalize_item_name("#2 pencils") == "pencils"
    assert canonicalize_item_name("glue stick") == "glue_sticks"
    assert canonicalize_item_name("wide ruled notebook paper") == (
        "notebook_paper"
    )


def test_e01_quantity_range_uses_minimum_and_preserves_maximum() -> None:
    """E-01: 2–3 boxes resolves to 2 while retaining 3 for later economics."""

    normalized = normalize_requirement(
        _requirement(
            "2-3 boxes of tissues",
            "tissues",
            2,
            quantity_is_range=True,
            quantity_max=3,
            unit_type="box",
        )
    )

    assert normalized.quantity == 2
    assert normalized.quantity_max == 3
    assert normalized.unit_type == "each"
    assert normalized.attributes["normalized_container_unit"] == "box"
    assert "quantity_range_minimum_selected" in normalized.assumption_flags


def test_e02_missing_pencil_pack_count_uses_flagged_standard_size() -> None:
    """E-02: one unspecified pencil pack becomes 12 pencils with a flag."""

    normalized = normalize_requirement(
        _requirement(
            "1 pack of pencils",
            "pencils",
            1,
            unit_type="pack",
        )
    )

    assert normalized.quantity == 12
    assert normalized.unit_type == "each"
    assert normalized.attributes["count"] == 12
    assert "standard_pack_count_assumed:12" in normalized.assumption_flags


def test_explicit_container_count_converts_to_individual_units() -> None:
    """Two boxes of 24 crayons normalize to exactly 48 crayons."""

    normalized = normalize_requirement(
        _requirement(
            "2 boxes of crayons, 24 count",
            "crayons",
            2,
            unit_type="box",
            attributes={"count": 24},
        )
    )

    assert normalized.quantity == 48
    assert normalized.unit_type == "each"
    assert normalized.attributes["count"] == 24


def test_e02_missing_notebook_paper_count_sets_assumption_flag() -> None:
    """E-02: paper stays one catalog pack and records assumed sheet contents."""

    normalized = normalize_requirement(
        _requirement(
            "1 pack wide-ruled notebook paper",
            "notebook_paper",
            1,
            unit_type="pack",
            attributes={"ruling": "wide"},
        )
    )

    assert normalized.quantity == 1
    assert normalized.unit_type == "each"
    assert normalized.attributes["count"] == 150
    assert normalized.attributes["normalized_container_unit"] == "pack"
    assert "standard_pack_count_assumed:150" in normalized.assumption_flags


def test_color_alternatives_are_stored_as_acceptable_values() -> None:
    """FR-19: black or blue remains two equally acceptable exact matches."""

    source = _requirement(
        "12 black or blue pens",
        "pens",
        12,
        attributes={"acceptable_colors": ["black", "blue", "BLACK"]},
    )
    normalized = normalize_requirement(source)

    assert source.attributes.acceptable_colors == ("black", "blue")
    assert normalized.attributes["acceptable_colors"] == ("black", "blue")
    assert "color" not in source.attributes.model_dump()


def test_e17_ream_converts_to_sheets_without_model_judgment() -> None:
    """E-17: one paper ream deterministically becomes 500 sheets."""

    normalized = normalize_requirement(
        _requirement(
            "1 ream of notebook paper",
            "notebook_paper",
            1,
            unit_type="ream",
        )
    )

    assert normalized.quantity == 500
    assert normalized.unit_type == "each"
    assert normalized.attributes["normalized_unit"] == "sheet"
    assert normalized.attributes["sheets_per_ream"] == 500
    assert "ream_converted_to_sheets:500" in normalized.assumption_flags


def test_e06_e07_nonpurchasable_lines_remain_display_only() -> None:
    """Fees and labeling instructions stay visible but never enter cart scope."""

    fee = _requirement(
        "Classroom activity fee: $25",
        "non_purchasable",
        0,
        req_id="fee",
        is_purchasable=False,
    )
    instruction = _requirement(
        "Label all supplies",
        "non_purchasable",
        0,
        req_id="label",
        is_purchasable=False,
    )

    result = normalize_requirements([fee, instruction])

    assert len(result.requirements) == 2
    assert len(result.cart_requirements) == 0
    assert len(result.display_only_requirements) == 2
    assert {
        item.source.raw_text for item in result.display_only_requirements
    } == {"Classroom activity fee: $25", "Label all supplies"}
    assert all(
        item.canonical_item == "non_purchasable"
        for item in result.display_only_requirements
    )


def test_optional_and_donation_items_stay_out_of_base_budget() -> None:
    """FR-09: optional items remain available as add-ons, not base needs."""

    optional = _requirement(
        "Optional tissues",
        "tissues",
        1,
        req_id="optional",
        is_required=False,
        requirement_type="optional",
    )
    donation = _requirement(
        "Donation wipes",
        "disinfecting_wipes",
        1,
        req_id="donation",
        is_required=False,
        requirement_type="donation",
    )

    result = normalize_requirements([optional, donation])

    assert len(result.cart_requirements) == 2
    assert len(result.budget_requirements) == 0
    assert all(item.is_cart_eligible for item in result.cart_requirements)


def test_low_confidence_add_on_review_is_deferred_until_selected() -> None:
    """BR-10: non-required uncertainty does not interrupt the base cart."""

    donation = _requirement(
        "Donation wipes",
        "disinfecting_wipes",
        1,
        req_id="donation",
        is_required=False,
        requirement_type="donation",
        extraction_confidence=0.69,
    )
    result = normalize_requirements([donation])

    assert result.manual_review_requirements == ()
    assert tuple(
        item.source.req_id for item in result.deferred_review_requirements
    ) == ("donation",)
    assert result.review_requirements_for() == ()
    assert tuple(
        item.source.req_id
        for item in result.review_requirements_for({"donation"})
    ) == ("donation",)


def test_low_confidence_required_item_still_requires_immediate_review() -> None:
    """FR-12: required-item confidence gating is unaffected."""

    required = _requirement(
        "1 pair scissors",
        "scissors",
        1,
        extraction_confidence=0.69,
    )
    result = normalize_requirements([required])

    assert len(result.manual_review_requirements) == 1
    assert result.deferred_review_requirements == ()


def test_low_confidence_display_only_line_never_interrupts_cart() -> None:
    """FR-10: uncertain non-purchasable text remains display-only."""

    instruction = _requirement(
        "Label everything",
        "non_purchasable",
        0,
        is_purchasable=False,
        extraction_confidence=0.0,
    )
    normalized = normalize_requirement(instruction)

    assert normalized.is_display_only is True
    assert normalized.manual_review_required is False
    assert normalized.review_deferred is False
    assert "category_not_allowed" not in normalized.assumption_flags


def test_any_color_creates_no_attribute_restriction() -> None:
    """FR-19: 'any color' cannot become a preference-dependent choice."""

    requirement = _requirement(
        "2 highlighters, any color",
        "highlighters",
        2,
        attributes={"acceptable_colors": ["any color"]},
    )

    assert requirement.attributes.acceptable_colors == ()


def test_disallowed_category_is_flagged_and_excluded_from_cart() -> None:
    """Defense 3: a laptop cannot enter cart scope through normalization."""

    normalized = normalize_requirement(
        _requirement("1 laptop", "laptop", 1)
    )

    assert normalized.quantity == 1
    assert normalized.is_cart_eligible is False
    assert normalized.is_display_only is True
    assert normalized.manual_review_required is True
    assert "category_not_allowed" in normalized.assumption_flags
