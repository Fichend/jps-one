"""Admin routes for encrypted integration configuration and Meta enrichment."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from api.security import require_api_access
from business.integrations.meta_service import (
    IntegrationConfigError,
    IntegrationProviderError,
    enrich_meta_profile,
    list_supported_integrations,
    read_integration,
    test_meta_connection,
    write_integration,
)
from connectors.meta.graph_api import MetaGraphError


router = APIRouter(prefix="/api/admin/integrations", tags=["admin-integrations"])
public_router = APIRouter(prefix="/api/v1/social", tags=["social-enrichment"])


class IntegrationSaveRequest(BaseModel):
    enabled: bool = True
    config: dict[str, Any] = Field(default_factory=dict)


class IntegrationResponse(BaseModel):
    provider: str
    enabled: bool
    status: str
    config: dict[str, Any]
    secret_status: dict[str, bool]
    scopes: str = ""
    last_test_at: str = ""
    last_test_status: str = ""
    last_test_message: str = ""
    created_at: str = ""
    updated_at: str = ""


class IntegrationTestResponse(BaseModel):
    provider: str
    status: Literal["ok", "error"]
    message: str
    assets: dict[str, Any] = Field(default_factory=dict)


class SocialEnrichRequest(BaseModel):
    provider: Literal["meta_instagram"] = "meta_instagram"
    profile_url: str = ""
    handle: str = ""


class SocialEnrichResponse(BaseModel):
    provider: str
    status: Literal["ok"]
    result: dict[str, Any]


def _ensure_supported(provider: str) -> None:
    try:
        read_integration(provider)
    except IntegrationProviderError as exc:
        raise HTTPException(status_code=404, detail="Unsupported integration provider") from exc


@router.get("", response_model=list[IntegrationResponse], dependencies=[Depends(require_api_access)])
async def get_integrations() -> list[dict[str, Any]]:
    return list_supported_integrations()


@router.get("/{provider}", response_model=IntegrationResponse, dependencies=[Depends(require_api_access)])
async def get_integration_config(provider: str) -> dict[str, Any]:
    _ensure_supported(provider)
    return read_integration(provider)


@router.patch("/{provider}", response_model=IntegrationResponse, dependencies=[Depends(require_api_access)])
async def save_integration_config(provider: str, payload: IntegrationSaveRequest) -> dict[str, Any]:
    _ensure_supported(provider)
    return write_integration(provider, payload.config, enabled=payload.enabled)


@router.post("/{provider}/test", response_model=IntegrationTestResponse, dependencies=[Depends(require_api_access)])
async def test_integration_config(provider: str) -> IntegrationTestResponse:
    _ensure_supported(provider)
    try:
        result = await test_meta_connection()
    except (MetaGraphError, IntegrationConfigError) as exc:
        message = str(exc)
        raise HTTPException(status_code=400, detail=str(message)) from exc
    return IntegrationTestResponse(
        provider=provider,
        status="ok",
        message="Meta Graph API connection successful",
        assets=result.get("assets") or {},
    )


@public_router.post("/enrich", response_model=SocialEnrichResponse, dependencies=[Depends(require_api_access)])
async def enrich_social_profile(payload: SocialEnrichRequest) -> SocialEnrichResponse:
    if payload.provider != "meta_instagram":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unsupported social enrichment provider")
    try:
        public = await enrich_meta_profile(profile_url=payload.profile_url, handle=payload.handle)
    except (MetaGraphError, IntegrationConfigError) as exc:
        message = str(exc)
        raise HTTPException(status_code=400, detail=str(message)) from exc
    return SocialEnrichResponse(provider=payload.provider, status="ok", result=public)
