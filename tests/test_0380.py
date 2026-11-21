"""0.38.0 (Miguel, 18 Nov): goal statuses are In progress / Blocked / Pending final review instead of green/yellow/red
lights. Pending final review is James's turn (Your turn first, /api/needs-you), never the owners'.
Run: python3 -m unittest discover -s tests"""
import json
import shutil
import subprocess
import unittest
from pathlib import Path

from test_013 import GH, S, reset
from test_017 import people, BODY
from test_0182 import node
from test_034 import Fixture, GOALS

ROOT = Path(__file__).resolve().parent.parent
JS = (ROOT / 'web/app.js').read_text()
NOW = S.datetime.now(S.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
OLD = '2020-01-01T00:00:00Z'


def goal(comments, assignees=('JanMesaric',), number=9):
    return node(number, ['goal'], author='jdefleur', comments={'totalCount': len(comments), 'nodes': [
        {'author': {'login': w}, 'body': b, 'createdAt': at} for w, b, at in comments]},
        assignees={'nodes': [{'login': a} for a in assignees]})


class Parse(unittest.TestCase):
    def setUp(self):
        reset()

    def test_new_and_old_values(self):
        rows = [('JanMesaric', 'Status: green\n\nfine', '2026-11-01T00:00:00Z'),
                ('JanMesaric', 'Status: yellow\n\nslipping', '2026-11-02T00:00:00Z'),
                ('JanMesaric', 'Status: red\n\nstuck', '2026-11-03T00:00:00Z'),
                ('JanMesaric', 'Status: working\n\non it', '2026-11-04T00:00:00Z'),
                ('JanMesaric', '**Status: Blocked**\nwaiting on Apple', '2026-11-05T00:00:00Z'),
                ('JanMesaric', 'Status: review\n\nI think it is done', '2026-11-06T00:00:00Z')]
        h = S.status_of(rows)
        self.assertEqual([x['status'] for x in h], ['review', 'blocked', 'working', 'blocked', 'working', 'working'])
        self.assertEqual([x['word'] for x in h[:3]], ['Pending final review', 'Blocked', 'In progress'])
        self.assertEqual(h[0]['color'], 'review')        # old readers get the new value under the old key
        self.assertNotIn('On track', json.dumps(h))

    def test_status_value(self):
        self.assertEqual([S.status_value(v) for v in ('green', 'YELLOW', 'red', 'working', 'blocked', 'review', 'blue', None)],
                         ['working', 'working', 'blocked', 'working', 'blocked', 'review', None, None])


class Post(unittest.TestCase):
    def setUp(self):
        GH.issues.clear()
        reset()
        people()
        GH.issues[40] = {'user': 'jdefleur', 'assignees': ['JanMesaric'], 'labels': {'goal'}, 'comments': [], 'body': BODY}

    def test_status_field(self):
        r = S.goal_status_set('n', {'repo': 'wizard-ux', 'number': 40, 'status': 'review', 'text': 'Done list is ticked.'})
        self.assertEqual(GH.issues[40]['comments'][-1], ('JanMesaric', 'Status: review\n\nDone list is ticked.'))
        self.assertEqual((r['status']['status'], r['status']['word']), ('review', 'Pending final review'))

    def test_old_color_callers_still_work(self):
        S.goal_status_set('n', {'repo': 'wizard-ux', 'number': 40, 'color': 'red', 'text': 'Stuck on review.'})
        self.assertEqual(GH.issues[40]['comments'][-1][1], 'Status: blocked\n\nStuck on review.')
        S.goal_status_set('n', {'repo': 'wizard-ux', 'number': 40, 'color': 'green', 'text': 'Moving.'})
        self.assertEqual(GH.issues[40]['comments'][-1][1], 'Status: working\n\nMoving.')
        with self.assertRaises(S.Problem) as e:
            S.goal_status_set('n', {'repo': 'wizard-ux', 'number': 40, 'status': 'done', 'text': 'Moving.'})
        self.assertEqual(str(e.exception.message), 'status must be working, blocked or review.')

    def test_mcp_schema(self):
        t = next(t for t in S.TOOLS if t['name'] == 'goal_status_set')
        props = t['inputSchema']['properties']
        self.assertEqual(props['status']['enum'], ['working', 'blocked', 'review'])
        self.assertIn('green', props['color']['enum'])
        self.assertEqual(t['inputSchema']['required'], ['text'])
        self.assertNotIn('On track', t['description'])
        api = json.loads((ROOT / 'openapi.json').read_text())
        body = api['paths']['/api/goal/status']['post']['requestBody']['content']['application/json']['schema']
        self.assertEqual(body['properties']['status']['enum'], ['working', 'blocked', 'review'])


class Turn(unittest.TestCase):
    def setUp(self):
        reset()
        people()

    def test_review_is_james_turn_not_owner(self):
        base = S.policy_base()
        old_review = [('JanMesaric', 'Status: review\n\nI think it is done', OLD)]
        jan = S.goal_card(goal(old_review), 'JanMesaric', base)
        self.assertFalse(jan['turn'])                                  # not nagged, even though the status is old
        james = S.goal_card(goal(old_review), 'jdefleur', base)
        self.assertTrue(james['turn'])
        self.assertEqual(james['turn_why'], 'Goal says it is done: check and close it')
        self.assertFalse(S.goal_card(goal(old_review), 'mistermizel', base)['turn'])

    def test_working_and_blocked_unchanged(self):
        base = S.policy_base()
        for st in ('working', 'blocked', 'green', 'red'):
            # 0.45.0: a stale status waits on James only (goals are his), never on the owner
            self.assertTrue(S.goal_card(goal([('JanMesaric', f'Status: {st}\n\nx', OLD)]), 'jdefleur', base)['turn'])
            self.assertFalse(S.goal_card(goal([('JanMesaric', f'Status: {st}\n\nx', NOW)]), 'jdefleur', base)['turn'])
            self.assertFalse(S.goal_card(goal([('JanMesaric', f'Status: {st}\n\nx', OLD)]), 'JanMesaric', base)['turn'])


class NeedsYou(Fixture):
    def setUp(self):
        super().setUp()
        self.saved_goals = [dict(g) for g in GOALS]
        GOALS[0]['comments'] = {'totalCount': 1, 'nodes': [
            {'author': {'login': 'mistermizel'}, 'body': 'Status: review\n\nShipped, check it.', 'createdAt': OLD}]}
        S._needs.clear()

    def tearDown(self):
        GOALS[:] = self.saved_goals
        S._needs.clear()
        super().tearDown()

    def test_review_goal_goes_to_james(self):
        u = 'humanitylabs-org/wizard-ux#40'
        self.assertNotIn(u, self.ids('m'))                            # the owner is not nagged
        S._needs.clear()
        self.assertEqual(self.ids('j').get(u), 'Goal says it is done: check and close it')


class Page(unittest.TestCase):
    def test_no_lights_wording(self):
        self.assertNotIn('On track', JS)
        self.assertNotIn('At risk', JS)
        self.assertIn("const LIGHT = { working: 'In progress', blocked: 'Blocked', review: 'Pending final review' };", JS)
        self.assertIn("status: st, text", JS)
        css = (ROOT / 'web/styles.css').read_text()
        self.assertIn('.bd-light.review', css)
        self.assertNotIn('.bd-light.green', css)

    @unittest.skipUnless(shutil.which('node'), 'node missing')
    def test_old_values_map_in_page(self):
        a = JS.index('const LIGHT = {')
        src = JS[a:JS.index('\n', JS.index('const stOf'))] + """
console.log(JSON.stringify([stOf({color: 'green'}), stOf({color: 'yellow'}), stOf({color: 'red'}), stOf({status: 'review'}), stOf({status: 'working', color: 'working'})]));"""
        got = json.loads(subprocess.run(['node', '-e', src], capture_output=True, text=True, check=True).stdout)
        self.assertEqual(got, ['working', 'working', 'blocked', 'review', 'working'])

    def test_skill_documents_status(self):
        sk = (ROOT / 'skill/SKILL.md').read_text()
        self.assertIn('`Status: working|blocked|review`', sk)
        self.assertNotIn('On track', sk)
