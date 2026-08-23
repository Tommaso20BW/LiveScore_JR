import unittest
from unittest.mock import Mock, patch

import juve_bot_espn as bot


class CanvaExportTests(unittest.TestCase):
    def test_requests_pro_lossless_at_native_size(self):
        failed_response = Mock(status_code=400, text="test stop")

        with patch.object(bot.SESSION, "post", return_value=failed_response) as post:
            self.assertIsNone(bot.get_canva_image("test-access-token", pagina=10))

        request_payload = post.call_args.kwargs["json"]
        self.assertEqual(request_payload["design_id"], bot.CANVA_DESIGN_ID)
        self.assertEqual(
            request_payload["format"],
            {
                "type": "png",
                "pages": [10],
                "export_quality": "pro",
                "lossless": True,
            },
        )
        self.assertNotIn("width", request_payload["format"])
        self.assertNotIn("height", request_payload["format"])


if __name__ == "__main__":
    unittest.main()
