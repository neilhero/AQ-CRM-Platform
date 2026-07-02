from pydantic import BaseModel
from typing import Optional, List
from datetime import date, datetime

class CustomerCreate(BaseModel):
    name: str; industry: Optional[str]=None; address: Optional[str]=None
    website: Optional[str]=None; level: Optional[str]="C"; description: Optional[str]=None

class CustomerUpdate(BaseModel):
    name: Optional[str]=None; industry: Optional[str]=None; address: Optional[str]=None
    website: Optional[str]=None; level: Optional[str]=None; description: Optional[str]=None

class CustomerOut(BaseModel):
    id: int; name: str; industry: Optional[str]=None; address: Optional[str]=None
    website: Optional[str]=None; level: Optional[str]=None; description: Optional[str]=None
    created_at: Optional[datetime]=None; updated_at: Optional[datetime]=None
    class Config: from_attributes=True

class OpportunityCreate(BaseModel):
    name: str; opp_type: str="direct"; sales_rep_id: int; customer_id: Optional[int]=None
    channel_partner_id: Optional[int]=None; end_customer_name: Optional[str]=None
    industry: Optional[str]=None; amount: Optional[float]=0.0; stage: Optional[str]="1"
    probability: Optional[str]="LOW"; key_person: Optional[str]=None; brief: Optional[str]=None
    expected_close_date: Optional[date]=None; required_product: Optional[str]=None
    next_follow_up_date: Optional[date]=None

class OpportunityUpdate(BaseModel):
    name: Optional[str]=None; stage: Optional[str]=None; probability: Optional[str]=None
    amount: Optional[float]=None; key_person: Optional[str]=None; brief: Optional[str]=None
    expected_close_date: Optional[date]=None; next_follow_up_date: Optional[date]=None; required_product: Optional[str]=None
    is_closed: Optional[bool]=None; industry: Optional[str]=None

class OpportunityOut(BaseModel):
    id: int; name: str; opp_type: Optional[str]=None; sales_rep_id: Optional[int]=None
    customer_id: Optional[int]=None; channel_partner_id: Optional[int]=None
    end_customer_name: Optional[str]=None; industry: Optional[str]=None
    amount: Optional[float]=0.0; stage: Optional[str]=None; probability: Optional[str]=None
    key_person: Optional[str]=None; brief: Optional[str]=None; pain_points: Optional[str]=None
    required_product: Optional[str]=None; handler_person: Optional[str]=None
    created_at: Optional[date]=None; updated_at: Optional[date]=None
    expected_close_date: Optional[date]=None; next_follow_up_date: Optional[date]=None
    is_closed: Optional[bool]=False; customer_name: Optional[str]=None
    sales_rep_name: Optional[str]=None; channel_partner_name: Optional[str]=None
    class Config: from_attributes=True

class ProductCreate(BaseModel):
    name: str; category: Optional[str]=None; sub_category: Optional[str]=None
    description: Optional[str]=None; unit_price: Optional[float]=0.0

class ProductUpdate(BaseModel):
    name: Optional[str]=None; category: Optional[str]=None; sub_category: Optional[str]=None
    description: Optional[str]=None; unit_price: Optional[float]=None; is_active: Optional[bool]=None

class ProductOut(BaseModel):
    id: int; name: str; category: Optional[str]=None; sub_category: Optional[str]=None
    description: Optional[str]=None; unit_price: Optional[float]=0.0; is_active: Optional[bool]=True
    created_at: Optional[datetime]=None
    class Config: from_attributes=True

class ChannelPartnerCreate(BaseModel):
    name: str; contact_person: Optional[str]=None; contact_phone: Optional[str]=None
    description: Optional[str]=None; level: Optional[str]="Register"; region: Optional[str]=None

class ChannelPartnerUpdate(BaseModel):
    name: Optional[str]=None; contact_person: Optional[str]=None; contact_phone: Optional[str]=None
    description: Optional[str]=None; level: Optional[str]=None; region: Optional[str]=None; status: Optional[str]=None

class ChannelPartnerOut(BaseModel):
    id: int; name: str; contact_person: Optional[str]=None; contact_phone: Optional[str]=None
    description: Optional[str]=None; level: Optional[str]=None; region: Optional[str]=None
    status: Optional[str]=None; created_at: Optional[datetime]=None
    class Config: from_attributes=True

class ContactCreate(BaseModel):
    name: str; customer_id: Optional[int]=None; partner_id: Optional[int]=None
    position: Optional[str]=None; role_type: Optional[str]=None; phone: Optional[str]=None
    email: Optional[str]=None; wechat: Optional[str]=None; notes: Optional[str]=None

class ContactUpdate(BaseModel):
    name: Optional[str]=None; position: Optional[str]=None; role_type: Optional[str]=None
    phone: Optional[str]=None; email: Optional[str]=None; wechat: Optional[str]=None; notes: Optional[str]=None

class ContactOut(BaseModel):
    id: int; name: str; customer_id: Optional[int]=None; partner_id: Optional[int]=None
    position: Optional[str]=None; role_type: Optional[str]=None; phone: Optional[str]=None
    email: Optional[str]=None; wechat: Optional[str]=None; notes: Optional[str]=None
    created_at: Optional[datetime]=None
    class Config: from_attributes=True

class FollowUpCreate(BaseModel):
    opportunity_id: int; content: str; contact_person: Optional[str]=None

class FollowUpOut(BaseModel):
    id: int; opportunity_id: int; creator_id: Optional[int]=None; content: str
    contact_person: Optional[str]=None; created_at: Optional[datetime]=None
    creator_name: Optional[str]=None
    class Config: from_attributes=True

class LeadCreate(BaseModel):
    name: str; company: Optional[str]=None; contact_name: Optional[str]=None
    contact_phone: Optional[str]=None; source: Optional[str]=None; quality: Optional[str]=None
    industry: Optional[str]=None; notes: Optional[str]=None; assigned_to: Optional[int]=None

class LeadUpdate(BaseModel):
    name: Optional[str]=None; company: Optional[str]=None; contact_name: Optional[str]=None
    contact_phone: Optional[str]=None; source: Optional[str]=None; quality: Optional[str]=None
    status: Optional[str]=None; industry: Optional[str]=None; notes: Optional[str]=None
    assigned_to: Optional[int]=None

class LeadOut(BaseModel):
    id: int; name: str; company: Optional[str]=None; contact_name: Optional[str]=None
    contact_phone: Optional[str]=None; source: Optional[str]=None; quality: Optional[str]=None
    status: Optional[str]=None; industry: Optional[str]=None; notes: Optional[str]=None
    assigned_to: Optional[int]=None; customer_id: Optional[int]=None; opportunity_id: Optional[int]=None
    created_at: Optional[datetime]=None; assigned_user_name: Optional[str]=None
    class Config: from_attributes=True
