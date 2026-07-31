from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    BidConversion, ChannelPartner, ChannelRegistration, Contact, Customer,
    FollowUp, Lead, Opportunity, OpportunityReview, PocRecord,
    PresalesRequest, PresalesSlaTracking, User,
)
from app.permissions import (
    ROLE_CHANNEL_MANAGER,
    ROLE_MANAGER,
    ROLE_PRESALES,
    ROLE_SALES,
    can_edit_business_record,
    managed_user_ids,
    scoped_channel_partner_query,
    scoped_customer_query,
    scoped_opportunity_query,
)
from app.routers.utils import require_user
from app.schemas import OpportunityCreate, OpportunityUpdate

router = APIRouter()

REQUIRED_OPPORTUNITY_FIELDS = {
    "industry": "行业",
    "stage": "阶段",
    "probability": "概率",
    "amount": "金额",
}
VALID_STAGES = {"1", "2", "3", "4", "5"}
VALID_PROBABILITIES = {"HIGH", "MID_HIGH", "MID", "LOW"}


def _raw_value(value):
    return value.value if hasattr(value, "value") else value


def _week_update_status(opportunity: Opportunity) -> str:
    """Return the current-week status without persisting a stale display value."""
    week_start = date.today() - timedelta(days=date.today().weekday())

    created_at = opportunity.created_at
    updated_at = opportunity.updated_at
    if hasattr(created_at, "date"):
        created_at = created_at.date()
    if hasattr(updated_at, "date"):
        updated_at = updated_at.date()

    if created_at and created_at >= week_start:
        return "NEW"
    if updated_at and updated_at >= week_start:
        return "UPDATED"
    return "UNCHANGED"


def _validate_required_opportunity_fields(values):
    missing = []
    for field, label in REQUIRED_OPPORTUNITY_FIELDS.items():
        value = _raw_value(values.get(field))
        if field == "amount":
            if value is None:
                missing.append(label)
        elif value is None or str(value).strip() == "":
            missing.append(label)
    if missing:
        raise HTTPException(400, "请填写必填项：" + "、".join(missing))
    if float(values["amount"]) < 0:
        raise HTTPException(400, "金额不能小于 0")
    stage = str(_raw_value(values["stage"]))
    probability = str(_raw_value(values["probability"]))
    if stage not in VALID_STAGES:
        raise HTTPException(400, "阶段不合法")
    if probability not in VALID_PROBABILITIES:
        raise HTTPException(400, "概率不合法")


def _validate_create_relationships(values, db: Session, user):
    opp_type = values.get("opp_type")
    if opp_type == "channel":
        partner_id = values.get("channel_partner_id")
        if not partner_id:
            raise HTTPException(400, "请选择关联渠道")
        partner = (
            scoped_channel_partner_query(db.query(ChannelPartner), db, user)
            .filter(ChannelPartner.id == partner_id)
            .first()
        )
        if not partner:
            raise HTTPException(403, "无权关联该渠道或渠道不存在")
        end_customer_name = (values.get("end_customer_name") or "").strip()
        if not end_customer_name:
            raise HTTPException(400, "请输入最终客户")
        values["end_customer_name"] = end_customer_name
        values["customer_id"] = None
        return

    customer_id = values.get("customer_id")
    if not customer_id:
        raise HTTPException(400, "请选择最终客户")
    customer = (
        scoped_customer_query(db.query(Customer), db, user)
        .filter(Customer.id == customer_id)
        .first()
    )
    if not customer:
        raise HTTPException(403, "无权关联该客户或客户不存在")
    values["channel_partner_id"] = None


def _apply_perm_filter(q, db: Session, user):
    return scoped_opportunity_query(q, db, user)


def _check_access(opp, db: Session, user):
    allowed = scoped_opportunity_query(db.query(Opportunity), db, user).filter(Opportunity.id == opp.id).first()
    if not allowed:
        raise HTTPException(403, "Access denied")


def _check_edit_access(opp, db: Session, user):
    is_channel = _raw_value(opp.opp_type) == "channel"
    if not can_edit_business_record(user, owner_id=opp.sales_rep_id, is_channel=is_channel, db=db):
        raise HTTPException(403, "Access denied")


def _contact_dict(contact):
    return {
        "id": contact.id,
        "name": contact.name,
        "department": contact.department,
        "position": contact.position,
        "role_type": contact.role_type,
        "phone": contact.phone,
        "email": contact.email,
        "wechat": contact.wechat,
        "notes": contact.notes,
    }


def _contact_person_text(contacts):
    return ";;".join(
        "|".join([
            c.name or "",
            c.department or "",
            c.position or "",
            c.phone or "",
            c.email or "",
        ])
        for c in contacts
    )


