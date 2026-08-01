"""Safe search-tool capability routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api.security import require_api_access
from hunt_copilot.schemas import ToolCapabilitiesResponse, ToolStatusResponse
from search_tools import list_tool_capabilities, list_tool_status


router = APIRouter(prefix="/api/v1/search-tools", tags=["search-tools"])


@router.get("/capabilities", response_model=ToolCapabilitiesResponse, dependencies=[Depends(require_api_access)])
def get_capabilities():
    return ToolCapabilitiesResponse(capabilities=list_tool_capabilities())


@router.get("/status", response_model=ToolStatusResponse, dependencies=[Depends(require_api_access)])
def get_status():
    return ToolStatusResponse(tools=list_tool_status())
