"""0.46.0 (Miguel, 21 Nov 2026): the pipeline has exactly two human steps, Pending approval (Feedback app reports from
outside the team: a team member approves or declines) and Show-and-tell (a feature's one yes or no). They wear ONE
treatment everywhere a stage shows (strip, stats, section headers, cards, the item's own line) and their counts show
under the strip; every automatic step stays neutral. /api/policy marks exactly those two steps `human: true`.
Run: python3 -m unittest discover -s tests"""
import functools
import http.server
import json
import re
import shutil
import subprocess
import threading
import unittest
from pathlib import Path

from test_013 import S

ROOT = Path(__file__).resolve().parent.parent
JS = (ROOT / 'web' / 'app.js').read_text()
FB = (ROOT / 'web' / 'feedback-stage.js').read_text()
CSS = (ROOT / 'web' / 'styles.css').read_text()
HTML = (ROOT / 'web' / 'index.html').read_text()
CHROME = next((shutil.which(b) for b in ('chromium', 'chromium-browser', 'google-chrome', 'google-chrome-stable') if shutil.which(b)), None)
HUMAN = {'feedback', 'show'}


class Policy(unittest.TestCase):
    def setUp(self):
        self.p = S.policy()

    def test_exactly_two_human_steps(self):
        marked = {(v, s['key']) for v, st in self.p['steps'].items() for s in st if s.get('human')}
        self.assertEqual({k for _, k in marked}, HUMAN)
        self.assertEqual(marked, {('features', 'feedback'), ('features', 'show'), ('bugs', 'feedback')})
        self.assertEqual(self.p['human_steps'], ['feedback', 'show'])

    def test_every_step_says_human_or_not(self):
        for v, st in self.p['steps'].items():
            for s in st:
                self.assertIs(type(s.get('human')), bool, (v, s['key']))
                if s['key'] not in HUMAN:
                    self.assertFalse(s['human'], (v, s['key']))

    def test_pending_approval_step(self):
        for v in ('features', 'bugs'):
            first = self.p['steps'][v][0]
            self.assertEqual((first['key'], first['name'], first['group'], first['human']), ('feedback', 'Pending approval', 'feedback', True))
            self.assertIn('/api/feedback/review', first['api']['decide'])
        self.assertNotIn('feedback', [s['key'] for s in self.p['steps']['goals']])
        show = next(s for s in self.p['steps']['features'] if s['key'] == 'show')
        self.assertTrue(show['human'])

    def test_lines_say_two(self):
        text = '\n'.join(self.p['lines'])
        self.assertIn('Exactly two human steps: Pending approval', text)
        self.assertNotIn('only human step', json.dumps(self.p))


class Source(unittest.TestCase):
    def test_one_treatment(self):
        self.assertIn("const HUMAN_STEPS = new Set(['feedback', 'show']);", JS)
        self.assertNotIn('human-n', HTML)                  # 0.49.0: the row under the strip repeated the strip's two tiles
        self.assertNotIn('humanChip', FB + JS)             # 0.49.0: the heading and the card's edge say Human
        self.assertIn('--bd-human: var(--bd-warn)', CSS)
        self.assertIn('.bd-dbin .bd-human-w { display: none; }', CSS)   # 0.46.1: icon only in the narrow pop-up steps

    def test_style_rules(self):
        new = CSS[CSS.index('/* 0.46.0'):]
        self.assertNotRegex(new, r'#[0-9a-fA-F]{3,8}\b')
        self.assertNotRegex(new, r'font-size:\s*[0-9.]+px')
        self.assertNotIn('rgba(', new)


@unittest.skipUnless(shutil.which('node') and CHROME, 'node or chromium missing')
class Rendered(unittest.TestCase):
    """The real page renders App features and Bugs with items in both human steps (tests/fixture_0460.js)."""
    @classmethod
    def setUpClass(cls):
        handler = functools.partial(type('Q', (http.server.SimpleHTTPRequestHandler,), {'log_message': lambda *a: None}),
                                    directory=str(ROOT / 'web'))
        cls.httpd = http.server.ThreadingHTTPServer(('127.0.0.1', 0), handler)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        url = f'http://127.0.0.1:{cls.httpd.server_address[1]}/index.html'
        p = subprocess.run(['node', str(ROOT / 'tests' / 'cdp_eval.mjs'), CHROME, url, str(ROOT / 'tests' / 'fixture_0460.js')],
                           capture_output=True, text=True, timeout=90)
        if p.returncode:
            raise AssertionError(p.stderr or p.stdout)
        cls.out = json.loads(p.stdout.strip().splitlines()[-1])

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()

    def test_strip_and_stats(self):
        for v, want in (('apps', HUMAN), ('bugs', {'feedback'})):
            o = self.out[v]
            self.assertNotIn('error', o)
            self.assertEqual({b['key'] for b in o['bins'] if b['human']}, want, v)
            self.assertEqual({b['key'] for b in o['bins'] if b['tag']}, want, v)
            self.assertEqual({b['key'] for b in o['stats'] if b['human']}, want, v)
            self.assertTrue(any(not b['human'] for b in o['bins']))   # automatic steps stay neutral

    def test_counts(self):
        # 0.49.0: the strip's own human tiles carry the counts (no second row)
        self.assertEqual({b['key']: b['n'] for b in self.out['apps']['bins'] if b['human']}, {'feedback': '1', 'show': '1'})
        self.assertEqual({b['key']: b['n'] for b in self.out['bugs']['bins'] if b['human']}, {'feedback': '1'})
        self.assertFalse(self.out['apps']['row'] or self.out['bugs']['row'])
        # and a stage nothing goes through any more is not in the strip while it is empty
        self.assertEqual([b['key'] for b in self.out['apps']['bins']], ['feedback', 'queued', 'building', 'answer', 'show', 'shipping', 'done'])

    def test_headers_and_cards(self):
        o = self.out['apps']
        self.assertEqual({h['id'] for h in o['heads'] if h['human']}, {'sec-feedback', 'sec-show'})
        self.assertTrue(all(not h['human'] for h in o['heads'] if h['id'] not in ('sec-feedback', 'sec-show')))
        cards = {c['title']: c for c in o['cards']}
        self.assertTrue(cards['Shuffle button']['human'] and cards['Dark mode please']['human'])
        self.assertIsNone(cards['Shuffle button']['chip'])      # 0.49.0: no chip repeating the heading
        self.assertIsNone(cards['Dark mode please']['chip'])
        self.assertFalse(cards['Queue view']['human'] or cards['Queue view']['chip'])

    def test_item_flow_line(self):
        f = self.out['flow']
        self.assertEqual([x['word'] for x in f if x['human']], ['Final approval'])
        self.assertTrue(next(x for x in f if x['word'] == 'Final approval')['cur'])


if __name__ == '__main__':
    unittest.main()
