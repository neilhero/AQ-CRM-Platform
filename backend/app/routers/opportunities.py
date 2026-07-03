from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional
from sqlalchemy import func
from app.database import get_db
from app.models import Opportunity, Customer, ChannelPartner, User
from app.schemas import OpportunityCreate, OpportunityUpdate
from app.routers.utils import require_user

router = APIRouter()

def _apply_perm_filter(q, user):
    """Apply role-based permission filter to opportunity query."""
    if user.role == "admin":
        return q
    if user.role == "channel_manager":
        return q.filter(Opportunity.opp_type == "channel")
    # sales and others: only own opportunities
    return q.filter(Opportunity.sales_rep_id == user.id)

def _check_access(opp, user):
    """Check if user can access this opportunity. Raise 403 if not."""
    if user.role == "admin":
        return
    if user.role == "channel_manager":
        if opp.opp_type and opp.opp_type.value != "channel":
            raise HTTPException(403, "Access denied")
        return
    if opp.sales_rep_id != user.id:
        raise HTTPException(403, "Access denied")

@router.get("")
def list_opps(keyword: Optional[str]=Query(None), stage: Optional[str]=Query(None),
              opp_type: Optional[str]=Query(None), sales_rep_id: Optional[int]=Query(None),
              skip: int=Query(0,ge=0), limit: int=Query(100,ge=1,le=500),
              db: Session=Depends(get_db), user=Depends(require_user)):
    q = db.query(Opportunity)
    q = _apply_perm_filter(q, user)
    if keyword: q = q.filter(Opportunity.name.contains(keyword))
    if stage: q = q.filter(Opportunity.stage == stage)
    if opp_type: q = q.filter(Opportunity.opp_type == opp_type)
    if sales_rep_id: q = q.filter(Opportunity.sales_rep_id == sales_rep_id)
    results = q.order_by(Opportunity.updated_at.desc()).offset(skip).limit(limit).all()
    out = []
    for o in results:
        d = {c.name: getattr(o, c.name) for c in o.__table__.columns}
        if o.customer_id:
            cust = db.query(Customer).filter_by(id=o.customer_id).first()
            d["customer_name"] = cust.name if cust else None
        if o.channel_partner_id:
            cp = db.query(ChannelPartner).filter_by(id=o.channel_partner_id).first()
            d["channel_partner_name"] = cp.name if cp else None
        if o.sales_rep_id:
            sr = db.query(User).filter_by(id=o.sales_rep_id).first()
            d["sales_rep_name"] = sr.real_name if sr else None
        d["opp_type"] = o.opp_type.value if o.opp_type else None
        d["stage"] = o.stage.value if o.stage else None
        d["probability"] = o.probability.value if o.probability else None
        out.append(d)
    return out

@router.get("/{oid}")
def get_opp(oid: int, db: Session=Depends(get_db), user=Depends(require_user)):
    o = db.query(Opportunity).filter_by(id=oid).first()
    if not o: raise HTTPException(404, "Not found")
    _check_access(o, user)
    d = {c.name: getattr(o, c.name) for c in o.__table__.columns}
    if o.customer_id:
        cust = db.query(Customer).filter_by(id=o.customer_id).first()
        d["customer_name"] = cust.name if cust else None
    if o.channel_partner_id:
        cp = db.query(ChannelPartner).filter_by(id=o.channel_partner_id).first()
        d["channel_partner_name"] = cp.name if cp else None
    if o.sales_rep_id:
        sr = db.query(User).filter_by(id=o.sales_rep_id).first()
        d["sales_rep_name"] = sr.real_name if sr else None
    d["opp_type"] = o.opp_type.value if o.opp_type else None
    d["stage"] = o.stage.value if o.stage else None
    d["probability"] = o.probability.value if o.probability else None
    return d

@router.post("", status_code=201)
def create_opp(data: OpportunityCreate, db: Session=Depends(get_db), user=Depends(require_user)):
    kwargs = data.model_dump()
    if kwargs.get("opp_type") == "channel":
        kwargs["opp_type"] = "channel"
    else:
        kwargs["opp_type"] = "direct"
    # Force sales_rep_id to current user for non-admin
    if user.role != "admin":
        kwargs["sales_rep_id"] = user.id
    o = Opportunity(**kwargs)
    db.add(o); db.commit(); db.refresh(o); return {"id": o.id, "name": o.name}

@router.put("/{oid}")
def update_opp(oid: int, data: OpportunityUpdate, db: Session=Depends(get_db), user=Depends(require_user)):
    o = db.query(Opportunity).filter_by(id=oid).first()
    if not o: raise HTTPException(404, "Not found")
    _check_access(o, user)
    for k,v in data.model_dump(exclude_unset=True).items(): setattr(o,k,v)
    db.commit(); db.refresh(o); return {"message": "updated"}

@router.delete("/{oid}", status_code=204)
def delete_opp(oid: int, db: Session=Depends(get_db), user=Depends(require_user)):
    o = db.query(Opportunity).filter_by(id=oid).first()
    if not o: raise HTTPException(404, "Not found")
    _check_access(o, user)
    db.delete(o); db.commit()

@router.get("/stats/summary")
def stats(db: Session=Depends(get_db), user=Depends(require_user)):
    q = db.query(Opportunity)
    q = _apply_perm_filter(q, user)
    total = q.count()
    active = q.filter(Opportunity.is_closed == False).count()
    total_amt = _apply_perm_filter(db.query(func.sum(Opportunity.amount)), user).filter(Opportunity.is_closed == False).scalar() or 0
    return {"total": total, "active": active, "total_amount": round(total_amt,1)}
