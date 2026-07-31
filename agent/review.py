"""Deterministic organization and confirmation of extracted supply items."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from agent.rules import (
    AMBIGUOUS_UNNAMED_BRAND_REQUIREMENT_ISSUE,
    CLEAR_EXTRACTION_CONFIDENCE,
    CONFIDENCE_FLOOR,
    COUNT_BASED_CATEGORIES,
    ITEM_FULFILLMENT_PREFERENCE_DEFAULT,
    LOW_CONFIDENCE_IDENTITY_ISSUE,
    LOW_CONFIDENCE_OTHER_DETAILS_ISSUE,
    LOW_CONFIDENCE_QUANTITY_ISSUE,
    NONPAGINATED_SOURCE_PAGE,
    PACKAGE_QUANTITY_STATE_DEFAULT,
    STANDARD_CONTAINER_CONTENT_COUNTS,
    STANDARD_PACK_COUNTS,
    SYSTEM_DECISION_PARENT_CONFIRMED_PRODUCT_IDENTITY,
    SYSTEM_DECISION_PARENT_CONFIRMED_QUANTITY,
    SYSTEM_DECISION_PARENT_REMOVED_MERGED_ITEM,
    unnamed_brand_requirement_needs_review,
)
from agent.schema import (
    ExtractionEnvelope,
    Requirement,
    RequirementAttributes,
    SupplyItemReview,
)


@dataclass(frozen=True)
class ConditionalReviewOption:
    """One parent-facing answer for a conditional supply question."""

    value: str
    label: str


@dataclass(frozen=True)
class ConditionalReviewQuestion:
    """One conditional question, possibly controlling several item branches."""

    question_id: str
    child_id: str
    prompt: str
    options: tuple[ConditionalReviewOption, ...]
    selected_value: str | None


@dataclass(frozen=True)
class DeduplicatedConditionalQuestion:
    """One repeated conditional decision shared across child lists."""

    group_id: str
    prompt: str
    child_ids: tuple[str, ...]
    option_labels: tuple[str, ...]
    questions: tuple[ConditionalReviewQuestion, ...]
    selected_label: str | None


@dataclass(frozen=True)
class ReviewFlagGroup:
    """One plain-language uncertainty confirmation shared by matching rows."""

    group_id: str
    child_ids: tuple[str, ...]
    row_ids: tuple[str, ...]
    representative_id: str
    messages: tuple[str, ...]


@dataclass(frozen=True)
class TeacherNoteGroup:
    """One non-purchasable source note and every child it affects."""

    source_text: str
    child_ids: tuple[str, ...]


def confidence_band(confidence: float) -> str:
    """Replace model-score false precision with a parent-facing band."""

    if confidence < float(CONFIDENCE_FLOOR):
        return "uncertain"
    if confidence < float(CLEAR_EXTRACTION_CONFIDENCE):
        return "worth checking"
    return "clear"


def _quantity_phrase(quantity: int | None, unit: str) -> str:
    """Return a concise quantity-and-unit phrase for an explanation."""

    if quantity is None:
        return "a usable quantity"
    unit_label = {
        "each": "item",
        "pack": "pack",
        "box": "box",
        "ream": "ream",
    }.get(unit, unit)
    if quantity != 1:
        unit_label += "es" if unit_label.endswith("x") else "s"
    return f"{quantity} {unit_label}"


def _range_phrase(lower: int, upper: int, unit: str) -> str:
    """Return a compact range such as `2–3 boxes`."""

    upper_phrase = _quantity_phrase(upper, unit)
    upper_unit = upper_phrase.split(" ", 1)[1]
    return f"{lower}–{upper} {upper_unit}"


def _assumed_package_unit(item_name: str) -> str:
    """Name the units parents expect inside an inferred package."""

    return {
        "notebook_paper": "sheets",
        "cardstock": "sheets",
        "tissues": "tissues",
        "pencils": "pencils",
        "colored_pencils": "colored pencils",
        "crayons": "crayons",
        "markers": "markers",
        "dry_erase_markers": "markers",
        "permanent_markers": "markers",
        "pens": "pens",
        "highlighters": "highlighters",
        "erasers": "erasers",
        "glue_sticks": "glue sticks",
        "sticky_notes": "pads",
    }.get(item_name, "items")


def review_issue_explanations(
    row: SupplyItemReview,
) -> tuple[str, ...]:
    """Translate review flags into concrete parent-facing explanations."""

    messages: list[str] = []
    for issue in row.issue_codes:
        if issue == "conditional_item":
            continue
        if issue == "missing_quantity":
            messages.append(
                "The list did not give a usable quantity."
            )
        elif issue == "low_confidence":
            messages.append(
                "The original line may be unclear. Compare it with the source "
                "shown here."
            )
        elif issue == LOW_CONFIDENCE_QUANTITY_ISSUE:
            messages.append(
                "The quantity may be unclear. Compare it with the source "
                "shown here."
            )
        elif issue == LOW_CONFIDENCE_IDENTITY_ISSUE:
            messages.append(
                "The item or its details may be unclear. The quantity was "
                "confirmed by you."
            )
        elif issue == LOW_CONFIDENCE_OTHER_DETAILS_ISSUE:
            messages.append(
                "Other details on the original line may be unclear. The item "
                "and quantity were confirmed by you."
            )
        elif issue == "quantity_range":
            if (
                row.required_quantity is not None
                and row.quantity_max is not None
            ):
                messages.append(
                    "The list gave a range of "
                    f"{_range_phrase(row.required_quantity, row.quantity_max, row.unit)}. "
                    f"We chose {row.required_quantity}."
                )
            else:
                messages.append(
                    "The list gave a quantity range. We used its lower end."
                )
        elif issue == "ambiguous_package_size":
            assumed_count = (
                row.package_size
                if row.package_quantity_state == "assumed"
                else (
                    STANDARD_PACK_COUNTS.get(row.item_name)
                    or STANDARD_CONTAINER_CONTENT_COUNTS.get(row.item_name)
                    if row.package_quantity_state == "unspecified"
                    else None
                )
            )
            if assumed_count is None:
                messages.append(
                    "The list did not say how many items were in the package."
                )
            else:
                messages.append(
                    "The list did not say how many "
                    f"{_assumed_package_unit(row.item_name)} were in the "
                    f"package. We assumed {assumed_count}."
                )
        elif issue == "ambiguous_item":
            messages.append(
                "The item name could not be interpreted clearly."
            )
        elif issue == AMBIGUOUS_UNNAMED_BRAND_REQUIREMENT_ISSUE:
            messages.append(
                "The list says not to substitute, but it does not name a "
                "brand. Check what must stay exact."
            )
        else:
            messages.append(
                issue.replace("_", " ").capitalize() + "."
            )
    return tuple(dict.fromkeys(messages))


def review_flag_groups(
    rows: Iterable[SupplyItemReview],
) -> tuple[ReviewFlagGroup, ...]:
    """Deduplicate identical uncertainty questions across child lists."""

    grouped: dict[tuple[object, ...], list[SupplyItemReview]] = {}
    for row in rows:
        messages = review_issue_explanations(row)
        if (
            not messages
            or not row.is_purchasable
            or row.provided_by_school
            or row.review_status == "deleted"
        ):
            continue
        signature: tuple[object, ...] = (
            row.item_name,
            row.required_quantity,
            row.unit,
            row.package_size,
            row.package_quantity_state,
            row.brand,
            row.brand_required,
            row.size,
            row.color,
            tuple(
                sorted(
                    (key, repr(value))
                    for key, value in row.required_attributes.items()
                )
            ),
            row.exclusions,
            row.optional,
            row.supply_scope,
            messages,
        )
        grouped.setdefault(signature, []).append(row)

    groups: list[ReviewFlagGroup] = []
    for members in grouped.values():
        identity = "\x1f".join(
            sorted(row.review_id for row in members)
        )
        group_id = (
            "review-flag-"
            + hashlib.sha256(identity.encode("utf-8")).hexdigest()
        )
        groups.append(
            ReviewFlagGroup(
                group_id=group_id,
                child_ids=tuple(
                    dict.fromkeys(row.child_id for row in members)
                ),
                row_ids=tuple(row.review_id for row in members),
                representative_id=members[0].review_id,
                messages=review_issue_explanations(members[0]),
            )
        )
    return tuple(groups)


def unhandled_review_flag_groups(
    rows: Iterable[SupplyItemReview],
    flag_groups: Iterable[ReviewFlagGroup],
    acknowledged_group_ids: Iterable[str] = (),
) -> tuple[ReviewFlagGroup, ...]:
    """Return the single source for marked-item and summary decision counts."""

    rows_by_id = {row.review_id: row for row in rows}
    acknowledged = frozenset(acknowledged_group_ids)
    return tuple(
        group
        for group in flag_groups
        if group.group_id not in acknowledged
        and not all(
            rows_by_id[row_id].review_status == "confirmed"
            for row_id in group.row_ids
            if row_id in rows_by_id
        )
    )


def teacher_note_groups(
    rows: Iterable[SupplyItemReview],
) -> tuple[TeacherNoteGroup, ...]:
    """Deduplicate non-purchasable teacher directions across children."""

    grouped: dict[str, list[SupplyItemReview]] = {}
    original_text: dict[str, str] = {}
    for row in rows:
        if (
            row.is_purchasable
            or row.provided_by_school
            or row.condition is not None
            or row.review_status == "deleted"
        ):
            continue
        signature = " ".join(row.source_text.casefold().split())
        grouped.setdefault(signature, []).append(row)
        original_text.setdefault(signature, row.source_text)
    return tuple(
        TeacherNoteGroup(
            source_text=original_text[signature],
            child_ids=tuple(
                dict.fromkeys(row.child_id for row in members)
            ),
        )
        for signature, members in grouped.items()
    )


def apply_review_confirmations(
    rows: Iterable[SupplyItemReview],
    flag_groups: Iterable[ReviewFlagGroup],
    confirmed_group_ids: Iterable[str],
) -> tuple[SupplyItemReview, ...]:
    """Accept clear rows by default and require confirmation only for flags."""

    confirmed_ids = frozenset(confirmed_group_ids)
    group_by_row_id = {
        row_id: group
        for group in flag_groups
        for row_id in group.row_ids
    }
    updated: list[SupplyItemReview] = []
    for row in rows:
        if row.review_status == "deleted":
            updated.append(row)
            continue
        group = group_by_row_id.get(row.review_id)
        if group is None:
            review_status = "confirmed"
        else:
            review_status = (
                "confirmed"
                if group.group_id in confirmed_ids
                else "pending"
            )
        updated.append(
            row.model_copy(update={"review_status": review_status})
        )
    return tuple(updated)


def _review_issues(requirement: Requirement) -> tuple[str, ...]:
    """Return deterministic review flags for one extracted item (FR-12)."""

    issues: list[str] = []
    if requirement.quantity < 1:
        issues.append("missing_quantity")
    if requirement.extraction_confidence < float(CONFIDENCE_FLOOR):
        identity_confirmed = (
            SYSTEM_DECISION_PARENT_CONFIRMED_PRODUCT_IDENTITY
            in requirement.system_decisions
        )
        quantity_confirmed = (
            SYSTEM_DECISION_PARENT_CONFIRMED_QUANTITY
            in requirement.system_decisions
        )
        issues.append(
            LOW_CONFIDENCE_OTHER_DETAILS_ISSUE
            if identity_confirmed and quantity_confirmed
            else LOW_CONFIDENCE_QUANTITY_ISSUE
            if identity_confirmed
            else LOW_CONFIDENCE_IDENTITY_ISSUE
            if quantity_confirmed
            else "low_confidence"
        )
    if requirement.quantity_is_range:
        issues.append("quantity_range")
    if (
        requirement.unit_type in {"pack", "box"}
        and (
            requirement.canonical_item in COUNT_BASED_CATEGORIES
            or requirement.canonical_item
            in STANDARD_CONTAINER_CONTENT_COUNTS
        )
    ):
        if requirement.attributes.count is None:
            issues.append("ambiguous_package_size")
    if requirement.is_purchasable and not requirement.canonical_item:
        issues.append("ambiguous_item")
    if unnamed_brand_requirement_needs_review(requirement.raw_text):
        issues.append(AMBIGUOUS_UNNAMED_BRAND_REQUIREMENT_ISSUE)
    if (
        requirement.condition is not None
        and requirement.condition_applies is None
    ):
        issues.append("conditional_item")
    return tuple(issues)


def _review_package_quantity(
    requirement: Requirement,
) -> tuple[int | None, str]:
    """Expose E-02's deterministic assumption in its editable data field."""

    explicit = requirement.attributes.count
    if explicit is not None:
        return explicit, "specified"
    if requirement.unit_type not in {"pack", "box"}:
        return None, PACKAGE_QUANTITY_STATE_DEFAULT
    assumed = (
        STANDARD_PACK_COUNTS.get(requirement.canonical_item)
        or STANDARD_CONTAINER_CONTENT_COUNTS.get(requirement.canonical_item)
    )
    if assumed is None:
        return None, PACKAGE_QUANTITY_STATE_DEFAULT
    return assumed, "assumed"


