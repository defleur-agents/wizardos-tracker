"""0.44.0 (Miguel, 21 Nov 2026): every feature gets ONE show-and-tell; Your decisions is the top of the Tracker.
Decider: core repos -> James (also his own); app repos -> the person who filed it (agent -> its person; builder bot ->
the linked item's filer, else Miguel). Yes = switch-default, No = closed not planned + dropped.
Run: python3 -m unittest discover -s tests"""
import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path

from test_013 import GH, S, reset
from test_017 import people

ROOT = Path(__file__).resolve().parent.parent
JS = (ROOT / 'web' / 'app.js').read_text()
CSS = (ROOT / 'web' / 'styles.css').read_text()
BOT = 'wizardos-builder[bot]'
HANDBACK = ("Built and merged behind the app switch.\n\nWhat changed: with the switch on, the station follows the song. Second "
            "sentence here. Third one.\n\nTested: https://example.test/receipt\n\nShow-and-tell:\nStarting a station from a song "
            "now plays songs like it. Your AI picks them.\nBefore: https://github.com/o/r/blob/e/before.png\n"
            "After: https://github.com/o/r/blob/e/after-1.png and https://github.com/o/r/blob/e/after-2.png (phone)\n"
            "Switch: wizard-music:curated-radio")


def app_policy():
    """wizard-ux counts as an app repo here (the GitHub stub only knows wizard-ux)."""
    reset({'core_repos': ['wizard-os']})
    people()


class Decider(unittest.TestCase):
    def setUp(self):
        GH.issues.clear()
        reset()
        people()

    def test_core_is_james(self):
        for who in ('mistermizel', 'JanMesaric', 'oscarhenrycollins', BOT, 'stranger'):
            self.assertEqual(S.show_decider('humanitylabs-org/wizard-os', who, ''), 'James', who)

    def test_james_own_core_is_james(self):
        self.assertEqual(S.show_decider('humanitylabs-org/wizard-ux', 'jdefleur', ''), 'James')
        self.assertEqual(S.show_decider('humanitylabs-org/try-wizard', 'defleur-agents', ''), 'James')

    def test_app_by_person_is_that_person(self):
        self.assertEqual(S.show_decider('humanitylabs-org/wizard-music', 'mistermizel', ''), 'Miguel')
        self.assertEqual(S.show_decider('humanitylabs-org/wizard-music', 'JanMesaric', ''), 'Jan')
        self.assertEqual(S.show_decider('humanitylabs-org/wizard-music', 'jdefleur', ''), 'James')

    def test_app_by_agent_is_its_person(self):
        self.assertEqual(S.show_decider('humanitylabs-org/wizard-music', 'oscarhenrycollins', ''), 'Miguel')   # Oscar
        self.assertEqual(S.show_decider('humanitylabs-org/wizard-music', 'defleur-agents', ''), 'James')       # Archimedes

    def test_builder_filed_follows_linked_item_else_miguel(self):
        authors = {'humanitylabs-org/wizard-health#8': ('defleur-agents', ''),
                   'humanitylabs-org/wizard-ux#1661': ('jdefleur', ''),
                   'humanitylabs-org/wizard-music#3': (BOT, 'Refs humanitylabs-org/wizard-health#8')}
        look = authors.get
        r = 'humanitylabs-org/wizard-health'
        self.assertEqual(S.show_decider(r, BOT, 'Refs humanitylabs-org/wizard-health#8\n\nmore', None, look), 'James')
        self.assertEqual(S.show_decider(r, BOT, 'Split from #8 (item 2).', None, look), 'James')   # bare #8 = same repo
        self.assertEqual(S.show_decider(r, BOT, 'Follow-up of https://github.com/humanitylabs-org/wizard-ux/issues/1661', None, look), 'James')
        self.assertEqual(S.show_decider(r, BOT, 'Refs humanitylabs-org/wizard-music#3', None, look), 'James')   # chain
        self.assertEqual(S.show_decider(r, BOT, 'No link at all', None, look), 'Miguel')
        self.assertEqual(S.show_decider(r, BOT, 'Refs humanitylabs-org/wizard-os#999', None, look), 'Miguel')  # unknown
        self.assertEqual(S.show_decider(r, BOT, 'Filed by @JanMesaric with Report or request in the Tracker.', None, look), 'Jan')

    def test_policy_override(self):
        reset({'show_deciders': {'core': 'Miguel', 'default': 'Jan'}})
        self.assertEqual(S.show_decider('humanitylabs-org/wizard-os', 'jdefleur', ''), 'Miguel')
        self.assertEqual(S.show_decider('humanitylabs-org/wizard-music', BOT, ''), 'Jan')


