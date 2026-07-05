from datetime import date, datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import FollowUp, Opportunity, User
from app.permissions import can_access_opportunity, scoped_opportunity_query
from app.routers.utils import require_user

CST = timezone(timedelta(hours=8))
router = APIRouter()


class QuickLogReq(BaseModel):
    content: str = ""
    contact_person: Optional[str] = None
    complete_reminder: bool = False


def _opp_perm_filter(q, db: Session, user):
    return scoped_opportunity_query(q, db, user)


def _check_opp_access(opp, db: Session, user):
    if not can_access_opportunity(db, user, opp.id):
        raise HTTPException(403, "Access denied")


@router.get("")
def list_followups(
    opportunity_id: Optional[int] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    user=Depends(require_user),
):
    q = db.query(FollowUp)
    if opportunity_id:
        q = q.filter(FollowUp.opportunity_id == opportunity_id)
    q = q.join(Opportunity, FollowUp.opportunity_id == Opportunity.id)
    q = _opp_perm_filter(q, db, user)
    results = q.order_by(FollowUp.created_at.desc()).offset(skip).limit(limit).all()
    out = []
    for f in results:
        d = {
            "id": f.id,
            "opportunity_id": f.opportunity_id,
            "content": f.content,
            "contact_person": f.contact_person,
            "created_at": str(f.created_at),
        }
        if f.creator_id:
            u = db.query(User).filter_by(id=f.creator_id).first()
            d["creator_name"] = u.real_name if u else "Unknown"
        out.append(d)
    return out


@router.post("", status_code=201)
def create_followup(
    opportunity_id: int,
    content: str = "",
    contact_person: Optional[str] = None,
    db: Session = Depends(get_db),
    user=Depends(require_user),
):
    opp = db.query(Opportunity).filter_by(id=opportunity_id).first()
    if not opp:
        raise HTTPException(404, "Opportunity not found")
    _check_opp_access(opp, db, user)
    fu = FollowUp(
        opportunity_id=opportunity_id,
        creator_id=user.id,
        content=content,
        contact_person=contact_person,
        created_at=datetime.now(CST),
    )
    db.add(fu)
    opp.updated_at = date.today()
    db.commit()
    db.refresh(fu)
    return {"id": fu.id, "message": "created"}


@router.get("/today")
def today_followups(db: Session = Depends(get_db), user=Depends(require_user)):
    opps = _opp_perm_filter(db.query(Opportunity).filter_by(is_closed=False), db, user).all()
    overdue = []
    today_list = []
    upcoming = []
    for o in opps:
        if o.next_follow_up_date:
            nfd = o.next_follow_up_date
            days_diff = (nfd - date.today()).days
            info = {
                "id": o.id,
                "name": o.name,
                "next_follow_up_date": str(nfd),
                "stage": o.stage.value if o.stage else "1",
                "customer_name": "",
                "amount": o.amount or 0,
                "days_diff": days_diff,
            }
            if o.sales_rep_id:
                c = db.query(User).filter_by(id=o.sales_rep_id).first()
                info["sales_rep_name"] = c.real_name if c else ""
            today = date.today()
            if nfd < today:
                info["days_overdue"] = abs(days_diff)
                overdue.append(info)
            elif nfd == today:
                today_list.append(info)
            elif nfd <= today + timedelta(days=7):
                upcoming.append(info)
    return {
        "overdue": overdue,
        "today": today_list,
        "upcoming": upcoming,
        "overdue_count": len(overdue),
        "today_count": len(today_list),
        "upcoming_count": len(upcoming),
        "total": len(overdue) + len(today_list) + len(upcoming),
    }


@router.post("/{fid}/quick-log")
def quick_log(fid: int, req: QuickLogReq, db: Session = Depends(get_db), user=Depends(require_user)):
    opp = db.query(Opportunity).filter_by(id=fid).first()
    if not opp:
        raise HTTPException(404, "Not found")
    _check_opp_access(opp, db, user)
    fu = FollowUp(
        opportunity_id=fid,
        creator_id=user.id,
        content=req.content or "快捷跟进",
        contact_person=req.contact_person,
        created_at=datetime.now(CST),
    )
    db.add(fu)
    opp.updated_at = date.today()
    if req.complete_reminder:
        opp.next_follow_up_date = None
    db.commit()
    return {"message": "logged", "follow_up_id": fu.id}
