from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    ChannelPartner,
    CommissionRule,
    Contact,
    Customer,
    CustomerOperationProfile,
    FollowUp,
    Lead,
    Opportunity,
    OpportunityReview,
    PartnerGrowthRecord,
    SalesTarget,
    User,
)
from app.routers.utils import require_admin, require_user

router = APIRouter()

PROBABILITY_WEIGHT = {"HIGH": 0.9, "MID_HIGH": 0.75, "MID": 0.55, "LOW": 0.25}
PROBABILITY_LABEL = {"HIGH": "高概率", "MID_HIGH": "中高概率", "MID": "中概率", "LOW": "低概率"}
STAGE_LABEL = {
    "1": "获取项目线索",
    "2": "见到用户/渠道",
    "3": "技术交流/试用",
    "4": "商务推进",
    "5": "成交",
}
SEGMENT_LABEL = {"strategic": "战略客户", "key": "重点客户", "normal": "普通客户", "dormant": "沉睡客户"}


class SalesTargetIn(BaseModel):
    sales_rep_id: int
    period_type: str = "quarter"
    period_label: str
    sales_target: float = 0
    collection_target: float = 0
    new_customer_target: int = 0
    channel_contribution_target: float = 0
    lead_conversion_target: float = 0
    win_rate_target: float = 0
    notes: Optional[str] = None


class SalesTargetPatch(BaseModel):
    sales_rep_id: Optional[int] = None
    period_type: Optional[str] = None
    period_label: Optional[str] = None
    sales_target: Optional[float] = None
    collection_target: Optional[float] = None
    new_customer_target: Optional[int] = None
    channel_contribution_target: Optional[float] = None
    lead_conversion_target: Optional[float] = None
    win_rate_target: Optional[float] = None
    notes: Optional[str] = None


class CustomerOperationIn(BaseModel):
    segment: str = "normal"
    owner_strategy: Optional[str] = None
    next_action: Optional[str] = None
    health_status: str = "normal"


class OpportunityReviewIn(BaseModel):
    opportunity_id: int
    result: str
    reason: Optional[str] = None
    competitor: Optional[str] = None
    price_gap: Optional[str] = None
    technical_gap: Optional[str] = None
    relationship_gap: Optional[str] = None
    product_feedback: Optional[str] = None
    market_feedback: Optional[str] = None
    review_date: Optional[date] = None


class OpportunityReviewPatch(BaseModel):
    result: Optional[str] = None
    reason: Optional[str] = None
    competitor: Optional[str] = None
    price_gap: Optional[str] = None
    technical_gap: Optional[str] = None
    relationship_gap: Optional[str] = None
    product_feedback: Optional[str] = None
    market_feedback: Optional[str] = None
    review_date: Optional[date] = None


class PartnerGrowthRecordIn(BaseModel):
    partner_id: int
    record_type: str
    title: str
    person_name: Optional[str] = None
    record_date: Optional[date] = None
    expiry_date: Optional[date] = None
    score: float = 0
    status: str = "valid"
    notes: Optional[str] = None


class PartnerGrowthRecordPatch(BaseModel):
    record_type: Optional[str] = None
    title: Optional[str] = None
    person_name: Optional[str] = None
    record_date: Optional[date] = None
    expiry_date: Optional[date] = None
    score: Optional[float] = None
    status: Optional[str] = None
    notes: Optional[str] = None


def _value(v):
    return v.value if hasattr(v, "value") else v


def _perm_filter(q, user):
    if user.role == "admin":
        return q
    if user.role == "channel_manager":
        return q.filter(Opportunity.opp_type == "channel")
    return q.filter(Opportunity.sales_rep_id == user.id)


def _check_opp_access(db: Session, opportunity_id: int, user):
    opp = _perm_filter(db.query(Opportunity).filter(Opportunity.id == opportunity_id), user).first()
    if not opp:
        raise HTTPException(403, "没有权限")
    return opp


def _date_range(period_label: Optional[str]):
    today = date.today()
    label = period_label or f"{today.year}Q{(today.month - 1) // 3 + 1}"
    try:
        if "Q" in label.upper():
            year, q = label.upper().split("Q", 1)
            year = int(year)
            q = int(q)
            start_month = (q - 1) * 3 + 1
            start = date(year, start_month, 1)
            end_month = start_month + 2
            next_month = date(year + (1 if end_month == 12 else 0), 1 if end_month == 12 else end_month + 1, 1)
            return label, start, next_month - timedelta(days=1)
        if len(label) == 4 and label.isdigit():
            year = int(label)
            return label, date(year, 1, 1), date(year, 12, 31)
        if "-" in label:
            year, month = [int(x) for x in label.split("-", 1)]
            start = date(year, month, 1)
            next_month = date(year + (1 if month == 12 else 0), 1 if month == 12 else month + 1, 1)
            return label, start, next_month - timedelta(days=1)
    except Exception:
        pass
    raise HTTPException(400, "period_label 格式应为 2026Q3、2026-07 或 2026")


