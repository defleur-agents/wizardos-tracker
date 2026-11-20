"""0.42.0 (Miguel, 20 Nov 2026): answer the builder and approve its blocked PR without leaving the Tracker (reply box on
the item sheet, Approve PR #N on Needs an answer items, board_approve_pr). Run: python3 -m unittest discover -s tests"""
import functools
import http.server
import json
import os
import shutil
import subprocess
import threading
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault('DATA_DIR', tempfile.mkdtemp(prefix='tracker-0420-'))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'app'))
import server as S  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
JS = (ROOT / 'web/app.js').read_text()
HTML = (ROOT / 'web/index.html').read_text()
ISSUE = 'humanitylabs-org/wizard-ux'
ASK = ('@mistermizel the next slice is ready and green, but GitHub won\'t let me merge it: "New changes require approval from '
       'someone other than the last pusher". PR https://github.com/humanitylabs-org/wizard-ux/pull/1571 closes the last gap. '
       'Options: (a) recommended: approve PR #1571 and I\'ll merge it?')


class Fake:
    """Stubs GitHub and the account for one test; records every write."""
    def __init__(self, login='mistermizel', labels=('feature', 'builder:blocked'), state='open', pr_state='open',
                 pr_author='wizardos-builder[bot]', comments=None, linked=(), review_state='APPROVED', comment_fails=False):
        self.login, self.writes = login, []
        self.cur = {'state': state, 'labels': [{'name': x} for x in labels], 'user': {'login': 'mistermizel'}}
        self.node = {'body': 'Two systems for trying changes.', 'prs': list(linked),
                     'comment_list': comments if comments is not None else [{'author': 'wizardos-builder', 'body': ASK}]}
        self.pr = {'state': pr_state, 'merged_at': None, 'title': 'Skins are look only', 'draft': False,
                   'html_url': 'https://github.com/humanitylabs-org/wizard-ux/pull/1571', 'user': {'login': pr_author},
                   'base': {'repo': {'full_name': ISSUE}}}
        self.review_state, self.comment_fails = review_state, comment_fails

    def gh(self, token, method, path, body=None, **kw):
        if method == 'GET' and '/pulls/' in path:
            return self.pr
        if method == 'POST' and path.endswith('/reviews'):
            self.writes.append(('review', path, body))
            return {'state': self.review_state, 'html_url': 'https://github.com/r#review'}
        if method == 'POST' and path.endswith('/comments'):
            if self.comment_fails:
                raise S.Problem(403, 'Your GitHub token cannot do that here.')
            self.writes.append(('comment', path, body))
            self.last = body['body']
            return {'id': 9}
        if method == 'GET' and '/issues/comments/' in path:
            return {'body': self.last, 'html_url': 'https://github.com/c#9'}
        raise AssertionError(f'unexpected {method} {path}')

    def __enter__(self):
        self.saved = (S.account_for, S._current, S._read_issue, S.gh, S._forget)
        S.account_for = lambda person=None, agent=False: ('k', {'token': 't', 'login': self.login})
        S._current = lambda acct, full, n: self.cur
        S._read_issue = lambda acct, full, n, fresh: self.node
        S.gh = self.gh
        S._forget = lambda token: None
        return self

    def __exit__(self, *a):
        S.account_for, S._current, S._read_issue, S.gh, S._forget = self.saved


