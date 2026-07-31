from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    AuditLog, BidConversion, BidRadarFollowTask, BidRadarSubscription,
    ChannelPartner, ChannelRegistration, Customer, CustomerMergeLog,
    FollowUp, ForecastSnapshot, Lead, Opportunity, OpportunityReview,
    OpportunityType, PartnerGrowthRecord, PocRecord, PresalesAsset, PresalesRequest,
    SalesTarget, User,
)
from app.permissions import (
    ROLE_LABELS, ROLE_MANAGER, ROLE_SALES, validate_role, require_admin_role,
)
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


class UserHandover(BaseModel):
    target_user_id: int
    transfer_all: bool = True
    customer_ids: list[int] = Field(default_factory=list)
    channel_partner_ids: list[int] = Field(default_factory=list)


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


def _handover_counts(db: Session, user_id: int):
    return {
        "leads": db.query(Lead).filter(Lead.assigned_to == user_id).count(),
        "customers": db.query(Customer).filter(Customer.owner_id == user_id).count(),
        "direct_opportunities": db.query(Opportunity).filter(
            Opportunity.sales_rep_id == user_id,
            Opportunity.opp_type == OpportunityType.DIRECT,
        ).count(),
        "channel_opportunities": db.query(Opportunity).filter(
            Opportunity.sales_rep_id == user_id,
            Opportunity.opp_type == OpportunityType.CHANNEL,
        ).count(),
        "channel_partners": db.query(ChannelPartner).filter(
            ChannelPartner.owner_id == user_id
        ).count(),
    }


def _validate_handover_users(db: Session, source_user: User, target_user_id: int):
    if source_user.id == target_user_id:
        raise HTTPException(400, "接收人不能是当前账号本人")
    if source_user.role == ROLE_SALES:
        target_roles = (ROLE_SALES, ROLE_MANAGER)
        target_error = "离职销售的接收人必须是启用状态的销售或销售负责人"
    elif source_user.role == ROLE_MANAGER:
        target_roles = (ROLE_SALES,)
        target_error = "销售负责人的业务只能转移给启用状态的销售"
    else:
        raise HTTPException(400, "当前业务交接仅适用于销售或销售负责人")
    target_user = db.query(User).filter(
        User.id == target_user_id,
        User.role.in_(target_roles),
        User.is_active == True,
    ).first()
    if not target_user:
        raise HTTPException(400, target_error)
    return target_user