def _forecast_category(opp):
    probability = _value(opp.probability) or "LOW"
    stage = _value(opp.stage) or "1"
    if probability == "HIGH" or stage == "4":
        return "commit"
    if probability in ("MID_HIGH", "MID") or stage == "3":
        return "best_case"
    return "pipeline"


def _group_value(opp, group_by, customer=None, partner=None, sales=None):
    if group_by == "region":
        return (partner.region if partner else None) or "未设置区域"
    if group_by == "industry":
        return opp.industry or (customer.industry if customer else None) or "未设置行业"
    if group_by == "product_line":
        return opp.required_product or "未设置产品线"
    if group_by == "sales":
        return (sales.real_name if sales else None) or "未设置销售"
    if group_by == "stage":
        stage = str(_value(opp.stage) or "1")
        return STAGE_LABEL.get(stage, stage)
    if group_by == "probability":
        prob = str(_value(opp.probability) or "LOW")
        return PROBABILITY_LABEL.get(prob, prob)
    return "全部"


def _target_dict(t: SalesTarget, user: Optional[User] = None):
    return {
        "id": t.id,
        "sales_rep_id": t.sales_rep_id,
        "sales_rep_name": user.real_name if user else None,
        "period_type": t.period_type,
        "period_label": t.period_label,
        "sales_target": t.sales_target or 0,
        "collection_target": t.collection_target or 0,
        "new_customer_target": t.new_customer_target or 0,
        "channel_contribution_target": t.channel_contribution_target or 0,
        "lead_conversion_target": t.lead_conversion_target or 0,
        "win_rate_target": t.win_rate_target or 0,
        "notes": t.notes,
    }


@router.get("/forecast")
def forecast(
    group_by: str = Query("sales", pattern="^(region|industry|product_line|sales|stage|probability)$"),
    period_label: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    user=Depends(require_user),
):
    label, start, end = _date_range(period_label)
    rows = (
        _perm_filter(
            db.query(Opportunity, Customer, ChannelPartner, User)
            .outerjoin(Customer, Opportunity.customer_id == Customer.id)
            .outerjoin(ChannelPartner, Opportunity.channel_partner_id == ChannelPartner.id)
            .outerjoin(User, Opportunity.sales_rep_id == User.id),
            user,
        )
        .filter(Opportunity.is_closed == False)
        .filter(or_(Opportunity.expected_close_date == None, Opportunity.expected_close_date.between(start, end)))
        .all()
    )
    buckets = {}
    totals = {"commit": 0.0, "best_case": 0.0, "pipeline": 0.0, "weighted": 0.0, "raw": 0.0}
    for opp, customer, partner, sales in rows:
        category = _forecast_category(opp)
        prob = _value(opp.probability) or "LOW"
        amount = float(opp.amount or 0)
        weighted = amount * PROBABILITY_WEIGHT.get(prob, 0.25)
        key = _group_value(opp, group_by, customer, partner, sales)
        bucket = buckets.setdefault(key, {"group": key, "opp_count": 0, "commit": 0.0, "best_case": 0.0, "pipeline": 0.0, "weighted": 0.0, "raw": 0.0})
        bucket["opp_count"] += 1
        bucket[category] += amount
        bucket["weighted"] += weighted
        bucket["raw"] += amount
        totals[category] += amount
        totals["weighted"] += weighted
        totals["raw"] += amount
    data = sorted(buckets.values(), key=lambda x: x["raw"], reverse=True)
    for row in data:
        for k in ("commit", "best_case", "pipeline", "weighted", "raw"):
            row[k] = round(row[k], 1)
    return {"period_label": label, "start_date": start, "end_date": end, "group_by": group_by, "totals": {k: round(v, 1) for k, v in totals.items()}, "items": data}


@router.get("/users")
def sales_users(db: Session = Depends(get_db), user=Depends(require_user)):
    q = db.query(User).filter(User.is_active == True)
    if user.role not in ("admin", "channel_manager"):
        q = q.filter(User.id == user.id)
    return [{"id": u.id, "username": u.username, "real_name": u.real_name, "role": u.role} for u in q.order_by(User.real_name).all()]


