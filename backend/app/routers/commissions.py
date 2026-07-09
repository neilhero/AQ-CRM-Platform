from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import ChannelPartner, CommissionRule
from app.permissions import ROLE_ADMIN, managed_user_ids
from app.routers.utils import require_user

router = APIRouter()


class CommissionRuleIn(BaseModel):
    partner_id: int
    rate_percent: float
    settlement_cycle: Optional[str] = "季度"
    effective_from: Optional[date] = None
    notes: Optional[str] = None


class CommissionRulePatch(BaseModel):
    partner_id: Optional[int] = None
    rate_percent: Optional[float] = None
    settlement_cycle: Optional[str] = None
    effective_from: Optional[date] = None
    notes: Optional[str] = None


def _to_dict(rule: CommissionRule, partner: Optional[ChannelPartner] = None):
    return {
        "id": rule.id,
        "partner_id": rule.partner_id,
        "partner_name": partner.name if partner else None,
        "rate_percent": rule.rate_percent,
        "settlement_cycle": rule.settlement_cycle,
        "effective_from": rule.effective_from.isoformat() if rule.effective_from else None,
        "notes": rule.notes,
        "created_at": rule.created_at.isoformat() if rule.created_at else None,
    }


def _manageable_owner_ids(db: Session, user):
    if user.role == ROLE_ADMIN:
        return None
    return managed_user_ids(db, user) or [user.id]


def _partner_query_for_user(db: Session, user):
    q = db.query(ChannelPartner)
    owner_ids = _manageable_owner_ids(db, user)
    if owner_ids is not None:
        q = q.filter(ChannelPartner.created_by.in_(owner_ids))
    return q


def _check_partner(pid: int, db: Session):
    partner = db.query(ChannelPartner).filter_by(id=pid).first()
    if not partner:
        raise HTTPException(404, "渠道不存在")
    return partner


def _check_partner_manage_access(pid: int, db: Session, user):
    partner = _check_partner(pid, db)
    owner_ids = _manageable_owner_ids(db, user)
    if owner_ids is not None and partner.created_by not in owner_ids:
        raise HTTPException(403, "无权操作该渠道返点规则")
    return partner


def _check_rule_manage_access(rule: CommissionRule, db: Session, user):
    if not rule:
        raise HTTPException(404, "返点规则不存在")
    return _check_partner_manage_access(rule.partner_id, db, user)


@router.get("")
def list_commission_rules(db: Session = Depends(get_db), user=Depends(require_user)):
    partner_ids = [row[0] for row in _partner_query_for_user(db, user).with_entities(ChannelPartner.id).all()]
    if not partner_ids:
        return []
    rows = (
        db.query(CommissionRule, ChannelPartner)
        .outerjoin(ChannelPartner, CommissionRule.partner_id == ChannelPartner.id)
        .filter(CommissionRule.partner_id.in_(partner_ids))
        .order_by(CommissionRule.id.desc())
        .all()
    )
    return [_to_dict(rule, partner) for rule, partner in rows]


@router.get("/partners")
def list_commission_partners(db: Session = Depends(get_db), user=Depends(require_user)):
    rows = _partner_query_for_user(db, user).order_by(ChannelPartner.name).limit(500).all()
    return [{"id": p.id, "name": p.name, "created_by": p.created_by} for p in rows]


@router.post("", status_code=201)
def create_commission_rule(data: CommissionRuleIn, db: Session = Depends(get_db), user=Depends(require_user)):
    partner = _check_partner_manage_access(data.partner_id, db, user)
    rule = CommissionRule(
        partner_id=data.partner_id,
        rate_percent=data.rate_percent,
        settlement_cycle=data.settlement_cycle or "季度",
        effective_from=data.effective_from or date.today(),
        notes=data.notes,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return _to_dict(rule, partner)


@router.put("/{rid}")
def update_commission_rule(rid: int, data: CommissionRulePatch, db: Session = Depends(get_db), user=Depends(require_user)):
    rule = db.query(CommissionRule).filter_by(id=rid).first()
    _check_rule_manage_access(rule, db, user)
    patch = data.model_dump(exclude_unset=True)
    if "partner_id" in patch and patch["partner_id"] is not None:
        _check_partner_manage_access(patch["partner_id"], db, user)
    for key, value in patch.items():
        setattr(rule, key, value)
    db.commit()
    db.refresh(rule)
    return _to_dict(rule, _check_partner(rule.partner_id, db))


@router.delete("/{rid}", status_code=204)
def delete_commission_rule(rid: int, db: Session = Depends(get_db), user=Depends(require_user)):
    rule = db.query(CommissionRule).filter_by(id=rid).first()
    _check_rule_manage_access(rule, db, user)
    db.delete(rule)
    db.commit()
