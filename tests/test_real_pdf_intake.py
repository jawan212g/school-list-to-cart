"""Model-free checks for the three real district PDF reference documents."""

from pathlib import Path

import pytest

from agent.extract import _document_content


SAMPLE_LISTS = Path(__file__).parent / "sample_lists"
REAL_PDF_CASES = (
    ("Machiasschoolsupplylist 1.pdf", 3),
    ("New_School Supply List 2025-2026 (1).pdf", 2),
    ("SchoolSuppliesListChecklist25-26.pdf", 6),
)


@pytest.mark.parametrize(("filename", "page_count"), REAL_PDF_CASES)
def test_real_district_pdf_renders_every_page_for_structure_detection(
    filename: str,
    page_count: int,
) -> None:
    """FR-06: real table/grid PDFs reach the vision path page by page."""

    content = _document_content(
        SAMPLE_LISTS / filename,
        "application/pdf",
        vision_model="vision-model",
    )

    assert sum(block["type"] == "input_image" for block in content) == page_count
    assert all(
        any(
            block.get("text") == f"[PDF PAGE {page_number}]"
            for block in content
        )
        for page_number in range(1, page_count + 1)
    )


@pytest.mark.parametrize(("filename", "page_count"), REAL_PDF_CASES)
def test_real_district_pdf_sends_only_parent_selected_page(
    filename: str,
    page_count: int,
) -> None:
    """FR-06: ignored pages do not reach selected-section item extraction."""

    selected_page = page_count
    content = _document_content(
        SAMPLE_LISTS / filename,
        "application/pdf",
        vision_model="vision-model",
        page_numbers=(selected_page,),
    )

    assert sum(block["type"] == "input_image" for block in content) == 1
    assert any(
        block.get("text") == f"[PDF PAGE {selected_page}]"
        for block in content
    )
