from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional
from app.database import get_db
from app.models import Product
from app.schemas import ProductCreate, ProductUpdate
from app.routers.utils import require_user, require_admin

router = APIRouter()

@router.get("")
def list_products(keyword: Optional[str]=Query(None), category: Optional[str]=Query(None),
                  skip: int=Query(0,ge=0), limit: int=Query(100,ge=1,le=500),
                  db: Session=Depends(get_db), user=Depends(require_user)):
    q = db.query(Product)
    if keyword: q = q.filter(Product.name.contains(keyword))
    if category: q = q.filter(Product.category == category)
    return q.order_by(Product.name).offset(skip).limit(limit).all()

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

@router.delete("/{pid}", status_code=204)
def delete_product(pid: int, db: Session=Depends(get_db), admin=Depends(require_admin)):
    p = db.query(Product).filter_by(id=pid).first()
    if not p: raise HTTPException(404, "Not found")
    db.delete(p); db.commit()
