import re
from datetime import date, datetime, timedelta
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    BidConversion,
    BidRadarItem,
    BidScoreCriterion,
    ChannelPartner,
    ChannelRegistration,
    ChannelRegistrationGovernance,
    ChannelRegistrationRule,
    CommissionRule,
    Contact,
    Customer,
    CustomerCompetitorInstall,
    CustomerDecisionEdge,
    CustomerDecisionNode,
    CustomerIdentity,
    CustomerMergeLog,
    CustomerOperationProfile,
    CustomerSecurityProfile,
    FollowUp,
    ForecastSnapshot,
    IndustryProductRecommendation,
    Lead,
    Opportunity,
    OpportunityReview,
    PartnerGrowthRecord,
    PocRecord,
    PresalesAsset,
    PresalesRequest,
    PresalesSlaRule,
    PresalesSlaTracking,
    Product,
    User,
    now_cst,
)
from app.routers.sales_growth import _date_range, forecast as forecast_summary
from app.routers.utils import require_admin, require_user

router = APIRouter()


class CustomerIdentityIn(BaseModel):
    unified_social_credit_code: Optional[str] = None
    short_name: Optional[str] = None
    aliases: Optional[str] = None
    parent_customer_id: Optional[int] = None
    source: Optional[str] = "manual"


class CustomerMergeIn(BaseModel):
    source_customer_id: int
    target_customer_id: int
    reason: Optional[str] = None


class RegistrationRuleIn(BaseModel):
    name: str = "默认报备规则"
    default_protection_days: int = 90
    max_extensions: int = 1
    extension_days: int = 30
    require_evidence: bool = True
    inactive_days_to_warn: int = 14
    inactive_days_to_expire: int = 30
    notes: Optional[str] = None


class RegistrationGovernanceIn(BaseModel):
    evidence_summary: Optional[str] = None
    last_activity_date: Optional[date] = None
    invalid_reason: Optional[str] = None
    owner_comment: Optional[str] = None


class RegistrationExtendIn(BaseModel):
    evidence_summary: str
    extension_days: Optional[int] = None


class PresalesScheduleIn(BaseModel):
    owner_id: Optional[int] = None
    scheduled_date: Optional[date] = None
    resource_name: Optional[str] = None
    notes: Optional[str] = None


class BidConvertIn(BaseModel):
    conversion_type: str = "lead"
    sales_rep_id: Optional[int] = None
    customer_id: Optional[int] = None
    create_customer: bool = True


class DecisionNodeIn(BaseModel):
    name: str
    role: Optional[str] = None
    department: Optional[str] = None
    influence: int = 3
    attitude: str = "neutral"
    relationship_strength: int = 3
    contact_id: Optional[int] = None
    notes: Optional[str] = None


class DecisionEdgeIn(BaseModel):
    source_node_id: int
    target_node_id: int
    relation: str = "influence"
    strength: int = 3
    notes: Optional[str] = None


class CompetitorInstallIn(BaseModel):
    competitor_name: str
    product_line: Optional[str] = None
    product_name: Optional[str] = None
    contract_end_date: Optional[date] = None
    satisfaction: int = 3
    replacement_chance: str = "medium"
    pain_points: Optional[str] = None
    notes: Optional[str] = None


class RecommendationIn(BaseModel):
    industry: str
    product_line: str
    product_sub_category: Optional[str] = None
    priority: int = 3
    scenario: Optional[str] = None
    pitch: Optional[str] = None
    is_active: bool = True


class PocRecordIn(BaseModel):
    opportunity_id: int
    presales_request_id: Optional[int] = None
    test_goal: Optional[str] = None
    environment: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    result: str = "pending"
    customer_feedback: Optional[str] = None
    next_step: Optional[str] = None


class ForecastSnapshotIn(BaseModel):
    period_label: str
    group_by: str = "sales"


class PresalesAssetIn(BaseModel):
    title: str
    asset_type: str = "solution"
    product_line: Optional[str] = None
    industry: Optional[str] = None
    url: Optional[str] = None
    summary: Optional[str] = None
    tags: Optional[str] = None


def _value(v):
    return v.value if hasattr(v, "value") else v


def _to_dict(row):
    if not row:
        return None
    data = {c.name: _value(getattr(row, c.name)) for c in row.__table__.columns}
    for k, v in list(data.items()):
        if isinstance(v, (date, datetime)):
            data[k] = v.isoformat()
    return data


