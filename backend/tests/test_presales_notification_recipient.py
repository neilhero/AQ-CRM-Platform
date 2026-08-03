from datetime import datetime
from types import SimpleNamespace

from fastapi import BackgroundTasks
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import Opportunity, OpportunityType, User
from app.routers.security_business import PresalesRequestIn, create_presales_request


def _session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_presales_confirmation_uses_selected_requester_dingtalk_userid():
    db = _session()
    creator = User(
        username="admin-creator",
        password_hash="unused",
        real_name="Admin Creator",
        role="admin",
        is_active=True,
    )
    requester = User(
        username="sales-requester",
        password_hash="unused",
        real_name="Sales Requester",
        role="manager",
        dingtalk_userid="sales-dingtalk-user",
        is_active=True,
    )
    presales = User(
        username="presales-owner",
        password_hash="unused",
        real_name="Presales Owner",
        role="presales",
        dingtalk_userid="presales-dingtalk-user",
        is_active=True,
    )
    db.add_all([creator, requester, presales])
    db.flush()
    opportunity = Opportunity(
        opp_type=OpportunityType.DIRECT,
        sales_rep_id=requester.id,
        name="Security Project",
    )
    db.add(opportunity)
    db.commit()

    tasks = BackgroundTasks()
    create_presales_request(
        PresalesRequestIn(
            opportunity_id=opportunity.id,
            request_type="presales_support",
            requester_id=requester.id,
            owner_id=presales.id,
            scheduled_date=datetime(2026, 8, 6, 10, 0),
            details="Prepare a presales proposal.",
        ),
        background_tasks=tasks,
        db=db,
        user=SimpleNamespace(
            id=creator.id,
            role="admin",
            dingtalk_userid=None,
        ),
    )

    assert len(tasks.tasks) == 1
    assert tasks.tasks[0].args[0] == "presales-dingtalk-user"
    assert tasks.tasks[0].args[-1] == "sales-dingtalk-user"
