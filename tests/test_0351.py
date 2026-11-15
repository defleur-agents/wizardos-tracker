"""0.35.1: app updates say what happened (Robert, 15 Nov: Messenger's update got stuck, then it opened blank)."""
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JS = (ROOT / 'web' / 'app.js').read_text()


class AppUpdate(unittest.TestCase):
    def test_waits_as_long_as_the_app_manager(self):
        # wam app_update waits up to 20 min for the update, then up to 5 min to start the app again
        self.assertIn('const UPDATE_WAIT_MS = 30 * 60000;', JS)
        self.assertNotIn("n < 360; n++", JS)

    def test_lost_job_is_said(self):
        self.assertIn("e.status === 404 && ++lost >= 3 ? { state: 'lost' }", JS)
        self.assertIn('The App Manager lost track of this update', JS)

    def test_stopped_after_update_is_said_at_once(self):
        i = JS.index("if (j.status === 'stopped') throw new Error(stoppedWhy(a.name, a.latest));")
        self.assertLess(i, JS.index("runStep(r, 'Restarting', jobDetail(j));"))
        self.assertIn('Updating doesn’t start a stopped app', JS)

    def test_settings_list_names_stopped_apps(self):
        self.assertIn("apps.filter(a => a.status === 'stopped')", JS)

    def test_header_says_refreshing(self):
        self.assertIn("f.textContent = 'refreshing…'", JS)
        self.assertNotIn("f.textContent = 'updating…'", JS)


class Version(unittest.TestCase):
    def test_versions_agree(self):
        from test_013 import S
        v = S.VERSION
        self.assertEqual(v, '0.35.1')
        self.assertIn(f"PAGE_VERSION = '{v}'", JS)
        self.assertIn(f"version: '{v}' }})", JS)
        self.assertIn(f'**{v}**', (ROOT / 'wizard.md').read_text())
        self.assertEqual(json.loads((ROOT / 'runtipi' / 'config.json').read_text())['version'], v)
        self.assertEqual(json.loads((ROOT / 'openapi.json').read_text())['info']['version'], v)


if __name__ == '__main__':
    unittest.main()