def _normalize_name(name: str):
    text = (name or "").lower()
    text = re.sub(r"[\s（）()【】\[\]·,，.。]", "", text)
    for suffix in ["有限责任公司", "股份有限公司", "有限公司", "集团公司", "集团", "信息中心", "数据中心", "采购中心"]:
        text = text.replace(suffix, "")
    return text


def _check_customer(db: Session, cid: int, user):
    row = db.query(Customer).filter_by(id=cid).first()
    if not row:
        raise HTTPException(404, "客户不存在")
    if user.role != "admin" and row.owner_id != user.id:
        raise HTTPException(403, "没有权限")
    return row


def _check_opp(db: Session, oid: int, user):
    opp = db.query(Opportunity).filter_by(id=oid).first()
    if not opp:
        raise HTTPException(404, "商机不存在")
    if user.role == "admin":
        return opp
    if user.role == "channel_manager" and _value(opp.opp_type) == "channel":
        return opp
    if opp.sales_rep_id == user.id:
        return opp
    raise HTTPException(403, "没有权限")


def _active_rule(db: Session):
    rule = db.query(ChannelRegistrationRule).filter_by(is_active=True).order_by(ChannelRegistrationRule.id.desc()).first()
    if not rule:
        rule = ChannelRegistrationRule()
        db.add(rule)
        db.commit()
        db.refresh(rule)
    return rule


@router.get("/customer-duplicates")
def customer_duplicates(db: Session = Depends(get_db), user=Depends(require_user)):
    customers = db.query(Customer).all() if user.role == "admin" else db.query(Customer).filter(Customer.owner_id == user.id).all()
    identities = {i.customer_id: i for i in db.query(CustomerIdentity).all()}
    buckets = {}
    for c in customers:
        ident = identities.get(c.id)
        key = (ident.normalized_name if ident else None) or _normalize_name(c.name)
        buckets.setdefault(key, []).append(c)
        if ident and ident.unified_social_credit_code:
            buckets.setdefault("code:" + ident.unified_social_credit_code, []).append(c)
    groups = []
    seen = set()
    for key, rows in buckets.items():
        ids = tuple(sorted({r.id for r in rows}))
        if len(ids) < 2 or ids in seen:
            continue
        seen.add(ids)
        groups.append({"match_key": key, "customers": [{"id": r.id, "name": r.name, "industry": r.industry, "owner_id": r.owner_id} for r in rows]})
    return groups


@router.get("/customers/{customer_id}/identity")
def get_customer_identity(customer_id: int, db: Session = Depends(get_db), user=Depends(require_user)):
    c = _check_customer(db, customer_id, user)
    ident = db.query(CustomerIdentity).filter_by(customer_id=customer_id).first()
    data = _to_dict(ident) or {"customer_id": customer_id, "normalized_name": _normalize_name(c.name)}
    data["customer_name"] = c.name
    return data


@router.put("/customers/{customer_id}/identity")
def upsert_customer_identity(customer_id: int, data: CustomerIdentityIn, db: Session = Depends(get_db), user=Depends(require_user)):
    c = _check_customer(db, customer_id, user)
    ident = db.query(CustomerIdentity).filter_by(customer_id=customer_id).first()
    if not ident:
        ident = CustomerIdentity(customer_id=customer_id)
        db.add(ident)
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(ident, k, v)
    ident.normalized_name = _normalize_name(data.short_name or c.name)
    db.commit()
    db.refresh(ident)
    return _to_dict(ident)


