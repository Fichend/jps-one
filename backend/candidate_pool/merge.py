"""Merge multi-source search rows into candidate customer profiles."""

from __future__ import annotations

import hashlib
import re
from typing import Any
from urllib.parse import urlparse

from scoring import apply_score
from candidate_pool.ranking import rank_candidates
from candidate_pool.profile_merge import normalize_candidate_profiles
from goal_guard.rank_integration import apply_goal_guard


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _domain(url: str) -> str:
    if not url:
        return ""
    parsed = urlparse(url if "://" in url else f"https://{url}")
    host = parsed.netloc.lower().split("@")[-1].split(":")[0]
    if host.startswith("www."):
        host = host[4:]
    return host


def _social_url_key(url: str) -> str:
    """Return a stable key for public social profile/page URLs.

    Social search actors can return rows without a clean website or phone. In
    that case using only the display name is too aggressive and can collapse
    separate Facebook/Instagram pages into one candidate. Keep the normalized
    profile path as an identity while still allowing later website evidence to
    merge the same company across sources.
    """
    clean = _clean(url)
    if not clean:
        return ""
    parsed = urlparse(clean if "://" in clean else f"https://{clean}")
    host = parsed.netloc.lower().split("@")[0].split(":")[0]
    if host.startswith("www."):
        host = host[4:]
    if not any(domain in host for domain in ("instagram.com", "facebook.com", "linkedin.com", "twitter.com", "x.com")):
        return ""
    path = "/".join(part for part in parsed.path.strip("/").split("/") if part)[:160]
    return f"social:{host}/{path}" if path else f"social:{host}"


def _name_key(value: str) -> str:
    text = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", value.lower())
    for suffix in ("limited", "ltd", "inc", "llc", "gmbh", "ptyltd", "pte", "co", "company"):
        text = text.removesuffix(suffix)
    return text[:80]


def _candidate_key(row: dict[str, Any]) -> str:
    keys = _candidate_keys(row)
    if keys:
        return keys[0]
    fallback = hashlib.sha1(repr(row).encode("utf-8", errors="ignore")).hexdigest()[:16]
    return f"row:{fallback}"


def _candidate_keys(row: dict[str, Any]) -> list[str]:
    maps_data = row.get("maps_data") if isinstance(row.get("maps_data"), dict) else {}
    evidence = row.get("evidence") if isinstance(row.get("evidence"), dict) else {}
    keys: list[str] = []
    candidate_id = _clean(row.get("candidate_id"))
    if candidate_id:
        keys.append(candidate_id)
    for value in (
        maps_data.get("place_id"),
        maps_data.get("cid"),
    ):
        if _clean(value):
            keys.append(f"place:{_clean(value).lower()}")

    link = _clean(row.get("link") or row.get("website") or row.get("instagram_url") or row.get("facebook_url"))
    source = _clean(row.get("source"))
    social_key = _social_url_key(link)
    link_domain = _domain(link)
    if link_domain and not any(host in link_domain for host in ("instagram.com", "facebook.com", "linkedin.com")):
        keys.append(f"domain:{link_domain}")

    external_domain = _domain(_clean(evidence.get("externalUrl") or evidence.get("website")))
    if external_domain:
        keys.append(f"domain:{external_domain}")

    username = _clean(evidence.get("username"))
    if not username and _clean(row.get("instagram_url")):
        username = urlparse(_clean(row.get("instagram_url"))).path.strip("/").split("/")[0]
    if username and ("instagram" in source or _clean(row.get("instagram_url"))):
        keys.append(f"instagram:{username.lower()}")
    if social_key:
        keys.append(social_key)

    phone = _clean(maps_data.get("phone_number") or evidence.get("phone") or row.get("phone"))
    if not phone and isinstance(row.get("phone_numbers"), list):
        phone = _clean(next((item for item in row.get("phone_numbers", []) if _clean(item)), ""))
    if phone:
        digits = re.sub(r"\D+", "", phone)
        if len(digits) >= 7:
            keys.append(f"phone:{digits}")

    title_key = _name_key(_clean(row.get("title") or row.get("company_name") or maps_data.get("title")))
    address_key = _name_key(_clean(row.get("address") or maps_data.get("address")))
    social_only_identity = bool(social_key) and not external_domain and not phone and not address_key
    if (title_key or address_key) and not social_only_identity:
        keys.append(f"name:{title_key}|{address_key}")

    deduped: list[str] = []
    for key in keys:
        if key not in deduped:
            deduped.append(key)
    return deduped


