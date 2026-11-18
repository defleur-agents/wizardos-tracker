"""0.39.1 (James, Archimedes, 18 Nov): the Tracker can no longer drain its user's GitHub budget.
The immutable release answers survive a restart (DATA_DIR/private/forever.json), a spent budget fails fast without a
request until GitHub's reset, the warm-up sits out a low budget, and a restart loop waits longer before warming up.
GitHub is a local mock server. Run: python3 -m unittest discover -s tests"""
import json
import os
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

os.environ.setdefault('DATA_DIR', tempfile.mkdtemp(prefix='tracker-0391-'))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'app'))
import server as S  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


class Mock(BaseHTTPRequestHandler):
    """Answers every path with Mock.answer = (status, headers, body); counts requests per path."""
    answer = (200, {}, {})
    hits = []

    def log_message(self, *a):
        pass

    def _go(self):
        Mock.hits.append(self.path)
        code, headers, body = Mock.answer
        b = json.dumps(body).encode()
        self.send_response(code)
        for k, v in headers.items():
            self.send_header(k, str(v))
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    do_GET = do_POST = _go


SRV = ThreadingHTTPServer(('127.0.0.1', 0), Mock)
threading.Thread(target=SRV.serve_forever, daemon=True).start()
BASE = f'http://127.0.0.1:{SRV.server_address[1]}'
TOK, OTHER = 'tok_james_budget_aaaaaaaaaaaaaaaa', 'tok_miguel_budget_aaaaaaaaaaaaaaa'


class Isolated(unittest.TestCase):
    def setUp(self):
        self.saved = (S.GITHUB, S.PRIVATE)
        S.GITHUB, S.PRIVATE = BASE, Path(tempfile.mkdtemp(prefix='tracker-0391-priv-'))
        S._limits.clear()
        S._cache.clear()
        S._forever.clear()
        S._forever_state.update(dirty=False, saved=0.0)
        Mock.hits, Mock.answer = [], (200, {}, {})

    def tearDown(self):
        S.GITHUB, S.PRIVATE = self.saved
        S._limits.clear()
        S._cache.clear()
        S._forever.clear()


