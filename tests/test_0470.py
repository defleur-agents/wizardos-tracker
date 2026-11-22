"""0.47.0 (Miguel, 21 Nov 2026): a show-and-tell card shows what its decider says yes or no to: the builder's pitch and its
Before / After screenshots as real pictures. The pictures sit in private repos of the team's org, so the page loads
them through GET /api/shot, which fetches only three link forms of that org with the signed-in person's token, serves
only real pictures and keeps them on the box. Run: python3 -m unittest discover -s tests"""
import http.client
import re
import shutil
import threading
import unittest
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote

from test_013 import GH, S, reset
from test_017 import people
from test_0182 import node

ROOT = Path(__file__).resolve().parent.parent
JS = (ROOT / 'web' / 'app.js').read_text()
CSS = (ROOT / 'web' / 'styles.css').read_text()
BOT = 'wizardos-builder[bot]'
SHOW = ['feature', 'show-and-tell']
PNG = b'\x89PNG\r\n\x1a\n' + b'0' * 64
MEDIA = 'https://github.com/humanitylabs-org/wizard-issue-media/blob/main/builder/wizard-app-manager/515/a-phone-04-on.png?raw=true'
RAW = 'https://raw.githubusercontent.com/humanitylabs-org/wizard-app-manager/builder/515-evidence/phone-switched_off.png'
BLOB = 'https://github.com/humanitylabs-org/wizard-notes/blob/builder/12-evidence/shots/after.jpg'


def fn(name):
    m = re.search(r'\n(?:async )?function ' + name + r'\(', JS)
    i, depth = JS.index('{', m.start()), 0
    for j in range(i, len(JS)):
        depth += {'{': 1, '}': -1}.get(JS[j], 0)
        if depth == 0:
            return JS[m.start():j + 1]


class Links(unittest.TestCase):
    def test_the_three_forms(self):
        self.assertEqual(S.shot_source(MEDIA), 'https://raw.githubusercontent.com/humanitylabs-org/wizard-issue-media/main/builder/wizard-app-manager/515/a-phone-04-on.png')
        self.assertEqual(S.shot_source(MEDIA.replace('?raw=true', '')), S.shot_source(MEDIA))
        self.assertEqual(S.shot_source(RAW), RAW)   # the ref has a slash: builder/515-evidence
        self.assertEqual(S.shot_source(BLOB), 'https://raw.githubusercontent.com/humanitylabs-org/wizard-notes/builder/12-evidence/shots/after.jpg')
        self.assertEqual(S.shot_source(BLOB + '?raw=true'), S.shot_source(BLOB))
        self.assertEqual(S.shot_source(RAW.replace('humanitylabs-org', 'HumanityLabs-Org')), RAW)   # GitHub owners ignore case

    def test_everything_else_is_refused(self):
        for u in ('https://example.com/x.png',
                  'https://raw.githubusercontent.com/torvalds/linux/master/x.png',                 # another owner
                  'https://github.com/torvalds/linux/blob/master/x.png?raw=true',
                  'http://raw.githubusercontent.com/humanitylabs-org/wizard-ux/main/x.png',          # not https
                  'https://raw.githubusercontent.com/humanitylabs-org/wizard-ux/main/../../x.png',   # ..
                  'https://raw.githubusercontent.com/humanitylabs-org/../torvalds/linux/master/x.png',
                  'https://raw.githubusercontent.com/humanitylabs-org/wizard-ux/main/%2e%2e/x.png',
                  'https://raw.githubusercontent.com/humanitylabs-org/wizard-ux/main/./x.png',
                  'https://raw.githubusercontent.com/humanitylabs-org/wizard-ux/x.png',              # no ref
                  'https://raw.githubusercontent.com.evil.example/humanitylabs-org/wizard-ux/main/x.png',
                  'https://evil.example/raw.githubusercontent.com/humanitylabs-org/wizard-ux/main/x.png',
                  'https://github.com@evil.example/humanitylabs-org/wizard-ux/blob/main/x.png',
                  'https://raw.githubusercontent.com:8443/humanitylabs-org/wizard-ux/main/x.png',
                  'https://raw.githubusercontent.com/humanitylabs-org/wizard-ux/main/x.png?token=abc',
                  'https://raw.githubusercontent.com/humanitylabs-org/wizard-ux/main/x.png#frag',
                  'https://raw.githubusercontent.com/humanitylabs-org/wizard-ux/main/x.png\n',
                  'https://raw.githubusercontent.com/humanitylabs-org/wizard-ux/main/secrets.env',   # not a picture's name
                  'https://github.com/humanitylabs-org/wizard-ux/raw/main/x.png',
                  'https://github.com/humanitylabs-org/wizard-ux/issues/5',
                  'https://github.com/user-attachments/assets/1b2c3d4e-0000-1111-2222-333344445555',
                  'https://api.github.com/repos/humanitylabs-org/wizard-ux/contents/x.png',
                  'file:///etc/passwd', 'x.png', '', None, 5, ['https://example.com/x.png']):
            self.assertIsNone(S.shot_source(u), u)

    def test_kind_by_first_bytes(self):
        self.assertEqual(S.shot_kind(PNG), 'image/png')
        self.assertEqual(S.shot_kind(b'\xff\xd8\xff\xe0' + b'0' * 20), 'image/jpeg')
        self.assertEqual(S.shot_kind(b'GIF89a' + b'0' * 20), 'image/gif')
        self.assertEqual(S.shot_kind(b'GIF87a' + b'0' * 20), 'image/gif')
        self.assertEqual(S.shot_kind(b'RIFF\x10\x00\x00\x00WEBPVP8 '), 'image/webp')
        for junk in (b'', None, b'<svg xmlns="http://www.w3.org/2000/svg">', b'<!doctype html><script>', b'RIFF\x10\x00\x00\x00WAVEfmt ',
                     b'{"message":"Not Found"}', b'%PDF-1.7', b'\x89PN'):
            self.assertIsNone(S.shot_kind(junk), junk)


