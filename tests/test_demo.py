"""Offline demonstration tests with no model or retailer dependency."""

from agent.demo import DEMO_LIST_TEXT, extract_demo_document


def test_bundled_demo_text_extracts_structured_items_deterministically() -> None:
    first = extract_demo_document(
        DEMO_LIST_TEXT,
        child_id="child-1",
        mime_type="text/plain",
    )
    second = extract_demo_document(
        DEMO_LIST_TEXT,
        child_id="child-1",
        mime_type="text/plain",
    )

    assert first == second
    assert [item.canonical_item for item in first.requirements] == [
        "pencils",
        "glue_sticks",
        "composition_notebooks",
        "tissues",
        "headphones",
        "backpacks",
    ]
    assert first.requirements[-1].requirement_type == "optional"


def test_demo_txt_bytes_need_no_external_client() -> None:
    result = extract_demo_document(
        b"2 pencils\n1 box tissues",
        child_id="child-1",
        mime_type="text/plain",
    )

    assert len(result.requirements) == 2
    assert all(item.extraction_confidence == 1.0 for item in result.requirements)