@router.get("/targets")
def list_targets(period_label: Optional[str] = None, db: Session = Depends(get_db), user=Depends(require_user)):
    q = db.query(SalesTarget, User).outerjoin(User, SalesTarget.sales_rep_id == User.id)
    if user.role != "admin":
        q = q.filter(SalesTarget.sales_rep_id == user.id)
    if period_label:
        q = q.filter(SalesTarget.period_label == period_label)
    return [_target_dict(t, u) for t, u in q.order_by(SalesTarget.period_label.desc(), User.real_name).all()]


@router.post("/targets", status_code=201)
def create_target(data: SalesTargetIn, db: Session = Depends(get_db), admin=Depends(require_admin)):
    if not db.query(User).filter_by(id=data.sales_rep_id).first():
        raise HTTPException(404, "销售不存在")
    target = SalesTarget(**data.model_dump())
    db.add(target)
    db.commit()
    db.refresh(target)
    return _target_dict(target, db.query(User).filter_by(id=target.sales_rep_id).first())


@router.get("/targets/summary")
def target_summary(period_label: Optional[str] = None, db: Session = Depends(get_db), user=Depends(require_user)):
    label, start, end = _date_range(period_label)
    rows = list_targets(label, db, user)
    result = []
    for row in rows:
        sales_id = row["sales_rep_id"]
        opps = db.query(Opportunity).filter(Opportunity.sales_rep_id == sales_id, Opportunity.created_at.between(start, end)).all()
        won = [o for o in opps if str(_value(o.stage)) == "5" or o.is_closed]
        leads = db.query(Lead).filter(Lead.assigned_to == sales_id, Lead.created_at >= start, Lead.created_at <= end).all()
        converted = [l for l in leads if str(_value(l.status)) == "converted" or l.opportunity_id]
        new_customers = db.query(Customer).filter(Customer.owner_id == sales_id, Customer.created_at >= start, Customer.created_at <= end).count()
        channel_amount = sum(o.amount or 0 for o in opps if str(_value(o.opp_type)) == "channel")
        total_amount = sum(o.amount or 0 for o in opps)
        won_amount = sum(o.amount or 0 for o in won)
        row.update({
            "actual_sales": round(total_amount, 1),
            "actual_collection": round(won_amount, 1),
            "actual_new_customers": new_customers,
            "actual_channel_contribution": round(channel_amount, 1),
            "actual_lead_conversion": round(len(converted) / len(leads) * 100, 1) if leads else 0,
            "actual_win_rate": round(len(won) / len(opps) * 100, 1) if opps else 0,
        })
        result.append(row)
    return {"period_label": label, "start_date": start, "end_date": end, "items": result}


@router.put("/targets/{target_id}")
def update_target(target_id: int, data: SalesTargetPatch, db: Session = Depends(get_db), admin=Depends(require_admin)):
    target = db.query(SalesTarget).filter_by(id=target_id).first()
    if not target:
        raise HTTPException(404, "目标不存在")
    patch = data.model_dump(exclude_unset=True)
    if "sales_rep_id" in patch and not db.query(User).filter_by(id=patch["sales_rep_id"]).first():
        raise HTTPException(404, "销售不存在")
    for k, v in patch.items():
        setattr(target, k, v)
    db.commit()
    db.refresh(target)
    return _target_dict(target, db.query(User).filter_by(id=target.sales_rep_id).first())


@router.delete("/targets/{target_id}", status_code=204)
def delete_target(target_id: int, db: Session = Depends(get_db), admin=Depends(require_admin)):
    target = db.query(SalesTarget).filter_by(id=target_id).first()
    if not target:
        raise HTTPException(404, "目标不存在")
    db.delete(target)
    db.commit()


