"""Tracker 0.54.0 (Miguel, 22 Nov 2026): James declines; the builder's work left."""
import json, os, pathlib, sys, tempfile, time, unittest
ROOT = pathlib.Path(__file__).resolve().parents[1]
JS = (ROOT / 'web' / 'app.js').read_text()


class Declines(unittest.TestCase):
    def test_button(self):
        self.assertIn("declines`, note => decideAct(i, 'no', note, true)", JS)


class Work(unittest.TestCase):
    def test_reported_and_estimated(self):
        os.environ['DATA_DIR'] = tempfile.mkdtemp()
        sys.path.insert(0, str(ROOT / 'app'))
        import importlib, server
        importlib.reload(server)
        self.assertIsNone(server.builder_status()['work'])
        server.builder_status(seen=True, work=json.dumps({'pool': 48, 'bugs': 30, 'features': 18, 'held': 59, 'passed24': 48, 'running': 2}))
        w = server.builder_status()['work']
        self.assertEqual((w['pool'], w['hours'], w['stale']), (48, 24.0, False))
        server.builder_status(seen=True, work='not json')   # a bad report never breaks the switch read
        self.assertEqual(server.builder_status()['work']['pool'], 48)

    def test_page_line(self):
        self.assertIn('function workLine(b)', JS)
        self.assertIn('id="workload"', (ROOT / 'web' / 'index.html').read_text())


if __name__ == '__main__':
    unittest.main()
