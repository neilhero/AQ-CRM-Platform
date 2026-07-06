import re
from typing import Optional

from sqlalchemy.orm import Session

from app.models import Customer


ORG_SUFFIXES = (
    "有限责任公司",
    "股份有限公司",
    "有限公司",
    "集团有限公司",
    "集团",
    "公司",
    "分公司",
    "子公司",
    "银行",
    "证券",
    "保险",
    "基金",
    "信托",
    "大学",
    "学院",
    "学校",
    "医院",
    "研究院",
    "研究所",
    "实验室",
    "数据局",
    "公安局",
    "财政局",
    "教育局",
    "交通局",
    "人社局",
    "大数据中心",
    "指挥中心",
    "信息中心",
    "中心",
    "委员会",
    "管委会",
    "办公室",
    "厅",
    "局",
    "委",
    "办",
)


INVALID_NAME_WORDS = ("测试", "test", "demo", "客户", "公司名", "未知", "无")


def normalize_company_name(name: Optional[str]) -> str:
    if not name:
        return ""
    value = str(name).strip()
    value = value.replace("（", "(").replace("）", ")")
    value = re.sub(r"\s+", "", value)
    return value


def validate_company_name_format(name: Optional[str]) -> tuple[bool, str, str]:
    normalized = normalize_company_name(name)
    if not normalized:
        return False, "请填写完整公司名。", normalized
    if len(normalized) < 4:
        return False, "公司名不完整，请填写完整公司名。", normalized
    lowered = normalized.lower()
    if any(word in lowered for word in INVALID_NAME_WORDS):
        return False, "公司名不完整，请填写真实、完整的公司全称。", normalized
    if not any(suffix in normalized for suffix in ORG_SUFFIXES):
        return False, "公司名不完整，请填写完整公司名，例如：杭州安泉数智科技有限公司。", normalized
    return True, "公司名格式通过。", normalized


def find_duplicate_customer(db: Session, normalized_name: str, exclude_id: Optional[int] = None) -> Optional[Customer]:
    if not normalized_name:
        return None
    rows = db.query(Customer).all()
    for row in rows:
        if exclude_id is not None and row.id == exclude_id:
            continue
        if normalize_company_name(row.name) == normalized_name:
            return row
    return None


def customer_owner_name(customer: Optional[Customer]) -> str:
    if not customer or not getattr(customer, "owner", None):
        return "其他人"
    owner = customer.owner
    return owner.real_name or owner.username or "其他人"
