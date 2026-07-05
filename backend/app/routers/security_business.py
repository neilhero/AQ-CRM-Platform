from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    BidRadarFollowTask,
    BidRadarItem,
    BidRadarSubscription,
    ChannelPartner,
    ChannelRegistration,
    Customer,
    CustomerSecurityProfile,
    Lead,
    Opportunity,
    PresalesRequest,
    User,
)
from app.permissions import ROLE_ADMIN, ROLE_PRESALES, can_access_customer, can_access_opportunity, scoped_opportunity_query
from app.routers.utils import require_admin, require_user

router = APIRouter()


class CustomerSecurityProfileIn(BaseModel):
    org_structure: Optional[str] = None
    decision_chain: Optional[str] = None
    technical_owner: Optional[str] = None
    purchase_owner: Optional[str] = None
    historical_projects: Optional[str] = None
    security_products: Optional[str] = None
    competitors: Optional[str] = None
    mlps_status: Optional[str] = None
    crypto_status: Optional[str] = None
    xinchuang_status: Optional[str] = None
    notes: Optional[str] = None


class ChannelRegistrationIn(BaseModel):
    opportunity_id: Optional[int] = None
    partner_id: Optional[int] = None
    final_customer_name: str
    region: Optional[str] = None
    protection_start: Optional[date] = None
    protection_days: Optional[int] = 90
    notes: Optional[str] = None


class ChannelRegistrationUpdate(BaseModel):
    status: Optional[str] = None
    region: Optional[str] = None
    protection_end: Optional[date] = None
    conflict_reason: Optional[str] = None
    arbitration_result: Optional[str] = None
    notes: Optional[str] = None


class PresalesRequestIn(BaseModel):
    customer_id: Optional[int] = None
    opportunity_id: int
    request_type: str
    title: Optional[str] = None
    requester_id: int
    owner_id: int
    scheduled_date: datetime
    resource_name: Optional[str] = None
    details: str


class PresalesRequestUpdate(BaseModel):
    status: Optional[str] = None
    requester_id: Optional[int] = None
    owner_id: Optional[int] = None
    scheduled_date: Optional[datetime] = None
    resource_name: Optional[str] = None
    details: Optional[str] = None
    result: Optional[str] = None


class BidRadarSubscriptionIn(BaseModel):
    name: str
    keywords: str
    regions: Optional[str] = None
    product_lines: Optional[str] = None
    min_budget: Optional[float] = 0.0
    is_active: Optional[bool] = True


class BidRadarItemIn(BaseModel):
    title: str
    buyer: Optional[str] = None
    source: Optional[str] = None
    url: Optional[str] = None
    region: Optional[str] = None
    budget: Optional[float] = 0.0
    deadline: Optional[date] = None
    competitor_judgment: Optional[str] = None
    matched_product_line: Optional[str] = None
    notes: Optional[str] = None


class BidRadarItemUpdate(BaseModel):
    status: Optional[str] = None
    competitor_judgment: Optional[str] = None
    matched_product_line: Optional[str] = None
    notes: Optional[str] = None


def _value(v):
    return v.value if hasattr(v, "value") else v


def _to_dict(row):
    data = {c.name: _value(getattr(row, c.name)) for c in row.__table__.columns}
    for k, v in list(data.items()):
        if isinstance(v, (date, datetime)):
            data[k] = v.isoformat()
    return data


def _check_opp_access(db: Session, opportunity_id: int, user):
    opp = db.query(Opportunity).filter_by(id=opportunity_id).first()
    if not opp:
        raise HTTPException(404, "商机不存在")
    if can_access_opportunity(db, user, opportunity_id):
        return opp
    raise HTTPException(403, "无权访问该商机")


def _accessible_opp_ids(db: Session, user):
    q = scoped_opportunity_query(db.query(Opportunity.id), db, user)
    return [row[0] for row in q.all()]


def _enrich_registration(db: Session, reg: ChannelRegistration):
    data = _to_dict(reg)
    if reg.partner_id:
        partner = db.query(ChannelPartner).filter_by(id=reg.partner_id).first()
        data["partner_name"] = partner.name if partner else None
    if reg.opportunity_id:
        opp = db.query(Opportunity).filter_by(id=reg.opportunity_id).first()
        data["opportunity_name"] = opp.name if opp else None
    if reg.duplicate_customer_id:
        cust = db.query(Customer).filter_by(id=reg.duplicate_customer_id).first()
        data["duplicate_customer_name"] = cust.name if cust else None
    return data


