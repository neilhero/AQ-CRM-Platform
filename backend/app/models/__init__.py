from sqlalchemy import Column, Integer, String, Float, Text, DateTime, ForeignKey, Enum, Date, Boolean
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime, date, timezone, timedelta
import enum

CST = timezone(timedelta(hours=8))

def now_cst():
    return datetime.now(CST)

from app.database import Base

class OpportunityStage(str, enum.Enum):
    STAGE_1 = "1"
    STAGE_2 = "2"
    STAGE_3 = "3"
    STAGE_4 = "4"
    STAGE_5 = "5"

class ProbabilityLevel(str, enum.Enum):
    HIGH = "HIGH"
    MID_HIGH = "MID_HIGH"
    MID = "MID"
    LOW = "LOW"

class UpdateStatus(str, enum.Enum):
    NEW_THIS_WEEK = "NEW"
    UPDATED_THIS_WEEK = "UPDATED"
    UNCHANGED = "UNCHANGED"

class OpportunityType(str, enum.Enum):
    DIRECT = "direct"
    CHANNEL = "channel"

class CustomerLevel(str, enum.Enum):
    VIP = "VIP"
    A = "A"
    B = "B"
    C = "C"

class LeadSource(str, enum.Enum):
    WEBSITE = "website"
    EXHIBITION = "exhibition"
    PARTNER = "partner"
    PHONE = "phone"
    BIDDING = "bidding"
    OTHER = "other"

class LeadQuality(str, enum.Enum):
    COLD = "cold"
    WARM = "warm"
    HOT = "hot"

class LeadStatus(str, enum.Enum):
    NEW = "new"
    CONTACTED = "contacted"
    CONFIRMED = "confirmed"
    CONVERTED = "converted"
    CLOSED = "closed"

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(64), unique=True, nullable=False, index=True)
    password_hash = Column(String(256), nullable=False)
    real_name = Column(String(64), nullable=False)
    role = Column(String(32), default="sales")
    email = Column(String(128))
    phone = Column(String(32))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=now_cst)
    opportunities = relationship("Opportunity", back_populates="sales_rep")
    follow_ups = relationship("FollowUp", back_populates="creator")

class Customer(Base):
    __tablename__ = "customers"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(256), nullable=False, unique=True, index=True)
    industry = Column(String(64), index=True)
    address = Column(String(512))
    website = Column(String(256))
    level = Column(String(16), default="C", index=True)
    description = Column(Text)
    created_at = Column(DateTime, default=now_cst)
    updated_at = Column(DateTime, default=now_cst, onupdate=now_cst)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    owner = relationship("User")
    contacts = relationship("Contact", back_populates="customer")
    opportunities = relationship("Opportunity", back_populates="customer")

class ChannelPartner(Base):
    __tablename__ = "channel_partners"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(256), nullable=False, index=True)
    contact_person = Column(String(128))
    contact_phone = Column(String(32))
    description = Column(Text)
    level = Column(String(16), default="Register", index=True)
    region = Column(String(32), index=True)
    status = Column(String(16), default="active", index=True)
    created_at = Column(DateTime, default=now_cst)
    opportunities = relationship("Opportunity", back_populates="channel_partner")
    contacts = relationship("Contact", back_populates="channel_partner")

class Contact(Base):
    __tablename__ = "contacts"
    id = Column(Integer, primary_key=True, autoincrement=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True)
    partner_id = Column(Integer, ForeignKey("channel_partners.id"), nullable=True)
    name = Column(String(64), nullable=False)
    position = Column(String(128))
    role_type = Column(String(32))
    phone = Column(String(32))
    email = Column(String(128))
    wechat = Column(String(64))
    notes = Column(Text)
    created_at = Column(DateTime, default=now_cst)
    customer = relationship("Customer", back_populates="contacts")
    channel_partner = relationship("ChannelPartner", back_populates="contacts")

class Product(Base):
    __tablename__ = "products"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(256), nullable=False, unique=True)
    category = Column(String(128), index=True)
    sub_category = Column(String(128), index=True)
    description = Column(Text)
    unit_price = Column(Float, default=0.0)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=now_cst)