def organize_extractions(
    extractions: dict[str, ExtractionEnvelope],
) -> tuple[SupplyItemReview, ...]:
    """Create stable, sorted review rows without model calls (FR-07–FR-12)."""

    rows: list[SupplyItemReview] = []
    for child_id in sorted(extractions):
        for requirement in extractions[child_id].requirements:
            package_size, package_quantity_state = _review_package_quantity(
                requirement
            )
            rows.append(
                SupplyItemReview(
                    review_id=(
                        f"{requirement.child_id}:{requirement.req_id}"
                    ),
                    req_id=requirement.req_id,
                    child_id=requirement.child_id,
                    item_name=requirement.canonical_item,
                    required_quantity=(
                        requirement.quantity
                        if requirement.quantity > 0
                        else None
                    ),
                    quantity_is_range=requirement.quantity_is_range,
                    quantity_max=requirement.quantity_max,
                    unit=requirement.unit_type,
                    package_size=package_size,
                    package_quantity_state=package_quantity_state,
                    item_fulfillment_preference=(
                        requirement.item_fulfillment_preference
                    ),
                    brand=(
                        requirement.brand_lock or requirement.brand_hint
                    ),
                    brand_hint=requirement.brand_hint,
                    brand_required=requirement.brand_lock is not None,
                    size=requirement.attributes.size,
                    color=requirement.attributes.acceptable_colors,
                    material=requirement.attributes.material,
                    required_attributes=requirement.attributes.model_dump(
                        exclude_none=True,
                        exclude={
                            "acceptable_colors",
                            "count",
                            "size",
                            "material",
                        },
                    ),
                    exclusions=requirement.exclusions,
                    optional=not requirement.is_required,
                    is_purchasable=requirement.is_purchasable,
                    supply_scope=requirement.supply_scope,
                    ambiguous_descriptors=(
                        requirement.ambiguous_descriptors
                    ),
                    provided_by_school=requirement.provided_by_school,
                    condition=requirement.condition,
                    condition_applies=requirement.condition_applies,
                    condition_group_id=requirement.condition_group_id,
                    condition_question=requirement.condition_question,
                    condition_option=requirement.condition_option,
                    source_document=requirement.source_document,
                    source_section=requirement.source_section,
                    source_page=requirement.source_page,
                    source_language=requirement.source_language,
                    sources=requirement.sources,
                    variant_sources=requirement.variant_sources,
                    product_variant_id=requirement.product_variant_id,
                    system_decisions=requirement.system_decisions,
                    source_text=requirement.raw_text,
                    confidence=requirement.extraction_confidence,
                    review_status=(
                        "deleted"
                        if (
                            SYSTEM_DECISION_PARENT_REMOVED_MERGED_ITEM
                            in requirement.system_decisions
                        )
                        else "pending"
                    ),
                    already_owned=False,
                    allow_equivalents=requirement.brand_lock is None,
                    issue_codes=_review_issues(requirement),
                )
            )
    return tuple(
        sorted(
            rows,
            key=lambda row: (
                row.child_id.casefold(),
                row.item_name.casefold(),
                row.source_text.casefold(),
                row.review_id,
            ),
        )
    )


