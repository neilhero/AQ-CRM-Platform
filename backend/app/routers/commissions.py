from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional
from datetime import date

from app.database import get_db
from app.models import ChannelPartner, CommissionRule
from app.routers.utils import require_user, require_admin

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


def _check_partner(pid: int, db: Session):
    partner = db.query(ChannelPartner).filter_by(id=pid).first()
    if not partner:
        raise HTTPException(404, "渠道伙伴不存在")
    return partner


@router.get("")
def list_commission_rules(db: Session = Depends(get_db), user=Depends(require_user)):
    rows = (
        db.query(CommissionRule, ChannelPartner)
        .outerjoin(ChannelPartner, CommissionRule.partner_id == ChannelPartner.id)
        .order_by(CommissionRule.id.desc())
        .all()
    )
    return [_to_dict(rule, partner) for rule, partner in rows]


@router.post("", status_code=201)
def create_commission_rule(data: CommissionRuleIn, db: Session = Depends(get_db), admin=Depends(require_admin)):
    _check_partner(data.partner_id, db)
    rule = CommissionRule(
        partner_id=data.partner_id,
        rate_percent=data.rate_percent,
        settlement_cycle=data.settlement_cycle or "季度",
        effective_from=data.effective_from or date.today(),
        notes=data.notes,
    )
    db.add(rule); db.commit(); db.refresh(rule)
    return _to_dict(rule, _check_partner(rule.partner_id, db))


@router.put("/{rid}")
def update_commission_rule(rid: int, data: CommissionRulePatch, db: Session = Depends(get_db), admin=Depends(require_admin)):
    rule = db.query(CommissionRule).filter_by(id=rid).first()
    if not rule:
        raise HTTPException(404, "返点规则不存在")
    patch = data.model_dump(exclude_unset=True)
    if "partner_id" in patch and patch["partner_id"] is not None:
        _check_partner(patch["partner_id"], db)
    for key, value in patch.items():
        setattr(rule, key, value)
    db.commit(); db.refresh(rule)
    return _to_dict(rule, _check_partner(rule.partner_id, db))


@router.delete("/{rid}", status_code=204)
def delete_commission_rule(rid: int, db: Session = Depends(get_db), admin=Depends(require_admin)):
    rule = db.query(CommissionRule).filter_by(id=rid).first()
    if not rule:
        raise HTTPException(404, "返点规则不存在")
    db.delete(rule); db.commit()
