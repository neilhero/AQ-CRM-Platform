from datetime import datetime, timedelta
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
from app.routers.opportunities import create_opp, get_opp, list_opps, update_opp
from app.routers.sales_growth import customer_operation_notifications, customer_operations
from app.schemas import OpportunityCreate, OpportunityUpdate


VALID_KEY_PERSON = "Key Contact|Security|Director|13700000000|key@example.com"
VALID_HANDLER_PERSON = "Handler Contact|Procurement|Manager|13800000000|handler@example.com"


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


def test_customer_operations_accepts_opportunity_datetime_created_at():
    db = _session()
    owner = User(
        username="operations-owner",
        password_hash="unused",
        real_name="Operations Owner",
        role="sales",
        is_active=True,
    )
    db.add(owner)
    db.flush()
    customer = Customer(name="Operations Customer", owner_id=owner.id)
    db.add(customer)
    db.flush()
    opportunity = Opportunity(
        opp_type=OpportunityType.DIRECT,
        sales_rep_id=owner.id,
        customer_id=customer.id,
        name="Stale Project",
        industry="Enterprise",
        amount=100,
        stage=OpportunityStage.STAGE_1,
        probability=ProbabilityLevel.LOW,
        created_at=datetime.now() - timedelta(days=31),
    )
    db.add(opportunity)
    db.commit()

    actor = _admin_actor(owner)
    result = customer_operations(db=db, user=actor)
    notices = customer_operation_notifications(db=db, user=actor)

    assert len(result["items"]) == 1
    assert any(alert["type"] == "stale_opportunity" for alert in result["alerts"])
    assert isinstance(notices["items"], list)


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


def test_opportunity_list_filters_and_sorts_stage_and_probability():
    db = _session()
    owner = User(
        username="list-owner",
        password_hash="unused",
        real_name="List Owner",
        role="sales",
        is_active=True,
    )
    db.add(owner)
    db.flush()
    opportunities = [
        Opportunity(
            opp_type=OpportunityType.DIRECT,
            sales_rep_id=owner.id,
            name="Direct Low Stage",
            industry="Enterprise",
            amount=10,
            stage=OpportunityStage.STAGE_1,
            probability=ProbabilityLevel.LOW,
        ),
        Opportunity(
            opp_type=OpportunityType.DIRECT,
            sales_rep_id=owner.id,
            name="Direct High Stage",
            industry="Enterprise",
            amount=20,
            stage=OpportunityStage.STAGE_3,
            probability=ProbabilityLevel.HIGH,
        ),
        Opportunity(
            opp_type=OpportunityType.CHANNEL,
            sales_rep_id=owner.id,
            name="Channel Mid Stage",
            industry="Enterprise",
            amount=30,
            stage=OpportunityStage.STAGE_2,
            probability=ProbabilityLevel.MID,
        ),
        Opportunity(
            opp_type=OpportunityType.CHANNEL,
            sales_rep_id=owner.id,
            name="Channel Low Probability",
            industry="Enterprise",
            amount=40,
            stage=OpportunityStage.STAGE_4,
            probability=ProbabilityLevel.LOW,
        ),
    ]
    db.add_all(opportunities)
    db.commit()
    actor = _admin_actor(owner)

    stage_sorted = list_opps(
        keyword=None,
        stage=None,
        probability=None,
        opp_type=None,
        sales_rep_id=None,
        channel_partner_id=None,
        sort_by="stage",
        sort_order="ascend",
        skip=0,
        limit=100,
        db=db,
        user=actor,
    )
    assert [item["stage"] for item in stage_sorted] == ["1", "2", "3", "4"]

    probability_sorted = list_opps(
        keyword=None,
        stage=None,
        probability=None,
        opp_type=None,
        sales_rep_id=None,
        channel_partner_id=None,
        sort_by="probability",
        sort_order="ascend",
        skip=0,
        limit=100,
        db=db,
        user=actor,
    )
    assert [item["probability"] for item in probability_sorted] == [
        "LOW", "LOW", "MID", "HIGH"
    ]

    direct_low = list_opps(
        keyword=None,
        stage=None,
        probability="LOW",
        opp_type="direct",
        sales_rep_id=None,
        channel_partner_id=None,
        sort_by=None,
        sort_order=None,
        skip=0,
        limit=100,
        db=db,
        user=actor,
    )
    assert [item["name"] for item in direct_low] == ["Direct Low Stage"]

    channel_stage = list_opps(
        keyword=None,
        stage="2",
        probability=None,
        opp_type="channel",
        sales_rep_id=None,
        channel_partner_id=None,
        sort_by=None,
        sort_order=None,
        skip=0,
        limit=100,
        db=db,
        user=actor,
    )
    assert [item["name"] for item in channel_stage] == ["Channel Mid Stage"]


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


