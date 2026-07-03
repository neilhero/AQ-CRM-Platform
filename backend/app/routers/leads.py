from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime, timezone, timedelta
from app.database import get_db
from app.models import Lead, LeadStatus, User, Customer, Opportunity
from app.schemas import LeadCreate, LeadUpdate
from app.routers.utils import require_user, require_admin

CST = timezone(timedelta(hours=8))
router = APIRouter()

@router.get("")
def list_leads(keyword: Optional[str]=Query(None), status: Optional[str]=Query(None),
               source: Optional[str]=Query(None), quality: Optional[str]=Query(None),
               skip: int=Query(0,ge=0), limit: int=Query(100,ge=1,le=500),
               db: Session=Depends(get_db), user=Depends(require_user)):
    q = db.query(Lead)
    if keyword: q = q.filter(Lead.name.contains(keyword))
    if status: q = q.filter(Lead.status == status)
    if source: q = q.filter(Lead.source == source)
    if quality: q = q.filter(Lead.quality == quality)
    results = q.order_by(Lead.created_at.desc()).offset(skip).limit(limit).all()
    out = []
    for l in results:
        d = {c.name: getattr(l, c.name) for c in l.__table__.columns}
        if l.assigned_to:
            u = db.query(User).filter_by(id=l.assigned_to).first()
            d["assigned_user_name"] = u.real_name if u else None
        d["source"] = l.source.value if l.source else None
        d["quality"] = l.quality.value if l.quality else None
        d["status"] = l.status.value if l.status else None
        out.append(d)
    return out

@router.get("/{lid}")
def get_lead(lid: int, db: Session=Depends(get_db), user=Depends(require_user)):
    l = db.query(Lead).filter_by(id=lid).first()
    if not l: raise HTTPException(404, "Not found")
    return l

@router.post("", status_code=201)
def create_lead(data: LeadCreate, db: Session=Depends(get_db), user=Depends(require_user)):
    kwargs = data.model_dump()
    l = Lead(**kwargs)
    db.add(l); db.commit(); db.refresh(l); return l

@router.put("/{lid}")
def update_lead(lid: int, data: LeadUpdate, db: Session=Depends(get_db), user=Depends(require_user)):
    l = db.query(Lead).filter_by(id=lid).first()
    if not l: raise HTTPException(404, "Not found")
    for k,v in data.model_dump(exclude_unset=True).items(): setattr(l,k,v)
    db.commit(); db.refresh(l); return l

@router.delete("/{lid}", status_code=204)
def delete_lead(lid: int, db: Session=Depends(get_db), admin=Depends(require_admin)):
    l = db.query(Lead).filter_by(id=lid).first()
    if not l: raise HTTPException(404, "Not found")
    db.delete(l); db.commit()

@router.post("/{lid}/convert")
def convert_lead(lid: int, sales_rep_id: Optional[int]=None, db: Session=Depends(get_db), user=Depends(require_user)):
    l = db.query(Lead).filter_by(id=lid).first()
    if not l: raise HTTPException(404, "Not found")
    cust = Customer(name=l.company or l.name, industry=l.industry or "")
    db.add(cust); db.flush()
    opp = Opportunity(name=l.name or "Converted lead", opp_type="direct",
                      sales_rep_id=sales_rep_id or user.id, customer_id=cust.id,
                      industry=l.industry, amount=0)
    db.add(opp); db.flush()
    l.status = LeadStatus.CONVERTED
    l.customer_id = cust.id
    l.opportunity_id = opp.id
    db.commit()
    return {"customer_id": cust.id, "opportunity_id": opp.id, "message": "Converted"}

@router.get("/stats/funnel")
def lead_funnel(db: Session=Depends(get_db), user=Depends(require_user)):
    total = db.query(Lead).count()
    stages = {}
    for s in LeadStatus:
        count = db.query(Lead).filter_by(status=s).count()
        stages[s.value] = count
    return {"total": total, "stages": stages}

@router.get("/sales/list")
def sales_list(db: Session=Depends(get_db), user=Depends(require_user)):
    users = db.query(User).filter_by(is_active=True).all()
    return [{"id": u.id, "username": u.username, "real_name": u.real_name, "role": u.role} for u in users]