class ApprovePr(unittest.TestCase):
    def test_lists_the_pr_the_builder_asks_about(self):
        with Fake() as f:
            prs = S.answer_prs({'token': 't', 'login': 'mistermizel'}, ISSUE, 1190)
        self.assertEqual([(p['repo'], p['number'], p['asked'], p['mine']) for p in prs], [(ISSUE, 1571, True, False)])

    def test_linked_prs_count_too_and_closed_ones_do_not(self):
        linked = [{'number': 1571, 'repo': ISSUE, 'state': 'open'}, {'number': 1500, 'repo': ISSUE, 'state': 'merged'}]
        with Fake(comments=[{'author': 'wizardos-builder', 'body': 'Which colour?'}], linked=linked):
            prs = S.answer_prs({'token': 't', 'login': 'x'}, ISSUE, 1190)
        self.assertEqual([p['number'] for p in prs], [1571])
        with Fake(pr_state='closed'):
            self.assertEqual(S.answer_prs({'token': 't', 'login': 'x'}, ISSUE, 1190), [])

    def test_only_items_waiting_on_an_answer(self):
        with Fake(labels=('feature',)):
            self.assertEqual(S.answer_prs({'token': 't', 'login': 'x'}, ISSUE, 1190), [])
            with self.assertRaises(S.Problem) as e:
                S.approve_pr('k', {'repo': ISSUE, 'number': 1190, 'pr': 1571})
            self.assertEqual(e.exception.code, 409)

    def test_approve_reviews_as_you_then_comments(self):
        with Fake() as f:
            out = S.approve_pr('k', {'repo': ISSUE, 'number': 1190, 'pr': 1571})
        self.assertTrue(out['approved'])
        self.assertIsNone(out['warning'])
        kind, path, body = f.writes[0]
        self.assertEqual((kind, path, body), ('review', f'/repos/{ISSUE}/pulls/1571/reviews', {'event': 'APPROVE', 'body': 'Approved in WizardOS Tracker'}))
        self.assertEqual(f.writes[1][0], 'comment')
        self.assertEqual(f.writes[1][1], f'/repos/{ISSUE}/issues/1190/comments')
        self.assertIn('Approved PR #1571', f.writes[1][2]['body'])

    def test_pr_by_url_and_unlinked_pr_refused(self):
        with Fake() as f:
            out = S.approve_pr('k', {'issue': f'{ISSUE}#1190', 'pr': 'https://github.com/humanitylabs-org/wizard-ux/pull/1571'})
            self.assertTrue(out['approved'])
            with self.assertRaises(S.Problem) as e:
                S.approve_pr('k', {'repo': ISSUE, 'number': 1190, 'pr': 999})
            self.assertEqual(e.exception.code, 409)

    def test_own_pr_and_a_refused_review(self):
        with Fake(pr_author='mistermizel'):
            with self.assertRaises(S.Problem) as e:
                S.approve_pr('k', {'repo': ISSUE, 'number': 1190, 'pr': 1571})
            self.assertEqual(e.exception.reason, 'own_pr')
        with Fake(review_state='PENDING') as f:
            with self.assertRaises(S.Problem):
                S.approve_pr('k', {'repo': ISSUE, 'number': 1190, 'pr': 1571})
            self.assertEqual([w[0] for w in f.writes], ['review'])    # no 'approved' comment when it did not approve

    def test_approved_but_comment_failed_says_so(self):
        with Fake(comment_fails=True):
            out = S.approve_pr('k', {'repo': ISSUE, 'number': 1190, 'pr': 1571})
        self.assertTrue(out['approved'])
        self.assertIn('did not save', out['warning'])

    def test_agents_need_a_humans_words(self):
        with Fake():
            with self.assertRaises(S.Problem) as e:
                S.CALLS['board_approve_pr']({'issue': f'{ISSUE}#1190', 'pr': 1571})
            self.assertEqual(e.exception.code, 403)
            out = S.CALLS['board_approve_pr']({'issue': f'{ISSUE}#1190', 'pr': 1571, 'owner_request': 'Miguel: approve PR 1571 please'})
            self.assertTrue(out['approved'])
        tool = next(t for t in S.TOOLS if t['name'] == 'board_approve_pr')
        self.assertIn('owner_request', tool['inputSchema']['required'])

    def test_answered_after_a_team_reply(self):
        rows = [('wizardos-builder', ASK)]
        self.assertFalse(S.answered_after(rows, 0))
        self.assertTrue(S.answered_after(rows + [('mistermizel', 'Approved PR #1571 in the WizardOS Tracker.')], 0))
        self.assertFalse(S.answered_after(rows + [('wizardos-builder[bot]', 'still waiting')], 0))
        self.assertFalse(S.answered_after(rows, None))

    def test_route_and_openapi(self):
        src = (ROOT / 'app/server.py').read_text()
        self.assertIn("'/api/pr/approve': lambda: approve_pr(who, body)", src)
        self.assertIn('/api/pr/approve', json.loads((ROOT / 'openapi.json').read_text())['paths'])
        self.assertGreaterEqual(tuple(map(int, S.VERSION.split('.'))), (0, 42, 0))
        self.assertIn(f"const PAGE_VERSION = '{S.VERSION}'", JS)