class Fetch(unittest.TestCase):
    def setUp(self):
        GH.issues.clear()
        reset()
        people()
        self.saved = S._shot_get
        self.asked, self.answer = [], PNG
        S._shot_get = lambda raw, token: self.asked.append((raw, token)) or self.answer
        S._shot_miss.clear()
        shutil.rmtree(S.PRIVATE / 'shots', ignore_errors=True)

    def tearDown(self):
        S._shot_get = self.saved
        S._shot_miss.clear()
        shutil.rmtree(S.PRIVATE / 'shots', ignore_errors=True)
        reset()

    def code(self, *a):
        with self.assertRaises(S.Problem) as e:
            S.shot(*a)
        return e.exception.code

    def test_fetched_with_the_persons_token_then_kept(self):
        self.assertEqual(S.shot('m', MEDIA), (PNG, 'image/png'))
        self.assertEqual(self.asked, [(S.shot_source(MEDIA), 'tok_miguel_aaaaaaaaaaaaaaaaaaaaaa')])
        self.assertEqual(S.shot('m', MEDIA), (PNG, 'image/png'))                       # from the box, not GitHub
        self.assertEqual(S.shot('n', MEDIA.replace('?raw=true', '')), (PNG, 'image/png'))   # the same picture, another link form
        self.assertEqual(len(self.asked), 1)
        kept = list((S.PRIVATE / 'shots').iterdir())
        self.assertEqual(len(kept), 1)
        self.assertEqual(kept[0].stat().st_mode & 0o777, 0o600)

    def test_refused_links_never_reach_github(self):
        for u in ('https://example.com/x.png', 'https://raw.githubusercontent.com/torvalds/linux/master/x.png', '', None):
            self.assertEqual(self.code('m', u), 400)
        self.assertEqual(self.asked, [])

    def test_signed_in_people_only(self):
        self.assertEqual(self.code('', MEDIA), 401)
        self.assertEqual(self.code('stranger', MEDIA), 401)
        self.assertEqual(self.asked, [])

    def test_only_real_pictures(self):
        for self.answer in (b'<svg onload="alert(1)">', b'<!doctype html>', b'', PNG + b'0' * S.SHOT_MAX):
            S._shot_miss.clear()
            self.assertEqual(self.code('m', RAW), 404)
        self.assertFalse((S.PRIVATE / 'shots').exists() and list((S.PRIVATE / 'shots').iterdir()))

    def test_a_missing_picture_is_not_asked_for_again_at_once(self):
        def gone(raw, token):
            self.asked.append(raw)
            raise urllib.error.HTTPError(raw, 404, 'Not Found', {}, None)
        S._shot_get = gone
        self.assertEqual(self.code('m', RAW), 404)
        self.assertEqual(self.code('m', RAW), 404)
        self.assertEqual(len(self.asked), 1)
        S._shot_get = lambda raw, token: self.asked.append(raw) or PNG   # another person's token is tried on its own
        self.assertEqual(S.shot('n', RAW), (PNG, 'image/png'))

    def test_the_oldest_pictures_go(self):
        keep, S.SHOT_KEEP = S.SHOT_KEEP, 3
        self.addCleanup(setattr, S, 'SHOT_KEEP', keep)
        for k in range(6):
            S.shot('m', RAW.replace('phone-', f'phone-{k}-'))
        self.assertEqual(len(list((S.PRIVATE / 'shots').iterdir())), 3)
        self.assertEqual(S.shot('m', RAW.replace('phone-', 'phone-5-')), (PNG, 'image/png'))
        self.assertEqual(len(self.asked), 6)

    def test_redirects_are_not_followed(self):
        class Hop(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(302)
                self.send_header('Location', 'http://127.0.0.1:9/elsewhere.png')
                self.end_headers()

            def log_message(self, *a):
                pass
        srv = ThreadingHTTPServer(('127.0.0.1', 0), Hop)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)
        with self.assertRaises(urllib.error.HTTPError) as e:
            self.saved(f'http://127.0.0.1:{srv.server_address[1]}/x.png', 'tok')
        self.assertEqual(e.exception.code, 302)

    def test_route(self):
        srv = ThreadingHTTPServer(('127.0.0.1', 0), S.Handler)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)

        def get(url, who='m'):
            c = http.client.HTTPConnection('127.0.0.1', srv.server_address[1], timeout=10)
            c.request('GET', '/api/shot?u=' + quote(url, safe=''), headers={'Tailscale-User-Login': who} if who else {})
            r = c.getresponse()
            body = r.read()
            c.close()
            return r.status, body, r.headers
        code, body, h = get(MEDIA)
        self.assertEqual((code, body, h['Content-Type']), (200, PNG, 'image/png'))
        self.assertEqual((h['X-Content-Type-Options'], h['Cache-Control']), ('nosniff', 'private, max-age=86400'))
        for bad in ('https://example.com/x.png', 'https://raw.githubusercontent.com/torvalds/linux/master/x.png'):
            code, body, h = get(bad)
            self.assertEqual((code, h['Cache-Control']), (400, 'no-store'))
        self.assertEqual(get(MEDIA, who='')[0], 401)
        self.answer = b'not a picture'
        code, body, _ = get(RAW)
        self.assertEqual(code, 404)
        self.assertNotIn(b'github', body.lower())


