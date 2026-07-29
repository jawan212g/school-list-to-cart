"""Model-free tests for deterministic extraction security and review gating."""

import logging
import sys
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import httpx
import pytest
from openai import (
    APIConnectionError,
    AuthenticationError,
    BadRequestError,
    RateLimitError,
)

import agent.extract as extraction
from agent.extract import _apply_security_filters
from agent.schema import (
    DocumentSection,
    DocumentStructureEnvelope,
    ExtractionEnvelope,
    Requirement,
)
from agent.rules import VISION_MODEL_CALL_TIMEOUT_SECONDS


def test_small_model_prompt_requires_calibrated_evidence_only_output() -> None:
    """FR-09/FR-12/FR-13: the prompt addresses observed small-model defects."""

    instruction = extraction.SYSTEM_INSTRUCTION

    assert "1.0 only when" in instruction
    assert "0.65 or lower" in instruction
    assert "Any invented field, lost text, or guessed value" in instruction
    assert "quantity_max=null" in instruction
    assert "no mechanical pencils" in instruction
    assert 'requirement_type="donation"' in instruction
    assert 'neither character="#2" nor size="standard"' in instruction
    assert "never stop or truncate raw_text at a quote" in instruction
    assert "quart H-P" in instruction
    assert "one mutually exclusive set" in instruction
    assert "condition_group_id" in instruction
    assert "plain item name as" in instruction


def test_understood_out_of_catalog_item_keeps_source_evidence() -> None:
    """FR-12/E-36: rejected catalog categories remain visible to the parent."""

    envelope = ExtractionEnvelope(
        requirements=(
            Requirement(
                req_id="tape",
                child_id="model-child",
                raw_text="1 roll Scotch tape",
                canonical_item="tape",
                quantity=1,
                source_section="5th Grade",
                source_page=2,
                extraction_confidence=1.0,
            ),
        )
    )

    secured = _apply_security_filters(envelope, "child-1")

    assert secured.requirements == ()
    assert len(secured.catalog_unavailable_items) == 1
    unavailable = secured.catalog_unavailable_items[0]
    assert unavailable.child_id == "child-1"
    assert unavailable.item_name == "tape"
    assert unavailable.source_line == "1 roll Scotch tape"
    assert unavailable.section_name == "5th Grade"
    assert unavailable.page_number == 2


def test_last_name_bag_branches_are_grouped_deterministically() -> None:
    """All extracted last-name ranges become one mutually exclusive question."""

    model_output = ExtractionEnvelope(
        requirements=tuple(
            Requirement(
                req_id=req_id,
                child_id="model-child",
                raw_text=raw_text,
                canonical_item="zip_top_bags",
                quantity=1,
                condition=condition,
                source_section="Fourth Grade",
                source_page=2,
                extraction_confidence=1.0,
            )
            for req_id, raw_text, condition in (
                (
                    "gallon",
                    "Ziploc gallon | 4th: Last Name A-G",
                    "Last Name A-G",
                ),
                (
                    "quart",
                    "Ziploc quart | 4th: Last Name H-P",
                    "Last Name H-P",
                ),
                (
                    "sandwich",
                    "Ziploc sandwich | 4th: Last Name Q-Z",
                    "Last Name Q-Z",
                ),
            )
        )
    )

    secured = extraction.apply_extraction_security_filters(
        model_output,
        "child-1",
    )

    assert len(secured.requirements) == 3
    assert {
        requirement.condition_group_id
        for requirement in secured.requirements
    } == {"last-name:child-1:2:fourth-grade:zip_top_bags"}
    assert {
        requirement.condition_question
        for requirement in secured.requirements
    } == {"This list assigns bags by last name. Which applies?"}
    assert {
        requirement.condition_option
        for requirement in secured.requirements
    } == {
        "Ziploc gallon — Last Name A-G",
        "Ziploc quart — Last Name H-P",
        "Ziploc sandwich — Last Name Q-Z",
    }


