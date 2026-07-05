from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.database import engine, Base, SessionLocal
from app.models import User, Customer, ChannelPartner, Contact, Product, ProductSubCategory, Opportunity, FollowUp, CommissionRule, Lead, MenuConfig, StageConfig, IndustryConfig, AuditLog, AuditChange, CustomerSecurityProfile, ChannelRegistration, PresalesRequest, BidRadarSubscription, BidRadarItem, BidRadarFollowTask, SalesTarget, CustomerOperationProfile, OpportunityReview, PartnerGrowthRecord, CustomerIdentity, ChannelRegistrationRule, ChannelRegistrationGovernance, PresalesSlaRule, PresalesSlaTracking, BidConversion, CustomerDecisionNode, CustomerDecisionEdge, CustomerCompetitorInstall, IndustryProductRecommendation, PocRecord, ForecastSnapshot, PresalesAsset, BidScoreCriterion
from datetime import date, datetime, timezone, timedelta
import hashlib, os, json, re
from sqlalchemy import text

CST = timezone(timedelta(hours=8))

from app.services.auth import hash_password
from app.services.auth import get_current_user

app = FastAPI(title="AnQuan CRM v3.3")

app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:8097", "http://127.0.0.1:8097", "http://121.41.66.121"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

Base.metadata.create_all(bind=engine)
UPLOAD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

def ensure_schema_updates():
    with engine.begin() as conn:
        if engine.dialect.name == "sqlite":
            product_cols = [row[1] for row in conn.execute(text("PRAGMA table_info(products)")).fetchall()]
            if "sort_order" not in product_cols:
                conn.execute(text("ALTER TABLE products ADD COLUMN sort_order INTEGER DEFAULT 0"))
            recommendation_cols = [row[1] for row in conn.execute(text("PRAGMA table_info(industry_product_recommendations)")).fetchall()]
            if "product_sub_category" not in recommendation_cols:
                conn.execute(text("ALTER TABLE industry_product_recommendations ADD COLUMN product_sub_category VARCHAR(128)"))
            user_cols = [row[1] for row in conn.execute(text("PRAGMA table_info(users)")).fetchall()]
            if "manager_id" not in user_cols:
                conn.execute(text("ALTER TABLE users ADD COLUMN manager_id INTEGER"))
            presales_cols = [row[1] for row in conn.execute(text("PRAGMA table_info(presales_requests)")).fetchall()]
            if "requester_id" not in presales_cols:
                conn.execute(text("ALTER TABLE presales_requests ADD COLUMN requester_id INTEGER"))
            asset_cols = [row[1] for row in conn.execute(text("PRAGMA table_info(presales_assets)")).fetchall()]
            if "product_sub_category" not in asset_cols:
                conn.execute(text("ALTER TABLE presales_assets ADD COLUMN product_sub_category VARCHAR(128)"))
            if "file_name" not in asset_cols:
                conn.execute(text("ALTER TABLE presales_assets ADD COLUMN file_name VARCHAR(256)"))
            if "file_url" not in asset_cols:
                conn.execute(text("ALTER TABLE presales_assets ADD COLUMN file_url VARCHAR(512)"))
            if "file_size" not in asset_cols:
                conn.execute(text("ALTER TABLE presales_assets ADD COLUMN file_size INTEGER DEFAULT 0"))

ensure_schema_updates()

AUDIT_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

