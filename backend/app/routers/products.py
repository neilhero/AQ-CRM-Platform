from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session
from typing import Optional
from app.database import get_db
from app.models import Product, ProductSubCategory
from app.schemas import ProductCreate, ProductUpdate
from app.routers.utils import require_user, require_admin

router = APIRouter()

PRODUCT_CATEGORIES = {
    "AI安全": ["大模型安全", "智能体安全"],
    "数据安全": ["WAAP", "WAF", "脱敏", "漏扫", "NGFW", "DLP"],
    "AI教育": ["AI教学平台", "实训平台", "平台"],
}

def _seed_sub_categories(db: Session):
    changed = False
    for category, names in PRODUCT_CATEGORIES.items():
        for idx, name in enumerate(names):
            exists = db.query(ProductSubCategory).filter_by(category=category, name=name).first()
            if not exists:
                db.add(ProductSubCategory(category=category, name=name, sort_order=idx))
                changed = True
    if changed:
        db.commit()

def _next_product_order(db: Session, category: Optional[str]):
    if not category:
        return 0
    max_order = db.query(func.max(Product.sort_order)).filter(Product.category == category).scalar()
    return int(max_order or 0) + 1

@router.get("")
def list_products(keyword: Optional[str]=Query(None), category: Optional[str]=Query(None),
                  skip: int=Query(0,ge=0), limit: int=Query(100,ge=1,le=500),
                  db: Session=Depends(get_db), user=Depends(require_user)):
    q = db.query(Product)
    if keyword: q = q.filter(Product.name.contains(keyword))
    if category: q = q.filter(Product.category == category)
    return q.order_by(Product.category, Product.sort_order, Product.name).offset(skip).limit(limit).all()

@router.get("/categories")
def list_categories(db: Session=Depends(get_db), user=Depends(require_user)):
    _seed_sub_categories(db)
    stats = {
        key: {"key": key, "label": key, "count": 0, "children": []}
        for key in PRODUCT_CATEGORIES.keys()
    }
    sub_rows = (
        db.query(ProductSubCategory)
        .filter(ProductSubCategory.is_active == True)
        .order_by(ProductSubCategory.category, ProductSubCategory.sort_order, ProductSubCategory.id)
        .all()
    )
    for row in sub_rows:
        if row.category not in stats:
            stats[row.category] = {"key": row.category, "label": row.category, "count": 0, "children": []}
        stats[row.category]["children"].append({"id": row.id, "key": row.name, "label": row.name, "count": 0})

    count_rows = (
        db.query(Product.category, Product.sub_category, func.count(Product.id))
        .group_by(Product.category, Product.sub_category)
        .all()
    )
    for category, sub_category, count in count_rows:
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
                stats[category]["children"].append({"id": None, "key": sub_category, "label": sub_category, "count": count})
    return list(stats.values())

@router.post("/sub-categories", status_code=201)
def create_sub_category(data: dict=Body(...), db: Session=Depends(get_db), admin=Depends(require_admin)):
    category = (data.get("category") or "").strip()
    name = (data.get("name") or "").strip()
    if not category or not name:
        raise HTTPException(400, "Category and name required")
    exists = db.query(ProductSubCategory).filter_by(category=category, name=name).first()
    if exists:
        if exists.is_active:
            raise HTTPException(400, "Sub category exists")
        exists.is_active = True
        db.commit(); db.refresh(exists)
        return {"id": exists.id, "category": exists.category, "name": exists.name, "sort_order": exists.sort_order}
    max_order = db.query(func.max(ProductSubCategory.sort_order)).filter(ProductSubCategory.category == category).scalar()
    row = ProductSubCategory(category=category, name=name, sort_order=int(max_order or 0) + 1)
    db.add(row); db.commit(); db.refresh(row)
    return {"id": row.id, "category": row.category, "name": row.name, "sort_order": row.sort_order}

@router.put("/sub-categories/{sub_id}")
def update_sub_category(sub_id: int, data: dict=Body(...), db: Session=Depends(get_db), admin=Depends(require_admin)):
    row = db.query(ProductSubCategory).filter_by(id=sub_id).first()
    if not row:
        raise HTTPException(404, "Not found")
    name = (data.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "Name required")
    duplicate = (
        db.query(ProductSubCategory)
        .filter(ProductSubCategory.category == row.category, ProductSubCategory.name == name, ProductSubCategory.id != sub_id)
        .first()
    )
    if duplicate:
        raise HTTPException(400, "Sub category exists")
    old_name = row.name
    row.name = name
    for product in db.query(Product).filter(Product.category == row.category, Product.sub_category == old_name).all():
        product.sub_category = name
    db.commit(); db.refresh(row)
    return {"id": row.id, "category": row.category, "name": row.name, "sort_order": row.sort_order}

@router.delete("/sub-categories/{sub_id}")
def delete_sub_category(sub_id: int, db: Session=Depends(get_db), admin=Depends(require_admin)):
    row = db.query(ProductSubCategory).filter_by(id=sub_id).first()
    if not row:
        raise HTTPException(404, "Not found")
    for product in db.query(Product).filter(Product.category == row.category, Product.sub_category == row.name).all():
        product.sub_category = None
    row.is_active = False
    db.commit()
    return {"deleted": True}

@router.put("/reorder")
def reorder_products(data: dict=Body(...), db: Session=Depends(get_db), admin=Depends(require_admin)):
    product_ids = data.get("product_ids") or []
    for idx, pid in enumerate(product_ids):
        product = db.query(Product).filter_by(id=pid).first()
        if product:
            product.sort_order = idx
    db.commit()
    return {"updated": len(product_ids)}

@router.get("/{pid}")
def get_product(pid: int, db: Session=Depends(get_db), user=Depends(require_user)):
    p = db.query(Product).filter_by(id=pid).first()
    if not p: raise HTTPException(404, "Not found")
    return p

@router.post("", status_code=201)
def create_product(data: ProductCreate, db: Session=Depends(get_db), admin=Depends(require_admin)):
    if db.query(Product).filter_by(name=data.name).first(): raise HTTPException(400, "Name exists")
    payload = data.model_dump()
    if payload.get("category") and not payload.get("sort_order"):
        payload["sort_order"] = _next_product_order(db, payload.get("category"))
    p = Product(**payload)
    db.add(p); db.commit(); db.refresh(p); return p

@router.put("/{pid}")
def update_product(pid: int, data: ProductUpdate, db: Session=Depends(get_db), admin=Depends(require_admin)):
    p = db.query(Product).filter_by(id=pid).first()
    if not p: raise HTTPException(404, "Not found")
    updates = data.model_dump(exclude_unset=True)
    category_changed = "category" in updates and updates.get("category") != p.category
    for k,v in updates.items(): setattr(p,k,v)
    if category_changed:
        p.sort_order = _next_product_order(db, p.category)
    db.commit(); db.refresh(p); return p

@router.put("/{pid}/classify")
def classify_product(pid: int, category: str=Query(...), sub_category: Optional[str]=Query(None),
                     db: Session=Depends(get_db), admin=Depends(require_admin)):
    p = db.query(Product).filter_by(id=pid).first()
    if not p: raise HTTPException(404, "Not found")
    p.category = category
    p.sub_category = sub_category
    p.sort_order = _next_product_order(db, category)
    db.commit(); db.refresh(p); return p

@router.delete("/{pid}", status_code=204)
def delete_product(pid: int, db: Session=Depends(get_db), admin=Depends(require_admin)):
    p = db.query(Product).filter_by(id=pid).first()
    if not p: raise HTTPException(404, "Not found")
    db.delete(p); db.commit()
