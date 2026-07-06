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
    manager_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
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
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    creator = relationship("User")
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
    sort_order = Column(Integer, default=0, index=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=now_cst)

class ProductSubCategory(Base):
    __tablename__ = "product_sub_categories"
    id = Column(Integer, primary_key=True, autoincrement=True)
    category = Column(String(128), nullable=False, index=True)
    name = Column(String(128), nullable=False, index=True)
    sort_order = Column(Integer, default=0, index=True)
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

class IndustryConfig(Base):
    __tablename__ = "industry_configs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(64), unique=True, nullable=False, index=True)
    sort_order = Column(Integer, default=0)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=now_cst)

class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    username = Column(String(64), index=True)
    method = Column(String(12), nullable=False)
    path = Column(String(512), nullable=False, index=True)
    status_code = Column(Integer, default=0)
    client_ip = Column(String(64))
    user_agent = Column(String(512))
    action = Column(String(64), index=True)
    created_at = Column(DateTime, default=now_cst, index=True)

class CustomerSecurityProfile(Base):
    __tablename__ = "customer_security_profiles"
    id = Column(Integer, primary_key=True, autoincrement=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), unique=True, nullable=False, index=True)
    org_structure = Column(Text)
    decision_chain = Column(Text)
    technical_owner = Column(String(128))
    purchase_owner = Column(String(128))
    historical_projects = Column(Text)
    security_products = Column(Text)
    competitors = Column(Text)
    mlps_status = Column(String(128))
    crypto_status = Column(String(128))
    xinchuang_status = Column(String(128))
    notes = Column(Text)
    updated_at = Column(DateTime, default=now_cst, onupdate=now_cst)
    created_at = Column(DateTime, default=now_cst)

class ChannelRegistration(Base):
    __tablename__ = "channel_registrations"
    id = Column(Integer, primary_key=True, autoincrement=True)
    opportunity_id = Column(Integer, ForeignKey("opportunities.id"), nullable=True, index=True)
    partner_id = Column(Integer, ForeignKey("channel_partners.id"), nullable=True, index=True)
    final_customer_name = Column(String(256), nullable=False, index=True)
    region = Column(String(64), index=True)
    protection_start = Column(Date, default=date.today)
    protection_end = Column(Date, index=True)
    status = Column(String(32), default="pending", index=True)
    duplicate_customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True)
    conflict_with_id = Column(Integer, nullable=True, index=True)
    conflict_reason = Column(Text)
    arbitration_result = Column(Text)
    arbitrator_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    notes = Column(Text)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    updated_at = Column(DateTime, default=now_cst, onupdate=now_cst)
    created_at = Column(DateTime, default=now_cst)

class PresalesRequest(Base):
    __tablename__ = "presales_requests"
    id = Column(Integer, primary_key=True, autoincrement=True)
    opportunity_id = Column(Integer, ForeignKey("opportunities.id"), nullable=False, index=True)
    request_type = Column(String(64), nullable=False, index=True)
    title = Column(String(256), nullable=False)
    status = Column(String(32), default="pending", index=True)
    requester_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    requested_date = Column(Date, default=date.today)
    scheduled_date = Column(DateTime, nullable=True, index=True)
    resource_name = Column(String(128))
    details = Column(Text)
    result = Column(Text)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    updated_at = Column(DateTime, default=now_cst, onupdate=now_cst)
    created_at = Column(DateTime, default=now_cst)

class BidRadarSubscription(Base):
    __tablename__ = "bid_radar_subscriptions"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(128), nullable=False)
    keywords = Column(Text, nullable=False)
    regions = Column(String(256))
    product_lines = Column(String(256))
    min_budget = Column(Float, default=0.0)
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    created_at = Column(DateTime, default=now_cst)