def _parse_contact_people(value):
    people = []
    for raw_person in (value or "").split(";;"):
        fields = [field.strip() for field in raw_person.split("|")]
        if len(fields) >= 5:
            name, department, position, phone, email = fields[:5]
        else:
            fields += [""] * (4 - len(fields))
            name, position, phone, email = fields[:4]
            department = ""
        if any((name, department, position, phone, email)):
            if not name or not phone:
                raise HTTPException(422, "联系人姓名和联系方式为必填项")
            people.append({
                "name": name,
                "department": department or None,
                "position": position or None,
                "phone": phone or None,
                "email": email or None,
            })
    return people


def _sync_customer_contacts(db: Session, customer_id, role_type, value):
    if not customer_id:
        return
    for person in _parse_contact_people(value):
        contact = (
            db.query(Contact)
            .filter(
                Contact.customer_id == customer_id,
                Contact.role_type == role_type,
                Contact.name == person["name"],
            )
            .first()
        )
        if not contact:
            contact = Contact(
                customer_id=customer_id,
                partner_id=None,
                role_type=role_type,
                name=person["name"],
            )
            db.add(contact)
        for field in ("department", "position", "phone", "email"):
            if person[field]:
                setattr(contact, field, person[field])


def _sync_opportunity_contacts(db: Session, opportunity, changed_fields=None):
    changed_fields = set(changed_fields or ("key_person", "handler_person"))
    if "key_person" in changed_fields:
        _sync_customer_contacts(
            db, opportunity.customer_id, "key_person", opportunity.key_person
        )
    if "handler_person" in changed_fields:
        _sync_customer_contacts(
            db, opportunity.customer_id, "handler", opportunity.handler_person
        )


@router.get("")
def list_opps(
    keyword: Optional[str] = Query(None),
    stage: Optional[str] = Query(None),
    opp_type: Optional[str] = Query(None),
    sales_rep_id: Optional[int] = Query(None),
    channel_partner_id: Optional[int] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    user=Depends(require_user),
):
    q = _apply_perm_filter(db.query(Opportunity), db, user)
    if keyword:
        q = q.filter(Opportunity.name.contains(keyword))
    if stage:
        q = q.filter(Opportunity.stage == stage)
    if opp_type:
        q = q.filter(Opportunity.opp_type == opp_type)
    if sales_rep_id:
        q = q.filter(Opportunity.sales_rep_id == sales_rep_id)
    if channel_partner_id:
        q = q.filter(Opportunity.channel_partner_id == channel_partner_id)
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
        creator = (
            db.query(User).filter_by(id=o.created_by_id).first()
            if o.created_by_id else None
        )
        d["created_by_name"] = o.created_by_name or (
            (creator.real_name or creator.username) if creator else None
        )
        d["opp_type"] = o.opp_type.value if o.opp_type else None
        d["stage"] = o.stage.value if o.stage else None
        d["probability"] = o.probability.value if o.probability else None
        d["update_status"] = _week_update_status(o)
        out.append(d)
    return out


@router.get("/stats/summary")
def stats(db: Session = Depends(get_db), user=Depends(require_user)):
    q = _apply_perm_filter(db.query(Opportunity), db, user)
    total = q.count()
    active = q.filter(Opportunity.is_closed == False).count()
    total_amt = (
        _apply_perm_filter(db.query(func.sum(Opportunity.amount)), db, user)
        .filter(Opportunity.is_closed == False)
        .scalar()
        or 0
    )
    return {"total": total, "active": active, "total_amount": round(total_amt, 1)}


@router.get("/{oid}")
def get_opp(oid: int, db: Session = Depends(get_db), user=Depends(require_user)):
    o = db.query(Opportunity).filter_by(id=oid).first()
    if not o:
        raise HTTPException(404, "Not found")
    _check_access(o, db, user)
    d = {c.name: getattr(o, c.name) for c in o.__table__.columns}
    if o.customer_id:
        cust = db.query(Customer).filter_by(id=o.customer_id).first()
        d["customer_name"] = cust.name if cust else None
        contacts = (
            db.query(Contact)
            .filter(Contact.customer_id == o.customer_id)
            .order_by(Contact.id.desc())
            .all()
        )
        d["customer_contacts"] = [_contact_dict(c) for c in contacts]
        if not d.get("key_person"):
            key_contacts = [c for c in contacts if c.role_type == "key_person"]
            if key_contacts:
                d["key_person"] = _contact_person_text(key_contacts)
        if not d.get("handler_person"):
            handler_contacts = [c for c in contacts if c.role_type == "handler"]
            if handler_contacts:
                d["handler_person"] = _contact_person_text(handler_contacts)
    else:
        d["customer_contacts"] = []
    if o.channel_partner_id:
        cp = db.query(ChannelPartner).filter_by(id=o.channel_partner_id).first()
        d["channel_partner_name"] = cp.name if cp else None
    if o.sales_rep_id:
        sr = db.query(User).filter_by(id=o.sales_rep_id).first()
        d["sales_rep_name"] = sr.real_name if sr else None
    creator = (
        db.query(User).filter_by(id=o.created_by_id).first()
        if o.created_by_id else None
    )
    d["created_by_name"] = o.created_by_name or (
        (creator.real_name or creator.username) if creator else None
    )
    d["opp_type"] = o.opp_type.value if o.opp_type else None
    d["stage"] = o.stage.value if o.stage else None
    d["probability"] = o.probability.value if o.probability else None
    d["update_status"] = _week_update_status(o)
    return d


