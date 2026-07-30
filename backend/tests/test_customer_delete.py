from types import SimpleNamespace

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import (
    Customer,
    CustomerOperationProfile,
    CustomerSecurityProfile,
    Opportunity,
    OpportunityType,
    User,
)
from app.routers.customers import delete_customer


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


def test_delete_customer_removes_profiles_and_preserves_opportunity():
    db = _session()
    owner = User(
        username="owner",
        password_hash="unused",
        real_name="销售",
        role="sales",
        is_active=True,
    )
    customer = Customer(name="测试客户有限公司", industry="企业", owner=owner)
    db.add_all([owner, customer])
    db.flush()
    db.add_all(
        [
            CustomerSecurityProfile(customer_id=customer.id),
            CustomerOperationProfile(customer_id=customer.id),
            Opportunity(
                opp_type=OpportunityType.DIRECT,
                sales_rep_id=owner.id,
                customer_id=customer.id,
                name="测试商机",
            ),
        ]
    )
    db.commit()
    customer_id = customer.id

    delete_customer(
        customer_id,
        db=db,
        user=SimpleNamespace(id=owner.id, role="admin"),
    )

    assert db.query(Customer).filter(Customer.id == customer_id).first() is None
    assert db.query(CustomerSecurityProfile).count() == 0
    assert db.query(CustomerOperationProfile).count() == 0
    opportunity = db.query(Opportunity).one()
    assert opportunity.customer_id is None
    assert opportunity.end_customer_name == "测试客户有限公司"