class Page(unittest.TestCase):
    def test_reply_box_on_every_item_sheet(self):
        for x in ('id="d-reply"', 'id="d-reply-t"', 'id="d-reply-go"', 'id="d-approve"'):
            self.assertIn(x, HTML)
        self.assertLess(HTML.index('id="d-comments"'), HTML.index('id="d-reply"'))
        self.assertIn("'Answer the builder'", JS)
        self.assertIn("api('api/issue/comment', { repo: i.repo, number: i.number, body: text })", JS)

    def test_reply_shows_before_the_request_and_retries(self):
        sub = JS[JS.index("el('d-reply').addEventListener('submit'"):]
        sub = sub[:sub.index('});')]
        self.assertLess(sub.index('pendingComment(text)'), sub.index('sendReply('))
        send = JS[JS.index('async function sendReply'):JS.index('function replyBox')]
        self.assertLess(send.index('markAnswered(i.id, true)'), send.index('await api('))
        self.assertIn("smallBtn('Retry'", send)

    def test_approve_button(self):
        self.assertIn('`Approve PR #${p.number}`', JS)
        body = JS[JS.index('async function approvePr'):]
        self.assertLess(body.index('busyOn(b)'), body.index('await api('))
        self.assertIn("api('api/pr/approve', { repo: d.repo, number: d.number, pr: p.number, pr_repo: p.repo })", body)
        self.assertIn("smallBtn('Retry'", body[:body.index('\n}\n')])


CHROME = next((shutil.which(b) for b in ('chromium', 'chromium-browser', 'google-chrome') if shutil.which(b)), None)


@unittest.skipUnless(shutil.which('node') and CHROME, 'node or chromium missing')
class Rendered(unittest.TestCase):
    """The real page with GitHub stubbed (tests/fixture_0420.js)."""
    @classmethod
    def setUpClass(cls):
        handler = functools.partial(type('Q', (http.server.SimpleHTTPRequestHandler,), {'log_message': lambda *a: None}),
                                    directory=str(ROOT / 'web'))
        cls.httpd = http.server.ThreadingHTTPServer(('127.0.0.1', 0), handler)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        url = f'http://127.0.0.1:{cls.httpd.server_address[1]}/index.html'
        p = subprocess.run(['node', str(ROOT / 'tests' / 'cdp_eval.mjs'), CHROME, url, str(ROOT / 'tests' / 'fixture_0420.js')],
                           capture_output=True, text=True, timeout=90)
        if p.returncode:
            raise AssertionError(p.stderr or p.stdout)
        cls.out = json.loads(p.stdout.strip().splitlines()[-1])

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()

    def test_box_and_button_show_on_an_answer_item(self):
        o = self.out
        self.assertEqual(o['reply'], {'shown': True, 'label': 'Answer the builder', 'sendOff': True})
        self.assertTrue(o['sendOn'])
        self.assertTrue(o['approve']['shown'])
        self.assertEqual(o['approve']['buttons'], ['Approve PR #1571'])

    def test_send_shows_at_once_then_retry_after_a_failure(self):
        o = self.out
        self.assertTrue(o['immediate']['pending'] and o['immediate']['answered'], o['immediate'])
        self.assertIn('Yes, go with option (a).', o['immediate']['text'])
        self.assertEqual(o['immediate']['box'], '')
        self.assertTrue(o['immediate']['line'].startswith('Answered'))
        self.assertTrue(o['failed']['unsent'] and o['failed']['retry'] and not o['failed']['answered'], o['failed'])
        self.assertIn('Not sent: Your GitHub token cannot do that here.', o['failed']['text'])
        self.assertFalse(o['retried']['unsent'] or o['retried']['pending'])
        self.assertTrue(o['retried']['answered'])

    def test_approve_confirms_then_approves(self):
        o = self.out
        self.assertIn('Approve PR #1571 on GitHub as mistermizel?', o['confirm'])
        self.assertTrue(o['approveBusy'])
        self.assertIn('PR #1571 approved', o['approved'])
        self.assertEqual([c[0] for c in o['calls']], ['api/issue/comment', 'api/issue/comment', 'api/pr/approve'])
        self.assertEqual(o['calls'][2][1], {'repo': ISSUE, 'number': 1190, 'pr': 1571, 'pr_repo': ISSUE})


if __name__ == '__main__':
    unittest.main()