AUDIT_ENTITY_MAP = {
    "customers": Customer,
    "opportunities": Opportunity,
    "products": Product,
    "channel-partners": ChannelPartner,
    "channel": ChannelPartner,
    "contacts": Contact,
    "leads": Lead,
    "commissions": CommissionRule,
    "sales-targets": SalesTarget,
    "channel-registrations": ChannelRegistration,
    "presales-requests": PresalesRequest,
    "bid-radar-items": BidRadarItem,
    "bid-radar-subscriptions": BidRadarSubscription,
    "customer-identities": CustomerIdentity,
    "channel-registration-rules": ChannelRegistrationRule,
    "channel-registration-governance": ChannelRegistrationGovernance,
    "presales-sla-rules": PresalesSlaRule,
    "presales-sla-tracking": PresalesSlaTracking,
    "bid-conversions": BidConversion,
    "decision-nodes": CustomerDecisionNode,
    "decision-edges": CustomerDecisionEdge,
    "competitor-installs": CustomerCompetitorInstall,
    "industry-product-recommendations": IndustryProductRecommendation,
    "poc-records": PocRecord,
    "forecast-snapshots": ForecastSnapshot,
    "presales-assets": PresalesAsset,
    "bid-score-criteria": BidScoreCriterion,
    "opportunity-reviews": OpportunityReview,
    "partner-growth-records": PartnerGrowthRecord,
}

def _audit_json_value(value):
    if hasattr(value, "value"):
        return value.value
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value

def _audit_snapshot(db, model, entity_id):
    if not model or not entity_id:
        return None
    if model is CustomerIdentity:
        row = db.query(model).filter_by(customer_id=entity_id).first()
    elif model is ChannelRegistrationGovernance:
        row = db.query(model).filter_by(registration_id=entity_id).first()
    else:
        row = db.query(model).filter_by(id=entity_id).first()
    if not row:
        return None
    return json.dumps({c.name: _audit_json_value(getattr(row, c.name)) for c in row.__table__.columns}, ensure_ascii=False)

def _audit_entity_from_path(path):
    parts = [p for p in path.split("/") if p]
    if len(parts) < 3 or parts[0] != "api":
        return None, None, None
    entity_key = parts[1]
    if parts[1] == "security-business" and len(parts) >= 3:
        if parts[2] == "channel-registrations":
            entity_key = "channel-registrations"
        elif parts[2] == "presales-requests":
            entity_key = "presales-requests"
        elif parts[2] == "bid-radar" and len(parts) >= 4:
            entity_key = "bid-radar-" + parts[3]
    elif parts[1] == "sales-growth" and len(parts) >= 3:
        if parts[2] == "targets":
            entity_key = "sales-targets"
        elif parts[2] == "opportunity-reviews":
            entity_key = "opportunity-reviews"
        elif parts[2] == "partner-growth" and len(parts) >= 4 and parts[3] == "records":
            entity_key = "partner-growth-records"
    elif parts[1] == "business-excellence" and len(parts) >= 3:
        if parts[2] in {"industry-product-recommendations", "poc-records", "forecast-snapshots", "presales-assets"}:
            entity_key = parts[2]
        elif parts[2] == "customers" and len(parts) >= 5 and parts[4] == "identity":
            entity_key = "customer-identities"
        elif parts[2] == "customers" and len(parts) >= 5 and parts[4] == "competitor-installs":
            entity_key = "competitor-installs"
        elif parts[2] == "customers" and len(parts) >= 5 and parts[4] == "decision-nodes":
            entity_key = "decision-nodes"
        elif parts[2] == "customers" and len(parts) >= 5 and parts[4] == "decision-edges":
            entity_key = "decision-edges"
        elif parts[2] == "bid-radar" and len(parts) >= 5 and parts[3] == "items":
            entity_key = "bid-radar-items"
        elif parts[2] == "channel-registration-rule":
            entity_key = "channel-registration-rules"
        elif parts[2] == "channel-registrations":
            entity_key = "channel-registrations"
    entity_id = None
    for part in parts[2:]:
        if re.fullmatch(r"\d+", part):
            entity_id = int(part)
            break
    return entity_key, AUDIT_ENTITY_MAP.get(entity_key), entity_id

