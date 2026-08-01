"""API routes for the dialogue-first Hunt Copilot."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from api.security import require_api_access
from hunt_copilot.schemas import (
    ConfirmExecutionRequest,
    CopilotHistoryResponse,
    CopilotResponse,
    ExecutionResponse,
    SendCopilotMessageRequest,
    SearchSkillsResponse,
    StartCopilotRequest,
    UpdateStrategyRequest,
)
from hunt_copilot.search_skills import list_search_skills
from hunt_copilot.service import HuntCopilotService

router = APIRouter(prefix="/api/v1/hunt-copilot", tags=["hunt-copilot"])


def _service() -> HuntCopilotService:
    return HuntCopilotService()


@router.get("/skills", response_model=SearchSkillsResponse, dependencies=[Depends(require_api_access)])
def get_search_skills():
    return SearchSkillsResponse(skills=list_search_skills())


@router.get("/sessions", response_model=CopilotHistoryResponse, dependencies=[Depends(require_api_access)])
def list_sessions(limit: int = 50):
    return CopilotHistoryResponse(sessions=_service().list_history(limit=limit))


@router.post("/sessions", response_model=CopilotResponse, dependencies=[Depends(require_api_access)])
def start_session(request: StartCopilotRequest):
    session, assistant = _service().start(request.message)
    return CopilotResponse(session=session, assistant_message=assistant)


@router.get("/sessions/{session_id}", response_model=CopilotResponse, dependencies=[Depends(require_api_access)])
def get_session(session_id: str):
    try:
        session = _service().get(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Hunt Copilot session not found") from exc
    return CopilotResponse(session=session, assistant_message="")


@router.post("/sessions/{session_id}/duplicate", response_model=CopilotResponse, dependencies=[Depends(require_api_access)])
def duplicate_session(session_id: str):
    try:
        session, assistant = _service().duplicate_session(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Hunt Copilot session not found") from exc
    return CopilotResponse(session=session, assistant_message=assistant)


@router.post("/sessions/{session_id}/messages", response_model=CopilotResponse, dependencies=[Depends(require_api_access)])
def send_message(session_id: str, request: SendCopilotMessageRequest):
    try:
        session, assistant = _service().send(session_id, request.message)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Hunt Copilot session not found") from exc
    return CopilotResponse(session=session, assistant_message=assistant)


@router.patch("/sessions/{session_id}/strategy", response_model=CopilotResponse, dependencies=[Depends(require_api_access)])
def update_strategy(session_id: str, request: UpdateStrategyRequest):
    try:
        session, assistant = _service().update_strategy(session_id, request.strategy)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Hunt Copilot session not found") from exc
    return CopilotResponse(session=session, assistant_message=assistant)


@router.post("/sessions/{session_id}/confirm-strategy", response_model=CopilotResponse, dependencies=[Depends(require_api_access)])
def confirm_strategy(session_id: str):
    try:
        session, assistant = _service().confirm_strategy(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Hunt Copilot session not found") from exc
    return CopilotResponse(session=session, assistant_message=assistant)


@router.post("/sessions/{session_id}/check-channels", response_model=CopilotResponse, dependencies=[Depends(require_api_access)])
def check_channels(session_id: str):
    try:
        session, assistant = _service().check_channels(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Hunt Copilot session not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return CopilotResponse(session=session, assistant_message=assistant)


@router.post("/sessions/{session_id}/execute", response_model=ExecutionResponse, dependencies=[Depends(require_api_access)])
def confirm_execution(session_id: str, request: ConfirmExecutionRequest):
    try:
        session, job = _service().confirm_execution(session_id, request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Hunt Copilot session not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return ExecutionResponse(session=session, job=job)