def test_create_requires_key_person_and_handler_person():
    db = _session()
    owner = User(
        username="required-contact-owner",
        password_hash="unused",
        real_name="Required Contact Owner",
        role="sales",
        is_active=True,
    )
    db.add(owner)
    db.flush()
    customer = Customer(name="Required Contact Customer", owner_id=owner.id)
    db.add(customer)
    db.commit()
    actor = _admin_actor(owner)
    common = {
        "opp_type": "direct",
        "sales_rep_id": owner.id,
        "customer_id": customer.id,
        "industry": "Enterprise",
        "amount": 100,
        "stage": "1",
        "probability": "LOW",
    }

    _assert_http_error(
        "请至少填写一名关键人",
        lambda: create_opp(
            OpportunityCreate(
                name="Missing Key Person",
                handler_person=VALID_HANDLER_PERSON,
                **common,
            ),
            db=db,
            user=actor,
        ),
    )
    _assert_http_error(
        "请至少填写一名经办人",
        lambda: create_opp(
            OpportunityCreate(
                name="Missing Handler Person",
                key_person=VALID_KEY_PERSON,
                **common,
            ),
            db=db,
            user=actor,
        ),
    )


def test_edit_can_clear_key_person_and_handler_person():
    db = _session()
    owner = User(
        username="clear-contact-owner",
        password_hash="unused",
        real_name="Clear Contact Owner",
        role="sales",
        is_active=True,
    )
    db.add(owner)
    db.flush()
    customer = Customer(name="Clear Contact Customer", owner_id=owner.id)
    db.add(customer)
    db.commit()
    actor = _admin_actor(owner)
    result = create_opp(
        OpportunityCreate(
            name="Clear Contact Project",
            opp_type="direct",
            sales_rep_id=owner.id,
            customer_id=customer.id,
            industry="Enterprise",
            amount=100,
            stage="1",
            probability="LOW",
            key_person=VALID_KEY_PERSON,
            handler_person=VALID_HANDLER_PERSON,
        ),
        db=db,
        user=actor,
    )

    update_opp(
        result["id"],
        OpportunityUpdate(key_person="", handler_person=""),
        db=db,
        user=actor,
    )

    opportunity = db.query(Opportunity).filter_by(id=result["id"]).one()
    assert opportunity.key_person == ""
    assert opportunity.handler_person == ""
    detail = get_opp(result["id"], db=db, user=actor)
    assert detail["key_person"] == ""
    assert detail["handler_person"] == ""


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
            key_person=VALID_KEY_PERSON,
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
            key_person=VALID_KEY_PERSON,
            handler_person=VALID_HANDLER_PERSON,
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


def test_new_opportunity_keeps_precise_creation_time():
    db = _session()
    owner = User(
        username="time-owner",
        password_hash="unused",
        real_name="Time Owner",
        role="sales",
        is_active=True,
    )
    db.add(owner)
    db.flush()
    customer = Customer(name="Time Customer", owner_id=owner.id)
    db.add(customer)
    db.commit()

    result = create_opp(
        OpportunityCreate(
            name="Timestamp Project",
            sales_rep_id=owner.id,
            customer_id=customer.id,
            industry="Healthcare",
            amount=100,
            stage="1",
            probability="LOW",
            key_person=VALID_KEY_PERSON,
            handler_person=VALID_HANDLER_PERSON,
        ),
        db=db,
        user=_admin_actor(owner),
    )

    opportunity = db.query(Opportunity).filter_by(id=result["id"]).one()
    assert isinstance(opportunity.created_at, datetime)
    assert isinstance(opportunity.updated_at, datetime)


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
        "key_person": VALID_KEY_PERSON,
        "handler_person": VALID_HANDLER_PERSON,
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
