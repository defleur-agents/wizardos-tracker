"""0.48.0 (Miguel, 21 Nov 2026): one idea, one card, one yes or no. The builder splits one idea into pieces across repos
and each piece asked for its own decision. Show-and-tell items are one idea when they name the same switch or one says
`Part of: <owner>/<repo>#<n>` about another item at show-and-tell; joining is transitive, the root is the oldest piece,
the decider is the core decider when any piece is in a core repo. /api/decisions counts ideas, /api/split cards carry
the idea, and a yes or no on any piece decides every piece (retry-safe, with a result per piece).
Run: python3 -m unittest discover -s tests"""
import json
import re
import shutil
import subprocess
import time
import unittest
from pathlib import Path

from test_013 import GH, S, reset
from test_017 import people
from test_0182 import node

ROOT = Path(__file__).resolve().parent.parent
JS = (ROOT / 'web' / 'app.js').read_text()
CSS = (ROOT / 'web' / 'styles.css').read_text()
BOT = 'wizardos-builder[bot]'
SHOW = ['feature', 'show-and-tell']
ORG = 'humanitylabs-org'
OS_, UX, SVC, MUSIC, NOTES = (f'{ORG}/{r}' for r in ('wizard-os', 'wizard-ux', 'wizard-agent-service', 'wizard-music', 'wizard-notes'))
POLICY = {'core_repos': ['wizard-os', 'wizard-ux', 'wizard-agent-service']}


def fn(name):
    m = re.search(r'\n(?:async )?function ' + name + r'\(', JS)
    i, depth = JS.index('{', m.start()), 0
    for j in range(i, len(JS)):
        depth += {'{': 1, '}': -1}.get(JS[j], 0)
        if depth == 0:
            return JS[m.start():j + 1]


def said(*rows):
    return {'totalCount': len(rows), 'nodes': [{'author': {'login': who}, 'body': b, 'createdAt': '2026-11-20T00:00:00Z'} for who, b in rows]}


def piece(number, repo, day, author='mistermizel', switch=None, body='', comments=()):
    rows = list(comments) + ([(BOT, f'What changed: a thing.\n\nSwitch: {switch}')] if switch is not None else [])
    return node(number, SHOW, author=author, repo=repo, body=body, comments=said(*rows), createdAt=f'2026-11-{day:02d}T00:00:00Z',
                title=f'piece {number}')


def item(i, repo, day, decider='Miguel', switch=None, part_of=()):
    return {'id': f'{repo}#{i}', 'repo': repo, 'number': i, 'created_at': f'2026-11-{day:02d}T00:00:00Z', 'decider': decider,
            'switch': switch, '_part_of': [p.lower() for p in part_of]}