@app.middleware("http")
async def audit_write_requests(request, call_next):
    response = None
    entity_key, entity_model, entity_id = _audit_entity_from_path(request.url.path)
    before_snapshot = None
    if request.method in {"PUT", "PATCH", "DELETE"} and request.url.path.startswith("/api/") and entity_model and entity_id:
        db_before = SessionLocal()
        try:
            before_snapshot = _audit_snapshot(db_before, entity_model, entity_id)
        finally:
            db_before.close()
    try:
        response = await call_next(request)
        return response
    finally:
        if request.method in AUDIT_METHODS and request.url.path.startswith("/api/"):
            db = SessionLocal()
            try:
                user = None
                auth_header = request.headers.get("authorization") or ""
                if auth_header.startswith("Bearer "):
                    user = get_current_user(db, auth_header.replace("Bearer ", ""))
                client = request.client.host if request.client else ""
                log = AuditLog(
                    user_id=user.id if user else None,
                    username=user.username if user else None,
                    method=request.method,
                    path=request.url.path,
                    status_code=response.status_code if response else 500,
                    client_ip=client,
                    user_agent=request.headers.get("user-agent", "")[:512],
                    action=f"{request.method} {request.url.path}",
                )
                db.add(log)
                db.flush()
                if entity_model and entity_id and (before_snapshot or request.method in {"PUT", "PATCH", "DELETE"}):
                    db.add(AuditChange(
                        audit_log_id=log.id,
                        entity_type=entity_key,
                        entity_id=entity_id,
                        before_snapshot=before_snapshot,
                        after_snapshot=None if request.method == "DELETE" else _audit_snapshot(db, entity_model, entity_id),
                    ))
                db.commit()
            except Exception:
                db.rollback()
            finally:
                db.close()

@app.get("/")
def root():
    return {"message": "AnQuan CRM v3.3 API", "status": "running"}

