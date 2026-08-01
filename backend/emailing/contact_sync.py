"""Synchronize edited email contact profiles back to Hunt results."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from api.hunt_store import load_hunt, now_iso, save_hunt


def _text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _domain(url: Any) -> str:
    raw = _text(url).lower()
    if not raw:
        return ""
    if not raw.startswith(("http://", "https://")):
        raw = "https://" + raw
    parsed = urlparse(raw)
    host = parsed.netloc or parsed.path.split("/")[0]
    return host.removeprefix("www.")


def _name_key(value: Any) -> str:
    text = _text(value).lower()
    text = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", text)
    return text


def _identity_keys(row: dict[str, Any]) -> set[str]:
    keys: set[str] = set()
    for value in (row.get("candidate_id"), row.get("lead_id"), row.get("id")):
        clean = _text(value).lower()
        if clean:
            keys.add(f"id:{clean}")
    domain = _domain(row.get("website") or row.get("url") or row.get("link"))
    if domain:
        keys.add(f"domain:{domain}")
    name = _name_key(row.get("company_name") or row.get("name") or row.get("title"))
    if name:
        keys.add(f"name:{name}")
    for email in _list(row.get("emails")) + ([row.get("email")] if row.get("email") else []):
        clean = _text(email).lower()
        if clean:
            keys.add(f"email:{clean}")
    return keys


def _profile_keys(profile: dict[str, Any]) -> set[str]:
    keys = _identity_keys(profile)
    snapshot = profile.get("lead_snapshot") if isinstance(profile.get("lead_snapshot"), dict) else {}
    keys.update(_identity_keys(snapshot))
    return keys


def _append_unique(values: list[Any], value: str) -> list[str]:
    result = [_text(item).lower() for item in values if _text(item)]
    clean = _text(value).lower()
    if clean and clean not in result:
        result.append(clean)
    return result


def _append_manual_evidence(row: dict[str, Any], email: str, updated_at: str) -> None:
    evidence_items = row.get("evidence_items") if isinstance(row.get("evidence_items"), list) else []
    marker = f"manual_email_update:{email}"
    if not any(isinstance(item, dict) and item.get("id") == marker for item in evidence_items):
        evidence_items.append({
            "id": marker,
            "source": "manual_email_update",
            "source_url": _text(row.get("website")),
            "url": _text(row.get("website")),
            "title": "业务员手动补全邮箱",
            "claim": f"业务员在邮件资料中补全收件邮箱：{email}",
            "snippet": f"业务员在邮件资料中补全收件邮箱：{email}",
            "confidence": 1.0,
            "updated_at": updated_at,
        })
    row["evidence_items"] = evidence_items


def _merge_profile_into_row(row: dict[str, Any], profile: dict[str, Any], updated_at: str) -> bool:
    email = _text(profile.get("recipient_email")).lower()
    if not email:
        return False
    changed = False
    emails = _append_unique(_list(row.get("emails")), email)
    if emails != row.get("emails"):
        row["emails"] = emails
        changed = True
    if _text(row.get("email")).lower() != email:
        row["email"] = email
        changed = True
    for source_key, target_key in (("recipient_name", "contact_person"), ("recipient_title", "contact_title")):
        value = _text(profile.get(source_key))
        if value and _text(row.get(target_key)) != value:
            row[target_key] = value
            changed = True
    if email:
        decision_makers = row.get("decision_makers") if isinstance(row.get("decision_makers"), list) else []
        if not any(isinstance(item, dict) and _text(item.get("email")).lower() == email for item in decision_makers):
            decision_makers.append({
                "name": _text(profile.get("recipient_name")),
                "title": _text(profile.get("recipient_title")),
                "email": email,
                "source": "manual_email_update",
                "updated_at": updated_at,
            })
            row["decision_makers"] = decision_makers
            changed = True
    current_score = float(row.get("contactability_score") or 0)
    if current_score < 0.9:
        row["contactability_score"] = 0.9
        changed = True
    manual_updates = row.get("manual_updates") if isinstance(row.get("manual_updates"), list) else []
    manual_updates.append({"field": "email", "value": email, "source": "email_contact_profile", "updated_at": updated_at})
    row["manual_updates"] = manual_updates[-20:]
    _append_manual_evidence(row, email, updated_at)
    row["updated_at"] = updated_at
    row["profile_manually_updated"] = True
    return True or changed


def sync_contact_profile_to_hunt(profile: dict[str, Any]) -> dict[str, Any]:
    """Write edited contact profile fields back to a hunt JSON result."""

    hunt_id = _text(profile.get("hunt_id"))
    if not hunt_id:
        return {"synced": False, "matched_count": 0}
    hunt = load_hunt(hunt_id)
    if not hunt or not isinstance(hunt.get("result"), dict):
        return {"synced": False, "matched_count": 0}

    profile_keys = _profile_keys(profile)
    updated_at = now_iso()
    result = hunt["result"]
    matched_count = 0
    for collection_name in ("candidate_pool", "leads"):
        rows = result.get(collection_name)
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            if profile_keys and profile_keys.isdisjoint(_identity_keys(row)):
                continue
            if _merge_profile_into_row(row, profile, updated_at):
                matched_count += 1

    if matched_count:
        hunt["updated_at"] = updated_at
        save_hunt(hunt_id, hunt)
        try:
            from api import routes as hunt_routes  # Imported lazily to avoid startup cycles.

            if hunt_id in hunt_routes._hunts:
                hunt_routes._hunts[hunt_id] = hunt
        except Exception:
            pass
    return {"synced": bool(matched_count), "matched_count": matched_count, "updated_at": updated_at}


def sync_contact_profile_selection_to_hunt(profile: dict[str, Any]) -> dict[str, Any]:
    """Write the red outreach bookmark state from Email Sending back to Hunt."""

    hunt_id = _text(profile.get("hunt_id"))
    if not hunt_id:
        return {"synced": False, "matched_count": 0}
    hunt = load_hunt(hunt_id)
    if not hunt or not isinstance(hunt.get("result"), dict):
        return {"synced": False, "matched_count": 0}

    profile_keys = _profile_keys(profile)
    selected = bool(profile.get("selected_for_outreach"))
    updated_at = now_iso()
    result = hunt["result"]
    matched_count = 0
    for collection_name in ("candidate_pool", "leads"):
        rows = result.get(collection_name)
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            if profile_keys and profile_keys.isdisjoint(_identity_keys(row)):
                continue
            row["selected_for_outreach"] = selected
            row["selection_source"] = "email_sending" if selected else ""
            row["selected_at"] = updated_at if selected else ""
            row["updated_at"] = updated_at
            matched_count += 1

    if matched_count:
        hunt["updated_at"] = updated_at
        save_hunt(hunt_id, hunt)
        try:
            from api import routes as hunt_routes  # Imported lazily to avoid startup cycles.

            if hunt_id in hunt_routes._hunts:
                hunt_routes._hunts[hunt_id] = hunt
        except Exception:
            pass
    return {"synced": bool(matched_count), "matched_count": matched_count, "updated_at": updated_at}
