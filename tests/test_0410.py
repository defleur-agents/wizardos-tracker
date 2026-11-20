"""0.41.0 (Miguel, 20 Nov 2026): core features filed since the cutover need no approval; a duplicate check at filing.
Run: python3 -m unittest discover -s tests"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault('DATA_DIR', tempfile.mkdtemp(prefix='tracker-0400-'))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'app'))
import dupes  # noqa: E402
import server as S  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
JS = (ROOT / 'web/app.js').read_text()
CUT = S.POLICY_DEFAULT['core_approval_not_needed_since']
BEFORE, AFTER = '2026-11-19T10:16:28Z', '2026-11-21T09:00:00Z'


class Cutover(unittest.TestCase):
    def g(self, repo, labels, created, body=None, base=None):
        return S.item_group(repo, labels, 'open', base, created, body)

    def test_cutover_is_a_utc_time_and_in_the_policy(self):
        self.assertRegex(CUT, r'^2026-11-20T\d\d:\d\d:\d\dZ$')
        self.assertEqual(S.policy_base()['core_approval_not_needed_since'], CUT)
        pol = S.policy()
        self.assertEqual(pol['core_approval_not_needed_since'], CUT)
        self.assertEqual(pol['builder_rules']['core_feature_needs_label_if_filed_before'], CUT)
        self.assertIn('possible-duplicate', pol['builder_rules']['skip_labels'])

    def test_old_core_features_keep_waiting_new_ones_queue(self):
        self.assertEqual(self.g('o/wizard-ux', ['feature'], BEFORE), 'james')
        self.assertEqual(self.g('o/wizard-ux', ['feature'], AFTER), 'queued')
        self.assertEqual(self.g('o/wizard-ux', ['feature'], CUT), 'queued')               # on the cutover: new
        self.assertEqual(self.g('o/wizard-ux', ['feature'], None), 'james')               # unknown age: as before
        self.assertEqual(self.g('o/wizard-ux', ['feature', 'james-approved'], BEFORE), 'queued')
        self.assertEqual(self.g('o/wizard-messenger', ['feature'], BEFORE), 'queued')     # app features never waited
        self.assertEqual(self.g('o/wizard-ux', ['feature', 'building'], BEFORE), 'building')

    def test_a_refiled_copy_keeps_its_original_filing_time(self):
        body = f'words\n\nFiled by @x with Report or request (moved from o/wizard-os#1).\n\n<!-- filed-at: {BEFORE} -->'
        self.assertEqual(self.g('o/try-wizard', ['feature', 'refiled'], AFTER, body), 'james')
        self.assertEqual(self.g('o/try-wizard', ['feature', 'refiled'], AFTER, 'words'), 'queued')

    def test_policy_file_can_move_the_cutover(self):
        base = {**S.policy_base(), 'core_approval_not_needed_since': '2026-11-01T00:00:00Z'}
        self.assertEqual(self.g('o/wizard-ux', ['feature'], BEFORE, None, base), 'queued')
        self.assertEqual(S._cutover('not a date')[0], CUT)

    def test_sorting_approve_only_for_the_old_backlog(self):
        self.assertTrue(S.needs_approval('o/wizard-os', ['feature', 'triage'], BEFORE))
        self.assertFalse(S.needs_approval('o/wizard-os', ['feature', 'triage'], AFTER))
        self.assertFalse(S.needs_approval('o/wizard-os', ['bug', 'triage'], BEFORE))

    def test_james_decide_refuses_a_new_core_feature(self):
        saved = (S.account_for, S._current)
        S.account_for = lambda person=None, agent=False: ('k', {'token': 't', 'login': 'mistermizel'})
        S._current = lambda acct, full, n: {'labels': [{'name': 'feature'}], 'state': 'open', 'created_at': AFTER, 'body': ''}
        try:
            with self.assertRaises(S.Problem) as e:
                S.james_decide('k', {'repo': 'humanitylabs-org/wizard-ux', 'number': 5, 'decision': 'approve'})
            self.assertEqual(e.exception.code, 409)
        finally:
            S.account_for, S._current = saved


ITEMS = [
    {'id': 'o/wizard-ux#10', 'title': 'Search in Settings', 'url': 'u10',
     'para': 'A search box at the top of Settings that finds any setting by name, like macOS System Settings.'},
    {'id': 'o/wizard-ux#11', 'title': 'Phone nav: bigger orb and icons', 'url': 'u11',
     'para': 'Make the phone navigation orb bigger and the icons larger, one badge on the ring.'},
    {'id': 'o/wizard-mail#3', 'title': 'Mark all as read', 'url': 'u3', 'para': 'One tap marks every message in the inbox as read.'},
    {'id': 'o/wizard-os#7', 'title': 'Release signing keys in GitHub Actions', 'url': 'u7',
     'para': 'Move the phone and Mac release signing keys into GitHub Actions secrets.'},
]


class Similarity(unittest.TestCase):
    def test_finds_the_same_idea_in_other_words(self):
        got = dupes.matches({'title': 'Let me search settings', 'para': 'I want a search field in Settings to find a setting by its name.'}, ITEMS)
        self.assertEqual([g['id'] for g in got][:1], ['o/wizard-ux#10'])

    def test_unrelated_ideas_do_not_match(self):
        self.assertEqual(dupes.matches({'title': 'Dark mode for the calendar week view',
                                        'para': 'The week grid should follow the dark skin colours.'}, ITEMS), [])
        self.assertEqual(dupes.matches({'title': '', 'para': ''}, ITEMS), [])
        self.assertEqual(dupes.matches({'title': 'Search settings', 'para': ''}, []), [])

    def test_at_most_three_and_one_short_comment(self):
        many = [{**ITEMS[0], 'id': f'o/r#{n}'} for n in range(6)]
        got = dupes.matches({'title': 'Search in Settings', 'para': 'search box top of Settings finds any setting by name'}, many)
        self.assertEqual(len(got), 3)
        self.assertEqual(dupes.comment(got), 'Possible duplicate of o/r#0, o/r#1, o/r#2')


class NotRelatedParts(unittest.TestCase):
    NEW = {'id': 'o/wizard-os#50', 'repo': 'o/wizard-os', 'title': 'Search in Settings', 'author': 'oscar', 'ts': 1000.0,
           'para': 'A search box at the top of Settings that finds any setting by name.'}

    def test_linked_items_and_plan_siblings_are_not_duplicates(self):
        old = {**ITEMS[0], 'repo': 'o/wizard-ux', 'author': 'oscar', 'ts': 900.0, 'refs': set()}
        self.assertEqual(len(dupes.matches(self.NEW, [{**old, 'ts': -1e6}])), 1)            # same author, long ago: a dupe
        self.assertEqual(dupes.matches(self.NEW, [old]), [])                                 # part of the same plan
        self.assertEqual(dupes.matches({**self.NEW, 'refs': dupes.refs('UI part: wizard-ux#10', 'o/wizard-os', 'o')},
                                       [{**old, 'author': 'x'}]), [])                         # the new one links it
        self.assertEqual(dupes.matches(self.NEW, [{**old, 'author': 'x', 'refs': {'o/wizard-os#50'}}]), [])   # it links the new one
        self.assertEqual(len(dupes.matches(self.NEW, [{**old, 'author': 'x'}])), 1)
        self.assertNotIn('refs', dupes.matches(self.NEW, [{**old, 'author': 'x'}])[0])

    def test_refs_forms(self):
        self.assertEqual(dupes.refs('see #4, wizard-ux#9 and https://github.com/o/r/issues/2', 'o/a', 'o'),
                         {'o/a#4', 'o/wizard-ux#9', 'o/r#2'})


class DupeCheck(unittest.TestCase):
    def setUp(self):
        self.saved = (S.gh, S._view_nodes, S._ensure_label, S._add_label, S.settings)
        self.calls = []
        nodes = [{'number': 10, 'title': 'Search in Settings', 'url': 'https://github.com/o/wizard-ux/issues/10',
                  'body': ITEMS[0]['para'] + '\n\n---\nfooter', 'repository': {'nameWithOwner': 'o/wizard-ux'}},
                 {'number': 12, 'title': 'Search in Settings', 'url': 'https://github.com/o/wizard-os/issues/12',
                  'body': 'the new one itself', 'repository': {'nameWithOwner': 'o/wizard-os'}}]
        S._view_nodes = lambda tok, q, **k: (self.calls.append(('search', q)), (nodes, 2))[1]
        S.gh = lambda tok, m, path, body=None, **k: (self.calls.append((m, path, body)), {})[1]
        S._ensure_label = lambda *a: self.calls.append(('ensure',) + a[1:3])
        S._add_label = lambda acct, full, n, label: self.calls.append(('label', full, n, label))
        S.settings = lambda: {'org': 'o'}

    def tearDown(self):
        S.gh, S._view_nodes, S._ensure_label, S._add_label, S.settings = self.saved

    def test_match_comments_once_labels_and_answers_the_matches(self):
        made = {'id': 'o/wizard-os#12', 'repo': 'o/wizard-os', 'number': 12}
        got = S.dupe_check({'token': 't'}, made, 'Let me search settings', 'A search field in Settings that finds a setting by name.')
        self.assertEqual([g['id'] for g in got], ['o/wizard-ux#10'])          # never itself
        self.assertEqual(set(got[0]), {'id', 'title', 'url', 'score'})
        search = [c for c in self.calls if c[0] == 'search'][0][1]
        self.assertIn('is:open', search)
        self.assertIn('-label:goal', search)
        posts = [c for c in self.calls if c[0] == 'POST']
        self.assertEqual(posts, [('POST', '/repos/o/wizard-os/issues/12/comments', {'body': 'Possible duplicate of o/wizard-ux#10'})])
        self.assertIn(('label', 'o/wizard-os', 12, 'possible-duplicate'), self.calls)

    def test_no_match_no_comment_and_a_failure_never_fails_filing(self):
        made = {'id': 'o/wizard-os#12', 'repo': 'o/wizard-os', 'number': 12}
        self.assertEqual(S.dupe_check({'token': 't'}, made, 'Dark calendar week', 'The week grid follows dark skins.'), [])
        self.assertFalse([c for c in self.calls if c[0] in ('POST', 'label')])
        S._view_nodes = lambda *a, **k: (_ for _ in ()).throw(S.Problem(502, 'GitHub down'))
        self.assertEqual(S.dupe_check({'token': 't'}, made, 'Search settings', 'search settings by name'), [])

    def test_filing_paths_run_the_check(self):
        src = (ROOT / 'app/server.py').read_text()
        rf = src[src.index('def report_feature('):src.index('def _current(')]
        self.assertIn("out['possible_duplicates'] = dupe_check(", rf)
        rr = src[src.index('def report_file('):src.index('# ---------- MCP ----------')]
        self.assertIn("dupe_check(acct, made", rr)
        self.assertIn("if kind == 'feature' else []", rr)
        self.assertIn("'possible_duplicates': dup", rr)


class NotDuplicate(unittest.TestCase):
    def setUp(self):
        self.saved = (S.account_for, S._current, S.gh, S._forget)
        self.labels = ['feature', 'possible-duplicate']
        self.calls = []
        S._current = lambda acct, full, n: {'labels': [{'name': x} for x in self.labels]}
        S._forget = lambda tok: None

        def gh(tok, m, path, body=None, **k):
            self.calls.append((m, path, body))
            if m == 'DELETE':
                self.labels.remove('possible-duplicate')
            return {}
        S.gh = gh

    def tearDown(self):
        S.account_for, S._current, S.gh, S._forget = self.saved

    def test_team_member_clears_it(self):
        S.account_for = lambda person=None, agent=False: ('k', {'token': 't', 'login': 'JanMesaric'})
        out = S.not_duplicate('k', {'repo': 'humanitylabs-org/wizard-ux', 'number': 3})
        self.assertNotIn('possible-duplicate', out['labels'])
        self.assertEqual(self.calls[0][0:2], ('POST', '/repos/humanitylabs-org/wizard-ux/issues/3/comments'))
        self.assertEqual(self.calls[1][0:2], ('DELETE', '/repos/humanitylabs-org/wizard-ux/issues/3/labels/possible-duplicate'))

    def test_outsiders_are_refused(self):
        S.account_for = lambda person=None, agent=False: ('k', {'token': 't', 'login': 'stranger'})
        with self.assertRaises(S.Problem) as e:
            S.not_duplicate('k', {'repo': 'humanitylabs-org/wizard-ux', 'number': 3})
        self.assertEqual(e.exception.code, 403)
        self.assertEqual(self.calls, [])

    def test_route_exists(self):
        self.assertIn("'/api/not-duplicate': lambda: not_duplicate(who, body)", (ROOT / 'app/server.py').read_text())


def fn(name):
    start = JS.index('function ' + name + '(')
    depth, i = 0, JS.index('{', start)
    while True:
        depth += {'{': 1, '}': -1}.get(JS[i], 0)
        i += 1
        if depth == 0:
            return JS[start:i]


@unittest.skipUnless(shutil.which('node'), 'node missing')
class Page(unittest.TestCase):
    def run_js(self, src):
        return json.loads(subprocess.run(['node', '-e', src], capture_output=True, text=True, check=True).stdout)

    def test_waiting_for_approval_holds_only_the_old_backlog(self):
        bins = self.run_js(fn('binsOf') + "\nconsole.log(JSON.stringify(binsOf('core').map(x => [x.key, x.groups])));")
        self.assertIn(['james', ['james']], bins)
        self.assertIn(['queued', ['sorting', 'queued']], bins)
        self.assertIn("bins = bins.filter(b => b.key !== 'james')", JS)   # an empty one leaves the strip

    def test_queued_core_card_does_not_say_approved(self):
        src = ("const nextLine = () => '', bugLine = () => ['', ''], onboxOf = () => null, firstLine = x => x;\n" + fn('whereLine')
               + "\nconsole.log(JSON.stringify(whereLine({ group: 'queued', category: 'core', wait_reason: 'Next for the builder' })));")
        self.assertEqual(self.run_js(src)[0], 'Queued · Next for the builder')

    def test_dupe_chip_and_not_a_duplicate(self):
        self.assertIn("'Possible duplicate'", JS)
        self.assertIn("smallBtn('Not a duplicate'", JS)
        self.assertIn("api('api/not-duplicate'", JS)
        self.assertIn('possible_duplicates', (ROOT / 'web/report.js').read_text())


if __name__ == '__main__':
    unittest.main()