def test_vision_extraction_uses_the_longer_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Rendered-page extraction receives the vision-specific request ceiling."""

    received: dict[str, object] = {}

    def fake_request(*args: object, **kwargs: object) -> ExtractionEnvelope:
        received.update(kwargs)
        return ExtractionEnvelope(
            requirements=(
                Requirement(
                    req_id="pencils",
                    child_id="child-1",
                    raw_text="12 pencils",
                    canonical_item="pencils",
                    quantity=12,
                    extraction_confidence=1.0,
                ),
            )
        )

    monkeypatch.setattr(
        extraction,
        "request_structured_output",
        fake_request,
    )

    extraction._call_model(
        object(),  # type: ignore[arg-type]
        [
            {
                "type": "input_image",
                "image_url": "data:image/png;base64,AA==",
            }
        ],
        retry=False,
    )

    assert received["timeout_seconds"] == (
        VISION_MODEL_CALL_TIMEOUT_SECONDS
    )


def test_raw_text_with_inch_quote_round_trips_without_truncation() -> None:
    """FR-07: quote characters remain intact through schema JSON validation."""

    raw_text = '1 plastic pencil box (approx. 8" — no oversized boxes)'
    requirement = Requirement(
        req_id="pencil-box",
        child_id="grade2",
        raw_text=raw_text,
        canonical_item="pencil_boxes",
        quantity=1,
        exclusions=("oversized boxes",),
        attributes={"material": "plastic", "size": "approx. 8 inches"},
        extraction_confidence=1.0,
    )

    round_tripped = Requirement.model_validate_json(
        requirement.model_dump_json()
    )

    assert round_tripped.raw_text == raw_text


def test_matrix_cell_unit_repairs_prevent_double_counting() -> None:
    """FR-11: visible matrix units override a misleading row label."""

    individual = Requirement(
        req_id="matrix-crayons",
        child_id="grade-4",
        raw_text="Box of crayons | 4th: 24 crayons",
        canonical_item="crayons",
        quantity=24,
        unit_type="box",
        attributes={"count": 24},
        extraction_confidence=1.0,
    )
    boxed = Requirement(
        req_id="boxed-crayons",
        child_id="grade-4",
        raw_text=(
            "1 Box 24 Crayola crayons | FOURTH GRADE: "
            "1 Box 24 Crayola crayons"
        ),
        canonical_item="crayons",
        quantity=24,
        unit_type="box",
        attributes={"count": 24},
        extraction_confidence=1.0,
    )

    assert individual.quantity == 24
    assert individual.unit_type == "each"
    assert individual.attributes.count is None
    assert individual.extraction_confidence == 0.69
    assert boxed.quantity == 1
    assert boxed.unit_type == "box"
    assert boxed.attributes.count == 24
    assert boxed.extraction_confidence == 0.69


def test_subject_count_and_brand_word_do_not_invent_pack_or_material() -> None:
    """FR-13: subject numbers and brand words stay out of literal attributes."""

    notebook = Requirement(
        req_id="notebook",
        child_id="grade-4",
        raw_text="1 3-Subject spiral notebook",
        canonical_item="spiral_notebooks",
        quantity=1,
        attributes={"count": 3},
        extraction_confidence=1.0,
    )
    pens = Requirement(
        req_id="pens",
        child_id="grade-4",
        raw_text="2 Paper Mate Flair Pens Medium Black",
        canonical_item="pens",
        quantity=2,
        attributes={"material": "paper"},
        extraction_confidence=1.0,
    )

    assert notebook.attributes.count is None
    assert pens.attributes.material is None
    assert notebook.extraction_confidence == 0.69
    assert pens.extraction_confidence == 0.69


def test_source_line_repairs_model_truncation_at_inch_quote() -> None:
    """FR-07/BR-11: source-proven text repair lowers confidence for review."""

    complete = '1 plastic pencil box (approx. 8" — no oversized boxes)'
    envelope = ExtractionEnvelope(
        requirements=(
            Requirement(
                req_id="pencil-box",
                child_id="grade2",
                raw_text="1 plastic pencil box (approx. 8",
                canonical_item="pencil_boxes",
                quantity=1,
                extraction_confidence=0.9,
            ),
        )
    )

    restored = extraction._restore_complete_raw_text(
        envelope,
        extraction._text_content(complete),
    )

    assert restored.requirements[0].raw_text == complete
    assert restored.requirements[0].extraction_confidence == 0.69


def test_source_line_restores_html_encoded_quote_and_changed_dash() -> None:
    """FR-07: transport-altered punctuation is restored from the source."""

    complete = '1 plastic pencil box (approx. 8" — no oversized boxes)'
    envelope = ExtractionEnvelope(
        requirements=(
            Requirement(
                req_id="pencil-box",
                child_id="grade2",
                raw_text=(
                    "1 plastic pencil box "
                    "(approx. 8&#34; � no oversized boxes)"
                ),
                canonical_item="pencil_boxes",
                quantity=1,
                extraction_confidence=1.0,
            ),
        )
    )

    restored = extraction._restore_complete_raw_text(
        envelope,
        extraction._text_content(complete),
    )

    assert restored.requirements[0].raw_text == complete
    assert restored.requirements[0].extraction_confidence == 0.69


def test_nonempty_document_with_empty_model_result_fails_extraction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """E-33: a schema-valid empty response cannot silently erase a list."""

    monkeypatch.setattr(
        extraction,
        "_call_model_with_service_errors",
        lambda *args, **kwargs: ExtractionEnvelope(requirements=()),
    )

    with pytest.raises(
        extraction.EmptyExtractionError,
        match="No supply requirements were found",
    ):
        extraction.extract_document(
            "12 pencils",
            child_id="child",
            mime_type="text/plain",
            client=object(),  # type: ignore[arg-type]
        )


def _requirement(
    *,
    req_id: str,
    requirement_type: str,
    confidence: float,
) -> Requirement:
    return Requirement(
        req_id=req_id,
        child_id="model-child",
        raw_text=f"{requirement_type} item",
        canonical_item="tissues",
        quantity=1,
        unit_type="box",
        is_required=requirement_type == "required",
        is_purchasable=True,
        requirement_type=requirement_type,  # type: ignore[arg-type]
        extraction_confidence=confidence,
    )


def test_optional_model_review_flag_is_deferred_by_deterministic_gate() -> None:
    """BR-10: model-proposed add-on review cannot interrupt the base cart."""

    model_output = ExtractionEnvelope(
        stated_grades=("Grade 5",),
        stated_teachers=("Ms. Rivera",),
        requirements=(
            _requirement(
                req_id="donation",
                requirement_type="donation",
                confidence=0.69,
            ),
        ),
        manual_review_required=True,
        review_reasons=("Wish-list packaging is uncertain.",),
    )

    secured = _apply_security_filters(model_output, "child-a")

    assert secured.manual_review_required is False
    assert secured.review_reasons == ()
    assert secured.deferred_review_reasons == (
        "Low-confidence extraction requires review: donation item",
    )
    assert secured.stated_grades == ("Grade 5",)
    assert secured.stated_teachers == ("Ms. Rivera",)


def test_required_low_confidence_review_remains_immediate() -> None:
    """FR-12: required low-confidence extraction still interrupts."""

    model_output = ExtractionEnvelope(
        requirements=(
            _requirement(
                req_id="required",
                requirement_type="required",
                confidence=0.69,
            ),
        ),
    )

    secured = _apply_security_filters(model_output, "child-a")

    assert secured.manual_review_required is True
    assert secured.review_reasons == (
        "Low-confidence extraction requires review: required item",
    )
    assert secured.deferred_review_reasons == ()


def test_identical_model_reading_is_suppressed_before_quantity_math() -> None:
    """BR-13: a repeated visual line cannot multiply the requested quantity."""

    duplicate = Requirement(
        req_id="duplicate-a",
        child_id="model",
        raw_text="Composition book | 5th: 1",
        canonical_item="composition_notebooks",
        quantity=1,
        extraction_confidence=0.9,
    )
    envelope = ExtractionEnvelope(
        requirements=(
            duplicate,
            duplicate.model_copy(update={"req_id": "duplicate-b"}),
        )
    )

    secured = _apply_security_filters(envelope, "child-a")

    assert len(secured.requirements) == 1
    assert secured.skipped_lines == (
        "Duplicate reading suppressed: Composition book | 5th: 1",
    )


def _status_error(
    error_type: type[AuthenticationError]
    | type[RateLimitError]
    | type[BadRequestError],
    status_code: int,
    message: str,
) -> Exception:
    request = httpx.Request("POST", "https://api.openai.com/v1/responses")
    response = httpx.Response(status_code, request=request)
    return error_type(message, response=response, body=None)


@pytest.mark.parametrize(
    ("error", "expected_message"),
    [
        (
            _status_error(
                AuthenticationError,
                401,
                "underlying-auth",
            ),
            "OpenAI authentication failed",
        ),
        (
            _status_error(
                RateLimitError,
                429,
                "underlying-rate-limit",
            ),
            "rate limit or quota was reached",
        ),
        (
            APIConnectionError(
                message="underlying-connection",
                request=httpx.Request(
                    "POST",
                    "https://api.openai.com/v1/responses",
                ),
            ),
            "Streamlit Cloud could not connect to OpenAI",
        ),
        (
            _status_error(
                BadRequestError,
                400,
                "underlying-bad-request",
            ),
            "OpenAI rejected the extraction request",
        ),
    ],
)
def test_openai_failures_are_logged_and_become_actionable(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    error: Exception,
    expected_message: str,
) -> None:
    """FR-07: service failures retain logs and expose useful next actions."""

    def fail_call(*args: object, **kwargs: object) -> ExtractionEnvelope:
        raise error

    monkeypatch.setattr(extraction, "_call_model", fail_call)
    with caplog.at_level(logging.ERROR, logger="agent.extract"):
        with pytest.raises(
            extraction.ExtractionServiceError,
            match=expected_message,
        ):
            extraction._call_model_with_service_errors(  # type: ignore[arg-type]
                object(),
                [],
                False,
            )

    assert str(error) in caplog.text


def test_api_key_diagnostic_masks_secret_and_reports_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """D-2: diagnostics reveal only a partial key and its source."""

    secret_key = "sk-live-1234567890abcdefghijklmnopwxyz"
    monkeypatch.setenv("OPENAI_API_KEY", "environment-key-not-selected")
    monkeypatch.setitem(
        sys.modules,
        "streamlit",
        SimpleNamespace(secrets={"OPENAI_API_KEY": secret_key}),
    )

    diagnostic = extraction.get_api_key_diagnostic()

    assert diagnostic.found is True
    assert diagnostic.source == "st.secrets"
    assert diagnostic.masked_key == "sk-live-...wxyz"
    assert secret_key not in diagnostic.masked_key


def test_api_key_diagnostic_reports_environment_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """D-2: environment fallback is distinguished from Streamlit secrets."""

    environment_key = "env-key-1234567890abcdefghijklmnoplast"
    monkeypatch.setenv("OPENAI_API_KEY", environment_key)
    monkeypatch.setitem(
        sys.modules,
        "streamlit",
        SimpleNamespace(secrets={}),
    )

    diagnostic = extraction.get_api_key_diagnostic()

    assert diagnostic.found is True
    assert diagnostic.source == "environment"
    assert diagnostic.masked_key == "env-key-...last"
    assert environment_key not in diagnostic.masked_key


def test_txt_input_extracts_readable_content_without_mutation() -> None:
    """FR-06: UTF-8 TXT content reaches the delimited model input."""

    content = extraction._document_content(
        b"2 boxes of tissues\n12 pencils",
        "text/plain",
    )

    assert len(content) == 1
    assert "2 boxes of tissues\n12 pencils" in content[0]["text"]


def test_docx_input_extracts_paragraphs_bullets_and_tables(
    docx_list_bytes: bytes,
) -> None:
    """FR-06: readable DOCX blocks become delimited extraction text."""

    content = extraction._document_content(
        docx_list_bytes,
        (
            "application/vnd.openxmlformats-officedocument."
            "wordprocessingml.document"
        ),
    )
    text = content[0]["text"]

    assert "2 boxes of tissues" in text
    assert "12 pencils" in text
    assert "Item | 4 glue sticks" in text


@pytest.mark.parametrize(
    ("fixture_name", "mime_type", "expected_prefix"),
    [
        ("png_list_bytes", "image/png", "data:image/png;base64,"),
        ("jpeg_list_bytes", "image/jpeg", "data:image/jpeg;base64,"),
    ],
)
def test_repeatable_image_fixtures_build_multimodal_content(
    request: pytest.FixtureRequest,
    fixture_name: str,
    mime_type: str,
    expected_prefix: str,
) -> None:
    """FR-06: stable image fixtures reach the image-capable model path."""

    content = extraction._document_content(
        request.getfixturevalue(fixture_name),
        mime_type,
    )

    assert [block["type"] for block in content] == [
        "input_text",
        "input_image",
        "input_text",
    ]
    assert content[1]["image_url"].startswith(expected_prefix)


def test_pdf_pages_are_rendered_as_images_before_model_reading(
    multipage_pdf_bytes: bytes,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FR-06: PDF layout reaches vision as one image block per page."""

    def text_path_must_not_run(data: bytes) -> str:
        del data
        raise AssertionError("text extraction is fallback-only")

    monkeypatch.setattr(extraction, "_pdf_text", text_path_must_not_run)

    content = extraction._document_content(
        multipage_pdf_bytes,
        "application/pdf",
        vision_model="vision-model",
    )

    assert [block["type"] for block in content] == [
        "input_text",
        "input_text",
        "input_image",
        "input_text",
        "input_image",
        "input_text",
    ]
    assert content[2]["image_url"].startswith("data:image/png;base64,")
    assert content[4]["image_url"].startswith("data:image/png;base64,")
    assert content[1]["text"] == "[PDF PAGE 1]"
    assert content[3]["text"] == "[PDF PAGE 2]"


