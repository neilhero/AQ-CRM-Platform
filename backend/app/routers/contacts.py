from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional
from app.database import get_db
from app.models import Contact
from app.schemas import ContactCreate, ContactUpdate
from app.routers.utils import require_user

router = APIRouter()

@router.get("")
def list_contacts(customer_id: Optional[int]=Query(None), partner_id: Optional[int]=Query(None),
                  skip: int=Query(0,ge=0), limit: int=Query(100,ge=1,le=500),
                  db: Session=Depends(get_db), user=Depends(require_user)):
    q = db.query(Contact)
    if customer_id: q = q.filter(Contact.customer_id == customer_id)
    if partner_id: q = q.filter(Contact.partner_id == partner_id)
    return q.offset(skip).limit(limit).all()

@router.get("/{cid}")
def get_contact(cid: int, db: Session=Depends(get_db), user=Depends(require_user)):
    c = db.query(Contact).filter_by(id=cid).first()
    if not c: raise HTTPException(404, "Not found")
    return c

@router.post("", status_code=201)
def create_contact(data: ContactCreate, db: Session=Depends(get_db), user=Depends(require_user)):
    c = Contact(**data.model_dump())
    db.add(c); db.commit(); db.refresh(c); return c

@router.put("/{cid}")
def update_contact(cid: int, data: ContactUpdate, db: Session=Depends(get_db), user=Depends(require_user)):
    c = db.query(Contact).filter_by(id=cid).first()
    if not c: raise HTTPException(404, "Not found")
    for k,v in data.model_dump(exclude_unset=True).items(): setattr(c,k,v)
    db.commit(); db.refresh(c); return c

@router.delete("/{cid}", status_code=204)
def delete_contact(cid: int, db: Session=Depends(get_db), user=Depends(require_user)):
    c = db.query(Contact).filter_by(id=cid).first()
    if not c: raise HTTPException(404, "Not found")
    db.delete(c); db.commit()
