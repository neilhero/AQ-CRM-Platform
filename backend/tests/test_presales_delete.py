from types import SimpleNamespace

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import Opportunity, OpportunityType, PocRecord, PresalesRequest, User
from app.routers.security_business import delete_presales_request


def _session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_admin_delete_presales_request_detaches_poc_record():
    db = _session()
    owner = User(
        username="sales-owner",
        password_hash="unused",
        real_name="Sales Owner",
        role="sales",
        is_active=True,
    )
    db.add(owner)
    db.flush()
    opportunity = Opportunity(
        opp_type=OpportunityType.DIRECT,
        sales_rep_id=owner.id,
        name="Security Project",
    )
    db.add(opportunity)
    db.flush()
    request = PresalesRequest(
        opportunity_id=opportunity.id,
        request_type="presales_support",
        title="Presales Support",
        created_by=owner.id,
    )
    db.add(request)
    db.flush()
    poc = PocRecord(
        opportunity_id=opportunity.id,
        presales_request_id=request.id,
    )
    db.add(poc)
    db.commit()
    request_id = request.id

    delete_presales_request(
        request_id,
        db=db,
        admin=SimpleNamespace(id=1, role="admin"),
    )

    assert db.query(PresalesRequest).filter_by(id=request_id).first() is None
    assert db.query(PocRecord).one().presales_request_id is None
