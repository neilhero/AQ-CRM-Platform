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

    def test_ip_public_url_is_normalized_to_certificate_domain(self):
        with patch.dict(
            os.environ,
            {
                "CRM_PUBLIC_URL": "https://121.41.66.121",
                "CRM_CANONICAL_URL": "https://an-ai.cn",
            },
            clear=False,
        ), patch.object(
            dingtalk,
            "send_work_notification",
            return_value={"status": "sent", "task_id": 1},
        ) as mocked_send:
            dingtalk.send_presales_notification_safe(
                "user-1",
                45,
                "客户",
                "商机",
                "售前支持",
                "销售",
                None,
                "需求",
            )

        self.assertEqual(
            mocked_send.call_args.args[3],
            "https://an-ai.cn/#/presales?request_id=45",
        )

    def test_submitter_and_presales_receive_tailored_notifications(self):
        with patch.object(
            dingtalk,
            "send_work_notification",
            return_value={"status": "sent", "task_id": 1},
        ) as mocked_send:
            dingtalk.send_presales_notification_safe(
                "presales-user",
                43,
                "测试客户有限公司",
                "安全建设项目",
                "售前支持",
                "销售甲",
                datetime(2026, 8, 6, 10, 0),
                "请协助准备方案。",
                "sales-user",
            )

        self.assertEqual(mocked_send.call_count, 2)
        presales_args = mocked_send.call_args_list[0].args
        requester_args = mocked_send.call_args_list[1].args
        self.assertEqual(presales_args[0], "presales-user")
        self.assertIn("待处理", presales_args[2])
        self.assertEqual(requester_args[0], "sales-user")
        self.assertIn("已提交", requester_args[1])
        self.assertIn("已提交", requester_args[2])
        self.assertEqual(
            requester_args[3],
            "https://an-ai.cn/#/presales?request_id=43",
        )

    def test_same_dingtalk_user_does_not_receive_duplicate_notification(self):
        with patch.object(
            dingtalk,
            "send_work_notification",
            return_value={"status": "sent", "task_id": 1},
        ) as mocked_send:
            dingtalk.send_presales_notification_safe(
                "same-user",
                44,
                "客户",
                "商机",
                "售前支持",
                "销售",
                None,
                "需求",
                "same-user",
            )

        mocked_send.assert_called_once()

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
