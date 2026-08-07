from datetime import datetime
from types import SimpleNamespace

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import Contact, Customer, Opportunity, OpportunityType, PresalesRequest, User
from app.permissions import can_access_customer, can_access_opportunity
from app.routers.contacts import delete_contact
from app.routers.customers import delete_customer
from app.routers.opportunities import _check_edit_access, delete_opp


def _session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _assert_forbidden(action):
    try:
        action()
    except HTTPException as exc:
        assert exc.status_code == 403
    else:
        raise AssertionError("Presales must not be allowed to delete a shared record")


def test_presales_can_view_collaboration_scope_but_cannot_delete_records():
    db = _session()
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
    db.add_all([sales, presales])
    db.flush()

    customer = Customer(name="Shared Customer", industry="Enterprise", owner_id=sales.id)
    db.add(customer)
    db.flush()
    contact = Contact(customer_id=customer.id, name="Shared Contact")
    opportunity = Opportunity(
        opp_type=OpportunityType.DIRECT,
        sales_rep_id=sales.id,
        customer_id=customer.id,
        name="Shared Opportunity",
    )
    db.add_all([contact, opportunity])
    db.flush()
    db.add(
        PresalesRequest(
            opportunity_id=opportunity.id,
            request_type="presales_support",
            title="Presales request",
            requester_id=sales.id,
            owner_id=presales.id,
            created_by=sales.id,
            scheduled_date=datetime.now(),
        )
    )
    db.commit()

    user = SimpleNamespace(id=presales.id, role="presales")
    assert can_access_customer(db, user, customer.id)
    assert can_access_opportunity(db, user, opportunity.id)
    assert _check_edit_access(opportunity, db, user) is None

    _assert_forbidden(lambda: delete_customer(customer.id, db=db, user=user))
    _assert_forbidden(lambda: delete_contact(contact.id, db=db, user=user))
    _assert_forbidden(lambda: delete_opp(opportunity.id, db=db, user=user))

    assert db.query(Customer).filter_by(id=customer.id).first() is not None
    assert db.query(Contact).filter_by(id=contact.id).first() is not None
    assert db.query(Opportunity).filter_by(id=opportunity.id).first() is not None
