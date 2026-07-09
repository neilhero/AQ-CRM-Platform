from datetime import date, datetime, timedelta, timezone
from html import unescape
from typing import Optional
from urllib.parse import quote, urljoin
from urllib.request import Request, urlopen
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import BiddingDataSource, BidRadarFollowTask, BidRadarItem, BidRadarSubscription, Lead
from app.permissions import ROLE_ADMIN, require_admin_role
from app.routers.utils import require_user

CST = timezone(timedelta(hours=8))
router = APIRouter()


DEFAULT_SOURCES = [
    ("企查查", "https://www.qcc.com/web/search?key={keyword}", "企业侧招采与公告检索"),
    ("天眼查", "https://www.tianyancha.com/search?key={keyword}", "企业侧招采与公告检索"),
    ("千里马招标", "https://search.qianlima.com/search.jsp?key={keyword}", "招标公告聚合检索"),
    ("乙方宝", "https://www.yfbzb.com/search/search?keywords={keyword}", "招标采购信息检索"),
    ("寻标宝", "https://www.xunbiaobao.com/search?keyword={keyword}", "招标采购信息检索"),
    ("中国政府采购网", "http://search.ccgp.gov.cn/bxsearch?searchtype=1&kw={keyword}", "政府采购公告检索"),
    ("必应招标搜索", "https://cn.bing.com/search?q={keyword}%20%E6%8B%9B%E6%A0%87%20site%3Aqianlima.com%20OR%20site%3Accgp.gov.cn%20OR%20site%3Ayfbzb.com", "公网招标采购兜底检索"),
]


class KeywordIn(BaseModel):
    name: str
    keywords: str
    regions: Optional[str] = None
    product_lines: Optional[str] = None
    min_budget: Optional[float] = 0
    is_active: Optional[bool] = True


class SourceIn(BaseModel):
    name: str
    search_url: str
    is_active: Optional[bool] = True
    sort_order: Optional[int] = 0
    notes: Optional[str] = None


def _to_dict(row):
    return {col.name: getattr(row, col.name) for col in row.__table__.columns}


def _keywords(text: str):
    return [x.strip() for x in (text or "").replace("，", ",").replace("、", ",").split(",") if x.strip()]


def _ensure_default_sources(db: Session):
    existing_rows = {row.name: row for row in db.query(BiddingDataSource).all()}
    for idx, (name, url, notes) in enumerate(DEFAULT_SOURCES, start=1):
        if name in existing_rows:
            if name == "必应招标搜索":
                existing_rows[name].search_url = url
                existing_rows[name].notes = notes
            continue
        db.add(BiddingDataSource(name=name, search_url=url, notes=notes, sort_order=idx, is_active=True))
    db.commit()


def _fetch_html(url: str) -> str:
    req = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.7",
        },
    )
    with urlopen(req, timeout=12) as resp:
        raw = resp.read(1024 * 512)
    for enc in ("utf-8", "gb18030", "gbk"):
        try:
            return raw.decode(enc)
        except Exception:
            continue
    return raw.decode("utf-8", errors="ignore")


