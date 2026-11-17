"""0.37.3: Update all runs up to three apps side by side."""
import unittest
from pathlib import Path
JS = (Path(__file__).resolve().parent.parent / 'web/app.js').read_text()

class Parallel(unittest.TestCase):
    def test_three_at_a_time(self):
        body = JS[JS.index('async function updateAll'):JS.index('async function updateWizardOS(')]
        self.assertIn('Math.min(3, queue.length)', body)
        self.assertNotIn('for (const a of list) await updateApp', body)