def _enrich_presales_request(db: Session, row: PresalesRequest):
    data = _to_dict(row)
    opp = db.query(Opportunity).filter_by(id=row.opportunity_id).first()
    customer = db.query(Customer).filter_by(id=opp.customer_id).first() if opp and opp.customer_id else None
    requester_id = row.requester_id or row.created_by
    requester = db.query(User).filter_by(id=requester_id).first() if requester_id else None
    owner = db.query(User).filter_by(id=row.owner_id).first() if row.owner_id else None
    creator = db.query(User).filter_by(id=row.created_by).first() if row.created_by else None
    data["opportunity_name"] = opp.name if opp else None
    data["customer_id"] = customer.id if customer else None
    data["customer_name"] = customer.name if customer else None
    data["requester_id"] = requester_id
    data["requester_name"] = requester.real_name if requester else None
    data["owner_name"] = owner.real_name if owner else None
    data["created_by_name"] = creator.real_name if creator else None
    return data


@router.get("/customer-profiles/{customer_id}")
def get_customer_profile(customer_id: int, db: Session = Depends(get_db), user=Depends(require_user)):
    cust = db.query(Customer).filter_by(id=customer_id).first()
    if not cust:
        raise HTTPException(404, "客户不存在")
    if not can_access_customer(db, user, customer_id):
        raise HTTPException(403, "Access denied")
    profile = db.query(CustomerSecurityProfile).filter_by(customer_id=customer_id).first()
    data = _to_dict(profile) if profile else {"customer_id": customer_id}
    data["customer_name"] = cust.name
    data["contacts"] = [_to_dict(c) for c in cust.contacts]
    data["opportunities"] = [_to_dict(o) for o in cust.opportunities]
    return data


@router.put("/customer-profiles/{customer_id}")
def upsert_customer_profile(customer_id: int, data: CustomerSecurityProfileIn, db: Session = Depends(get_db), user=Depends(require_user)):
    cust = db.query(Customer).filter_by(id=customer_id).first()
    if not cust:
        raise HTTPException(404, "客户不存在")
    if not can_access_customer(db, user, customer_id):
        raise HTTPException(403, "Access denied")
    profile = db.query(CustomerSecurityProfile).filter_by(customer_id=customer_id).first()
    if not profile:
        profile = CustomerSecurityProfile(customer_id=customer_id)
        db.add(profile)
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(profile, k, v)
    db.commit()
    db.refresh(profile)
    return _to_dict(profile)


@router.get("/channel-registrations")
def list_channel_registrations(
    keyword: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    user=Depends(require_user),
):
    q = db.query(ChannelRegistration)
    if user.role != ROLE_ADMIN:
        opp_ids = _accessible_opp_ids(db, user)
        if opp_ids:
            q = q.filter(or_(ChannelRegistration.created_by == user.id, ChannelRegistration.opportunity_id.in_(opp_ids)))
        else:
            q = q.filter(ChannelRegistration.created_by == user.id)
    if keyword:
        q = q.filter(ChannelRegistration.final_customer_name.contains(keyword))
    if status:
        q = q.filter(ChannelRegistration.status == status)
    rows = q.order_by(ChannelRegistration.created_at.desc()).limit(200).all()
    return [_enrich_registration(db, r) for r in rows]


@router.post("/channel-registrations", status_code=201)
def create_channel_registration(data: ChannelRegistrationIn, db: Session = Depends(get_db), user=Depends(require_user)):
    name = (data.final_customer_name or "").strip()
    if not name:
        raise HTTPException(400, "最终客户不能为空")
    if data.opportunity_id:
        _check_opp_access(db, data.opportunity_id, user)
    start = data.protection_start or date.today()
    end = start + timedelta(days=max(data.protection_days or 90, 1))
    duplicate = db.query(Customer).filter(Customer.name == name).first()
    conflict = (
        db.query(ChannelRegistration)
        .filter(ChannelRegistration.final_customer_name == name)
        .filter(ChannelRegistration.status.in_(["pending", "protected", "conflict"]))
        .filter(or_(ChannelRegistration.protection_end == None, ChannelRegistration.protection_end >= date.today()))
        .order_by(ChannelRegistration.created_at.desc())
        .first()
    )
    reg = ChannelRegistration(
        opportunity_id=data.opportunity_id,
        partner_id=data.partner_id,
        final_customer_name=name,
        region=data.region,
        protection_start=start,
        protection_end=end,
        duplicate_customer_id=duplicate.id if duplicate else None,
        conflict_with_id=conflict.id if conflict else None,
        conflict_reason="存在保护期内报备" if conflict else None,
        status="conflict" if conflict else "pending",
        notes=data.notes,
        created_by=user.id,
    )
    db.add(reg)
    db.commit()
    db.refresh(reg)
    return _enrich_registration(db, reg)