def conditional_review_questions(
    rows: Iterable[SupplyItemReview],
) -> tuple[ConditionalReviewQuestion, ...]:
    """Build one parent question per mutually exclusive condition group."""

    active = tuple(
        row
        for row in rows
        if row.review_status != "deleted" and not row.already_owned
    )
    grouped: dict[str, list[SupplyItemReview]] = {}
    standalone: list[SupplyItemReview] = []
    for row in active:
        if row.condition is None:
            continue
        if row.condition_group_id is None:
            standalone.append(row)
            continue
        grouped.setdefault(row.condition_group_id, []).append(row)

    questions: list[ConditionalReviewQuestion] = []
    for group_id, branches in grouped.items():
        if len(branches) < 2:
            standalone.extend(branches)
            continue
        ordered = sorted(
            branches,
            key=lambda row: (
                (row.condition or "").casefold(),
                (row.condition_option or "").casefold(),
                row.review_id,
            ),
        )
        selected = [
            row.review_id for row in ordered if row.condition_applies is True
        ]
        questions.append(
            ConditionalReviewQuestion(
                question_id=group_id,
                child_id=ordered[0].child_id,
                prompt=(
                    ordered[0].condition_question
                    or "Which conditional item applies?"
                ),
                options=tuple(
                    ConditionalReviewOption(
                        value=row.review_id,
                        label=(
                            row.condition_option
                            or row.condition
                            or row.source_text
                        ),
                    )
                    for row in ordered
                ),
                selected_value=selected[0] if len(selected) == 1 else None,
            )
        )

    for row in standalone:
        questions.append(
            ConditionalReviewQuestion(
                question_id=f"condition:{row.review_id}",
                child_id=row.child_id,
                prompt=f'Does this apply: "{row.condition}"?',
                options=(
                    ConditionalReviewOption(value="yes", label="Yes"),
                    ConditionalReviewOption(value="no", label="No"),
                ),
                selected_value=(
                    "yes"
                    if row.condition_applies is True
                    else "no" if row.condition_applies is False else None
                ),
            )
        )
    return tuple(
        sorted(
            questions,
            key=lambda question: (
                question.child_id.casefold(),
                question.prompt.casefold(),
                question.question_id,
            ),
        )
    )