@app.on_event("startup")
def seed():
    db = SessionLocal()
    try:
        if db.query(User).count() == 0:
            db.add(User(username="admin", password_hash=hash_password("admin@aq123"), real_name="系统管理员", role="admin"))
            db.add(User(username="channel001", password_hash=hashlib.sha256("channel123".encode()).hexdigest(), real_name="张三", role="manager"))
            db.add(User(username="sales001", password_hash=hashlib.sha256("sales123".encode()).hexdigest(), real_name="李四", role="sales"))
            db.commit()
        if db.query(Customer).count() == 0:
            custs = [
                Customer(name="浙江省政府云", industry="政数", level="VIP", owner_id=1),
                Customer(name="上海AI研究院", industry="科研", level="A", owner_id=1),
                Customer(name="北京智慧城市中心", industry="政数", level="A", owner_id=1),
                Customer(name="广州数据局", industry="政数", level="B", owner_id=1),
                Customer(name="深圳科技大学", industry="教育", level="B", owner_id=1),
                Customer(name="江苏移动", industry="运营商", level="A", owner_id=1),
                Customer(name="工商银行数据中心", industry="金融", level="VIP", owner_id=1),
                Customer(name="杭州公安", industry="公安", level="A", owner_id=1),
            ]
            for c in custs: db.add(c)
            db.commit()
        if db.query(Product).count() == 0:
            prods = [
                Product(name="安泉大模型防火墙 v3.0", category="AI安全", sub_category="大模型安全", unit_price=80),
                Product(name="安泉数据防泄漏系统", category="数据安全", sub_category="DLP", unit_price=60),
                Product(name="安泉AI教育平台", category="AI教育", sub_category="平台", unit_price=45),
                Product(name="安泉智能体安全套件", category="AI安全", sub_category="智能体安全", unit_price=95),
                Product(name="安泉红队测试工具", category="AI安全", sub_category="大模型安全", unit_price=50),
            ]
            for p in prods: db.add(p)
            db.commit()
        default_product_sub_categories = {
            "AI安全": ["大模型安全", "智能体安全"],
            "数据安全": ["WAAP", "WAF", "脱敏", "漏扫", "NGFW", "DLP"],
            "AI教育": ["AI教学平台", "实训平台", "平台"],
        }
        for category, names in default_product_sub_categories.items():
            for idx, name in enumerate(names):
                exists = db.query(ProductSubCategory).filter_by(category=category, name=name).first()
                if not exists:
                    db.add(ProductSubCategory(category=category, name=name, sort_order=idx))
        db.commit()
        if db.query(ChannelPartner).count() == 0:
            chs = [
                ChannelPartner(name="北京网安科技", contact_person="王雷", contact_phone="【手机号已脱敏】", level="金牌", region="华北"),
                ChannelPartner(name="上海安信网络", contact_person="陈明", contact_phone="【手机号已脱敏】", level="银牌", region="华东"),
                ChannelPartner(name="深圳锐安信安", contact_person="李强", contact_phone="【手机号已脱敏】", level="铜牌", region="华南"),
            ]
            for ch in chs: db.add(ch)
            db.commit()
        if db.query(CommissionRule).count() == 0:
            crs = [
                CommissionRule(partner_id=1, rate_percent=15, settlement_cycle="季度"),
                CommissionRule(partner_id=2, rate_percent=10, settlement_cycle="月度"),
                CommissionRule(partner_id=3, rate_percent=8, settlement_cycle="季度"),
            ]
            for cr in crs: db.add(cr)
            db.commit()
        if db.query(MenuConfig).count() == 0:
            menus = [
                MenuConfig(menu_key="group-dashboard", label="仪表盘", is_visible=True, sort_order=1),
                MenuConfig(menu_key="/dashboard", label="仪表盘", is_visible=True, sort_order=11, parent_key="group-dashboard"),
                MenuConfig(menu_key="/business-excellence", label="经营驾驶舱", is_visible=True, sort_order=12, parent_key="group-dashboard"),
                MenuConfig(menu_key="/follow-ups", label="今日待跟进", is_visible=True, sort_order=2),
                MenuConfig(menu_key="group-customer", label="客户管理", is_visible=True, sort_order=3),
                MenuConfig(menu_key="/customers", label="客户管理", is_visible=True, sort_order=31, parent_key="group-customer"),
                MenuConfig(menu_key="/customers/profile", label="客户360画像", is_visible=True, sort_order=32, parent_key="group-customer"),
                MenuConfig(menu_key="/customers/operations", label="客户分层运营", is_visible=True, sort_order=33, parent_key="group-customer"),
                MenuConfig(menu_key="group-opp", label="商机管理", is_visible=True, sort_order=4),
                MenuConfig(menu_key="/opportunities/direct", label="直销商机", is_visible=True, sort_order=41, parent_key="group-opp"),
                MenuConfig(menu_key="/opportunities/channel", label="渠道商机", is_visible=True, sort_order=42, parent_key="group-opp"),
                MenuConfig(menu_key="group-leads", label="线索管理", is_visible=True, sort_order=5),
                MenuConfig(menu_key="/leads", label="线索管理", is_visible=True, sort_order=51, parent_key="group-leads"),
                MenuConfig(menu_key="/leads/bid-radar", label="招标雷达", is_visible=True, sort_order=52, parent_key="group-leads"),
                MenuConfig(menu_key="/leads/bid-conversion", label="招标转化", is_visible=True, sort_order=53, parent_key="group-leads"),
                MenuConfig(menu_key="group-partner", label="渠道管理", is_visible=True, sort_order=6),
                MenuConfig(menu_key="/partners", label="渠道档案", is_visible=True, sort_order=61, parent_key="group-partner"),
                MenuConfig(menu_key="/partners/performance", label="渠道绩效", is_visible=True, sort_order=62, parent_key="group-partner"),
                MenuConfig(menu_key="/partners/growth", label="渠道成长", is_visible=True, sort_order=63, parent_key="group-partner"),
                MenuConfig(menu_key="/partners/registration", label="项目报备", is_visible=True, sort_order=64, parent_key="group-partner"),
                MenuConfig(menu_key="/partners/commission", label="返点管理", is_visible=True, sort_order=65, parent_key="group-partner"),
                MenuConfig(menu_key="/partners/credit", label="渠道伙伴信用", is_visible=False, sort_order=66, parent_key="group-partner"),
                MenuConfig(menu_key="group-presales", label="售前协同", is_visible=True, sort_order=7),
                MenuConfig(menu_key="/presales", label="售前协同", is_visible=True, sort_order=71, parent_key="group-presales"),
                MenuConfig(menu_key="/presales/assets", label="售前资产", is_visible=True, sort_order=72, parent_key="group-presales"),
                MenuConfig(menu_key="/security-business", label="网安业务", is_visible=False, sort_order=55),
                MenuConfig(menu_key="group-product", label="产品管理", is_visible=True, sort_order=8),
                MenuConfig(menu_key="/products", label="产品管理", is_visible=True, sort_order=81, parent_key="group-product"),
                MenuConfig(menu_key="/products/recommendations", label="推荐产品", is_visible=True, sort_order=82, parent_key="group-product"),
            ]
            for m in menus: db.add(m)
            db.commit()
        dashboard_group_menu = db.query(MenuConfig).filter_by(menu_key="group-dashboard").first()
        if not dashboard_group_menu:
            db.add(MenuConfig(menu_key="group-dashboard", label="仪表盘", is_visible=True, sort_order=1))
            db.commit()
        dashboard_menu = db.query(MenuConfig).filter_by(menu_key="/dashboard").first()
        if dashboard_menu:
            dashboard_menu.label = "仪表盘"
            dashboard_menu.parent_key = "group-dashboard"
            dashboard_menu.sort_order = 11
        business_cockpit_menu = db.query(MenuConfig).filter_by(menu_key="/business-excellence").first()
        if not business_cockpit_menu:
            db.add(MenuConfig(menu_key="/business-excellence", label="经营驾驶舱", is_visible=True, sort_order=12, parent_key="group-dashboard"))
        else:
            business_cockpit_menu.label = "经营驾驶舱"
            business_cockpit_menu.parent_key = "group-dashboard"
            business_cockpit_menu.sort_order = 12
            business_cockpit_menu.is_visible = True
        db.commit()
        customer_group_menu = db.query(MenuConfig).filter_by(menu_key="group-customer").first()
        if not customer_group_menu:
            db.add(MenuConfig(menu_key="group-customer", label="客户管理", is_visible=True, sort_order=3))
            db.commit()
        customer_menu = db.query(MenuConfig).filter_by(menu_key="/customers").first()
        if customer_menu:
            customer_menu.label = "客户管理"
            customer_menu.parent_key = "group-customer"
            customer_menu.sort_order = 31
        customer_profile_menu = db.query(MenuConfig).filter_by(menu_key="/customers/profile").first()
        if not customer_profile_menu:
            db.add(MenuConfig(menu_key="/customers/profile", label="客户360画像", is_visible=True, sort_order=32, parent_key="group-customer"))
        else:
            customer_profile_menu.label = "客户360画像"
            customer_profile_menu.parent_key = "group-customer"
            customer_profile_menu.sort_order = 32
        customer_operations_menu = db.query(MenuConfig).filter_by(menu_key="/customers/operations").first()
        if not customer_operations_menu:
            db.add(MenuConfig(menu_key="/customers/operations", label="客户分层运营", is_visible=True, sort_order=33, parent_key="group-customer"))
        else:
            customer_operations_menu.label = "客户分层运营"
            customer_operations_menu.parent_key = "group-customer"
            customer_operations_menu.sort_order = 33
        db.commit()
        leads_group_menu = db.query(MenuConfig).filter_by(menu_key="group-leads").first()
        if not leads_group_menu:
            db.add(MenuConfig(menu_key="group-leads", label="线索管理", is_visible=True, sort_order=5))
            db.commit()
        leads_menu = db.query(MenuConfig).filter_by(menu_key="/leads").first()
        if leads_menu:
            leads_menu.label = "线索管理"
            leads_menu.parent_key = "group-leads"
            leads_menu.sort_order = 51
        bid_radar_menu = db.query(MenuConfig).filter_by(menu_key="/leads/bid-radar").first()
        if not bid_radar_menu:
            db.add(MenuConfig(menu_key="/leads/bid-radar", label="招标雷达", is_visible=True, sort_order=52, parent_key="group-leads"))
        else:
            bid_radar_menu.label = "招标雷达"
            bid_radar_menu.parent_key = "group-leads"
            bid_radar_menu.sort_order = 52
        bid_conversion_menu = db.query(MenuConfig).filter_by(menu_key="/leads/bid-conversion").first()
        if not bid_conversion_menu:
            db.add(MenuConfig(menu_key="/leads/bid-conversion", label="招标转化", is_visible=True, sort_order=53, parent_key="group-leads"))
        else:
            bid_conversion_menu.label = "招标转化"
            bid_conversion_menu.parent_key = "group-leads"
            bid_conversion_menu.sort_order = 53
        presales_group_menu = db.query(MenuConfig).filter_by(menu_key="group-presales").first()
        if not presales_group_menu:
            db.add(MenuConfig(menu_key="group-presales", label="售前协同", is_visible=True, sort_order=7))
            db.commit()
        else:
            presales_group_menu.sort_order = 7
        presales_menu = db.query(MenuConfig).filter_by(menu_key="/presales").first()
        if not presales_menu:
            db.add(MenuConfig(menu_key="/presales", label="售前协同", is_visible=True, sort_order=71, parent_key="group-presales"))
        else:
            presales_menu.label = "售前协同"
            presales_menu.parent_key = "group-presales"
            presales_menu.sort_order = 71
            presales_menu.is_visible = True
        presales_assets_menu = db.query(MenuConfig).filter_by(menu_key="/presales/assets").first()
        if not presales_assets_menu:
            db.add(MenuConfig(menu_key="/presales/assets", label="售前资产", is_visible=True, sort_order=72, parent_key="group-presales"))
        else:
            presales_assets_menu.label = "售前资产"
            presales_assets_menu.parent_key = "group-presales"
            presales_assets_menu.sort_order = 72
        security_menu = db.query(MenuConfig).filter_by(menu_key="/security-business").first()
        if security_menu:
            security_menu.is_visible = False
        product_group_menu = db.query(MenuConfig).filter_by(menu_key="group-product").first()
        if not product_group_menu:
            db.add(MenuConfig(menu_key="group-product", label="产品管理", is_visible=True, sort_order=8))
            db.commit()
        else:
            product_group_menu.sort_order = 8
        products_menu = db.query(MenuConfig).filter_by(menu_key="/products").first()
        if products_menu:
            products_menu.label = "产品管理"
            products_menu.parent_key = "group-product"
            products_menu.sort_order = 81
        product_recommendations_menu = db.query(MenuConfig).filter_by(menu_key="/products/recommendations").first()
        if not product_recommendations_menu:
            db.add(MenuConfig(menu_key="/products/recommendations", label="推荐产品", is_visible=True, sort_order=82, parent_key="group-product"))
        else:
            product_recommendations_menu.label = "推荐产品"
            product_recommendations_menu.parent_key = "group-product"
            product_recommendations_menu.sort_order = 82
        partner_group_menu = db.query(MenuConfig).filter_by(menu_key="group-partner").first()
        if not partner_group_menu:
            db.add(MenuConfig(menu_key="group-partner", label="渠道管理", is_visible=True, sort_order=6))
        else:
            partner_group_menu.label = "渠道管理"
            partner_group_menu.sort_order = 6
        db.commit()
        partner_archive_menu = db.query(MenuConfig).filter_by(menu_key="/partners").first()
        if partner_archive_menu:
            partner_archive_menu.label = "渠道档案"
            partner_archive_menu.parent_key = "group-partner"
            partner_archive_menu.sort_order = 61
            partner_archive_menu.is_visible = True
        else:
            db.add(MenuConfig(menu_key="/partners", label="渠道档案", is_visible=True, sort_order=61, parent_key="group-partner"))
        registration_menu = db.query(MenuConfig).filter_by(menu_key="/partners/registration").first()
        if not registration_menu:
            db.add(MenuConfig(menu_key="/partners/registration", label="项目报备", is_visible=True, sort_order=64, parent_key="group-partner"))
            db.commit()
        else:
            registration_menu.label = "项目报备"
            registration_menu.parent_key = "group-partner"
            registration_menu.sort_order = 64
        partner_growth_menu = db.query(MenuConfig).filter_by(menu_key="/partners/growth").first()
        if not partner_growth_menu:
            db.add(MenuConfig(menu_key="/partners/growth", label="渠道成长", is_visible=True, sort_order=63, parent_key="group-partner"))
        else:
            partner_growth_menu.label = "渠道成长"
            partner_growth_menu.parent_key = "group-partner"
            partner_growth_menu.sort_order = 63
        partner_credit_menu = db.query(MenuConfig).filter_by(menu_key="/partners/credit").first()
        if not partner_credit_menu:
            db.add(MenuConfig(menu_key="/partners/credit", label="渠道伙伴信用", is_visible=False, sort_order=66, parent_key="group-partner"))
        else:
            partner_credit_menu.label = "渠道伙伴信用"
            partner_credit_menu.parent_key = "group-partner"
            partner_credit_menu.sort_order = 66
            partner_credit_menu.is_visible = False
        partner_performance_menu = db.query(MenuConfig).filter_by(menu_key="/partners/performance").first()
        if not partner_performance_menu:
            db.add(MenuConfig(menu_key="/partners/performance", label="渠道绩效", is_visible=True, sort_order=62, parent_key="group-partner"))
        else:
            partner_performance_menu.label = "渠道绩效"
            partner_performance_menu.parent_key = "group-partner"
            partner_performance_menu.sort_order = 62
            partner_performance_menu.is_visible = True
        partner_commission_menu = db.query(MenuConfig).filter_by(menu_key="/partners/commission").first()
        if partner_commission_menu and partner_commission_menu.sort_order != 65:
            partner_commission_menu.sort_order = 65
        db.commit()
        growth_menu = db.query(MenuConfig).filter_by(menu_key="/sales-growth").first()
        if not growth_menu:
            db.add(MenuConfig(menu_key="/sales-growth", label="销售增长", is_visible=False, sort_order=56))
        else:
            growth_menu.is_visible = False
            growth_menu.parent_key = None
            growth_menu.sort_order = 56
        excellence_menu = db.query(MenuConfig).filter_by(menu_key="/business-excellence").first()
        if not excellence_menu:
            db.add(MenuConfig(menu_key="/business-excellence", label="经营驾驶舱", is_visible=True, sort_order=12, parent_key="group-dashboard"))
        else:
            excellence_menu.label = "经营驾驶舱"
            excellence_menu.parent_key = "group-dashboard"
            excellence_menu.sort_order = 12
            excellence_menu.is_visible = True
        db.commit()
    finally:
        db.close()

