from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime, timezone, timedelta, date
from app.database import get_db
from app.models import FollowUp, Opportunity, User
from app.routers.utils import require_user

CST = timezone(timedelta(hours=8))
router = APIRouter()

def _opp_perm_filter(q, user):
    if user.role == "admin": return q
    if user.role == "channel_manager": return q.filter(Opportunity.opp_type == "channel")
    return q.filter(Opportunity.sales_rep_id == user.id)

@router.get("")
def list_followups(opportunity_id: Optional[int]=Query(None),
                   skip: int=Query(0,ge=0), limit: int=Query(50,ge=1,le=200),
                   db: Session=Depends(get_db), user=Depends(require_user)):
    q = db.query(FollowUp)
    if opportunity_id: q = q.filter(FollowUp.opportunity_id == opportunity_id)
    # Filter to only follow-ups for opportunities user can access
    q = q.join(Opportunity, FollowUp.opportunity_id == Opportunity.id)
    q = _opp_perm_filter(q, user)
    results = q.order_by(FollowUp.created_at.desc()).offset(skip).limit(limit).all()
    out = []
    for f in results:
        d = {"id": f.id, "opportunity_id": f.opportunity_id, "content": f.content,
             "contact_person": f.contact_person, "created_at": str(f.created_at)}
        if f.creator_id:
            u = db.query(User).filter_by(id=f.creator_id).first()
            d["creator_name"] = u.real_name if u else "Unknown"
        out.append(d)
    return out

@router.post("", status_code=201)
def create_followup(opportunity_id: int, content: str = "", contact_person: Optional[str] = None,
                    db: Session = Depends(get_db), user=Depends(require_user)):
    # Check access to the opportunity
    opp = db.query(Opportunity).filter_by(id=opportunity_id).first()
    if not opp: raise HTTPException(404, "Opportunity not found")
    if user.role != "admin":
        if user.role == "channel_manager" and opp.opp_type and opp.opp_type.value != "channel":
            raise HTTPException(403, "Access denied")
        if user.role not in ("admin", "channel_manager") and opp.sales_rep_id != user.id:
            raise HTTPException(403, "Access denied")
    fu = FollowUp(opportunity_id=opportunity_id, creator_id=user.id,
                  content=content, contact_person=contact_person, created_at=datetime.now(CST))
    db.add(fu)
    opp.updated_at = date.today()
    db.commit()
    db.refresh(fu)
    return {"id": fu.id, "message": "created"}

@router.get("/today")
def today_followups(db: Session=Depends(get_db), user=Depends(require_user)):
    opps = _opp_perm_filter(db.query(Opportunity).filter_by(is_closed=False), user).all()
    overdue = []; today_list = []; upcoming = []
    for o in opps:
        if o.next_follow_up_date:
            nfd = o.next_follow_up_date
            info = {"id": o.id, "name": o.name, "next_follow_up_date": str(nfd),
                    "stage": o.stage.value if o.stage else "1",
                    "customer_name": "", "amount": o.amount or 0}
            if o.sales_rep_id:
                c = db.query(User).filter_by(id=o.sales_rep_id).first()
                info["sales_rep_name"] = c.real_name if c else ""
            today = date.today()
            if nfd < today:
                info["days_overdue"] = (today - nfd).days
                overdue.append(info)
            elif nfd == today:
                today_list.append(info)
            elif nfd <= today + timedelta(days=7):
                upcoming.append(info)
    return {
        "overdue": overdue, "today": today_list, "upcoming": upcoming,
        "overdue_count": len(overdue), "today_count": len(today_list),
        "upcoming_count": len(upcoming), "total": len(overdue) + len(today_list) + len(upcoming)
    }

@router.post("/{fid}/quick-log")
def quick_log(fid: int, content: str="", db: Session=Depends(get_db), user=Depends(require_user)):
    opp = db.query(Opportunity).filter_by(id=fid).first()
    if not opp: raise HTTPException(404, "Not found")
    if user.role != "admin":
        if user.role == "channel_manager" and opp.opp_type and opp.opp_type.value != "channel":
            raise HTTPException(403, "Access denied")
        if user.role not in ("admin", "channel_manager") and opp.sales_rep_id != user.id:
            raise HTTPException(403, "Access denied")
    fu = FollowUp(opportunity_id=fid, creator_id=user.id, content=content or "快捷跟进",
                  created_at=datetime.now(CST))
    db.add(fu)
    opp.updated_at = date.today()
    db.commit()
    return {"message": "logged"}