def _clean_text(value: str) -> str:
    value = re.sub(r"<[^>]+>", "", value or "")
    value = unescape(value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def _extract_results(source: BiddingDataSource, keyword: str, html: str):
    results = []
    seen = set()
    for m in re.finditer(r"<a\b[^>]*href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", html, flags=re.I | re.S):
        href, label_html = m.group(1), m.group(2)
        title = _clean_text(label_html)
        if not title or len(title) < 6:
            continue
        text = title.lower()
        if keyword.lower() not in text and not any(word in title for word in ("招标", "采购", "项目", "公告", "中标", "成交")):
            continue
        if any(skip in href.lower() for skip in ("javascript:", "#", "login", "passport")):
            continue
        url = urljoin(source.search_url.split("{keyword}")[0], href)
        key = (title, url)
        if key in seen:
            continue
        seen.add(key)
        results.append({"title": title[:180], "url": url, "source": source.name, "keyword": keyword})
        if len(results) >= 5:
            break
    return results


def _create_task(db: Session, item: BidRadarItem, owner_id: Optional[int]):
    due = item.deadline - timedelta(days=3) if item.deadline else date.today() + timedelta(days=3)
    task = BidRadarFollowTask(
        radar_item_id=item.id,
        title=f"跟进招标：{item.title}",
        owner_id=owner_id,
        due_date=due,
        notes=f"来源：{item.source}；关键词：{item.matched_product_line or '-'}；链接：{item.url or '-'}",
    )
    db.add(task)
    return task


@router.get("/keywords")
def list_keywords(db: Session = Depends(get_db), user=Depends(require_user)):
    q = db.query(BidRadarSubscription)
    if user.role != ROLE_ADMIN:
        q = q.filter(BidRadarSubscription.owner_id == user.id)
    return [_to_dict(r) for r in q.order_by(BidRadarSubscription.created_at.desc()).all()]


@router.post("/keywords", status_code=201)
def create_keyword(data: KeywordIn, db: Session = Depends(get_db), user=Depends(require_user)):
    if not _keywords(data.keywords):
        raise HTTPException(400, "请填写至少一个监测关键词")
    row = BidRadarSubscription(**data.model_dump(), owner_id=user.id)
    db.add(row)
    db.commit()
    db.refresh(row)
    return _to_dict(row)


@router.put("/keywords/{keyword_id}")
def update_keyword(keyword_id: int, data: KeywordIn, db: Session = Depends(get_db), user=Depends(require_user)):
    row = db.query(BidRadarSubscription).filter_by(id=keyword_id).first()
    if not row:
        raise HTTPException(404, "监测关键词不存在")
    if user.role != ROLE_ADMIN and row.owner_id != user.id:
        raise HTTPException(403, "只能维护自己的监测关键词")
    if not _keywords(data.keywords):
        raise HTTPException(400, "请填写至少一个监测关键词")
    for k, v in data.model_dump().items():
        setattr(row, k, v)
    db.commit()
    db.refresh(row)
    return _to_dict(row)


@router.delete("/keywords/{keyword_id}", status_code=204)
def delete_keyword(keyword_id: int, db: Session = Depends(get_db), user=Depends(require_user)):
    row = db.query(BidRadarSubscription).filter_by(id=keyword_id).first()
    if not row:
        raise HTTPException(404, "监测关键词不存在")
    if user.role != ROLE_ADMIN and row.owner_id != user.id:
        raise HTTPException(403, "只能删除自己的监测关键词")
    db.delete(row)
    db.commit()


@router.get("/sources")
def list_sources(db: Session = Depends(get_db), user=Depends(require_user)):
    _ensure_default_sources(db)
    return [_to_dict(r) for r in db.query(BiddingDataSource).order_by(BiddingDataSource.sort_order, BiddingDataSource.id).all()]


@router.post("/sources", status_code=201)
def create_source(data: SourceIn, db: Session = Depends(get_db), user=Depends(require_user)):
    require_admin_role(user)
    if "{keyword}" not in data.search_url:
        raise HTTPException(400, "搜索地址必须包含 {keyword} 占位符")
    row = BiddingDataSource(**data.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return _to_dict(row)


@router.put("/sources/{source_id}")
def update_source(source_id: int, data: SourceIn, db: Session = Depends(get_db), user=Depends(require_user)):
    require_admin_role(user)
    row = db.query(BiddingDataSource).filter_by(id=source_id).first()
    if not row:
        raise HTTPException(404, "数据源不存在")
    if "{keyword}" not in data.search_url:
        raise HTTPException(400, "搜索地址必须包含 {keyword} 占位符")
    for k, v in data.model_dump().items():
        setattr(row, k, v)
    db.commit()
    db.refresh(row)
    return _to_dict(row)


@router.delete("/sources/{source_id}", status_code=204)
def delete_source(source_id: int, db: Session = Depends(get_db), user=Depends(require_user)):
    require_admin_role(user)
    row = db.query(BiddingDataSource).filter_by(id=source_id).first()
    if not row:
        raise HTTPException(404, "数据源不存在")
    db.delete(row)
    db.commit()


@router.post("/collect")
def collect_biddings(db: Session = Depends(get_db), user=Depends(require_user)):
    _ensure_default_sources(db)
    sources = db.query(BiddingDataSource).filter_by(is_active=True).order_by(BiddingDataSource.sort_order, BiddingDataSource.id).all()
    subs = db.query(BidRadarSubscription).filter_by(is_active=True).all()
    keyword_pairs = []
    for sub in subs:
        for word in _keywords(sub.keywords):
            keyword_pairs.append((sub, word))
    if not keyword_pairs:
        return {"collected_count": 0, "total_sources": len(sources), "keyword_stats": {}, "collected": [], "skipped": [], "source_stats": {}, "source_errors": [], "message": "请先设置监测关键词"}

    collected, skipped, source_errors = [], [], []
    keyword_stats, source_stats = {}, {s.name: 0 for s in sources}
    for source in sources:
        for sub, keyword in keyword_pairs:
            url = quote(source.search_url.replace("{keyword}", quote(keyword)), safe=":/?&=%")
            try:
                html = _fetch_html(url)
                results = _extract_results(source, keyword, html)
            except Exception as exc:
                source_errors.append({"source": source.name, "keyword": keyword, "error": str(exc)[:160]})
                continue
            source_stats[source.name] += len(results)
            for result in results:
                title = result["title"]
                exists = db.query(Lead).filter_by(name=title).first()
                if exists:
                    skipped.append({"name": title, "source_site": source.name})
                    continue
                item_exists = db.query(BidRadarItem).filter_by(title=title, source=source.name).first()
                if item_exists:
                    skipped.append({"name": title, "source_site": source.name})
                    continue
                lead = Lead(
                    name=title,
                    company="待核实",
                    source="bidding",
                    quality="warm",
                    status="new",
                    industry="招投标",
                    assigned_to=user.id,
                    notes=f"招标采集：来源 {source.name}；关键词 {keyword}；链接 {result['url']}",
                )
                db.add(lead)
                db.flush()
                item = BidRadarItem(
                    subscription_id=sub.id,
                    title=title,
                    buyer="待核实",
                    source=source.name,
                    url=result["url"],
                    region=sub.regions,
                    matched_product_line=keyword,
                    lead_id=lead.id,
                    notes=f"由线索管理招标采集创建；关键词：{keyword}",
                )
                db.add(item)
                db.flush()
                _create_task(db, item, user.id)
                row = {
                    "id": lead.id,
                    "name": lead.name,
                    "company": lead.company,
                    "source_site": source.name,
                    "budget": 0,
                    "deadline": "-",
                    "quality": "温",
                    "url": result["url"],
                }
                collected.append(row)
                keyword_stats[keyword] = keyword_stats.get(keyword, 0) + 1
    db.commit()
    return {
        "collected_count": len(collected),
        "total_sources": len(sources),
        "keyword_stats": keyword_stats,
        "collected": collected,
        "skipped": skipped[:20],
        "source_stats": source_stats,
        "source_errors": source_errors[:20],
    }


@router.get("/stats")
def bidding_stats(db: Session = Depends(get_db), user=Depends(require_user)):
    total = db.query(Lead).filter_by(source="bidding").count()
    return {"total_bidding_leads": total}
