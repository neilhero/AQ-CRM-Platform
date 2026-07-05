from fastapi import HTTPException


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

ADMIN_ONLY_MENUS = {"group-product", "/products", "/products/recommendations"}

ROLE_MENU_KEYS = {
    ROLE_ADMIN: None,
    ROLE_MANAGER: {
        "group-dashboard",
        "/dashboard",
        "/business-excellence",
        "/follow-ups",
        "group-customer",
        "/customers",
        "/customers/profile",
        "/customers/operations",
        "group-opp",
        "/opportunities/direct",
        "/opportunities/channel",
        "group-leads",
        "/leads",
        "/leads/bid-radar",
        "/leads/bid-conversion",
        "group-presales",
        "/presales",
        "/presales/assets",
        "group-partner",
        "/partners",
        "/partners/performance",
        "/partners/registration",
        "/partners/growth",
    },
    ROLE_SALES: {
        "group-dashboard",
        "/dashboard",
        "/follow-ups",
        "group-customer",
        "/customers",
        "/customers/profile",
        "group-opp",
        "/opportunities/direct",
        "/opportunities/channel",
        "group-leads",
        "/leads",
        "/leads/bid-radar",
        "group-presales",
        "/presales",
    },
    ROLE_CHANNEL_MANAGER: {
        "group-dashboard",
        "/dashboard",
        "/follow-ups",
        "group-opp",
        "/opportunities/channel",
        "group-leads",
        "/leads/bid-radar",
        "group-partner",
        "/partners",
        "/partners/performance",
        "/partners/registration",
        "/partners/growth",
        "group-presales",
        "/presales",
    },
    ROLE_PRESALES: {
        "group-dashboard",
        "/dashboard",
        "group-customer",
        "/customers/profile",
        "group-opp",
        "/opportunities/direct",
        "/opportunities/channel",
        "group-presales",
        "/presales",
        "/presales/assets",
        "group-leads",
        "/leads/bid-radar",
    },
}


def role_label(role: str) -> str:
    return ROLE_LABELS.get(role or "", role or "-")


def validate_role(role: str) -> str:
    if role not in VALID_ROLES:
        raise HTTPException(400, "角色无效，可选：admin/manager/sales/channel_manager/presales")
    return role


def menu_allowed(role: str, menu_key: str) -> bool:
    allowed = ROLE_MENU_KEYS.get(role)
    return allowed is None or menu_key in allowed


def can_view_all_sales_data(user) -> bool:
    return user.role in (ROLE_ADMIN, ROLE_MANAGER, ROLE_PRESALES)


def can_view_channel_data(user) -> bool:
    return user.role in (ROLE_ADMIN, ROLE_MANAGER, ROLE_CHANNEL_MANAGER, ROLE_PRESALES)


def is_channel_only(user) -> bool:
    return user.role == ROLE_CHANNEL_MANAGER


def require_admin_role(user):
    if user.role != ROLE_ADMIN:
        raise HTTPException(403, "仅管理员可操作")
    return user


def can_edit_business_record(user, owner_id=None, is_channel=False) -> bool:
    if user.role in (ROLE_ADMIN, ROLE_MANAGER):
        return True
    if user.role == ROLE_CHANNEL_MANAGER:
        return bool(is_channel)
    if user.role == ROLE_SALES:
        return owner_id == user.id
    return False
