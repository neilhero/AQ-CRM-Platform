import importlib.util
import os
from pathlib import Path
from types import SimpleNamespace
import unittest


def load_bidding_module():
    candidate = os.getenv("BIDDING_MODULE_PATH")
    if not candidate:
        from app.routers import bidding

        return bidding
    spec = importlib.util.spec_from_file_location("bidding_candidate", candidate)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


bidding = load_bidding_module()


class BiddingParserTests(unittest.TestCase):
    def setUp(self):
        self.source = SimpleNamespace(
            name="中国政府采购网",
            search_url="https://search.ccgp.gov.cn/bxsearch?searchtype=1&kw={keyword}",
        )

    def test_extracts_matching_public_notice(self):
        html = """
        <div class="notice">
          <a href="/notice/123">某单位网络安全设备采购项目公开招标公告</a>
          <p>采购人：杭州市数据资源管理局 | 预算金额：128.5万元 |
             投标截止时间：2026-08-15 09:30</p>
        </div>
        """
        rows = bidding._extract_results(self.source, "网络安全", html)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["company"], "杭州市数据资源管理局")
        self.assertEqual(rows[0]["budget"], 128.5)
        self.assertEqual(rows[0]["deadline"].isoformat(), "2026-08-15")

    def test_ignores_unrelated_notice(self):
        html = '<a href="/notice/456">某单位办公家具采购项目公开招标公告</a>'
        self.assertEqual(bidding._extract_results(self.source, "网络安全", html), [])

    def test_parses_qcc_result_shape(self):
        payload = {
            "Result": {
                "Data": [
                    {
                        "Title": "政务网络安全服务招标",
                        "ContentUrl": "https://example.com/tender/1",
                        "BudgetAmt": "2.5亿元",
                        "BidEndDate": "2026-09-01 10:00",
                        "Province": "浙江省",
                        "City": "杭州市",
                        "BidInviUnitList": [
                            {"Name": "杭州市某单位", "Contact": "张老师", "TelNo": "0571-12345678"}
                        ],
                    }
                ]
            }
        }
        rows = bidding._extract_qcc_rows(payload)
        self.assertEqual(rows[0]["Title"], "政务网络安全服务招标")
        self.assertEqual(bidding._parse_money_wan(rows[0]["BudgetAmt"]), 25000)

    def test_real_ccgp_sample_when_provided(self):
        sample = os.getenv("CCGP_SAMPLE_PATH")
        if not sample:
            self.skipTest("CCGP_SAMPLE_PATH not set")
        html = Path(sample).read_text(encoding="utf-8")
        rows = bidding._extract_results(self.source, "网络安全", html)
        self.assertGreater(len(rows), 0)
        self.assertTrue(all("网络安全" in bidding._clean_text(row["title"]) for row in rows))

    def test_live_ccgp_collection_when_enabled(self):
        if os.getenv("CCGP_LIVE") != "1":
            self.skipTest("CCGP_LIVE not enabled")
        rows = bidding._collect_source(self.source, "网络安全")
        self.assertGreater(len(rows), 0)
        self.assertTrue(all(row["url"].startswith(("http://", "https://")) for row in rows))


if __name__ == "__main__":
    unittest.main()
