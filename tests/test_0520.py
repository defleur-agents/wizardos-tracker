"""Tracker 0.52.0 (Miguel, 22 Nov 2026): a card opens on what to do; the history is folded and easy to read."""
import pathlib, unittest
ROOT = pathlib.Path(__file__).resolve().parents[1]
JS = (ROOT / 'web' / 'app.js').read_text()
HTML = (ROOT / 'web' / 'index.html').read_text()
CSS = (ROOT / 'web' / 'styles.css').read_text()


class CardFirst(unittest.TestCase):
    def test_link_waits_for_its_tab(self):
        self.assertIn('else if (!first) await listIn(want || view);', JS)

    def test_history_starts_folded(self):
        self.assertIn("checkMode(true);   // 0.52.0", JS)
        self.assertIn('Show details and history', HTML)
        self.assertIn('#d-reply:not(.bd-d-reply-ask)', CSS)

    def test_final_approval_shows_pitch_in_sheet(self):
        self.assertIn("i.group === 'show' ? showTell(i) : []", JS)

    def test_history_reads_easily(self):
        self.assertIn('function foldLong(box)', JS)
        self.assertIn("bot ? 'Builder' : nameOf(c.author)", JS)

    def test_changelog(self):
        self.assertIn('**0.52.0**', (ROOT / 'wizard.md').read_text())


if __name__ == '__main__':
    unittest.main()