class RateLimitGuard(Isolated):
    def test_spent_budget_fails_fast_until_reset_and_says_when(self):
        reset = int(time.time()) + 720
        Mock.answer = (403, {'X-RateLimit-Remaining': 0, 'X-RateLimit-Reset': reset, 'X-RateLimit-Resource': 'core'},
                       {'message': 'API rate limit exceeded for user ID 1.'})
        with self.assertRaises(S.Problem) as e:
            S.gh(TOK, 'GET', '/repos/o/r/compare/a...b')
        self.assertEqual((e.exception.code, e.exception.reason), (429, 'rate_limited'))
        self.assertEqual(e.exception.message, 'GitHub limit reached; back in 12 minutes.')
        Mock.answer = (200, {}, {'status': 'ahead'})   # GitHub would answer now, but the Tracker must not ask
        for path in ('/repos/o/r/compare/c...d', '/repos/o/r/contents/x', '/orgs/o/repos'):
            with self.assertRaises(S.Problem) as e:
                S.gh(TOK, 'GET', path)
            self.assertEqual(e.exception.code, 429)
            self.assertIn('back in 12 minutes', e.exception.message)
        self.assertEqual(len(Mock.hits), 1, 'no request after the limit')
        self.assertFalse(S.budget_ok(TOK))
        # another person's token has its own budget
        self.assertEqual(S.gh(OTHER, 'GET', '/repos/o/r/compare/c...d'), {'status': 'ahead'})
        self.assertEqual(len(Mock.hits), 2)

    def test_last_allowed_call_blocks_the_next(self):
        Mock.answer = (200, {'X-RateLimit-Remaining': 0, 'X-RateLimit-Reset': int(time.time()) + 300}, {'ok': 1})
        self.assertEqual(S.gh(TOK, 'GET', '/user', cache=False), {'ok': 1})
        with self.assertRaises(S.Problem) as e:
            S.gh(TOK, 'GET', '/user', cache=False)
        self.assertEqual(e.exception.message, 'GitHub limit reached; back in 5 minutes.')
        self.assertEqual(len(Mock.hits), 1)

    def test_retry_after_and_secondary_limits(self):
        Mock.answer = (429, {'Retry-After': 30}, {'message': 'slow down'})
        with self.assertRaises(S.Problem) as e:
            S.gh(TOK, 'GET', '/a')
        self.assertEqual(e.exception.message, 'GitHub limit reached; back in a minute.')
        self.assertTrue(25 < S._rate_wait(S._tid(TOK), 'core') <= 30)
        S._limits.clear()
        Mock.answer = (403, {}, {'message': 'You have exceeded a secondary rate limit. Please wait a few minutes.'})
        with self.assertRaises(S.Problem):
            S.gh(TOK, 'GET', '/b')
        self.assertTrue(55 < S._rate_wait(S._tid(TOK), 'core') <= S.RATE_SECONDARY)
        with self.assertRaises(S.Problem):
            S.gh(TOK, 'GET', '/c')
        self.assertEqual(Mock.hits, ['/a', '/b'])

    def test_budgets_are_separate_search_graphql_core(self):
        Mock.answer = (403, {'X-RateLimit-Remaining': 0, 'X-RateLimit-Reset': int(time.time()) + 50, 'X-RateLimit-Resource': 'search'},
                       {'message': 'API rate limit exceeded'})
        with self.assertRaises(S.Problem):
            S.gh(TOK, 'GET', '/search/issues?q=x')
        Mock.answer = (200, {'X-RateLimit-Remaining': 4000, 'X-RateLimit-Reset': int(time.time()) + 50}, {'fine': True})
        self.assertEqual(S.gh(TOK, 'GET', '/repos/o/r'), {'fine': True})
        with self.assertRaises(S.Problem):
            S.gh(TOK, 'GET', '/search/issues?q=y')
        self.assertTrue(S.budget_ok(TOK))

    def test_another_budget_never_stands_in_for_core(self):
        """0.39.2: an answer counted against another budget keeps its own row."""
        Mock.answer = (200, {'X-RateLimit-Remaining': 900, 'X-RateLimit-Reset': int(time.time()) + 900, 'X-RateLimit-Resource': 'core'}, {})
        S.gh(TOK, 'GET', '/repos/o/r', cache=False)
        Mock.answer = (200, {'X-RateLimit-Remaining': 5000, 'X-RateLimit-Reset': int(time.time()) + 3600, 'X-RateLimit-Resource': 'integration_manifest'}, {})
        S.gh(TOK, 'GET', '/repos/o/r/x', cache=False)
        self.assertEqual(S.budget_of(TOK)['core']['remaining'], 900)
        self.assertEqual(S.budget_of(TOK)['integration_manifest']['remaining'], 5000)
        self.assertFalse(S.budget_ok(TOK))
        # a refusal on a named budget also stops the calls of this kind
        Mock.answer = (403, {'X-RateLimit-Remaining': 0, 'X-RateLimit-Reset': int(time.time()) + 120, 'X-RateLimit-Resource': 'code_search'},
                       {'message': 'API rate limit exceeded'})
        with self.assertRaises(S.Problem):
            S.gh(TOK, 'GET', '/search/code?q=x')
        n = len(Mock.hits)
        with self.assertRaises(S.Problem):
            S.gh(TOK, 'GET', '/search/code?q=y')
        self.assertEqual(len(Mock.hits), n)
        S._limits.clear()
        S._limits_load()
        self.assertTrue(S._rate_wait(S._tid(TOK), 'code_search') > 0, 'kept across a restart under its own name')

    def test_graphql_rate_limited_answer_blocks_graphql(self):
        Mock.answer = (200, {'X-RateLimit-Remaining': 0, 'X-RateLimit-Reset': int(time.time()) + 600, 'X-RateLimit-Resource': 'graphql'},
                       {'errors': [{'type': 'RATE_LIMITED', 'message': 'API rate limit exceeded'}]})
        with self.assertRaises(S.Problem) as e:
            S.gh(TOK, 'GRAPHQL', '/graphql', {'query': 'q'})
        self.assertEqual(e.exception.code, 429)
        with self.assertRaises(S.Problem):
            S.gh(TOK, 'GRAPHQL', '/graphql', {'query': 'other'})
        self.assertEqual(len(Mock.hits), 1)

    def test_a_running_limit_carries_over_a_restart(self):
        Mock.answer = (403, {'X-RateLimit-Remaining': 0, 'X-RateLimit-Reset': int(time.time()) + 900}, {'message': 'API rate limit exceeded'})
        with self.assertRaises(S.Problem):
            S.gh(TOK, 'GET', '/x')
        kept = (S.PRIVATE / 'github_limits.json').read_text()
        self.assertNotIn(TOK, kept, 'never a token on disk')
        S._limits.clear()   # the restart
        S._limits_load()
        with self.assertRaises(S.Problem) as e:
            S.gh(TOK, 'GET', '/y')
        self.assertIn('back in 15 minutes', e.exception.message)
        self.assertEqual(Mock.hits, ['/x'])

    def test_low_budget_skips_the_warm_up_round(self):
        S._write('accounts.json', {'people': {'owner': {'token': TOK, 'login': 'jdefleur'}}, 'default': 'owner'})
        asked = []
        real = S.done_list
        S.done_list = lambda key, args: asked.append(args['view'])
        try:
            Mock.answer = (200, {'X-RateLimit-Remaining': 999, 'X-RateLimit-Reset': int(time.time()) + 1800}, {})
            S.gh(TOK, 'GET', '/user', cache=False)
            self.assertFalse(S.budget_ok(TOK))
            self.assertFalse(S._warm_round())
            self.assertEqual(asked, [])
            Mock.answer = (200, {'X-RateLimit-Remaining': 4500, 'X-RateLimit-Reset': int(time.time()) + 1800}, {})
            S.gh(TOK, 'GET', '/user', cache=False)
            self.assertTrue(S._warm_round())
            self.assertEqual(asked, ['bugs', 'apps', 'core'])
            # a budget whose reset has passed is fresh again
            S._limits[(S._tid(TOK), 'core')] = {'remaining': 3, 'reset': int(time.time()) - 5, 'until': 0}
            self.assertTrue(S.budget_ok(TOK))
        finally:
            S.done_list = real
        self.assertEqual(S.budget_of(TOK)['core']['remaining'], 3)


