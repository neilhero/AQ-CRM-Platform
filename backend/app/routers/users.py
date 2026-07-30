from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    AuditLog, BidConversion, BidRadarFollowTask, BidRadarSubscription,
    ChannelPartner, ChannelRegistration, Customer, CustomerMergeLog,
    FollowUp, ForecastSnapshot, Lead, Opportunity, OpportunityReview,
    PartnerGrowthRecord, PocRecord, PresalesAsset, PresalesRequest,
    SalesTarget, User,
)
from app.permissions import ROLE_LABELS, ROLE_MANAGER, validate_role, require_admin_role
from app.routers.utils import require_user
from app.services.auth import hash_password

router = APIRouter()


class UserCreate(BaseModel):
    username: str
    password: str
    real_name: str
    role: str = "sales"
    manager_id: Optional[int] = None
    dingtalk_userid: Optional[str] = None


class UserUpdate(BaseModel):
    real_name: Optional[str] = None
    role: Optional[str] = None
    manager_id: Optional[int] = None
    is_active: Optional[bool] = None
    dingtalk_userid: Optional[str] = None


class ResetPwd(BaseModel):
    new_password: str


def require_admin(user=Depends(require_user)):
    return require_admin_role(user)


def _manager_name(db: Session, manager_id: Optional[int]):
    if not manager_id:
        return None
    manager = db.query(User).filter_by(id=manager_id).first()
    return manager.real_name if manager else None


def _validate_manager(db: Session, manager_id: Optional[int]):
    if not manager_id:
        return
    manager = db.query(User).filter_by(id=manager_id, role=ROLE_MANAGER, is_active=True).first()
    if not manager:
        raise HTTPException(400, "直属销售负责人必须是启用状态的销售负责人")


def _user_out(user: User, db: Session):
    return {
        "id": user.id,
        "username": user.username,
        "real_name": user.real_name,
        "role": user.role,
        "role_label": ROLE_LABELS.get(user.role, user.role),
        "manager_id": user.manager_id,
        "manager_name": _manager_name(db, user.manager_id),
        "dingtalk_userid": user.dingtalk_userid,
        "is_active": user.is_active,
    }


def _handoff_user_references(db: Session, user_id: int):
    """Preserve business history while removing an account."""
    null_references = (
        (User, User.manager_id),
        (Customer, Customer.owner_id),
        (ChannelPartner, ChannelPartner.created_by),
        (Lead, Lead.assigned_to),
        (AuditLog, AuditLog.user_id),
        (ChannelRegistration, ChannelRegistration.arbitrator_id),
        (ChannelRegistration, ChannelRegistration.created_by),
        (PresalesRequest, PresalesRequest.requester_id),
        (PresalesRequest, PresalesRequest.owner_id),
        (PresalesRequest, PresalesRequest.created_by),
        (BidRadarSubscription, BidRadarSubscription.owner_id),
        (BidRadarFollowTask, BidRadarFollowTask.owner_id),
        (OpportunityReview, OpportunityReview.reviewer_id),
        (PartnerGrowthRecord, PartnerGrowthRecord.created_by),
        (CustomerMergeLog, CustomerMergeLog.merged_by),
        (BidConversion, BidConversion.converted_by),
        (PocRecord, PocRecord.created_by),
        (ForecastSnapshot, ForecastSnapshot.owner_id),
        (PresalesAsset, PresalesAsset.created_by),
    )
    for model, column in null_references:
        db.query(model).filter(column == user_id).update(
            {column: None}, synchronize_session=False
        )

    # These columns are mandatory, so transfer their historical ownership.
    db.query(Opportunity).filter(Opportunity.sales_rep_id == user_id).update(
        {Opportunity.sales_rep_id: 1}, synchronize_session=False
    )
    db.query(FollowUp).filter(FollowUp.creator_id == user_id).update(
        {FollowUp.creator_id: 1}, synchronize_session=False
    )
    db.query(SalesTarget).filter(SalesTarget.sales_rep_id == user_id).update(
        {SalesTarget.sales_rep_id: 1}, synchronize_session=False
    )


@router.get("")
def list_users(db: Session = Depends(get_db), admin=Depends(require_admin)):
    users = db.query(User).order_by(User.id).all()
    return [_user_out(u, db) for u in users]


@router.post("", status_code=201)
def create_user(data: UserCreate, db: Session = Depends(get_db), admin=Depends(require_admin)):
    validate_role(data.role)
    _validate_manager(db, data.manager_id)
    if db.query(User).filter_by(username=data.username).first():
        raise HTTPException(400, "用户名已存在")
    if len(data.password) < 6:
        raise HTTPException(400, "密码至少6位")
    user = User(
        username=data.username,
        password_hash=hash_password(data.password),
        real_name=data.real_name,
        role=data.role,
        manager_id=data.manager_id,
        dingtalk_userid=(data.dingtalk_userid or "").strip() or None,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return _user_out(user, db)


@router.put("/{uid}")
def update_user(uid: int, data: UserUpdate, db: Session = Depends(get_db), admin=Depends(require_admin)):
    user = db.query(User).filter_by(id=uid).first()
    if not user:
        raise HTTPException(404, "用户不存在")
    if data.real_name is not None:
        user.real_name = data.real_name
    if data.role is not None:
        validate_role(data.role)
        user.role = data.role
    if "manager_id" in data.model_fields_set:
        if data.manager_id == user.id:
            raise HTTPException(400, "直属主管不能选择自己")
        _validate_manager(db, data.manager_id)
        user.manager_id = data.manager_id
    if data.is_active is not None:
        user.is_active = data.is_active
    if "dingtalk_userid" in data.model_fields_set:
        user.dingtalk_userid = (data.dingtalk_userid or "").strip() or None
    db.commit()
    db.refresh(user)
    return _user_out(user, db)


@router.delete("/{uid}", status_code=204)
def delete_user(uid: int, db: Session = Depends(get_db), admin=Depends(require_admin)):
    user = db.query(User).filter_by(id=uid).first()
    if not user:
        raise HTTPException(404, "用户不存在")
    if user.id == 1:
        raise HTTPException(400, "不能删除系统管理员")
    try:
        _handoff_user_references(db, user.id)
        db.delete(user)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "该账号已关联业务数据，不能删除；请先停用账号或完成业务交接")


@router.put("/{uid}/reset-password")
def reset_password(uid: int, data: ResetPwd, db: Session = Depends(get_db), admin=Depends(require_admin)):
    user = db.query(User).filter_by(id=uid).first()
    if not user:
        raise HTTPException(404, "用户不存在")
    if len(data.new_password) < 6:
        raise HTTPException(400, "密码至少6位")
    user.password_hash = hash_password(data.new_password)
    db.commit()
    return {"message": "密码已重置"}
