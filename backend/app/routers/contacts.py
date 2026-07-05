from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional
from app.database import get_db
from app.models import Contact, Customer
from app.permissions import can_view_all_sales_data, is_channel_only
from app.schemas import ContactCreate, ContactUpdate
from app.routers.utils import require_user

router = APIRouter()

def _check_contact_access(contact_id: int, db: Session, user):
    """Verify user can access this contact. Returns the contact."""
    c = db.query(Contact).filter_by(id=contact_id).first()
    if not c:
        raise HTTPException(404, "Not found")
    if can_view_all_sales_data(user):
        return c
    # Check via customer ownership
    if c.customer_id:
        cust = db.query(Customer).filter_by(id=c.customer_id).first()
        if cust and (is_channel_only(user) or cust.owner_id == user.id):
            return c
    # Check via channel partner - for channel managers
    if c.partner_id and is_channel_only(user):
        return c
    raise HTTPException(403, "Access denied")

@router.get("")
def list_contacts(customer_id: Optional[int]=Query(None), partner_id: Optional[int]=Query(None),
                  skip: int=Query(0,ge=0), limit: int=Query(100,ge=1,le=500),
                  db: Session=Depends(get_db), user=Depends(require_user)):
    q = db.query(Contact)
    if customer_id: q = q.filter(Contact.customer_id == customer_id)
    if partner_id: q = q.filter(Contact.partner_id == partner_id)
    # Non-admin: only show contacts of customers they own
    if not can_view_all_sales_data(user):
        if is_channel_only(user) and partner_id:
            return q.offset(skip).limit(limit).all()
        owned_cust_ids = [c.id for c in db.query(Customer).filter(Customer.owner_id == user.id).all()]
        q = q.filter(Contact.customer_id.in_(owned_cust_ids) if owned_cust_ids else Contact.customer_id == -1)
    return q.offset(skip).limit(limit).all()

@router.get("/{cid}")
def get_contact(cid: int, db: Session=Depends(get_db), user=Depends(require_user)):
    return _check_contact_access(cid, db, user)

@router.post("", status_code=201)
def create_contact(data: ContactCreate, db: Session=Depends(get_db), user=Depends(require_user)):
    if data.customer_id:
        cust = db.query(Customer).filter_by(id=data.customer_id).first()
        if not cust:
            raise HTTPException(404, "Customer not found")
        if not can_view_all_sales_data(user) and cust.owner_id != user.id:
            raise HTTPException(403, "Access denied")
    if data.partner_id and not (can_view_all_sales_data(user) or is_channel_only(user)):
        raise HTTPException(403, "Access denied")
    c = Contact(**data.model_dump())
    db.add(c); db.commit(); db.refresh(c); return c

@router.put("/{cid}")
def update_contact(cid: int, data: ContactUpdate, db: Session=Depends(get_db), user=Depends(require_user)):
    c = _check_contact_access(cid, db, user)
    for k,v in data.model_dump(exclude_unset=True).items(): setattr(c,k,v)
    db.commit(); db.refresh(c); return c

@router.delete("/{cid}", status_code=204)
def delete_contact(cid: int, db: Session=Depends(get_db), user=Depends(require_user)):
    c = _check_contact_access(cid, db, user)
    db.delete(c); db.commit()
