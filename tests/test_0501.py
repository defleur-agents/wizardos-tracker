"""Tracker 0.50.1 (Miguel, 21-22 Nov 2026: 'the update all thing is still not working', 'I should be able to update
individually as well'). What his tap did on 21 Nov, from the App Manager's own record: three apps started together but
the banner showed one; Update all then started the WizardOS update, which fails on his Wizard for a reason outside the
Tracker, restarts Wizard, and (started again while apps updated) broke Music's update. Now: every running update shows,
each thing has its own Update, a WizardOS update that failed last time says why and is left out of Update all, and an
app update never starts while WizardOS installs.
Run: python3 -m unittest discover -s tests"""
import functools
import http.server
import json
import shutil
import subprocess
import sys
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JS = (ROOT / 'web' / 'app.js').read_text()
CSS = (ROOT / 'web' / 'styles.css').read_text()
sys.path.insert(0, str(ROOT / 'app'))
import server as S  # noqa: E402

CHROME = next((shutil.which(b) for b in ('chromium', 'chromium-browser', 'google-chrome', 'google-chrome-stable') if shutil.which(b)), None)
REASON = 'Last WizardOS update failed (0.3.358): wizard-agent-service: update to release source failed.'


class Source(unittest.TestCase):
    def test_version(self):
        self.assertGreaterEqual(tuple(int(x) for x in S.VERSION.split('.')), (0, 50, 1))
        self.assertIn('**0.50.1**', (ROOT / 'wizard.md').read_text())

    def test_the_panel_and_the_banner_say_the_failure_the_same_way(self):
        self.assertEqual(JS.count('osFailText('), 2)       # one sentence, used by the banner and by the panel
        self.assertIn("card.append(make('p', 'bd-why', osFailText(u)));", JS)

    def test_style_rules(self):
        new = CSS[CSS.index('/* 0.50.1'):CSS.index('/* 0.24.2')]
        self.assertNotRegex(new, r'#[0-9a-fA-F]{3,8}\b|rgba?\(')
        self.assertNotRegex(new, r'font-size:\s*[0-9.]+px')


@unittest.skipUnless(shutil.which('node') and CHROME, 'node or chromium missing')
class Rendered(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        handler = functools.partial(type('Q', (http.server.SimpleHTTPRequestHandler,), {'log_message': lambda *a: None}),
                                    directory=str(ROOT / 'web'))
        cls.httpd = http.server.ThreadingHTTPServer(('127.0.0.1', 0), handler)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        url = f'http://127.0.0.1:{cls.httpd.server_address[1]}/index.html'
        p = subprocess.run(['node', str(ROOT / 'tests' / 'cdp_eval.mjs'), CHROME, url, str(ROOT / 'tests' / 'fixture_0501.js')],
                           capture_output=True, text=True, timeout=90)
        if p.returncode:
            raise AssertionError(p.stderr or p.stdout)
        cls.out = json.loads(p.stdout.strip().splitlines()[-1])

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()

    def test_each_thing_has_its_own_update(self):
        o = self.out['offered']
        self.assertEqual(o['title'], '3 updates ready: Tinfoil, Wisdom, WizardOS.')
        self.assertEqual(o['rows'], [['wizard-tinfoil', 'Tinfoil 0.3.16 \u2192 0.3.17', 'Update'], ['wisdom', 'Wisdom 0.4.38 \u2192 0.4.39', 'Update'],
                                     ['os', 'WizardOS 0.3.362', 'Try again']])
        self.assertEqual(o['all'], 'Update all')

    def test_a_wizardos_update_that_failed_says_why(self):
        self.assertEqual(self.out['offered']['why'], {'os': REASON + ' Update all leaves it out.'})

    def test_one_app_alone_leaves_the_rest_untouched_and_offered(self):
        r, d = self.out['oneRunning'], self.out['oneDone']
        self.assertEqual(r['calls'], ['wizard-tinfoil'])
        self.assertEqual(r['panels'], [['wizard-tinfoil', 'running']])
        self.assertEqual([x[0] for x in r['rows']], ['wisdom', 'os'])             # still offered while Tinfoil updates
        self.assertEqual(d['calls'], ['wizard-tinfoil'])                          # nothing else was started
        self.assertEqual(d['rows'], [['wisdom', 'Wisdom 0.4.38 \u2192 0.4.39', 'Update'], ['os', 'WizardOS 0.3.362', 'Try again']])
        self.assertEqual(d['title'], '2 updates ready: Wisdom, WizardOS.')        # Tinfoil is no longer listed

    def test_update_all_leaves_out_the_wizardos_update_that_failed(self):
        r, d = self.out['allBadRunning'], self.out['allBadDone']
        self.assertEqual(r['panels'], [['wizard-tinfoil', 'running'], ['wisdom', 'running']])
        self.assertEqual(r['q'], 'Updating 2: 0 done')
        self.assertEqual(d['calls'], ['wizard-tinfoil', 'wisdom'])                # never 'os'
        self.assertEqual(d['rows'], [['os', 'WizardOS 0.3.362', 'Try again']])    # still there, with its reason
        self.assertEqual(d['why'], {'os': REASON})

    def test_every_running_update_shows_and_wizardos_goes_last(self):
        self.assertEqual(self.out['healthy']['rows'][-1], ['os', 'WizardOS 0.3.350 \u2192 0.3.362', 'Update'])
        r = self.out['allRunning']
        self.assertEqual(r['panels'], [['a1', 'running'], ['a2', 'running'], ['a3', 'running']])   # it showed one of the three
        self.assertEqual(r['q'], 'Updating 5: 0 done \u00b7 next: Delta, WizardOS')
        self.assertEqual(self.out['peak'], 3)
        self.assertEqual(self.out['allDone']['calls'], ['a1', 'a2', 'a3', 'a4', 'os'])
        self.assertTrue(self.out['allDone']['hidden'])                            # nothing left to offer

    def test_one_that_fails_keeps_its_line_its_reason_and_a_retry(self):
        o = self.out['oneFailed']
        self.assertEqual(o['rows'], [['a2', 'Beta 1 \u2192 2', 'Retry']])
        self.assertEqual(o['why'], {'a2': 'Didn\u2019t update: Beta 2 did not work; 1 still runs'})

    def test_an_app_update_waits_while_wizardos_installs(self):
        self.assertEqual(self.out['held']['calls'], [])
        self.assertEqual(self.out['held']['notes'], ['Alpha waits for the WizardOS update to finish.'])
        self.assertEqual(self.out['heldDone']['calls'], ['a1'])

    def test_the_confirm_never_says_null(self):
        self.assertTrue(self.out['confirm'])


if __name__ == '__main__':
    unittest.main()
