"""Map JPS One lead/candidate data into the background-check template cells."""

from __future__ import annotations

import re
from typing import Any


TEMPLATE_CELLS = (
    "A1",
    "B4", "D4", "B5", "B6", "D6", "B7", "D7", "B8", "B9", "D9",
    "B12", "D12", "A13", "B13", "C13", "D13", "B14", "D14",
    "B15", "D15", "B16", "D16", "B17", "D17", "B18", "D18",
    "B19", "D19", "A22", "B23", "D23", "B24", "D24", "B25", "B26",
)


def map_customer_to_cells(customer: dict[str, Any], hunt: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return an A1-cell mapping for one customer background-check sheet.

    Missing data is represented as an empty string so the template stays blank.
    """
    hunt = hunt or {}
    result = hunt.get("result") if isinstance(hunt.get("result"), dict) else {}
    company_name = _first_str(customer, "company_name", "title", "name")
    country = _first_str(customer, "country", "country_code", "target_country") or _first_list_value(result.get("target_regions")) or _first_list_value(hunt.get("target_regions"))
    website = _first_str(customer, "website", "link")
    social = _as_dict(customer.get("social_media"))
    social_links = _social_links(customer, social)

    emails = _list_values(customer.get("emails")) or _list_values(customer.get("email_addresses"))
    email = _first_str(customer, "email") or _first_list_value(emails)
    phones = _list_values(customer.get("phone_numbers")) or _list_values(customer.get("phones"))
    phone = _first_str(customer, "phone", "phone_number") or _first_list_value(phones)
    address = _first_str(customer, "address") or _maps_value(customer, "address")
    product_lines = _joined(
        customer.get("product_lines"),
        customer.get("matched_products"),
        customer.get("product_keywords"),
        result.get("product_keywords"),
        hunt.get("product_keywords"),
    )
    target_group = _first_str(customer, "target_customer_group") or _first_str(result, "target_customer_profile") or _first_str(hunt, "target_customer_profile")
    company_type = _first_str(customer, "customer_type", "customer_role", "industry")
    market = country

    decision_makers = [_as_dict(item) for item in customer.get("decision_makers", []) if isinstance(item, dict)] if isinstance(customer.get("decision_makers"), list) else []
    contact_name = _first_str(customer, "contact_person", "contact_name") or _first_str(decision_makers[0], "name") if decision_makers else _first_str(customer, "contact_person", "contact_name")
    about = _about_text(customer)
    customs_data = _customs_text(customer)

    cells = {cell: "" for cell in TEMPLATE_CELLS}
    cells.update(
        {
            "A1": _join_title(country, company_name),
            "B4": website,
            "D4": company_type,
            "B5": about,
            "B6": contact_name,
            "D6": phone,
            "B7": email,
            "D7": address,
            "B8": product_lines,
            "B9": _joined(customer.get("brands"), customer.get("brand_names")),
            "D9": market,
            "A13": "社媒资料",
            "B13": _social_cell_value("LinkedIn", social_links.get("linkedin", "")),
            "C13": _social_cell_value("Instagram", social_links.get("instagram", "")),
            "D13": _social_cell_value("Facebook", social_links.get("facebook", ""), extra=("X", social_links.get("x", ""))),
            "B14": _first_str(customer, "company_size"),
            "D14": _first_str(customer, "employees", "employee_count"),
            "B19": _maps_snapshot(customer),
            "D19": _first_str(customer, "warehouse_size"),
            "A22": customs_data,
            "B23": _first_str(customer, "import_from"),
            "D23": _first_str(customer, "import_frequency"),
            "B24": _first_str(customer, "export_to"),
            "D24": _first_str(customer, "export_frequency"),
            "B25": _first_str(customer, "frequent_purchase_goods") or product_lines,
            "B26": target_group,
        }
    )
    for index, dm in enumerate(decision_makers[:4], start=15):
        cells[f"B{index}"] = _first_str(dm, "name")
        cells[f"D{index}"] = _contact_bundle(dm)
    return cells


def sheet_title_for_customer(customer: dict[str, Any]) -> str:
    company = _first_str(customer, "company_name", "title", "name") or "客户背调"
    clean = re.sub(r"[\\/*?:\[\]]+", " ", company).strip()
    return (clean or "客户背调")[:31]


def file_stem_for_customer(customer: dict[str, Any]) -> str:
    company = _first_str(customer, "company_name", "title", "name") or "customer"
    clean = re.sub(r"[^\w\u4e00-\u9fff.-]+", "-", company, flags=re.UNICODE).strip("-.")
    return clean[:80] or "customer"


def _first_str(data: dict[str, Any], *keys: str) -> str:
    if not isinstance(data, dict):
        return ""
    for key in keys:
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, (int, float)) and value not in (0, 0.0):
            return str(value)
    return ""


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list_values(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item or "").strip()]


def _first_list_value(value: Any) -> str:
    if isinstance(value, list):
        return next((str(item).strip() for item in value if str(item or "").strip()), "")
    if isinstance(value, str):
        return value.strip()
    return ""


def _joined(*values: Any) -> str:
    items: list[str] = []
    for value in values:
        if isinstance(value, list):
            items.extend(str(item).strip() for item in value if str(item or "").strip())
        elif isinstance(value, str) and value.strip():
            items.append(value.strip())
    deduped: list[str] = []
    for item in items:
        if item not in deduped:
            deduped.append(item)
    return "、".join(deduped)


def _social_value(social: dict[str, Any], platform: str) -> str:
    return _first_str(social, platform, f"{platform}_url", platform.title())


def _social_links(customer: dict[str, Any], social: dict[str, Any]) -> dict[str, str]:
    links = {
        "linkedin": _first_str(customer, "linkedin_url", "linkedin") or _social_value(social, "linkedin"),
        "instagram": _first_str(customer, "instagram_url", "instagram") or _social_value(social, "instagram"),
        "facebook": _first_str(customer, "facebook_url", "facebook") or _social_value(social, "facebook"),
        "x": _first_str(customer, "twitter_url", "x_url", "twitter", "x") or _social_value(social, "twitter") or _social_value(social, "x"),
    }
    for profile in customer.get("social_profiles", []) if isinstance(customer.get("social_profiles"), list) else []:
        if not isinstance(profile, dict):
            continue
        provider = _first_str(profile, "provider", "platform", "type").lower()
        url = _first_str(profile, "url", "profile_url", "link")
        if not url:
            continue
        if "linkedin" in provider and not links["linkedin"]:
            links["linkedin"] = url
        elif "instagram" in provider and not links["instagram"]:
            links["instagram"] = url
        elif "facebook" in provider and not links["facebook"]:
            links["facebook"] = url
        elif provider in {"x", "twitter"} and not links["x"]:
            links["x"] = url
    return links


def _social_cell_value(label: str, url: str, *, extra: tuple[str, str] | None = None) -> str:
    parts = [f"{label}:\n{url}"] if url else []
    if extra and extra[1]:
        parts.append(f"{extra[0]}:\n{extra[1]}")
    return "\n".join(parts)


def _maps_value(customer: dict[str, Any], key: str) -> str:
    maps = _as_dict(customer.get("maps_data"))
    return _first_str(maps, key)


def _about_text(customer: dict[str, Any]) -> str:
    description = _first_str(customer, "description", "about", "about_us")
    if description:
        return description
    for evidence in _evidence_items(customer):
        claim = _first_str(evidence, "claim", "snippet", "title")
        if claim:
            return claim
    return ""


def _customs_text(customer: dict[str, Any]) -> str:
    value = _first_str(customer, "customs_data")
    lowered = value.lower()
    negative = ("no data", "no public customs", "not applicable", "not an importer", "not an exporter")
    if any(marker in lowered for marker in negative):
        return ""
    return value


def _maps_snapshot(customer: dict[str, Any]) -> str:
    maps = _as_dict(customer.get("maps_data"))
    parts = []
    for label, value in (
        ("地址", _first_str(maps, "address")),
        ("类型", _first_str(maps, "type")),
        ("电话", _first_str(maps, "phone_number", "phoneNumber")),
        ("评分", _first_str(maps, "rating")),
    ):
        if value:
            parts.append(f"{label}: {value}")
    return "；".join(parts)


def _evidence_items(customer: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for key in ("evidence", "evidence_items"):
        raw = customer.get(key)
        if isinstance(raw, list):
            items.extend(item for item in raw if isinstance(item, dict))
    return items


def _contact_bundle(item: dict[str, Any]) -> str:
    parts = []
    for key in ("email", "phone", "tel", "whatsapp"):
        value = _first_str(item, key)
        if value:
            parts.append(value)
    return " / ".join(parts)


def _join_title(country: str, company_name: str) -> str:
    if country and company_name:
        return f"{country}+{company_name}"
    return company_name or country
