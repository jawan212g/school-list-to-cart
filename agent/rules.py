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

DEFAULT_TAX_BASIS_POINTS = 700  # BR-02: default tax rate is 7.0%.
BASIS_POINTS_DENOMINATOR = 10_000  # BR-02: integer tax-rate scale.

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