def _confidence(row: dict[str, Any]) -> float:
    source = _clean(row.get("source"))
    maps_data = row.get("maps_data") if isinstance(row.get("maps_data"), dict) else {}
    evidence = row.get("evidence") if isinstance(row.get("evidence"), dict) else {}
    score = 0.2
    if row.get("link"):
        score += 0.15
    if maps_data.get("website") or evidence.get("externalUrl") or evidence.get("website"):
        score += 0.2
    if maps_data.get("phone_number") or evidence.get("phone"):
        score += 0.15
    if maps_data.get("place_id"):
        score += 0.15
    if source in {"google_maps", "apify_instagram", "apify_facebook"}:
        score += 0.1
    if evidence.get("followersCount"):
        score += 0.05
    return min(score, 1.0)


def _merge_candidate(candidate: dict[str, Any], row: dict[str, Any]) -> None:
    maps_data = row.get("maps_data") if isinstance(row.get("maps_data"), dict) else {}
    evidence = row.get("evidence") if isinstance(row.get("evidence"), dict) else {}
    source = _clean(row.get("source") or row.get("source_tool") or "search")
    title = _clean(row.get("title") or row.get("company_name") or maps_data.get("title"))
    link = _clean(row.get("link") or row.get("website") or row.get("instagram_url") or row.get("facebook_url"))

    if title and not candidate.get("company_name"):
        candidate["company_name"] = title
    website = _clean(maps_data.get("website") or evidence.get("externalUrl") or evidence.get("website"))
    if not website and link and not any(host in _domain(link) for host in ("instagram.com", "facebook.com", "linkedin.com")):
        website = link
    if website and not candidate.get("website"):
        candidate["website"] = website

    if (maps_data.get("address") or row.get("address")) and not candidate.get("address"):
        candidate["address"] = _clean(maps_data.get("address") or row.get("address"))
    if maps_data.get("phone_number") and not candidate.get("phone"):
        candidate["phone"] = _clean(maps_data.get("phone_number"))
    email = _clean(evidence.get("email") or evidence.get("businessEmail") or evidence.get("publicEmail") or row.get("email"))
    if not email and isinstance(row.get("emails"), list):
        email = _clean(next((item for item in row.get("emails", []) if _clean(item)), ""))
    if email and not candidate.get("email"):
        candidate["email"] = email
    phone = _clean(evidence.get("phone") or evidence.get("phoneNumber") or row.get("phone"))
    if not phone and isinstance(row.get("phone_numbers"), list):
        phone = _clean(next((item for item in row.get("phone_numbers", []) if _clean(item)), ""))
    if phone and not candidate.get("phone"):
        candidate["phone"] = phone
    if maps_data.get("place_id") and not candidate.get("google_maps_place_id"):
        candidate["google_maps_place_id"] = _clean(maps_data.get("place_id"))
    social_media = row.get("social_media") if isinstance(row.get("social_media"), dict) else {}
    instagram_url = _clean(row.get("instagram_url") or social_media.get("instagram") or social_media.get("instagram_url"))
    facebook_url = _clean(row.get("facebook_url") or social_media.get("facebook") or social_media.get("facebook_url"))
    linkedin_url = _clean(row.get("linkedin_url") or social_media.get("linkedin") or social_media.get("linkedin_url"))
    if "instagram" in source and link and not candidate.get("instagram_url"):
        candidate["instagram_url"] = link
    if instagram_url and not candidate.get("instagram_url"):
        candidate["instagram_url"] = instagram_url
    if "facebook" in source and link and not candidate.get("facebook_url"):
        candidate["facebook_url"] = link
    if facebook_url and not candidate.get("facebook_url"):
        candidate["facebook_url"] = facebook_url
    if linkedin_url and not candidate.get("linkedin_url"):
        candidate["linkedin_url"] = linkedin_url

    if isinstance(row.get("emails"), list):
        candidate["emails"] = sorted({*_clean_list(candidate.get("emails")), *_clean_list(row.get("emails"))})
    elif candidate.get("email"):
        candidate["emails"] = sorted({*_clean_list(candidate.get("emails")), _clean(candidate.get("email"))})
    if isinstance(row.get("phone_numbers"), list):
        candidate["phone_numbers"] = sorted({*_clean_list(candidate.get("phone_numbers")), *_clean_list(row.get("phone_numbers"))})
    elif candidate.get("phone"):
        candidate["phone_numbers"] = sorted({*_clean_list(candidate.get("phone_numbers")), _clean(candidate.get("phone"))})
    for key in ("country", "industry", "description", "customer_type", "priority_tier", "customs_data"):
        if _clean(row.get(key)) and not candidate.get(key):
            candidate[key] = _clean(row.get(key))
    for key in ("enrichment_status", "enrichment_attempts"):
        if row.get(key) not in (None, "", []):
            candidate[key] = row.get(key)
    if isinstance(row.get("enrichment_trace"), list):
        existing_trace = candidate.setdefault("enrichment_trace", [])
        if isinstance(existing_trace, list):
            existing_trace.extend(item for item in row.get("enrichment_trace", []) if isinstance(item, dict))

    if source and source not in candidate["source_channels"]:
        candidate["source_channels"].append(source)
    if isinstance(row.get("source_channels"), list):
        for channel in row.get("source_channels", []):
            clean_channel = _clean(channel)
            if clean_channel and clean_channel not in candidate["source_channels"]:
                candidate["source_channels"].append(clean_channel)
    candidate["confidence"] = max(float(candidate.get("confidence", 0.0)), _confidence(row))
    if isinstance(row.get("evidence_items"), list):
        for item in row.get("evidence_items", []):
            if isinstance(item, dict):
                candidate["evidence_items"].append(item)
    candidate["evidence_items"].append(
        {
            "source": source,
            "url": link,
            "title": title,
            "snippet": _clean(row.get("snippet")),
            "raw": {"maps_data": maps_data, "evidence": evidence},
            "confidence": _confidence(row),
        }
    )


