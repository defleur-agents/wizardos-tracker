"""0.36.6 (James, 17 Nov): Building is its own Core stage again (wizardos-tracker: Build queue -> Building), the sheet's
confirm popover stays inside the sheet (#102), and an open item waiting for its check has one finishing action, Works (#103).
Run: python3 -m unittest discover -s tests"""
import json
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JS = (ROOT / 'web/app.js').read_text()


def fn(name):
    start = JS.index('function ' + name + '(')
    depth, i = 0, JS.index('{', start)
    while True:
        depth += {'{': 1, '}': -1}.get(JS[i], 0)
        i += 1
        if depth == 0:
            return JS[start:i]


def const(name):
    start = JS.index('const ' + name + ' = ')
    return JS[start:JS.index(';\n', start) + 1]


@unittest.skipUnless(shutil.which('node'), 'node missing')
class UI(unittest.TestCase):
    def run_js(self, src):
        return json.loads(subprocess.run(['node', '-e', src], capture_output=True, text=True, check=True).stdout)

    def test_core_has_building_apart_from_the_queue(self):
        src = fn('binsOf') + """
const b = binsOf('core');
console.log(JSON.stringify(b.map(x => [x.key, x.word, x.groups])));"""
        bins = self.run_js(src)
        q = next(x for x in bins if x[0] == 'queued')
        self.assertEqual(q[1], 'Queued')   # 0.49.0: one word on every tab
        bl = next(x for x in bins if x[1] == 'Building')
        self.assertEqual(q[2], ['sorting', 'queued'])   # 0.40.0: new core items being sorted wait for the builder, not for approval
        self.assertEqual(bl[2], ['building'])
        self.assertEqual([x[0] for x in bins].index('building'), [x[0] for x in bins].index('queued') + 1)
        self.assertEqual(len({x[0] for x in bins}), len(bins))       # stage keys stay unique

    def test_popover_stays_inside_the_sheet(self):
        # A sheet docked on the right (46vw of 1280 = 589px wide, from x=691); Works sits near its left edge.
        src = ("const innerWidth = 1280, innerHeight = 800, document = { body: {} };\n" + fn('popRoom') + '\n'
               + const('popLeft') + """
const sheet = { getBoundingClientRect: () => ({ left: 691, right: 1280, top: 0, bottom: 800 }) };
const r = { left: 700, width: 60, top: 400, bottom: 430 };
const room = popRoom(sheet), w = Math.min(260, room.hi - room.lo), x = popLeft(r, w, room.lo, room.hi);
const narrow = { getBoundingClientRect: () => ({ left: 1100, right: 1280, top: 0, bottom: 800 }) };
const rn = popRoom(narrow), wn = Math.min(260, rn.hi - rn.lo), xn = popLeft({ left: 1110, width: 50 }, wn, rn.lo, rn.hi);
const body = popRoom(document.body);
console.log(JSON.stringify([x, w, xn, wn, rn.lo, rn.hi, body.lo, body.hi]));""")
        x, w, xn, wn, lo, hi, blo, bhi = self.run_js(src)
        self.assertGreaterEqual(x, 691 + 12)                          # fail-old: the viewport clamp put it at 600
        self.assertLessEqual(x + w, 1280 - 12)
        self.assertGreaterEqual(xn, lo)
        self.assertLessEqual(xn + wn, hi)                             # a narrow panel: narrower popover, still inside
        self.assertEqual([blo, bhi], [12, 1268])                      # outside a sheet: the viewport, as before

    def test_check_has_one_finishing_action(self):
        src = "let openItem = null;\n" + fn('checkFinishes') + """
const open = { state: 'open', kind: 'bug' }, shut = { state: 'closed', kind: 'bug' };
console.log(JSON.stringify([
  checkFinishes({ kind: 'bug', shipped: true, can_review: true }, open),
  checkFinishes({ kind: 'bug', shipped: true, can_review: true, state_reason: 'not_planned' }, open),
  checkFinishes({ kind: 'bug', shipped: true, can_review: true }, shut),
  checkFinishes({ kind: 'feature', group: 'test' }, { state: 'open', kind: 'feature' }),
  checkFinishes({ kind: 'feature', group: 'test', nextrel: true }, { state: 'open', kind: 'feature' }),
  checkFinishes({ kind: 'feature', group: 'queued' }, { state: 'open', kind: 'feature' }),
  checkFinishes({ kind: 'goal', group: 'test' }, { state: 'open', kind: 'goal' }),
  checkFinishes(null, open)]));"""
        self.assertEqual(self.run_js(src), [True, False, False, True, False, False, False, False])
        self.assertIn('checkFinishes(d && openItem && openItem.id === d.id ? openItem : null, d)', fn('closeCtl'))

    def test_works_says_it_closes(self):
        self.assertNotIn('It stays on its release path.', JS)
        self.assertIn('Mark as works? It closes as fixed, tagged Checked by you.', JS)


if __name__ == '__main__':
    unittest.main()