@router.get("/customer-operations")
def customer_operations(db: Session = Depends(get_db), user=Depends(require_user)):
    customers = db.query(Customer).all() if user.role == "admin" else db.query(Customer).filter(Customer.owner_id == user.id).all()
    profiles = {p.customer_id: p for p in db.query(CustomerOperationProfile).all()}
    today = date.today()
    items = []
    alerts = []
    for customer in customers:
        profile = profiles.get(customer.id)
        opps = db.query(Opportunity).filter(Opportunity.customer_id == customer.id).all()
        amount = sum(o.amount or 0 for o in opps)
        latest_follow = (
            db.query(func.max(FollowUp.created_at))
            .join(Opportunity, FollowUp.opportunity_id == Opportunity.id)
            .filter(Opportunity.customer_id == customer.id)
            .scalar()
        )
        inferred = "strategic" if customer.level == "VIP" or amount >= 300 else "key" if customer.level == "A" or amount >= 100 else "normal"
        if latest_follow and (today - latest_follow.date()).days >= 90:
            inferred = "dormant"
        segment = profile.segment if profile else inferred
        active_opps = [o for o in opps if not o.is_closed]
        stale_opps = [o for o in active_opps if o.updated_at and (today - o.updated_at).days >= 30]
        if latest_follow is None or (today - latest_follow.date()).days >= 30:
            alerts.append({"type": "long_no_follow", "level": "warning", "customer_id": customer.id, "customer_name": customer.name, "message": "长期未跟进"})
        if segment in ("strategic", "key") and not active_opps:
            alerts.append({"type": "key_no_opportunity", "level": "warning", "customer_id": customer.id, "customer_name": customer.name, "message": "重点客户暂无活跃商机"})
        for opp in stale_opps:
            alerts.append({"type": "stale_opportunity", "level": "warning", "customer_id": customer.id, "customer_name": customer.name, "opportunity_id": opp.id, "opportunity_name": opp.name, "message": "商机久未推进"})
        items.append({
            "customer_id": customer.id,
            "customer_name": customer.name,
            "industry": customer.industry,
            "level": customer.level,
            "segment": segment,
            "segment_label": SEGMENT_LABEL.get(segment, segment),
            "owner_strategy": profile.owner_strategy if profile else None,
            "next_action": profile.next_action if profile else None,
            "health_status": profile.health_status if profile else ("risk" if stale_opps else "normal"),
            "active_opportunities": len(active_opps),
            "total_amount": round(amount, 1),
            "last_follow_up_at": latest_follow,
        })
    summary = {}
    for item in items:
        summary[item["segment"]] = summary.get(item["segment"], 0) + 1
    return {"summary": summary, "items": items, "alerts": alerts[:100]}


@router.put("/customer-operations/{customer_id}")
def upsert_customer_operation(customer_id: int, data: CustomerOperationIn, db: Session = Depends(get_db), user=Depends(require_user)):
    customer = db.query(Customer).filter_by(id=customer_id).first()
    if not customer:
        raise HTTPException(404, "客户不存在")
    if user.role != "admin" and customer.owner_id != user.id:
        raise HTTPException(403, "没有权限")
    profile = db.query(CustomerOperationProfile).filter_by(customer_id=customer_id).first()
    if not profile:
        profile = CustomerOperationProfile(customer_id=customer_id)
        db.add(profile)
    for k, v in data.model_dump().items():
        setattr(profile, k, v)
    db.commit()
    db.refresh(profile)
    return {"message": "updated", "customer_id": customer_id}


@router.get("/opportunity-reviews")
def list_reviews(opportunity_id: Optional[int] = None, db: Session = Depends(get_db), user=Depends(require_user)):
    q = db.query(OpportunityReview, Opportunity, User).join(Opportunity, OpportunityReview.opportunity_id == Opportunity.id).outerjoin(User, OpportunityReview.reviewer_id == User.id)
    q = _perm_filter(q, user)
    if opportunity_id:
        q = q.filter(OpportunityReview.opportunity_id == opportunity_id)
    rows = []
    for review, opp, reviewer in q.order_by(OpportunityReview.review_date.desc(), OpportunityReview.id.desc()).limit(200).all():
        rows.append({
            "id": review.id,
            "opportunity_id": review.opportunity_id,
            "opportunity_name": opp.name if opp else None,
            "result": review.result,
            "reason": review.reason,
            "competitor": review.competitor,
            "price_gap": review.price_gap,
            "technical_gap": review.technical_gap,
            "relationship_gap": review.relationship_gap,
            "product_feedback": review.product_feedback,
            "market_feedback": review.market_feedback,
            "reviewer_name": reviewer.real_name if reviewer else None,
            "review_date": review.review_date,
        })
    return rows


@router.post("/opportunity-reviews", status_code=201)
def create_review(data: OpportunityReviewIn, db: Session = Depends(get_db), user=Depends(require_user)):
    if not db.query(Opportunity).filter_by(id=data.opportunity_id).first():
        raise HTTPException(404, "商机不存在")
    opp = _check_opp_access(db, data.opportunity_id, user)
    review = OpportunityReview(**data.model_dump(exclude_unset=True), reviewer_id=user.id)
    if not review.review_date:
        review.review_date = date.today()
    db.add(review)
    if data.result in ("won", "lost"):
        opp.is_closed = True
        opp.closed_reason = data.reason
    db.commit()
    db.refresh(review)
    return {"id": review.id}