RECEIPT_OK = ('<!-- builder-verify -->\n**Tested before merge: Passed** · PR humanitylabs-org/wizard-music#7 at `5eb88d7` · 9.9 min\n\n'
              'It works.\n\nAfter: ' + ' '.join(MEDIA.replace('04-on', f'0{k}-on') for k in (1, 2, 3, 4)) + '\n')
RECEIPT_FAILED = ('<!-- builder-verify -->\n**Tested before merge: Failed** · PR humanitylabs-org/wizard-music#7 at `5eb88d7`\n\n'
                  'The button does nothing.\n\nWhat the tester saw: ' + MEDIA + ' ' + RAW + '\n')
HANDOVER = ('Done. The list now sorts itself.\n\nShow-and-tell:\nYour playlists now sort themselves by the last time you played them. '
            'Nothing to set up.\nBefore: ' + RAW + '\nAfter: ' + BLOB + ' https://github.com/user-attachments/assets/1b2c3d4e\nSwitch: wizard/sorted-lists\n')


class Pitch(unittest.TestCase):
    def test_the_testers_receipt_gives_after(self):
        p = S.show_pitch(['Building it now.', RECEIPT_OK], 'Sort my playlists.\n\nMore words.')
        self.assertEqual(p['before'], [])
        self.assertEqual(p['after'], [MEDIA.replace('04-on', f'0{k}-on') for k in (1, 2, 3)])   # at most three
        self.assertEqual(p['pitch'], 'Sort my playlists.')

    def test_what_the_tester_saw_is_not_after(self):
        p = S.show_pitch([RECEIPT_FAILED], 'Sort my playlists.')
        self.assertEqual((p['before'], p['after']), ([], []))
        p = S.show_pitch([HANDOVER, RECEIPT_FAILED], '')
        self.assertEqual((p['before'], p['after'][0]), ([RAW], BLOB))
        self.assertTrue(p['pitch'].startswith('Your playlists now sort themselves'))