class Rule(unittest.TestCase):
    """idea_groups and the `Part of:` line, pure."""
    def setUp(self):
        reset(POLICY)
        people()
        self.base = S.policy_base()

    def tearDown(self):
        reset()

    def ideas(self, items, gone=()):
        return S.idea_groups(items, self.base, gone)

    def test_same_switch_joins(self):
        g = self.ideas([item(1, MUSIC, 2, switch='wizard-music:radio'), item(2, MUSIC, 1, switch=' Wizard-Music:Radio '),
                        item(3, MUSIC, 3, switch='wizard-music:other')])
        self.assertEqual(g[f'{MUSIC}#1'.lower()]['parts'], [f'{MUSIC}#2', f'{MUSIC}#1'])   # trimmed, any case
        self.assertIs(g[f'{MUSIC}#1'.lower()], g[f'{MUSIC}#2'.lower()])
        self.assertEqual(g[f'{MUSIC}#3'.lower()]['parts'], [f'{MUSIC}#3'])

    def test_no_switch_or_none_never_joins(self):
        g = self.ideas([item(1, MUSIC, 1), item(2, MUSIC, 2), item(3, MUSIC, 3, switch=''), item(4, MUSIC, 4, switch='   '),
                        item(5, MUSIC, 5, switch='none'), item(6, MUSIC, 6, switch='None (docs only)')])
        self.assertEqual(len({x['idea'] for x in g.values()}), 6)
        self.assertTrue(all(len(x['parts']) == 1 for x in g.values()))

    def test_part_of_only_names_an_item_at_show_and_tell(self):
        g = self.ideas([item(1, OS_, 1, 'James'), item(2, MUSIC, 2, part_of=[f'{OS_}#1']), item(3, MUSIC, 3, part_of=[f'{OS_}#99']),
                        item(4, MUSIC, 4, part_of=[f'{MUSIC}#4'])])   # #99 is not listed; #4 names itself
        self.assertEqual(g[f'{MUSIC}#2'.lower()]['parts'], [f'{OS_}#1', f'{MUSIC}#2'])
        self.assertEqual(g[f'{MUSIC}#3'.lower()]['parts'], [f'{MUSIC}#3'])
        self.assertEqual(g[f'{MUSIC}#4'.lower()]['parts'], [f'{MUSIC}#4'])

    def test_transitive_and_root_is_the_oldest(self):
        # 1 and 2 share a switch; 3 is part of 2; 4 is part of 3; 5 shares 4's own switch
        g = self.ideas([item(1, MUSIC, 5, switch='a/x'), item(2, NOTES, 3, switch='a/x'), item(3, NOTES, 9, part_of=[f'{NOTES}#2']),
                        item(4, MUSIC, 2, switch='b/y', part_of=[f'{NOTES}#3']), item(5, NOTES, 7, switch='b/y'), item(6, NOTES, 1)])
        one = g[f'{MUSIC}#1'.lower()]
        self.assertEqual(one['idea'], f'{MUSIC}#4')                 # the oldest piece, not the first listed
        self.assertEqual(one['parts'], [f'{MUSIC}#4', f'{NOTES}#2', f'{MUSIC}#1', f'{NOTES}#5', f'{NOTES}#3'])   # root first, then by age
        self.assertEqual(len({x['idea'] for x in g.values()}), 2)
        self.assertEqual(g[f'{NOTES}#6'.lower()]['parts'], [f'{NOTES}#6'])

    def test_decider(self):
        # app pieces only: the root's decider
        g = self.ideas([item(1, MUSIC, 2, 'Jan', 'a/x'), item(2, NOTES, 1, 'Miguel', 'a/x')])
        self.assertEqual(g[f'{MUSIC}#1'.lower()]['decider'], 'Miguel')
        # any piece in a core repo: the core decider, whoever the root's is
        g = self.ideas([item(1, MUSIC, 1, 'Miguel', 'a/x'), item(2, UX, 2, 'James', 'a/x'), item(3, NOTES, 3, 'Jan', 'a/x')])
        self.assertEqual({x['decider'] for x in g.values()}, {'James'})
        reset({**POLICY, 'show_deciders': {'core': 'Jan'}})
        people()
        g = S.idea_groups([item(1, MUSIC, 1, 'Miguel', 'a/x'), item(2, UX, 2, 'Jan', 'a/x')])
        self.assertEqual(g[f'{MUSIC}#1'.lower()]['decider'], 'Jan')
        # an idea of one keeps its own decider
        self.assertEqual(self.ideas([item(1, MUSIC, 1, 'Jan')])[f'{MUSIC}#1'.lower()]['decider'], 'Jan')

    def test_decided_pieces_leave_the_idea_but_not_its_rule(self):
        items = [item(1, UX, 1, 'James', 'a/x'), item(2, MUSIC, 2, 'Miguel', 'a/x'), item(3, MUSIC, 3, 'Miguel', 'a/x')]
        g = self.ideas(items, gone={f'{UX}#1'})
        self.assertNotIn(f'{UX}#1'.lower(), g)
        self.assertEqual(g[f'{MUSIC}#2'.lower()]['parts'], [f'{MUSIC}#2', f'{MUSIC}#3'])
        self.assertEqual(g[f'{MUSIC}#2'.lower()]['all'], [f'{UX}#1', f'{MUSIC}#2', f'{MUSIC}#3'])
        self.assertEqual(g[f'{MUSIC}#2'.lower()]['decider'], 'James')   # still the same idea while GitHub lists the core piece
        self.assertEqual(self.ideas(items, gone={x['id'] for x in items}), {})

    def test_part_of_line(self):
        refs = lambda t: S.part_of_refs([t], ORG)   # noqa: E731
        want = [f'{ORG}/wizard-os#676']
        for line in ('Part of: humanitylabs-org/wizard-os#676', 'Part of: wizard-os#676', 'part of:wizard-os#676',
                     '**Part of:** wizard-os#676', '`Part of: wizard-os#676`', '> Part of: `humanitylabs-org/wizard-os#676`',
                     '- Part of: wizard-os#676 (the settings half)', 'Intro.\n\nPART OF: Wizard-OS#676\nMore.'):
            self.assertEqual(refs(line), want, line)
        for line in ('This is part of: wizard-os#676', 'Part of wizard-os#676', 'Part of: #676', 'Part of: torvalds/linux#1',
                     'Part of: the agent inbox', 'Split from humanitylabs-org/wizard-os#676', ''):
            self.assertEqual(refs(line), [], line)
        self.assertEqual(S.part_of_refs(['Part of: wizard-os#1', None, 'x\nPart of: wizard-ux#2'], ORG), [f'{ORG}/wizard-os#1', f'{ORG}/wizard-ux#2'])