@router.post("", status_code=201)
def create_opp(data: OpportunityCreate, db: Session = Depends(get_db), user=Depends(require_user)):
    if user.role == ROLE_PRESALES:
        raise HTTPException(403, "售前角色不能新建商机")
    kwargs = data.model_dump()
    _validate_required_opportunity_fields(kwargs)
    kwargs["opp_type"] = "channel" if kwargs.get("opp_type") == "channel" else "direct"
    if user.role == ROLE_CHANNEL_MANAGER and kwargs.get("opp_type") != "channel":
        raise HTTPException(403, "渠道负责人只能新建渠道商机")
    if user.role in (ROLE_SALES, ROLE_CHANNEL_MANAGER):
        kwargs["sales_rep_id"] = user.id
    elif user.role == ROLE_MANAGER and kwargs.get("sales_rep_id") not in (managed_user_ids(db, user) or []):
        raise HTTPException(403, "只能分配给自己或管辖销售")
    _validate_create_relationships(kwargs, db, user)
    o = Opportunity(
        **kwargs,
        created_by_id=user.id,
        created_by_name=user.real_name or user.username,
    )
    db.add(o)
    _sync_opportunity_contacts(db, o)
    db.commit()
    db.refresh(o)
    return {"id": o.id, "name": o.name}


@router.put("/{oid}")
def update_opp(oid: int, data: OpportunityUpdate, db: Session = Depends(get_db), user=Depends(require_user)):
    o = db.query(Opportunity).filter_by(id=oid).first()
    if not o:
        raise HTTPException(404, "Not found")
    _check_access(o, db, user)
    _check_edit_access(o, db, user)
    updates = data.model_dump(exclude_unset=True)
    if "channel_partner_id" in updates and updates["channel_partner_id"] is not None:
        partner = (
            scoped_channel_partner_query(db.query(ChannelPartner), db, user)
            .filter(ChannelPartner.id == updates["channel_partner_id"])
            .first()
        )
        if not partner:
            raise HTTPException(403, "无权关联该渠道或渠道不存在")
    final_values = {
        field: updates[field] if field in updates else _raw_value(getattr(o, field))
        for field in REQUIRED_OPPORTUNITY_FIELDS
    }
    _validate_required_opportunity_fields(final_values)
    for k, v in updates.items():
        setattr(o, k, v)
    o.updated_at = date.today()
    _sync_opportunity_contacts(db, o, updates.keys())
    db.commit()
    db.refresh(o)
    return {"message": "updated"}


@router.delete("/{oid}", status_code=204)
def delete_opp(oid: int, db: Session = Depends(get_db), user=Depends(require_user)):
    o = db.query(Opportunity).filter_by(id=oid).first()
    if not o:
        raise HTTPException(404, "Not found")
    _check_access(o, db, user)
    _check_edit_access(o, db, user)
    # Remove or detach dependent records before deleting the opportunity.
    request_ids = [row[0] for row in db.query(PresalesRequest.id).filter(
        PresalesRequest.opportunity_id == oid
    ).all()]
    try:
        if request_ids:
            db.query(PresalesSlaTracking).filter(
                PresalesSlaTracking.request_id.in_(request_ids)
            ).delete(synchronize_session=False)
        db.query(PocRecord).filter(PocRecord.opportunity_id == oid).delete(
            synchronize_session=False
        )
        db.query(PresalesRequest).filter(PresalesRequest.opportunity_id == oid).delete(
            synchronize_session=False
        )
        db.query(FollowUp).filter(FollowUp.opportunity_id == oid).delete(
            synchronize_session=False
        )
        db.query(OpportunityReview).filter(OpportunityReview.opportunity_id == oid).delete(
            synchronize_session=False
        )
        db.query(Lead).filter(Lead.opportunity_id == oid).update(
            {Lead.opportunity_id: None}, synchronize_session=False
        )
        db.query(ChannelRegistration).filter(ChannelRegistration.opportunity_id == oid).update(
            {ChannelRegistration.opportunity_id: None}, synchronize_session=False
        )
        db.query(BidConversion).filter(BidConversion.opportunity_id == oid).update(
            {BidConversion.opportunity_id: None}, synchronize_session=False
        )
        db.delete(o)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "该商机存在未能清理的关联数据，暂时无法删除")
