from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import Optional
import csv
import io

from app.database import get_db
from app.models import Customer
from app.routers.utils import require_user

router = APIRouter()


@router.get("/customers")
def export_customers(
    ids: Optional[str] = Query(None),
    keyword: Optional[str] = Query(None),
    industry: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    user=Depends(require_user),
):
    q = db.query(Customer)
    if user.role != "admin":
        q = q.filter(Customer.owner_id == user.id)
    if ids:
        selected_ids = [int(x) for x in ids.split(",") if x.strip().isdigit()]
        q = q.filter(Customer.id.in_(selected_ids or [-1]))
    else:
        if keyword:
            q = q.filter(Customer.name.contains(keyword))
        if industry:
            q = q.filter(Customer.industry == industry)

    rows = q.order_by(Customer.updated_at.desc()).all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "客户名称", "行业", "地址", "网址", "客户等级", "描述", "创建时间", "更新时间"])
    for item in rows:
        writer.writerow([
            item.id,
            item.name,
            item.industry or "",
            item.address or "",
            item.website or "",
            item.level or "",
            item.description or "",
            item.created_at.strftime("%Y-%m-%d %H:%M:%S") if item.created_at else "",
            item.updated_at.strftime("%Y-%m-%d %H:%M:%S") if item.updated_at else "",
        ])
    data = io.BytesIO(output.getvalue().encode("utf-8-sig"))
    return StreamingResponse(
        data,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=customers.csv"},
    )
