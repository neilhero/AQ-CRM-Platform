from datetime import date, datetime, timezone, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import ChannelPartner, Customer, FollowUp, Lead, Opportunity, OpportunityType, User
from app.permissions import ROLE_ADMIN
from app.permissions import managed_user_ids, scoped_customer_query, scoped_lead_query, scoped_opportunity_query
from app.routers.utils import require_user

CST = timezone(timedelta(hours=8))
router = APIRouter()


def _perm_filter(q, db: Session, user):
    return scoped_opportunity_query(q, db, user)


def _customer_count(db: Session, user):
    return scoped_customer_query(db.query(Customer), db, user).count()


def _lead_count(db: Session, user):
    return scoped_lead_query(db.query(Lead), db, user).count()


@router.get("/stats")
def dashboard_stats(db: Session = Depends(get_db), user=Depends(require_user)):
    base = _perm_filter(db.query(Opportunity), db, user)
    total_opps = base.count()
    total_amount = base.with_entities(func.sum(Opportunity.amount)).scalar() or 0
    stage_dist = {}
    industry_dist = {}
    probability_dist = {}
    active_opps = base.filter(Opportunity.is_closed == False).all()
    for o in active_opps:
        stage = str(o.stage.value if o.stage else "1")
        stage_dist[stage] = stage_dist.get(stage, 0) + 1
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
            db,
            user,
        )
        .order_by(FollowUp.created_at.desc())
        .limit(8)
        .all()
    )
    recent_follow_ups = []
    for follow_up, opportunity, creator in recent_rows:
        recent_follow_ups.append(
            {
                "id": follow_up.id,
                "opportunity_id": follow_up.opportunity_id,
                "opportunity_name": opportunity.name if opportunity else "",
                "content": follow_up.content,
                "contact_person": follow_up.contact_person,
                "created_at": follow_up.created_at.isoformat() if follow_up.created_at else None,
                "creator_name": creator.real_name if creator else "",
            }
        )
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
        "recent_follow_ups": recent_follow_ups,
    }


@router.get("/sales-performance")
def sales_performance(period: str = Query("month"), db: Session = Depends(get_db), user=Depends(require_user)):
    user_ids = managed_user_ids(db, user)
    q = db.query(User).filter(User.is_active == True, User.role.in_(["sales", "channel_manager"]))
    if user_ids is not None:
        q = q.filter(User.id.in_(user_ids or [-1]))
    users = q.order_by(User.id).all()
    today = date.today()
    start = date(today.year, today.month, 1)
    if period == "quarter":
        start_month = ((today.month - 1) // 3) * 3 + 1
        start = date(today.year, start_month, 1)
    elif period == "year":
        start = date(today.year, 1, 1)
    result = []
    for u in users:
        base = _perm_filter(
            db.query(Opportunity).filter(Opportunity.sales_rep_id == u.id, Opportunity.created_at >= start),
            db,
            user,
        )
        opps = base.all()
        won = [o for o in opps if o.stage and str(o.stage.value) == "5"]
        opp_count = len(opps)
        won_count = len(won)
        total_amt = round(sum(o.amount or 0 for o in opps), 1)
        won_amt = round(sum(o.amount or 0 for o in won), 1)
        result.append(
            {
                "sales_rep_id": u.id,
                "sales_rep_name": u.real_name,
                "opp_count": opp_count,
                "won_count": won_count,
                "total_amount": total_amt,
                "won_amount": won_amt,
                "conversion_rate": round(won_count / opp_count * 100, 1) if opp_count > 0 else 0,
                "avg_deal_size": round(total_amt / won_count, 1) if won_count > 0 else 0,
            }
        )
    return sorted(result, key=lambda x: (x["total_amount"], x["won_amount"], x["opp_count"]), reverse=True)


@router.get("/partner-performance")
def partner_performance(period: str = Query("year"), db: Session = Depends(get_db), user=Depends(require_user)):
    today = date.today()
    start = None
    if period != "all":
        ndays = 30
        if period == "quarter":
            ndays = 90
        elif period == "year":
            ndays = 365
        start = today - timedelta(days=ndays)

    partner_q = db.query(ChannelPartner)
    if user.role != ROLE_ADMIN:
        partner_q = partner_q.filter(ChannelPartner.created_by == user.id)
    partners = partner_q.order_by(ChannelPartner.name).all()

    result = []
    for partner in partners:
        opp_q = db.query(Opportunity).filter(
            Opportunity.opp_type == OpportunityType.CHANNEL,
            Opportunity.channel_partner_id == partner.id,
        )
        if start:
            opp_q = opp_q.filter(Opportunity.created_at >= start)
        opp_q = _perm_filter(opp_q, db, user)
        opps = opp_q.all()
        won_opps = [o for o in opps if o.stage and str(o.stage.value) == "5"]
        sales_names = []
        for uid in sorted({o.sales_rep_id for o in opps if o.sales_rep_id}):
            sales = db.query(User).filter(User.id == uid).first()
            if sales:
                sales_names.append(sales.real_name or sales.username)
        result.append(
            {
                "partner_id": partner.id,
                "partner_name": partner.name,
                "level": partner.level,
                "region": partner.region,
                "completed_amount": round(sum(o.amount or 0 for o in won_opps), 1),
                "opp_count": len(opps),
                "total_amount": round(sum(o.amount or 0 for o in opps), 1),
                "sales_names": "、".join(sales_names) if sales_names else "-",
            }
        )
    return sorted(result, key=lambda x: (x["completed_amount"], x["total_amount"], x["opp_count"]), reverse=True)
