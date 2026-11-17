"""0.37.0 (Miguel, 17 Nov): UX tweaks are features with a fast lane for policy ux_tweakers (Robert)."""
import os, sys, unittest
from unittest import mock
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))
import server as s


class UxTweak(unittest.TestCase):
    def test_policy_default_robert(self):
        base = s.policy_base()
        self.assertEqual(base['ux_tweakers'], ['Robert'])
        self.assertTrue(s.can_ux_tweak('hacalastudio', base))
        for who in ('jdefleur', 'mistermizel', 'oscarhenrycollins', 'JanMesaric', 'stranger', ''):
            self.assertFalse(s.can_ux_tweak(who, base), who)

    def test_lane_refuses_others(self):
        with self.assertRaises(s.Problem) as e:
            s.ux_lane({'login': 'jdefleur'}, {'ux_tweak': True})
        self.assertEqual(e.exception.status if hasattr(e.exception, 'status') else 403, 403)
        self.assertIn('Only Robert', str(e.exception.message if hasattr(e.exception, 'message') else e.exception))

    def test_lane_labels_for_robert(self):
        extra, line = s.ux_lane({'login': 'hacalastudio'}, {'ux_tweak': True})
        self.assertEqual(extra, ['ux-tweak', 'james-approved'])
        self.assertIn('UX tweak from Robert', line)
        self.assertEqual(s.ux_lane({'login': 'jdefleur'}, {}), ([], ''))

    def test_report_feature_files_approved(self):
        made = {}
        def create(acct, full, title, body, label):
            made.update(full=full, body=body, labels=label); return {'labels': label}
        with mock.patch.object(s, 'account_for', return_value=('k', {'login': 'hacalastudio', 'token': 't'})), \
             mock.patch.object(s, '_create', side_effect=create), mock.patch.object(s, '_ensure_label'), \
             mock.patch.object(s, 'settings', return_value={'org': 'humanitylabs-org'}):
            s.report_feature('robert', {'repo': 'wizard-ux', 'title': 'Tighter chat padding', 'ux_tweak': True})
        self.assertEqual(made['labels'], ['feature', 'ux-tweak', 'james-approved'])
        # a core feature carrying james-approved is Queued for the builder, not Waiting for approval
        self.assertEqual(s.item_group('humanitylabs-org/wizard-ux', made['labels']), 'queued')

    def test_mcp_schema_has_flag(self):
        names = {t['name']: t for t in s.TOOLS}
        for n in ('board_report_feature', 'report_or_request'):
            self.assertIn('ux_tweak', names[n]['inputSchema']['properties'])


if __name__ == '__main__':
    unittest.main()