@router.post("/customer-merge")
def merge_customers(data: CustomerMergeIn, db: Session = Depends(get_db), admin=Depends(require_admin)):
    if data.source_customer_id == data.target_customer_id:
        raise HTTPException(400, "不能合并同一个客户")
    source = db.query(Customer).filter_by(id=data.source_customer_id).first()
    target = db.query(Customer).filter_by(id=data.target_customer_id).first()
    if not source or not target:
        raise HTTPException(404, "客户不存在")
    db.query(Contact).filter(Contact.customer_id == source.id).update({"customer_id": target.id})
    db.query(Opportunity).filter(Opportunity.customer_id == source.id).update({"customer_id": target.id})
    source_profile = db.query(CustomerSecurityProfile).filter_by(customer_id=source.id).first()
    target_profile = db.query(CustomerSecurityProfile).filter_by(customer_id=target.id).first()
    if source_profile and target_profile:
        db.delete(source_profile)
    elif source_profile:
        source_profile.customer_id = target.id
    db.query(CustomerDecisionNode).filter(CustomerDecisionNode.customer_id == source.id).update({"customer_id": target.id})
    db.query(CustomerDecisionEdge).filter(CustomerDecisionEdge.customer_id == source.id).update({"customer_id": target.id})
    db.query(CustomerCompetitorInstall).filter(CustomerCompetitorInstall.customer_id == source.id).update({"customer_id": target.id})
    db.query(CustomerOperationProfile).filter(CustomerOperationProfile.customer_id == source.id).delete()
    db.query(CustomerIdentity).filter(CustomerIdentity.customer_id == source.id).delete()
    db.add(CustomerMergeLog(
        source_customer_id=source.id,
        source_customer_name=source.name,
        target_customer_id=target.id,
        target_customer_name=target.name,
        reason=data.reason,
        merged_by=admin.id,
    ))
    db.delete(source)
    db.commit()
    return {"message": "merged", "source_customer_id": data.source_customer_id, "target_customer_id": data.target_customer_id}


@router.get("/channel-registration-rule")
def get_registration_rule(db: Session = Depends(get_db), user=Depends(require_user)):
    return _to_dict(_active_rule(db))


@router.put("/channel-registration-rule")
def update_registration_rule(data: RegistrationRuleIn, db: Session = Depends(get_db), admin=Depends(require_admin)):
    rule = _active_rule(db)
    for k, v in data.model_dump().items():
        setattr(rule, k, v)
    db.commit()
    db.refresh(rule)
    return _to_dict(rule)


@router.put("/channel-registrations/{registration_id}/governance")
def upsert_registration_governance(registration_id: int, data: RegistrationGovernanceIn, db: Session = Depends(get_db), user=Depends(require_user)):
    reg = db.query(ChannelRegistration).filter_by(id=registration_id).first()
    if not reg:
        raise HTTPException(404, "报备不存在")
    row = db.query(ChannelRegistrationGovernance).filter_by(registration_id=registration_id).first()
    if not row:
        row = ChannelRegistrationGovernance(registration_id=registration_id)
        db.add(row)
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(row, k, v)
    db.commit()
    db.refresh(row)
    return _to_dict(row)


@router.post("/channel-registrations/{registration_id}/extend")
def extend_registration(registration_id: int, data: RegistrationExtendIn, db: Session = Depends(get_db), user=Depends(require_user)):
    reg = db.query(ChannelRegistration).filter_by(id=registration_id).first()
    if not reg:
        raise HTTPException(404, "报备不存在")
    rule = _active_rule(db)
    row = db.query(ChannelRegistrationGovernance).filter_by(registration_id=registration_id).first()
    if not row:
        row = ChannelRegistrationGovernance(registration_id=registration_id)
        db.add(row)
    if row.extension_count >= rule.max_extensions:
        raise HTTPException(400, "已达到最大延期次数")
    if rule.require_evidence and not data.evidence_summary.strip():
        raise HTTPException(400, "延期需要填写推进证据")
    days = data.extension_days or rule.extension_days
    reg.protection_end = (reg.protection_end or date.today()) + timedelta(days=days)
    row.extension_count += 1
    row.evidence_summary = data.evidence_summary
    row.last_activity_date = date.today()
    db.commit()
    return {"message": "extended", "protection_end": reg.protection_end, "extension_count": row.extension_count}


@router.get("/presales-sla-rules")
def list_presales_sla_rules(db: Session = Depends(get_db), user=Depends(require_user)):
    if db.query(PresalesSlaRule).count() == 0:
        defaults = [
            ("presales_support", "售前支持", 8, 48),
            ("poc", "POC申请", 24, 120),
            ("test_resource", "测试资源排期", 12, 72),
            ("solution_review", "方案评审", 8, 48),
            ("bid_support", "标书支持", 8, 72),
            ("demo", "演示记录", 8, 48),
        ]
        for key, label, response, delivery in defaults:
            db.add(PresalesSlaRule(request_type=key, label=label, response_hours=response, delivery_hours=delivery))
        db.commit()
    return [_to_dict(r) for r in db.query(PresalesSlaRule).filter_by(is_active=True).order_by(PresalesSlaRule.id).all()]


