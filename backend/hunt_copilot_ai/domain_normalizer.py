"""Business vocabulary normalization for Hunt Copilot."""

from __future__ import annotations

import re

from hunt_copilot.strategy_commands import COUNTRY_ALIASES, HARD_FIELD_ALIASES


CUSTOMER_ROLE_ALIASES: tuple[tuple[str, str], ...] = (
    ("牙科设备经销商", "dental equipment distributor"),
    ("牙科经销商", "dental equipment distributor"),
    ("牙科设备代理商", "dental equipment distributor"),
    ("牙科耗材经销商", "dental consumables distributor"),
    ("牙科用品进口商", "dental supplies importer"),
    ("医疗耗材经销商", "medical consumables distributor"),
    ("医用耗材经销商", "medical consumables distributor"),
    ("医疗耗材进口商", "medical consumables importer"),
    ("医用耗材进口商", "medical consumables importer"),
    ("医院耗材供应商", "hospital supplies distributor"),
    ("医院用品经销商", "hospital supplies distributor"),
    ("灭菌产品经销商", "sterilization products distributor"),
    ("灭菌耗材经销商", "sterilization products distributor"),
    ("CSSD供应商", "CSSD supplier"),
    ("CSSD 供应商", "CSSD supplier"),
    ("普通牙科诊所", "general dental clinic"),
    ("牙科诊所", "dental clinic"),
    ("诊所", "clinic"),
    ("牙科学校", "dental school"),
    ("牙科学院", "dental school"),
    ("大学", "university"),
    ("学院", "college"),
    ("培训中心", "training center"),
    ("经销商", "distributor"),
    ("分销商", "distributor"),
    ("代理商", "agent"),
    ("进口商", "importer"),
    ("供应商", "supplier"),
    ("制造商", "manufacturer"),
    ("distributors", "distributor"),
    ("distributor", "distributor"),
    ("dealers", "distributor"),
    ("dealer", "distributor"),
    ("agents", "agent"),
    ("agent", "agent"),
    ("importers", "importer"),
    ("importer", "importer"),
    ("suppliers", "supplier"),
    ("supplier", "supplier"),
    ("manufacturers", "manufacturer"),
    ("manufacturer", "manufacturer"),
    ("hospitals", "hospital"),
    ("hospital", "hospital"),
    ("clinics", "clinic"),
    ("clinic", "clinic"),
    ("dental schools", "dental school"),
    ("dental school", "dental school"),
    ("training centers", "training center"),
    ("training center", "training center"),
    ("dental equipment distributors", "dental equipment distributor"),
    ("dental equipment distributor", "dental equipment distributor"),
    ("dental consumables distributors", "dental consumables distributor"),
    ("dental consumables distributor", "dental consumables distributor"),
    ("dental supplies importers", "dental supplies importer"),
    ("dental supplies importer", "dental supplies importer"),
    ("medical consumables distributors", "medical consumables distributor"),
    ("medical consumables distributor", "medical consumables distributor"),
    ("medical consumables importers", "medical consumables importer"),
    ("medical consumables importer", "medical consumables importer"),
    ("hospital supplies distributors", "hospital supplies distributor"),
    ("hospital supplies distributor", "hospital supplies distributor"),
    ("sterilization products distributors", "sterilization products distributor"),
    ("sterilization products distributor", "sterilization products distributor"),
    ("cssd suppliers", "CSSD supplier"),
    ("cssd supplier", "CSSD supplier"),
)

APPLICATION_SCENARIO_ALIASES: tuple[tuple[str, str], ...] = (
    ("cssd", "CSSD"),
    ("central sterile supply department", "CSSD"),
    ("central sterile", "CSSD"),
    ("消毒供应中心", "CSSD"),
    ("消供中心", "CSSD"),
    ("灭菌中心", "CSSD"),
    ("医院消毒供应中心", "CSSD"),
    ("hospital sterile supply department", "CSSD"),
    ("central de material e esterilização", "CSSD"),
    ("cme", "CSSD"),
    ("dental education", "dental education"),
    ("simulation lab", "simulation lab"),
    ("teaching lab", "teaching lab"),
    ("training lab", "training lab"),
)

