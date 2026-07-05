from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Contact, Customer
from app.permissions import can_access_customer, scoped_customer_query
from app.routers.utils import require_user
from app.schemas import ContactCreate, ContactUpdate

router = APIRouter()


def _check_contact_access(contact_id: int, db: Session, user):
    c = db.query(Contact).filter_by(id=contact_id).first()
    if not c:
        raise HTTPException(404, "Not found")
    if c.customer_id and can_access_customer(db, user, c.customer_id):
        return c
    if c.partner_id:
        return c
    raise HTTPException(403, "Access denied")


@router.get("")
def list_contacts(
    customer_id: Optional[int] = Query(None),
    partner_id: Optional[int] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    user=Depends(require_user),
):
    q = db.query(Contact)
    if customer_id:
        if not can_access_customer(db, user, customer_id):
            raise HTTPException(403, "Access denied")
        q = q.filter(Contact.customer_id == customer_id)
    elif partner_id:
        q = q.filter(Contact.partner_id == partner_id)
    else:
        customer_ids = [c.id for c in scoped_customer_query(db.query(Customer), db, user).all()]
        q = q.filter(Contact.customer_id.in_(customer_ids or [-1]))
    return q.offset(skip).limit(limit).all()


@router.get("/{cid}")
def get_contact(cid: int, db: Session = Depends(get_db), user=Depends(require_user)):
    return _check_contact_access(cid, db, user)


@router.post("", status_code=201)
def create_contact(data: ContactCreate, db: Session = Depends(get_db), user=Depends(require_user)):
    if data.customer_id:
        cust = db.query(Customer).filter_by(id=data.customer_id).first()
        if not cust:
            raise HTTPException(404, "Customer not found")
        if not can_access_customer(db, user, data.customer_id):
            raise HTTPException(403, "Access denied")
    c = Contact(**data.model_dump())
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


@router.put("/{cid}")
def update_contact(cid: int, data: ContactUpdate, db: Session = Depends(get_db), user=Depends(require_user)):
    c = _check_contact_access(cid, db, user)
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(c, k, v)
    db.commit()
    db.refresh(c)
    return c


@router.delete("/{cid}", status_code=204)
def delete_contact(cid: int, db: Session = Depends(get_db), user=Depends(require_user)):
    c = _check_contact_access(cid, db, user)
    db.delete(c)
    db.commit()
