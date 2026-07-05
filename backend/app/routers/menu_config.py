from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import MenuConfig
from app.permissions import menu_allowed, require_admin_role
from app.routers.utils import require_user

router = APIRouter()


@router.get("")
def get_menu_config(db: Session = Depends(get_db), user=Depends(require_user)):
    items = db.query(MenuConfig).order_by(MenuConfig.sort_order).all()
    return [
        {
            "menu_key": m.menu_key,
            "label": m.label,
            "is_visible": bool(m.is_visible and menu_allowed(user.role, m.menu_key)),
            "sort_order": m.sort_order,
            "parent_key": m.parent_key,
        }
        for m in items
    ]


@router.put("")
async def update_menu_config(request: Request, db: Session = Depends(get_db), user=Depends(require_user)):
    require_admin_role(user)
    items = await request.json()
    for item in items:
        m = db.query(MenuConfig).filter_by(menu_key=item["menu_key"]).first()
        if m:
            m.is_visible = item.get("is_visible", True)
    db.commit()
    return {"ok": True}
