"""Customer pool API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from api.hunt_store import save_hunt, now_iso
from api.security import require_api_access
from business.leads.customer_pool import (
    CustomerPoolImportError,
    ImportHuntLeadsResponse,
    LeadPoolResponse,
    build_lead_pool,
    mark_hunt_imported,
)


router = APIRouter(prefix="/api/v1/customer-pool", tags=["customer-pool"])


@router.get("", response_model=LeadPoolResponse, dependencies=[Depends(require_api_access)])
async def get_customer_pool() -> LeadPoolResponse:
    """Return imported leads grouped by their source hunt."""
    from api.routes import _hunts

    return build_lead_pool(_hunts)


@router.post("/imports/{hunt_id}", response_model=ImportHuntLeadsResponse, dependencies=[Depends(require_api_access)])
async def import_hunt_leads_to_customer_pool(hunt_id: str) -> ImportHuntLeadsResponse:
    """Mark a historical hunt as imported into the customer pool."""
    from api.routes import _hunts

    try:
        response = mark_hunt_imported(_hunts, hunt_id, now_iso)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Hunt not found") from exc
    except CustomerPoolImportError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    save_hunt(hunt_id, _hunts[hunt_id])
    return response
