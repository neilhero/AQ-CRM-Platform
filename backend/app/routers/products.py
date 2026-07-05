from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session
from typing import Optional
from app.database import get_db
from app.models import Product
from app.schemas import ProductCreate, ProductUpdate
from app.routers.utils import require_user, require_admin

router = APIRouter()

PRODUCT_CATEGORIES = {
    "AI安全": ["大模型安全", "智能体安全"],
    "数据安全": ["WAAP", "WAF", "脱敏", "漏扫", "NGFW"],
    "AI教育": ["AI教学平台", "实训平台"],
}

@router.get("")
def list_products(keyword: Optional[str]=Query(None), category: Optional[str]=Query(None),
                  skip: int=Query(0,ge=0), limit: int=Query(100,ge=1,le=500),
                  db: Session=Depends(get_db), user=Depends(require_user)):
    q = db.query(Product)
    if keyword: q = q.filter(Product.name.contains(keyword))
    if category: q = q.filter(Product.category == category)
    return q.order_by(Product.name).offset(skip).limit(limit).all()

@router.get("/categories")
def list_categories(db: Session=Depends(get_db), user=Depends(require_user)):
    stats = {
        key: {
            "key": key,
            "label": key,
            "count": 0,
            "children": [{"key": sub, "label": sub, "count": 0} for sub in subs],
        }
        for key, subs in PRODUCT_CATEGORIES.items()
    }
    rows = (
        db.query(Product.category, Product.sub_category, func.count(Product.id))
        .group_by(Product.category, Product.sub_category)
        .all()
    )
    for category, sub_category, count in rows:
        if not category:
            continue
        if category not in stats:
            stats[category] = {"key": category, "label": category, "count": 0, "children": []}
        stats[category]["count"] += count
        if sub_category:
            child = next((item for item in stats[category]["children"] if item["key"] == sub_category), None)
            if child:
                child["count"] += count
            else:
                stats[category]["children"].append({"key": sub_category, "label": sub_category, "count": count})
    return list(stats.values())

@router.get("/{pid}")
def get_product(pid: int, db: Session=Depends(get_db), user=Depends(require_user)):
    p = db.query(Product).filter_by(id=pid).first()
    if not p: raise HTTPException(404, "Not found")
    return p

@router.post("", status_code=201)
def create_product(data: ProductCreate, db: Session=Depends(get_db), admin=Depends(require_admin)):
    if db.query(Product).filter_by(name=data.name).first(): raise HTTPException(400, "Name exists")
    p = Product(**data.model_dump())
    db.add(p); db.commit(); db.refresh(p); return p

@router.put("/{pid}")
def update_product(pid: int, data: ProductUpdate, db: Session=Depends(get_db), admin=Depends(require_admin)):
    p = db.query(Product).filter_by(id=pid).first()
    if not p: raise HTTPException(404, "Not found")
    for k,v in data.model_dump(exclude_unset=True).items(): setattr(p,k,v)
    db.commit(); db.refresh(p); return p

@router.put("/{pid}/classify")
def classify_product(pid: int, category: str=Query(...), sub_category: Optional[str]=Query(None),
                     db: Session=Depends(get_db), admin=Depends(require_admin)):
    p = db.query(Product).filter_by(id=pid).first()
    if not p: raise HTTPException(404, "Not found")
    p.category = category
    p.sub_category = sub_category
    db.commit(); db.refresh(p); return p

@router.delete("/{pid}", status_code=204)
def delete_product(pid: int, db: Session=Depends(get_db), admin=Depends(require_admin)):
    p = db.query(Product).filter_by(id=pid).first()
    if not p: raise HTTPException(404, "Not found")
    db.delete(p); db.commit()
