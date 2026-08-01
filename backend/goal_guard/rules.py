"""Deterministic keyword rules for GoalGuard.

Rules are intentionally conservative. They enforce the user's requested buyer
type before contact/social completeness can influence ranking.
"""

from __future__ import annotations


DENTAL_MARKERS = (
    "dental", "dentistry", "dentist", "odont", "stomatology", "oral health",
    "牙科", "口腔", "nha khoa", "răng", "ทันต", "ทันตกรรม", "gigi", "pergigi",
)

SCHOOL_MARKERS = (
    "faculty of dentistry", "school of dentistry", "dental school", "dental college",
    "college of dentistry", "university", "faculty", "academy", "department of dentistry",
    "preclinical lab", "simulation lab", "teaching hospital", "牙科学校", "口腔学院",
    "牙科学院", "大学", "学院", "คณะทันตแพทยศาสตร์", "มหาวิทยาลัย", "สำนักวิชา",
)

TRAINING_MARKERS = (
    "training center", "simulation center", "education center", "course center",
    "phantom head lab", "preclinical training", "培训中心", "实训中心", "教学中心",
    "ศูนย์ฝึกอบรม", "ศูนย์การเรียน", "lab training",
)

DISTRIBUTOR_MARKERS = (
    "distributor", "dealer", "importer", "wholesaler", "reseller", "trader",
    "supplier", "authorized distributor", "agent", "distribution", "showroom",
    "经销", "代理", "进口商", "批发", "ตัวแทนจำหน่าย", "ผู้นำเข้า", "จำหน่าย",
)

MANUFACTURER_MARKERS = (
    "manufacturer", "factory", "producer", "manufacturing", "own brand", "oem factory",
    "made in", "生产商", "制造商", "工厂", "ผู้ผลิต", "โรงงาน",
)

CLINIC_MARKERS = (
    "dental clinic", "orthodontic clinic", "clinic", "dentist clinic", "private practice",
    "普通牙科诊所", "牙科诊所", "口腔诊所", "phòng khám nha khoa", "คลินิกทันตกรรม",
)

ASSOCIATION_MARKERS = (
    "association", "society", "council", "chamber", "สมาคม", "协会", "学会",
)

DIRECTORY_MARKERS = (
    "directory", "list of", "top 10", "yellow pages", "business listing", "supplier list",
    "目录", "名录", "รายชื่อ", "listing",
)

MEDIA_MARKERS = (
    "news", "article", "blog", "press release", "journal", "researchgate", "academia.edu",
    "wikipedia", "reddit", "ข่าว", "新闻", "博客",
)

REQUEST_SCHOOL_MARKERS = SCHOOL_MARKERS + TRAINING_MARKERS + ("school", "college", "training", "教育", "学校", "培训", "院校")
REQUEST_DISTRIBUTOR_MARKERS = DISTRIBUTOR_MARKERS + ("distribution", "channel partner", "渠道", "经销商", "代理商")