class Board(unittest.TestCase):
    """board_split over a stubbed GitHub search: show-and-tell items carry pitch / before / after from the builder's
    comments that read already has."""
    def setUp(self):
        GH.issues.clear()
        reset({'core_repos': ['wizard-os'], 'core_approvers': ['James'], 'core_approval_not_needed_since': '2026-01-01'})
        people()
        S._decided.clear()
        S._boards.clear()
        S._decide_cache.clear()
        self.saved = (S._view_search, S._view_nodes, S.view_stats, S.org_repos, S.gh)

        def said(*bodies):
            return {'totalCount': len(bodies), 'nodes': [{'author': {'login': who}, 'body': b, 'createdAt': '2026-11-20T00:00:00Z'} for who, b in bodies]}
        self.nodes = {
            'core': [node(1, SHOW, author='mistermizel', repo='humanitylabs-org/wizard-os', comments=said((BOT, HANDOVER), (BOT, RECEIPT_FAILED))),
                     node(2, ['feature', 'approved'], author='mistermizel', repo='humanitylabs-org/wizard-os', comments=said((BOT, HANDOVER)))],
            'apps': [node(3, SHOW, author='mistermizel', repo='humanitylabs-org/wizard-music', body='Sort my playlists.\n\nMore words.',
                          comments=said((BOT, 'Building it now.'), (BOT, RECEIPT_OK))),
                     node(4, SHOW, author='JanMesaric', repo='humanitylabs-org/wizard-music', body='Sort my playlists.',
                          comments=said(('JanMesaric', 'After: ' + MEDIA), (BOT, RECEIPT_FAILED))),
                     node(5, SHOW, author='JanMesaric', repo='humanitylabs-org/wizard-music')],
            'bugs': [],
        }
        self.asked = []

        def search(token, view, q, **kw):
            self.asked.append((view, q, kw))
            return [n for n in self.nodes[view]], len(self.nodes[view])
        S._view_search = search
        S._view_nodes = lambda token, q, **kw: ([n for v in ('core', 'apps') for n in self.nodes[v] if 'show-and-tell' in str(n['labels'])], 4)
        S.view_stats = lambda *a, **k: None
        S.org_repos = lambda *a, **k: []
        real = S.gh
        self.rest = []
        S.gh = lambda token, method, path, *a, **k: self.rest.append(path) or real(token, method, path, *a, **k)

    def tearDown(self):
        S._view_search, S._view_nodes, S.view_stats, S.org_repos, S.gh = self.saved
        S._boards.clear()
        S._decide_cache.clear()
        reset()

    def cards(self, who='m'):
        return {i['number']: i for v in ('core', 'apps') for l in S.board_split(who, {'view': v})['groups'].values() for i in l}

    def test_show_cards_carry_pitch_and_pictures(self):
        c = self.cards()
        self.assertEqual({n: c[n]['group'] for n in c}, {1: 'show', 2: 'shipping', 3: 'show', 4: 'show', 5: 'show'})
        self.assertTrue(c[1]['pitch'].startswith('Your playlists now sort themselves by the last time you played them.'))
        self.assertEqual((c[1]['before'], c[1]['after']), ([RAW], [BLOB]))   # the user-attachments link stays a link
        self.assertEqual(c[3]['pitch'], 'Sort my playlists.')
        self.assertEqual((c[3]['before'], len(c[3]['after'])), ([], 3))
        # a failed test's 'What the tester saw' is not After, and only the builder's comments count
        self.assertEqual((c[4]['pitch'], c[4]['before'], c[4]['after']), ('Sort my playlists.', [], []))
        self.assertEqual((c[5]['pitch'], c[5]['before'], c[5]['after']), ('', [], []))
        for k in ('pitch', 'before', 'after'):
            self.assertNotIn(k, c[2])   # show-and-tell cards only
        self.assertEqual(c[1]['decider'], 'James')
        self.assertEqual(self.cards('n')[1]['after'], [BLOB])   # everyone who sees the card, not only its decider

    def test_no_request_per_card(self):
        self.cards()
        self.assertFalse([p for p in self.rest if '/comments' in p or '/issues/' in p], self.rest)
        heavy = [kw for _, q, kw in self.asked if 'show-and-tell' in q]
        self.assertTrue(heavy and all(kw.get('heavy') and kw.get('limit', 0) >= 200 for kw in heavy), heavy)

    def test_decisions_unchanged(self):
        d = S.decisions('m', {'for': 'all'})
        one = next(i for i in d['items'] if i['number'] == 1)
        self.assertEqual(sorted(one), sorted(['id', 'repo', 'number', 'title', 'url', 'category', 'decider', 'opener', 'created_at', 'switch',
                                              'pitch', 'before', 'after', 'can_decide', 'idea', 'parts',
                                              'since', 'auto_at', 'auto_due']))   # 0.48.0: + idea, parts; 0.51.0: + the 7-day clock
        self.assertEqual(one['after'], [BLOB, 'https://github.com/user-attachments/assets/1b2c3d4e'])


