"""Repeatable file fixtures for supply-list intake tests."""

from __future__ import annotations

from io import BytesIO

import pytest
from docx import Document
from PIL import Image


@pytest.fixture
def docx_list_bytes() -> bytes:
    """Return a deterministic DOCX with paragraphs, a bullet, and a table."""

    document = Document()
    document.add_paragraph("2 boxes of tissues")
    document.add_paragraph("12 pencils", style="List Bullet")
    table = document.add_table(rows=1, cols=2)
    table.cell(0, 0).text = "Item"
    table.cell(0, 1).text = "4 glue sticks"
    output = BytesIO()
    document.save(output)
    return output.getvalue()


def _image_bytes(image_format: str) -> bytes:
    image = Image.new("RGB", (16, 16), color=(255, 255, 255))
    output = BytesIO()
    image.save(output, format=image_format)
    return output.getvalue()


@pytest.fixture
def png_list_bytes() -> bytes:
    """Return stable PNG bytes for image-content packaging tests."""

    return _image_bytes("PNG")


@pytest.fixture
def jpeg_list_bytes() -> bytes:
    """Return stable JPEG bytes for image-content packaging tests."""

    return _image_bytes("JPEG")
