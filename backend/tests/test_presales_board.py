from datetime import datetime
from types import SimpleNamespace

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import Opportunity, OpportunityType, PresalesRequest, User
from app.routers.dashboard import presales_board


def _session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _seed(db):
    sales = User(
        username="sales",
        password_hash="unused",
        real_name="Sales",
        role="sales",
        is_active=True,
    )
    presales = User(
        username="presales",
        password_hash="unused",
        real_name="Presales",
        role="presales",
        is_active=True,
    )
    other_presales = User(
        username="other-presales",
        password_hash="unused",
        real_name="Other Presales",
        role="presales",
        is_active=True,
    )
    db.add_all([sales, presales, other_presales])
    db.flush()
    opportunity = Opportunity(
        opp_type=OpportunityType.DIRECT,
        sales_rep_id=sales.id,
        name="Security Project",
    )
    db.add(opportunity)
    db.flush()
    now = datetime.now()
    db.add_all(
        [
            PresalesRequest(
                opportunity_id=opportunity.id,
                request_type="presales_support",
                title="Completed",
                status="done",
                requester_id=sales.id,
                owner_id=presales.id,
                scheduled_date=now,
                created_by=sales.id,
            ),
            PresalesRequest(
                opportunity_id=opportunity.id,
                request_type="poc",
                title="Active",
                status="in_progress",
                requester_id=sales.id,
                owner_id=presales.id,
                scheduled_date=now,
                created_by=sales.id,
            ),
            PresalesRequest(
                opportunity_id=opportunity.id,
                request_type="solution_review",
                title="Other Owner",
                status="pending",
                requester_id=sales.id,
                owner_id=other_presales.id,
                scheduled_date=now,
                created_by=sales.id,
            ),
        ]
    )
    db.commit()
    return presales


def test_global_and_personal_presales_board_scopes():
    db = _session()
    presales = _seed(db)

    global_board = presales_board(
        period="month",
        scope="all",
        db=db,
        user=SimpleNamespace(id=99, role="sales"),
    )
    assert global_board["summary"] == {
        "total": 3,
        "completed": 1,
        "in_progress": 1,
        "pending": 1,
    }

    personal_board = presales_board(
        period="month",
        scope="mine",
        db=db,
        user=SimpleNamespace(id=presales.id, role="presales"),
    )
    assert personal_board["summary"]["total"] == 2
    assert personal_board["summary"]["completed"] == 1
    assert personal_board["summary"]["in_progress"] == 1
    assert all(item["owner_name"] == "Presales" for item in personal_board["items"])


def test_personal_presales_board_rejects_non_presales_role():
    db = _session()
    try:
        presales_board(
            period="week",
            scope="mine",
            db=db,
            user=SimpleNamespace(id=1, role="sales"),
        )
    except HTTPException as exc:
        assert exc.status_code == 403
    else:
        raise AssertionError("Non-presales role should not access the personal presales board")