@router.put("/channel-registrations/{registration_id}")
def update_channel_registration(registration_id: int, data: ChannelRegistrationUpdate, db: Session = Depends(get_db), admin=Depends(require_admin)):
    reg = db.query(ChannelRegistration).filter_by(id=registration_id).first()
    if not reg:
        raise HTTPException(404, "报备不存在")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(reg, k, v)
    if data.arbitration_result:
        reg.arbitrator_id = admin.id
    db.commit()
    db.refresh(reg)
    return _enrich_registration(db, reg)


@router.get("/presales-requests")
def list_presales_requests(
    opportunity_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    user=Depends(require_user),
):
    q = db.query(PresalesRequest)
    if opportunity_id:
        _check_opp_access(db, opportunity_id, user)
        q = q.filter(PresalesRequest.opportunity_id == opportunity_id)
    elif user.role != ROLE_ADMIN:
        opp_ids = _accessible_opp_ids(db, user)
        q = q.filter(or_(
            PresalesRequest.created_by == user.id,
            PresalesRequest.requester_id == user.id,
            PresalesRequest.owner_id == user.id,
            PresalesRequest.opportunity_id.in_(opp_ids or [-1]),
        ))
    if status:
        q = q.filter(PresalesRequest.status == status)
    rows = q.order_by(PresalesRequest.created_at.desc()).limit(200).all()
    return [_enrich_presales_request(db, row) for row in rows]


@router.get("/presales-notifications")
def list_presales_notifications(db: Session = Depends(get_db), user=Depends(require_user)):
    q = db.query(PresalesRequest).filter(PresalesRequest.status.in_(["pending", "in_progress"]))
    if user.role == ROLE_PRESALES:
        q = q.filter(PresalesRequest.owner_id == user.id)
    elif user.role != ROLE_ADMIN:
        q = q.filter(or_(PresalesRequest.created_by == user.id, PresalesRequest.requester_id == user.id))
    rows = q.order_by(PresalesRequest.created_at.desc()).limit(20).all()
    items = [_enrich_presales_request(db, row) for row in rows]
    return {"count": len(items), "items": items}


@router.post("/presales-requests", status_code=201)
def create_presales_request(data: PresalesRequestIn, db: Session = Depends(get_db), user=Depends(require_user)):
    opp = _check_opp_access(db, data.opportunity_id, user)
    if data.customer_id and opp.customer_id and data.customer_id != opp.customer_id:
        raise HTTPException(400, "商机不属于所选客户")
    requester = db.query(User).filter_by(id=data.requester_id).first()
    if not requester:
        raise HTTPException(400, "负责人不存在")
    presales_user = db.query(User).filter_by(id=data.owner_id).first()
    if not presales_user or presales_user.role != ROLE_PRESALES:
        raise HTTPException(400, "请选择有效的售前支持人员")
    payload = data.model_dump(exclude={"customer_id"})
    if not payload.get("title"):
        payload["title"] = f"{opp.name}售前协同"
    row = PresalesRequest(**payload, created_by=user.id)
    db.add(row)
    db.commit()
    db.refresh(row)
    return _enrich_presales_request(db, row)


@router.put("/presales-requests/{request_id}")
def update_presales_request(request_id: int, data: PresalesRequestUpdate, db: Session = Depends(get_db), user=Depends(require_user)):
    row = db.query(PresalesRequest).filter_by(id=request_id).first()
    if not row:
        raise HTTPException(404, "售前申请不存在")
    _check_opp_access(db, row.opportunity_id, user)
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(row, k, v)
    db.commit()
    db.refresh(row)
    return _enrich_presales_request(db, row)


@router.get("/bid-radar/subscriptions")
def list_bid_subscriptions(db: Session = Depends(get_db), user=Depends(require_user)):
    return [_to_dict(r) for r in db.query(BidRadarSubscription).order_by(BidRadarSubscription.created_at.desc()).all()]


@router.post("/bid-radar/subscriptions", status_code=201)
def create_bid_subscription(data: BidRadarSubscriptionIn, db: Session = Depends(get_db), user=Depends(require_user)):
    row = BidRadarSubscription(**data.model_dump(), owner_id=user.id)
    db.add(row)
    db.commit()
    db.refresh(row)
    return _to_dict(row)


@router.put("/bid-radar/subscriptions/{subscription_id}")
def update_bid_subscription(subscription_id: int, data: BidRadarSubscriptionIn, db: Session = Depends(get_db), user=Depends(require_user)):
    row = db.query(BidRadarSubscription).filter_by(id=subscription_id).first()
    if not row:
        raise HTTPException(404, "订阅不存在")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(row, k, v)
    db.commit()
    db.refresh(row)
    return _to_dict(row)


@router.get("/bid-radar/items")
def list_bid_items(status: Optional[str] = Query(None), db: Session = Depends(get_db), user=Depends(require_user)):
    q = db.query(BidRadarItem)
    if status:
        q = q.filter(BidRadarItem.status == status)
    rows = q.order_by(BidRadarItem.created_at.desc()).limit(200).all()
    return [_to_dict(r) for r in rows]


