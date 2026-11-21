"""0.43.0 (Miguel, 21 Nov 2026): no person tests anything. The builder's own tester (builder-verify) is the only check,
before merge; no AI review after the merge. Bugs and app features close automatically; core-repo features add James's
show-and-tell, the only human step. Run: python3 -m unittest discover -s tests"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault('DATA_DIR', tempfile.mkdtemp(prefix='tracker-0430-'))
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'app'))
import server as S  # noqa: E402

JS = (ROOT / 'web' / 'app.js').read_text()
HUMAN_TESTS = re.compile(r"(whoever filed it tries|filer'?s? (check|tries)|human (reviewer )?should try|check it when you can|"
                         r"the opener's agent checks)", re.I)


def fn(name):
    return re.search(r'^function ' + name + r'\(.*?^}', JS, re.S | re.M).group(0)


class Steps(unittest.TestCase):
    def test_bug_steps(self):
        st = S.steps_for('bugs')
        self.assertEqual([s['key'] for s in st], ['open', 'build', 'tester'])
        t = st[2]
        self.assertEqual(t['name'], 'Tester')
        self.assertEqual(t['role'], "WizardOS Builder's tester")
        self.assertFalse(t['person'])
        self.assertIn('before it merges', t['about'])
        self.assertIn('closed automatically', t['about'])
        self.assertIn('Nobody tests it by hand', t['about'])
        for s in st:
            self.assertNotRegex(s['about'] + s['next'], HUMAN_TESTS)
            self.assertNotIn('ai-review', s['about'] + s['next'])

    def test_feature_steps(self):
        st = S.steps_for('features')
        self.assertEqual([s['key'] for s in st], ['open', 'build', 'tester', 'show'])
        show = st[3]
        self.assertEqual((show['name'], show['role'], show['person'], show['only']), ('Show-and-tell', 'James', True, 'core_repos'))
        self.assertEqual(show['label'], 'show-and-tell')
        self.assertIn('the one human step', show['about'])
        self.assertIn('switched on', st[1]['about'])
        self.assertIn('off switch', st[1]['about'])
        self.assertEqual([s for s in st if s.get('person')], [show])   # the only step a person does
        for s in st:
            self.assertNotRegex(s['about'] + s['next'], HUMAN_TESTS)

    def test_goals_unchanged(self):
        self.assertEqual([s['key'] for s in S.steps_for('goals')], ['open', 'build', 'ai', 'review'])


class Policy(unittest.TestCase):
    def setUp(self):
        self.p = S.policy()

    def test_lines(self):
        text = '\n'.join(self.p['lines'])
        self.assertNotIn('Human review: the filer', text)
        self.assertNotIn("filer's check", text)
        self.assertNotIn('7 days', text)
        self.assertIn("the builder's own tester, before merge", text)
        self.assertIn('no person tests anything', text)
        self.assertIn('Show-and-tell is the only human step', text)
        self.assertIn('App features (repos outside core_repos)', text)
        self.assertTrue(any(l.startswith('Bugs (Miguel, 21 Nov)') and 'closed automatically by the builder' in l for l in self.p['lines']))
        self.assertTrue(any('builder:blocked' in l and '10 minutes' in l for l in self.p['lines']))

    def test_bug_flow(self):
        f = self.p['builder_rules']['bug_flow']
        self.assertEqual(f['hand_back'], 'ready-to-test')
        self.assertEqual(f['closed_by'], 'builder')
        self.assertIsNone(f['filer_check'])
        self.assertIsNone(f['auto_accept_seconds'])
        self.assertIsNone(f['ai_review'])
        self.assertNotIn('filer_note', f)

    def test_feature_flow_and_human_steps(self):
        r = self.p['builder_rules']
        self.assertEqual(r['feature_flow']['app']['closed_by'], 'builder')
        self.assertIsNone(r['feature_flow']['app']['person'])
        self.assertEqual(r['feature_flow']['core']['person'], 'James')
        self.assertEqual(r['feature_flow']['core']['then'], 'show-and-tell')
        self.assertEqual(r['human_steps'], ['show-and-tell (core-repo features, James)'])
        self.assertEqual(r['blocked'], {'label': 'builder:blocked', 'only_for': 'real decisions', 'recheck_seconds': 600})
        self.assertEqual(r['core_repos'], ['wizard-os', 'wizard-ux', 'wizard-app-manager', 'wizard-agent-service', 'try-wizard'])

    def test_policy_steps_match(self):
        self.assertEqual([s['key'] for s in self.p['steps']['bugs']], ['open', 'build', 'tester'])


class Tools(unittest.TestCase):
    def desc(self, name):
        return next(t for t in S.TOOLS if t['name'] == name)

    def test_no_agent_is_told_a_person_tries_it(self):
        for name in ('ai_review_pass', 'ai_review_fail', 'board_report_bug', 'board_report_feature'):
            t = self.desc(name)
            self.assertNotRegex(json.dumps(t), HUMAN_TESTS, name)
            self.assertNotIn('human reviewer should try', json.dumps(t), name)
        p = self.desc('ai_review_pass')['description']
        self.assertIn('Never ask a person to test or try anything', p)
        self.assertIn("Builder's own tester", p)
        self.assertIn('Nobody tests by hand', self.desc('board_report_feature')['description'])


class NobodysTurn(unittest.TestCase):
    def test_needs_you_never_counts_tested_items(self):
        cards = {'test': [{'id': 'a#1', 'turn': True}, {'id': 'a#2', 'turn': True, 'shipped': True}],
                 'show': [{'id': 'a#3', 'turn': True}]}
        self.assertEqual([i['id'] for i in S.needs_you_items([{'james': True, 'groups': cards}])], ['a#3'])
        self.assertEqual(S.needs_you_items([{'james': False, 'groups': cards}]), [])

    @unittest.skipUnless(shutil.which('node'), 'node missing')
    def test_my_turn_and_card_words(self):
        src = fn('myTurn') + '\n' + fn('whereLine') + """