def _handoff_user_references(db: Session, user_id: int):
    """Preserve business history while removing an account."""
    null_references = (
        (User, User.manager_id),
        (Customer, Customer.owner_id),
        (Customer, Customer.created_by_id),
        (ChannelPartner, ChannelPartner.owner_id),
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
        (Opportunity, Opportunity.created_by_id),
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


@router.get("/{uid}/handover-summary")
def handover_summary(
    uid: int,
    db: Session = Depends(get_db),
    admin=Depends(require_admin),
):
    source_user = db.query(User).filter_by(id=uid).first()
    if not source_user:
        raise HTTPException(404, "用户不存在")
    if source_user.role not in (ROLE_SALES, ROLE_MANAGER):
        raise HTTPException(400, "当前业务交接仅适用于销售或销售负责人")
    target_roles = (
        (ROLE_SALES, ROLE_MANAGER)
        if source_user.role == ROLE_SALES
        else (ROLE_SALES,)
    )
    targets = db.query(User).filter(
        User.role.in_(target_roles),
        User.is_active == True,
        User.id != source_user.id,
    ).order_by(User.real_name, User.id).all()
    return {
        "source_user": _user_out(source_user, db),
        "mode": "offboarding" if source_user.role == ROLE_SALES else "transfer",
        "counts": _handover_counts(db, source_user.id),
        "eligible_targets": [_user_out(user, db) for user in targets],
        "customers": (
            [
                {"id": row.id, "name": row.name}
                for row in db.query(Customer).filter(
                    Customer.owner_id == source_user.id
                ).order_by(Customer.name).all()
            ]
            if source_user.role == ROLE_MANAGER else []
        ),
        "channel_partners": (
            [
                {"id": row.id, "name": row.name}
                for row in db.query(ChannelPartner).filter(
                    ChannelPartner.owner_id == source_user.id
                ).order_by(ChannelPartner.name).all()
            ]
            if source_user.role == ROLE_MANAGER else []
        ),
    }


@router.post("/{uid}/handover")
def handover_user(
    uid: int,
    data: UserHandover,
    db: Session = Depends(get_db),
    admin=Depends(require_admin),
):
    source_user = db.query(User).filter_by(id=uid).with_for_update().first()
    if not source_user:
        raise HTTPException(404, "用户不存在")
    target_user = _validate_handover_users(db, source_user, data.target_user_id)
    is_offboarding = source_user.role == ROLE_SALES
    transfer_all = is_offboarding or data.transfer_all

    if transfer_all:
        counts = _handover_counts(db, source_user.id)
        customer_ids = None
        partner_ids = None
    else:
        customer_ids = list(dict.fromkeys(data.customer_ids or []))
        partner_ids = list(dict.fromkeys(data.channel_partner_ids or []))
        if not customer_ids and not partner_ids:
            raise HTTPException(400, "请至少选择一个客户或渠道")
        valid_customer_ids = {
            row[0] for row in db.query(Customer.id).filter(
                Customer.id.in_(customer_ids or [-1]),
                Customer.owner_id == source_user.id,
            ).all()
        }
        valid_partner_ids = {
            row[0] for row in db.query(ChannelPartner.id).filter(
                ChannelPartner.id.in_(partner_ids or [-1]),
                ChannelPartner.owner_id == source_user.id,
            ).all()
        }
        if len(valid_customer_ids) != len(customer_ids):
            raise HTTPException(403, "所选客户中包含无权转移的数据")
        if len(valid_partner_ids) != len(partner_ids):
            raise HTTPException(403, "所选渠道中包含无权转移的数据")
        customer_ids = list(valid_customer_ids)
        partner_ids = list(valid_partner_ids)
        linked_filter = or_(
            Opportunity.customer_id.in_(customer_ids or [-1]),
            Opportunity.channel_partner_id.in_(partner_ids or [-1]),
        )
        counts = {
            "leads": db.query(Lead).filter(
                Lead.assigned_to == source_user.id,
                Lead.customer_id.in_(customer_ids or [-1]),
            ).count(),
            "customers": len(customer_ids),
            "direct_opportunities": db.query(Opportunity).filter(
                Opportunity.sales_rep_id == source_user.id,
                Opportunity.opp_type == OpportunityType.DIRECT,
                linked_filter,
            ).count(),
            "channel_opportunities": db.query(Opportunity).filter(
                Opportunity.sales_rep_id == source_user.id,
                Opportunity.opp_type == OpportunityType.CHANNEL,
                linked_filter,
            ).count(),
            "channel_partners": len(partner_ids),
        }

    try:
        customer_query = db.query(Customer).filter(
            Customer.owner_id == source_user.id
        )
        lead_query = db.query(Lead).filter(Lead.assigned_to == source_user.id)
        opportunity_query = db.query(Opportunity).filter(
            Opportunity.sales_rep_id == source_user.id
        )
        partner_query = db.query(ChannelPartner).filter(
            ChannelPartner.owner_id == source_user.id
        )
        if not transfer_all:
            customer_query = customer_query.filter(
                Customer.id.in_(customer_ids or [-1])
            )
            lead_query = lead_query.filter(
                Lead.customer_id.in_(customer_ids or [-1])
            )
            opportunity_query = opportunity_query.filter(
                or_(
                    Opportunity.customer_id.in_(customer_ids or [-1]),
                    Opportunity.channel_partner_id.in_(partner_ids or [-1]),
                )
            )
            partner_query = partner_query.filter(
                ChannelPartner.id.in_(partner_ids or [-1])
            )
        customer_query.update(
            {Customer.owner_id: target_user.id}, synchronize_session=False
        )
        lead_query.update(
            {Lead.assigned_to: target_user.id}, synchronize_session=False
        )
        opportunity_query.update(
            {Opportunity.sales_rep_id: target_user.id}, synchronize_session=False
        )
        partner_query.update(
            {ChannelPartner.owner_id: target_user.id}, synchronize_session=False
        )
        if is_offboarding:
            source_user.is_active = False
        db.add(AuditLog(
            user_id=admin.id,
            username=admin.username,
            method="POST",
            path=f"/api/users/{source_user.id}/handover",
            status_code=200,
            action=(
                f"{'销售离职交接' if is_offboarding else '销售负责人业务转移'}："
                f"{source_user.real_name} -> {target_user.real_name}；"
                f"线索{counts['leads']}，客户{counts['customers']}，"
                f"直销商机{counts['direct_opportunities']}，"
                f"渠道商机{counts['channel_opportunities']}，"
                f"渠道档案{counts['channel_partners']}"
            ),
        ))
        db.commit()
    except Exception:
        db.rollback()
        raise

    return {
        "message": (
            "离职交接已完成，原销售账号已停用"
            if is_offboarding
            else "业务转移已完成，销售负责人账号保持启用"
        ),
        "mode": "offboarding" if is_offboarding else "transfer",
        "source_deactivated": is_offboarding,
        "transfer_all": transfer_all,
        "source_user": _user_out(source_user, db),
        "target_user": _user_out(target_user, db),
        "transferred": counts,
    }


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
    if data.is_active is False and user.role in (ROLE_SALES, ROLE_MANAGER):
        counts = _handover_counts(db, user.id)
        if sum(counts.values()) > 0:
            action_name = "离职交接" if user.role == ROLE_SALES else "业务转移"
            raise HTTPException(
                409,
                f"该账号仍有客户、商机或渠道数据，请先使用“{action_name}”完成转移",
            )
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