def deduplicate_conditional_questions(
    questions: Iterable[ConditionalReviewQuestion],
) -> tuple[DeduplicatedConditionalQuestion, ...]:
    """Ask identical conditional questions once across child lists."""

    grouped: dict[
        tuple[str, tuple[str, ...]],
        list[ConditionalReviewQuestion],
    ] = {}
    for question in questions:
        signature = (
            question.prompt.casefold(),
            tuple(
                option.label.casefold()
                for option in question.options
            ),
        )
        grouped.setdefault(signature, []).append(question)

    deduplicated: list[DeduplicatedConditionalQuestion] = []
    for index, members in enumerate(grouped.values(), start=1):
        selected_labels: list[str] = []
        for question in members:
            selected = next(
                (
                    option.label
                    for option in question.options
                    if option.value == question.selected_value
                ),
                None,
            )
            if selected is not None:
                selected_labels.append(selected)
        selected_label = (
            selected_labels[0]
            if selected_labels
            and len(set(selected_labels)) == 1
            else None
        )
        deduplicated.append(
            DeduplicatedConditionalQuestion(
                group_id=f"conditional-review-{index}",
                prompt=members[0].prompt,
                child_ids=tuple(
                    dict.fromkeys(
                        question.child_id for question in members
                    )
                ),
                option_labels=tuple(
                    option.label for option in members[0].options
                ),
                questions=tuple(members),
                selected_label=selected_label,
            )
        )
    return tuple(deduplicated)


