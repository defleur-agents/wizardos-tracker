"""0.45.0 (Miguel, 21 Nov 2026): ONE place and ONE count for what waits on each person. Waiting on me has three
sections only (To approve, Questions for you, Goals needing a status: James only); no 'To try', no pre-build core
approval, nobody presses 'James approved' for James; Approve / Decline on the card, the decider only, and a decided
card leaves every list at once (also while GitHub search still lists its old labels).
Run: python3 -m unittest discover -s tests"""
import json
import re
import shutil
import subprocess
import time
import unittest
from pathlib import Path

from test_013 import GH, S, reset
from test_017 import people
from test_0182 import node

ROOT = Path(__file__).resolve().parent.parent
JS = (ROOT / 'web' / 'app.js').read_text()
HTML = (ROOT / 'web' / 'index.html').read_text()
CSS = (ROOT / 'web' / 'styles.css').read_text()
BOT = 'wizardos-builder[bot]'
PAGE = re.search(r"const PAGE_VERSION = '([^']+)'", JS).group(1)
SHOW = ['feature', 'show-and-tell']


def fn(name):
    m = re.search(r'\n(?:async )?function ' + name + r'\(', JS)
    i, depth = JS.index('{', m.start()), 0
    for j in range(i, len(JS)):
        depth += {'{': 1, '}': -1}.get(JS[j], 0)
        if depth == 0:
            return JS[m.start():j + 1]