from app.routers import auth, customers, opportunities, products, channel, contacts, followups, leads, bidding, import_data, dashboard, users, menu_config, stages, commissions, company_utils, export_data, industries, audit, security_business, sales_growth, business_excellence

app.include_router(auth.router, prefix="/api/auth", tags=["Auth"])
app.include_router(customers.router, prefix="/api/customers", tags=["Customers"])
app.include_router(opportunities.router, prefix="/api/opportunities", tags=["Opportunities"])
app.include_router(products.router, prefix="/api/products", tags=["Products"])
app.include_router(channel.router, prefix="/api/channel", tags=["Channel"])
app.include_router(channel.router, prefix="/api/channel-partners", tags=["ChannelPartners"])
app.include_router(contacts.router, prefix="/api/contacts", tags=["Contacts"])
app.include_router(followups.router, prefix="/api/follow-ups", tags=["FollowUps"])
app.include_router(leads.router, prefix="/api/leads", tags=["Leads"])
app.include_router(bidding.router, prefix="/api/bidding", tags=["Bidding"])
app.include_router(import_data.router, prefix="/api/import", tags=["Import"])
app.include_router(dashboard.router, prefix="/api/dashboard", tags=["Dashboard"])
app.include_router(users.router, prefix="/api/users", tags=["Users"])
app.include_router(menu_config.router, prefix="/api/menu-config", tags=["MenuConfig"])
app.include_router(stages.router, prefix="/api/stages", tags=["Stages"])
app.include_router(industries.router, prefix="/api/industries", tags=["Industries"])
app.include_router(commissions.router, prefix="/api/commissions", tags=["Commissions"])
app.include_router(company_utils.router, prefix="/api/utils", tags=["Utils"])
app.include_router(export_data.router, prefix="/api/export", tags=["Export"])
app.include_router(audit.router, prefix="/api/audit-logs", tags=["AuditLogs"])
app.include_router(security_business.router, prefix="/api/security-business", tags=["SecurityBusiness"])
app.include_router(sales_growth.router, prefix="/api/sales-growth", tags=["SalesGrowth"])
app.include_router(business_excellence.router, prefix="/api/business-excellence", tags=["BusinessExcellence"])

