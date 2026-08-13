"""Deterministic, field-aware commands for Hunt Copilot strategy edits.

The parser only accepts high-confidence single-field edits. Full requirements
stay in the requirement planner, while read-only queries never reach a writer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any

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
    "china": "China", "pr china": "China", "people's republic of china": "China", "中国": "China", "中华人民共和国": "China",
    "singapore": "Singapore", "新加坡": "Singapore",
    "united arab emirates": "United Arab Emirates", "uae": "United Arab Emirates", "阿联酋": "United Arab Emirates",
    "saudi arabia": "Saudi Arabia", "saudi": "Saudi Arabia", "沙特阿拉伯": "Saudi Arabia", "沙特": "Saudi Arabia",
    "turkey": "Turkey", "türkiye": "Turkey", "土耳其": "Turkey",
    "russia": "Russia", "俄罗斯": "Russia",
    "south africa": "South Africa", "南非": "South Africa",
    "argentina": "Argentina", "阿根廷": "Argentina",
    "chile": "Chile", "智利": "Chile",
    "colombia": "Colombia", "哥伦比亚": "Colombia",
    "peru": "Peru", "秘鲁": "Peru",
}

HARD_FIELD_ALIASES = {
    "instagram": "require_instagram", "insta": "require_instagram", "ins": "require_instagram", "ig": "require_instagram",
    "facebook": "require_facebook", "fb": "require_facebook", "脸书": "require_facebook",
    "email": "require_email", "e-mail": "require_email", "邮箱": "require_email", "邮件": "require_email",
    "phone": "require_phone", "tel": "require_phone", "电话": "require_phone", "号码": "require_phone", "whatsapp": "require_phone",
    "website": "require_website", "official site": "require_website", "官网": "require_website",
    "address": "require_address", "location": "require_address", "地址": "require_address",
}
HARD_FILTER_KEYS = tuple(dict.fromkeys(HARD_FIELD_ALIASES.values()))

CUSTOMER_ALIASES = {
    "医院": "hospital", "hospital": "hospital",
    "诊所": "clinic", "clinic": "clinic", "普通牙科诊所": "general dental clinic",
    "制造商": "manufacturer", "manufacturer": "manufacturer",
    "经销商": "distributor", "distributor": "distributor", "dealer": "distributor",
    "进口商": "importer", "importer": "importer",
    "供应商": "supplier", "supplier": "supplier",
    "牙科学校": "dental school", "dental school": "dental school",
}

FIELD_LABELS = {
    "target_regions": "目标地区",
    "customer_types": "目标客户",
    "product_keywords": "产品关键词",
    "application_scenarios": "应用场景",
    "business_notes": "业务说明",
    "exclusions": "排除对象",
    "hard_filters": "硬条件",
    "preferred_fields": "优先字段",
    "budget.max_candidates": "候选数量",
    "budget.final_leads": "最终客户数量",
    "budget.total_usd": "正式预算",
}


@dataclass(frozen=True)
class StrategyCommand:
    operation: str
    field: str = ""
    values: tuple[str, ...] = ()
    also_exclude: tuple[str, ...] = ()
    clarification: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {"field": self.field, "operation": self.operation, "values": list(self.values)}


@dataclass
class CommandApplication:
    strategy: HuntStrategy
    changed: bool
    previous_values: list[str] = field(default_factory=list)
    current_values: list[str] = field(default_factory=list)
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    unmatched: list[str] = field(default_factory=list)


def parse_strategy_command(message: str) -> StrategyCommand | None:
    text = _clean_text(message)
    lower = text.casefold()
    if re.fullmatch(r"(?:请)?撤销(?:刚才|上一次|最近)?(?:的)?(?:修改|操作)?[。.!！]?", lower) or lower in {"undo", "undo last change"}:
        return StrategyCommand("undo")
    if is_strategy_query(text):
        return StrategyCommand("query")
    if looks_like_full_requirement(text):
        return None

    for parser in (
        _parse_preferred_field_command,
        _parse_hard_filter_command,
        _parse_budget_command,
        _parse_exclusion_command,
        _parse_product_command,
        _parse_customer_command,
    ):
        command = parser(text)
        if command is not None:
            return command

    region_command = _parse_region_command(text)
    if region_command is not None:
        return region_command

    if _has_mutation_marker(lower) and _countries_in_text(lower):
        return StrategyCommand(
            "clarify",
            values=tuple(_countries_in_text(lower)),
            clarification="请确认要修改哪个字段：目标地区、产品关键词，还是排除对象？",
        )

    exclusive = re.fullmatch(r"(?:只要|只用|只保留|仅保留|only|use only)\s+(.+)", lower, flags=re.IGNORECASE)
    if exclusive and not _countries_in_text(lower):
        values = _split_values(exclusive.group(1), split_chinese_and=False)
        return StrategyCommand("keep_only", "product_keywords", tuple(values)) if values else None
    if _has_mutation_marker(lower):
        return StrategyCommand(
            "clarify",
            clarification="请明确要修改的字段，例如“目标客户去掉医院”或“产品关键词去掉 hospital”。",
        )
    return None


def apply_strategy_command(strategy: HuntStrategy, command: StrategyCommand, *, raw_message: str = "") -> CommandApplication:
    updated = strategy.model_copy(deep=True)
    if command.operation in {"query", "clarify", "undo"}:
        return CommandApplication(updated, False)

    previous = _field_values(updated, command.field)
    added: list[str] = []
    removed: list[str] = []
    unmatched: list[str] = []

    if command.field in {"target_regions", "customer_types", "product_keywords", "exclusions", "preferred_fields"}:
        current = list(getattr(updated, command.field))
        incoming = [_normalize_value(command.field, value) for value in command.values]
        if command.operation in {"replace", "keep_only"}:
            result = _unique(incoming)
            removed = [item for item in current if not _contains_equivalent(result, item, command.field)]
            added = [item for item in result if not _contains_equivalent(current, item, command.field)]
        elif command.operation == "add":
            result = list(current)
            for item in incoming:
                if not _contains_equivalent(result, item, command.field):
                    result.append(item)
                    added.append(item)
        elif command.operation == "remove":
            result = []
            matched_keys: set[str] = set()
            for item in current:
                match = next((value for value in incoming if _equivalent_or_related(item, value, command.field)), None)
                if match is None:
                    result.append(item)
                else:
                    removed.append(item)
                    matched_keys.add(_normal_key(match, command.field))
            unmatched = [item for item in incoming if _normal_key(item, command.field) not in matched_keys]
        elif command.operation == "clear":
            result = []
            removed = list(current)
        else:
            return CommandApplication(updated, False, previous_values=previous, current_values=previous)
        setattr(updated, command.field, _unique(result))

        if command.field == "target_regions":
            excluded = list(updated.exclusions)
            to_exclude = list(command.also_exclude)
            if command.operation == "remove":
                to_exclude.extend(removed)
            for item in to_exclude:
                normalized = _normalize_value("target_regions", item)
                if not _contains_equivalent(excluded, normalized, "target_regions"):
                    excluded.append(normalized)
            kept = {_normal_key(item, "target_regions") for item in updated.target_regions}
            updated.exclusions = [item for item in excluded if _normal_key(item, "target_regions") not in kept]

    elif command.field == "hard_filters":
        requested_keys = [_hard_field_key(value) for value in command.values]
        requested_keys = [key for key in requested_keys if key]
        if command.operation in {"replace", "keep_only", "clear"}:
            keep = set(requested_keys) if command.operation != "clear" else set()
            for key in HARD_FILTER_KEYS:
                was_enabled = bool(getattr(updated.hard_filters, key))
                should_enable = key in keep
                setattr(updated.hard_filters, key, should_enable)
                if was_enabled and not should_enable:
                    removed.append(_hard_label(key))
                elif should_enable and not was_enabled:
                    added.append(_hard_label(key))
        for value in command.values:
            key = _hard_field_key(value)
            if not key:
                unmatched.append(value)
                continue
            was_enabled = bool(getattr(updated.hard_filters, key))
            if command.operation == "add":
                setattr(updated.hard_filters, key, True)
                label = _hard_label(key)
                if not was_enabled:
                    added.append(label)
                updated.preferred_fields = [item for item in updated.preferred_fields if _hard_field_key(item) != key]
            elif command.operation == "remove":
                setattr(updated.hard_filters, key, False)
                label = _hard_label(key)
                if was_enabled:
                    removed.append(label)
        updated.required_fields = updated.hard_filters.enabled_labels()

    elif command.field.startswith("budget.") and command.values:
        attribute = command.field.split(".", 1)[1]
        old_value = getattr(updated.budget, attribute)
        raw_value = float(command.values[0])
        new_value: Any = int(raw_value) if attribute in {"max_candidates", "final_leads"} else raw_value
        if attribute == "final_leads" and new_value > updated.budget.max_candidates:
            updated.budget.max_candidates = max(new_value, new_value * 4)
        setattr(updated.budget, attribute, new_value)
        if old_value != new_value:
            removed.append(str(old_value))
            added.append(str(new_value))

    current_values = _field_values(updated, command.field)
    changed = _business_dump(strategy) != _business_dump(updated)
    if changed:
        if raw_message.strip():
            updated.raw_requirement = (updated.raw_requirement + "\n" + raw_message.strip()).strip()
        updated.strategy_version += 1
        updated.strategy_confirmed = False
        updated.needs_recheck = True
    else:
        updated = strategy.model_copy(deep=True)
        current_values = previous
    validated = HuntStrategy.model_validate(updated.model_dump())
    return CommandApplication(validated, changed, previous, current_values, added, removed, unmatched)


def command_applied(strategy: HuntStrategy, expected: HuntStrategy) -> bool:
    return strategy.model_dump(mode="json") == expected.model_dump(mode="json")


def business_fields_equal(strategy: HuntStrategy, expected: HuntStrategy) -> bool:
    return _business_dump(strategy) == _business_dump(expected)


def is_strategy_query(message: str) -> bool:
    text = _clean_text(message).casefold()
    if text in {"确认当前策略", "confirm current strategy"}:
        return False
    if _has_mutation_marker(text) and not any(marker in text for marker in ("有没有问题", "是否合理", "为什么")):
        return False
    direct = (
        "最终策略卡", "当前策略", "策略是什么", "策略卡是什么", "显示策略", "查看策略", "给我看策略",
        "显示当前产品", "当前产品关键词", "产品关键词有哪些", "当前目标客户", "目标客户有哪些",
        "哪些是硬条件", "到底哪些是硬条件", "当前硬条件", "数量和预算", "预算汇总", "数量汇总",
        "我最后选的是哪个国家", "最后选了哪个国家", "把条件捋一遍", "条件捋一遍", "完整展示出来",
        "show final strategy", "show current strategy", "show strategy", "current product keywords",
    )
    if any(marker in text for marker in direct):
        return True
    question_words = ("是什么", "有哪些", "多少", "为什么", "是不是", "能保证", "难不难", "合理吗", "有没有问题", "怎么看")
    strategy_words = ("策略", "条件", "地区", "国家", "客户", "产品", "关键词", "候选", "预算", "精准")
    return any(word in text for word in question_words) and any(word in text for word in strategy_words)


def looks_like_full_requirement(message: str) -> bool:
    text = _clean_text(message).casefold()
    starters = ("我要找", "我需要", "帮我找", "帮我整", "寻找", "找", "need ", "find ", "looking for")
    starts_search = text.startswith(starters) or any(text.startswith(prefix + country.casefold()) for prefix in ("",) for country in COUNTRY_ALIASES.values())
    signals = 0
    signals += bool(_countries_in_text(text))
    signals += any(marker in text for marker in ("客户", "经销商", "进口商", "供应商", "学校", "医院", "诊所", "distributor", "importer", "supplier", "hospital", "school"))
    signals += any(marker in text for marker in ("产品", "关键词", "product", "phantom", "dental", "sterilization", "indicator"))
    signals += any(marker in text for marker in ("必须", "要官网", "要邮箱", "must have", "required"))
    signals += any(marker in text for marker in ("排除", "exclude", "without"))
    signals += any(marker in text for marker in ("候选", "最终", "预算", "candidate", "final leads", "usd"))
    explicit_single_field = bool(re.match(r"^(?:目标地区|目标国家|产品关键词|产品|目标客户|客户类型|排除项|排除对象|候选|最终|预算|instagram|facebook|邮箱|电话|官网|地址)\b", text))
    return (starts_search and signals >= 2) or (signals >= 3 and not explicit_single_field)


def _parse_product_command(text: str) -> StrategyCommand | None:
    return _parse_explicit_list_command(text, "product_keywords", r"(?:产品关键词|产品|关键词|product\s+keywords?)")


def _parse_customer_command(text: str) -> StrategyCommand | None:
    return _parse_explicit_list_command(text, "customer_types", r"(?:目标客户类型|目标客户|客户类型|customer\s+types?)")


def _parse_exclusion_command(text: str) -> StrategyCommand | None:
    lower = _clean_text(text).casefold()
    explicit = _parse_explicit_list_command(text, "exclusions", r"(?:排除对象|排除项|exclusions?)")
    if explicit is not None:
        return explicit
    direct = re.fullmatch(r"(?:排除|不要包含|exclude|without)\s*(.+)", lower, flags=re.IGNORECASE)
    if direct:
        values = _split_values(direct.group(1), split_chinese_and=True)
        return StrategyCommand("add", "exclusions", tuple(values)) if values else None
    return None


def _parse_explicit_list_command(text: str, field_name: str, field_pattern: str) -> StrategyCommand | None:
    lower = _clean_text(text).casefold()
    actions = {
        "keep_only": r"只保留|仅保留|只要|只用|keep only|use only",
        "remove": r"去掉|删除|移除|剔除|remove|delete",
        "replace": r"改成|改为|替换为|设置为|设为|replace(?: with)?|set to",
        "add": r"增加|添加|加上|新增|add",
        "clear": r"清空|全部删除|clear",
    }
    field_clear = re.fullmatch(rf"(?:清空|全部删除|clear)\s*{field_pattern}", lower, flags=re.IGNORECASE)
    clear_field = re.fullmatch(rf"{field_pattern}\s*(?:清空|全部删除|clear)", lower, flags=re.IGNORECASE)
    if field_clear or clear_field:
        return StrategyCommand("clear", field_name)
    action_union = "|".join(f"(?:{pattern})" for pattern in actions.values())
    field_first = re.search(rf"{field_pattern}\s*(?P<action>{action_union})\s*(?P<value>.+)", lower, flags=re.IGNORECASE)
    action_first = re.search(rf"(?P<action>{action_union})\s*(?P<value>.+?)\s*(?:from|在|从)\s*{field_pattern}", lower, flags=re.IGNORECASE)
    match = field_first or action_first
    if not match:
        return None
    operation = _operation_for(match.group("action"), actions)
    if not operation:
        return None
    split_and = field_name != "product_keywords"
    values = _split_values(match.group("value"), split_chinese_and=split_and)
    return StrategyCommand(operation, field_name, tuple(values)) if values or operation == "clear" else None


def _parse_region_command(text: str) -> StrategyCommand | None:
    lower = _clean_text(text).casefold()
    if re.fullmatch(r"(?:清空|全部删除|clear)\s*(?:目标地区|目标国家|target\s+regions?)", lower) or re.fullmatch(
        r"(?:目标地区|目标国家|target\s+regions?)\s*(?:清空|全部删除|clear)", lower
    ):
        return StrategyCommand("clear", "target_regions")
    countries = _countries_in_text(lower)
    if not countries:
        return None

    compound = re.search(r"(?P<old>.+?)(?:不要了|不要|去掉|排除).{0,8}(?:只搞|只做|改成|改为|换成|只要)\s*(?P<new>.+)", lower)
    if compound:
        old = _countries_in_text(compound.group("old"))
        new = _countries_in_text(compound.group("new"))
        if new:
            return StrategyCommand("replace", "target_regions", tuple(new), tuple(item for item in old if item not in new))

    if any(marker in lower for marker in ("算了还是", "还是选", "还是要")):
        return StrategyCommand("replace", "target_regions", (countries[-1],))
    if re.fullmatch(r"(?:目标地区|目标国家|target\s+regions?)\s*[:：]\s*.+", lower):
        return StrategyCommand("replace", "target_regions", tuple(countries))
    if any(marker in lower for marker in ("只要", "只搞", "只做", "只保留", "keep only", "only")):
        return StrategyCommand("keep_only", "target_regions", (countries[-1],))
    if re.search(r"(?:目标地区|目标国家|地区|国家).{0,5}(?:改成|改为|设置为|设为|换成|replace|set to)", lower):
        return StrategyCommand("replace", "target_regions", (countries[-1],))
    if re.search(r"(?:目标地区|目标国家|地区|国家).{0,5}(?:增加|添加|加上|add)", lower):
        return StrategyCommand("add", "target_regions", tuple(countries))
    if re.search(r"(?:目标地区|目标国家|地区|国家).{0,5}(?:不要|删除|移除|去掉|排除|remove|exclude)", lower):
        return StrategyCommand("remove", "target_regions", tuple(countries))
    return None


def _parse_hard_filter_command(text: str) -> StrategyCommand | None:
    lower = _clean_text(text).casefold()
    if re.fullmatch(r"(?:清空|取消全部|全部取消)\s*(?:硬条件|必须字段)", lower):
        return StrategyCommand("clear", "hard_filters")
    fields = [canonical for alias, canonical in HARD_FIELD_ALIASES.items() if _token_present(lower, alias)]
    fields = _unique(fields)
    if not fields:
        return None
    if any(marker in lower for marker in ("只保留", "仅保留", "只要", "keep only", "use only")):
        return StrategyCommand("keep_only", "hard_filters", tuple(fields))
    if any(marker in lower for marker in ("改成", "改为", "替换为", "设置为", "replace", "set to")):
        return StrategyCommand("replace", "hard_filters", tuple(fields))
    if any(marker in lower for marker in ("删除", "移除", "去掉", "remove", "delete")):
        return StrategyCommand("remove", "hard_filters", tuple(fields))
    if any(marker in lower for marker in ("不是必须", "不是硬条件", "取消必须", "取消硬条件", "不再必须", "not required")):
        return StrategyCommand("remove", "hard_filters", tuple(fields))
    if any(marker in lower for marker in ("必须增加", "增加", "必须有", "硬条件", "required", "must have")):
        return StrategyCommand("add", "hard_filters", tuple(fields))
    return None


def _parse_preferred_field_command(text: str) -> StrategyCommand | None:
    lower = _clean_text(text).casefold()
    if re.fullmatch(r"(?:清空|全部删除|clear)\s*(?:优先字段|优先项)", lower) or re.fullmatch(
        r"(?:优先字段|优先项)\s*(?:清空|全部删除|clear)", lower
    ):
        return StrategyCommand("clear", "preferred_fields")
    fields = _unique([canonical for alias, canonical in HARD_FIELD_ALIASES.items() if _token_present(lower, alias)])
    if not fields or not any(marker in lower for marker in ("优先", "preferred", "priority")):
        return None
    if any(marker in lower for marker in ("取消优先", "移出优先", "删除优先", "remove preferred")):
        return StrategyCommand("remove", "preferred_fields", tuple(fields))
    if any(marker in lower for marker in ("只保留", "仅保留", "只要", "keep only")):
        return StrategyCommand("keep_only", "preferred_fields", tuple(fields))
    if any(marker in lower for marker in ("改成", "改为", "替换为", "设置为", "replace", "set to")):
        return StrategyCommand("replace", "preferred_fields", tuple(fields))
    return StrategyCommand("add", "preferred_fields", tuple(fields))


def _parse_budget_command(text: str) -> StrategyCommand | None:
    lower = _clean_text(text).casefold()
    if any(marker in lower for marker in ("是不是", "多少", "汇总", "查看", "显示")):
        return None
    candidate = re.search(r"候选(?:改成|设为|设置为|只要|数量为)?\s*(\d+)", lower)
    if candidate:
        return StrategyCommand("replace", "budget.max_candidates", (candidate.group(1),))
    final = re.search(r"(?:最终|入库|top)(?:改成|设为|设置为|只要|数量为)?\s*(\d+)", lower)
    if final:
        return StrategyCommand("replace", "budget.final_leads", (final.group(1),))
    money = re.search(r"预算(?:控制在|改成|设为|设置为)?\s*(\d+(?:\.\d+)?)\s*(?:usd|美元|美金|\$)?", lower)
    if money:
        return StrategyCommand("replace", "budget.total_usd", (money.group(1),))
    return None


def _operation_for(value: str, actions: dict[str, str]) -> str:
    for operation, pattern in actions.items():
        if re.fullmatch(pattern, value.strip(), flags=re.IGNORECASE):
            return operation
    return ""


def _split_values(payload: str, *, split_chinese_and: bool) -> list[str]:
    clean = re.split(r"[。；;!?！？]", str(payload or "").strip(), maxsplit=1)[0]
    separators = r",|，|、|\band\b|以及"
    if split_chinese_and:
        separators += r"|和"
    parts = re.split(rf"\s*(?:{separators})\s*", clean, flags=re.IGNORECASE)
    return _unique([_strip_particles(item) for item in parts if _strip_particles(item)])


def _countries_in_text(text: str) -> list[str]:
    matches: list[tuple[int, str]] = []
    for alias, canonical in COUNTRY_ALIASES.items():
        pattern = rf"(?<![a-z]){re.escape(alias)}(?![a-z])" if alias.isascii() else re.escape(alias)
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            matches.append((match.start(), canonical))
    return _unique([value for _, value in sorted(matches)])


def _field_values(strategy: HuntStrategy, field_name: str) -> list[str]:
    if field_name in {"target_regions", "customer_types", "product_keywords", "exclusions", "preferred_fields"}:
        return list(getattr(strategy, field_name))
    if field_name == "hard_filters":
        return strategy.hard_filters.enabled_labels()
    if field_name.startswith("budget."):
        return [str(getattr(strategy.budget, field_name.split(".", 1)[1]))]
    return []


def _normalize_value(field_name: str, value: str) -> str:
    clean = _strip_particles(value)
    if field_name == "target_regions":
        return COUNTRY_ALIASES.get(clean.casefold(), clean)
    if field_name in {"customer_types", "exclusions"}:
        return CUSTOMER_ALIASES.get(clean.casefold(), clean)
    if field_name == "preferred_fields":
        key = _hard_field_key(clean)
        return _hard_label(key) if key else clean
    return clean


def _normal_key(value: str, field_name: str) -> str:
    clean = _normalize_value(field_name, value).casefold()
    if field_name in {"customer_types", "exclusions"}:
        return CUSTOMER_ALIASES.get(clean, clean)
    return clean


def _equivalent_or_related(left: str, right: str, field_name: str) -> bool:
    left_key = _normal_key(left, field_name)
    right_key = _normal_key(right, field_name)
    if left_key == right_key:
        return True
    if field_name in {"customer_types", "exclusions"} and min(len(left_key), len(right_key)) >= 4:
        return left_key in right_key or right_key in left_key
    return False


def _contains_equivalent(values: list[str], target: str, field_name: str) -> bool:
    return any(_equivalent_or_related(item, target, field_name) for item in values)


def _hard_field_key(value: str) -> str:
    clean = str(value or "").strip().casefold()
    if clean.startswith("require_"):
        return clean
    return HARD_FIELD_ALIASES.get(clean, "")


def _hard_label(key: str) -> str:
    return {
        "require_instagram": "Instagram", "require_facebook": "Facebook", "require_email": "邮箱",
        "require_phone": "电话", "require_website": "官网", "require_address": "地址",
    }.get(key, key)


def _business_dump(strategy: HuntStrategy) -> dict[str, Any]:
    data = strategy.model_dump()
    for key in (
        "raw_requirement",
        "strategy_version",
        "strategy_confirmed",
        "needs_recheck",
        "product_knowledge_refs",
        "product_knowledge_notes",
        "product_knowledge_summary",
    ):
        data.pop(key, None)
    return data


def _has_mutation_marker(text: str) -> bool:
    return any(marker in text for marker in (
        "改成", "改为", "设置为", "设为", "换成", "增加", "添加", "删除", "移除", "去掉", "排除",
        "只要", "只用", "只保留", "清空", "不是必须", "不是硬条件", "remove", "delete", "replace", "add", "keep only",
    ))


def _token_present(text: str, token: str) -> bool:
    if token.isascii():
        return bool(re.search(rf"(?<![a-z]){re.escape(token)}(?![a-z])", text, flags=re.IGNORECASE))
    return token in text


def _strip_particles(value: str) -> str:
    clean = str(value or "").strip(" '\"：:，,。.;；")
    clean = re.sub(r"^(?:是|为|把|从)", "", clean).strip()
    clean = re.sub(r"(?:里面|中|里|哈|吧)$", "", clean).strip()
    return clean


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


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
