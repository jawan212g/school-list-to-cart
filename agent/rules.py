"""Named business-rule constants from BRD Section 9.7."""

from decimal import Decimal


MINOR_SUBSTITUTION_TYPES = frozenset(
    {"different_unlocked_brand", "allowed_pack_size", "same_attributes"}
)  # BR-01: substitutions that do not require approval.
MAJOR_SUBSTITUTION_TYPES = frozenset(
    {
        "brand_lock_break",
        "pack_count_difference",
        "different_category",
        "attribute_change",
        "non_returnable_swap",
    }
)  # BR-01: substitutions that require approval.
MAJOR_PACK_DIFFERENCE_PERCENT = 20  # BR-01: pack-count approval threshold.
SUBSTITUTION_NONE = "none"  # BR-01: no substitution occurred.
SUBSTITUTION_MINOR = "minor"  # BR-01: substitution may proceed automatically.
SUBSTITUTION_MAJOR = "major"  # BR-01: substitution requires approval.

DEFAULT_TAX_BASIS_POINTS = 700  # BR-02: default tax rate is 7.0%.
BASIS_POINTS_DENOMINATOR = 10_000  # BR-02: integer tax-rate scale.
TAX_ROUNDING_METHOD = "half_up_to_nearest_cent"  # BR-02: fractional cents.
TAX_ROUNDING_OFFSET = BASIS_POINTS_DENOMINATOR // 2  # BR-02: half-up offset.

TOTAL_INCLUDES_TAX_AND_FEES = True  # BR-03: totals are always landed cost.

REQUIRED_ITEM_AUTO_DROP_ALLOWED = False  # BR-04: required items stay in the cart.

OPTIONAL_ITEMS_INCLUDED_BY_DEFAULT = False  # BR-05: optional items start excluded.
OPTIONAL_ITEM_HEADROOM_PERCENT = 90  # BR-05: add-ons appear at 90% of budget.

OVERAGE_PERCENT = 50  # BR-06: relative package overage ceiling.
PERCENT_DENOMINATOR = 100  # BR-06: integer percentage scale.
OVERAGE_ABSOLUTE_UNITS = 6  # BR-06: minimum absolute overage allowance.

ADDITIONAL_STORE_PENALTY_CENTS = 600  # BR-07: $6 per store after the first.
TRIP_PENALTY_SHOWN_IN_TOTAL = False  # BR-07: comparison-only penalty.

NON_RETURNABLE_APPROVAL_THRESHOLD_CENTS = 1_500  # BR-08: above $15.

SHARED_COST_ALLOCATION_METHOD = "proportional_by_units"  # BR-09.

INTERRUPT_TARGET_COUNT = 3  # BR-10: target approval-interrupt maximum.
INTERRUPT_DESIGN_FAILURE_COUNT = 6  # BR-10: more than six is a failure.

CONFIDENCE_FLOOR = Decimal("0.7")  # BR-11: extraction/match review threshold.
MAXIMUM_MATCH_CONFIDENCE = Decimal("1.0")  # FR-18: exact structured match.
MINIMUM_MATCH_CONFIDENCE = Decimal("0.0")  # FR-18: missing judgment is blocked.

CART_REVALIDATION_REQUIRED = True  # BR-12: revalidate before checkout.

DUPLICATE_SUPPRESSION_REQUIRED = True  # BR-13: combine identical needs.


ALLOWED_CATEGORIES = frozenset(
    {
        "pencils",
        "glue_sticks",
        "scissors",
        "crayons",
        "colored_pencils",
        "markers",
        "composition_notebooks",
        "spiral_notebooks",
        "notebook_paper",
        "binders",
        "dividers",
        "pens",
        "highlighters",
        "erasers",
        "pencil_boxes",
        "backpacks",
        "headphones",
        "rulers",
        "folders",
        "index_cards",
        "tissues",
        "disinfecting_wipes",
        "zip_top_bags",
        "cardstock",
        "hand_sanitizer",
    }
)

