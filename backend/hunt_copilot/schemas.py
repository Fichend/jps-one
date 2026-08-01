"""Schemas for the Hunt Copilot dialogue and strategy card."""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class CopilotState(StrEnum):
    COLLECTING_REQUIREMENTS = "COLLECTING_REQUIREMENTS"
    COLLECTING_TARGET = "COLLECTING_TARGET"
    COLLECTING_REQUIRED_FIELDS = "COLLECTING_REQUIRED_FIELDS"
    COLLECTING_BUDGET = "COLLECTING_BUDGET"
    COLLECTING_RULES = "COLLECTING_RULES"
    STRATEGY_READY = "STRATEGY_READY"
    WAITING_STRATEGY_CONFIRMATION = "WAITING_STRATEGY_CONFIRMATION"
    CHECKING_CHANNELS = "CHECKING_CHANNELS"
    CHANNEL_CHECK_FAILED = "CHANNEL_CHECK_FAILED"
    PREVIEW_COMPLETED = "PREVIEW_COMPLETED"
    WAITING_EXECUTION_CONFIRMATION = "WAITING_EXECUTION_CONFIRMATION"
    PREVIEW_READY = "PREVIEW_READY"
    RUNNING_FULL_SEARCH = "RUNNING_FULL_SEARCH"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class ChatMessage(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str
    created_at: str


class HardFilters(BaseModel):
    require_instagram: bool = False
    require_facebook: bool = False
    require_email: bool = False
    require_phone: bool = False
    require_website: bool = False
    require_address: bool = False

    def enabled_labels(self) -> list[str]:
        labels = []
        for field, label in (
            ("require_instagram", "Instagram"),
            ("require_facebook", "Facebook"),
            ("require_email", "邮箱"),
            ("require_phone", "电话"),
            ("require_website", "官网"),
            ("require_address", "地址"),
        ):
            if getattr(self, field):
                labels.append(label)
        return labels


class SearchBudget(BaseModel):
    preview_total_usd: float = Field(default=0.1, ge=0, le=25)
    total_usd: float = Field(default=1.0, ge=0.01, le=100)
    apify_actor_max_items: int = Field(default=20, ge=1, le=200)
    apify_actor_max_total_charge_usd: float = Field(default=0.2, ge=0.01, le=25)
    apify_task_max_total_charge_usd: float = Field(default=1.0, ge=0.01, le=100)
    max_candidates: int = Field(default=40, ge=1, le=1000)
    final_leads: int = Field(default=10, ge=1, le=500)

    @model_validator(mode="after")
    def validate_budget(self) -> "SearchBudget":
        if self.final_leads > self.max_candidates:
            raise ValueError("final_leads cannot exceed max_candidates")
        if self.preview_total_usd > self.total_usd:
            raise ValueError("preview_total_usd cannot exceed total_usd")
        if self.apify_task_max_total_charge_usd > self.total_usd:
            self.apify_task_max_total_charge_usd = self.total_usd
        return self


class ExecutionRules(BaseModel):
    hard_filter_enabled: bool = True
    missing_required_action: Literal["pending_then_reject", "reject_immediately"] = "pending_then_reject"
    candidate_pool_enabled: bool = True
    merge_multi_source_evidence: bool = True
    allow_execution: bool = False


class HuntStrategy(BaseModel):
    target_regions: list[str] = Field(default_factory=list)
    customer_types: list[str] = Field(default_factory=list)
    product_keywords: list[str] = Field(default_factory=list)
    exclusions: list[str] = Field(default_factory=list)
    hard_filters: HardFilters = Field(default_factory=HardFilters)
    budget: SearchBudget = Field(default_factory=SearchBudget)
    rules: ExecutionRules = Field(default_factory=ExecutionRules)
    search_sources: list[str] = Field(default_factory=lambda: ["web", "google_maps", "instagram", "facebook"])
    raw_requirement: str = ""
    required_fields: list[str] = Field(default_factory=list)
    preferred_fields: list[str] = Field(default_factory=list)
    confirmed_fields: list[str] = Field(default_factory=list)
    strategy_version: int = 1
    strategy_confirmed: bool = False
    needs_recheck: bool = False
    product_knowledge_refs: list[str] = Field(default_factory=list)
    product_knowledge_notes: list[str] = Field(default_factory=list)
    product_knowledge_summary: str = ""

    @model_validator(mode="after")
    def normalize_strategy(self) -> "HuntStrategy":
        self.target_regions = _dedupe(self.target_regions)
        self.customer_types = _dedupe(self.customer_types)
        self.product_keywords = _dedupe(self.product_keywords)
        self.exclusions = _dedupe(self.exclusions)
        self.search_sources = ["web", "google_maps", "instagram", "facebook"]
        self.required_fields = _dedupe(self.required_fields or self.hard_filters.enabled_labels())
        self.preferred_fields = _dedupe(self.preferred_fields)
        self.confirmed_fields = _dedupe(self.confirmed_fields)
        self.product_knowledge_refs = _dedupe(self.product_knowledge_refs)
        self.product_knowledge_notes = _dedupe(self.product_knowledge_notes)
        return self


class PlannerResponse(BaseModel):
    intent: str = "provide_requirement"
    assistant_message: str = ""
    strategy_patch: dict[str, Any] = Field(default_factory=dict)
    detected_conflicts: list[str] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
    ready_for_strategy_card: bool = False
    suggested_action: str = "continue_collecting"


class ConversationRoute(BaseModel):
    intent: str = "search_requirement"
    should_call_planner: bool = True
    should_update_strategy: bool = True
    should_run_action: bool = False
    action: str = ""
    confidence: float = 0.0
    reason: str = ""
    assistant_message: str = ""


class ToolPlanStep(BaseModel):
    tool: str
    query: str = ""
    max_results: int = Field(default=10, ge=1, le=100)
    purpose: str = ""
    requires_confirmation: bool = True
    phase: Literal["discovery", "enrichment", "evidence"] = "discovery"
    execution_mode: Literal["search_phase", "candidate_enrichment", "disabled"] = "search_phase"


class ToolPlan(BaseModel):
    objective: str = ""
    steps: list[ToolPlanStep] = Field(default_factory=list)
    estimated_max_results: int = 0
    requires_user_confirmation: bool = True
    created_by: Literal["minimax", "fallback"] = "fallback"
    plan_hash: str = ""
    summary: str = ""


class ToolExecutionPreview(BaseModel):
    tool: str
    status: Literal["ready", "missing_config", "disabled", "blocked"]
    message: str
    phase: Literal["discovery", "enrichment", "evidence"] = "discovery"
    execution_mode: Literal["search_phase", "candidate_enrichment", "disabled"] = "search_phase"


class ChannelStatus(BaseModel):
    channel: str
    enabled: bool
    configured: bool
    status: Literal["ok", "missing_config", "disabled", "not_execution_tested"]
    message: str


class SearchSkill(BaseModel):
    id: str
    name: str
    description: str = ""
    applicable_intents: list[str] = Field(default_factory=list)
    target_company_types: list[str] = Field(default_factory=list)
    default_product_categories: list[str] = Field(default_factory=list)
    recommended_channels: list[str] = Field(default_factory=list)
    optional_channels: list[str] = Field(default_factory=list)
    default_filters: list[str] = Field(default_factory=list)
    required_fields: list[str] = Field(default_factory=list)
    planner_instructions: str = ""
    risk_notes: list[str] = Field(default_factory=list)


class SearchSkillSelection(BaseModel):
    skill: SearchSkill
    reason: str = ""
    overlays: list[SearchSkill] = Field(default_factory=list)


class ToolCapability(BaseModel):
    id: str
    name: str
    provider: str
    best_for: list[str] = Field(default_factory=list)
    not_for: list[str] = Field(default_factory=list)
    requires: list[str] = Field(default_factory=list)
    requires_any: list[str] = Field(default_factory=list)
    budget_sensitive: bool = False
    role: str = "supplementary"
    returned_fields: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class ToolStatus(BaseModel):
    capability: ToolCapability
    configured: bool
    status: Literal["ok", "missing_config", "disabled", "not_execution_tested"]
    message: str


class PreviewSummary(BaseModel):
    status: Literal["ready", "blocked"] = "ready"
    estimated_queries: int = 0
    expected_candidate_pool: int = 0
    expected_final_leads: int = 0
    required_fields: list[str] = Field(default_factory=list)
    channel_breakdown: dict[str, str] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class StrategyCriticNote(BaseModel):
    level: Literal["info", "warning", "blocking"] = "info"
    title: str
    message: str
    impact: str = ""
    suggested_fix: str = ""


class CopilotSession(BaseModel):
    session_id: str
    state: CopilotState
    messages: list[ChatMessage] = Field(default_factory=list)
    strategy: HuntStrategy = Field(default_factory=HuntStrategy)
    channel_status: list[ChannelStatus] = Field(default_factory=list)
    preview: PreviewSummary | None = None
    automation_job_id: str = ""
    allowed_actions: list[str] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
    detected_conflicts: list[str] = Field(default_factory=list)
    strategy_version: int = 1
    needs_recheck: bool = False
    selected_skill: SearchSkillSelection | None = None
    critic_notes: list[StrategyCriticNote] = Field(default_factory=list)
    tool_plan: ToolPlan | None = None
    tool_execution_preview: list[ToolExecutionPreview] = Field(default_factory=list)
    strategy_hash: str = ""
    similar_history: list[dict[str, Any]] = Field(default_factory=list)
    suggested_replies: list[str] = Field(default_factory=list)
    conversation_summary: str = ""
    last_user_intent: str = ""
    last_ai_action: str = ""
    clarification_focus: str = ""
    recent_strategy_changes: list[str] = Field(default_factory=list)
    created_at: str
    updated_at: str


class CopilotHistorySummary(BaseModel):
    session_id: str
    created_at: str
    updated_at: str
    state: str
    target_regions: list[str] = Field(default_factory=list)
    customer_types: list[str] = Field(default_factory=list)
    product_keywords: list[str] = Field(default_factory=list)
    required_fields: list[str] = Field(default_factory=list)
    max_candidates: int = 0
    final_leads: int = 0
    job_id: str = ""
    job_status: str = ""
    result_count: int = 0
    candidate_count: int = 0
    instagram_count: int = 0
    email_count: int = 0
    phone_count: int = 0
    strategy_hash: str = ""
    similarity: float = 0.0


class CopilotHistoryResponse(BaseModel):
    sessions: list[CopilotHistorySummary]


class StartCopilotRequest(BaseModel):
    message: str = Field(default="", description="Natural language hunt requirement")


class SendCopilotMessageRequest(BaseModel):
    message: str


class UpdateStrategyRequest(BaseModel):
    strategy: HuntStrategy


class ConfirmExecutionRequest(BaseModel):
    enable_email_craft: bool = False
    email_template_examples: list[str] = Field(default_factory=list)
    email_template_notes: str = ""


class CopilotResponse(BaseModel):
    session: CopilotSession
    assistant_message: str = ""


class SearchSkillsResponse(BaseModel):
    skills: list[SearchSkill]


class ToolCapabilitiesResponse(BaseModel):
    capabilities: list[ToolCapability]


class ToolStatusResponse(BaseModel):
    tools: list[ToolStatus]


class ExecutionResponse(BaseModel):
    session: CopilotSession
    job: dict[str, Any]


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        clean = str(value or "").strip()
        key = clean.lower()
        if clean and key not in seen:
            seen.add(key)
            result.append(clean)
    return result
