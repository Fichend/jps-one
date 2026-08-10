"""Natural-language host replies that do not mutate strategy or run tools."""

from __future__ import annotations

import operator
import re
from typing import Callable

from hunt_copilot.schemas import ConversationRoute, CopilotSession


OPS: dict[str, Callable[[float, float], float]] = {
    "+": operator.add,
    "-": operator.sub,
    "*": operator.mul,
    "x": operator.mul,
    "×": operator.mul,
    "/": operator.truediv,
    "÷": operator.truediv,
}


class ConversationHost:
    """Produce conversational responses while the executor remains controlled."""

    def reply(self, route: ConversationRoute, session: CopilotSession, message: str) -> str:
        if route.assistant_message:
            return route.assistant_message
        if route.intent == "smalltalk":
            return self._smalltalk()
        if route.intent == "capability_help":
            return self._capability_help()
        if route.intent == "general_question":
            return self._general_question(message)
        if route.intent == "strategy_discussion":
            return self._strategy_discussion(message, session)
        if route.intent == "execution_confirmation":
            return self.blocked_action(session, action="confirm_execution")
        if route.intent == "off_topic":
            return "这个问题和客户搜索关系不大，我可以简单回答；如果要继续创建获客任务，告诉我目标国家、客户类型和产品关键词就行。"
        return "我在。你可以直接描述要找的国家、客户类型、JPS 产品和硬条件；确认前我不会调用搜索 API。"

    def blocked_action(self, session: CopilotSession, *, action: str) -> str:
        if action == "confirm_execution":
            if not session.strategy.strategy_confirmed:
                return "还不能开始搜索。需要先把右侧策略卡确认下来，然后做通道检查，最后才会正式执行。"
            if session.preview is None:
                return "策略已经确认，但还没有做通道检查。请先检查 Tavily、Google Maps、Instagram/Facebook 等通道，通过后再正式执行。"
            return "可以准备正式执行。为了安全起见，请使用右侧“正式执行”按钮创建唯一 Hunt 任务。"
        return "当前状态还不能执行这个动作，我会先保证策略、预算和通道都通过校验。"

    @staticmethod
    def _smalltalk() -> str:
        return "你好，我在。你可以先随便测试我；要创建客户搜索任务时，告诉我目标国家、客户类型和 JPS 产品就行。"

    @staticmethod
    def _capability_help() -> str:
        return (
            "我可以帮业务员把获客想法整理成可执行搜索策略：目标国家、客户类型、JPS 产品关键词、"
            "排除对象、硬条件、候选池数量和预算。策略确认后，系统会调用 Tavily、Google Maps、"
            "Apify Instagram/Facebook 等公开通道，把多源证据合并进候选池，再按 JPS 评分排序，"
            "并支持为单个客户生成背调表。"
        )

    def _general_question(self, message: str) -> str:
        answer = _try_math(message)
        if answer:
            return f"{answer}。如果你是在测试 Copilot，我也可以继续回答；要创建搜索任务时，告诉我目标国家和客户类型就行。"
        return "这个我可以回答，但它不会影响右侧策略卡。要继续做客户搜索时，直接告诉我目标市场、客户类型或需要修改的条件。"

    @staticmethod
    def _strategy_discussion(message: str, session: CopilotSession) -> str:
        lower = message.lower()
        if lower.strip() in {"可以", "好的", "好", "没问题", "就这样", "行", "ok", "okay", "yes", "确认", "确认策略", "同意确认"}:
            return "收到，但这类简短回复不会确认或修改策略。请点击右侧“确认策略”，或明确输入“确认当前策略”。"
        if "instagram" in lower or "ins" in lower:
            return "Instagram 作为硬条件会提高可触达性，但也会减少合格客户数量。更稳的做法是把候选池设为最终客户数的 4-5 倍，缺 Instagram 的客户保留在候补排序里。"
        if "预算" in message or "budget" in lower:
            return f"当前正式预算是 {session.strategy.budget.total_usd:g} USD，候选池 {session.strategy.budget.max_candidates} 个。预算越低，社媒和官网补全的覆盖率越容易受影响。"
        return "这个属于策略判断，我先不改策略卡。你可以告诉我“改成什么”或“确认采用哪种规则”，我再更新右侧策略。"


def _try_math(message: str) -> str:
    text = str(message or "").strip().lower().replace("几", "").replace("多少", "")
    match = re.search(r"(-?\d+(?:\.\d+)?)\s*([+\-*/x×÷])\s*(-?\d+(?:\.\d+)?)", text)
    if not match:
        return ""
    left = float(match.group(1))
    op = match.group(2)
    right = float(match.group(3))
    if op in {"/", "÷"} and right == 0:
        return "除数不能为 0"
    result = OPS[op](left, right)
    if result.is_integer():
        return f"{int(left)}{op}{int(right)}={int(result)}"
    return f"{left:g}{op}{right:g}={result:g}"
