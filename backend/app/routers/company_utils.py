from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.company_validation import (
    customer_owner_name,
    find_duplicate_customer,
    validate_company_name_format,
)
from app.database import get_db
from app.models import Customer
from app.routers.utils import require_user

router = APIRouter()


@router.get("/validate-company")
def validate_company(name: str = Query(..., min_length=1), db: Session = Depends(get_db), user=Depends(require_user)):
    format_ok, format_message, normalized = validate_company_name_format(name)
    if not format_ok:
        return {
            "valid": False,
            "format_valid": False,
            "exists": False,
            "message": format_message,
            "matched_customer": None,
            "similar": [],
        }

    existing = find_duplicate_customer(db, normalized)
    fuzzy = []
    if normalized:
        fuzzy = (
            db.query(Customer)
            .filter(Customer.name.contains(normalized))
            .limit(5)
            .all()
        )

    owner_name = customer_owner_name(existing) if existing else None
    if existing:
        message = f"该客户已由{owner_name}建过，请勿重复创建。"
    else:
        message = "公司名格式通过，客户名称可用。"

    return {
        "valid": format_ok and existing is None,
        "format_valid": format_ok,
        "exists": existing is not None,
        "message": message,
        "matched_customer": {"id": existing.id, "name": existing.name, "owner_name": owner_name} if existing else None,
        "similar": [{"id": item.id, "name": item.name} for item in fuzzy if not existing or item.id != existing.id],
    }