class Listed(unittest.TestCase):
    """GET /api/decisions and GET /api/split over a stubbed show-and-tell list."""
    def setUp(self):
        GH.issues.clear()
        reset(POLICY)
        people()
        for c in (S._decided, S._boards, S._needs, S._decide_cache):
            c.clear()
        self.saved = (S._view_search, S._view_nodes, S.view_stats, S.org_repos, S.gh)
        self.show = [
            # the Agent inbox idea: one switch, three pieces in two core repos, the oldest first
            piece(549, SVC, 1, switch='wizard/agent-inbox', comments=[(BOT, 'Show-and-tell:\nYour agent has one inbox now.')]),
            piece(1569, UX, 2, switch='wizard/agent-inbox'),
            piece(550, SVC, 3, switch='Wizard/Agent-Inbox'),
            # an app piece that says it is part of a core item (its own switch differs): body, by the builder
            piece(676, OS_, 4, switch='wizard/private-first'),
            piece(77, NOTES, 5, author=BOT, switch='wizard-notes:setup', body=f'Split out.\n\nPart of: {OS_}#676\n'),
            # Part of in a comment: by a team member's agent (joins), by a stranger (does not)
            piece(20, MUSIC, 6, author='JanMesaric', switch='wizard-music:radio'),
            piece(21, MUSIC, 7, author='JanMesaric', comments=[('oscarhenrycollins', 'Part of: wizard-music#20')]),
            piece(22, MUSIC, 8, author='mistermizel', comments=[('stranger', 'Part of: wizard-music#20')]),
            # names an item that is not at show-and-tell
            piece(23, MUSIC, 9, author='mistermizel', body='Part of: wizard-music#999'),
            # no switch at all, twice: never one idea
            piece(24, MUSIC, 10, author='mistermizel', switch='none (docs only)'),
            piece(25, MUSIC, 11, author='mistermizel', switch='none'),
        ]
        self.asked, self.rest = [], []

        def nodes(token, q, **kw):
            self.asked.append((q, kw))
            return ([n for n in self.show], len(self.show)) if 'show-and-tell' in q else ([], 0)

        def search(token, view, q, **kw):
            keep = [n for n in self.show if view in ('core', 'apps') and S.is_core(n['repository']['nameWithOwner']) == (view == 'core')]
            return keep, len(keep)
        S._view_nodes, S._view_search = nodes, search
        S.view_stats = lambda *a, **k: None
        S.org_repos = lambda *a, **k: []
        real = S.gh
        S.gh = lambda token, method, path, *a, **k: self.rest.append(path) or real(token, method, path, *a, **k)

    def tearDown(self):
        S._view_search, S._view_nodes, S.view_stats, S.org_repos, S.gh = self.saved
        for c in (S._decided, S._boards, S._needs, S._decide_cache):
            c.clear()
        reset()

    def by(self, d):
        return {i['id'].split('/')[-1]: i for i in d['items']}

    def test_decisions_join_and_count_ideas(self):
        d = S.decisions('m', {'for': 'all'})
        i = self.by(d)
        self.assertEqual((d['total'], d['count'], d['ideas']), (11, 11, 7))        # eleven pieces, seven ideas
        inbox = [f'{SVC}#549', f'{UX}#1569', f'{SVC}#550']
        for k in ('wizard-agent-service#549', 'wizard-ux#1569', 'wizard-agent-service#550'):
            self.assertEqual((i[k]['idea'], i[k]['parts'], i[k]['decider']), (inbox[0], inbox, 'James'), k)
        # Part of in the body: the app piece joins the core item, and James decides both
        self.assertEqual(i['wizard-notes#77']['parts'], [f'{OS_}#676', f'{NOTES}#77'])
        self.assertEqual((i['wizard-notes#77']['idea'], i['wizard-notes#77']['decider']), (f'{OS_}#676', 'James'))
        self.assertEqual(i['wizard-os#676']['parts'], [f'{OS_}#676', f'{NOTES}#77'])
        # Part of in a team agent's comment joins; the root's decider (Jan filed #20) decides
        self.assertEqual((i['wizard-music#21']['parts'], i['wizard-music#21']['decider']), ([f'{MUSIC}#20', f'{MUSIC}#21'], 'Jan'))
        # a stranger's comment joins nothing; neither does a line naming an item that is not at show-and-tell
        for k in ('wizard-music#22', 'wizard-music#23', 'wizard-music#24', 'wizard-music#25'):
            self.assertEqual((i[k]['idea'], i[k]['parts'], i[k]['decider']), (i[k]['id'], [i[k]['id']], 'Miguel'), k)
        # counts are ideas per decider: the builder's cap reads these
        self.assertEqual(d['counts'], {'James': 2, 'Jan': 1, 'Miguel': 4})
        self.assertEqual(sum(d['counts'].values()), d['ideas'])
        self.assertNotIn('_part_of', i['wizard-notes#77'])

    def test_for_one_person_and_can_decide_follow_the_idea(self):
        d = S.decisions('m', {})
        self.assertEqual((d['for'], d['count'], d['ideas']), ('Miguel', 4, 4))
        self.assertTrue(all(x['can_decide'] for x in d['items']))
        j = S.decisions('j', {})
        self.assertEqual((j['count'], j['ideas']), (5, 2))                          # five pieces, two decisions
        self.assertIn('wizard-notes#77', self.by(j))                                # the builder-filed app piece is James's now
        self.assertTrue(all(x['can_decide'] for x in j['items']))
        self.assertFalse(any(x['can_decide'] for x in S.decisions('m', {'for': 'James'})['items']))
        self.assertEqual(S.CALLS['decisions_list']({'for': 'all'})['counts'], {'James': 2, 'Jan': 1, 'Miguel': 4})

    def test_no_request_per_card_and_one_read(self):
        S.decisions('m', {'for': 'all'})
        S.board_split('m', {'view': 'core'})
        S.board_split('m', {'view': 'apps'})
        self.assertFalse([p for p in self.rest if '/comments' in p or '/issues/' in p], self.rest)
        lists = [kw for q, kw in self.asked if 'show-and-tell' in q]
        self.assertEqual(len(lists), 1)                                             # kept a minute, shared by the tabs
        self.assertTrue(lists[0].get('heavy') and lists[0].get('limit', 0) >= 200)

    def split(self, who, view):
        return S.board_split(who, {'view': view})

    def test_split_cards_carry_the_idea(self):
        core = self.split('j', 'core')
        c = {i['number']: i for i in core['groups']['show']}
        self.assertEqual(sorted(c), [549, 550, 676, 1569])                          # every piece is still listed
        for n in (549, 550, 1569):
            self.assertEqual(c[n]['idea'], f'{SVC}#549')
            self.assertEqual([x['id'] for x in c[n]['parts']], [f'{SVC}#549', f'{UX}#1569', f'{SVC}#550'])
            self.assertEqual(sorted(c[n]['parts'][0]), ['id', 'number', 'repo', 'title', 'url'])
            self.assertEqual(c[n]['idea_show']['title'], 'piece 549')
            self.assertEqual(c[n]['idea_show']['pitch'], 'Your agent has one inbox now.')
            self.assertTrue(c[n]['can_decide'] and c[n]['turn'])
        self.assertEqual(core['counts']['show'], 2)                                 # four pieces, two ideas
        self.assertEqual(core['waiting']['show']['n'], 2)
        self.assertEqual(core['waiting']['show']['by'], [['James', 2]])
        apps = self.split('m', 'apps')
        a = {i['number']: i for i in apps['groups']['show']}
        # the app piece of a core idea: James decides it, also on the Apps tab, and the card shows the root
        self.assertEqual((a[77]['decider'], a[77]['can_decide'], a[77]['turn']), ('James', False, False))
        self.assertEqual(a[77]['waiting_on']['who'], ['James'])
        self.assertEqual((a[77]['idea'], a[77]['idea_show']['title']), (f'{OS_}#676', 'piece 676'))
        self.assertEqual((a[21]['decider'], a[20]['decider']), ('Jan', 'Jan'))
        # an idea of one is as before: itself, no idea_show
        self.assertEqual((a[22]['idea'], [x['id'] for x in a[22]['parts']]), (f'{MUSIC}#22', [f'{MUSIC}#22']))
        self.assertNotIn('idea_show', a[22])
        self.assertTrue(a[22]['can_decide'] and a[22]['turn'])
        self.assertEqual(apps['counts']['show'], 6)                                 # 7 pieces: #20 + #21 are one
        self.assertEqual(dict(map(tuple, apps['waiting']['show']['by'])), {'Miguel': 4, 'Jan': 1, 'James': 1})

    def test_waiting_on_me_counts_an_idea_once(self):
        ny = S.needs_you('j')
        self.assertEqual(ny['count'], 2)
        self.assertEqual(sorted(x['id'] for x in ny['items']), sorted([f'{SVC}#549', f'{OS_}#676']))   # under the root
        self.assertEqual({x['title'] for x in ny['items']}, {'piece 549', 'piece 676'})
        self.assertEqual(S.needs_you('m')['count'], 4)

    def test_pictures_come_from_the_root_else_the_first_pieces(self):
        shot = lambda k: f'https://raw.githubusercontent.com/{ORG}/wizard-issue-media/main/{k}.png'   # noqa: E731
        root = {'title': 'r', 'pitch': 'p', 'before': [], 'after': []}
        a = {'title': 'a', 'after': [shot('a1'), shot('a2'), 'https://example.com/x.png'], 'before': [shot('b1')]}
        b = {'title': 'b', 'after': [shot('a2'), shot('a3'), shot('a4')], 'before': []}
        got = S.idea_show([root, a, b])
        self.assertEqual((got['title'], got['pitch']), ('r', 'p'))
        self.assertEqual(got['after'], [shot('a1'), shot('a2'), shot('a3')])        # at most three, no repeats, only showable
        self.assertEqual(got['before'], [shot('b1')])
        got = S.idea_show([{**root, 'after': [shot('r1')]}, a, b])
        self.assertEqual((got['after'], got['before']), ([shot('r1')], []))         # the root has one: only the root's


