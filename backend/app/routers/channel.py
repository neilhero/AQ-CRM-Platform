from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional
from app.database import get_db
from app.models import ChannelPartner
from app.schemas import ChannelPartnerCreate, ChannelPartnerUpdate
from app.routers.utils import require_user, require_admin

router = APIRouter()

@router.get("")
def list_partners(keyword: Optional[str]=Query(None), level: Optional[str]=Query(None),
                  region: Optional[str]=Query(None), skip: int=Query(0,ge=0), limit: int=Query(100,ge=1,le=500),
                  db: Session=Depends(get_db), user=Depends(require_user)):
    q = db.query(ChannelPartner)
    if keyword: q = q.filter(ChannelPartner.name.contains(keyword))
    if level: q = q.filter(ChannelPartner.level == level)
    if region: q = q.filter(ChannelPartner.region == region)
    return q.order_by(ChannelPartner.name).offset(skip).limit(limit).all()

@router.get("/{pid}")
def get_partner(pid: int, db: Session=Depends(get_db), user=Depends(require_user)):
    p = db.query(ChannelPartner).filter_by(id=pid).first()
    if not p: raise HTTPException(404, "Not found")
    return p

@router.post("", status_code=201)
def create_partner(data: ChannelPartnerCreate, db: Session=Depends(get_db), admin=Depends(require_admin)):
    p = ChannelPartner(**data.model_dump())
    db.add(p); db.commit(); db.refresh(p); return p

@router.put("/{pid}")
def update_partner(pid: int, data: ChannelPartnerUpdate, db: Session=Depends(get_db), admin=Depends(require_admin)):
    p = db.query(ChannelPartner).filter_by(id=pid).first()
    if not p: raise HTTPException(404, "Not found")
    for k,v in data.model_dump(exclude_unset=True).items(): setattr(p,k,v)
    db.commit(); db.refresh(p); return p

@router.delete("/{pid}", status_code=204)
def delete_partner(pid: int, db: Session=Depends(get_db), admin=Depends(require_admin)):
    p = db.query(ChannelPartner).filter_by(id=pid).first()
    if not p: raise HTTPException(404, "Not found")
    db.delete(p); db.commit()
