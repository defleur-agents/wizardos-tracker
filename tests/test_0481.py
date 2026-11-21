"""Tracker 0.48.1 (Miguel, 21 Nov 2026): Try it is back, on the show-and-tell card. The switch lived only on the
hand-testing cards and went with them in 0.43.0, so a feature that ships switched off could not be switched on from the
Tracker before its yes or no. The UI test renders real show-and-tell cards in headless Chromium.
Run: python3 -m unittest discover -s tests"""
import functools
import http.server
import json
import re
import shutil
import subprocess
import sys
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JS = (ROOT / 'web' / 'app.js').read_text()
sys.path.insert(0, str(ROOT / 'app'))
import server as S  # noqa: E402

CHROME = next((shutil.which(b) for b in ('chromium', 'chromium-browser', 'google-chrome', 'google-chrome-stable') if shutil.which(b)), None)


class Source(unittest.TestCase):
    def test_version(self):
        self.assertGreaterEqual(tuple(int(x) for x in S.VERSION.split('.')), (0, 48, 1))
        self.assertIn('**0.48.1**', (ROOT / 'wizard.md').read_text())

    def test_show_branch_has_the_toggle_before_the_decider_check(self):
        m = re.search(r'^function actionArea\(.*?^}', JS, re.S | re.M).group(0)
        show = m[m.index("if (g === 'show')"):]
        self.assertLess(show.index('tryToggle(i)'), show.index('if (!i.can_decide)'))

    def test_show_cards_are_checked_against_this_wizard(self):
        self.assertIn("const askOn = [...(d.groups.test || []), ...(d.groups.show || []),", JS)


@unittest.skipUnless(shutil.which('node') and CHROME, 'node or chromium missing')
class RenderedShowCard(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        handler = functools.partial(type('Q', (http.server.SimpleHTTPRequestHandler,), {'log_message': lambda *a: None}),
                                    directory=str(ROOT / 'web'))
        cls.httpd = http.server.ThreadingHTTPServer(('127.0.0.1', 0), handler)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        url = f'http://127.0.0.1:{cls.httpd.server_address[1]}/index.html'
        p = subprocess.run(['node', str(ROOT / 'tests' / 'cdp_eval.mjs'), CHROME, url, str(ROOT / 'tests' / 'show_try_fixture.js')],
                           capture_output=True, text=True, timeout=90)
        if p.returncode:
            raise AssertionError(p.stderr or p.stdout)
        cls.out = json.loads(p.stdout.strip().splitlines()[-1])

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()

    def test_a_switch_on_this_wizard_is_a_live_toggle_beside_approve_and_decline(self):
        c = self.out['core']
        self.assertTrue(c['toggle'] and not c['grey'], c)
        self.assertEqual(c['coreSwitch'], 'wizard/agent-inbox')
        self.assertIn('Try it', c['label'])
        self.assertEqual(c['buttons'][-2:], ['Approve', 'Decline'])

    def test_someone_who_does_not_decide_can_still_try(self):
        c = self.out['core_other_decides']
        self.assertTrue(c['toggle'] and not c['grey'], c)
        self.assertIn('James decides', c['why'])
        self.assertNotIn('Approve', c['buttons'])

    def test_an_app_switch_flips_in_its_app(self):
        c = self.out['app']
        self.assertTrue(c['toggle'] and not c['grey'], c)
        self.assertEqual(c['appSwitch'], 'wizard-calendar:three-day')
        self.assertIn('Open Calendar', c['buttons'])

    def test_a_switch_this_wizard_does_not_have_is_grey_and_says_why(self):
        for k in ('core_missing', 'app_missing', 'needs_update'):
            with self.subTest(k):
                c = self.out[k]
                self.assertTrue(c['toggle'] and c['grey'], c)
                self.assertTrue(c['why'], c)
                self.assertEqual(c['buttons'][-2:], ['Approve', 'Decline'])   # the yes or no stays
        self.assertIn('Update WizardOS', self.out['needs_update']['why'])

    def test_no_switch_no_toggle(self):
        c = self.out['none']
        self.assertFalse(c['toggle'], c)
        self.assertEqual(c['buttons'], ['Approve', 'Decline'])


if __name__ == '__main__':
    unittest.main()