class Board(unittest.TestCase):
    """board_split over a stubbed GitHub search: core show-and-tell (James decides), Miguel's app one, Jan's app one, a
    builder question naming Miguel, a goal without a status."""
    def setUp(self):
        GH.issues.clear()
        reset({'core_repos': ['wizard-os'], 'core_approvers': ['James'], 'core_approval_not_needed_since': '2026-01-01'})
        people()
        S._decided.clear()
        S._boards.clear()
        S._needs.clear()
        self.saved = (S._view_search, S._view_nodes, S.view_stats, S.org_repos)
        q = [{'author': {'login': BOT}, 'body': 'Question for @mistermizel: which colour should it be?', 'createdAt': '2026-11-20T00:00:00Z'}]
        self.nodes = {
            'core': [node(1, SHOW, author='mistermizel', repo='humanitylabs-org/wizard-os'),
                     node(2, ['feature'], author='mistermizel', repo='humanitylabs-org/wizard-os')],
            'apps': [node(3, SHOW, author='mistermizel', repo='humanitylabs-org/wizard-music'),
                     node(4, SHOW, author='JanMesaric', repo='humanitylabs-org/wizard-music'),
                     node(5, ['feature', 'building', 'builder:blocked'], author='JanMesaric', repo='humanitylabs-org/wizard-music',
                          comments={'totalCount': 1, 'nodes': q})],
            'bugs': [], 'goals': [node(9, ['goal'], author='jdefleur', repo='humanitylabs-org/wizard-os')],
        }

        def search(token, view, q, **kw):
            return [n for n in self.nodes[view]], len(self.nodes[view])
        S._view_search = search
        S._view_nodes = lambda token, q, **kw: ((self.nodes['goals'], len(self.nodes['goals'])) if 'label:goal' in q else ([], 0))
        S.view_stats = lambda *a, **k: None
        S.org_repos = lambda *a, **k: []

    def tearDown(self):
        S._view_search, S._view_nodes, S.view_stats, S.org_repos = self.saved
        S._boards.clear()
        reset()

    def cards(self, who):
        return {i['number']: i for v in ('core', 'apps', 'goals') for l in S.board_split(who, {'view': v})['groups'].values() for i in l}

    def test_decider_only_buttons(self):
        c = self.cards('m')
        self.assertEqual(c[1]['decider'], 'James')
        self.assertFalse(c[1]['can_decide'])          # Miguel sees no Approve on a core item
        self.assertFalse(c[1]['turn'])
        self.assertFalse(c[1]['can_james'])           # nobody presses 'James approved' for James
        self.assertEqual(c[1]['waiting_on']['who'], ['James'])
        self.assertTrue(c[3]['can_decide'] and c[3]['turn'])    # his own app feature
        self.assertFalse(c[4]['can_decide'])          # Jan's app feature: Jan decides
        self.assertEqual(c[4]['decider'], 'Jan')
        cj = self.cards('j')
        self.assertTrue(cj[1]['can_decide'] and cj[1]['turn'])  # James does
        self.assertFalse(cj[3]['can_decide'])

    def test_no_prebuild_approval(self):
        c = self.cards('m')
        self.assertEqual(c[2]['group'], 'queued')     # core feature, policy: no approval needed
        self.assertFalse(c[2].get('turn'))
        reset({'core_repos': ['wizard-os']})          # even under an old policy (James or Miguel approve) it is no one's turn
        people()
        c = self.cards('m')
        self.assertEqual(c[2]['group'], 'james')
        self.assertFalse(c[2]['turn'])

    def test_question_without_a_name_waits_on_its_filer(self):
        self.nodes['apps'].append(node(6, ['feature', 'builder:blocked'], author='JanMesaric', repo='humanitylabs-org/wizard-music'))
        c = self.cards('m')
        self.assertTrue(c[5]['turn'])                 # names Miguel
        self.assertFalse(c[6]['turn'])                # names nobody: Jan filed it, so it waits on Jan
        self.assertEqual(c[6]['waiting_on']['who'], ['Jan'])
        self.assertTrue(self.cards('n')[6]['turn'])

    def test_goals_james_only(self):
        self.assertFalse(self.cards('m')[9]['turn'])
        self.assertTrue(self.cards('j')[9]['turn'])

    def test_counts_equal(self):
        """The badge (api/needs-you) = the Waiting on me sections, for Miguel and for James."""
        for who, login, want in (('m', 'mistermizel', {'approve': [3], 'answer': [5]}), ('j', 'jdefleur', {'approve': [1], 'goals': [9]})):
            S._boards.clear()
            S._needs.clear()
            splits = [S.board_served(who, {'view': v}) for v in S.NEEDS_VIEWS]
            got = {}
            for d in splits:
                for g, l in d['groups'].items():
                    for i in l:
                        if i.get('turn') and g in ('show', 'answer', 'goals'):
                            got.setdefault({'show': 'approve'}.get(g, g), []).append(i['number'])
            self.assertEqual(got, want, who)
            ny = S.needs_you(who)
            self.assertEqual(ny['count'], sum(len(v) for v in want.values()), who)
            self.assertEqual(ny['count'], len(ny['items']))

    def test_decide_removes_from_waiting_on_me(self):
        GH.issues[3] = {'user': 'mistermizel', 'labels': set(SHOW), 'body': '', 'comments': [(BOT, 'Switch: none')]}
        before = S.needs_you('m')['count']
        S.board_served('m', {'view': 'apps'})        # kept answer, still listing #3
        orig = S._target
        S._target = lambda a: ('humanitylabs-org/wizard-ux', 3)   # the GitHub stub knows wizard-ux only
        try:
            S.decide('m', {'repo': 'wizard-music', 'number': 3, 'decision': 'yes'})
        finally:
            S._target = orig
        self.assertIn('switch-default', GH.issues[3]['labels'])
        self.assertNotIn('show-and-tell', GH.issues[3]['labels'])
        S._decided['humanitylabs-org/wizard-music#3'] = time.time()
        # GitHub search still says show-and-tell: the kept answer and a fresh one both leave it out
        served = S.board_served('m', {'view': 'apps'})
        self.assertNotIn(3, [i['number'] for i in served['groups']['show']])
        self.assertEqual(served['counts']['show'], len(served['groups']['show']))
        fresh = S.board_split('m', {'view': 'apps'})
        self.assertNotIn(3, [i['number'] for i in fresh['groups']['show']])
        self.assertEqual(S.needs_you('m')['count'], before - 1)

    def test_one_read_at_a_time_and_stale_on_limit(self):   # 0.45.1
        import threading
        calls, gate = [], threading.Event()
        real, real_split = S._view_search, S.board_split

        def slow(token, view, q, **kw):
            gate.wait(2)
            return real(token, view, q, **kw)
        S._view_search = slow
        S.board_split = lambda p, a: calls.append(a['view']) or real_split(p, a)
        self.addCleanup(setattr, S, 'board_split', real_split)
        out = []
        ts = [threading.Thread(target=lambda: out.append(S.board_served('m', {'view': 'apps'}))) for _ in range(4)]
        for t in ts:
            t.start()
        time.sleep(0.3)
        gate.set()
        for t in ts:
            t.join(5)
        self.assertEqual(calls, ['apps'])             # four requests, one GitHub read
        self.assertEqual(len(out), 4)

        def limited(*a, **k):
            raise S.Problem(429, 'GitHub limit reached; back in a minute.', 'rate_limited')
        S._view_search = limited
        d = S.board_served('m', {'view': 'apps', 'refresh': True})   # Reload while limited: the last answer, marked
        self.assertTrue(d['stale'])
        self.assertEqual(d['counts'], out[0]['counts'])
        S._boards.clear()
        with self.assertRaises(S.Problem):
            S.board_served('m', {'view': 'apps'})     # nothing kept: the error as before

    def test_served_is_kept(self):
        a = S.board_served('m', {'view': 'apps'})
        calls = []
        S._view_search = lambda *a, **k: calls.append(1) or ([], 0)
        b = S.board_served('m', {'view': 'apps'})
        self.assertEqual(calls, [])                   # warm: no GitHub crawl
        self.assertEqual(a['counts'], b['counts'])