class FakeGitHub:
    """Issues in any repo, for the fan-out: GET issue / comments, labels, comment, close. `refuse` = repos whose
    labels GitHub will not set."""
    def __init__(self):
        self.issues, self.refuse, self.calls = {}, set(), []

    def add(self, iid, user='mistermizel', labels=SHOW, body='', comments=()):
        self.issues[iid.lower()] = {'user': user, 'labels': set(labels), 'body': body, 'comments': list(comments), 'state': 'open',
                                    'state_reason': None}

    def __call__(self, token, method, path, body=None, **kw):
        self.calls.append((method, path))
        m = re.match(r'^/repos/([\w.-]+/[\w.-]+)/issues/(\d+)(?:/(labels|comments)(?:/([\w:-]+))?)?(?:\?.*)?$', path)
        if not m:
            return {}   # POST /repos/x/labels (make the label), the author lookups
        full, n, what, label = m.groups()
        it = self.issues[f'{full}#{n}'.lower()]
        if method == 'GET' and not what:
            return {'number': int(n), 'state': it['state'], 'state_reason': it['state_reason'], 'user': {'login': it['user']},
                    'body': it['body'], 'labels': [{'name': x} for x in sorted(it['labels'])], 'comments': len(it['comments'])}
        if method == 'GET':
            return [{'user': {'login': w}, 'body': b} for w, b in it['comments']]
        if what == 'labels' and method == 'POST':
            if full in self.refuse:
                raise S.Problem(403, 'Resource not accessible by integration')
            it['labels'] |= set(body['labels'])
        elif what == 'labels' and method == 'DELETE':
            it['labels'].discard(label)
        elif what == 'comments':
            it['comments'].append(('me', body['body']))
        elif method == 'PATCH':
            it['state'], it['state_reason'] = body['state'], body.get('state_reason')
        return {}


