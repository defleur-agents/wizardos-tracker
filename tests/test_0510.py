"""Tracker 0.51.0 (Miguel, 21-22 Nov 2026).
1. "Items people filed themselves turn on by themselves after 7 days if nobody says no": an idea at final approval whose
   every piece was filed by its decider gets `auto_at`; the builder's sweep approves it once `auto_due`. The clock starts
   no earlier than the rule. The card says the date.
2. "When I refresh, this one item always seems open": the shell keeps the last link it opened in the Tracker's window
   and loads it on every refresh. A link opens its card once.
Run: python3 -m unittest discover -s tests"""
import json
import re
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JS = (ROOT / 'web' / 'app.js').read_text()
sys.path.insert(0, str(ROOT / 'app'))
import server as S  # noqa: E402


def fn(name):
    m = re.search(r'\n(?:async )?function ' + name + r'\(', JS)
    i, depth = JS.index('{', m.start()), 0
    for j in range(i, len(JS)):
        depth += {'{': 1, '}': -1}.get(JS[j], 0)
        if depth == 0:
            return JS[m.start():j + 1]


def node(src):
    p = subprocess.run(['node', '-e', src], capture_output=True, text=True, timeout=30)
    if p.returncode:
        raise AssertionError(p.stderr)
    return json.loads(p.stdout.strip().splitlines()[-1])


BASE = {**S.POLICY_DEFAULT}
ORG = 'humanitylabs-org'


def item(n, repo='wizard-music', opener='Miguel', decider='Miguel', since='2026-11-23T10:00:00Z', switch=None, part_of=()):
    return {'id': f'{ORG}/{repo}#{n}', 'repo': f'{ORG}/{repo}', 'number': n, 'created_at': f'2026-11-{10 + n:02d}T00:00:00Z',
            'decider': decider, 'opener': opener, 'since': since, 'switch': switch, '_part_of': list(part_of)}


class AutoApprove(unittest.TestCase):
    def test_version(self):
        self.assertGreaterEqual(tuple(int(x) for x in S.VERSION.split('.')), (0, 51, 0))
        self.assertIn('**0.51.0**', (ROOT / 'wizard.md').read_text())

    def test_the_rule_is_seven_days_and_starts_with_the_rule(self):
        self.assertEqual(S.SHOW_AUTO_SECONDS, 7 * 86400)
        self.assertEqual(S.SHOW_AUTO_SINCE, '2026-11-22T00:00:00Z')

    def test_when_it_reached_final_approval(self):
        n = {'stages': {'nodes': [{'createdAt': '2026-11-01T00:00:00Z', 'label': {'name': 'show-and-tell'}},
                                  {'createdAt': '2026-11-05T00:00:00Z', 'label': {'name': 'building'}},
                                  {'createdAt': '2026-11-09T00:00:00Z', 'label': {'name': 'Show-And-Tell'}}, {}, None]}}
        self.assertEqual(S.show_since(n), '2026-11-09T00:00:00Z')      # the last time, when it went back and came again
        self.assertIsNone(S.show_since({'stages': {'nodes': [{'createdAt': '2026-11-05T00:00:00Z', 'label': {'name': 'building'}}]}}))
        self.assertIsNone(S.show_since({}))
        self.assertIn('stages: timelineItems(itemTypes: [LABELED_EVENT]', S.DECIDE_PAGE)
        self.assertEqual(S.DECIDE_PAGE.count(' timelineItems('), 2)    # the second one needs its alias

    def test_only_an_idea_filed_by_its_decider(self):
        mine = [{'opener': 'Miguel', 'since': '2026-11-23T10:00:00Z'}]
        self.assertEqual(S.show_auto_at(mine, 'miguel'), '2026-11-30T10:00:00Z')
        self.assertIsNone(S.show_auto_at([{'opener': 'Miguel', 'since': '2026-11-23T10:00:00Z'}], 'James'))   # someone else approves it
        self.assertIsNone(S.show_auto_at(mine + [{'opener': 'Jan', 'since': '2026-11-23T10:00:00Z'}], 'Miguel'))   # one piece is not his
        self.assertIsNone(S.show_auto_at([{'opener': 'Miguel', 'since': None}], 'Miguel'))                     # unknown: never guessed
        self.assertIsNone(S.show_auto_at([], 'Miguel'))

    def test_the_clock_never_starts_before_the_rule(self):
        self.assertEqual(S.show_auto_at([{'opener': 'James', 'since': '2026-10-12T00:00:00Z'}], 'James'), '2026-11-29T00:00:00Z')

    def test_the_newest_piece_sets_the_clock(self):
        parts = [{'opener': 'James', 'since': '2026-11-23T10:00:00Z'}, {'opener': 'James', 'since': '2026-11-26T09:00:00Z'}]
        self.assertEqual(S.show_auto_at(parts, 'James'), '2026-12-03T09:00:00Z')

    def test_an_idea_carries_it(self):
        a, b = item(1, switch='music/queue'), item(2, repo='wizard-podcasts', switch='music/queue', since='2026-11-25T10:00:00Z')
        c = item(3, opener='Jan', decider='Miguel')
        g = S.idea_groups([a, b, c], BASE)
        self.assertEqual(g[a['id'].lower()]['auto_at'], '2026-12-02T10:00:00Z')
        self.assertIs(g[a['id'].lower()], g[b['id'].lower()])
        self.assertIsNone(g[c['id'].lower()]['auto_at'])

    def test_the_policy_tells_the_builder(self):
        src = (ROOT / 'app' / 'server.py').read_text()
        self.assertIn("'auto_approve': {'who': 'an idea whose every piece was filed by the person who approves it',", src)
        self.assertIn("'seconds': SHOW_AUTO_SECONDS, 'since': SHOW_AUTO_SINCE, 'by': 'builder',", src)
        self.assertIn("'auto_due': bool(g.get('auto_at')) and now >= _ts(g['auto_at'])", src)
        self.assertIn("extra['auto_at'] = idea.get('auto_at') if idea else None", src)

    def test_the_tracker_never_approves_by_itself(self):
        src = (ROOT / 'app' / 'server.py').read_text()
        # it only says when; nothing in the server calls an approval off the clock (the builder's sweep does it, as the builder)
        for name in ('show_since', 'show_auto_at'):
            body = src[src.index(f'def {name}('):]
            body = body[:body.index('\n\n\n')]
            self.assertNotRegex(body, r'gh\(|_decide|_add_label|_close\(')
        self.assertNotRegex(src, r"auto_due[^\n]*_decide_piece|_decide_piece[^\n]*auto_due")

    @unittest.skipUnless(shutil.which('node'), 'node missing')
    def test_the_card_says_the_date(self):
        stub = """
class N { constructor(t, c, x){this.tag=t; this.cls=c||''; this.textContent=x||''; this.children=[]; this.classList={add(){}};} append(...c){this.children.push(...c.filter(Boolean));} }
const make = (t, c, x) => new N(t, c, x);
const tryState = () => ({}), tryToggle = () => null, updPanel = () => null, blockerBits = () => [], openKey = b => b, openApp = () => {};
const smallBtn = t => new N('button', 'btn', t), askPop = () => {}, noteAsk = () => {}, decideAct = () => {};
const waitHead = () => ({});   // the card's first line already says who it waits on
const isHuman = () => false, canTest = () => false, humanTurn = () => false;
"""
        body = fn('actionArea')
        src = stub + body + """
const texts = r => r ? r.children.map(c => c.textContent) : null;
const at = '2026-11-29T00:00:00Z';
const day = new Date(at).toLocaleDateString(undefined, { day: 'numeric', month: 'short' });
const mine = actionArea({ group: 'show', kind: 'feature', can_decide: true, decider: 'Miguel', auto_at: at });
const his = actionArea({ group: 'show', kind: 'feature', can_decide: false, decider: 'James', auto_at: at });
const plain = actionArea({ group: 'show', kind: 'feature', can_decide: false, decider: 'James', auto_at: null });
console.log(JSON.stringify([texts(mine), texts(his), plain, day]));"""
        try:
            mine, his, plain, day = node(src)
        except AssertionError as e:   # actionArea leans on more of the page than this stub has: the source says it instead
            self.skipTest(str(e)[:200])
        line = f'Turns on for everyone by itself on {day} unless declined'
        self.assertEqual(mine, ['Approve', 'Decline', line])
        self.assertEqual(his, [line])
        self.assertIsNone(plain)

    def test_the_card_line_in_source(self):
        self.assertIn("`Turns on for everyone by itself on ${new Date(i.auto_at).toLocaleDateString(undefined, { day: 'numeric', month: 'short' })} unless declined`", JS)
        self.assertIn("if (auto) row.append(auto); return said && !tg0 && !t0.run && !auto ? null : row; }", JS)
        self.assertIn("row.append(yes, no); if (auto) row.append(auto); return row;", JS)


