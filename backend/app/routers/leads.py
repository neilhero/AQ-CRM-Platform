from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Customer, Lead, LeadStatus, Opportunity, User
from app.permissions import (
    ROLE_CHANNEL_MANAGER,
    ROLE_MANAGER,
    ROLE_SALES,
    can_access_lead,
    managed_user_ids,
    scoped_lead_query,
)
from app.routers.utils import require_user
from app.schemas import LeadCreate, LeadUpdate

CST = timezone(timedelta(hours=8))
router = APIRouter()


def _lead_perm_filter(q, db: Session, user):
    return scoped_lead_query(q, db, user)


def _check_lead_access(lead: Lead, db: Session, user):
    if not can_access_lead(db, user, lead.id):
        raise HTTPException(403, "Access denied")


@router.get("")
def list_leads(
    keyword: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    quality: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    user=Depends(require_user),
):
    q = _lead_perm_filter(db.query(Lead), db, user)
    if keyword:
        q = q.filter(Lead.name.contains(keyword))
    if status:
        q = q.filter(Lead.status == status)
    if source:
        q = q.filter(Lead.source == source)
    if quality:
        q = q.filter(Lead.quality == quality)
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


@router.get("/stats/funnel")
def lead_funnel(db: Session = Depends(get_db), user=Depends(require_user)):
    total = _lead_perm_filter(db.query(Lead), db, user).count()
    stages = {}
    for s in LeadStatus:
        stages[s.value] = _lead_perm_filter(db.query(Lead), db, user).filter_by(status=s).count()
    return {"total": total, "stages": stages}


@router.get("/sales/list")
def sales_list(db: Session = Depends(get_db), user=Depends(require_user)):
    users = (
        db.query(User)
        .filter(User.is_active == True, User.role.in_(["sales", "manager", "channel_manager"]))
        .order_by(User.id)
        .all()
    )
    return [{"id": u.id, "username": u.username, "real_name": u.real_name, "role": u.role} for u in users]


@router.get("/{lid}")
def get_lead(lid: int, db: Session = Depends(get_db), user=Depends(require_user)):
    l = db.query(Lead).filter_by(id=lid).first()
    if not l:
        raise HTTPException(404, "Not found")
    _check_lead_access(l, db, user)
    return l


@router.post("", status_code=201)
def create_lead(data: LeadCreate, db: Session = Depends(get_db), user=Depends(require_user)):
    kwargs = data.model_dump()
    if user.role in (ROLE_SALES, ROLE_CHANNEL_MANAGER):
        kwargs["assigned_to"] = user.id
    elif user.role == ROLE_MANAGER and kwargs.get("assigned_to") not in (managed_user_ids(db, user) or []):
        kwargs["assigned_to"] = user.id
    elif not kwargs.get("assigned_to"):
        kwargs["assigned_to"] = user.id
    if user.role == ROLE_CHANNEL_MANAGER:
        kwargs["source"] = "partner"
    l = Lead(**kwargs)
    db.add(l)
    db.commit()
    db.refresh(l)
    return l


@router.put("/{lid}")
def update_lead(lid: int, data: LeadUpdate, db: Session = Depends(get_db), user=Depends(require_user)):
    l = db.query(Lead).filter_by(id=lid).first()
    if not l:
        raise HTTPException(404, "Not found")
    _check_lead_access(l, db, user)
    updates = data.model_dump(exclude_unset=True)
    if "assigned_to" in updates and user.role == ROLE_MANAGER:
        if updates["assigned_to"] not in (managed_user_ids(db, user) or []):
            raise HTTPException(403, "只能分配给自己或管辖销售")
    elif "assigned_to" in updates and user.role in (ROLE_SALES, ROLE_CHANNEL_MANAGER):
        updates["assigned_to"] = user.id
    for k, v in updates.items():
        setattr(l, k, v)
    db.commit()
    db.refresh(l)
    return l


@router.delete("/{lid}", status_code=204)
def delete_lead(lid: int, db: Session = Depends(get_db), user=Depends(require_user)):
    l = db.query(Lead).filter_by(id=lid).first()
    if not l:
        raise HTTPException(404, "Not found")
    _check_lead_access(l, db, user)
    db.delete(l)
    db.commit()


@router.post("/{lid}/convert")
def convert_lead(
    lid: int,
    sales_rep_id: Optional[int] = None,
    db: Session = Depends(get_db),
    user=Depends(require_user),
):
    l = db.query(Lead).filter_by(id=lid).first()
    if not l:
        raise HTTPException(404, "Not found")
    _check_lead_access(l, db, user)
    owner_id = sales_rep_id or l.assigned_to or user.id
    if user.role == ROLE_MANAGER and owner_id not in (managed_user_ids(db, user) or []):
        raise HTTPException(403, "只能转给自己或管辖销售")
    if user.role in (ROLE_SALES, ROLE_CHANNEL_MANAGER):
        owner_id = user.id
    cust = Customer(name=l.company or l.name, industry=l.industry or "", owner_id=owner_id)
    db.add(cust)
    db.flush()
    opp = Opportunity(
        name=l.name or "Converted lead",
        opp_type="channel" if user.role == ROLE_CHANNEL_MANAGER else "direct",
        sales_rep_id=owner_id,
        customer_id=cust.id,
        industry=l.industry,
        amount=0,
    )
    db.add(opp)
    db.flush()
    l.status = LeadStatus.CONVERTED
    l.customer_id = cust.id
    l.opportunity_id = opp.id
    db.commit()
    return {"customer_id": cust.id, "opportunity_id": opp.id, "message": "Converted"}

