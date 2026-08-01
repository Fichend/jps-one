"""JPS One framework and foundation routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api.security import require_api_access
from workflows.framework_status import get_framework_status


router = APIRouter(prefix="/jps-one", tags=["jps-one"], dependencies=[Depends(require_api_access)])


@router.get("/framework/status")
def framework_status() -> dict[str, object]:
    """Return the JPS One foundation status without exposing secrets."""

    return get_framework_status()

