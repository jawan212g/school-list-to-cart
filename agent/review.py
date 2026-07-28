"""Deterministic organization and confirmation of extracted supply items."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from agent.rules import CONFIDENCE_FLOOR
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


def _review_issues(requirement: Requirement) -> tuple[str, ...]:
    """Return deterministic review flags for one extracted item (FR-12)."""

    issues: list[str] = []
    if requirement.quantity < 1:
        issues.append("missing_quantity")
    if requirement.extraction_confidence < float(CONFIDENCE_FLOOR):
        issues.append("low_confidence")
    if requirement.quantity_is_range:
        issues.append("quantity_range")
    if requirement.unit_type in {"pack", "box"}:
        if requirement.attributes.count is None:
            issues.append("ambiguous_package_size")
    if requirement.is_purchasable and not requirement.canonical_item:
        issues.append("ambiguous_item")
    if (
        requirement.condition is not None
        and requirement.condition_applies is None
    ):
        issues.append("conditional_item")
    return tuple(issues)


def organize_extractions(
    extractions: dict[str, ExtractionEnvelope],
) -> tuple[SupplyItemReview, ...]:
    """Create stable, sorted review rows without model calls (FR-07–FR-12)."""

    rows = [
        SupplyItemReview(
            review_id=f"{requirement.child_id}:{requirement.req_id}",
            req_id=requirement.req_id,
            child_id=requirement.child_id,
            item_name=requirement.canonical_item,
            required_quantity=(
                requirement.quantity if requirement.quantity > 0 else None
            ),
            unit=requirement.unit_type,
            package_size=requirement.attributes.count,
            brand=requirement.brand_lock,
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
            optional=not requirement.is_required,
            is_purchasable=requirement.is_purchasable,
            supply_scope=requirement.supply_scope,
            provided_by_school=requirement.provided_by_school,
            condition=requirement.condition,
            condition_applies=requirement.condition_applies,
            condition_group_id=requirement.condition_group_id,
            condition_question=requirement.condition_question,
            condition_option=requirement.condition_option,
            source_section=requirement.source_section,
            source_page=requirement.source_page,
            source_language=requirement.source_language,
            notes=None,
            source_text=requirement.raw_text,
            confidence=requirement.extraction_confidence,
            review_status="pending",
            already_owned=False,
            allow_equivalents=requirement.brand_lock is None,
            issue_codes=_review_issues(requirement),
        )
        for child_id in sorted(extractions)
        for requirement in extractions[child_id].requirements
    ]
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
                "count": row.package_size,
                "size": row.size,
                "material": row.material,
            }
        )
        confirmed.append(
            Requirement(
                req_id=row.req_id,
                child_id=row.child_id,
                raw_text=row.source_text,
                canonical_item=row.item_name,
                quantity=quantity,
                unit_type=row.unit,
                brand_lock=(
                    row.brand if row.brand_required else None
                ),
                exclusions=(),
                is_required=is_required,
                is_purchasable=is_purchasable,
                requirement_type=(
                    "required" if is_required else "optional"
                ),
                supply_scope=row.supply_scope,
                provided_by_school=row.provided_by_school,
                condition=row.condition,
                condition_applies=row.condition_applies,
                condition_group_id=row.condition_group_id,
                condition_question=row.condition_question,
                condition_option=row.condition_option,
                source_section=row.source_section,
                source_page=row.source_page,
                source_language=row.source_language,
                attributes=RequirementAttributes.model_validate(attributes),
                extraction_confidence=row.confidence,
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
        )
        for child_id, envelope in original.items()
    }