def conditional_answers_for_selection(
    group: DeduplicatedConditionalQuestion,
    selected_label: str | None,
) -> dict[str, str | None]:
    """Expand one shared parent answer back to every source-list question."""

    answers: dict[str, str | None] = {}
    for question in group.questions:
        answers[question.question_id] = next(
            (
                option.value
                for option in question.options
                if option.label == selected_label
            ),
            None,
        )
    return answers


def apply_conditional_answers(
    rows: Iterable[SupplyItemReview],
    answers: Mapping[str, str | None],
) -> tuple[SupplyItemReview, ...]:
    """Apply one answer per question and only one branch per condition group."""

    updated: list[SupplyItemReview] = []
    for row in rows:
        question_id = (
            row.condition_group_id
            if row.condition_group_id is not None
            else f"condition:{row.review_id}"
        )
        answer = answers.get(question_id)
        if row.condition is None or answer is None:
            updated.append(row)
            continue
        applies = (
            answer == row.review_id
            if row.condition_group_id is not None
            else answer == "yes"
        )
        updated.append(
            row.model_copy(
                update={
                    "condition_applies": applies,
                    "is_purchasable": (
                        not row.provided_by_school if applies else False
                    ),
                }
            )
        )
    return tuple(updated)


def validate_mutually_exclusive_condition_groups(
    rows: Iterable[SupplyItemReview],
) -> None:
    """Reject unresolved or contradictory mutually exclusive item branches."""

    grouped: dict[str, list[SupplyItemReview]] = {}
    for row in rows:
        if (
            row.condition_group_id is not None
            and row.review_status != "deleted"
            and not row.already_owned
        ):
            grouped.setdefault(row.condition_group_id, []).append(row)
    for branches in grouped.values():
        selected = sum(
            row.condition_applies is True for row in branches
        )
        if selected != 1:
            question = (
                branches[0].condition_question
                or "Choose exactly one conditional item."
            )
            raise ValueError(question)


