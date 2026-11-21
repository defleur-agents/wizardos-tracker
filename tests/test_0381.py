"""0.38.1 (James, humanitylabs-org/wizardos-tracker#109): Works / Needs changes / Still broken update the card at once.
The card leaves its stage before the back end answers; the request runs in the background; only a failure puts the
card back (same place) with a clear message, and keeps a Needs changes note for the retry. Runs the page's own code.
Run: python3 -m unittest discover -s tests"""
import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path

JS = (Path(__file__).resolve().parent.parent / 'web/app.js').read_text()


def block():
    a = JS.index('const pendingChecks = new Set();')
    b = JS.index('// 0.45.0 (Miguel, 21 Nov): Approve / Decline at a show-and-tell')
    return JS[a:b]


HARNESS = r"""
const log = [];
let view = 'bugs', openId = null, renders = 0;
const NO_WORD = i => (i && i.kind === 'bug' ? 'Still broken' : 'Needs changes');
const cache = { bugs: { groups: { test: [{ id: 'o/r#1', title: 'One' }, { id: 'o/r#2', title: 'Two', kind: 'bug', repo: 'o/r', number: 2 }, { id: 'o/r#3', title: 'Three' }], done: [] } },
                core: { groups: { james: [{ id: 'o/r#9' }] } } };
const details = new Map([['o/r#2', 1]]), onbox = new Map(), doneCache = {};
const el = id => ({ open: false });
const WzSheet = { close() {} }, closeApp = () => {}, hold = () => {}, unpop = () => {};
const render = () => { renders++; };
const toast = t => log.push(['toast', t]);
const say = (t, k) => log.push(['say', t, k]);
let loads = 0; const load = () => { loads++; };
let settle; const calls = [];
const api = (path, body) => { calls.push([path, body]); return new Promise((res, rej) => { settle = { res, rej }; }); };
const setTimeout = f => f();
const ids = () => cache.bugs.groups.test.map(x => x.id);
""" 


@unittest.skipUnless(shutil.which('node'), 'node missing')
class Optimistic(unittest.TestCase):
    def run_js(self, body):
        src = HARNESS + block() + '\n(async () => {\n' + body + '\n})().catch(e => { console.error(e); process.exit(1); });'
        out = subprocess.run(['node', '-e', src], capture_output=True, text=True, timeout=30)
        self.assertEqual(out.returncode, 0, out.stderr)
        return json.loads(out.stdout)

    def test_works_moves_card_before_the_back_end_answers_then_stays(self):
        got = self.run_js("""
const item = cache.bugs.groups.test[1];
const ret = tested(item, true, '', null);
const during = { ids: ids(), renders, toast: log.slice(), calls: calls.length };
settle.res({ ok: true });
await new Promise(r => process.nextTick(r)); await null;
console.log(JSON.stringify({ ret, during, after: ids(), details: details.has('o/r#2'), loads }));""")
        self.assertTrue(got['ret'])                                   # returns at once, not a promise to wait on
        self.assertEqual(got['during']['ids'], ['o/r#1', 'o/r#3'])     # gone the same frame
        self.assertGreaterEqual(got['during']['renders'], 1)
        self.assertEqual(got['during']['toast'], [['toast', 'Thanks — tagged Checked by you.']])
        self.assertEqual(got['during']['calls'], 1)
        self.assertEqual(got['after'], ['o/r#1', 'o/r#3'])
        self.assertFalse(got['details'])
        self.assertEqual(got['loads'], 1)

    def test_failure_rolls_back_in_place_with_a_clear_message(self):
        got = self.run_js("""
const item = cache.bugs.groups.test[1];
tested(item, true, '', null);
const during = ids();
settle.rej(new Error('GitHub said no.'));
await new Promise(r => setImmediate(r));
console.log(JSON.stringify({ during, after: ids(), log }));""")
        self.assertEqual(got['during'], ['o/r#1', 'o/r#3'])
        self.assertEqual(got['after'], ['o/r#1', 'o/r#2', 'o/r#3'])   # back where it was
        msgs = [m[1] for m in got['log'] if m[0] == 'toast']
        self.assertEqual(msgs[-1], 'Works wasn’t saved, so “Two” is back: GitHub said no.')
        self.assertIn(['say', msgs[-1], 'error'], got['log'])

    def test_needs_changes_keeps_the_note_on_failure(self):
        got = self.run_js("""
const item = cache.bugs.groups.test[0];
tested(item, false, 'Still choppy', null);
const sent = calls[0];
settle.rej(new Error('Offline.'));
await new Promise(r => setImmediate(r));
console.log(JSON.stringify({ sent, kept: keptNotes.get('o/r#1'), after: ids(), last: log[log.length - 1] }));""")
        self.assertEqual(got['sent'][0], 'api/test/fails')
        self.assertEqual(got['sent'][1]['note'], 'Still choppy')
        self.assertEqual(got['kept'], 'Still choppy')
        self.assertEqual(got['after'], ['o/r#1', 'o/r#2', 'o/r#3'])
        self.assertEqual(got['last'][1], 'Needs changes wasn’t saved, so “One” is back: Offline. Your note is kept.')

    def test_a_reload_while_saving_does_not_bring_the_card_back(self):
        got = self.run_js("""
tested(cache.bugs.groups.test[2], true, '', null);
const fresh = dropPending({ groups: { test: [{ id: 'o/r#1' }, { id: 'o/r#3' }] } });
const second = tested({ id: 'o/r#3' }, true, '', null);
settle.res({});
await new Promise(r => setImmediate(r));
const later = dropPending({ groups: { test: [{ id: 'o/r#3' }] } });
console.log(JSON.stringify({ fresh: fresh.groups.test.map(x => x.id), second, calls: calls.length, later: later.groups.test.map(x => x.id) }));""")
        self.assertEqual(got['fresh'], ['o/r#1'])
        self.assertTrue(got['second'])
        self.assertEqual(got['calls'], 1)                            # a double tap doesn't send twice
        self.assertEqual(got['later'], ['o/r#3'])                    # saved: the server's word counts again

    def test_wiring(self):
        self.assertIn('cache[which] = dropPending(d);', JS)
        self.assertIn("prefill: keptNotes.get(i.id) || ''", JS)
        self.assertNotIn('async function tested(', JS)
        self.assertNotIn("const done = works ? busyOn(b)", JS)


if __name__ == '__main__':
    unittest.main()
