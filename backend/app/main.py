from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.database import engine, Base, SessionLocal
from app.models import User, Customer, ChannelPartner, Contact, Product, Opportunity, FollowUp, CommissionRule, Lead
from datetime import date, datetime, timezone, timedelta
import hashlib, os

CST = timezone(timedelta(hours=8))

app = FastAPI(title="AnQuan CRM v3.2")

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

Base.metadata.create_all(bind=engine)

@app.get("/")
def root():
    return {"message": "AnQuan CRM v3.2 API", "status": "running"}

@app.on_event("startup")
def seed():
    db = SessionLocal()
    try:
        if db.query(User).count() == 0:
            db.add(User(username="admin", password_hash=hashlib.sha256("admin123".encode()).hexdigest(), real_name="系统管理员", role="admin"))
            db.add(User(username="channel001", password_hash=hashlib.sha256("channel123".encode()).hexdigest(), real_name="张三", role="manager"))
            db.add(User(username="sales001", password_hash=hashlib.sha256("sales123".encode()).hexdigest(), real_name="李四", role="sales"))
            db.commit()
        if db.query(Customer).count() == 0:
            custs = [
                Customer(name="浙江省政府云", industry="政数", level="VIP"),
                Customer(name="上海AI研究院", industry="科研", level="A"),
                Customer(name="北京智慧城市中心", industry="政数", level="A"),
                Customer(name="广州数据局", industry="政数", level="B"),
                Customer(name="深圳科技大学", industry="教育", level="B"),
                Customer(name="江苏移动", industry="运营商", level="A"),
                Customer(name="工商银行数据中心", industry="金融", level="VIP"),
                Customer(name="杭州公安", industry="公安", level="A"),
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
    finally:
        db.close()

from app.routers import auth, customers, opportunities, products, channel, contacts, followups, leads, bidding, import_data, dashboard, users

app.include_router(auth.router, prefix="/api/auth", tags=["Auth"])
app.include_router(customers.router, prefix="/api/customers", tags=["Customers"])
app.include_router(opportunities.router, prefix="/api/opportunities", tags=["Opportunities"])
app.include_router(products.router, prefix="/api/products", tags=["Products"])
app.include_router(channel.router, prefix="/api/channel", tags=["Channel"])
app.include_router(contacts.router, prefix="/api/contacts", tags=["Contacts"])
app.include_router(followups.router, prefix="/api/follow-ups", tags=["FollowUps"])
app.include_router(leads.router, prefix="/api/leads", tags=["Leads"])
app.include_router(bidding.router, prefix="/api/bidding", tags=["Bidding"])
app.include_router(import_data.router, prefix="/api/import", tags=["Import"])
app.include_router(dashboard.router, prefix="/api/dashboard", tags=["Dashboard"])
app.include_router(users.router, prefix="/api/users", tags=["Users"])
