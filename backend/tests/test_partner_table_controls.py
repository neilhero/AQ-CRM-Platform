from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import ChannelPartner, User
from app.routers.dashboard import partner_performance


FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "index.html"


def _source() -> str:
    return FRONTEND.read_text(encoding="utf-8")


def test_partner_archive_creator_sort_and_filter_are_leadership_only():
    source = _source()

    assert "var canManagePartnerView = partnerUser.role === 'admin' || partnerUser.role === 'manager';" in source
    assert "filters: canManagePartnerView ? creatorFilters : undefined" in source
    assert "sorter: canManagePartnerView ? function(a, b)" in source
    assert "record.created_by_name || record.owner_name" in source


def test_partner_performance_creator_sort_and_filter_are_leadership_only():
    source = _source()

    assert "var canManagePerformanceView = performanceUser.role === 'admin' || performanceUser.role === 'manager';" in source
    assert "title: '创建人', dataIndex: 'created_by_name'" in source
    assert "filters: canManagePerformanceView ? creatorFilters : undefined" in source
    assert "String(record.created_by_name || '') === String(value)" in source


def test_partner_performance_returns_original_creator_for_any_role():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()
    try:
        creator = User(
            username="sales_manager",
            password_hash="x",
            real_name="刘义",
            role="manager",
            is_active=True,
        )
        db.add(creator)
        db.flush()
        db.add(
            ChannelPartner(
                name="测试渠道",
                created_by=creator.id,
                created_by_name="刘义",
                owner_id=creator.id,
            )
        )
        db.commit()

        result = partner_performance(
            period="all",
            db=db,
            user=SimpleNamespace(id=999, role="admin"),
        )

        assert len(result) == 1
        assert result[0]["created_by_name"] == "刘义"
        assert "sales_names" not in result[0]
    finally:
        db.close()
