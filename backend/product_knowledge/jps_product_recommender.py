"""Deterministic JPS product and customer-type recommender for Hunt Copilot."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from product_knowledge.jps_catalog_loader import load_jps_product_template


@dataclass
class ProductRecommendation:
    recommended_keywords: list[str] = field(default_factory=list)
    matched_families: list[str] = field(default_factory=list)
    normalized_customer_types: list[str] = field(default_factory=list)
    normalized_exclusions: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    needs_user_confirmation: bool = True

    def as_dict(self) -> dict[str, Any]:
        return {
            "recommended_keywords": self.recommended_keywords,
            "matched_families": self.matched_families,
            "normalized_customer_types": self.normalized_customer_types,
            "normalized_exclusions": self.normalized_exclusions,
            "reasons": self.reasons,
            "needs_user_confirmation": self.needs_user_confirmation,
        }


class JpsProductRecommender:
    """Recommend only curated JPS catalogue keywords.

    The recommender is intentionally deterministic and auditable. It maps
    Chinese/English customer descriptions to canonical customer types, removes
    excluded targets, and returns catalogue keywords that fit the remaining ICP.
    """

    def __init__(self, template: dict[str, Any] | None = None) -> None:
        self.template = template or load_jps_product_template()
        self.alias_index = self._build_alias_index(self.template)

    def normalize_customer_types(self, values: list[str], *, text: str = "") -> list[str]:
        return self._normalize_values(values, text=text, include_exclusions=False)

    def normalize_exclusions(self, values: list[str], *, text: str = "") -> list[str]:
        return self._normalize_values(values, text=text, include_exclusions=True)

    def recommend(
        self,
        *,
        customer_types: list[str],
        exclusions: list[str] | None = None,
        product_keywords: list[str] | None = None,
        user_requirement: str = "",
        limit: int = 8,
    ) -> ProductRecommendation:
        normalized_targets = self.normalize_customer_types(customer_types, text=user_requirement)
        normalized_exclusions = self.normalize_exclusions(exclusions or [], text=user_requirement)
        target_keys = self._canonical_keys(normalized_targets)
        exclusion_keys = self._canonical_keys(normalized_exclusions)

        filtered_targets = [item for item in normalized_targets if self._canonical_key(item) not in exclusion_keys]
        target_keys = self._canonical_keys(filtered_targets)

        explicit_keywords = _dedupe(product_keywords or [])
        if explicit_keywords:
            return ProductRecommendation(
                recommended_keywords=explicit_keywords[:limit],
                normalized_customer_types=filtered_targets,
                normalized_exclusions=normalized_exclusions,
                reasons=["用户已经提供产品关键词，系统保留用户输入。"],
                needs_user_confirmation=False,
            )

        families = self.template.get("product_families", []) if isinstance(self.template.get("product_families"), list) else []
        scored: list[tuple[int, dict[str, Any]]] = []
        for family in families:
            if not isinstance(family, dict):
                continue
            best = set(str(item) for item in family.get("best_customer_types", []) or [])
            excluded = set(str(item) for item in family.get("exclude_customer_types", []) or [])
            score = len(target_keys & best) * 3
            score -= len(target_keys & excluded) * 4
            score -= len(exclusion_keys & best)
            score += self._product_signal_score(family, user_requirement)
            if score > 0:
                scored.append((score, family))

        if not scored:
            default_keywords = _dedupe(self.template.get("default_keywords", []) or [])
            return ProductRecommendation(
                recommended_keywords=default_keywords[:limit],
                normalized_customer_types=filtered_targets,
                normalized_exclusions=normalized_exclusions,
                reasons=["未匹配到明确产品线，使用 JPS 目录默认牙科产品关键词。"],
                needs_user_confirmation=True,
            )

        scored.sort(key=lambda item: item[0], reverse=True)
        keywords: list[str] = []
        matched_families: list[str] = []
        reasons: list[str] = []
        for _, family in scored:
            matched_families.append(str(family.get("family", "")))
            reason = str(family.get("reason_zh", "")).strip()
            if reason:
                reasons.append(reason)
            keywords.extend(str(item) for item in family.get("keywords", []) or [])

        return ProductRecommendation(
            recommended_keywords=_dedupe(keywords)[:limit],
            matched_families=_dedupe(matched_families),
            normalized_customer_types=filtered_targets,
            normalized_exclusions=normalized_exclusions,
            reasons=_dedupe(reasons),
            needs_user_confirmation=True,
        )

    def _normalize_values(self, values: list[str], *, text: str = "", include_exclusions: bool) -> list[str]:
        found: list[str] = []
        haystack = "\n".join([text, *values]).lower()
        exclusion_windows = _exclusion_windows(text)
        explicit_haystack = "\n".join(values).lower()
        for key, item in self.alias_index.items():
            canonical = str(item["canonical_en"])
            aliases = item["aliases"]
            for alias in aliases:
                alias_lower = alias.lower()
                if alias_lower not in haystack:
                    continue
                in_exclusion = any(alias_lower in window for window in exclusion_windows)
                explicitly_provided = alias_lower in explicit_haystack
                if include_exclusions:
                    if in_exclusion or explicitly_provided:
                        found.append(canonical)
                elif not in_exclusion:
                    found.append(canonical)
                break
        for value in values:
            clean = str(value or "").strip()
            clean = clean.strip("。.;；,， ")
            if not clean:
                continue
            already_mapped = False
            for item in self.alias_index.values():
                aliases = [str(alias).lower() for alias in item.get("aliases", [])]
                if any(alias and alias in clean.lower() for alias in aliases) and str(item.get("canonical_en")) in found:
                    already_mapped = True
                    break
            if not already_mapped and clean not in found:
                found.append(clean)
        return _dedupe(found)

    def _canonical_key(self, value: str) -> str:
        normalized = value.lower().strip()
        for key, item in self.alias_index.items():
            if normalized == str(item["canonical_en"]).lower():
                return key
        return re.sub(r"[^a-z0-9]+", "_", normalized).strip("_")

    def _canonical_keys(self, values: list[str]) -> set[str]:
        return {self._canonical_key(value) for value in values if value}

    @staticmethod
    def _product_signal_score(family: dict[str, Any], text: str) -> int:
        haystack = (text or "").lower()
        if not haystack:
            return 0
        signals = [*(family.get("keywords", []) or []), *(family.get("zh_aliases", []) or [])]
        matches = 0
        for signal in signals:
            clean = str(signal or "").strip().lower()
            if clean and clean in haystack:
                matches += 1
        return min(matches, 3) * 4

    @staticmethod
    def _build_alias_index(template: dict[str, Any]) -> dict[str, dict[str, Any]]:
        raw = template.get("customer_type_aliases", {})
        if not isinstance(raw, dict):
            return {}
        result: dict[str, dict[str, Any]] = {}
        for key, value in raw.items():
            if not isinstance(value, dict):
                continue
            aliases = [str(item).strip() for item in value.get("aliases", []) or [] if str(item).strip()]
            canonical = str(value.get("canonical_en", key)).strip()
            result[str(key)] = {"canonical_en": canonical, "aliases": aliases + [canonical]}
        return result


def _exclusion_windows(text: str) -> list[str]:
    windows: list[str] = []
    for match in re.finditer(r"(排除|不要|不需要|exclude|without|not)\s*([^。；;\n]+)", text, flags=re.IGNORECASE):
        windows.append(match.group(0).lower())
    return windows


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        clean = str(value or "").strip()
        key = clean.lower()
        if clean and key not in seen:
            seen.add(key)
            result.append(clean)
    return result