@router.put("/presales-requests/{request_id}/schedule")
def schedule_presales(request_id: int, data: PresalesScheduleIn, db: Session = Depends(get_db), user=Depends(require_user)):
    req = db.query(PresalesRequest).filter_by(id=request_id).first()
    if not req:
        raise HTTPException(404, "售前申请不存在")
    if data.owner_id is not None:
        req.owner_id = data.owner_id
    if data.scheduled_date is not None:
        req.scheduled_date = data.scheduled_date
    if data.resource_name is not None:
        req.resource_name = data.resource_name
    rule = db.query(PresalesSlaRule).filter_by(request_type=req.request_type, is_active=True).first()
    if not rule:
        list_presales_sla_rules(db, user)
        rule = db.query(PresalesSlaRule).filter_by(request_type=req.request_type, is_active=True).first()
    tracking = db.query(PresalesSlaTracking).filter_by(request_id=request_id).first()
    if not tracking:
        tracking = PresalesSlaTracking(request_id=request_id)
        db.add(tracking)
    base = req.created_at or now_cst()
    tracking.response_due_at = base + timedelta(hours=rule.response_hours if rule else 24)
    tracking.delivery_due_at = base + timedelta(hours=rule.delivery_hours if rule else 72)
    tracking.notes = data.notes
    tracking.sla_status = "scheduled"
    db.commit()
    return {"request": _to_dict(req), "sla": _to_dict(tracking)}


@router.get("/presales-sla")
def presales_sla_board(db: Session = Depends(get_db), user=Depends(require_user)):
    rows = []
    for req in db.query(PresalesRequest).order_by(PresalesRequest.created_at.desc()).limit(200).all():
        tracking = db.query(PresalesSlaTracking).filter_by(request_id=req.id).first()
        status = "pending"
        if tracking:
            if tracking.completed_at:
                status = "done"
            elif tracking.delivery_due_at and tracking.delivery_due_at < now_cst():
                status = "overdue"
            else:
                status = tracking.sla_status
        rows.append({"request": _to_dict(req), "sla": _to_dict(tracking), "computed_status": status})
    return rows


@router.post("/bid-radar/items/{item_id}/convert")
def convert_bid_item(item_id: int, data: BidConvertIn, db: Session = Depends(get_db), user=Depends(require_user)):
    item = db.query(BidRadarItem).filter_by(id=item_id).first()
    if not item:
        raise HTTPException(404, "招标情报不存在")
    sales_id = data.sales_rep_id or user.id
    lead = item.lead_id and db.query(Lead).filter_by(id=item.lead_id).first()
    if not lead:
        lead = Lead(name=item.title, company=item.buyer, source="bidding", quality="warm", industry=item.matched_product_line, notes=item.notes, assigned_to=sales_id)
        db.add(lead)
        db.flush()
        item.lead_id = lead.id
    opp = None
    if data.conversion_type == "opportunity":
        customer_id = data.customer_id
        if not customer_id and data.create_customer and item.buyer:
            customer = db.query(Customer).filter_by(name=item.buyer).first()
            if not customer:
                customer = Customer(name=item.buyer, industry=item.matched_product_line or "招投标", owner_id=sales_id)
                db.add(customer)
                db.flush()
            customer_id = customer.id
        opp = Opportunity(
            name=item.title,
            opp_type="direct",
            sales_rep_id=sales_id,
            customer_id=customer_id,
            industry=item.matched_product_line or "招投标",
            amount=item.budget or 0,
            stage="1",
            probability="LOW",
            required_product=item.matched_product_line,
            expected_close_date=item.deadline,
            brief=f"由招标雷达转化：{item.source or ''}",
        )
        db.add(opp)
        db.flush()
    conv = BidConversion(bid_item_id=item.id, lead_id=lead.id, opportunity_id=opp.id if opp else None, converted_by=user.id, conversion_type=data.conversion_type)
    item.status = "converted"
    db.add(conv)
    db.commit()
    return {"lead_id": lead.id, "opportunity_id": opp.id if opp else None, "conversion_id": conv.id}


@router.get("/customers/{customer_id}/decision-graph")
def get_decision_graph(customer_id: int, db: Session = Depends(get_db), user=Depends(require_user)):
    _check_customer(db, customer_id, user)
    nodes = db.query(CustomerDecisionNode).filter_by(customer_id=customer_id).all()
    edges = db.query(CustomerDecisionEdge).filter_by(customer_id=customer_id).all()
    return {"nodes": [_to_dict(n) for n in nodes], "edges": [_to_dict(e) for e in edges]}


