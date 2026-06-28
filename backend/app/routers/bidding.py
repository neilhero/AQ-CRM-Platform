from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from datetime import datetime, timezone, timedelta
from app.database import get_db
from app.models import Lead
from app.routers.utils import require_user

CST = timezone(timedelta(hours=8))
router = APIRouter()

MOCK_BIDDINGS = [
    {"title": "AI大模型安全评测平台采购", "source": "千里马", "amount": 800, "company": "某省级大数据中心"},
    {"title": "智能防火墙系统建设项目", "source": "中国招标网", "amount": 500, "company": "某市公安"},
    {"title": "AI安全护栏技术集成服务", "source": "政府采购网", "amount": 350, "company": "某金融机构"},
    {"title": "大模型内容安全检测平台", "source": "千里马", "amount": 600, "company": "某运营商"},
    {"title": "AI系统安全评估服务采购", "source": "招标在线", "amount": 280, "company": "某能源集团"},
    {"title": "智能体安全防护系统", "source": "中国招标网", "amount": 450, "company": "某教育机构"},
    {"title": "大模型对抗样本检测工具", "source": "政府采购网", "amount": 180, "company": "某医疗单位"},
    {"title": "AI安全合规审计平台", "source": "千里马", "amount": 320, "company": "某政府部门"},
]

@router.post("/collect")
def collect_biddings(db: Session=Depends(get_db), user=Depends(require_user)):
    count = 0
    for b in MOCK_BIDDINGS:
        existing = db.query(Lead).filter_by(name=b["title"]).first()
        if not existing:
            l = Lead(name=b["title"], company=b["company"], source="bidding",
                     quality="warm", status="new", industry="Government",
                     notes=f"来源: {b['source']}, 预算: {b['amount']}万元")
            db.add(l)
            count += 1
    db.commit()
    return {"collected": count, "total_sources": len(MOCK_BIDDINGS)}

@router.get("/stats")
def bidding_stats(db: Session=Depends(get_db), user=Depends(require_user)):
    total = db.query(Lead).filter_by(source="bidding").count()
    return {"total_bidding_leads": total}