def unresolved_required_items(
    rows: Iterable[SupplyItemReview],
) -> tuple[SupplyItemReview, ...]:
    """Return active required rows that are not ready for planning."""

    return tuple(
        row
        for row in rows
        if not row.optional
        and row.is_purchasable
        and not row.already_owned
        and not row.provided_by_school
        and row.review_status != "deleted"
        and (
            row.review_status != "confirmed"
            or row.required_quantity is None
            or (
                row.condition is not None
                and row.condition_applies is None
            )
        )
    )


def confirmed_requirements(
    rows: Iterable[SupplyItemReview],
    *,
    allow_unresolved: bool = False,
) -> tuple[Requirement, ...]:
    """Convert only user-confirmed active rows to the cart contract (FR-12)."""

    active_rows = tuple(
        row
        for row in rows
        if row.review_status != "deleted" and not row.already_owned
    )
    validate_mutually_exclusive_condition_groups(active_rows)
    unresolved = unresolved_required_items(active_rows)
    if unresolved and not allow_unresolved:
        raise ValueError(
            "Required items remain unresolved: "
            + ", ".join(row.item_name for row in unresolved)
        )

    confirmed: list[Requirement] = []
    for row in active_rows:
        preserve_display_row = (
            not row.is_purchasable
            or row.provided_by_school
            or (
                row.condition is not None
                and row.condition_applies is False
            )
        )
        if (
            row.review_status != "confirmed"
            and not allow_unresolved
            and not preserve_display_row
        ):
            continue
        if row.required_quantity is None:
            if not allow_unresolved:
                continue
            quantity = 1
        else:
            quantity = row.required_quantity
        excluded_by_condition = (
            row.condition is not None
            and row.condition_applies is False
        )
        is_purchasable = (
            row.is_purchasable
            and not row.provided_by_school
            and not excluded_by_condition
        )
        is_required = (
            is_purchasable
            and not row.optional
        )
        attributes = dict(row.required_attributes)
        attributes.update(
            {
                "acceptable_colors": row.color,
                "count": (
                    row.package_size
                    if row.package_quantity_state != "unspecified"
                    else None
                ),
                "size": row.size,
                "material": row.material,
            }
        )
        confirmed_requirement = Requirement(
                req_id=row.req_id,
                child_id=row.child_id,
                raw_text=row.source_text,
                canonical_item=row.item_name,
                quantity=quantity,
                quantity_is_range=row.quantity_is_range,
                quantity_max=row.quantity_max,
                unit_type=row.unit,
                brand_lock=None,
                brand_hint=row.brand if not row.brand_required else row.brand_hint,
                exclusions=row.exclusions,
                is_required=is_required,
                is_purchasable=is_purchasable,
                requirement_type=(
                    "required" if is_required else "optional"
                ),
                supply_scope=row.supply_scope,
                package_quantity_state=row.package_quantity_state,
                item_fulfillment_preference=(
                    row.item_fulfillment_preference
                    or ITEM_FULFILLMENT_PREFERENCE_DEFAULT
                ),
                ambiguous_descriptors=row.ambiguous_descriptors,
                provided_by_school=row.provided_by_school,
                condition=row.condition,
                condition_applies=row.condition_applies,
                condition_group_id=row.condition_group_id,
                condition_question=row.condition_question,
                condition_option=row.condition_option,
                source_document=row.source_document,
                source_section=row.source_section,
                source_page=row.source_page or NONPAGINATED_SOURCE_PAGE,
                source_language=row.source_language,
                sources=row.sources,
                variant_sources=row.variant_sources,
                product_variant_id=row.product_variant_id,
                system_decisions=(),
                attributes=RequirementAttributes(),
                extraction_confidence=row.confidence,
            )
        confirmed.append(
            confirmed_requirement.model_copy(
                update={
                    "brand_lock": (
                        row.brand if row.brand_required else None
                    ),
                    "attributes": RequirementAttributes.model_validate(
                        attributes
                    ),
                    "system_decisions": row.system_decisions,
                }
            )
        )
    return tuple(confirmed)


def reviewed_envelopes(
    original: dict[str, ExtractionEnvelope],
    rows: Iterable[SupplyItemReview],
    *,
    allow_unresolved: bool = False,
) -> dict[str, ExtractionEnvelope]:
    """Rebuild extraction envelopes from confirmed review rows."""

    requirements = confirmed_requirements(
        rows,
        allow_unresolved=allow_unresolved,
    )
    by_child: dict[str, list[Requirement]] = {
        child_id: [] for child_id in original
    }
    for requirement in requirements:
        by_child.setdefault(requirement.child_id, []).append(requirement)
    return {
        child_id: ExtractionEnvelope(
            stated_grades=envelope.stated_grades,
            stated_teachers=envelope.stated_teachers,
            requirements=tuple(by_child.get(child_id, ())),
            document_selection=envelope.document_selection,
            uninterpreted_lines=envelope.uninterpreted_lines,
            skipped_lines=envelope.skipped_lines,
            catalog_unavailable_items=envelope.catalog_unavailable_items,
        )
        for child_id, envelope in original.items()
    }
