"""Tracker 0.50.0 (Miguel, asked 21 Nov 2026): the pipeline first. Core, Apps and Bugs open on the stage strip alone;
a tapped stage shows its cards, tapped again it puts them away. The Waiting on me screen is gone: what waits on you is
an orange count on its tab and its stage. Goals reads '8 goals' (never a badge). Show-and-tell is called Final approval
on the page; the label, the API keys and the comment lines the builder reads keep their names.
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
CSS = (ROOT / 'web' / 'styles.css').read_text()
HTML = (ROOT / 'web' / 'index.html').read_text()
sys.path.insert(0, str(ROOT / 'app'))
import server as S  # noqa: E402

CHROME = next((shutil.which(b) for b in ('chromium', 'chromium-browser', 'google-chrome', 'google-chrome-stable') if shutil.which(b)), None)


class Source(unittest.TestCase):
    def test_version(self):
        self.assertGreaterEqual(tuple(int(x) for x in S.VERSION.split('.')), (0, 50, 0))
        self.assertIn('**0.50.0**', (ROOT / 'wizard.md').read_text())

    def test_no_waiting_on_me_screen(self):
        for gone in ('me-btn', 'renderMe', 'loadMe', 'bd-meview', "'#me': 'me'"):
            self.assertNotIn(gone, JS + HTML + CSS, gone)

    def test_goals_is_a_plain_count(self):
        self.assertNotIn('goals-n', JS + HTML)
        self.assertIn("el('goals-t').textContent = k ? `${k} ${k === 1 ? 'goal' : 'goals'}` : 'Goals';", JS)

    def test_the_name_is_only_the_page_s_word(self):
        self.assertEqual(S.SHOW_LABEL, 'show-and-tell')                 # the label the builder reads
        src = (ROOT / 'app' / 'server.py').read_text()
        self.assertIn("f'Show-and-tell: yes", src)                      # and its comment lines
        self.assertIn("{ key: 'show', word: 'Final approval', groups: ['show'] }", JS)
        self.assertNotRegex(JS, r"word: 'Show-and-tell'")

    def test_style_rules(self):
        new = CSS[CSS.index('/* 0.50.0'):]
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
        p = subprocess.run(['node', str(ROOT / 'tests' / 'cdp_eval.mjs'), CHROME, url, str(ROOT / 'tests' / 'fixture_0500.js')],
                           capture_output=True, text=True, timeout=90)
        if p.returncode:
            raise AssertionError(p.stderr or p.stdout)
        cls.out = json.loads(p.stdout.strip().splitlines()[-1])

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()

    def test_a_tab_opens_on_the_pipeline_alone(self):
        o = self.out['opened']
        self.assertEqual((o['stage'], o['cards'], o['heads'], o['tools']), (None, 0, [], False))
        self.assertEqual(o['empty'], 'Tap a stage to see what\u2019s in it.')
        self.assertEqual(o['strip']['queued'][0], '2')                  # the numbers are all there
        self.assertEqual(o['strip']['show'][0], '3')

    def test_a_tapped_stage_shows_only_its_cards(self):
        o = self.out['tapped']
        self.assertEqual((o['stage'], o['cards'], o['tools']), ('show', 3, True))
        self.assertIn('Waiting on you', o['divider'])                   # yours lead the stage
        self.assertEqual(o['heads'], ['HumanFinal approval 1'])       # the Human tag, then the stage's name on the page
        self.assertEqual(o['waiton'], ['Waiting on James for final approval'])   # a card says who approves, once
        self.assertEqual((self.out['other']['stage'], self.out['other']['cards'], self.out['other']['heads']), ('queued', 2, ['Queued 2']))

    def test_tapped_again_it_puts_them_away(self):
        o = self.out['again']
        self.assertEqual((o['stage'], o['cards'], o['tools']), (None, 0, False))

    def test_another_tab_starts_on_the_pipeline_too(self):
        self.assertEqual((self.out['core']['stage'], self.out['core']['cards']), (None, 0))
        self.assertEqual((self.out['back']['stage'], self.out['back']['cards']), (None, 0))

    def test_orange_counts_say_where_you_are_needed(self):
        self.assertEqual(self.out['tabs'], {'goals': None, 'core': '1', 'apps': '2', 'bugs': None})
        self.assertEqual(self.out['opened']['strip']['show'][1], '2')
        self.assertIsNone(self.out['opened']['strip']['queued'][1])
        self.assertEqual(self.out['core']['strip']['answer'][1], '1')
        self.assertFalse(self.out['me'])

    def test_goals_reads_as_words(self):
        self.assertEqual(self.out['goals'], '2 goals')

    def test_an_old_me_link_opens_where_you_are_needed(self):
        self.assertEqual(self.out['mine'], {'view': 'apps', 'stage': 'show', 'cards': 3})


if __name__ == '__main__':
    unittest.main()
