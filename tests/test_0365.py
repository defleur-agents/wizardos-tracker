"""0.36.5 (Miguel, 16 Nov): a core idea still being sorted (label triage) offers Approve / Decline."""
import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))
import server as S  # noqa: E402


class SortingApproval(unittest.TestCase):
    def test_core_idea_being_sorted_can_be_approved(self):
        self.assertEqual(S.sorting_approval('core', ['feature', 'triage'], True),
                         {'sort_approve': True, 'can_james': True, 'james_rule': '', 'turn': True})

    def test_others_see_it_greyed_with_the_rule(self):
        r = S.sorting_approval('core', ['feature', 'triage'], False)
        self.assertTrue(r['sort_approve'])
        self.assertFalse(r['can_james'])
        self.assertEqual(r['james_rule'], 'Only James or Miguel can approve core features.')

    def test_already_approved_says_so(self):
        self.assertEqual(S.sorting_approval('core', ['feature', 'triage', 'james-approved'], True), {'pre_approved': True})

    def test_bugs_and_app_ideas_never_wait_for_approval(self):
        self.assertEqual(S.sorting_approval('core', ['bug', 'triage'], True), {})
        self.assertEqual(S.sorting_approval('app', ['feature', 'triage'], True), {})

    def test_page_offers_approve_while_sorting(self):
        js = open(os.path.join(os.path.dirname(__file__), '..', 'web', 'app.js')).read()
        self.assertIn("(g === 'sorting' && i.sort_approve)", js)


if __name__ == '__main__':
    unittest.main()
