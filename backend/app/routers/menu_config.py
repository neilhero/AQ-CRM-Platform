from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import MenuConfig
from app.routers.utils import require_user

router = APIRouter()


@router.get("")
def get_menu_config(db: Session = Depends(get_db), _user=Depends(require_user)):
    items = db.query(MenuConfig).order_by(MenuConfig.sort_order).all()
    return [{"menu_key": m.menu_key, "label": m.label, "is_visible": m.is_visible,
             "sort_order": m.sort_order, "parent_key": m.parent_key} for m in items]


@router.put("")
def update_menu_config(items: list[dict], db: Session = Depends(get_db), user=Depends(require_user)):
    if user.role != "admin":
        raise HTTPException(403, "仅管理员可操作")
    for item in items:
        m = db.query(MenuConfig).filter_by(menu_key=item["menu_key"]).first()
        if m:
            m.is_visible = item.get("is_visible", True)
    db.commit()
    return {"ok": True}