class FanOut(unittest.TestCase):
    """POST /api/decide on one piece decides every piece of its idea."""
    def setUp(self):
        GH.issues.clear()
        reset(POLICY)
        people()
        for c in (S._decided, S._boards, S._needs, S._decide_cache, S._labels_made):
            c.clear()
        self.saved = (S._view_nodes, S.gh)
        self.gh = FakeGitHub()
        sw = (BOT, 'What changed: x.\n\nSwitch: wizard/agent-inbox')
        self.show = [piece(549, SVC, 1, switch='wizard/agent-inbox'), piece(1569, UX, 2, switch='wizard/agent-inbox'),
                     piece(77, NOTES, 3, author=BOT, switch='wizard-notes:setup', body=f'Part of: {UX}#1569'),
                     piece(20, MUSIC, 4, switch='wizard-music:radio'), piece(21, MUSIC, 5, switch='wizard-music:radio'),
                     piece(30, MUSIC, 6)]
        self.gh.add(f'{SVC}#549', comments=[sw])
        self.gh.add(f'{UX}#1569', comments=[sw])
        self.gh.add(f'{NOTES}#77', user=BOT, body=f'Part of: {UX}#1569', comments=[(BOT, 'Switch: wizard-notes:setup')])
        self.gh.add(f'{MUSIC}#20', comments=[(BOT, 'Switch: wizard-music:radio')])
        self.gh.add(f'{MUSIC}#21', comments=[(BOT, 'Switch: wizard-music:radio')])
        self.gh.add(f'{MUSIC}#30', comments=[(BOT, 'Switch: none')])
        self.inbox = [f'{SVC}#549', f'{UX}#1569', f'{NOTES}#77']
        S._view_nodes = lambda token, q, **kw: ([n for n in self.show], len(self.show)) if 'show-and-tell' in q else ([], 0)
        S.gh = self.gh

    def tearDown(self):
        S._view_nodes, S.gh = self.saved
        for c in (S._decided, S._boards, S._needs, S._decide_cache, S._labels_made):
            c.clear()
        reset()

    def it(self, iid):
        return self.gh.issues[iid.lower()]

    def test_yes_on_any_piece_decides_every_piece(self):
        r = S.decide('j', {'repo': 'wizard-notes', 'number': 77, 'decision': 'approve', 'note': 'Ship it'})   # the youngest piece
        self.assertEqual((r['idea'], r['decider'], r['failed'], r['saved']), (f'{SVC}#549', 'James', 0, True))
        self.assertEqual(r['parts'], [{'id': x, 'ok': True} for x in self.inbox])    # root first
        self.assertEqual((r['id'], r['number'], r['decision'], r['switch_default'], r['switch']), (f'{NOTES}#77', 77, 'yes', True, True))
        for x in self.inbox:
            it = self.it(x)
            self.assertTrue({'approved', 'switch-default'} <= it['labels'], x)
            self.assertNotIn('show-and-tell', it['labels'], x)
            self.assertEqual(it['state'], 'open', x)                                 # the builder turns it on and closes it
            said_ = it['comments'][-1][1]
            self.assertTrue(said_.startswith('Show-and-tell: yes \u2014 James (@jdefleur)'), said_)
            self.assertIn('Ship it', said_)
            self.assertIn('Builder: turn it on for everyone', said_)
            self.assertTrue(said_.endswith(': one idea, one yes or no.'), said_)
            self.assertIn(x, S._decided)
        self.assertIn(f'Decided together with {SVC}#549: one idea, one yes or no.', self.it(f'{UX}#1569')['comments'][-1][1])
        self.assertIn(f'Decided together with its other parts ({UX}#1569, {NOTES}#77): one idea, one yes or no.',
                      self.it(f'{SVC}#549')['comments'][-1][1])
        self.assertIn('show-and-tell', self.it(f'{MUSIC}#20')['labels'])             # another idea is untouched
        self.assertEqual(S.decisions('j', {'for': 'all'})['counts'], {'Miguel': 2})   # the whole idea left the queue

    def test_no_declines_every_piece(self):
        r = S.decide('m', {'repo': 'wizard-music', 'number': 20, 'decision': 'no', 'note': 'Not needed'})
        self.assertEqual(r['parts'], [{'id': f'{MUSIC}#20', 'ok': True}, {'id': f'{MUSIC}#21', 'ok': True}])
        for x in (f'{MUSIC}#20', f'{MUSIC}#21'):
            it = self.it(x)
            self.assertTrue({'dropped', 'switch-cleanup'} <= it['labels'])
            self.assertNotIn('show-and-tell', it['labels'])
            self.assertEqual((it['state'], it['state_reason']), ('closed', 'not_planned'))
            self.assertIn('Why: Not needed', it['comments'][-1][1])
        self.assertIn(f'Decided together with {MUSIC}#20: one idea, one yes or no.', self.it(f'{MUSIC}#21')['comments'][-1][1])

    def test_an_idea_of_one_is_as_before(self):
        r = S.decide('m', {'repo': 'wizard-music', 'number': 30, 'decision': 'yes'})
        self.assertEqual((r['idea'], r['parts'], r['failed'], r['saved']), (f'{MUSIC}#30', [{'id': f'{MUSIC}#30', 'ok': True}], 0, True))
        said_ = self.it(f'{MUSIC}#30')['comments'][-1][1]
        self.assertNotIn('Decided together', said_)
        self.assertEqual(said_, 'Show-and-tell: yes \u2014 Miguel (@mistermizel)\n\nBuilder: it has no switch; make sure it is on for everyone, then close this issue.')
        self.assertIn('show-and-tell', self.it(f'{MUSIC}#20')['labels'])

    def test_only_the_ideas_decider(self):
        # wizard-notes#77 alone would be Miguel's (the builder filed it, no linked filer); its idea has core pieces: James's
        for who in ('m', 'n'):
            with self.assertRaises(S.Problem) as e:
                S.decide(who, {'repo': 'wizard-notes', 'number': 77, 'decision': 'yes'})
            self.assertEqual((e.exception.code, e.exception.reason), (403, 'not_decider'))
            self.assertIn('James', e.exception.message)
        self.assertFalse([c for c in self.gh.calls if c[0] != 'GET'], self.gh.calls)   # nothing was written anywhere
        for x in self.inbox:
            self.assertIn('show-and-tell', self.it(x)['labels'])
        with self.assertRaises(S.Problem) as e:   # and James does not decide Miguel's app idea
            S.decide('j', {'repo': 'wizard-music', 'number': 21, 'decision': 'yes'})
        self.assertEqual(e.exception.reason, 'not_decider')
        with self.assertRaises(S.Problem):        # an agent needs its person's words, as before
            S.CALLS['board_decide']({'issue': f'{MUSIC}#20', 'decision': 'yes'})
        r = S.CALLS['board_decide']({'issue': f'{MUSIC}#21', 'decision': 'yes', 'owner_request': 'Miguel: yes to the radio'})
        self.assertEqual([p['ok'] for p in r['parts']], [True, True])                # Miguel's agent, Miguel's idea

    def test_a_failed_piece_does_not_stop_the_others_and_a_retry_is_safe(self):
        self.gh.refuse.add(UX)
        r = S.decide('j', {'repo': 'wizard-agent-service', 'number': 549, 'decision': 'yes'})
        self.assertEqual([(p['id'], p['ok']) for p in r['parts']], [(self.inbox[0], True), (self.inbox[1], False), (self.inbox[2], True)])
        self.assertIn('GitHub refused the label', r['parts'][1]['error'])
        self.assertIn(f'{UX}#1569', r['parts'][1]['error'])
        self.assertEqual((r['failed'], r['saved']), (1, False))
        self.assertIn('show-and-tell', self.it(f'{UX}#1569')['labels'])              # nothing half-done on the refused one
        self.assertEqual(len(self.it(f'{UX}#1569')['comments']), 1)
        self.assertNotIn(f'{UX}#1569', S._decided)
        # what is left is still James's to decide (GitHub search still lists the decided core piece)
        left = S.decisions('j', {'for': 'all'})
        one = next(i for i in left['items'] if i['id'] == f'{UX}#1569')
        self.assertEqual((one['parts'], one['decider']), ([f'{UX}#1569'], 'James'))
        self.assertNotIn(f'{SVC}#549', [i['id'] for i in left['items']])
        # the retry, on a piece that was already decided: the two done pieces are left alone, the third is decided
        self.gh.refuse.clear()
        before = {x: len(self.it(x)['comments']) for x in self.inbox}
        r = S.decide('j', {'repo': 'wizard-agent-service', 'number': 549, 'decision': 'yes'})
        self.assertEqual(r['parts'], [{'id': self.inbox[0], 'ok': True, 'already': True}, {'id': self.inbox[1], 'ok': True},
                                      {'id': self.inbox[2], 'ok': True, 'already': True}])
        self.assertEqual((r['failed'], r['saved']), (0, True))
        self.assertEqual({x: len(self.it(x)['comments']) - before[x] for x in self.inbox},
                         {self.inbox[0]: 0, self.inbox[1]: 1, self.inbox[2]: 0})     # no second comment
        self.assertTrue(all('switch-default' in self.it(x)['labels'] and 'show-and-tell' not in self.it(x)['labels'] for x in self.inbox))
        # and once more: everything already carries the yes
        r = S.decide('j', {'repo': 'wizard-ux', 'number': 1569, 'decision': 'yes'})
        self.assertTrue(all(p['ok'] and p.get('already') for p in r['parts']))

    def test_every_piece_refused_is_the_error_as_before(self):
        self.gh.refuse.update({SVC, UX, NOTES})
        with self.assertRaises(S.Problem) as e:
            S.decide('j', {'repo': 'wizard-ux', 'number': 1569, 'decision': 'yes'})
        self.assertEqual(e.exception.reason, 'label_refused')
        self.assertEqual(S._decided, {})

    def test_a_piece_that_left_show_and_tell_is_never_decided(self):
        # the builder took #1569 back to Building; GitHub search (the kept list) still names it at show-and-tell
        self.it(f'{UX}#1569')['labels'] = {'feature', 'building'}
        r = S.decide('j', {'repo': 'wizard-agent-service', 'number': 549, 'decision': 'no'})
        self.assertEqual([(p['id'], p['ok'], p.get('skipped', False)) for p in r['parts']],
                         [(self.inbox[0], True, False), (self.inbox[1], False, True), (self.inbox[2], True, False)])
        self.assertEqual((r['failed'], r['saved']), (0, True))                       # left alone is not a failure
        self.assertEqual(self.it(f'{UX}#1569')['labels'], {'feature', 'building'})
        self.assertEqual((self.it(f'{UX}#1569')['state'], len(self.it(f'{UX}#1569')['comments'])), ('open', 1))
        # naming a piece that is not waiting stays a 409, as before, and one decided the other way is not 'already'
        with self.assertRaises(S.Problem) as e:
            S.decide('j', {'repo': 'wizard-ux', 'number': 1569, 'decision': 'no'})
        self.assertEqual((e.exception.code, e.exception.reason), (409, 'not_show'))
        with self.assertRaises(S.Problem) as e:
            S.decide('j', {'repo': 'wizard-agent-service', 'number': 549, 'decision': 'yes'})   # it was declined
        self.assertEqual(e.exception.code, 409)

    def test_decided_cards_leave_the_board_together(self):
        S.view_stats_, S.org_repos_, search_ = S.view_stats, S.org_repos, S._view_search
        S.view_stats, S.org_repos = (lambda *a, **k: None), (lambda *a, **k: [])
        S._view_search = lambda token, view, q, **kw: ([n for n in self.show if view == 'apps' and not S.is_core(n['repository']['nameWithOwner'])], 4)
        try:
            self.assertEqual(S.board_split('m', {'view': 'apps'})['counts']['show'], 3)   # #77, #20 + #21, #30
            S.decide('m', {'repo': 'wizard-music', 'number': 21, 'decision': 'yes'})
            after = S.board_split('m', {'view': 'apps'})                                 # search still lists both
            self.assertEqual(sorted(i['number'] for i in after['groups']['show']), [30, 77])
            self.assertEqual(after['counts']['show'], 2)
        finally:
            S.view_stats, S.org_repos, S._view_search = S.view_stats_, S.org_repos_, search_
            del S.view_stats_, S.org_repos_