class BidRadarItem(Base):
    __tablename__ = "bid_radar_items"
    id = Column(Integer, primary_key=True, autoincrement=True)
    subscription_id = Column(Integer, ForeignKey("bid_radar_subscriptions.id"), nullable=True, index=True)
    title = Column(String(256), nullable=False, index=True)
    buyer = Column(String(256), index=True)
    source = Column(String(128))
    url = Column(String(512))
    region = Column(String(64), index=True)
    budget = Column(Float, default=0.0)
    deadline = Column(Date, nullable=True, index=True)
    competitor_judgment = Column(String(256))
    matched_product_line = Column(String(256))
    status = Column(String(32), default="new", index=True)
    lead_id = Column(Integer, ForeignKey("leads.id"), nullable=True)
    notes = Column(Text)
    created_at = Column(DateTime, default=now_cst)

class BidRadarFollowTask(Base):
    __tablename__ = "bid_radar_follow_tasks"
    id = Column(Integer, primary_key=True, autoincrement=True)
    radar_item_id = Column(Integer, ForeignKey("bid_radar_items.id"), nullable=False, index=True)
    title = Column(String(256), nullable=False)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    due_date = Column(Date, nullable=True, index=True)
    status = Column(String(32), default="open", index=True)
    notes = Column(Text)
    created_at = Column(DateTime, default=now_cst)

class SalesTarget(Base):
    __tablename__ = "sales_targets"
    id = Column(Integer, primary_key=True, autoincrement=True)
    sales_rep_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    period_type = Column(String(16), default="quarter", index=True)
    period_label = Column(String(32), nullable=False, index=True)
    sales_target = Column(Float, default=0.0)
    collection_target = Column(Float, default=0.0)
    new_customer_target = Column(Integer, default=0)
    channel_contribution_target = Column(Float, default=0.0)
    lead_conversion_target = Column(Float, default=0.0)
    win_rate_target = Column(Float, default=0.0)
    notes = Column(Text)
    created_at = Column(DateTime, default=now_cst)
    updated_at = Column(DateTime, default=now_cst, onupdate=now_cst)

class CustomerOperationProfile(Base):
    __tablename__ = "customer_operation_profiles"
    id = Column(Integer, primary_key=True, autoincrement=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), unique=True, nullable=False, index=True)
    segment = Column(String(32), default="normal", index=True)
    owner_strategy = Column(Text)
    next_action = Column(Text)
    health_status = Column(String(32), default="normal", index=True)
    updated_at = Column(DateTime, default=now_cst, onupdate=now_cst)
    created_at = Column(DateTime, default=now_cst)

class OpportunityReview(Base):
    __tablename__ = "opportunity_reviews"
    id = Column(Integer, primary_key=True, autoincrement=True)
    opportunity_id = Column(Integer, ForeignKey("opportunities.id"), nullable=False, index=True)
    result = Column(String(16), nullable=False, index=True)
    reason = Column(String(256))
    competitor = Column(String(256))
    price_gap = Column(Text)
    technical_gap = Column(Text)
    relationship_gap = Column(Text)
    product_feedback = Column(Text)
    market_feedback = Column(Text)
    reviewer_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    review_date = Column(Date, default=date.today, index=True)
    created_at = Column(DateTime, default=now_cst)
    updated_at = Column(DateTime, default=now_cst, onupdate=now_cst)

class PartnerGrowthRecord(Base):
    __tablename__ = "partner_growth_records"
    id = Column(Integer, primary_key=True, autoincrement=True)
    partner_id = Column(Integer, ForeignKey("channel_partners.id"), nullable=False, index=True)
    record_type = Column(String(32), nullable=False, index=True)
    title = Column(String(256), nullable=False)
    person_name = Column(String(128))
    record_date = Column(Date, default=date.today, index=True)
    expiry_date = Column(Date, nullable=True)
    score = Column(Float, default=0.0)
    status = Column(String(32), default="valid", index=True)
    notes = Column(Text)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=now_cst)

class AuditChange(Base):
    __tablename__ = "audit_changes"
    id = Column(Integer, primary_key=True, autoincrement=True)
    audit_log_id = Column(Integer, ForeignKey("audit_logs.id"), nullable=True, index=True)
    entity_type = Column(String(64), index=True)
    entity_id = Column(Integer, nullable=True, index=True)
    before_snapshot = Column(Text)
    after_snapshot = Column(Text)
    created_at = Column(DateTime, default=now_cst)

