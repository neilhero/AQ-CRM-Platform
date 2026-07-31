from datetime import date, timedelta
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Opportunity, OpportunityStage, OpportunityType, User
from app.routers.dashboard import sales_performance


def test_sales_performance_counts_complete_direct_and_channel_pipeline():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()
    try:
        seller = User(
            username="seller",
            password_hash="x",
            real_name="销售甲",
            role="sales",
            is_active=True,
        )
        other_role = User(
            username="manager",
            password_hash="x",
            real_name="主管甲",
            role="manager",
            is_active=True,
        )
        db.add_all([seller, other_role])
        db.flush()

        previous_month = date.today().replace(day=1) - timedelta(days=1)
        db.add_all(
            [
                Opportunity(
                    name="跨月直销商机",
                    opp_type=OpportunityType.DIRECT,
                    sales_rep_id=seller.id,
                    amount=45,
                    created_at=previous_month,
                ),
                Opportunity(
                    name="本月渠道商机",
                    opp_type=OpportunityType.CHANNEL,
                    sales_rep_id=seller.id,
                    amount=60,
                    created_at=date.today(),
                ),
                Opportunity(
                    name="主管商机",
                    opp_type=OpportunityType.DIRECT,
                    sales_rep_id=other_role.id,
                    amount=999,
                    created_at=date.today(),
                ),
            ]
        )
        db.commit()

        result = sales_performance(
            period="month",
            db=db,
            user=SimpleNamespace(id=seller.id, role="sales"),
        )

        assert len(result) == 1
        assert result[0]["sales_rep_name"] == "销售甲"
        assert result[0]["opp_count"] == 2
        assert result[0]["total_amount"] == 105
    finally:
        db.close()
