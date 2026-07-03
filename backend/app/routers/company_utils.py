from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Customer
from app.routers.utils import require_user

router = APIRouter()


@router.get("/validate-company")
def validate_company(name: str = Query(..., min_length=1), db: Session = Depends(get_db), user=Depends(require_user)):
    normalized = name.strip()
    existing = db.query(Customer).filter(Customer.name == normalized).first()
    fuzzy = []
    if normalized:
        fuzzy = (
            db.query(Customer)
            .filter(Customer.name.contains(normalized))
            .limit(5)
            .all()
        )
    return {
        "valid": existing is None,
        "exists": existing is not None,
        "message": "客户名称可用" if existing is None else "客户已存在",
        "matched_customer": {"id": existing.id, "name": existing.name} if existing else None,
        "verification_urls": [
            f"https://www.qcc.com/web/search?key={normalized}",
            f"https://www.tianyancha.com/search?key={normalized}",
        ],
        "similar": [{"id": item.id, "name": item.name} for item in fuzzy if not existing or item.id != existing.id],
    }
