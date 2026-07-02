from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import StageConfig
from app.schemas import StageConfigOut, StageConfigUpdate
from app.routers.utils import require_user

router = APIRouter()

def _seed_defaults(db: Session):
    """Seed default stages if table is empty."""
    if db.query(StageConfig).count() > 0:
        return
    defaults = [
        {"stage_key": "1", "label": "1. 获取项目信息", "color": "#f59e0b", "pct": "20%", "sort_order": 1},
        {"stage_key": "2", "label": "2. 见到用户/渠道", "color": "#3b82f6", "pct": "40%", "sort_order": 2},
        {"stage_key": "3", "label": "3. 技术交流/试用", "color": "#8b5cf6", "pct": "60%", "sort_order": 3},
        {"stage_key": "4", "label": "4. 明确合作意向", "color": "#f97316", "pct": "80%", "sort_order": 4},
        {"stage_key": "5", "label": "5. 确定合作/招投标", "color": "#22c55e", "pct": "100%", "sort_order": 5},
    ]
    for d in defaults:
        db.add(StageConfig(**d))
    db.commit()

@router.get("", response_model=list[StageConfigOut])
def list_stages(db: Session = Depends(get_db), user=Depends(require_user)):
    _seed_defaults(db)
    return db.query(StageConfig).order_by(StageConfig.sort_order).all()

@router.put("/{stage_key}")
def update_stage(stage_key: str, data: StageConfigUpdate, db: Session = Depends(get_db), user=Depends(require_user)):
    if user.role != "admin":
        raise HTTPException(403, "仅管理员可修改阶段配置")
    stage = db.query(StageConfig).filter_by(stage_key=stage_key).first()
    if not stage:
        raise HTTPException(404, "阶段不存在")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(stage, k, v)
    db.commit(); db.refresh(stage)
    return {"message": "updated", "stage_key": stage_key}