class Opportunity(Base):
    __tablename__ = "opportunities"
    id = Column(Integer, primary_key=True, autoincrement=True)
    opp_type = Column(Enum(OpportunityType), nullable=False, default=OpportunityType.DIRECT)
    sales_rep_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True)
    end_customer_name = Column(String(256))
    channel_partner_id = Column(Integer, ForeignKey("channel_partners.id"), nullable=True)
    name = Column(String(256), nullable=False, index=True)
    industry = Column(String(64))
    pain_points = Column(Text)
    required_product = Column(String(256))
    brief = Column(Text)
    amount = Column(Float, default=0.0)
    stage = Column(Enum(OpportunityStage), default=OpportunityStage.STAGE_1)
    probability = Column(Enum(ProbabilityLevel), default=ProbabilityLevel.LOW)
    key_person = Column(String(256))
    handler_person = Column(String(256))
    created_at = Column(Date, default=date.today)
    updated_at = Column(Date, default=date.today, onupdate=date.today)
    expected_close_date = Column(Date)
    next_follow_up_date = Column(Date)
    update_status = Column(Enum(UpdateStatus), default=UpdateStatus.NEW_THIS_WEEK)
    is_closed = Column(Boolean, default=False)
    closed_reason = Column(String(256))
    sales_rep = relationship("User", back_populates="opportunities")
    customer = relationship("Customer", back_populates="opportunities")
    channel_partner = relationship("ChannelPartner", back_populates="opportunities")
    follow_ups = relationship("FollowUp", back_populates="opportunity", order_by="FollowUp.created_at.desc()")

class FollowUp(Base):
    __tablename__ = "follow_ups"
    id = Column(Integer, primary_key=True, autoincrement=True)
    opportunity_id = Column(Integer, ForeignKey("opportunities.id"), nullable=False)
    creator_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    content = Column(Text, nullable=False)
    contact_person = Column(String(128))
    created_at = Column(DateTime, default=now_cst)
    opportunity = relationship("Opportunity", back_populates="follow_ups")
    creator = relationship("User", back_populates="follow_ups")

class CommissionRule(Base):
    __tablename__ = "commission_rules"
    id = Column(Integer, primary_key=True, autoincrement=True)
    partner_id = Column(Integer, ForeignKey("channel_partners.id"), nullable=False)
    rate_percent = Column(Float, nullable=False, default=0.0)
    settlement_cycle = Column(String(16), default="Quarterly")
    effective_from = Column(Date, default=date.today)
    notes = Column(Text)
    created_at = Column(DateTime, default=now_cst)

class Lead(Base):
    __tablename__ = "leads"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(256), nullable=False, index=True)
    company = Column(String(256))
    contact_name = Column(String(64))
    contact_phone = Column(String(32))
    source = Column(Enum(LeadSource), default=LeadSource.OTHER)
    quality = Column(Enum(LeadQuality), default=LeadQuality.COLD)
    status = Column(Enum(LeadStatus), default=LeadStatus.NEW)
    industry = Column(String(64))
    notes = Column(Text)
    assigned_to = Column(Integer, ForeignKey("users.id"), nullable=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True)
    opportunity_id = Column(Integer, ForeignKey("opportunities.id"), nullable=True)
    created_at = Column(DateTime, default=now_cst)
    updated_at = Column(DateTime, default=now_cst, onupdate=now_cst)

class MenuConfig(Base):
    __tablename__ = "menu_config"
    menu_key = Column(String(64), primary_key=True)
    label = Column(String(64), nullable=False)
    is_visible = Column(Boolean, default=True, nullable=False)
    sort_order = Column(Integer, default=0)
    parent_key = Column(String(64), nullable=True)

class StageConfig(Base):
    __tablename__ = "stage_configs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    stage_key = Column(String(10), unique=True, nullable=False, index=True)
    label = Column(String(64), nullable=False)
    color = Column(String(20), default="#999")
    pct = Column(String(10), default="20%")
    sort_order = Column(Integer, default=0)
