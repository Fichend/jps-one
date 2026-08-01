"""Tool-plan builder compatibility wrapper."""

from __future__ import annotations

from hunt_copilot.schemas import HuntStrategy, ToolPlan
from tool_executor.search_plan_compiler import SearchPlanCompiler


def build_tool_plan(strategy: HuntStrategy, *, created_by: str = "fallback") -> ToolPlan:
    return SearchPlanCompiler().compile(strategy, created_by=created_by)