class Pitch(unittest.TestCase):
    def test_show_section_and_shots(self):
        p = S.show_pitch([HANDBACK])
        self.assertEqual(p['pitch'], 'Starting a station from a song now plays songs like it. Your AI picks them.')
        self.assertEqual(p['before'], ['https://github.com/o/r/blob/e/before.png'])
        self.assertEqual(p['after'], ['https://github.com/o/r/blob/e/after-1.png', 'https://github.com/o/r/blob/e/after-2.png'])

    def test_falls_back_to_what_changed(self):
        p = S.show_pitch(['What changed: with the switch on, the list is sorted. It also scrolls. And more.\n\nSwitch: none'])
        self.assertEqual(p['pitch'], 'With the switch on, the list is sorted. It also scrolls.')
        self.assertEqual((p['before'], p['after']), ([], []))


class YesNo(unittest.TestCase):
    def setUp(self):
        GH.issues.clear()
        app_policy()

    def _item(self, n, user, switch=True, labels=('feature', 'show-and-tell')):
        GH.issues[n] = {'user': user, 'labels': set(labels), 'body': '',
                        'comments': [(BOT, HANDBACK if switch else 'What changed: docs.\n\nSwitch: none (docs only).')]}

    def test_yes_adds_switch_default_removes_show(self):
        self._item(60, 'mistermizel')
        r = S.decide('m', {'repo': 'wizard-ux', 'number': 60, 'decision': 'yes', 'note': 'Love it'})
        it = GH.issues[60]
        self.assertIn('switch-default', it['labels'])
        self.assertIn('approved', it['labels'])
        self.assertNotIn('show-and-tell', it['labels'])
        self.assertEqual(it.get('state', 'open'), 'open')   # the builder turns it on and closes it
        self.assertTrue(it['comments'][-1][1].startswith('Show-and-tell: yes \u2014 Miguel (@mistermizel)'))
        self.assertIn('Love it', it['comments'][-1][1])
        self.assertTrue(r['switch_default'] and r['saved'])

    def test_yes_without_switch_still_switch_default(self):
        self._item(61, 'oscarhenrycollins', switch=False)   # Oscar's filing -> Miguel decides
        S.decide('m', {'repo': 'wizard-ux', 'number': 61, 'decision': 'yes'})
        self.assertIn('switch-default', GH.issues[61]['labels'])
        self.assertNotIn('show-and-tell', GH.issues[61]['labels'])

    def test_no_closes_not_planned_dropped(self):
        self._item(62, 'mistermizel')
        r = S.decide('m', {'repo': 'wizard-ux', 'number': 62, 'decision': 'no', 'note': 'Not needed'})
        it = GH.issues[62]
        self.assertIn('dropped', it['labels'])
        self.assertIn('switch-cleanup', it['labels'])   # merged behind a switch: the builder's sweep removes it
        self.assertNotIn('show-and-tell', it['labels'])
        self.assertEqual(it['state'], 'closed')
        self.assertTrue(it['comments'][-1][1].startswith('Show-and-tell: no \u2014 Miguel'))
        self.assertIn('Why: Not needed', it['comments'][-1][1])
        self.assertEqual(r['decision'], 'no')

    def test_only_the_decider(self):
        self._item(63, 'defleur-agents')   # Archimedes filed it: James decides
        with self.assertRaises(S.Problem) as e:
            S.decide('m', {'repo': 'wizard-ux', 'number': 63, 'decision': 'yes'})
        self.assertEqual((e.exception.code, e.exception.reason), (403, 'not_decider'))
        self.assertIn('show-and-tell', GH.issues[63]['labels'])
        S.decide('j', {'repo': 'wizard-ux', 'number': 63, 'decision': 'no'})
        self.assertIn('dropped', GH.issues[63]['labels'])

    def test_core_is_james_only(self):
        reset()   # wizard-ux is core again
        people()
        self._item(64, 'mistermizel')
        with self.assertRaises(S.Problem):
            S.decide('m', {'repo': 'wizard-ux', 'number': 64, 'decision': 'yes'})
        S.decide('j', {'repo': 'wizard-ux', 'number': 64, 'decision': 'yes'})
        self.assertIn('switch-default', GH.issues[64]['labels'])

    def test_agent_needs_owner_words_and_their_person(self):
        self._item(65, 'mistermizel')
        with self.assertRaises(S.Problem):   # no owner_request
            S.CALLS['board_decide']({'issue': 'humanitylabs-org/wizard-ux#65', 'decision': 'yes'})
        r = S.CALLS['board_decide']({'issue': 'humanitylabs-org/wizard-ux#65', 'decision': 'yes', 'owner_request': 'Miguel: yes to that one'})
        self.assertTrue(r['saved'])   # the agent account here is Miguel's (default): Oscar acts for Miguel
        self.assertIn('switch-default', GH.issues[65]['labels'])
        self._item(66, 'jdefleur')
        with self.assertRaises(S.Problem) as e:
            S.CALLS['board_decide']({'issue': 'humanitylabs-org/wizard-ux#66', 'decision': 'no', 'owner_request': 'Miguel says drop it'})
        self.assertEqual(e.exception.code, 403)

    def test_not_waiting(self):
        self._item(67, 'mistermizel', labels=('feature', 'building'))
        with self.assertRaises(S.Problem) as e:
            S.decide('m', {'repo': 'wizard-ux', 'number': 67, 'decision': 'yes'})
        self.assertEqual(e.exception.code, 409)
        with self.assertRaises(S.Problem):
            S.decide('m', {'repo': 'wizard-ux', 'number': 67, 'decision': 'maybe'})


