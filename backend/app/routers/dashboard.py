from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import date, datetime, timezone, timedelta
from app.database import get_db
from app.models import Opportunity, Customer, Lead, User, FollowUp
from app.permissions import can_view_all_sales_data, is_channel_only
from app.routers.utils import require_user

CST = timezone(timedelta(hours=8))
router = APIRouter()

def _perm_filter(q, user):
    if can_view_all_sales_data(user): return q
    if is_channel_only(user): return q.filter(Opportunity.opp_type == "channel")
    return q.filter(Opportunity.sales_rep_id == user.id)

def _customer_count(db: Session, user):
    if can_view_all_sales_data(user):
        return db.query(Customer).count()
    return db.query(Customer).filter(Customer.owner_id == user.id).count()

def _lead_count(db: Session, user):
    if can_view_all_sales_data(user):
        return db.query(Lead).count()
    if is_channel_only(user):
        return db.query(Lead).filter(Lead.source == "partner").count()
    return db.query(Lead).filter(Lead.assigned_to == user.id).count()

@router.get("/stats")
def dashboard_stats(db: Session=Depends(get_db), user=Depends(require_user)):
    base = _perm_filter(db.query(Opportunity), user)
    total_opps = base.count()
    total_amount = base.with_entities(func.sum(Opportunity.amount)).scalar() or 0
    stage_dist = {}
    industry_dist = {}
    probability_dist = {}
    active_opps = base.filter(Opportunity.is_closed == False).all()
    for o in active_opps:
        s = str(o.stage.value if o.stage else "1")
        stage_dist[s] = stage_dist.get(s, 0) + 1
        industry = o.industry or "未分类"
        industry_dist[industry] = industry_dist.get(industry, 0) + 1
        probability = o.probability.value if o.probability else "LOW"
        probability_dist[probability] = probability_dist.get(probability, 0) + 1
    today = date.today()
    weekly_new = base.filter(Opportunity.created_at >= today - timedelta(days=7)).count()
    weekly_updated = base.filter(Opportunity.updated_at >= today).count()
    recent_rows = (
        _perm_filter(
            db.query(FollowUp, Opportunity, User)
            .join(Opportunity, FollowUp.opportunity_id == Opportunity.id)
            .outerjoin(User, FollowUp.creator_id == User.id),
            user,
        )
        .order_by(FollowUp.created_at.desc())
        .limit(8)
        .all()
    )
    recent_follow_ups = []
    for follow_up, opportunity, creator in recent_rows:
        recent_follow_ups.append({
            "id": follow_up.id,
            "opportunity_id": follow_up.opportunity_id,
            "opportunity_name": opportunity.name if opportunity else "",
            "content": follow_up.content,
            "contact_person": follow_up.contact_person,
            "created_at": follow_up.created_at.isoformat() if follow_up.created_at else None,
            "creator_name": creator.real_name if creator else "",
        })
    return {
        "total_opportunities": total_opps,
        "total_amount": round(total_amount, 1),
        "stage_distribution": stage_dist,
        "industry_distribution": industry_dist,
        "probability_distribution": probability_dist,
        "weekly_new": weekly_new,
        "weekly_updated": weekly_updated,
        "customer_count": _customer_count(db, user),
        "lead_count": _lead_count(db, user),
        "overdue_reminders": [],
        "upcoming_reminders": [],
        "recent_follow_ups": recent_follow_ups
    }

@router.get("/sales-performance")
def sales_performance(period: str=Query("month"), db: Session=Depends(get_db), user=Depends(require_user)):
    # Filter users: admin sees all, sales sees self, channel_manager sees all
    if can_view_all_sales_data(user):
        users = db.query(User).filter_by(is_active=True).all()
    elif is_channel_only(user):
        users = db.query(User).filter_by(is_active=True).all()
    else:
        users = [user]
    users = [
        u for u in users
        if (u.role or "").lower() != "admin" and (u.username or "").lower() != "admin"
    ]
    today = date.today()
    ndays = 30
    if period == "quarter": ndays = 90
    elif period == "year": ndays = 365
    start = today - timedelta(days=ndays)
    result = []
    for u in users:
        base = db.query(Opportunity).filter(Opportunity.sales_rep_id == u.id, Opportunity.created_at >= start)
        base = _perm_filter(base, user)
        opps = base.all()
        won = [o for o in opps if o.stage and str(o.stage.value) == "5"]
        opp_count = len(opps)
        won_count = len(won)
        total_amt = round(sum(o.amount or 0 for o in opps), 1)
        result.append({
            "sales_rep_id": u.id,
            "sales_rep_name": u.real_name,
            "opp_count": opp_count,
            "won_count": won_count,
            "total_amount": total_amt,
            "conversion_rate": round(won_count / opp_count * 100, 1) if opp_count > 0 else 0,
            "avg_deal_size": round(total_amt / won_count, 1) if won_count > 0 else 0
        })
    return sorted(result, key=lambda x: (x["total_amount"], x["opp_count"]), reverse=True)
