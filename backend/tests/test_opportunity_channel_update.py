from types import SimpleNamespace

from fastapi import HTTPException
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import (
    ChannelPartner,
    Contact,
    Customer,
    Opportunity,
    OpportunityStage,
    OpportunityType,
    ProbabilityLevel,
    User,
)
from app.routers.opportunities import create_opp, update_opp
from app.schemas import OpportunityCreate, OpportunityUpdate


def _admin_actor(user):
    return SimpleNamespace(
        id=user.id,
        role="admin",
        real_name=user.real_name,
        username=user.username,
    )


def _assert_http_error(detail, callback):
    try:
        callback()
    except HTTPException as exc:
        assert exc.detail == detail
        return
    raise AssertionError(f"Expected HTTPException: {detail}")


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


def test_channel_partner_can_be_changed_when_updating_opportunity():
    db = _session()
    owner = User(
        username="sales-owner",
        password_hash="unused",
        real_name="Sales Owner",
        role="sales",
        is_active=True,
    )
    first_partner = ChannelPartner(name="First Partner", creator=owner)
    second_partner = ChannelPartner(name="Second Partner", creator=owner)
    db.add_all([owner, first_partner, second_partner])
    db.flush()
    opportunity = Opportunity(
        opp_type=OpportunityType.CHANNEL,
        sales_rep_id=owner.id,
        channel_partner_id=first_partner.id,
        name="Channel Project",
        industry="Enterprise",
        amount=100,
        stage=OpportunityStage.STAGE_1,
        probability=ProbabilityLevel.LOW,
    )
    db.add(opportunity)
    db.commit()

    update_opp(
        opportunity.id,
        OpportunityUpdate(channel_partner_id=second_partner.id),
        db=db,
        user=_admin_actor(owner),
    )

    db.refresh(opportunity)
    assert opportunity.channel_partner_id == second_partner.id


def test_handler_person_is_saved_on_create_and_update():
    db = _session()
    owner = User(
        username="contact-owner",
        password_hash="unused",
        real_name="Contact Owner",
        role="sales",
        is_active=True,
    )
    db.add(owner)
    db.flush()
    customer = Customer(name="Contact Customer", owner_id=owner.id)
    db.add(customer)
    db.commit()

    result = create_opp(
        OpportunityCreate(
            name="Contact Project",
            opp_type="direct",
            sales_rep_id=owner.id,
            customer_id=customer.id,
            industry="Enterprise",
            amount=100,
            stage="1",
            probability="LOW",
            key_person="Key One|Security|CISO|13700000000|key@example.com",
            handler_person="Handler One|Procurement|Manager|13800000000|one@example.com",
        ),
        db=db,
        user=_admin_actor(owner),
    )

    opportunity = db.query(Opportunity).filter_by(id=result["id"]).one()
    assert opportunity.handler_person.startswith("Handler One|")
    key_contact = db.query(Contact).filter_by(
        customer_id=customer.id, role_type="key_person", name="Key One"
    ).one()
    handler_contact = db.query(Contact).filter_by(
        customer_id=customer.id, role_type="handler", name="Handler One"
    ).one()
    assert key_contact.department == "Security"
    assert key_contact.position == "CISO"
    assert handler_contact.department == "Procurement"
    assert handler_contact.phone == "13800000000"

    update_opp(
        opportunity.id,
        OpportunityUpdate(
            handler_person="Handler Two|IT|Director|13900000000|two@example.com"
        ),
        db=db,
        user=_admin_actor(owner),
    )

    db.refresh(opportunity)
    assert opportunity.handler_person.startswith("Handler Two|")
    updated_handler = db.query(Contact).filter_by(
        customer_id=customer.id, role_type="handler", name="Handler Two"
    ).one()
    assert updated_handler.department == "IT"
    assert updated_handler.email == "two@example.com"


