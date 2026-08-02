from pathlib import Path


FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "index.html"


def _source() -> str:
    return FRONTEND.read_text(encoding="utf-8")


def test_partner_archive_creator_sort_and_filter_are_leadership_only():
    source = _source()

    assert "var canManagePartnerView = partnerUser.role === 'admin' || partnerUser.role === 'manager';" in source
    assert "filters: canManagePartnerView ? creatorFilters : undefined" in source
    assert "sorter: canManagePartnerView ? function(a, b)" in source
    assert "record.created_by_name || record.owner_name" in source


def test_partner_performance_sales_filter_handles_multiple_salespeople():
    source = _source()

    assert "var canManagePerformanceView = performanceUser.role === 'admin' || performanceUser.role === 'manager';" in source
    assert "split(/[、,，]/)" in source
    assert "filters: canManagePerformanceView ? salesFilters : undefined" in source
    assert "salesNameList(record.sales_names).indexOf(String(value)) >= 0" in source
