"""Import-safe structural checks for the Streamlit application."""

import pytest

import app


def test_money_and_tax_inputs_convert_at_the_interface_boundary() -> None:
    """E-37/BR-02: valid inputs become integer cents and basis points."""

    assert app.money_to_cents("75") == 7_500
    assert app.money_to_cents("$1,234.56") == 123_456
    assert app.tax_percent_to_basis_points("7.0") == 700
    assert app.tax_percent_to_basis_points("7.125") == 713


@pytest.mark.parametrize("value", ["0", "-1", "abc", "1.001"])
def test_invalid_budget_input_has_a_clear_validation_error(value: str) -> None:
    """E-37: invalid budgets stop before any pipeline work."""

    with pytest.raises(ValueError, match="Budget|budget"):
        app.money_to_cents(value)


def test_upload_validation_checks_type_size_and_file_signature() -> None:
    """FR-06/E-35: only validated PDF, JPG, PNG, and TXT reach extraction."""

    assert (
        app.validate_uploaded_document("list.pdf", b"%PDF-1.7")
        == "application/pdf"
    )
    assert (
        app.validate_uploaded_document("list.jpg", b"\xff\xd8\xffdata")
        == "image/jpeg"
    )
    assert (
        app.validate_uploaded_document(
            "list.png",
            b"\x89PNG\r\n\x1a\ndata",
        )
        == "image/png"
    )
    assert (
        app.validate_uploaded_document("list.txt", b"2 pencils")
        == "text/plain"
    )
    with pytest.raises(ValueError, match="valid PDF"):
        app.validate_uploaded_document("malware.pdf", b"MZ executable")
    with pytest.raises(ValueError, match="PDF, JPG, PNG, or TXT"):
        app.validate_uploaded_document("list.exe", b"MZ")
