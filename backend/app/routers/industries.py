from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional

from app.database import get_db
from app.models import IndustryConfig
from app.routers.utils import require_user, require_admin

router = APIRouter()

DEFAULT_INDUSTRIES = [
    "网信", "公安", "能源/电力", "运营商", "金融", "教育", "医疗", "交通",
    "企业", "政府", "测评机构", "政数（大数据局）", "其他",
]


class IndustryIn(BaseModel):
    name: str
    sort_order: Optional[int] = None
    is_active: Optional[bool] = True


class IndustryUpdate(BaseModel):
    name: Optional[str] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None


class IndustryReorderItem(BaseModel):
    id: int
    sort_order: int


def _seed_defaults(db: Session):
    if db.query(IndustryConfig).count() > 0:
        return
    for idx, name in enumerate(DEFAULT_INDUSTRIES, start=1):
        db.add(IndustryConfig(name=name, sort_order=idx, is_active=True))
    db.commit()


def _item(ind: IndustryConfig):
    return {
        "id": ind.id,
        "name": ind.name,
        "sort_order": ind.sort_order,
        "is_active": ind.is_active,
        "created_at": ind.created_at.isoformat() if ind.created_at else None,
    }


@router.get("")
def list_industries(include_inactive: bool = False, db: Session = Depends(get_db), user=Depends(require_user)):
    _seed_defaults(db)
    q = db.query(IndustryConfig)
    if not include_inactive:
        q = q.filter(IndustryConfig.is_active == True)
    rows = q.order_by(IndustryConfig.sort_order, IndustryConfig.id).all()
    return [_item(row) for row in rows]


@router.post("", status_code=201)
def create_industry(data: IndustryIn, db: Session = Depends(get_db), admin=Depends(require_admin)):
    _seed_defaults(db)
    name = data.name.strip()
    if not name:
        raise HTTPException(400, "行业名称不能为空")
    if db.query(IndustryConfig).filter(IndustryConfig.name == name).first():
        raise HTTPException(400, "行业名称已存在")
    max_order = db.query(IndustryConfig).count() + 1
    ind = IndustryConfig(name=name, sort_order=data.sort_order or max_order, is_active=data.is_active is not False)
    db.add(ind); db.commit(); db.refresh(ind)
    return _item(ind)


@router.put("/reorder")
def reorder_industries(items: list[IndustryReorderItem], db: Session = Depends(get_db), admin=Depends(require_admin)):
    _seed_defaults(db)
    by_id = {row.id: row for row in db.query(IndustryConfig).all()}
    for item in items:
        if item.id in by_id:
            by_id[item.id].sort_order = item.sort_order
    db.commit()
    return {"message": "updated"}


@router.put("/{industry_id}")
def update_industry(industry_id: int, data: IndustryUpdate, db: Session = Depends(get_db), admin=Depends(require_admin)):
    _seed_defaults(db)
    ind = db.query(IndustryConfig).filter_by(id=industry_id).first()
    if not ind:
        raise HTTPException(404, "行业不存在")
    patch = data.model_dump(exclude_unset=True)
    if "name" in patch and patch["name"] is not None:
        name = patch["name"].strip()
        if not name:
            raise HTTPException(400, "行业名称不能为空")
        exists = db.query(IndustryConfig).filter(IndustryConfig.name == name, IndustryConfig.id != industry_id).first()
        if exists:
            raise HTTPException(400, "行业名称已存在")
        ind.name = name
    if "sort_order" in patch and patch["sort_order"] is not None:
        ind.sort_order = patch["sort_order"]
    if "is_active" in patch and patch["is_active"] is not None:
        ind.is_active = patch["is_active"]
    db.commit(); db.refresh(ind)
    return _item(ind)


@router.delete("/{industry_id}", status_code=204)
def delete_industry(industry_id: int, db: Session = Depends(get_db), admin=Depends(require_admin)):
    ind = db.query(IndustryConfig).filter_by(id=industry_id).first()
    if not ind:
        raise HTTPException(404, "行业不存在")
    db.delete(ind); db.commit()