@router.put("/opportunity-reviews/{review_id}")
def update_review(review_id: int, data: OpportunityReviewPatch, db: Session = Depends(get_db), user=Depends(require_user)):
    review = db.query(OpportunityReview).filter_by(id=review_id).first()
    if not review:
        raise HTTPException(404, "复盘不存在")
    opp = _check_opp_access(db, review.opportunity_id, user)
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(review, k, v)
    if review.result in ("won", "lost") and opp:
        opp.is_closed = True
        opp.closed_reason = review.reason
    db.commit()
    return {"message": "updated"}


@router.delete("/opportunity-reviews/{review_id}", status_code=204)
def delete_review(review_id: int, db: Session = Depends(get_db), admin=Depends(require_admin)):
    review = db.query(OpportunityReview).filter_by(id=review_id).first()
    if not review:
        raise HTTPException(404, "复盘不存在")
    db.delete(review)
    db.commit()


@router.get("/partner-growth/summary")
def partner_growth_summary(db: Session = Depends(get_db), user=Depends(require_user)):
    partners = db.query(ChannelPartner).order_by(ChannelPartner.name).all()
    records = db.query(PartnerGrowthRecord).all()
    by_partner = {}
    for record in records:
        by_partner.setdefault(record.partner_id, []).append(record)
    rows = []
    for partner in partners:
        opps = db.query(Opportunity).filter(Opportunity.channel_partner_id == partner.id).all()
        amount = sum(o.amount or 0 for o in opps)
        won_amount = sum(o.amount or 0 for o in opps if str(_value(o.stage)) == "5" or o.is_closed)
        rule = db.query(CommissionRule).filter(CommissionRule.partner_id == partner.id).order_by(CommissionRule.id.desc()).first()
        rate = rule.rate_percent if rule else 0
        partner_records = by_partner.get(partner.id, [])
        rows.append({
            "partner_id": partner.id,
            "partner_name": partner.name,
            "level": partner.level,
            "authorized_region": partner.region,
            "status": partner.status,
            "opportunity_count": len(opps),
            "cumulative_performance": round(amount, 1),
            "won_performance": round(won_amount, 1),
            "rebate_rate": rate,
            "estimated_rebate": round(won_amount * rate / 100, 1),
            "certified_people": len([r for r in partner_records if r.record_type == "certification"]),
            "training_count": len([r for r in partner_records if r.record_type == "training"]),
            "violation_count": len([r for r in partner_records if r.record_type == "violation"]),
        })
    return rows


@router.get("/partner-growth/records")
def list_partner_records(partner_id: Optional[int] = None, record_type: Optional[str] = None, db: Session = Depends(get_db), user=Depends(require_user)):
    q = db.query(PartnerGrowthRecord, ChannelPartner).join(ChannelPartner, PartnerGrowthRecord.partner_id == ChannelPartner.id)
    if partner_id:
        q = q.filter(PartnerGrowthRecord.partner_id == partner_id)
    if record_type:
        q = q.filter(PartnerGrowthRecord.record_type == record_type)
    return [{
        "id": r.id,
        "partner_id": r.partner_id,
        "partner_name": p.name if p else None,
        "record_type": r.record_type,
        "title": r.title,
        "person_name": r.person_name,
        "record_date": r.record_date,
        "expiry_date": r.expiry_date,
        "score": r.score,
        "status": r.status,
        "notes": r.notes,
    } for r, p in q.order_by(PartnerGrowthRecord.record_date.desc(), PartnerGrowthRecord.id.desc()).limit(300).all()]


@router.post("/partner-growth/records", status_code=201)
def create_partner_record(data: PartnerGrowthRecordIn, db: Session = Depends(get_db), user=Depends(require_user)):
    if not db.query(ChannelPartner).filter_by(id=data.partner_id).first():
        raise HTTPException(404, "渠道伙伴不存在")
    record = PartnerGrowthRecord(**data.model_dump(exclude_unset=True), created_by=user.id)
    if not record.record_date:
        record.record_date = date.today()
    db.add(record)
    db.commit()
    db.refresh(record)
    return {"id": record.id}


@router.put("/partner-growth/records/{record_id}")
def update_partner_record(record_id: int, data: PartnerGrowthRecordPatch, db: Session = Depends(get_db), user=Depends(require_user)):
    record = db.query(PartnerGrowthRecord).filter_by(id=record_id).first()
    if not record:
        raise HTTPException(404, "记录不存在")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(record, k, v)
    db.commit()
    return {"message": "updated"}


@router.delete("/partner-growth/records/{record_id}", status_code=204)
def delete_partner_record(record_id: int, db: Session = Depends(get_db), admin=Depends(require_admin)):
    record = db.query(PartnerGrowthRecord).filter_by(id=record_id).first()
    if not record:
        raise HTTPException(404, "记录不存在")
    db.delete(record)
    db.commit()
