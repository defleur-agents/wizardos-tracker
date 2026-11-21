"""0.43.1 (21 Nov 2026): the item sheet's always-present reply box (form.bd-fail.bd-d-reply, 0.42.0) made typing() true,
so load() never drew the list. Run: python3 -m unittest discover -s tests"""
import json
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JS = (ROOT / 'web' / 'app.js').read_text()
HTML = (ROOT / 'web' / 'index.html').read_text()


@unittest.skipUnless(shutil.which('node'), 'node missing')
class Typing(unittest.TestCase):
    def run_typing(self, forms):
        line = next(l for l in JS.splitlines() if l.startswith('const typing = '))
        src = ("const document = { querySelector(sel) { const m = /^\\.bd-fail(?::not\\(\\.([\\w-]+)\\))?$/.exec(sel);"
               " return FORMS.find(c => c.includes('bd-fail') && !(m[1] && c.includes(m[1]))) || null; } };\n"
               f"const FORMS = {json.dumps(forms)};\n{line}\nconsole.log(JSON.stringify(typing()));")
        return json.loads(subprocess.run(['node', '-e', src], capture_output=True, text=True, check=True).stdout)

    def test_reply_box_alone_is_not_typing(self):
        self.assertIn('class="bd-fail bd-d-reply"', HTML)   # the static form that caused it
        self.assertFalse(self.run_typing(['bd-fail bd-d-reply']))

    def test_open_note_still_holds_redraws(self):
        self.assertTrue(self.run_typing(['bd-fail bd-d-reply', 'bd-fail bd-confirm']))
        self.assertTrue(self.run_typing(['bd-fail bd-confirm bd-sform']))


if __name__ == '__main__':
    unittest.main()