# ===================== Nested customer contacts =====================
from app.database import get_db
from app.schemas import ContactCreate, ContactUpdate
from app.routers.utils import require_user
from app.permissions import can_access_customer
from sqlalchemy.orm import Session
from fastapi import Depends, HTTPException

def _check_cust_owner(customer_id: int, db: Session, user):
    c = db.query(Customer).filter_by(id=customer_id).first()
    if not c: raise HTTPException(404, "客户不存在")
    if not can_access_customer(db, user, customer_id):
        raise HTTPException(403, "没有权限访问该客户")
    return c

@app.get("/api/customers/{customer_id}/contacts")
def cust_contacts_list(customer_id: int, db: Session=Depends(get_db), user=Depends(require_user)):
    _check_cust_owner(customer_id, db, user)
    return db.query(Contact).filter(Contact.customer_id == customer_id).all()

@app.post("/api/customers/{customer_id}/contacts", status_code=201)
def cust_contacts_create(customer_id: int, data: ContactCreate, db: Session=Depends(get_db), user=Depends(require_user)):
    _check_cust_owner(customer_id, db, user)
    c = Contact(**{**data.model_dump(), 'customer_id': customer_id})
    db.add(c); db.commit(); db.refresh(c); return c

@app.put("/api/customers/{customer_id}/contacts/{cid}")
def cust_contacts_update(customer_id: int, cid: int, data: ContactUpdate, db: Session=Depends(get_db), user=Depends(require_user)):
    _check_cust_owner(customer_id, db, user)
    c = db.query(Contact).filter_by(id=cid, customer_id=customer_id).first()
    if not c: raise HTTPException(404, "Not found")
    for k,v in data.model_dump(exclude_unset=True).items(): setattr(c,k,v)
    db.commit(); db.refresh(c); return c

@app.delete("/api/customers/{customer_id}/contacts/{cid}", status_code=204)
def cust_contacts_delete(customer_id: int, cid: int, db: Session=Depends(get_db), user=Depends(require_user)):
    _check_cust_owner(customer_id, db, user)
    c = db.query(Contact).filter_by(id=cid, customer_id=customer_id).first()
    if not c: raise HTTPException(404, "Not found")
    db.delete(c); db.commit()