def test_two_pdf_inputs_render_safely_in_parallel(
    multipage_pdf_bytes: bytes,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FR-06: concurrent list intake never triggers a text-layout fallback."""

    def text_path_must_not_run(data: bytes) -> str:
        del data
        raise AssertionError("parallel rendering must stay on the vision path")

    monkeypatch.setattr(extraction, "_pdf_text", text_path_must_not_run)

    def package_pdf(_: int) -> list[dict[str, object]]:
        return extraction._document_content(
            multipage_pdf_bytes,
            "application/pdf",
            vision_model="vision-model",
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = tuple(executor.map(package_pdf, range(2)))

    assert all(
        sum(block["type"] == "input_image" for block in content) == 2
        for content in results
    )


def test_pdf_text_is_used_only_when_page_rendering_fails(
    multipage_pdf_bytes: bytes,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FR-06: readable text remains a narrow PDF-render failure fallback."""

    monkeypatch.setattr(
        extraction,
        "_render_pdf_pages",
        lambda data: (_ for _ in ()).throw(RuntimeError("render failed")),
    )
    monkeypatch.setattr(
        extraction,
        "_pdf_text",
        lambda data, page_numbers=(): "Grade 2\n12 pencils",
    )

    content = extraction._document_content(
        multipage_pdf_bytes,
        "application/pdf",
        vision_model="vision-model",
    )

    assert [block["type"] for block in content] == ["input_text"]
    assert "Grade 2\n12 pencils" in content[0]["text"]


def test_pdf_requires_a_configured_vision_model(
    multipage_pdf_bytes: bytes,
) -> None:
    """FR-06: PDF uploads fail clearly instead of losing visual layout."""

    with pytest.raises(
        extraction.ExtractionInputError,
        match="LLM_VISION_MODEL is not configured",
    ):
        extraction._document_content(
            multipage_pdf_bytes,
            "application/pdf",
            vision_model=None,
        )


def test_matrix_and_translated_sections_are_parent_selectable() -> None:
    """FR-06: grade columns select independently and translations do not add."""

    structure = DocumentStructureEnvelope(
        layouts=("grade_matrix", "multilingual"),
        languages=("English", "Spanish"),
        sections=(
            DocumentSection(
                section_id="english-k",
                label="English — Kindergarten column",
                grades=("Kindergarten",),
                page_numbers=(1,),
                language="English",
                column_label="K",
                source_line="K",
            ),
            DocumentSection(
                section_id="english-1",
                label="English — Grade 1 column",
                grades=("Grade 1",),
                page_numbers=(1,),
                language="English",
                column_label="1",
                source_line="1",
            ),
            DocumentSection(
                section_id="spanish-k",
                label="Spanish — Kindergarten column",
                grades=("Kindergarten",),
                page_numbers=(2,),
                language="Spanish",
                column_label="K",
                source_line="KINDER",
                duplicate_of_section_id="english-k",
            ),
        ),
    )

    selection = extraction.build_document_selection(
        structure,
        ("english-k",),
    )

    assert tuple(
        section.section_id
        for section in extraction.selectable_document_sections(structure)
    ) == ("english-k", "english-1")
    assert selection.selected_section_labels == (
        "English — Kindergarten column",
    )
    assert selection.ignored_section_labels == (
        "English — Grade 1 column",
        "Spanish — Kindergarten column",
    )
    assert selection.selected_page_numbers == (1,)
    assert selection.selected_column_labels == ("K",)


def test_one_grade_skips_parent_section_choice_but_names_translation() -> None:
    """FR-06: one grade auto-selects once and still reports ignored copies."""

    structure = DocumentStructureEnvelope(
        layouts=("multilingual",),
        languages=("English", "Spanish"),
        sections=(
            DocumentSection(
                section_id="english",
                label="Grade 2 — English",
                grades=("Grade 2",),
                language="English",
                source_line="Grade 2",
            ),
            DocumentSection(
                section_id="spanish",
                label="Grade 2 — Spanish",
                grades=("Grade 2",),
                language="Spanish",
                source_line="Grado 2",
                duplicate_of_section_id="english",
            ),
        ),
    )

    from agent.sections import (
        build_resolved_section_choice,
        choice_to_document_selection,
        resolve_document_sections,
    )

    resolution = resolve_document_sections(structure, "Grade 2")
    selection = choice_to_document_selection(
        structure,
        build_resolved_section_choice(resolution),
    )

    assert selection is not None
    assert selection.selected_section_ids == ("english",)
    assert selection.selected_page_numbers == ()
    assert selection.selected_column_labels == ()
    assert selection.ignored_section_ids == ("spanish",)


def test_selected_section_sends_only_its_pdf_pages(
    multipage_pdf_bytes: bytes,
) -> None:
    """FR-06: item extraction does not resend ignored document pages."""

    content = extraction._document_content(
        multipage_pdf_bytes,
        "application/pdf",
        vision_model="vision-model",
        page_numbers=(2,),
    )

    assert sum(block["type"] == "input_image" for block in content) == 1
    assert any(block.get("text") == "[PDF PAGE 2]" for block in content)
    assert not any(block.get("text") == "[PDF PAGE 1]" for block in content)
@pytest.mark.parametrize(
    ("source_line", "expected_ruling"),
    (
        ("1 wide ruled composition notebook", "wide-ruled"),
        ("1 college ruled composition notebook", "college-ruled"),
        ("1 graph paper composition notebook", "graph"),
        ("1 quad ruled composition notebook", "quad"),
        ("1 lined composition notebook", "lined"),
        ("1 plain composition notebook", "plain"),
    ),
)
def test_production_schema_captures_product_defining_rulings(
    source_line: str,
    expected_ruling: str,
) -> None:
    """BR-31: stated ruling values survive the validated Requirement."""

    requirement = Requirement(
        req_id="notebook",
        child_id="child-1",
        raw_text=source_line,
        canonical_item="composition_notebooks",
        quantity=1,
        extraction_confidence=1.0,
    )

    assert requirement.attributes.ruling == expected_ruling


def test_regular_composition_descriptor_remains_explicitly_ambiguous() -> None:
    """BR-32: regular is preserved for a parent question, not guessed."""

    requirement = Requirement(
        req_id="regular",
        child_id="child-1",
        raw_text="4 Regular composition books",
        canonical_item="composition_notebooks",
        quantity=4,
        attributes={"style": "regular"},
        extraction_confidence=1.0,
    )

    assert requirement.attributes.ruling is None
    assert requirement.attributes.style is None
    assert requirement.ambiguous_descriptors == ("regular",)
