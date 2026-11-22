"""Tracker 0.49.0 (Miguel, 21 Nov 2026): clean-up, each thing is said once. The Waiting on people row under the strip
repeated the strip's two Human tiles; every card repeated its section heading in a chip and its first line in
'X decides'; Waiting on me said 'Waiting on you' on every card; two stages nothing goes through sat in the strip at 0.
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
sys.path.insert(0, str(ROOT / 'app'))
import server as S  # noqa: E402

CHROME = next((shutil.which(b) for b in ('chromium', 'chromium-browser', 'google-chrome', 'google-chrome-stable') if shutil.which(b)), None)


def fn(name):
    return re.search(r'^(?:async )?function ' + name + r'\(.*?^}', JS, re.S | re.M).group(0)


def node(src):
    return json.loads(subprocess.run(['node', '-e', src], capture_output=True, text=True, check=True).stdout)


class Source(unittest.TestCase):
    def test_version(self):
        self.assertGreaterEqual(tuple(int(x) for x in S.VERSION.split('.')), (0, 49, 0))
        self.assertIn('**0.49.0**', (ROOT / 'wizard.md').read_text())

    def test_no_second_human_row(self):
        self.assertNotIn('humanCounts', JS)
        self.assertNotIn('Waiting on people', JS + (ROOT / 'web' / 'index.html').read_text())
        self.assertNotIn('.bd-human-n', CSS)

    def test_style_rules(self):
        new = CSS[CSS.index('/* 0.49.0'):]
        self.assertNotRegex(new, r'#[0-9a-fA-F]{3,8}\b|rgba?\(')
        self.assertNotRegex(new, r'font-size:\s*[0-9.]+px')


@unittest.skipUnless(shutil.which('node'), 'node missing')
class Logic(unittest.TestCase):
    def test_one_word_for_the_queue(self):
        words = node(fn('binsOf') + "console.log(JSON.stringify(['core', 'apps', 'bugs'].map(v => binsOf(v).find(b => b.key === 'queued').word)));")
        self.assertEqual(words, ['Queued', 'Queued', 'Queued'])

    def test_a_person_is_listed_once_whatever_the_capitals(self):
        out = node(fn('authorsOf') + "console.log(JSON.stringify(authorsOf({groups: {a: [{author: 'JanMesaric'}, {author: 'janmesaric'}, {author: 'JanMesaric'}], b: [{author: 'jdefleur'}]}})));")
        self.assertEqual(out, [['JanMesaric', 3], ['jdefleur', 1]])

    def test_under_the_waiting_on_you_divider_a_card_does_not_repeat_it(self):
        # 0.50.0: the Waiting on me screen is gone; the cards that wait on you lead their stage under one divider
        stub = """
class N { constructor(){this.children=[];} append(...c){this.children.push(...c);} }
const make = (t, c, x) => { const n = new N(); n.textContent = x || ''; return n; };
const document = { createTextNode: t => ({ textContent: t }) };
const cache = { core: { me_person: 'Miguel' } };
const sortBy = { core: 'turn', apps: 'oldest' }; const myTurn = i => !!i.turn;
"""
        src = stub + 'const WAIT_WHAT = { show: "for final approval" };' + fn('waitHead') + """
const mine = { group: 'show', turn: true, waiting_on: { who: ['Miguel'] } }, his = { group: 'show', waiting_on: { who: ['James'] } };
let view = 'core'; const a = [waitHead(mine) === null, waitHead(his) !== null];
view = 'apps'; a.push(waitHead(mine) !== null);   // another sort: no divider, so the card says it
console.log(JSON.stringify(a));"""
        self.assertEqual(node(src), [True, True, True])


@unittest.skipUnless(shutil.which('node') and CHROME, 'node or chromium missing')
class Rendered(unittest.TestCase):
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

    def test_who_decides_is_said_once(self):
        c = self.out['other_waits']
        self.assertIn('Waiting on James', c['head'])
        self.assertNotIn('decides', c['why'])
        self.assertTrue(c['toggle'])                       # Try it stays for everyone
        n = self.out['other_waits_no_switch']
        self.assertIn('Waiting on James', n['head'])
        self.assertFalse(n['act'])                         # nothing to press: no empty row

    def test_without_the_first_line_it_still_says_who_decides(self):
        self.assertIn('James decides', self.out['core_other_decides']['why'])


if __name__ == '__main__':
    unittest.main()
