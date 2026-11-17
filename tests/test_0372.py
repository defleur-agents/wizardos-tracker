"""0.37.2: an app the WizardOS release pins is judged by the release, never offered a Store update."""
import unittest
from test_013 import S


class ReleasePinned(unittest.TestCase):
    def setUp(self):
        self.saved = (S.contains, S.code_commit, S.release_manifest, S.release_pointer, S.store_listing)
        order = ['a', 'b', 'c']
        S.code_commit = lambda t, repo, c: c
        S.contains = lambda t, repo, sha, ref: order.index(sha) <= order.index(ref)
        rel = {'1': {'default_apps': {'claude': {'app': 'wizard-claude', 'repo': 'o/claude-connection', 'commit': 'a' * 0 + 'a'}}},
               '2': {'default_apps': {'claude': {'app': 'wizard-claude', 'repo': 'o/claude-connection', 'commit': 'b'}}}}
        S.SHA40_saved = S.SHA40
        S.SHA40 = __import__('re').compile(r'^[a-c]$')
        S.release_manifest = lambda t, v: rel.get(v)
        S.release_pointer = lambda t, n: '2'
        S.store_listing = lambda repo: self.fail('a release-pinned app must not consult the Store')

    def tearDown(self):
        (S.contains, S.code_commit, S.release_manifest, S.release_pointer, S.store_listing) = self.saved
        S.SHA40 = S.SHA40_saved

    def test_pinned_app(self):
        d = {'repo': 'o/claude-connection', 'sha': 'b'}
        self.assertEqual(S.where('t', d, {'release': '1', 'channel': 'latest'}), ('no', 'Update WizardOS in Settings', 'wizard-claude'))
        self.assertEqual(S.where('t', d, {'release': '2', 'channel': 'latest'}), ('yes', None, 'wizard-claude'))
        d2 = {'repo': 'o/claude-connection', 'sha': 'c'}
        self.assertEqual(S.where('t', d2, {'release': '2', 'channel': 'latest'}), ('no', 'Not released yet', 'wizard-claude'))

    def test_page_marks_system_apps_pinned(self):
        js = open(__import__('os').path.join(__import__('os').path.dirname(__file__), '..', 'web', 'app.js')).read()
        self.assertIn('WITH_OS.has(w.id) || !!w.system', js)
        self.assertIn('async function onBox(', js)


if __name__ == '__main__':
    unittest.main()