class Page(unittest.TestCase):
    def test_one_card_per_idea(self):
        if not shutil.which('node'):
            self.skipTest('node missing')
        root = {'id': 'o/a#1', 'group': 'show', 'idea': 'o/a#1', 'title': 'Root', 'parts': [{'id': 'o/a#1', 'title': 'Root'}, {'id': 'o/b#2', 'title': 'B'}],
                'idea_show': {'title': 'Root', 'pitch': 'P', 'before': [], 'after': ['u']}}
        cards = [{**root, 'id': 'o/b#2', 'title': 'B'}, {'id': 'o/c#3', 'group': 'show', 'idea': 'o/c#3', 'title': 'C', 'parts': [{'id': 'o/c#3', 'title': 'C'}]},
                 root, {'id': 'o/d#4', 'group': 'answer', 'title': 'D'}, {'id': 'o/e#5', 'group': 'show', 'title': 'old server'}]
        src = fn('onePerIdea') + fn('ideaOf') + '\nconst l = ' + json.dumps(cards) + ''';
const out = onePerIdea(l);
console.log(JSON.stringify([out.map(i => i.id), l.map(i => { const x = ideaOf(i); return x && [x.root.id, x.title, x.pitch, x.after]; }),
  onePerIdea([l[0], l[1]]).map(i => i.id), onePerIdea(null)]));'''
        out = json.loads(subprocess.run(['node', '-e', src], capture_output=True, text=True, check=True).stdout)
        self.assertEqual(out[0], ['o/a#1', 'o/c#3', 'o/d#4', 'o/e#5'])   # the idea once, where its first piece was, as its root
        self.assertEqual(out[1], [['o/a#1', 'Root', 'P', ['u']], None, ['o/a#1', 'Root', 'P', ['u']], None, None])
        self.assertEqual(out[2], ['o/b#2', 'o/c#3'])                     # the root is in another tab: the piece stands for it
        self.assertEqual(out[3], [])

    def test_the_card(self):
        card, parts, tell = fn('itemCard'), fn('partsLine'), fn('showTell')
        self.assertIn('const idea = ideaOf(i);', card)
        self.assertIn('idea ? openPart(idea.root) : openDetail(i)', card)
        self.assertIn('h.textContent = idea ? idea.title : i.title;', card)
        self.assertIn('if (idea) c.append(partsLine(i));', card)
        self.assertLess(card.index('showTell(i)'), card.index('partsLine(i)'))
        self.assertLess(card.index('partsLine(i)'), card.index('actionArea(i)'))
        self.assertIn('i = ideaOf(i) || i;', tell)                       # the root's pitch and pictures
        self.assertIn('`${n} parts`', parts)
        self.assertIn("b.setAttribute('aria-expanded', String(on))", parts)
        self.assertIn('ul.hidden = !on', parts)
        self.assertIn('openPart(p)', parts)
        self.assertIn('partsOpen', parts)                                # stays open through the 30-second repaint
        self.assertNotIn('innerHTML', parts)
        self.assertIn('cardsOf(p.id)[0]', fn('openPart'))
        self.assertIn('api/issue?repo=', fn('openPart'))

    def test_lists_and_counts_use_ideas(self):
        self.assertIn('groups.show = onePerIdea(groups.show);', fn('render'))
        self.assertLess(fn('render').index('onePerIdea(groups.show)'), fn('render').index('strip(d, bins, groups)'))   # the strip counts ideas
        self.assertIn('return onePerIdea(out);', fn('mineIn'))           # 0.50.0: the orange counts on the tab and the stage

    def test_approve_all_parts(self):
        if not shutil.which('node'):
            self.skipTest('node missing')
        stub = """
class N { constructor(t){this.tag=t;this.children=[];this.classList={add:()=>{}};this.textContent='';}
  append(...c){this.children.push(...c);} addEventListener(){} setAttribute(){} }
const make = (t, c, x) => { const n = new N(t); n.className = c; if (x !== undefined) n.textContent = x; return n; };
const asked = [];
const smallBtn = (t, f) => { const b = make('button', 'bd-mini', t); b.go = f; return b; };
const askPop = (b, text, yes) => asked.push([text, yes]);
const noteAsk = (row, ph, yes) => asked.push([ph, yes]);
const tryState = () => ({}), tryToggle = () => null;   // 0.48.1: these items have no switch
const waitHead = () => null;   // 0.49.0: no 'Waiting on' line on these
"""
        src = stub + fn('ideaOf') + fn('actionArea') + """
const p = n => Array.from({length: n}, (_, k) => ({id: 'o/r#' + k, title: 't' + k}));
for (const parts of [p(10), p(1), undefined]) {
  const a = actionArea({group: 'show', kind: 'feature', category: 'core', decider: 'James', can_decide: true, idea: 'o/r#0', parts}, false);
  a.children.forEach(b => b.go(b));
}
const quiet = actionArea({group: 'show', kind: 'feature', decider: 'James', can_decide: false, idea: 'o/r#0', parts: p(3)}, false);
console.log(JSON.stringify([asked, quiet.children.map(x => x.textContent)]));"""
        out = json.loads(subprocess.run(['node', '-e', src], capture_output=True, text=True, check=True).stdout)
        one = [['Approve? The builder turns it on for everyone and closes it.', 'Approve'], ['Why not? (optional)', 'Decline']]
        self.assertEqual(out[0], [['Approve all 10 parts? The builder turns it on for everyone and closes it.', 'Approve'],
                                  ['Why not? (optional)', 'Decline all 10 parts'], *one, *one])   # one part: the 0.47.0 words
        self.assertEqual(out[1], ['James decides'])

    def test_decide_takes_the_whole_idea_and_names_failed_parts(self):
        act = fn('decideAct')
        self.assertIn('sameIdea(x, i)', act)
        self.assertIn('ids.has(openId)', act)
        self.assertIn("filter(p => !p.ok && !p.skipped).map(p => p.id)", act)
        self.assertIn('if (bad.has(x.id))', act)                                   # the refused parts come back
        self.assertIn('`Couldn’t save that: ${bad.size} of ${r.parts.length} parts could not be updated.`', act)
        self.assertIn("'Approved: the builder turns it on for everyone.'", act)   # the 0.45.0 toasts stay
        self.assertIn("const sameIdea = (x, i) => x.id === i.id || (x.group === 'show' && i.group === 'show' && !!i.idea && x.idea === i.idea);", JS)

    def test_styles(self):
        new = CSS[CSS.index('/* 0.48.0'):]
        for cls in ('.bd-parts-b', '.bd-parts-l', '.bd-part ', '.bd-part-r'):
            self.assertIn(cls, new)
        self.assertIn('.bd-parts-l[hidden] { display: none; }', new)
        self.assertIn('overflow-wrap: anywhere', re.search(r'\.bd-part \{[^}]*\}', new).group(0))
        self.assertIsNone(re.search(r'#[0-9a-fA-F]{3,8}\b|rgba?\(', new))
        self.assertIsNone(re.search(r'font-size:\s*[\d.]+px', new))

    def test_node_check(self):
        if not shutil.which('node'):
            self.skipTest('node missing')
        subprocess.run(['node', '--check', str(ROOT / 'web' / 'app.js')], check=True)


class Docs(unittest.TestCase):
    def test_version_and_words(self):
        self.assertGreaterEqual(tuple(int(x) for x in S.VERSION.split('.'))[:2], (0, 48))
        self.assertIn(f"const PAGE_VERSION = '{S.VERSION}';", JS)
        api = json.loads((ROOT / 'openapi.json').read_text())
        self.assertIn('counts and ideas count ideas, not pieces', api['paths']['/api/decisions']['get']['summary'])
        self.assertIn('deciding any part decides the whole idea', api['paths']['/api/decide']['post']['summary'])
        skill = (ROOT / 'skill' / 'SKILL.md').read_text()
        self.assertIn('deciding any part decides the whole idea', skill)
        self.assertIn('**0.48.0**', (ROOT / 'wizard.md').read_text())
        tools = {t['name']: t['description'] for t in S.TOOLS}
        self.assertIn('Deciding any part decides the whole idea', tools['board_decide'])
        self.assertIn('count ideas, not pieces', tools['decisions_list'])


if __name__ == '__main__':
    unittest.main()