class DecideLabels(unittest.TestCase):
    def setUp(self):
        GH.issues.clear()
        reset({'core_repos': ['wizard-os']})
        people()

    def test_label_refused_is_clear_and_comment_not_posted(self):
        GH.issues[70] = {'user': 'mistermizel', 'labels': set(SHOW), 'body': '', 'comments': [(BOT, 'Switch: none')]}
        orig = S._add_label

        def refuse(acct, full, number, label):
            raise S.Problem(403, 'Resource not accessible by integration')
        S._add_label = refuse
        try:
            with self.assertRaises(S.Problem) as e:
                S.decide('m', {'repo': 'wizard-ux', 'number': 70, 'decision': 'yes'})
        finally:
            S._add_label = orig
        self.assertEqual(e.exception.reason, 'label_refused')
        self.assertIn('approved', e.exception.message)
        self.assertIn('humanitylabs-org/wizard-ux#70', e.exception.message)
        self.assertEqual(len(GH.issues[70]['comments']), 1)     # nothing half-done
        self.assertIn('show-and-tell', GH.issues[70]['labels'])

    def test_missing_labels_created_first(self):
        GH.issues[71] = {'user': 'mistermizel', 'labels': set(SHOW), 'body': '', 'comments': [(BOT, 'Switch: none')]}
        S._labels_made.clear()
        GH.calls.clear()
        S.decide('m', {'repo': 'wizard-ux', 'number': 71, 'decision': 'yes'})
        made = [p for m, p, _ in GH.calls if m == 'POST' and p == '/repos/humanitylabs-org/wizard-ux/labels']
        self.assertEqual(len(made), 2)                # approved + switch-default
        first_comment = next(k for k, (m, p, _) in enumerate(GH.calls) if p.endswith('/71/comments') and m == 'POST')
        first_label = next(k for k, (m, p, _) in enumerate(GH.calls) if p.endswith('/71/labels') and m == 'POST')
        self.assertLess(first_label, first_comment)

    def test_old_james_approved_is_decider_only(self):
        GH.issues[72] = {'user': 'JanMesaric', 'labels': {'feature', 'show-and-tell'}, 'comments': []}
        reset()              # wizard-ux is core: James decides
        people()
        with self.assertRaises(S.Problem) as e:
            S.show_and_tell('m', {'repo': 'wizard-ux', 'number': 72})
        self.assertEqual((e.exception.code, e.exception.reason), (403, 'not_decider'))
        S.show_and_tell('j', {'repo': 'wizard-ux', 'number': 72})
        self.assertNotIn('show-and-tell', GH.issues[72]['labels'])


