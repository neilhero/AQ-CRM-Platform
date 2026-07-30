import os
import unittest
from datetime import datetime
from unittest.mock import patch

from app.services import dingtalk


class DingTalkNotificationTests(unittest.TestCase):
    def test_disabled_notification_is_skipped(self):
        with patch.dict(os.environ, {"DINGTALK_ENABLED": "false"}, clear=False):
            result = dingtalk.send_work_notification(
                "user-1",
                "title",
                "content",
                "https://an-ai.cn/#/presales",
            )
        self.assertEqual(result["status"], "skipped")
        self.assertEqual(result["reason"], "disabled")

    def test_presales_message_contains_business_context(self):
        with patch.object(
            dingtalk,
            "send_work_notification",
            return_value={"status": "sent", "task_id": 1},
        ) as mocked_send:
            dingtalk.send_presales_notification_safe(
                "user-1",
                42,
                "测试客户有限公司",
                "安全建设项目",
                "POC申请",
                "销售甲",
                datetime(2026, 7, 29, 14, 30),
                "请协助完成测试方案。",
            )

        args = mocked_send.call_args.args
        self.assertEqual(args[0], "user-1")
        self.assertIn("测试客户有限公司", args[2])
        self.assertIn("安全建设项目", args[2])
        self.assertIn("2026-07-29 14:30", args[2])
        self.assertEqual(args[3], "https://an-ai.cn/#/presales?request_id=42")

    def test_delivery_error_does_not_escape_background_task(self):
        with patch.object(
            dingtalk,
            "send_work_notification",
            side_effect=dingtalk.DingTalkError("permission denied"),
        ):
            dingtalk.send_presales_notification_safe(
                "user-1",
                7,
                "客户",
                "商机",
                "售前支持",
                "销售",
                None,
                "需求",
            )


if __name__ == "__main__":
    unittest.main()
