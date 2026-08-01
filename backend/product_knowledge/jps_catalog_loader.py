"""Load curated JPS catalogue templates."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any


PACKAGE_ROOT = Path(__file__).resolve().parent
DEFAULT_TEMPLATE_PATH = PACKAGE_ROOT / "data" / "jps_product_templates.json"


class ProductTemplateError(RuntimeError):
    """Raised when the curated product template cannot be loaded safely."""


@lru_cache(maxsize=4)
def load_jps_product_template(path: str | None = None) -> dict[str, Any]:
    template_path = Path(path) if path else DEFAULT_TEMPLATE_PATH
    try:
        data = json.loads(template_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ProductTemplateError(f"Failed to load JPS product template: {template_path}") from exc
    if not isinstance(data, dict):
        raise ProductTemplateError("JPS product template must be a JSON object")
    if not isinstance(data.get("product_families"), list):
        raise ProductTemplateError("JPS product template missing product_families")
    return data