class Page(unittest.TestCase):
    def test_no_your_decisions(self):
        self.assertNotIn('id="decide"', HTML)
        for gone in ('Your decisions', 'drawDecisions', "api('api/decisions", 'decideNow', "'James approved'", "api('api/james'",
                     "api('api/show'", "'To try'", 'Approve this core feature', 'Feedback to approve ', 'Updates on this Wizard '):
            self.assertNotIn(gone, JS, gone)
        self.assertNotIn('bd-dec-', CSS)

    def test_waiting_on_me_sections(self):
        # 0.50.0: the same three kinds (myTurn), counted per tab for the orange badges instead of listed on a screen
        self.assertNotIn('ME_KINDS', JS)
        self.assertIn('function mineIn(v) {', JS)
        self.assertIn("if (i.group === 'show') return !!i.turn;", JS)
        self.assertIn("if (i.group === 'answer') return !!i.turn;", JS)

    def test_one_wording(self):
        area = fn('actionArea')
        self.assertIn("smallBtn('Approve'", area)
        self.assertIn("smallBtn('Decline'", area)
        self.assertNotIn("smallBtn('Yes'", area)
        self.assertIn('decides`', area)
        self.assertNotIn("g === 'james'", area)

    def test_myturn_rule(self):
        if not shutil.which('node'):
            self.skipTest('node missing')
        cases = [({'group': 'show', 'turn': True}, True), ({'group': 'show', 'turn': False, 'can_james': True}, False),
                 ({'group': 'james', 'can_james': True, 'turn': True}, False), ({'group': 'test', 'turn': True}, False),
                 ({'group': 'answer', 'turn': True}, True), ({'group': 'goals', 'turn': True}, True)]
        src = fn('myTurn') + '\nconsole.log(JSON.stringify(' + json.dumps([c for c, _ in cases]) + '.map(myTurn)));'
        out = subprocess.run(['node', '-e', src], capture_output=True, text=True, check=True).stdout
        self.assertEqual(json.loads(out), [w for _, w in cases])

    def test_action_area_render(self):
        """Render actionArea for a core show card as Miguel (James decides) and as James (Approve / Decline)."""
        if not shutil.which('node'):
            self.skipTest('node missing')
        stub = """
class N { constructor(t){this.tag=t;this.children=[];this.classList={add:()=>{}};this.textContent='';}
  append(...c){this.children.push(...c);} addEventListener(){} setAttribute(){} }
const make = (t, c, x) => { const n = new N(t); n.className = c; if (x !== undefined) n.textContent = x; return n; };
const smallBtn = (t, f) => make('button', 'bd-mini', t);
const text = n => typeof n === 'string' ? n : (n.textContent || '') + (n.children || []).map(text).join('|');
const tryState = () => ({}), tryToggle = () => null;   // 0.48.1: these items have no switch
const waitHead = () => null;   // 0.49.0: no 'Waiting on' line on these
"""
        src = stub + fn('actionArea') + """
const a = actionArea({group: 'show', kind: 'feature', category: 'core', decider: 'James', can_decide: false}, false);
const b = actionArea({group: 'show', kind: 'feature', category: 'core', decider: 'James', can_decide: true}, false);
const c = actionArea({group: 'james', kind: 'feature', category: 'core', can_james: true}, false);
console.log(JSON.stringify([text(a), b.children.map(x => x.textContent), c]));"""
        out = json.loads(subprocess.run(['node', '-e', src], capture_output=True, text=True, check=True).stdout)
        self.assertEqual(out[0], 'James decides')
        self.assertEqual(out[1], ['Approve', 'Decline'])
        self.assertIsNone(out[2])

    def test_style_gate_and_versions(self):
        tail = CSS[CSS.index('0.45.0'):]
        self.assertNotRegex(tail, r'#[0-9a-fA-F]{3,8}\b|rgba?\(')
        self.assertNotRegex(tail, r'font-size:\s*[0-9.]+px')
        self.assertEqual(S.VERSION, PAGE)
        self.assertIn(f"const PAGE_VERSION = '{PAGE}';", JS)

    def test_node_check(self):
        if not shutil.which('node'):
            self.skipTest('node missing')
        subprocess.run(['node', '--check', str(ROOT / 'web' / 'app.js')], check=True)


if __name__ == '__main__':
    unittest.main()