class CustomerIdentity(Base):
    __tablename__ = "customer_identities"
    id = Column(Integer, primary_key=True, autoincrement=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), unique=True, nullable=False, index=True)
    unified_social_credit_code = Column(String(64), index=True)
    short_name = Column(String(128), index=True)
    aliases = Column(Text)
    parent_customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True, index=True)
    normalized_name = Column(String(256), index=True)
    source = Column(String(64), default="manual")
    updated_at = Column(DateTime, default=now_cst, onupdate=now_cst)
    created_at = Column(DateTime, default=now_cst)

class CustomerMergeLog(Base):
    __tablename__ = "customer_merge_logs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    source_customer_id = Column(Integer, nullable=False, index=True)
    source_customer_name = Column(String(256))
    target_customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)
    target_customer_name = Column(String(256))
    reason = Column(Text)
    merged_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=now_cst)

class ChannelRegistrationRule(Base):
    __tablename__ = "channel_registration_rules"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(128), nullable=False, default="默认报备规则")
    default_protection_days = Column(Integer, default=90)
    max_extensions = Column(Integer, default=1)
    extension_days = Column(Integer, default=30)
    require_evidence = Column(Boolean, default=True)
    inactive_days_to_warn = Column(Integer, default=14)
    inactive_days_to_expire = Column(Integer, default=30)
    is_active = Column(Boolean, default=True, index=True)
    notes = Column(Text)
    updated_at = Column(DateTime, default=now_cst, onupdate=now_cst)
    created_at = Column(DateTime, default=now_cst)

class ChannelRegistrationGovernance(Base):
    __tablename__ = "channel_registration_governance"
    id = Column(Integer, primary_key=True, autoincrement=True)
    registration_id = Column(Integer, ForeignKey("channel_registrations.id"), unique=True, nullable=False, index=True)
    evidence_summary = Column(Text)
    extension_count = Column(Integer, default=0)
    last_activity_date = Column(Date, nullable=True, index=True)
    invalid_reason = Column(Text)
    owner_comment = Column(Text)
    updated_at = Column(DateTime, default=now_cst, onupdate=now_cst)
    created_at = Column(DateTime, default=now_cst)

class PresalesSlaRule(Base):
    __tablename__ = "presales_sla_rules"
    id = Column(Integer, primary_key=True, autoincrement=True)
    request_type = Column(String(64), unique=True, nullable=False, index=True)
    label = Column(String(128), nullable=False)
    response_hours = Column(Integer, default=24)
    delivery_hours = Column(Integer, default=72)
    is_active = Column(Boolean, default=True, index=True)
    notes = Column(Text)
    created_at = Column(DateTime, default=now_cst)

class PresalesSlaTracking(Base):
    __tablename__ = "presales_sla_tracking"
    id = Column(Integer, primary_key=True, autoincrement=True)
    request_id = Column(Integer, ForeignKey("presales_requests.id"), unique=True, nullable=False, index=True)
    response_due_at = Column(DateTime, nullable=True, index=True)
    delivery_due_at = Column(DateTime, nullable=True, index=True)
    responded_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    sla_status = Column(String(32), default="pending", index=True)
    notes = Column(Text)
    updated_at = Column(DateTime, default=now_cst, onupdate=now_cst)
    created_at = Column(DateTime, default=now_cst)

class BidConversion(Base):
    __tablename__ = "bid_conversions"
    id = Column(Integer, primary_key=True, autoincrement=True)
    bid_item_id = Column(Integer, ForeignKey("bid_radar_items.id"), nullable=False, index=True)
    lead_id = Column(Integer, ForeignKey("leads.id"), nullable=True)
    opportunity_id = Column(Integer, ForeignKey("opportunities.id"), nullable=True)
    converted_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    conversion_type = Column(String(32), default="lead", index=True)
    created_at = Column(DateTime, default=now_cst)

class CustomerDecisionNode(Base):
    __tablename__ = "customer_decision_nodes"
    id = Column(Integer, primary_key=True, autoincrement=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)
    name = Column(String(128), nullable=False)
    role = Column(String(64))
    department = Column(String(128))
    influence = Column(Integer, default=3)
    attitude = Column(String(32), default="neutral", index=True)
    relationship_strength = Column(Integer, default=3)
    contact_id = Column(Integer, ForeignKey("contacts.id"), nullable=True)
    notes = Column(Text)
    created_at = Column(DateTime, default=now_cst)