def test_contact_sync_updates_existing_customer_contact_without_duplicates():
    db = _session()
    owner = User(
        username="dedupe-owner",
        password_hash="unused",
        real_name="Dedupe Owner",
        role="sales",
        is_active=True,
    )
    db.add(owner)
    db.flush()
    customer = Customer(name="Dedupe Customer", owner_id=owner.id)
    db.add(customer)
    db.flush()
    db.add(Contact(
        customer_id=customer.id,
        name="Existing Handler",
        role_type="handler",
        position="Old Position",
    ))
    db.commit()

    create_opp(
        OpportunityCreate(
            name="Dedupe Project",
            opp_type="direct",
            sales_rep_id=owner.id,
            customer_id=customer.id,
            industry="Enterprise",
            amount=50,
            stage="1",
            probability="LOW",
            handler_person=(
                "Existing Handler|New Position|13812345678|existing@example.com"
            ),
        ),
        db=db,
        user=_admin_actor(owner),
    )

    contacts = db.query(Contact).filter_by(
        customer_id=customer.id, role_type="handler", name="Existing Handler"
    ).all()
    assert len(contacts) == 1
    assert contacts[0].position == "New Position"
    assert contacts[0].phone == "13812345678"


def test_pain_points_are_saved_on_create_and_update():
    db = _session()
    owner = User(
        username="pain-point-owner",
        password_hash="unused",
        real_name="Pain Point Owner",
        role="sales",
        is_active=True,
    )
    db.add(owner)
    db.flush()
    customer = Customer(name="Pain Point Customer", owner_id=owner.id)
    db.add(customer)
    db.commit()

    result = create_opp(
        OpportunityCreate(
            name="Pain Point Project",
            opp_type="direct",
            sales_rep_id=owner.id,
            customer_id=customer.id,
            industry="Education",
            amount=100,
            stage="1",
            probability="LOW",
            pain_points="Initial customer pain point",
        ),
        db=db,
        user=_admin_actor(owner),
    )

    opportunity = db.query(Opportunity).filter_by(id=result["id"]).one()
    assert opportunity.pain_points == "Initial customer pain point"

    update_opp(
        opportunity.id,
        OpportunityUpdate(pain_points="Updated customer pain point"),
        db=db,
        user=_admin_actor(owner),
    )

    db.refresh(opportunity)
    assert opportunity.pain_points == "Updated customer pain point"


def test_create_requires_relationships_for_each_opportunity_type():
    db = _session()
    owner = User(
        username="required-owner",
        password_hash="unused",
        real_name="Required Owner",
        role="sales",
        is_active=True,
    )
    db.add(owner)
    db.flush()
    customer = Customer(name="Required Customer", owner_id=owner.id)
    partner = ChannelPartner(
        name="Required Partner",
        creator=owner,
        owner_id=owner.id,
    )
    db.add_all([customer, partner])
    db.commit()
    actor = _admin_actor(owner)
    common = {
        "sales_rep_id": owner.id,
        "industry": "Enterprise",
        "amount": 100,
        "stage": "1",
        "probability": "LOW",
    }

    _assert_http_error(
        "请选择最终客户",
        lambda: create_opp(
            OpportunityCreate(name="Missing Direct Customer", **common),
            db=db,
            user=actor,
        ),
    )

    _assert_http_error(
        "请选择关联渠道",
        lambda: create_opp(
            OpportunityCreate(
                name="Missing Channel Partner",
                opp_type="channel",
                end_customer_name="End Customer",
                **common,
            ),
            db=db,
            user=actor,
        ),
    )

    _assert_http_error(
        "请输入最终客户",
        lambda: create_opp(
            OpportunityCreate(
                name="Missing Channel Customer",
                opp_type="channel",
                channel_partner_id=partner.id,
                **common,
            ),
            db=db,
            user=actor,
        ),
    )

    direct = create_opp(
        OpportunityCreate(
            name="Valid Direct",
            customer_id=customer.id,
            **common,
        ),
        db=db,
        user=actor,
    )
    channel = create_opp(
        OpportunityCreate(
            name="Valid Channel",
            opp_type="channel",
            channel_partner_id=partner.id,
            end_customer_name="  Valid End Customer  ",
            **common,
        ),
        db=db,
        user=actor,
    )

    assert db.query(Opportunity).filter_by(id=direct["id"]).one().customer_id == customer.id
    channel_opp = db.query(Opportunity).filter_by(id=channel["id"]).one()
    assert channel_opp.channel_partner_id == partner.id
    assert channel_opp.end_customer_name == "Valid End Customer"


if __name__ == "__main__":
    test_channel_partner_can_be_changed_when_updating_opportunity()
    test_handler_person_is_saved_on_create_and_update()
    test_contact_sync_updates_existing_customer_contact_without_duplicates()
    test_pain_points_are_saved_on_create_and_update()
    test_create_requires_relationships_for_each_opportunity_type()
    print("opportunity contact regression tests passed")