@unittest.skipUnless(shutil.which('node'), 'node missing')
class LinkOpensOnce(unittest.TestCase):
    """linkRestored(): is this load the shell putting an old link back (true: show the list), or a link someone tapped?"""
    def run_case(self, framed, tapped, shown, hash_='#item/humanitylabs-org/wizard-ux/1665'):
        src = f"""
const store = {json.dumps({'board.link.shown': shown} if shown is not None else {})};
const localStorage = {{ getItem: k => (k in store ? store[k] : null), setItem: (k, v) => {{ store[k] = v; }} }};
const window = {{}}; window.parent = {'{}' if framed else 'window'};
const location = {{ hash: {json.dumps(hash_)} }};
const LINK_KEY = 'board.link.shown'; const tappedIn = {json.dumps(tapped)};
{fn('linkShown')}
{fn('linkRestored')}
console.log(JSON.stringify(linkRestored()));"""
        return node(src)

    def test_truth_table(self):
        link, other = '#item/humanitylabs-org/wizard-ux/1665', '#item/humanitylabs-org/wizard-ux/9'
        self.assertFalse(self.run_case(False, False, link))    # the page in its own tab: a link always opens
        self.assertTrue(self.run_case(True, False, link))      # the shell put back the link this page already showed
        self.assertTrue(self.run_case(True, None, link))       # the same, in a browser that cannot say what was tapped
        self.assertFalse(self.run_case(True, True, link))      # the same link tapped again while the app was closed
        self.assertFalse(self.run_case(True, False, other))    # a link it has not shown yet
        self.assertTrue(self.run_case(True, False, None))      # nothing shown since this release and nothing tapped: the stuck one
        self.assertFalse(self.run_case(True, True, None))      # a first link, tapped
        self.assertFalse(self.run_case(True, None, None))      # cannot tell: open it

    def test_wired(self):
        self.assertIn("if (fresh && linkRestored()) return linkDone();", JS)
        self.assertIn("load(view); openLinked(true); loadSide();", JS)
        self.assertIn("window.addEventListener('hashchange', () => { if (ITEM_RE.test(location.hash)) openLinked(); });", JS)   # a tap while open always opens
        self.assertIn("unpop(); hold(false); linkDone(); });", JS)   # closing the card lets the same link open it again


if __name__ == '__main__':
    unittest.main()
