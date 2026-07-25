from datetime import date, datetime, timedelta, timezone
from html import unescape
from typing import Optional
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urljoin, urlparse
from urllib.request import Request, urlopen
import hashlib
import json
import os
import re
import time

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
    ("中国政府采购网", "https://search.ccgp.gov.cn/bxsearch?searchtype=1&kw={keyword}", True, "财政部指定政府采购信息发布媒体，公开页面采集"),
    ("企查查", "https://www.qcc.com/web/search?key={keyword}", False, "建议配置 QCC_APP_KEY、QCC_SECRET_KEY 后使用官方招投标 API"),
    ("天眼查", "https://www.tianyancha.com/search?key={keyword}", False, "商业数据源，建议采购官方开放平台接口后启用"),
    ("千里马招标", "https://search.qianlima.com/search.jsp?key={keyword}", False, "商业数据源，公开页可访问时采集；访问受限时请使用授权服务"),
    ("乙方宝", "https://www.yfbzb.com/search/search?keywords={keyword}", False, "商业数据源，公开页可访问时采集；访问受限时请使用授权服务"),
    ("寻标宝", "https://www.xunbiaobao.com/search?keyword={keyword}", False, "商业数据源，公开页可访问时采集；访问受限时请使用授权服务"),
]

MAX_RESPONSE_BYTES = 2 * 1024 * 1024
BLOCK_MARKERS = (
    "访问过于频繁",
    "请求过于频繁",
    "安全验证",
    "请完成验证",
    "请输入验证码",
    "滑动验证",
    "访问受限",
    "captcha",
    "robot check",
    "verify you are human",
)
RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class SourceFetchError(Exception):
    def __init__(self, status: str, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


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


class SourceTestIn(BaseModel):
    keyword: str = "网络安全"


def _to_dict(row):
    return {col.name: getattr(row, col.name) for col in row.__table__.columns}


def _keywords(text: str):
    return [x.strip() for x in (text or "").replace("，", ",").replace("、", ",").split(",") if x.strip()]


def _ensure_default_sources(db: Session):
    # Seed the built-in sources only for a brand-new database. Re-creating a
    # missing row here made user-deleted sources reappear after every refresh.
    if db.query(BiddingDataSource).count():
        return
    for idx, (name, url, is_active, notes) in enumerate(DEFAULT_SOURCES, start=1):
        db.add(BiddingDataSource(name=name, search_url=url, notes=notes, sort_order=idx, is_active=is_active))
    db.commit()


def _decode_response(raw: bytes, content_type: str = "") -> str:
    charset_match = re.search(r"charset=([\w-]+)", content_type or "", flags=re.I)
    encodings = [charset_match.group(1)] if charset_match else []
    encodings.extend(["utf-8", "gb18030", "gbk"])
    for enc in encodings:
        try:
            return raw.decode(enc)
        except Exception:
            continue
    return raw.decode("utf-8", errors="ignore")


def _fetch_text(url: str, extra_headers: Optional[dict] = None, timeout: int = 15) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise SourceFetchError("invalid", "数据源地址必须是有效的 HTTP/HTTPS 地址")
    headers = {
        "User-Agent": "AQ-CRM-BiddingCollector/3.6 (+public procurement monitor)",
        "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.7",
        "Cache-Control": "no-cache",
    }
    headers.update(extra_headers or {})
    last_error = None
    for attempt in range(2):
        try:
            req = Request(url, headers=headers)
            with urlopen(req, timeout=timeout) as resp:
                raw = resp.read(MAX_RESPONSE_BYTES)
                return _decode_response(raw, resp.headers.get("Content-Type", ""))
        except HTTPError as exc:
            last_error = exc
            if exc.code in (401, 403):
                raise SourceFetchError("restricted", f"访问受限（HTTP {exc.code}），请配置授权接口或停用该来源")
            if exc.code not in RETRYABLE_STATUS or attempt == 1:
                raise SourceFetchError("error", f"来源返回 HTTP {exc.code}")
            retry_after = exc.headers.get("Retry-After")
            time.sleep(min(float(retry_after or 1), 3))
        except URLError as exc:
            last_error = exc
            if attempt == 1:
                reason = getattr(exc, "reason", exc)
                raise SourceFetchError("unavailable", f"来源连接失败：{str(reason)[:80]}")
            time.sleep(1)
        except TimeoutError:
            last_error = TimeoutError()
            if attempt == 1:
                raise SourceFetchError("unavailable", "来源连接超时")
            time.sleep(1)
    raise SourceFetchError("error", str(last_error or "来源请求失败")[:120])


def _build_search_url(template: str, keyword: str) -> str:
    return template.replace("{keyword}", quote(keyword, safe=""))


def _clean_text(value: str) -> str:
    value = re.sub(r"<[^>]+>", "", value or "")
    value = unescape(value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def _normalize_text(value: str) -> str:
    return re.sub(r"[\s\-—_（）()【】\[\]·,，。:：;；]+", "", (value or "")).lower()


def _matches_keyword(value: str, keyword: str) -> bool:
    value_norm = _normalize_text(value)
    terms = [_normalize_text(term) for term in re.split(r"[\s,+，、]+", keyword or "") if _normalize_text(term)]
    return bool(terms) and all(term in value_norm for term in terms)


def _parse_money_wan(value: str) -> float:
    match = re.search(r"(\d+(?:\.\d+)?)\s*(亿元|万元|万|元)", value or "")
    if not match:
        return 0.0
    amount = float(match.group(1))
    unit = match.group(2)
    if unit == "亿元":
        return round(amount * 10000, 2)
    if unit in ("万元", "万"):
        return round(amount, 2)
    return round(amount / 10000, 2)


def _parse_date(value: str) -> Optional[date]:
    match = re.search(r"(20\d{2})[-年/.](\d{1,2})[-月/.](\d{1,2})", value or "")
    if not match:
        return None
    try:
        return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    except ValueError:
        return None


def _looks_blocked(text: str) -> bool:
    lower = (text or "").lower()
    return any(marker.lower() in lower for marker in BLOCK_MARKERS)


def _extract_labeled_value(text: str, labels: tuple[str, ...], max_len: int = 80) -> str:
    for label in labels:
        pattern = rf"{re.escape(label)}\s*(?:名称)?\s*[:：]\s*([^；;，,。|]+)"
        match = re.search(pattern, text)
        if not match:
            continue
        value = match.group(1).strip(" -_　\t")
        value = re.split(r"(?:采购人|采购单位|招标人|建设单位|业主单位|采购代理机构|联系人|项目联系人|电话|联系方式|联系电话)\s*(?:名称)?\s*[:：]", value)[0]
        value = value.strip(" -_　\t")
        if 1 < len(value) <= max_len:
            return value
    return ""


def _extract_phone(text: str) -> str:
    labeled = _extract_labeled_value(text, ("联系电话", "联系方式", "电话", "手机"), 40)
    match = re.search(r"(?:1[3-9]\d{9}|0\d{2,3}[-\s]?\d{7,8}(?:[-转]\d{1,6})?)", labeled or text)
    return match.group(0).replace(" ", "") if match else ""


def _extract_bid_contact_info(html: str, start: int, end: int) -> dict:
    raw_context = html[max(0, start - 900): min(len(html), end + 1400)]
    text = _clean_text(raw_context)
    company = _extract_labeled_value(
        text,
        ("采购人", "采购单位", "招标人", "建设单位", "业主单位", "采购代理机构", "代理机构", "公司"),
        120,
    )
    contact = _extract_labeled_value(text, ("项目联系人", "采购联系人", "招标联系人", "联系人"), 50)
    phone = _extract_phone(text)
    return {"company": company, "contact_name": contact, "contact_phone": phone}


def _extract_results(source: BiddingDataSource, keyword: str, html: str):
    results = []
    seen = set()
    for m in re.finditer(r"<a\b[^>]*href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", html, flags=re.I | re.S):
        href, label_html = m.group(1), m.group(2)
        title = _clean_text(label_html)
        if not title or len(title) < 6:
            continue
        raw_context = html[max(0, m.start() - 500): min(len(html), m.end() + 1200)]
        context = _clean_text(raw_context)
        if not _matches_keyword(title + " " + context, keyword):
            continue
        if any(skip in href.lower() for skip in ("javascript:", "#", "login", "passport")):
            continue
        url = urljoin(source.search_url.split("{keyword}")[0], href)
        key = (title, url)
        if key in seen:
            continue
        seen.add(key)
        contact_info = _extract_bid_contact_info(html, m.start(), m.end())
        budget = _parse_money_wan(context)
        deadline_match = re.search(r"(?:截止时间|投标截止|开标时间)\s*[:：]?\s*([^；;，,。|]{6,40})", context)
        deadline = _parse_date(deadline_match.group(1) if deadline_match else "")
        results.append({
            "title": title[:180],
            "url": url,
            "source": source.name,
            "keyword": keyword,
            "budget": budget,
            "deadline": deadline,
            **contact_info,
        })
        if len(results) >= 5:
            break
    return results


def _first_party_units(row: dict) -> tuple[str, str, str]:
    units = row.get("BidInviUnitList") or row.get("bidInviUnitList") or []
    if not isinstance(units, list) or not units:
        return "", "", ""
    first = units[0] if isinstance(units[0], dict) else {}
    return (
        str(first.get("Name") or first.get("name") or ""),
        str(first.get("Contact") or first.get("contact") or ""),
        str(first.get("TelNo") or first.get("telNo") or ""),
    )


def _extract_qcc_rows(payload: dict) -> list[dict]:
    result = payload.get("Result") or payload.get("result") or payload.get("Data") or payload.get("data") or {}
    if isinstance(result, dict):
        result = result.get("Data") or result.get("data") or result.get("List") or result.get("list") or []
    return result if isinstance(result, list) else []


def _collect_qcc_api(keyword: str) -> list[dict]:
    app_key = os.getenv("QCC_APP_KEY", "").strip()
    secret_key = os.getenv("QCC_SECRET_KEY", "").strip()
    if not app_key or not secret_key:
        raise SourceFetchError("authorization_required", "未配置企查查授权接口密钥")
    timestamp = str(int(time.time()))
    token = hashlib.md5(f"{app_key}{timestamp}{secret_key}".encode("utf-8")).hexdigest().upper()
    params = urlencode({"key": app_key, "keyword": keyword, "pageIndex": 1, "pageSize": 20})
    text = _fetch_text(
        f"https://api.qichacha.com/TenderCheck/GetList?{params}",
        {"Token": token, "Timespan": timestamp},
    )
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        raise SourceFetchError("error", "企查查授权接口返回了无效 JSON")
    rows = []
    for item in _extract_qcc_rows(payload):
        if not isinstance(item, dict):
            continue
        title = str(item.get("Title") or item.get("title") or "").strip()
        if not title or not _matches_keyword(title, keyword):
            continue
        company, contact_name, contact_phone = _first_party_units(item)
        deadline_text = str(item.get("BidEndDate") or item.get("bidEndDate") or "")
        rows.append({
            "title": title[:180],
            "url": str(item.get("ContentUrl") or item.get("contentUrl") or ""),
            "source": "企查查",
            "keyword": keyword,
            "company": company,
            "contact_name": contact_name,
            "contact_phone": contact_phone,
            "budget": _parse_money_wan(str(item.get("BudgetAmt") or item.get("budgetAmt") or "")),
            "deadline": _parse_date(deadline_text),
            "region": " / ".join(filter(None, [
                str(item.get("Province") or item.get("province") or ""),
                str(item.get("City") or item.get("city") or ""),
            ])),
        })
    return rows


def _collect_source(source: BiddingDataSource, keyword: str) -> list[dict]:
    if "企查查" in source.name and os.getenv("QCC_APP_KEY") and os.getenv("QCC_SECRET_KEY"):
        return _collect_qcc_api(keyword)
    html = _fetch_text(_build_search_url(source.search_url, keyword))
    results = _extract_results(source, keyword, html)
    if not results and _looks_blocked(html):
        raise SourceFetchError("restricted", "来源要求登录或人机验证，请使用授权接口或停用该来源")
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


@router.post("/sources/{source_id}/test")
def test_source(source_id: int, data: SourceTestIn, db: Session = Depends(get_db), user=Depends(require_user)):
    require_admin_role(user)
    row = db.query(BiddingDataSource).filter_by(id=source_id).first()
    if not row:
        raise HTTPException(404, "数据源不存在")
    keyword = (data.keyword or "").strip()
    if not keyword:
        raise HTTPException(400, "请输入测试关键词")
    started_at = time.monotonic()
    try:
        results = _collect_source(row, keyword)
        status = "success" if results else "empty"
        message = f"找到 {len(results)} 条匹配结果" if results else "来源可访问，但本次未找到匹配结果"
    except SourceFetchError as exc:
        results = []
        status = exc.status
        message = exc.message
    except Exception as exc:
        results = []
        status = "error"
        message = f"测试失败：{str(exc)[:100]}"
    return {
        "source": row.name,
        "status": status,
        "message": message,
        "elapsed_ms": int((time.monotonic() - started_at) * 1000),
        "sample_count": len(results),
        "samples": results[:3],
    }


@router.post("/collect")
def collect_biddings(db: Session = Depends(get_db), user=Depends(require_user)):
    _ensure_default_sources(db)
    sources = db.query(BiddingDataSource).filter_by(is_active=True).order_by(BiddingDataSource.sort_order, BiddingDataSource.id).all()
    sub_query = db.query(BidRadarSubscription).filter_by(is_active=True)
    if user.role != ROLE_ADMIN:
        sub_query = sub_query.filter(BidRadarSubscription.owner_id == user.id)
    subs = sub_query.all()
    keyword_pairs = []
    for sub in subs:
        for word in _keywords(sub.keywords):
            keyword_pairs.append((sub, word))
    if not sources:
        return {
            "collected_count": 0,
            "total_sources": 0,
            "keyword_stats": {},
            "collected": [],
            "skipped": [],
            "source_stats": {},
            "source_reports": [],
            "source_errors": [],
            "message": "请先启用至少一个招标数据源",
        }
    if not keyword_pairs:
        return {
            "collected_count": 0,
            "total_sources": len(sources),
            "keyword_stats": {},
            "collected": [],
            "skipped": [],
            "source_stats": {},
            "source_reports": [],
            "source_errors": [],
            "message": "请先设置监测关键词",
        }
    if len(keyword_pairs) * len(sources) > 100:
        raise HTTPException(400, "启用的数据源与关键词组合过多，请控制在 100 组以内")

    collected, skipped, source_errors = [], [], []
    keyword_stats, source_stats = {}, {s.name: 0 for s in sources}
    source_reports = []
    existing_titles = {_normalize_text(name) for (name,) in db.query(Lead.name).all() if name}
    existing_items = {
        (_normalize_text(title), source_name or "")
        for title, source_name in db.query(BidRadarItem.title, BidRadarItem.source).all()
        if title
    }
    for source in sources:
        report = {
            "source": source.name,
            "status": "empty",
            "matched": 0,
            "created": 0,
            "duplicates": 0,
            "message": "来源可访问，但未找到匹配结果",
        }
        fetched_any = False
        for sub, keyword in keyword_pairs:
            try:
                results = _collect_source(source, keyword)
                fetched_any = True
            except SourceFetchError as exc:
                if report["status"] != "success":
                    report["status"] = exc.status
                    report["message"] = exc.message
                source_errors.append({"source": source.name, "keyword": keyword, "status": exc.status, "error": exc.message})
                continue
            except Exception as exc:
                message = f"采集失败：{str(exc)[:120]}"
                if report["status"] != "success":
                    report["status"] = "error"
                    report["message"] = message
                source_errors.append({"source": source.name, "keyword": keyword, "status": "error", "error": message})
                continue
            source_stats[source.name] += len(results)
            report["matched"] += len(results)
            if results:
                report["status"] = "success"
                report["message"] = "采集成功"
            for result in results:
                title = result["title"]
                company = result.get("company") or ""
                contact_name = result.get("contact_name") or ""
                contact_phone = result.get("contact_phone") or ""
                title_key = _normalize_text(title)
                item_key = (title_key, source.name)
                note_parts = [f"招标采集：来源 {source.name}", f"关键词 {keyword}", f"链接 {result['url']}"]
                if company:
                    note_parts.append(f"采购单位 {company}")
                if contact_name:
                    note_parts.append(f"联系人 {contact_name}")
                if contact_phone:
                    note_parts.append(f"电话 {contact_phone}")
                if title_key in existing_titles or item_key in existing_items:
                    skipped.append({"name": title, "source_site": source.name})
                    report["duplicates"] += 1
                    continue
                lead = Lead(
                    name=title,
                    company=company,
                    contact_name=contact_name or None,
                    contact_phone=contact_phone or None,
                    source="bidding",
                    quality="warm",
                    status="new",
                    industry="招投标",
                    assigned_to=user.id,
                    notes="；".join(note_parts),
                )
                db.add(lead)
                db.flush()
                item = BidRadarItem(
                    subscription_id=sub.id,
                    title=title,
                    buyer=company,
                    source=source.name,
                    url=result["url"],
                    region=result.get("region") or sub.regions,
                    budget=float(result.get("budget") or 0),
                    deadline=result.get("deadline"),
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
                    "contact_name": lead.contact_name,
                    "contact_phone": lead.contact_phone,
                    "source_site": source.name,
                    "budget": float(result.get("budget") or 0),
                    "deadline": result["deadline"].isoformat() if result.get("deadline") else "-",
                    "url": result["url"],
                }
                collected.append(row)
                existing_titles.add(title_key)
                existing_items.add(item_key)
                report["created"] += 1
                keyword_stats[keyword] = keyword_stats.get(keyword, 0) + 1
        if fetched_any and report["status"] != "success":
            report["status"] = "empty"
            report["message"] = "来源可访问，但未找到匹配结果"
        source_reports.append(report)
    db.commit()
    successful_sources = sum(1 for report in source_reports if report["status"] == "success")
    return {
        "collected_count": len(collected),
        "total_sources": len(sources),
        "successful_sources": successful_sources,
        "keyword_stats": keyword_stats,
        "collected": collected,
        "skipped": skipped[:20],
        "source_stats": source_stats,
        "source_reports": source_reports,
        "source_errors": source_errors[:20],
        "message": (
            f"采集完成，新增 {len(collected)} 条线索"
            if successful_sources
            else "本次没有可用来源，请在数据源中查看测试结果并配置公开来源或授权接口"
        ),
    }


@router.get("/stats")
def bidding_stats(db: Session = Depends(get_db), user=Depends(require_user)):
    total = db.query(Lead).filter_by(source="bidding").count()
    return {"total_bidding_leads": total}