class Page(unittest.TestCase):
    def test_card_shows_pitch_and_pictures(self):
        card, tell, view = fn('itemCard'), fn('showTell'), fn('shotView')
        self.assertIn("if (i.group === 'show') c.append(...showTell(i));", card)
        self.assertLess(card.index('c.append(top)'), card.index('showTell(i)'))
        self.assertLess(card.index('showTell(i)'), card.index('actionArea(i)'))
        self.assertIn("make('p', 'bd-pitch', i.pitch)", tell)
        self.assertLess(tell.index("['After', i.after]"), tell.index("['Before', i.before]"))   # After first
        self.assertIn("'api/shot?u=' + encodeURIComponent(u)", tell)   # relative: the app is served under a path prefix
        self.assertNotIn("'/api/shot", JS)
        self.assertIn("img.loading = 'lazy'", tell)
        self.assertIn('img.onerror', tell)
        self.assertIn('b.remove()', tell)
        self.assertIn('shotView(src, label)', tell)
        self.assertIn('WzSheet.open(d)', view)   # the kit's sheet: ×, Esc, tap outside and Back close it
        self.assertIn('WzSheet.close(d)', view)
        self.assertNotIn('innerHTML', tell + view)

    def test_styles(self):
        new = CSS[CSS.index('/* 0.47.0'):]
        self.assertIn('-webkit-line-clamp: 3', re.search(r'\.bd-pitch \{[^}]*\}', new).group(0))
        self.assertIn('repeat(auto-fill, minmax(8.5rem, 1fr))', new)   # two side by side at 412 px
        thumb = re.search(r'\.bd-thumb img \{[^}]*\}', new).group(0)
        self.assertIn('height: 11rem', thumb)
        self.assertIn('object-fit: contain', thumb)
        self.assertIsNone(re.search(r'#[0-9a-fA-F]{3,8}\b|rgba?\(', new))
        self.assertIsNone(re.search(r'font-size:\s*[\d.]+px', new))

    def test_csp_still_loads_pictures_from_the_tracker_only(self):
        self.assertIn("img-src 'self' data:;", (ROOT / 'app' / 'server.py').read_text())

    def test_version(self):
        self.assertEqual(tuple(int(x) for x in S.VERSION.split('.'))[:2] >= (0, 47), True)


if __name__ == '__main__':
    unittest.main()
