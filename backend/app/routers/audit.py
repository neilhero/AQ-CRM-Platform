from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime, date, time

from app.database import get_db
from app.models import AuditLog, AuditChange
from app.routers.utils import require_admin

router = APIRouter()


@router.get("")
def list_audit_logs(
    username: Optional[str] = Query(None),
    method: Optional[str] = Query(None),
    path: Optional[str] = Query(None),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    admin=Depends(require_admin),
):
    q = db.query(AuditLog)
    if username:
        q = q.filter(AuditLog.username.contains(username))
    if method:
        q = q.filter(AuditLog.method == method.upper())
    if path:
        q = q.filter(AuditLog.path.contains(path))
    if start_date:
        q = q.filter(AuditLog.created_at >= datetime.combine(start_date, time.min))
    if end_date:
        q = q.filter(AuditLog.created_at <= datetime.combine(end_date, time.max))
    total = q.count()
    rows = q.order_by(AuditLog.created_at.desc()).offset(skip).limit(limit).all()
    changes = {
        change.audit_log_id: change
        for change in db.query(AuditChange).filter(AuditChange.audit_log_id.in_([row.id for row in rows] or [-1])).all()
    }
    return {
        "total": total,
        "items": [
            {
                "id": row.id,
                "user_id": row.user_id,
                "username": row.username,
                "method": row.method,
                "path": row.path,
                "status_code": row.status_code,
                "client_ip": row.client_ip,
                "user_agent": row.user_agent,
                "action": row.action,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "change": (
                    {
                        "entity_type": changes[row.id].entity_type,
                        "entity_id": changes[row.id].entity_id,
                        "before_snapshot": changes[row.id].before_snapshot,
                        "after_snapshot": changes[row.id].after_snapshot,
                    }
                    if row.id in changes
                    else None
                ),
            }
            for row in rows
        ],
    }
