"""0.35.1: app updates say what happened (Robert, 15 Nov: Messenger's update got stuck, then it opened blank)."""
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JS = (ROOT / 'web' / 'app.js').read_text()


class AppUpdate(unittest.TestCase):
    def test_waits_as_long_as_the_app_manager(self):
        # 0.36.0: 35 min (the App Manager's update limit is 30, wizard-app-manager#712)
        self.assertIn('const UPDATE_WAIT_MS = 35 * 60000;', JS)
        self.assertNotIn("n < 360; n++", JS)

    def test_lost_job_is_said(self):
        self.assertIn("e.status === 404 && ++lost >= 3 ? { state: 'lost' }", JS)
        self.assertIn('The App Manager lost track of this update', JS)

    def test_stopped_after_update_is_said_at_once(self):
        i = JS.index("if (j.status === 'stopped') throw tag(new Error(stoppedWhy(a.name, a.latest)), true);")
        self.assertLess(i, JS.index("runStep(r, 'Restarting', jobDetail(j));"))
        self.assertIn('ended up stopped', JS)   # 0.36.0: and the Tracker then starts it (test_036)

    def test_settings_list_names_stopped_apps(self):
        self.assertIn("apps.filter(a => isStopped(a) && !a.pinned && !runs.get(a.id))", JS)

    def test_header_says_refreshing(self):
        self.assertIn("f.textContent = 'refreshing…'", JS)
        self.assertNotIn("f.textContent = 'updating…'", JS)


class Version(unittest.TestCase):
    def test_versions_agree(self):
        from test_013 import S
        v = S.VERSION
        self.assertRegex(v, r'^\d+\.\d+\.\d+$')
        self.assertIn(f"PAGE_VERSION = '{v}'", JS)
        self.assertIn(f"version: '{v}' }})", JS)
        self.assertIn(f'**{v}**', (ROOT / 'wizard.md').read_text())
        self.assertEqual(json.loads((ROOT / 'runtipi' / 'config.json').read_text())['version'], v)
        self.assertEqual(json.loads((ROOT / 'openapi.json').read_text())['info']['version'], v)


if __name__ == '__main__':
    unittest.main()
