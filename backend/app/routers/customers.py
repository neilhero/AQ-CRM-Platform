from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Customer, Opportunity
from app.permissions import can_access_customer, scoped_customer_query, scoped_opportunity_query
from app.routers.utils import require_user
from app.schemas import CustomerCreate, CustomerUpdate

router = APIRouter()


@router.get("")
def list_customers(
    keyword: Optional[str] = Query(None),
    industry: Optional[str] = Query(None),
    level: Optional[str] = Query(None),
    owner_id: Optional[int] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    user=Depends(require_user),
):
    q = scoped_customer_query(db.query(Customer), db, user)
    if owner_id is not None:
        q = q.filter(Customer.owner_id == owner_id)
    if keyword:
        q = q.filter(Customer.name.contains(keyword))
    if industry:
        q = q.filter(Customer.industry == industry)
    if level:
        q = q.filter(Customer.level == level)
    return q.order_by(Customer.updated_at.desc()).offset(skip).limit(limit).all()


def _check_cust(cid: int, db: Session, user):
    c = db.query(Customer).filter_by(id=cid).first()
    if not c:
        raise HTTPException(404, "Not found")
    if not can_access_customer(db, user, cid):
        raise HTTPException(403, "没有权限访问该客户")
    return c


@router.get("/{cid}")
def get_customer(cid: int, db: Session = Depends(get_db), user=Depends(require_user)):
    return _check_cust(cid, db, user)


@router.post("", status_code=201)
def create_customer(data: CustomerCreate, db: Session = Depends(get_db), user=Depends(require_user)):
    if db.query(Customer).filter_by(name=data.name).first():
        raise HTTPException(400, "Name exists")
    c = Customer(**data.model_dump(), owner_id=user.id)
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


@router.put("/{cid}")
def update_customer(cid: int, data: CustomerUpdate, db: Session = Depends(get_db), user=Depends(require_user)):
    c = _check_cust(cid, db, user)
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(c, k, v)
    db.commit()
    db.refresh(c)
    return c


@router.delete("/{cid}", status_code=204)
def delete_customer(cid: int, db: Session = Depends(get_db), user=Depends(require_user)):
    c = _check_cust(cid, db, user)
    db.delete(c)
    db.commit()


@router.get("/{cid}/opportunities")
def get_customer_opps(cid: int, db: Session = Depends(get_db), user=Depends(require_user)):
    _check_cust(cid, db, user)
    q = scoped_opportunity_query(db.query(Opportunity), db, user)
    return q.filter_by(customer_id=cid, is_closed=False).order_by(Opportunity.updated_at.desc()).all()


@router.get("/{cid}/stats")
def get_customer_stats(cid: int, db: Session = Depends(get_db), user=Depends(require_user)):
    _check_cust(cid, db, user)
    opps = scoped_opportunity_query(db.query(Opportunity), db, user).filter_by(customer_id=cid, is_closed=False)
    total = opps.count()
    amt = (
        scoped_opportunity_query(db.query(func.sum(Opportunity.amount)), db, user)
        .filter_by(customer_id=cid, is_closed=False)
        .scalar()
        or 0
    )
    return {"total_opportunities": total, "total_amount": round(amt, 1)}
