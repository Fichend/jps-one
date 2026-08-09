"""Deterministic strategy commands for high-risk conversational edits.

Country keep/remove/replace operations must not depend on an LLM merge.  This
module intentionally handles only commands that can be parsed with high
confidence; everything else continues through the planner.
"""

from __future__ import annotations

from dataclasses import dataclass
import re

from hunt_copilot.schemas import HuntStrategy


COUNTRY_ALIASES = {
    "brazil": "Brazil", "brasil": "Brazil", "巴西": "Brazil",
    "mexico": "Mexico", "méxico": "Mexico", "墨西哥": "Mexico",
    "spain": "Spain", "españa": "Spain", "西班牙": "Spain",
    "vietnam": "Vietnam", "viet nam": "Vietnam", "越南": "Vietnam",
    "thailand": "Thailand", "泰国": "Thailand",
    "indonesia": "Indonesia", "印度尼西亚": "Indonesia", "印尼": "Indonesia",
    "malaysia": "Malaysia", "马来西亚": "Malaysia",
    "philippines": "Philippines", "菲律宾": "Philippines",
    "united states": "United States", "usa": "United States", "美国": "United States",
    "canada": "Canada", "加拿大": "Canada",
    "germany": "Germany", "德国": "Germany",
    "france": "France", "法国": "France",
    "italy": "Italy", "意大利": "Italy",
    "united kingdom": "United Kingdom", "uk": "United Kingdom", "英国": "United Kingdom",
    "australia": "Australia", "澳大利亚": "Australia", "澳洲": "Australia",
    "japan": "Japan", "日本": "Japan",
    "south korea": "South Korea", "korea": "South Korea", "韩国": "South Korea",
    "india": "India", "印度": "India",
}


@dataclass(frozen=True)
class StrategyCommand:
    operation: str
    field: str = ""
    values: tuple[str, ...] = ()


def parse_strategy_command(message: str) -> StrategyCommand | None:
    text = str(message or "").strip()
    lower = text.lower()
    if _is_strategy_query(lower):
        return StrategyCommand("show")

    countries = _countries_in_text(lower)
    if not countries:
        return None

    keep_only = ("只要", "只用", "只保留", "仅保留", "only")
    remove = ("不要", "删除", "移除", "去掉", "排除", "剔除", "exclude", "remove")
    replace = ("改成", "改为", "设置为", "设为", "目标地区是", "target region is")
    add = ("增加", "添加", "加上", "新增", "add")
    if any(marker in lower for marker in keep_only) and _keeps_only_countries(lower):
        return StrategyCommand("keep_only", "target_regions", tuple(countries))
    if any(marker in lower for marker in remove) and _removes_countries(lower):
        return StrategyCommand("remove", "target_regions", tuple(countries))
    if any(marker in lower for marker in replace):
        return StrategyCommand("replace", "target_regions", tuple(countries))
    field_assignment = bool(re.search(r"(?:目标地区|目标国家|target\s+regions?)\s*[:：]", lower))
    has_other_fields = any(marker in lower for marker in ("客户类型", "目标客户", "产品关键词", "产品：", "硬条件", "customer type", "product keyword"))
    if field_assignment and not has_other_fields:
        return StrategyCommand("replace", "target_regions", tuple(countries))
    if any(marker in lower for marker in add) and any(marker in lower for marker in ("地区", "国家", "region", "country")):
        return StrategyCommand("add", "target_regions", tuple(countries))
    return None


def apply_strategy_command(strategy: HuntStrategy, command: StrategyCommand, *, raw_message: str = "") -> HuntStrategy:
    updated = strategy.model_copy(deep=True)
    if command.operation == "show":
        return updated
    current = list(getattr(updated, command.field))
    values = list(command.values)
    if command.operation in {"keep_only", "replace"}:
        result = values
    elif command.operation == "remove":
        blocked = {item.casefold() for item in values}
        result = [item for item in current if item.casefold() not in blocked]
        updated.exclusions = _unique([*updated.exclusions, *values])
    elif command.operation == "add":
        result = _unique([*current, *values])
    else:
        return updated
    setattr(updated, command.field, _unique(result))
    if command.operation in {"keep_only", "replace"}:
        kept = {item.casefold() for item in values}
        updated.exclusions = [item for item in updated.exclusions if item.casefold() not in kept]
    if raw_message.strip():
        updated.raw_requirement = (updated.raw_requirement + "\n" + raw_message.strip()).strip()
    updated.strategy_version += 1
    updated.strategy_confirmed = False
    updated.needs_recheck = True
    return HuntStrategy.model_validate(updated.model_dump())


def command_applied(strategy: HuntStrategy, command: StrategyCommand) -> bool:
    if command.operation == "show":
        return True
    actual = {item.casefold() for item in getattr(strategy, command.field)}
    expected = {item.casefold() for item in command.values}
    if command.operation in {"keep_only", "replace"}:
        return actual == expected
    if command.operation == "remove":
        return not actual.intersection(expected)
    if command.operation == "add":
        return expected.issubset(actual)
    return False


def _is_strategy_query(text: str) -> bool:
    strategy_markers = ("策略", "条件", "设置", "strategy")
    query_markers = ("是什么", "有哪些", "显示", "查看", "当前", "最终", "汇总", "给我看", "show")
    return any(item in text for item in strategy_markers) and any(item in text for item in query_markers) and not any(
        item in text for item in ("改成", "改为", "设置为", "删除", "移除", "只要", "只保留")
    )


def _countries_in_text(text: str) -> list[str]:
    matches: list[tuple[int, str]] = []
    for alias, canonical in COUNTRY_ALIASES.items():
        pattern = rf"(?<![a-z]){re.escape(alias)}(?![a-z])" if alias.isascii() else re.escape(alias)
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            matches.append((match.start(), canonical))
    return _unique([value for _, value in sorted(matches)])


def _removes_countries(text: str) -> bool:
    if any(marker in text for marker in ("地区不要", "国家不要", "地区排除", "排除地区", "排除国家", "remove region", "exclude country")):
        return True
    remove_positions = [text.find(marker) for marker in ("不要", "删除", "移除", "去掉", "排除", "剔除", "exclude", "remove") if marker in text]
    country_positions = [text.find(alias) for alias in COUNTRY_ALIASES if alias in text]
    return any(0 <= remove_pos < country_pos and country_pos - remove_pos <= 16 for remove_pos in remove_positions for country_pos in country_positions)


def _keeps_only_countries(text: str) -> bool:
    if any(marker in text for marker in ("地区只要", "国家只要", "只保留地区", "只保留国家", "only region", "only country")):
        return True
    keep_positions = [text.find(marker) for marker in ("只要", "只用", "只保留", "仅保留", "only") if marker in text]
    country_positions = [text.find(alias) for alias in COUNTRY_ALIASES if alias in text]
    return any(0 <= keep_pos < country_pos and country_pos - keep_pos <= 12 for keep_pos in keep_positions for country_pos in country_positions)


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        clean = str(value or "").strip()
        key = clean.casefold()
        if clean and key not in seen:
            seen.add(key)
            result.append(clean)
    return result
