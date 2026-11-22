"""Tracker 0.53.0 (Miguel, 22 Nov 2026): 'James approves' pressed by anyone; no Mark done."""
import pathlib, unittest
ROOT = pathlib.Path(__file__).resolve().parents[1]
JS = (ROOT / 'web' / 'app.js').read_text(); SRV = (ROOT / 'app' / 'server.py').read_text()


class Behalf(unittest.TestCase):
    def test_button(self):
        self.assertIn("i.can_behalf", JS)
        self.assertIn("approves`, b => askPop", JS)
        self.assertIn("on_behalf: true", JS)

    def test_server(self):
        self.assertIn("'can_behalf': behalf", SRV)
        self.assertIn("pressed on {decider}\\u2019s behalf by", SRV)
        self.assertIn("'not_behalf'", SRV)

    def test_no_mark_done(self):
        self.assertIn("(d.state !== 'closed' && d.kind !== 'goal')", JS)


if __name__ == '__main__':
    unittest.main()