@router.post("/customers/{customer_id}/decision-nodes", status_code=201)
def create_decision_node(customer_id: int, data: DecisionNodeIn, db: Session = Depends(get_db), user=Depends(require_user)):
    _check_customer(db, customer_id, user)
    row = CustomerDecisionNode(customer_id=customer_id, **data.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return _to_dict(row)


@router.post("/customers/{customer_id}/decision-edges", status_code=201)
def create_decision_edge(customer_id: int, data: DecisionEdgeIn, db: Session = Depends(get_db), user=Depends(require_user)):
    _check_customer(db, customer_id, user)
    row = CustomerDecisionEdge(customer_id=customer_id, **data.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return _to_dict(row)


@router.get("/customers/{customer_id}/competitor-installs")
def list_competitor_installs(customer_id: int, db: Session = Depends(get_db), user=Depends(require_user)):
    _check_customer(db, customer_id, user)
    return [_to_dict(r) for r in db.query(CustomerCompetitorInstall).filter_by(customer_id=customer_id).order_by(CustomerCompetitorInstall.id.desc()).all()]


@router.post("/customers/{customer_id}/competitor-installs", status_code=201)
def create_competitor_install(customer_id: int, data: CompetitorInstallIn, db: Session = Depends(get_db), user=Depends(require_user)):
    _check_customer(db, customer_id, user)
    row = CustomerCompetitorInstall(customer_id=customer_id, **data.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return _to_dict(row)


@router.get("/industry-product-recommendations")
def list_recommendations(industry: Optional[str] = Query(None), db: Session = Depends(get_db), user=Depends(require_user)):
    q = db.query(IndustryProductRecommendation).filter_by(is_active=True)
    if industry:
        q = q.filter(IndustryProductRecommendation.industry == industry)
    return [_to_dict(r) for r in q.order_by(IndustryProductRecommendation.priority.asc()).all()]


@router.post("/industry-product-recommendations", status_code=201)
def create_recommendation(data: RecommendationIn, db: Session = Depends(get_db), admin=Depends(require_admin)):
    row = IndustryProductRecommendation(**data.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return _to_dict(row)


@router.put("/industry-product-recommendations/{recommendation_id}")
def update_recommendation(recommendation_id: int, data: RecommendationIn, db: Session = Depends(get_db), admin=Depends(require_admin)):
    row = db.query(IndustryProductRecommendation).filter_by(id=recommendation_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Recommendation not found")
    for key, value in data.model_dump().items():
        setattr(row, key, value)
    db.commit()
    db.refresh(row)
    return _to_dict(row)


@router.delete("/industry-product-recommendations/{recommendation_id}")
def delete_recommendation(recommendation_id: int, db: Session = Depends(get_db), admin=Depends(require_admin)):
    row = db.query(IndustryProductRecommendation).filter_by(id=recommendation_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Recommendation not found")
    row.is_active = False
    db.commit()
    return {"ok": True}


@router.post("/industry-product-recommendations/seed")
def seed_recommendations(db: Session = Depends(get_db), admin=Depends(require_admin)):
    seeds = [
        ("党政", "数据安全", "DLP", 3, "等保整改、密评合规、信创适配"),
        ("公安", "数据安全", "NGFW", 3, "视频专网、边界防护、数据安全治理"),
        ("网信", "AI安全", "大模型安全", 3, "数据分类分级、重要数据保护、AI安全监管"),
        ("能源/电力", "数据安全", "NGFW", 3, "工控边界、态势感知、等保整改"),
        ("金融", "数据安全", "DLP", 3, "数据防泄漏、零信任、终端安全"),
        ("运营商", "数据安全", "WAAP", 3, "云网安全、态势感知、数据安全"),
        ("教育", "AI安全", "大模型安全", 3, "大模型应用防护、内容安全、信创安全"),
    ]
    created = 0
    for industry, line, sub_category, priority, scenario in seeds:
        exists = db.query(IndustryProductRecommendation).filter_by(industry=industry, product_line=line).first()
        if exists:
            continue
        db.add(IndustryProductRecommendation(industry=industry, product_line=line, product_sub_category=sub_category, priority=priority, scenario=scenario, pitch=f"{industry}行业优先推荐{line}" + (f" / {sub_category}" if sub_category else "")))
        created += 1
    db.commit()
    return {"created": created}


@router.get("/poc-records")
def list_poc_records(opportunity_id: Optional[int] = None, db: Session = Depends(get_db), user=Depends(require_user)):
    q = db.query(PocRecord, Opportunity).join(Opportunity, PocRecord.opportunity_id == Opportunity.id)
    if opportunity_id:
        _check_opp(db, opportunity_id, user)
        q = q.filter(PocRecord.opportunity_id == opportunity_id)
    rows = []
    for poc, opp in q.order_by(PocRecord.created_at.desc()).limit(200).all():
        d = _to_dict(poc)
        d["opportunity_name"] = opp.name if opp else None
        rows.append(d)
    return rows


@router.post("/poc-records", status_code=201)
def create_poc_record(data: PocRecordIn, db: Session = Depends(get_db), user=Depends(require_user)):
    _check_opp(db, data.opportunity_id, user)
    row = PocRecord(**data.model_dump(), created_by=user.id)
    db.add(row)
    db.commit()
    db.refresh(row)
    return _to_dict(row)


@router.post("/forecast-snapshots")
def create_forecast_snapshot(data: ForecastSnapshotIn, db: Session = Depends(get_db), user=Depends(require_user)):
    result = forecast_summary(group_by=data.group_by, period_label=data.period_label, db=db, user=user)
    created = 0
    for item in result["items"]:
        db.add(ForecastSnapshot(
            period_label=data.period_label,
            group_by=data.group_by,
            group_key=item["group"],
            commit_amount=item["commit"],
            best_case_amount=item["best_case"],
            pipeline_amount=item["pipeline"],
            weighted_amount=item["weighted"],
            owner_id=user.id,
        ))
        created += 1
    db.commit()
    return {"created": created, "period_label": data.period_label, "group_by": data.group_by}


@router.get("/forecast-accuracy")
def forecast_accuracy(period_label: str = Query(...), db: Session = Depends(get_db), user=Depends(require_user)):
    label, start, end = _date_range(period_label)
    actual = db.query(func.sum(Opportunity.amount)).filter(Opportunity.is_closed == True, Opportunity.updated_at.between(start, end)).scalar() or 0
    snaps = db.query(ForecastSnapshot).filter_by(period_label=label).order_by(ForecastSnapshot.snapshot_date.desc()).all()
    rows = []
    for s in snaps:
        forecasted = s.commit_amount or s.weighted_amount or 0
        rows.append({**_to_dict(s), "actual_amount": round(actual, 1), "accuracy_rate": round((min(forecasted, actual) / max(forecasted, actual) * 100), 1) if forecasted and actual else 0})
    return rows


@router.get("/partner-credit-scores")
def partner_credit_scores(db: Session = Depends(get_db), user=Depends(require_user)):
    rows = []
    for p in db.query(ChannelPartner).all():
        opps = db.query(Opportunity).filter_by(channel_partner_id=p.id).all()
        records = db.query(PartnerGrowthRecord).filter_by(partner_id=p.id).all()
        performance = sum(o.amount or 0 for o in opps)
        violations = len([r for r in records if r.record_type == "violation"])
        trainings = len([r for r in records if r.record_type == "training"])
        certifications = len([r for r in records if r.record_type == "certification"])
        score = max(0, min(100, 60 + min(performance / 20, 20) + trainings * 2 + certifications * 3 - violations * 15))
        rows.append({"partner_id": p.id, "partner_name": p.name, "level": p.level, "credit_score": round(score, 1), "violations": violations, "trainings": trainings, "certifications": certifications, "performance": round(performance, 1)})
    return sorted(rows, key=lambda x: x["credit_score"], reverse=True)


@router.get("/presales-assets")
def list_presales_assets(keyword: Optional[str] = None, db: Session = Depends(get_db), user=Depends(require_user)):
    q = db.query(PresalesAsset)
    if keyword:
        q = q.filter(or_(PresalesAsset.title.contains(keyword), PresalesAsset.tags.contains(keyword), PresalesAsset.summary.contains(keyword)))
    return [_to_dict(r) for r in q.order_by(PresalesAsset.created_at.desc()).limit(200).all()]


@router.post("/presales-assets", status_code=201)
def create_presales_asset(data: PresalesAssetIn, db: Session = Depends(get_db), user=Depends(require_user)):
    row = PresalesAsset(**data.model_dump(), created_by=user.id)
    db.add(row)
    db.commit()
    db.refresh(row)
    return _to_dict(row)


@router.post("/bid-radar/items/{item_id}/parse-score")
def parse_bid_score(item_id: int, db: Session = Depends(get_db), user=Depends(require_user)):
    item = db.query(BidRadarItem).filter_by(id=item_id).first()
    if not item:
        raise HTTPException(404, "招标情报不存在")
    db.query(BidScoreCriterion).filter_by(bid_item_id=item_id).delete()
    text = " ".join([item.title or "", item.notes or "", item.matched_product_line or ""])
    templates = [
        ("技术响应", 35, 80, "low" if "大模型" in text or "数据" in text else "medium", "结合产品白皮书补充技术响应点"),
        ("商务报价", 25, 70, "medium", "提前准备竞品价格对比和分项报价策略"),
        ("项目经验", 20, 75, "medium", "匹配同类行业案例和成功复盘"),
        ("服务保障", 20, 85, "low", "补充本地化服务、应急响应和售后 SLA"),
    ]
    for criterion, weight, our_score, risk, suggestion in templates:
        db.add(BidScoreCriterion(bid_item_id=item_id, criterion=criterion, weight=weight, our_score=our_score, risk_level=risk, suggestion=suggestion))
    db.commit()
    return [_to_dict(r) for r in db.query(BidScoreCriterion).filter_by(bid_item_id=item_id).all()]


@router.get("/customer-maturity-scores")
def customer_maturity_scores(db: Session = Depends(get_db), user=Depends(require_user)):
    customers = db.query(Customer).all() if user.role == "admin" else db.query(Customer).filter(Customer.owner_id == user.id).all()
    rows = []
    for c in customers:
        profile = db.query(CustomerSecurityProfile).filter_by(customer_id=c.id).first()
        opp_count = db.query(Opportunity).filter_by(customer_id=c.id).count()
        comp_count = db.query(CustomerCompetitorInstall).filter_by(customer_id=c.id).count()
        node_count = db.query(CustomerDecisionNode).filter_by(customer_id=c.id).count()
        score = 30 + min(opp_count * 8, 20) + min(comp_count * 5, 15) + min(node_count * 5, 15)
        if profile:
            score += sum(5 for v in [profile.mlps_status, profile.crypto_status, profile.xinchuang_status, profile.security_products] if v)
        rows.append({"customer_id": c.id, "customer_name": c.name, "industry": c.industry, "maturity_score": min(score, 100), "opportunity_count": opp_count, "competitor_install_count": comp_count, "decision_node_count": node_count})
    return sorted(rows, key=lambda x: x["maturity_score"], reverse=True)


@router.get("/bi-dashboard")
def bi_dashboard(db: Session = Depends(get_db), user=Depends(require_user)):
    opp_count = db.query(Opportunity).count()
    active_amount = db.query(func.sum(Opportunity.amount)).filter(Opportunity.is_closed == False).scalar() or 0
    won_amount = db.query(func.sum(Opportunity.amount)).filter(Opportunity.is_closed == True).scalar() or 0
    presales_overdue = 0
    for t in db.query(PresalesSlaTracking).all():
        if not t.completed_at and t.delivery_due_at and t.delivery_due_at < now_cst():
            presales_overdue += 1
    return {
        "overview": {
            "customers": db.query(Customer).count(),
            "opportunities": opp_count,
            "active_amount": round(active_amount, 1),
            "won_amount": round(won_amount, 1),
            "leads": db.query(Lead).count(),
            "partners": db.query(ChannelPartner).count(),
        },
        "risk": {
            "presales_overdue": presales_overdue,
            "channel_conflicts": db.query(ChannelRegistration).filter_by(status="conflict").count(),
            "open_bid_items": db.query(BidRadarItem).filter(BidRadarItem.status != "converted").count(),
        },
        "closed_loop": {
            "poc_records": db.query(PocRecord).count(),
            "opportunity_reviews": db.query(OpportunityReview).count(),
            "presales_assets": db.query(PresalesAsset).count(),
            "forecast_snapshots": db.query(ForecastSnapshot).count(),
        },
    }