PRODUCT_KEYWORD_ALIASES: tuple[tuple[str, str], ...] = (
    ("sterilization indicator", "sterilization indicator"),
    ("chemical indicator", "chemical indicator"),
    ("chemical indicators", "chemical indicator"),
    ("biological indicator", "biological indicator"),
    ("biological indicators", "biological indicator"),
    ("sterilization pouch", "sterilization pouch"),
    ("sterilization roll", "sterilization roll"),
    ("sterilization", "sterilization"),
    ("sterilizer", "sterilizer"),
    ("autoclave", "autoclave"),
    ("dental simulator", "dental simulator"),
    ("phantom head", "phantom head"),
    ("dental teaching equipment", "dental teaching equipment"),
    ("medical consumables", "medical consumables"),
    ("sterilization indicator tape", "sterilization indicator tape"),
    ("sterilization indicator tapes", "sterilization indicator tape"),
    ("indicator label", "indicator label"),
    ("indicator labels", "indicator label"),
    ("sterilization reel", "sterilization reel"),
    ("sterilization reels", "sterilization reel"),
    ("crepe paper", "crepe paper"),
    ("nonwoven wrapping material", "nonwoven wrapping material"),
    ("nonwoven wrapping materials", "nonwoven wrapping material"),
    ("tyvek", "Tyvek"),
    ("surgical gown", "surgical gown"),
    ("isolation gown", "isolation gown"),
    ("face mask", "face mask"),
    ("bandage", "bandage"),
    ("wound dressing", "wound dressing"),
    ("syringe", "syringe"),
    ("dental consumables", "dental consumables"),
    ("dental disposable", "dental disposable"),
    ("dental burs", "dental burs"),
    ("diamond instruments", "diamond instruments"),
    ("灭菌耗材", "灭菌耗材"),
    ("灭菌指示", "sterilization indicator"),
    ("化学指示", "chemical indicator"),
    ("生物指示", "biological indicator"),
    ("灭菌袋", "sterilization pouch"),
    ("灭菌卷", "sterilization reel"),
    ("灭菌", "sterilization"),
    ("消毒", "sterilization"),
    ("牙科仿真", "dental simulator"),
    ("仿头模", "phantom head"),
    ("牙科耗材", "dental consumables"),
    ("牙科一次性用品", "dental disposable"),
    ("牙钻", "dental burs"),
    ("医用耗材", "medical consumables"),
    ("医疗耗材", "medical consumables"),
    ("手术衣", "surgical gown"),
    ("隔离衣", "isolation gown"),
    ("医用口罩", "face mask"),
    ("绷带", "bandage"),
    ("敷料", "wound dressing"),
    ("注射器", "syringe"),
    ("灭菌指示胶带", "sterilization indicator tape"),
    ("灭菌卷袋", "sterilization reel"),
    ("皱纹纸", "crepe paper"),
    ("无纺布包布", "nonwoven wrapping material"),
)

PRODUCT_EXPLICIT_MARKERS = (
    "产品是", "产品为", "产品:", "产品：", "产品关键词", "关键词是", "关键词为", "只要", "只用", "只保留",
    "product is", "product:", "product keywords", "use only", "keep only", "only",
)


def normalize_country(value: str) -> str:
    clean = _clean(value).casefold()
    return COUNTRY_ALIASES.get(clean, _clean(value))


def normalize_customer_role(value: str) -> str:
    clean = _clean(value).casefold()
    for alias, canonical in CUSTOMER_ROLE_ALIASES:
        if clean == alias.casefold():
            return canonical
    return _clean(value)


def normalize_application_scenario(value: str) -> str:
    clean = _clean(value).casefold()
    for alias, canonical in APPLICATION_SCENARIO_ALIASES:
        if clean == alias.casefold():
            return canonical
    return _clean(value)


def normalize_product_keyword(value: str) -> str:
    clean = _clean(value).casefold()
    for alias, canonical in PRODUCT_KEYWORD_ALIASES:
        if clean == alias.casefold():
            return canonical
    return _clean(value)


def normalize_contact_field(value: str) -> str:
    clean = _clean(value).casefold()
    return HARD_FIELD_ALIASES.get(clean, _clean(value))


def find_countries(text: str) -> list[tuple[str, str]]:
    lower = text.casefold()
    matches: list[tuple[int, str, str]] = []
    for alias, canonical in COUNTRY_ALIASES.items():
        pattern = rf"(?<![a-z]){re.escape(alias)}(?![a-z])" if alias.isascii() else re.escape(alias)
        match = re.search(pattern, lower, flags=re.IGNORECASE)
        if match:
            matches.append((match.start(), canonical, match.group(0)))
    return [(canonical, source) for _, canonical, source in sorted(matches)]


def marker_present(text: str, marker: str) -> bool:
    lower = text.casefold()
    token = marker.casefold()
    if token.isascii():
        return bool(re.search(rf"(?<![a-z]){re.escape(token)}(?![a-z])", lower, flags=re.IGNORECASE))
    return token in lower


def find_aliases(text: str, aliases: tuple[tuple[str, str], ...]) -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []
    seen: set[str] = set()
    matched_sources: list[str] = []
    for alias, canonical in sorted(aliases, key=lambda item: len(item[0]), reverse=True):
        if any(alias.casefold() in source.casefold() for source in matched_sources):
            continue
        if marker_present(text, alias):
            key = canonical.casefold()
            if key not in seen:
                seen.add(key)
                matched_sources.append(alias)
                result.append((canonical, alias))
    return result


def has_explicit_product_marker(text: str) -> bool:
    lower = text.casefold()
    return any(marker.casefold() in lower for marker in PRODUCT_EXPLICIT_MARKERS)


def split_values(value: str, *, split_chinese_and: bool = True) -> list[str]:
    separators = r",|，|、|;|；|/|\band\b|以及"
    if split_chinese_and:
        separators += r"|和"
    return [_clean(item) for item in re.split(rf"\s*(?:{separators})\s*", value, flags=re.IGNORECASE) if _clean(item)]


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip(" '\"：:，,。.;；"))
