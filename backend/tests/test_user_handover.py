from types import SimpleNamespace

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import AuditLog, ChannelPartner, Customer, Lead, Opportunity, OpportunityType, User
from app.routers.users import UserHandover, handover_user


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


def _user(username, role):
    return User(
        username=username,
        password_hash="unused",
        real_name=username,
        role=role,
        is_active=True,
    )


def test_sales_offboarding_changes_owners_but_preserves_creators():
    db = _session()
    admin = _user("admin", "admin")
    source = _user("leaving-sales", "sales")
    target = _user("sales-manager", "manager")
    db.add_all([admin, source, target])
    db.flush()

    customer = Customer(
        name="Customer A",
        owner_id=source.id,
        created_by_id=source.id,
        created_by_name=source.real_name,
    )
    partner = ChannelPartner(
        name="Partner A",
        created_by=source.id,
        created_by_name=source.real_name,
        owner_id=source.id,
    )
    db.add_all([customer, partner])
    db.flush()
    direct = Opportunity(
        opp_type=OpportunityType.DIRECT,
        sales_rep_id=source.id,
        created_by_id=source.id,
        created_by_name=source.real_name,
        customer_id=customer.id,
        name="Direct A",
    )
    channel = Opportunity(
        opp_type=OpportunityType.CHANNEL,
        sales_rep_id=source.id,
        created_by_id=source.id,
        created_by_name=source.real_name,
        channel_partner_id=partner.id,
        name="Channel A",
    )
    db.add_all([Lead(name="Lead A", assigned_to=source.id), direct, channel])
    db.commit()

    result = handover_user(
        source.id,
        UserHandover(target_user_id=target.id),
        db=db,
        admin=SimpleNamespace(id=admin.id, username=admin.username, role="admin"),
    )

    db.refresh(source)
    db.refresh(customer)
    db.refresh(partner)
    db.refresh(direct)
    db.refresh(channel)
    assert source.is_active is False
    assert customer.owner_id == target.id
    assert customer.created_by_id == source.id
    assert customer.created_by_name == source.real_name
    assert partner.owner_id == target.id
    assert partner.created_by == source.id
    assert partner.created_by_name == source.real_name
    assert direct.sales_rep_id == target.id
    assert direct.created_by_id == source.id
    assert direct.created_by_name == source.real_name
    assert channel.sales_rep_id == target.id
    assert channel.created_by_id == source.id
    assert channel.created_by_name == source.real_name
    assert db.query(Lead).filter_by(assigned_to=target.id).count() == 1
    assert result["transferred"] == {
        "leads": 1,
        "customers": 1,
        "direct_opportunities": 1,
        "channel_opportunities": 1,
        "channel_partners": 1,
    }
    assert db.query(AuditLog).count() == 1


def test_manager_can_select_customers_and_channels_with_linked_opportunities():
    db = _session()
    admin = _user("admin", "admin")
    manager = _user("manager", "manager")
    target = _user("target-sales", "sales")
    db.add_all([admin, manager, target])
    db.flush()

    selected_customer = Customer(
        name="Selected Customer",
        owner_id=manager.id,
        created_by_id=manager.id,
    )
    retained_customer = Customer(
        name="Retained Customer",
        owner_id=manager.id,
        created_by_id=manager.id,
    )
    selected_partner = ChannelPartner(
        name="Selected Partner",
        created_by=manager.id,
        owner_id=manager.id,
    )
    retained_partner = ChannelPartner(
        name="Retained Partner",
        created_by=manager.id,
        owner_id=manager.id,
    )
    db.add_all([selected_customer, retained_customer, selected_partner, retained_partner])
    db.flush()

    selected_direct = Opportunity(
        opp_type=OpportunityType.DIRECT,
        sales_rep_id=manager.id,
        created_by_id=manager.id,
        customer_id=selected_customer.id,
        name="Selected Direct",
    )
    retained_direct = Opportunity(
        opp_type=OpportunityType.DIRECT,
        sales_rep_id=manager.id,
        created_by_id=manager.id,
        customer_id=retained_customer.id,
        name="Retained Direct",
    )
    selected_channel = Opportunity(
        opp_type=OpportunityType.CHANNEL,
        sales_rep_id=manager.id,
        created_by_id=manager.id,
        channel_partner_id=selected_partner.id,
        name="Selected Channel",
    )
    retained_channel = Opportunity(
        opp_type=OpportunityType.CHANNEL,
        sales_rep_id=manager.id,
        created_by_id=manager.id,
        channel_partner_id=retained_partner.id,
        name="Retained Channel",
    )
    db.add_all([
        Lead(name="Selected Lead", assigned_to=manager.id, customer_id=selected_customer.id),
        Lead(name="Retained Lead", assigned_to=manager.id, customer_id=retained_customer.id),
        selected_direct,
        retained_direct,
        selected_channel,
        retained_channel,
    ])
    db.commit()

    result = handover_user(
        manager.id,
        UserHandover(
            target_user_id=target.id,
            transfer_all=False,
            customer_ids=[selected_customer.id],
            channel_partner_ids=[selected_partner.id],
        ),
        db=db,
        admin=SimpleNamespace(id=admin.id, username=admin.username, role="admin"),
    )

    for row in [manager, selected_customer, retained_customer, selected_partner, retained_partner]:
        db.refresh(row)
    for row in [selected_direct, retained_direct, selected_channel, retained_channel]:
        db.refresh(row)

    assert manager.is_active is True
    assert selected_customer.owner_id == target.id
    assert retained_customer.owner_id == manager.id
    assert selected_partner.owner_id == target.id
    assert retained_partner.owner_id == manager.id
    assert selected_direct.sales_rep_id == target.id
    assert retained_direct.sales_rep_id == manager.id
    assert selected_channel.sales_rep_id == target.id
    assert retained_channel.sales_rep_id == manager.id
    assert selected_customer.created_by_id == manager.id
    assert selected_partner.created_by == manager.id
    assert selected_direct.created_by_id == manager.id
    assert selected_channel.created_by_id == manager.id
    assert db.query(Lead).filter_by(assigned_to=target.id).count() == 1
    assert db.query(Lead).filter_by(assigned_to=manager.id).count() == 1
    assert result["transfer_all"] is False
    assert result["transferred"] == {
        "leads": 1,
        "customers": 1,
        "direct_opportunities": 1,
        "channel_opportunities": 1,
        "channel_partners": 1,
    }


if __name__ == "__main__":
    test_sales_offboarding_changes_owners_but_preserves_creators()
    test_manager_can_select_customers_and_channels_with_linked_opportunities()
    print("user handover regression tests passed")
