"""Service layer for single-customer background-check exports."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config.settings import Settings, get_settings
from backcheck.field_mapper import file_stem_for_customer
from backcheck.workbook_writer import write_backcheck_workbook


@dataclass(frozen=True)
class BackcheckExportResult:
    file_name: str
    path: Path
    count: int = 1


def export_candidate_backcheck(
    *,
    hunt_id: str,
    customer: dict[str, Any],
    hunt: dict[str, Any] | None = None,
    settings: Settings | None = None,
) -> BackcheckExportResult:
    settings = settings or get_settings()
    if not isinstance(customer, dict) or not customer:
        raise ValueError("customer is required")
    template_path = _template_path(settings)
    output_dir = _output_dir(settings)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    stem = file_stem_for_customer(customer)
    file_name = f"客户背调-{stem}-{timestamp}-{uuid.uuid4().hex[:6]}.xlsx"
    output_path = output_dir / file_name
    write_backcheck_workbook(template_path, output_path, customer, hunt=hunt)
    return BackcheckExportResult(file_name=file_name, path=output_path)


def resolve_backcheck_download(file_name: str, *, settings: Settings | None = None) -> Path:
    settings = settings or get_settings()
    clean_name = Path(str(file_name or "")).name
    if clean_name != file_name or not clean_name.endswith(".xlsx"):
        raise ValueError("invalid backcheck file name")
    output_dir = _output_dir(settings).resolve()
    path = (output_dir / clean_name).resolve()
    try:
        path.relative_to(output_dir)
    except ValueError as exc:
        raise ValueError("invalid backcheck file path") from exc
    if not path.is_file():
        raise FileNotFoundError(clean_name)
    return path


def _template_path(settings: Settings) -> Path:
    configured = str(getattr(settings, "backcheck_template_path", "") or "").strip()
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parent.parent / "templates" / "backcheck" / "客户背调 - 模板.xlsx"


def _output_dir(settings: Settings) -> Path:
    configured = str(getattr(settings, "backcheck_output_dir", "") or "").strip()
    if configured:
        path = Path(configured)
    else:
        path = Path(__file__).resolve().parent.parent / "outputs" / "backcheck"
    path.mkdir(parents=True, exist_ok=True)
    return path