const onboxOf = () => null, bugLine = () => ['x', ''], nextLine = () => '';
console.log(JSON.stringify([myTurn({group: 'test', can_review: true}), myTurn({group: 'show', can_james: true}),
  whereLine({group: 'test', category: 'app'})[0], whereLine({group: 'test', category: 'core'})[0], whereLine({group: 'airev'})[0]]));"""
        got = json.loads(subprocess.run(['node', '-e', src], capture_output=True, text=True, check=True).stdout)
        self.assertEqual(got, [False, True, 'Tested by the builder · it closes by itself',
                               'Tested by the builder · next: James’s show-and-tell', 'Older hand-back · the builder moves it on'])

    def test_no_check_it_todo_for_bugs(self):
        self.assertNotIn("smallBtn('Check it', () => openDetail(i, true))", JS)
        self.assertNotIn("test: 'to check it'", JS)
        self.assertNotIn("'Then ' + (i.opener || 'the filer') + ' checks it'", JS)
        self.assertNotIn('A quick sanity check by whoever filed it', JS)
        self.assertIn("smallBtn('Works'", JS)   # kept as an optional way to send it back
        self.assertIn("'Still broken'", JS)


class Bundle(unittest.TestCase):
    def test_shipped_bundle_is_this_source(self):
        # 0.43.0: the first 0.43.0 merge shipped the 0.42.0 bundle (compose not repacked); the compose's inline files
        # must equal the checked-in sources
        import base64
        import zlib
        import yaml
        cmd = yaml.safe_load((ROOT / 'runtipi' / 'docker-compose.yml').read_text())['services']['wizardos-tracker']['command']
        files = json.loads(zlib.decompress(base64.b64decode(''.join(cmd[3:]))))
        self.assertIn('app/server.py', files)
        for name, text in files.items():
            self.assertEqual(text, (ROOT / name).read_text(), name)
        self.assertTrue(all(len(x) <= 100000 for x in cmd[3:]))


class Version(unittest.TestCase):
    def test_version(self):
        self.assertEqual(S.VERSION, '0.43.0')
        self.assertIn("const PAGE_VERSION = '0.43.0'", JS)
        self.assertIn("version: '0.43.0' })", JS)
        self.assertEqual(json.loads((ROOT / 'runtipi' / 'config.json').read_text())['version'], '0.43.0')
        self.assertEqual(json.loads((ROOT / 'openapi.json').read_text())['info']['version'], '0.43.0')
        self.assertIn('**0.43.0**', (ROOT / 'wizard.md').read_text())
        self.assertIn('version: 0.43.0', (ROOT / 'skill' / 'SKILL.md').read_text())


if __name__ == '__main__':
    unittest.main()