class Policy(unittest.TestCase):
    def setUp(self):
        reset()

    def test_policy_describes_show_and_tell_for_core_and_app(self):
        p = json.loads(json.dumps(S.policy()))
        r = p['builder_rules']
        ff = r['feature_flow']
        self.assertEqual((ff['core']['then'], ff['app']['then']), ('show-and-tell', 'show-and-tell'))
        self.assertEqual(ff['core']['person'], 'James')
        self.assertEqual(ff['app']['person'], 'filer')
        self.assertEqual((ff['core']['yes'], ff['app']['yes']), ('switch-default', 'switch-default'))
        self.assertEqual(ff['decide']['mcp'], 'board_decide')
        self.assertEqual(len(r['human_steps']), 2)   # 0.46.0: Pending approval + Show-and-tell
        self.assertIn('James for core repos', r['human_steps'][1])
        self.assertIn('the filer for app repos', r['human_steps'][1])
        text = json.dumps(p)
        self.assertNotIn('No person in the loop', text)
        self.assertNotIn('core-repo features, James)', text)
        show = next(s for s in S.steps_for('features') if s['key'] == 'show')
        self.assertIsNone(show['only'])
        self.assertIn('the person who filed it', show['about'])

    def test_tool_descriptions(self):
        tools = {t['name']: t['description'] for t in S.TOOLS}
        self.assertIn('board_decide', tools)
        self.assertIn('decisions_list', tools)
        self.assertNotIn('closed automatically; core-repo', tools['board_report_feature'])
        self.assertIn('the person who filed it for app features', tools['board_report_feature'])
        self.assertIn('board_decide', S.CALLS)


class Page(unittest.TestCase):
    def test_decide_on_the_card(self):   # 0.45.0: Your decisions is gone; Approve / Decline on the card call api/decide
        html = (ROOT / 'web' / 'index.html').read_text()
        self.assertNotIn('id="decide"', html)
        self.assertIn("api('api/decide'", JS)

    def test_node_check(self):
        if not shutil.which('node'):
            self.skipTest('node missing')
        subprocess.run(['node', '--check', str(ROOT / 'web' / 'app.js')], check=True)


if __name__ == '__main__':
    unittest.main()
