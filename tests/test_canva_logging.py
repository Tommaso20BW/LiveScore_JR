import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, call, patch

import canva_page_one as canva


class CanvaLoggingTests(unittest.TestCase):
    def test_export_uses_structured_debug_logging_only(self):
        session = Mock()
        session.post.return_value.json.return_value = {'job': {'id': 'test'}}
        session.get.side_effect = [
            Mock(json=lambda: {
                'job': {
                    'status': 'success',
                    'urls': ['https://example.test/pdf']
                }
            }),
            Mock(content=b'pdf')
        ]

        with tempfile.TemporaryDirectory() as root, \
             patch.object(canva, 'extract_layers', return_value=Path(root)), \
             patch.object(canva, 'log_line') as structured_log, \
             patch('builtins.print') as raw_print:
            canva.export_page_one(
                session,
                'token',
                'design',
                Path(root),
                sleep=lambda _: None
            )

        raw_print.assert_not_called()
        self.assertEqual(
            structured_log.call_args_list,
            [
                call(
                    'DEBUG',
                    'CANVA',
                    'Nuovo export PDF PRO pagina 1 richiesto'
                ),
                call(
                    'DEBUG',
                    'CANVA',
                    'PDF PRO pagina 1 scaricato | '
                    'background e maschera verificati'
                ),
            ]
        )


if __name__ == '__main__':
    unittest.main()
