"""Write one-customer background-check workbooks from the Excel template."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from openpyxl import load_workbook
from openpyxl.styles import Alignment

from backcheck.field_mapper import TEMPLATE_CELLS, map_customer_to_cells, sheet_title_for_customer


def write_backcheck_workbook(template_path: Path, output_path: Path, customer: dict[str, Any], hunt: dict[str, Any] | None = None) -> Path:
    if not template_path.is_file():
        raise FileNotFoundError(f"Backcheck template not found: {template_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    workbook = load_workbook(template_path)
    template_sheet = workbook.worksheets[0]
    template_sheet.title = _unique_sheet_name(workbook, sheet_title_for_customer(customer), current=template_sheet.title)
    for sheet in list(workbook.worksheets[1:]):
        workbook.remove(sheet)

    cells = map_customer_to_cells(customer, hunt=hunt)
    for cell in TEMPLATE_CELLS:
        template_sheet[cell] = cells.get(cell, "")
    _fit_social_row(template_sheet)

    workbook.save(output_path)
    return output_path


def _fit_social_row(sheet) -> None:
    social_cells = [sheet[cell] for cell in ("B13", "C13", "D13")]
    social_texts = [str(cell.value or "") for cell in social_cells]
    if not any(social_texts):
        return
    for cell in social_cells:
        cell.alignment = Alignment(wrap_text=True, vertical="top")
    max_lines = max(text.count("\n") + 1 for text in social_texts if text)
    sheet.row_dimensions[13].height = max(float(sheet.row_dimensions[13].height or 18), min(96, 18 * max_lines + 24))


def _unique_sheet_name(workbook, desired: str, *, current: str) -> str:
    clean = (desired or "客户背调")[:31]
    existing = {sheet.title for sheet in workbook.worksheets if sheet.title != current}
    if clean not in existing:
        return clean
    base = clean[:28]
    index = 2
    while f"{base}-{index}" in existing:
        index += 1
    return f"{base}-{index}"[:31]