NON_PURCHASABLE_CATEGORY = "non_purchasable"
MAX_UPLOAD_BYTES = 10_000_000  # BRD 11.2: local upload size cap.

CANONICAL_ITEM_ALIASES = {
    "#2_pencil": "pencils",
    "#2_pencils": "pencils",
    "pencil": "pencils",
    "glue_stick": "glue_sticks",
    "scissor": "scissors",
    "pair_of_scissors": "scissors",
    "crayon": "crayons",
    "colored_pencil": "colored_pencils",
    "marker": "markers",
    "composition_notebook": "composition_notebooks",
    "spiral_notebook": "spiral_notebooks",
    "loose_leaf_paper": "notebook_paper",
    "wide_ruled_notebook_paper": "notebook_paper",
    "binder": "binders",
    "divider": "dividers",
    "pen": "pens",
    "highlighter": "highlighters",
    "eraser": "erasers",
    "pencil_box": "pencil_boxes",
    "backpack": "backpacks",
    "headphone": "headphones",
    "ruler": "rulers",
    "folder": "folders",
    "index_card": "index_cards",
    "tissue": "tissues",
    "disinfecting_wipe": "disinfecting_wipes",
    "zip_top_bag": "zip_top_bags",
    "zipper_bags": "zip_top_bags",
    "card_stock": "cardstock",
    "sanitizer": "hand_sanitizer",
}  # Deterministic canonical-name aliases for FR-11.

STANDARD_PACK_COUNTS = {
    "pencils": 12,
    "glue_sticks": 4,
    "crayons": 24,
    "colored_pencils": 12,
    "markers": 10,
    "composition_notebooks": 3,
    "spiral_notebooks": 3,
    "folders": 5,
    "pens": 12,
    "highlighters": 5,
    "erasers": 3,
}  # E-02: standard sizes used only when a count is omitted.

STANDARD_CONTAINER_CONTENT_COUNTS = {
    "notebook_paper": 150,
}  # E-02: assumed contents for catalog units sold as one container.

COUNT_BASED_CATEGORIES = frozenset(STANDARD_PACK_COUNTS)
PAPER_CATEGORIES = frozenset({"notebook_paper", "cardstock"})
REAM_SHEET_COUNT = 500  # E-17: one ream contains 500 sheets.

ATTRIBUTE_SENSITIVE_FIELDS = frozenset(
    {
        "acceptable_colors",
        "size",
        "ruling",
        "tab_count",
        "tip_style",
        "material",
        "style",
        "connector",
        "sharpened",
    }
)  # FR-19: changes to specified preference-sensitive attributes need approval.

CATEGORY_IMPLIED_EXCLUSION_TERMS = {
    "composition_notebooks": frozenset({"spiral"}),
}  # BR-13: category identity already excludes these alternatives.

CATEGORY_IMPLIED_ATTRIBUTE_TERMS = {
    "composition_notebooks": frozenset({"spiral"}),
}  # BR-13: redundant free-text attributes must not split identical needs.


def pack_count_difference_is_major(
    offered_count: int,
    requested_count: int,
) -> bool:
    """Return whether a pack-count difference exceeds BR-01's threshold."""

    if offered_count <= 0 or requested_count <= 0:
        raise ValueError("Pack counts must be positive")
    difference = abs(offered_count - requested_count)
    return (
        difference * PERCENT_DENOMINATOR
        > requested_count * MAJOR_PACK_DIFFERENCE_PERCENT
    )


def non_returnable_offer_requires_approval(
    is_returnable: bool,
    pack_price_cents: int,
) -> bool:
    """Apply BR-08 to a single offered package without cart arithmetic."""

    return (
        not is_returnable
        and pack_price_cents
        > NON_RETURNABLE_APPROVAL_THRESHOLD_CENTS
    )
