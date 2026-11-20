"""0.41.1 (Miguel, 20 Nov 2026): shipped bugs with no complaint in 7 days finish (builder-tick bug sweep); the Tracker
names both sweep comments. Run: python3 -m unittest discover -s tests"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault('DATA_DIR', tempfile.mkdtemp(prefix='tracker-0411-'))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'app'))
import server as S  # noqa: E402


def node(*comments, closer='wizardos-builder[bot]'):
    return {'comments': {'nodes': [{'author': {'login': who}, 'body': b} for who, b in comments]}, 'closedAt': '2026-11-20T06:00:00Z',
            'stateReason': 'COMPLETED', 'closer': {'nodes': [{'actor': {'login': closer}}]}}


class Swept(unittest.TestCase):
    def test_policy_accept_time_is_seven_days(self):
        flow = S.policy()['builder_rules']['bug_flow']
        self.assertEqual(flow['auto_accept_seconds'], 7 * 86400)   # builder-tick reads this
        self.assertGreaterEqual(tuple(map(int, S.VERSION.split('.'))), (0, 41, 1))

    def test_new_sweep_comment_reads_checked_7_days(self):
        n = node(('wizardos-builder[bot]', "Checked (no problems in 7 days): this fix shipped 7+ days ago and nobody said it "
                                           "still does not work, so it is closed as fixed."))
        self.assertEqual(S.checked_of(n)['text'], 'Checked (no problems in 7 days)')

    def test_old_3_day_sweep_comment_is_not_closed_on_merge(self):
        n = node(('wizardos-builder[bot]', 'Closed automatically: shipped 3+ days ago and nobody said it is still broken. '
                                           'Reopen or say Still broken if it is.'))
        self.assertEqual(S.checked_of(n)['text'], 'Checked (no problems in 3 days)')

    def test_people_still_win_and_plain_merges_stay(self):
        n = node(('wizardos-builder[bot]', 'Checked (no problems in 7 days): x'), ('oscarhenrycollins', 'Tested: works \u2014 @jdefleur'))
        self.assertEqual(S.checked_of(n)['text'], 'Checked by James')
        self.assertEqual(S.checked_of(node(('wizardos-builder[bot]', 'Merged.')))['text'], 'Closed on merge (no human check)')
        # a person writing the words does not make it a sweep
        self.assertEqual(S.checked_of(node(('JanMesaric', 'Closed automatically: 3+ days')))['text'], 'Closed on merge (no human check)')


if __name__ == '__main__':
    unittest.main()