class BoundedCache(Isolated):
    def test_big_answers_are_not_kept(self):
        Mock.answer = (200, {}, {'blob': 'x' * (S.CACHE_ITEM_MAX + 10)})
        S.gh(TOK, 'GET', '/big')
        S.gh(TOK, 'GET', '/big')
        self.assertEqual(Mock.hits, ['/big', '/big'])
        Mock.answer = (200, {}, {'small': 1})
        S.gh(TOK, 'GET', '/small')
        S.gh(TOK, 'GET', '/small')
        self.assertEqual(Mock.hits.count('/small'), 1)

    def test_total_bytes_are_capped(self):
        Mock.answer = (200, {}, {'blob': 'y' * (400 * 1024)})
        for i in range(40):   # 40 x 400 KB = 16 MB asked, at most 8 MB kept
            S.gh(TOK, 'GET', f'/page/{i}')
        self.assertLessEqual(sum(e[2] for e in S._cache.values()), S.CACHE_MAX_BYTES)
        self.assertIn((S._tid(TOK), 'GET', BASE + '/page/39', '', 'application/vnd.github+json'), S._cache, 'newest kept')

    def test_compare_asks_for_the_status_only(self):
        Mock.answer = (200, {}, {'status': 'ahead'})
        self.assertTrue(S.contains(TOK, 'o/r', 'a' * 40, 'b' * 40))
        self.assertIn('page=100', Mock.hits[0], 'a page past the commits: no files, no commits')


