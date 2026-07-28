"""Deterministic document-section resolution for the list intake screen."""

from __future__ import annotations

from dataclasses import dataclass

from agent.rules import (
    SECTION_MATCHING_GRADE_ACTION,
    SECTION_OTHER_GRADE_ACTION,
    SECTION_TRANSLATED_DUPLICATE_ACTION,
    SECTION_WITHOUT_GRADE_ACTION,
    choose_primary_document_language,
    document_section_action,
    section_is_in_primary_language,
)
from agent.schema import (
    DocumentSection,
    DocumentSelection,
    DocumentStructureEnvelope,
)


def build_document_selection(
    structure: DocumentStructureEnvelope,
    selected_section_ids: tuple[str, ...],
) -> DocumentSelection:
    """Validate parent-selected sections and name every ignored section."""

    sections_by_id = {
        section.section_id: section for section in structure.sections
    }
    unknown = tuple(
        section_id
        for section_id in selected_section_ids
        if section_id not in sections_by_id
    )
    if unknown:
        raise ValueError(
            "Unknown document section selection: " + ", ".join(unknown)
        )
    selected = tuple(
        sections_by_id[section_id] for section_id in selected_section_ids
    )
    ignored = tuple(
        section
        for section in structure.sections
        if section.section_id not in selected_section_ids
    )
    return DocumentSelection(
        selected_section_ids=selected_section_ids,
        selected_section_labels=tuple(
            section.label for section in selected
        ),
        selected_page_numbers=tuple(
            sorted(
                {
                    page_number
                    for section in selected
                    for page_number in section.page_numbers
                }
            )
        ),
        selected_column_labels=tuple(
            section.column_label
            for section in selected
            if section.column_label is not None
        ),
        selected_named_sections=tuple(
            dict.fromkeys(
                named_section
                for section in selected
                for named_section in section.named_sections
            )
        ),
        ignored_section_ids=tuple(
            section.section_id for section in ignored
        ),
        ignored_section_labels=tuple(
            section.label for section in ignored
        ),
    )


@dataclass(frozen=True)
class SectionResolution:
    """One student's BR-14 through BR-18 document-scope outcome."""

    student_grade: str
    primary_language: str | None
    auto_selected: tuple[DocumentSection, ...]
    parent_questions: tuple[DocumentSection, ...]
    other_grade_sections: tuple[DocumentSection, ...]
    translated_duplicates: tuple[DocumentSection, ...]
    covered_grades: tuple[str, ...]
    primary_language_sections: tuple[DocumentSection, ...]
    has_primary_language_source: bool

    @property
    def has_grade_match(self) -> bool:
        """Return whether BR-14 resolved at least one section."""

        return bool(self.auto_selected)

    @property
    def needs_parent_screen(self) -> bool:
        """Show the screen for multi-section, unresolved, or blocked documents."""

        return (
            not self.has_primary_language_source
            or not self.has_grade_match
            or bool(self.parent_questions)
            or len(self.primary_language_sections) > 1
        )

    @property
    def translated_provenance(
        self,
    ) -> tuple[tuple[DocumentSection, DocumentSection | None], ...]:
        """Attach each BR-16 duplicate to its source-language original."""

        originals_by_id = {
            section.section_id: section
            for section in self.primary_language_sections
        }
        return tuple(
            (
                duplicate,
                originals_by_id.get(
                    duplicate.duplicate_of_section_id or ""
                ),
            )
            for duplicate in self.translated_duplicates
        )


@dataclass(frozen=True)
class ResolvedSectionChoice:
    """Single source of truth for the statement and submitted selection."""

    resolution: SectionResolution
    selected_section_ids: tuple[str, ...]
    selected_section_labels: tuple[str, ...]
    manually_overridden: bool = False

    @property
    def can_continue(self) -> bool:
        """BR-18 forbids extraction with no selected source-language section."""

        return bool(self.selected_section_ids)


def primary_document_language(
    structure: DocumentStructureEnvelope,
) -> str | None:
    """Choose the model-named primary language or BR-18's stable fallback."""

    return choose_primary_document_language(
        structure.primary_language,
        structure.languages,
        tuple(
            section.language or ""
            for section in structure.sections
            if section.duplicate_of_section_id is None
        ),
    )


def resolve_document_sections(
    structure: DocumentStructureEnvelope,
    student_grade: str,
) -> SectionResolution:
    """Apply BR-14 through BR-18 to a production structure envelope."""

    primary_language = primary_document_language(structure)
    originals = tuple(
        section
        for section in structure.sections
        if section.duplicate_of_section_id is None
    )
    primary_sections = tuple(
        section
        for section in originals
        if section_is_in_primary_language(
            section.language,
            primary_language,
        )
    )
    translated: list[DocumentSection] = []
    selected: list[DocumentSection] = []
    questions: list[DocumentSection] = []
    other_grades: list[DocumentSection] = []
    for section in structure.sections:
        action = document_section_action(
            student_grade,
            section.grades,
            translated_duplicate_of=section.duplicate_of_section_id,
        )
        if action == SECTION_TRANSLATED_DUPLICATE_ACTION:
            translated.append(section)
            continue
        if section not in primary_sections:
            continue
        if action == SECTION_MATCHING_GRADE_ACTION:
            selected.append(section)
        elif action == SECTION_WITHOUT_GRADE_ACTION:
            questions.append(section)
        elif action == SECTION_OTHER_GRADE_ACTION:
            other_grades.append(section)

    covered_grades = tuple(
        dict.fromkeys(
            grade
            for section in primary_sections
            for grade in section.grades
            if grade.strip()
        )
    )
    return SectionResolution(
        student_grade=student_grade,
        primary_language=primary_language,
        auto_selected=tuple(selected),
        parent_questions=tuple(questions),
        other_grade_sections=tuple(other_grades),
        translated_duplicates=tuple(translated),
        covered_grades=covered_grades,
        primary_language_sections=primary_sections,
        has_primary_language_source=bool(primary_sections),
    )


def build_resolved_section_choice(
    resolution: SectionResolution,
    *,
    selected_question_ids: tuple[str, ...] = (),
    override_section_ids: tuple[str, ...] | None = None,
) -> ResolvedSectionChoice:
    """Build the one state object used for explanation and submission."""

    if override_section_ids is None:
        selected_ids = tuple(
            dict.fromkeys(
                (
                    *(
                        section.section_id
                        for section in resolution.auto_selected
                    ),
                    *selected_question_ids,
                )
            )
        )
        manually_overridden = False
    else:
        selectable_ids = {
            section.section_id
            for section in resolution.primary_language_sections
        }
        selected_ids = tuple(
            section_id
            for section_id in override_section_ids
            if section_id in selectable_ids
        )
        manually_overridden = True
    labels_by_id = {
        section.section_id: section.label
        for section in resolution.primary_language_sections
    }
    return ResolvedSectionChoice(
        resolution=resolution,
        selected_section_ids=selected_ids,
        selected_section_labels=tuple(
            labels_by_id[section_id]
            for section_id in selected_ids
            if section_id in labels_by_id
        ),
        manually_overridden=manually_overridden,
    )


def choice_to_document_selection(
    structure: DocumentStructureEnvelope,
    choice: ResolvedSectionChoice,
) -> DocumentSelection:
    """Validate the exact IDs described to the parent before extraction."""

    if not choice.can_continue:
        raise ValueError("Select a document section before continuing.")
    return build_document_selection(
        structure,
        choice.selected_section_ids,
    )
