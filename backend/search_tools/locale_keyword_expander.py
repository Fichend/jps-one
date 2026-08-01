"""Deterministic country/language keyword expansion for lead discovery.

The LLM keyword agent is useful, but it can be inconsistent across runs. This
module provides a bounded, deterministic layer that adds local-language search
phrases for countries where English-only discovery misses many SMEs.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any


@dataclass(frozen=True)
class LocaleProfile:
    aliases: tuple[str, ...]
    country_name: str
    language_code: str
    customer_terms: dict[str, tuple[str, ...]]
    product_terms: dict[str, tuple[str, ...]]
    generic_contact_terms: tuple[str, ...]


LOCALE_PROFILES: tuple[LocaleProfile, ...] = (
    LocaleProfile(
        aliases=("vietnam", "viet nam", "越南"),
        country_name="Vietnam",
        language_code="vi",
        customer_terms={
            "school": ("trường nha khoa", "khoa răng hàm mặt", "đại học y nha khoa"),
            "distributor": ("nhà phân phối thiết bị nha khoa", "công ty thiết bị nha khoa", "đại lý thiết bị nha khoa"),
            "clinic": ("phòng khám nha khoa",),
        },
        product_terms={
            "dental simulator": ("mô phỏng nha khoa", "thiết bị mô phỏng nha khoa", "phantom head nha khoa"),
            "phantom head": ("phantom head nha khoa", "mô hình phantom nha khoa"),
            "dental equipment": ("thiết bị nha khoa", "dụng cụ nha khoa"),
        },
        generic_contact_terms=("liên hệ", "email", "điện thoại"),
    ),
    LocaleProfile(
        aliases=("thailand", "thai", "泰国"),
        country_name="Thailand",
        language_code="th",
        customer_terms={
            "school": ("คณะทันตแพทยศาสตร์", "โรงเรียนทันตแพทย์", "มหาวิทยาลัยทันตแพทย์"),
            "distributor": ("ตัวแทนจำหน่ายอุปกรณ์ทันตกรรม", "บริษัทอุปกรณ์ทันตกรรม", "ผู้จำหน่ายอุปกรณ์ทันตกรรม"),
            "clinic": ("คลินิกทันตกรรม",),
        },
        product_terms={
            "dental simulator": ("เครื่องจำลองทันตกรรม", "อุปกรณ์ฝึกทันตกรรม", "phantom head ทันตกรรม"),
            "phantom head": ("phantom head ทันตกรรม", "หัวจำลองทันตกรรม"),
            "dental equipment": ("อุปกรณ์ทันตกรรม",),
        },
        generic_contact_terms=("ติดต่อ", "อีเมล", "โทรศัพท์"),
    ),
    LocaleProfile(
        aliases=("indonesia", "indonesian", "印尼", "印度尼西亚"),
        country_name="Indonesia",
        language_code="id",
        customer_terms={
            "school": ("fakultas kedokteran gigi", "sekolah kedokteran gigi", "universitas kedokteran gigi"),
            "distributor": ("distributor alat kedokteran gigi", "supplier alat kedokteran gigi", "perusahaan alat dental"),
            "clinic": ("klinik gigi",),
        },
        product_terms={
            "dental simulator": ("simulator kedokteran gigi", "alat simulasi dental", "phantom head dental"),
            "phantom head": ("phantom head dental", "model phantom gigi"),
            "dental equipment": ("alat kedokteran gigi", "peralatan dental"),
        },
        generic_contact_terms=("kontak", "email", "telepon"),
    ),
    LocaleProfile(
        aliases=("malaysia", "马来西亚"),
        country_name="Malaysia",
        language_code="ms",
        customer_terms={
            "school": ("fakulti pergigian", "sekolah pergigian", "universiti pergigian"),
            "distributor": ("pengedar peralatan pergigian", "pembekal peralatan pergigian", "syarikat dental"),
            "clinic": ("klinik pergigian",),
        },
        product_terms={
            "dental simulator": ("simulator pergigian", "peralatan latihan pergigian", "phantom head pergigian"),
            "phantom head": ("phantom head pergigian",),
            "dental equipment": ("peralatan pergigian",),
        },
        generic_contact_terms=("hubungi", "email", "telefon"),
    ),
    LocaleProfile(
        aliases=("philippines", "philippine", "菲律宾"),
        country_name="Philippines",
        language_code="en",
        customer_terms={
            "school": ("dental school", "college of dentistry", "dentistry university"),
            "distributor": ("dental equipment distributor", "dental supplier", "dental dealer"),
            "clinic": ("dental clinic",),
        },
        product_terms={
            "dental simulator": ("dental simulator", "dental simulation equipment", "phantom head dental"),
            "phantom head": ("phantom head dental",),
            "dental equipment": ("dental equipment",),
        },
        generic_contact_terms=("contact", "email", "phone"),
    ),
    LocaleProfile(
        aliases=("india", "印度"),
        country_name="India",
        language_code="en",
        customer_terms={
            "school": ("dental college", "dental school", "faculty of dentistry"),
            "distributor": ("dental equipment distributor", "dental supplier", "dental dealer"),
            "clinic": ("dental clinic",),
        },
        product_terms={
            "dental simulator": ("dental simulator", "preclinical dental simulator", "phantom head dental"),
            "phantom head": ("phantom head dental",),
            "dental equipment": ("dental equipment",),
        },
        generic_contact_terms=("contact", "email", "phone"),
    ),
    LocaleProfile(
        aliases=("uae", "united arab emirates", "阿联酋"),
        country_name="UAE",
        language_code="ar",
        customer_terms={
            "school": ("كلية طب الأسنان", "جامعة طب الأسنان"),
            "distributor": ("موزع معدات طب الأسنان", "شركة معدات طب الأسنان", "مورد معدات طب الأسنان"),
            "clinic": ("عيادة أسنان",),
        },
        product_terms={
            "dental simulator": ("محاكي طب الأسنان", "معدات تدريب طب الأسنان", "phantom head dental"),
            "phantom head": ("phantom head dental",),
            "dental equipment": ("معدات طب الأسنان",),
        },
        generic_contact_terms=("اتصل", "البريد الإلكتروني", "هاتف"),
    ),
    LocaleProfile(
        aliases=("saudi arabia", "saudi", "沙特", "沙特阿拉伯"),
        country_name="Saudi Arabia",
        language_code="ar",
        customer_terms={
            "school": ("كلية طب الأسنان", "جامعة طب الأسنان"),
            "distributor": ("موزع معدات طب الأسنان", "شركة معدات طب الأسنان", "مورد معدات طب الأسنان"),
            "clinic": ("عيادة أسنان",),
        },
        product_terms={
            "dental simulator": ("محاكي طب الأسنان", "معدات تدريب طب الأسنان", "phantom head dental"),
            "phantom head": ("phantom head dental",),
            "dental equipment": ("معدات طب الأسنان",),
        },
        generic_contact_terms=("اتصل", "البريد الإلكتروني", "هاتف"),
    ),
    LocaleProfile(
        aliases=("mexico", "méxico", "墨西哥"),
        country_name="Mexico",
        language_code="es",
        customer_terms={
            "school": ("facultad de odontología", "escuela dental", "universidad odontológica"),
            "distributor": ("distribuidor de equipo dental", "proveedor dental", "depósito dental"),
            "clinic": ("clínica dental",),
        },
        product_terms={
            "dental simulator": ("simulador dental", "equipo de simulación dental", "phantom head dental"),
            "phantom head": ("phantom head dental", "cabeza fantasma dental"),
            "dental equipment": ("equipo dental",),
        },
        generic_contact_terms=("contacto", "correo", "teléfono"),
    ),
    LocaleProfile(
        aliases=("brazil", "brasil", "巴西"),
        country_name="Brazil",
        language_code="pt",
        customer_terms={
            "school": ("faculdade de odontologia", "escola de odontologia", "universidade odontologia"),
            "distributor": ("distribuidor de equipamentos odontológicos", "fornecedor odontológico", "dental distribuidora"),
            "clinic": ("clínica odontológica",),
        },
        product_terms={
            "dental simulator": ("simulador odontológico", "equipamento de simulação odontológica", "phantom head odontológico"),
            "phantom head": ("phantom head odontológico",),
            "dental equipment": ("equipamentos odontológicos",),
        },
        generic_contact_terms=("contato", "email", "telefone"),
    ),
)


class LocaleKeywordExpander:
    """Expand user/LLM keywords with local-language discovery phrases."""

    def expand(
        self,
        *,
        base_keywords: list[str],
        target_regions: list[str],
        customer_profile: str = "",
        product_keywords: list[str] | None = None,
        hard_filters: dict[str, Any] | None = None,
        max_keywords: int = 18,
    ) -> list[str]:
        max_keywords = max(1, int(max_keywords or 18))
        product_keywords = product_keywords or []
        profiles = self.profiles_for_regions(target_regions)
        values: list[str] = []
        values.extend(_clean_list(base_keywords))
        for profile in profiles:
            values.extend(self._profile_queries(profile, customer_profile, product_keywords, hard_filters or {}))
        return _dedupe(values)[:max_keywords]

    def profiles_for_regions(self, target_regions: list[str]) -> list[LocaleProfile]:
        profiles: list[LocaleProfile] = []
        seen: set[str] = set()
        for region in target_regions or []:
            key = _normalize(region)
            for profile in LOCALE_PROFILES:
                if key in {_normalize(alias) for alias in profile.aliases} and profile.country_name not in seen:
                    seen.add(profile.country_name)
                    profiles.append(profile)
        return profiles

    def _profile_queries(
        self,
        profile: LocaleProfile,
        customer_profile: str,
        product_keywords: list[str],
        hard_filters: dict[str, Any],
    ) -> list[str]:
        customer_terms = self._customer_terms(profile, customer_profile)
        product_terms = self._product_terms(profile, product_keywords)
        if not customer_terms:
            customer_terms = [term for values in profile.customer_terms.values() for term in values[:1]]
        if not product_terms:
            product_terms = [term for values in profile.product_terms.values() for term in values[:1]]

        queries: list[str] = []
        for customer in customer_terms[:4]:
            queries.append(f"{customer} {profile.country_name}")
        for product in product_terms[:4]:
            for customer in customer_terms[:2]:
                queries.append(f"{product} {customer} {profile.country_name}")
        if hard_filters.get("require_instagram"):
            for term in [*customer_terms[:2], *product_terms[:2]]:
                queries.append(f"site:instagram.com {term} {profile.country_name}")
        if hard_filters.get("require_facebook"):
            for term in [*customer_terms[:2], *product_terms[:2]]:
                queries.append(f"site:facebook.com {term} {profile.country_name}")
        if hard_filters.get("require_email") or hard_filters.get("require_phone"):
            contact = " OR ".join(profile.generic_contact_terms[:2])
            for term in customer_terms[:2]:
                queries.append(f"{term} {contact} {profile.country_name}")
        return queries

    @staticmethod
    def _customer_terms(profile: LocaleProfile, customer_profile: str) -> list[str]:
        text = _normalize(customer_profile)
        selected: list[str] = []
        if any(token in text for token in ("school", "college", "university", "training", "学校", "大学", "学院")):
            selected.extend(profile.customer_terms.get("school", ()))
        if any(token in text for token in ("distributor", "dealer", "supplier", "wholesale", "经销", "代理", "供应")):
            selected.extend(profile.customer_terms.get("distributor", ()))
        if any(token in text for token in ("clinic", "诊所")):
            selected.extend(profile.customer_terms.get("clinic", ()))
        return _dedupe(selected)

    @staticmethod
    def _product_terms(profile: LocaleProfile, product_keywords: list[str]) -> list[str]:
        text = _normalize(" ".join(product_keywords))
        selected: list[str] = []
        if any(token in text for token in ("dental simulator", "simulator", "simulation", "模拟")):
            selected.extend(profile.product_terms.get("dental simulator", ()))
        if "phantom" in text:
            selected.extend(profile.product_terms.get("phantom head", ()))
        if any(token in text for token in ("dental equipment", "equipment", "牙科设备", "设备")):
            selected.extend(profile.product_terms.get("dental equipment", ()))
        return _dedupe(selected)


def _clean_list(values: list[str]) -> list[str]:
    return [str(value or "").strip() for value in values if str(value or "").strip()]


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        clean = str(value or "").strip()
        key = _normalize(clean)
        if clean and key not in seen:
            seen.add(key)
            result.append(clean)
    return result