@router.post("/bid-radar/items", status_code=201)
def create_bid_item(data: BidRadarItemIn, db: Session = Depends(get_db), user=Depends(require_user)):
    row = BidRadarItem(**data.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    task = _create_bid_follow_task(db, row, user.id)
    db.commit()
    return {"item": _to_dict(row), "task": _to_dict(task)}


@router.put("/bid-radar/items/{item_id}")
def update_bid_item(item_id: int, data: BidRadarItemUpdate, db: Session = Depends(get_db), user=Depends(require_user)):
    row = db.query(BidRadarItem).filter_by(id=item_id).first()
    if not row:
        raise HTTPException(404, "雷达情报不存在")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(row, k, v)
    db.commit()
    db.refresh(row)
    return _to_dict(row)


@router.get("/bid-radar/tasks")
def list_bid_tasks(status: Optional[str] = Query(None), db: Session = Depends(get_db), user=Depends(require_user)):
    q = db.query(BidRadarFollowTask)
    if status:
        q = q.filter(BidRadarFollowTask.status == status)
    return [_to_dict(r) for r in q.order_by(BidRadarFollowTask.due_date.asc()).limit(200).all()]


def _keywords(text: str):
    return [x.strip() for x in (text or "").replace("，", ",").replace("、", ",").split(",") if x.strip()]


def _create_bid_follow_task(db: Session, item: BidRadarItem, owner_id: Optional[int]):
    due = item.deadline - timedelta(days=3) if item.deadline else date.today() + timedelta(days=1)
    task = BidRadarFollowTask(
        radar_item_id=item.id,
        title=f"跟进招标：{item.title}",
        owner_id=owner_id,
        due_date=due,
        notes=f"预算 {item.budget or 0} 万；匹配产品线：{item.matched_product_line or '-'}；竞品判断：{item.competitor_judgment or '-'}",
    )
    db.add(task)
    return task


@router.post("/bid-radar/collect")
def collect_bid_radar(db: Session = Depends(get_db), user=Depends(require_user)):
    samples = [
        {"title": "海关大数据中心大模型防护项目", "buyer": "海关大数据中心", "region": "华东", "budget": 450, "deadline": date.today() + timedelta(days=12), "source": "中国政府采购网", "competitor_judgment": "可能出现奇安信、深信服", "matched_product_line": "大模型防火墙"},
        {"title": "能源集团数据安全与密评整改采购", "buyer": "某能源集团", "region": "华北", "budget": 280, "deadline": date.today() + timedelta(days=8), "source": "中国招标网", "competitor_judgment": "可能出现安恒、绿盟", "matched_product_line": "数据安全/密评服务"},
        {"title": "公安视频专网等保安全加固", "buyer": "某市公安局", "region": "华南", "budget": 520, "deadline": date.today() + timedelta(days=18), "source": "公共资源交易中心", "competitor_judgment": "可能出现天融信、启明星辰", "matched_product_line": "等保整改/边界防护"},
        {"title": "高校信创环境安全运营平台", "buyer": "某科技大学", "region": "华东", "budget": 160, "deadline": date.today() + timedelta(days=15), "source": "高校采购平台", "competitor_judgment": "可能出现深信服、绿盟", "matched_product_line": "安全运营/信创适配"},
    ]
    subs = db.query(BidRadarSubscription).filter_by(is_active=True).all()
    created = []
    for sub in subs:
        words = _keywords(sub.keywords)
        product_lines = _keywords(sub.product_lines)
        for sample in samples:
            text = sample["title"] + sample["buyer"] + sample["matched_product_line"]
            if words and not any(w in text for w in words):
                continue
            if sub.min_budget and sample["budget"] < sub.min_budget:
                continue
            exists = db.query(BidRadarItem).filter_by(title=sample["title"], buyer=sample["buyer"]).first()
            if exists:
                continue
            line = sample["matched_product_line"]
            if product_lines:
                line = next((p for p in product_lines if p in text), line)
            item = BidRadarItem(subscription_id=sub.id, matched_product_line=line, **{k: v for k, v in sample.items() if k != "matched_product_line"})
            db.add(item)
            db.flush()
            lead = Lead(
                name=item.title,
                company=item.buyer,
                source="bidding",
                quality="warm",
                industry="招投标",
                notes=f"招标雷达自动识别：预算 {item.budget} 万，截止 {item.deadline}，竞品判断：{item.competitor_judgment}",
                assigned_to=user.id,
            )
            db.add(lead)
            db.flush()
            item.lead_id = lead.id
            task = _create_bid_follow_task(db, item, user.id)
            created.append({"item": _to_dict(item), "task": _to_dict(task), "lead_id": lead.id})
    db.commit()
    return {"created": len(created), "items": created}