class CustomerDecisionEdge(Base):
    __tablename__ = "customer_decision_edges"
    id = Column(Integer, primary_key=True, autoincrement=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)
    source_node_id = Column(Integer, ForeignKey("customer_decision_nodes.id"), nullable=False)
    target_node_id = Column(Integer, ForeignKey("customer_decision_nodes.id"), nullable=False)
    relation = Column(String(64), default="influence")
    strength = Column(Integer, default=3)
    notes = Column(Text)
    created_at = Column(DateTime, default=now_cst)

class CustomerCompetitorInstall(Base):
    __tablename__ = "customer_competitor_installs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)
    competitor_name = Column(String(128), nullable=False, index=True)
    product_line = Column(String(128), index=True)
    product_name = Column(String(256))
    contract_end_date = Column(Date, nullable=True, index=True)
    satisfaction = Column(Integer, default=3)
    replacement_chance = Column(String(32), default="medium", index=True)
    pain_points = Column(Text)
    notes = Column(Text)
    created_at = Column(DateTime, default=now_cst)

class IndustryProductRecommendation(Base):
    __tablename__ = "industry_product_recommendations"
    id = Column(Integer, primary_key=True, autoincrement=True)
    industry = Column(String(64), nullable=False, index=True)
    product_line = Column(String(128), nullable=False, index=True)
    product_sub_category = Column(String(128), nullable=True, index=True)
    priority = Column(Integer, default=3, index=True)
    scenario = Column(Text)
    pitch = Column(Text)
    is_active = Column(Boolean, default=True, index=True)
    created_at = Column(DateTime, default=now_cst)

class PocRecord(Base):
    __tablename__ = "poc_records"
    id = Column(Integer, primary_key=True, autoincrement=True)
    opportunity_id = Column(Integer, ForeignKey("opportunities.id"), nullable=False, index=True)
    presales_request_id = Column(Integer, ForeignKey("presales_requests.id"), nullable=True, index=True)
    test_goal = Column(Text)
    environment = Column(Text)
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)
    result = Column(String(32), default="pending", index=True)
    customer_feedback = Column(Text)
    next_step = Column(Text)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    updated_at = Column(DateTime, default=now_cst, onupdate=now_cst)
    created_at = Column(DateTime, default=now_cst)

class ForecastSnapshot(Base):
    __tablename__ = "forecast_snapshots"
    id = Column(Integer, primary_key=True, autoincrement=True)
    period_label = Column(String(32), nullable=False, index=True)
    group_by = Column(String(32), default="sales", index=True)
    group_key = Column(String(128), default="全部", index=True)
    commit_amount = Column(Float, default=0.0)
    best_case_amount = Column(Float, default=0.0)
    pipeline_amount = Column(Float, default=0.0)
    weighted_amount = Column(Float, default=0.0)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    snapshot_date = Column(Date, default=date.today, index=True)
    created_at = Column(DateTime, default=now_cst)

class PresalesAsset(Base):
    __tablename__ = "presales_assets"
    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(256), nullable=False, index=True)
    asset_type = Column(String(64), default="solution", index=True)
    product_line = Column(String(128), index=True)
    product_sub_category = Column(String(128), index=True)
    industry = Column(String(64), index=True)
    url = Column(String(512))
    file_name = Column(String(256))
    file_url = Column(String(512))
    file_size = Column(Integer, default=0)
    summary = Column(Text)
    tags = Column(String(256))
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=now_cst)

class BidScoreCriterion(Base):
    __tablename__ = "bid_score_criteria"
    id = Column(Integer, primary_key=True, autoincrement=True)
    bid_item_id = Column(Integer, ForeignKey("bid_radar_items.id"), nullable=False, index=True)
    criterion = Column(String(256), nullable=False)
    weight = Column(Float, default=0.0)
    our_score = Column(Float, default=0.0)
    risk_level = Column(String(32), default="medium", index=True)
    suggestion = Column(Text)
    created_at = Column(DateTime, default=now_cst)