def build_candidate_pool(
    rows: list[dict[str, Any]],
    *,
    hunt_id: str = "",
    target_final_leads: int = 10,
    hard_filters: dict[str, Any] | None = None,
    exclusions: list[str] | None = None,
    customer_types: list[str] | None = None,
    product_keywords: list[str] | None = None,
    target_regions: list[str] | None = None,
    max_candidates: int | None = None,
) -> list[dict[str, Any]]:
    candidates: dict[str, dict[str, Any]] = {}
    aliases: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        row_keys = _candidate_keys(row)
        key = next((aliases[item] for item in row_keys if item in aliases), None) or (row_keys[0] if row_keys else _candidate_key(row))
        candidate = candidates.setdefault(
            key,
            {
                "candidate_id": key,
                "hunt_id": hunt_id,
                "status": "merged",
                "company_name": "",
                "website": "",
                "country": "",
                "address": "",
                "phone": "",
                "email": "",
                "linkedin_url": "",
                "facebook_url": "",
                "instagram_url": "",
                "google_maps_place_id": "",
                "source_channels": [],
                "evidence_items": [],
                "emails": [],
                "phone_numbers": [],
                "confidence": 0.0,
            },
        )
        for alias in row_keys:
            aliases[alias] = key
        _merge_candidate(candidate, row)

    goal_checked = apply_goal_guard(
        list(candidates.values()),
        customer_types=customer_types or [],
        product_keywords=product_keywords or [],
        target_regions=target_regions or [],
        exclusions=exclusions or [],
    )
    profiled = normalize_candidate_profiles(goal_checked)
    scored = [apply_score(candidate) for candidate in profiled]
    ranked = rank_candidates(
        scored,
        target_final_leads=target_final_leads,
        hard_filters=hard_filters or {},
        exclusions=exclusions or [],
        customer_types=customer_types or [],
        product_keywords=product_keywords or [],
        target_regions=target_regions or [],
    )
    if max_candidates is not None:
        return ranked[: max(1, int(max_candidates))]
    return ranked


def _clean_list(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    return [_clean(item) for item in values if _clean(item)]