class KeptAnswers(Isolated):
    def test_immutable_answers_survive_a_restart(self):
        Mock.answer = (200, {}, {'status': 'ahead'})
        sha, build = 'a' * 40, 'b' * 40
        self.assertTrue(S.contains(TOK, 'o/r', sha, build))
        S._forever_save(force=True)   # the first new answer is written at once; later ones within a minute
        self.assertTrue((S.PRIVATE / 'forever.json').is_file())
        S._forever.clear()   # the restart
        S._cache.clear()
        self.assertEqual(S._forever_load(), 1)
        Mock.answer = (500, {}, {'message': 'must not be asked'})
        self.assertTrue(S.contains(TOK, 'o/r', sha, build))
        self.assertEqual(len(Mock.hits), 1, 'the compare is not asked again after the restart')
        mode = (S.PRIVATE / 'forever.json').stat().st_mode & 0o777
        self.assertEqual(mode, 0o600)

    def test_not_there_answers_and_big_ones_stay_in_memory_only_and_the_file_is_bounded(self):
        S._forever[('cmp', 'o/r', 'x', 'y')] = None
        S._forever[('rel', 'huge')] = {'blob': 'z' * (S.FOREVER_ITEM_MAX + 1)}
        for i in range(300):
            S._forever[('ver', 'o/r', f'1.{i}')] = 'c' * 40 + 'p' * 200
        S._forever_state['dirty'] = True
        real = S.FOREVER_MAX_BYTES
        S.FOREVER_MAX_BYTES = 20_000
        try:
            S._forever_save(force=True)
        finally:
            S.FOREVER_MAX_BYTES = real
        rows = json.loads((S.PRIVATE / 'forever.json').read_text())
        keys = [tuple(r[0]) for r in rows]
        self.assertNotIn(('cmp', 'o/r', 'x', 'y'), keys)
        self.assertNotIn(('rel', 'huge'), keys)
        self.assertLess(len(json.dumps(rows)), 21_000)
        self.assertIn(('ver', 'o/r', '1.299'), keys, 'the newest are kept')
        self.assertNotIn(('ver', 'o/r', '1.0'), keys)

    def test_saving_is_throttled_and_a_broken_file_is_ignored(self):
        S._forever[('img', 'o/r', 'q')] = 'w'
        S._forever_state['dirty'] = True
        self.assertTrue(S._forever_save())
        S._forever[('img', 'o/r', 'q2')] = 'w'
        S._forever_state['dirty'] = True
        self.assertFalse(S._forever_save(), 'at most once a minute unless forced')
        (S.PRIVATE / 'forever.json').write_text('{not json')
        S._forever.clear()
        self.assertEqual(S._forever_load(), 0)

    def test_a_limited_lookup_is_not_remembered(self):
        Mock.answer = (403, {'X-RateLimit-Remaining': 0, 'X-RateLimit-Reset': int(time.time()) + 60}, {'message': 'API rate limit exceeded'})
        self.assertIsNone(S.contains(TOK, 'o/r', 'a' * 40, 'b' * 40))
        self.assertNotIn(('cmp', 'o/r', 'a' * 40, 'b' * 40), S._forever)
        S._timed[('ptr', 'stable')] = (time.time() - 10_000, '0.3.1')
        self.assertEqual(S.release_pointer(TOK, 'stable'), '0.3.1', 'limited: the last answer stands')
        S._timed.pop(('ptr', 'stable'), None)


class CrashLoop(Isolated):
    def test_quick_restarts_wait_longer_before_warming_up(self):
        t = 1_800_000_000
        self.assertEqual(S._warm_delay(t), S.WARM_FIRST)              # first start
        self.assertEqual(S._warm_delay(t + 70), 120)                  # OOM restart 70 s later
        self.assertEqual(S._warm_delay(t + 140), 240)
        self.assertEqual(S._warm_delay(t + 210), 480)
        self.assertEqual(S._warm_delay(t + 280), 960)
        self.assertEqual(S._warm_delay(t + 350), S.WARM_BACKOFF_MAX)
        self.assertEqual(S._warm_delay(t + 420), S.WARM_BACKOFF_MAX)
        self.assertEqual(S._warm_delay(t + 420 + S.WARM_RESTART_WINDOW + 1), S.WARM_FIRST)   # a normal restart later
        self.assertEqual(json.loads((S.PRIVATE / 'starts.json').read_text())['streak'], 0)

    def test_warm_up_thread_sleeps_the_delay_first(self):
        S._write('starts.json', {'last': int(time.time()) - 30, 'streak': 0})
        slept = []
        S._warm_releases(sleep=slept.append, rounds=1)
        self.assertEqual(slept, [120, S.WARM_EVERY])


class Recipe(unittest.TestCase):
    def test_compose_has_512m_and_no_extra_swap(self):
        import yaml
        svc = next(iter(yaml.safe_load((ROOT / 'runtipi/docker-compose.yml').read_text())['services'].values()))
        self.assertEqual((svc['mem_limit'], svc['memswap_limit']), ('512m', '512m'))


if __name__ == '__main__':
    unittest.main()
