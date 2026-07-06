from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional
from app.database import get_db
from app.models import ChannelPartner, ChannelRegistration, CommissionRule, Contact, Opportunity, PartnerGrowthRecord, User
from app.schemas import ChannelPartnerCreate, ChannelPartnerUpdate, ContactCreate, ContactUpdate
from app.permissions import ROLE_ADMIN
from app.routers.utils import require_user

router = APIRouter()


def _can_manage_partner(user, partner: ChannelPartner):
    if user.role == ROLE_ADMIN:
        return True
    return partner.created_by == user.id


def _check_partner_access(partner: ChannelPartner, user):
    if not partner:
        raise HTTPException(404, "Not found")
    if not _can_manage_partner(user, partner):
        raise HTTPException(403, "没有权限操作该渠道档案")
    return partner


def _partner_dict(db: Session, partner: ChannelPartner):
    creator = db.query(User).filter_by(id=partner.created_by).first() if partner.created_by else None
    return {
        "id": partner.id,
        "name": partner.name,
        "contact_person": partner.contact_person,
        "contact_phone": partner.contact_phone,
        "description": partner.description,
        "level": partner.level,
        "region": partner.region,
        "status": partner.status,
        "created_at": partner.created_at.isoformat() if partner.created_at else None,
        "created_by": partner.created_by,
        "created_by_name": (creator.real_name or creator.username) if creator else None,
        "opp_count": db.query(Opportunity).filter(Opportunity.channel_partner_id == partner.id).count(),
        "contact_count": db.query(Contact).filter(Contact.partner_id == partner.id).count(),
    }

@router.get("")
def list_partners(keyword: Optional[str]=Query(None), level: Optional[str]=Query(None),
                  region: Optional[str]=Query(None), skip: int=Query(0,ge=0), limit: int=Query(100,ge=1,le=500),
                  db: Session=Depends(get_db), user=Depends(require_user)):
    q = db.query(ChannelPartner)
    if user.role != ROLE_ADMIN:
        q = q.filter(ChannelPartner.created_by == user.id)
    if keyword: q = q.filter(ChannelPartner.name.contains(keyword))
    if level: q = q.filter(ChannelPartner.level == level)
    if region: q = q.filter(ChannelPartner.region == region)
    return [_partner_dict(db, p) for p in q.order_by(ChannelPartner.name).offset(skip).limit(limit).all()]

@router.get("/{pid}")
def get_partner(pid: int, db: Session=Depends(get_db), user=Depends(require_user)):
    p = db.query(ChannelPartner).filter_by(id=pid).first()
    _check_partner_access(p, user)
    return _partner_dict(db, p)

@router.post("", status_code=201)
def create_partner(data: ChannelPartnerCreate, db: Session=Depends(get_db), user=Depends(require_user)):
    p = ChannelPartner(**data.model_dump(), created_by=user.id)
    db.add(p); db.commit(); db.refresh(p); return _partner_dict(db, p)

@router.put("/{pid}")
def update_partner(pid: int, data: ChannelPartnerUpdate, db: Session=Depends(get_db), user=Depends(require_user)):
    p = db.query(ChannelPartner).filter_by(id=pid).first()
    _check_partner_access(p, user)
    for k,v in data.model_dump(exclude_unset=True).items(): setattr(p,k,v)
    db.commit(); db.refresh(p); return _partner_dict(db, p)

@router.delete("/{pid}", status_code=204)
def delete_partner(pid: int, db: Session=Depends(get_db), user=Depends(require_user)):
    p = db.query(ChannelPartner).filter_by(id=pid).first()
    _check_partner_access(p, user)
    db.query(Contact).filter(Contact.partner_id == pid).delete(synchronize_session=False)
    db.query(CommissionRule).filter(CommissionRule.partner_id == pid).delete(synchronize_session=False)
    db.query(PartnerGrowthRecord).filter(PartnerGrowthRecord.partner_id == pid).delete(synchronize_session=False)
    db.query(Opportunity).filter(Opportunity.channel_partner_id == pid).update(
        {Opportunity.channel_partner_id: None},
        synchronize_session=False,
    )
    db.query(ChannelRegistration).filter(ChannelRegistration.partner_id == pid).update(
        {ChannelRegistration.partner_id: None},
        synchronize_session=False,
    )
    db.delete(p); db.commit()

@router.get("/{pid}/contacts")
def list_partner_contacts(pid: int, db: Session=Depends(get_db), user=Depends(require_user)):
    p = db.query(ChannelPartner).filter_by(id=pid).first()
    _check_partner_access(p, user)
    return db.query(Contact).filter(Contact.partner_id == pid).order_by(Contact.id.desc()).all()

@router.post("/{pid}/contacts", status_code=201)
def create_partner_contact(pid: int, data: ContactCreate, db: Session=Depends(get_db), user=Depends(require_user)):
    p = db.query(ChannelPartner).filter_by(id=pid).first()
    _check_partner_access(p, user)
    c = Contact(**{**data.model_dump(exclude_unset=True), "partner_id": pid, "customer_id": None})
    db.add(c); db.commit(); db.refresh(c); return c

@router.put("/{pid}/contacts/{cid}")
def update_partner_contact(pid: int, cid: int, data: ContactUpdate, db: Session=Depends(get_db), user=Depends(require_user)):
    p = db.query(ChannelPartner).filter_by(id=pid).first()
    _check_partner_access(p, user)
    c = db.query(Contact).filter_by(id=cid, partner_id=pid).first()
    if not c: raise HTTPException(404, "Not found")
    for k, v in data.model_dump(exclude_unset=True).items(): setattr(c, k, v)
    db.commit(); db.refresh(c); return c

@router.delete("/{pid}/contacts/{cid}", status_code=204)
def delete_partner_contact(pid: int, cid: int, db: Session=Depends(get_db), user=Depends(require_user)):
    p = db.query(ChannelPartner).filter_by(id=pid).first()
    _check_partner_access(p, user)
    c = db.query(Contact).filter_by(id=cid, partner_id=pid).first()
    if not c: raise HTTPException(404, "Not found")
    db.delete(c); db.commit()
