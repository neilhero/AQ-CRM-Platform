from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from typing import Optional
import io
from app.database import get_db
from app.models import Customer, Lead
from app.routers.utils import require_user

router = APIRouter()

@router.get("/template/{type}")
def get_template(type: str, user=Depends(require_user)):
    if type == "customers":
        return {"headers": ["name","industry","address","website","level","description"],
                "sample": ["Example Corp","Technology","Beijing","https://example.com","B","Sample customer"]}
    elif type == "leads":
        return {"headers": ["name","company","contact_name","contact_phone","source","industry","notes"],
                "sample": ["Lead A","Company A","Zhang San","13800000000","website","Tech","Sample lead"]}
    return {"error": "Unknown type"}

@router.post("/preview")
async def preview_import(file: UploadFile=File(...), type: str="customers", user=Depends(require_user)):
    content = await file.read()
    text = content.decode("utf-8")
    lines = text.strip().split("\n")
    if len(lines) < 2:
        raise HTTPException(400, "Empty file")
    headers = [h.strip() for h in lines[0].split(",")]
    rows = []
    for line in lines[1:]:
        vals = [v.strip() for v in line.split(",")]
        rows.append(dict(zip(headers, vals)))
    return {"headers": headers, "rows": rows, "total": len(rows)}

@router.post("/confirm")
async def confirm_import(file: UploadFile=File(...), type: str="customers",
                         db: Session=Depends(get_db), user=Depends(require_user)):
    content = await file.read()
    text = content.decode("utf-8")
    lines = text.strip().split("\n")
    headers = [h.strip() for h in lines[0].split(",")]
    count = 0
    for line in lines[1:]:
        vals = [v.strip() for v in line.split(",")]
        row = dict(zip(headers, vals))
        if type == "customers":
            if not db.query(Customer).filter_by(name=row.get("name","")).first():
                db.add(Customer(name=row.get("name",""), industry=row.get("industry",""),
                                address=row.get("address",""), website=row.get("website",""),
                                level=row.get("level","C"), description=row.get("description","")))
                count += 1
        elif type == "leads":
            db.add(Lead(name=row.get("name",""), company=row.get("company",""),
                        contact_name=row.get("contact_name",""), contact_phone=row.get("contact_phone",""),
                        source=row.get("source","other"), industry=row.get("industry",""),
                        notes=row.get("notes","")))
            count += 1
    db.commit()
    return {"imported": count}
