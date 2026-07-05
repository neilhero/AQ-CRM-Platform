from fastapi import HTTPException
from sqlalchemy import or_


ROLE_ADMIN = "admin"
ROLE_MANAGER = "manager"
ROLE_SALES = "sales"
ROLE_CHANNEL_MANAGER = "channel_manager"
ROLE_PRESALES = "presales"

VALID_ROLES = (
    ROLE_ADMIN,
    ROLE_MANAGER,
    ROLE_SALES,
    ROLE_CHANNEL_MANAGER,
    ROLE_PRESALES,
)

ROLE_LABELS = {
    ROLE_ADMIN: "管理员",
    ROLE_MANAGER: "销售主管",
    ROLE_SALES: "销售",
    ROLE_CHANNEL_MANAGER: "渠道经理",
    ROLE_PRESALES: "售前",
}


def role_label(role: str) -> str:
    return ROLE_LABELS.get(role or "", role or "-")


def validate_role(role: str) -> str:
    if role not in VALID_ROLES:
        raise HTTPException(400, "角色无效，可选：admin/manager/sales/channel_manager/presales")
    return role


def menu_allowed(role: str, menu_key: str) -> bool:
    return True


def can_view_all_sales_data(user) -> bool:
    return user.role == ROLE_ADMIN


def can_view_channel_data(user) -> bool:
    return user.role in (ROLE_ADMIN, ROLE_CHANNEL_MANAGER)


def is_channel_only(user) -> bool:
    return user.role == ROLE_CHANNEL_MANAGER


def require_admin_role(user):
    if user.role != ROLE_ADMIN:
        raise HTTPException(403, "仅管理员可操作")
    return user


def managed_user_ids(db, user):
    if user.role == ROLE_ADMIN:
        return None
    if user.role == ROLE_MANAGER:
        from app.models import User

        rows = (
            db.query(User.id)
            .filter(User.manager_id == user.id, User.is_active == True)
            .all()
        )
        return [user.id] + [row[0] for row in rows]
    return [user.id]


def presales_opportunity_ids(db, user):
    if user.role != ROLE_PRESALES:
        return []
    from app.models import PresalesRequest

    rows = (
        db.query(PresalesRequest.opportunity_id)
        .filter(or_(PresalesRequest.owner_id == user.id, PresalesRequest.created_by == user.id))
        .all()
    )
    return [row[0] for row in rows]


def scoped_opportunity_query(q, db, user):
    from app.models import Opportunity

    if user.role == ROLE_ADMIN:
        return q
    if user.role == ROLE_PRESALES:
        opp_ids = presales_opportunity_ids(db, user)
        return q.filter(Opportunity.id.in_(opp_ids or [-1]))
    owner_ids = managed_user_ids(db, user)
    return q.filter(Opportunity.sales_rep_id.in_(owner_ids or [-1]))


def scoped_customer_query(q, db, user):
    from app.models import Customer, Opportunity

    if user.role == ROLE_ADMIN:
        return q
    if user.role == ROLE_PRESALES:
        opp_ids = presales_opportunity_ids(db, user)
        rows = (
            db.query(Opportunity.customer_id)
            .filter(Opportunity.id.in_(opp_ids or [-1]), Opportunity.customer_id != None)
            .all()
        )
        customer_ids = [row[0] for row in rows]
        return q.filter(Customer.id.in_(customer_ids or [-1]))
    owner_ids = managed_user_ids(db, user)
    return q.filter(Customer.owner_id.in_(owner_ids or [-1]))


def scoped_lead_query(q, db, user):
    from app.models import Lead

    if user.role == ROLE_ADMIN:
        return q
    if user.role == ROLE_PRESALES:
        opp_ids = presales_opportunity_ids(db, user)
        return q.filter(Lead.opportunity_id.in_(opp_ids or [-1]))
    owner_ids = managed_user_ids(db, user)
    return q.filter(Lead.assigned_to.in_(owner_ids or [-1]))


def can_access_opportunity(db, user, opportunity_id: int) -> bool:
    from app.models import Opportunity

    return scoped_opportunity_query(db.query(Opportunity), db, user).filter(Opportunity.id == opportunity_id).first() is not None


def can_access_customer(db, user, customer_id: int) -> bool:
    from app.models import Customer

    return scoped_customer_query(db.query(Customer), db, user).filter(Customer.id == customer_id).first() is not None


def can_access_lead(db, user, lead_id: int) -> bool:
    from app.models import Lead

    return scoped_lead_query(db.query(Lead), db, user).filter(Lead.id == lead_id).first() is not None


def can_edit_owned_record(db, user, owner_id=None) -> bool:
    if user.role == ROLE_ADMIN:
        return True
    if user.role == ROLE_PRESALES:
        return False
    return owner_id in (managed_user_ids(db, user) or [])


def can_edit_business_record(user, owner_id=None, is_channel=False, db=None) -> bool:
    if db is not None:
        return can_edit_owned_record(db, user, owner_id)
    if user.role == ROLE_ADMIN:
        return True
    if user.role == ROLE_CHANNEL_MANAGER:
        return owner_id == user.id
    if user.role in (ROLE_MANAGER, ROLE_SALES):
        return owner_id == user.id
    return False
