"""Tracker 0.36.0 (Miguel, 15 Nov: "Robert must get unstuck himself with one tap"): a stopped app has Start in Settings,
and an update that ends with the app stopped or on its old version is started and retried once by the Tracker itself.
The flow runs for real in node against a fake App Manager (the code is cut from web/app.js, nothing re-typed).
Run: python3 -m unittest discover -s tests"""
import json
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JS = (ROOT / 'web/app.js').read_text()

HARNESS = r'''
const vm = require('vm');
const [src, raw] = process.argv.slice(-2), scen = JSON.parse(raw);
const calls = [], runsSeen = [];
let apps = JSON.parse(JSON.stringify(scen.apps)), installedNew = false;
const answers = scen.answers;   // "METHOD path" -> list of answers, the last one repeats
function answer(key) {
  const q = answers[key]; if (!q) { const e = new Error('not found'); e.status = 404; throw e; }
  const a = q.length > 1 ? q.shift() : q[0];
  if (a.body && a.body.state === 'installed') installedNew = true;
  if (a.set) for (const [id, kv] of Object.entries(a.set)) Object.assign(apps.find(x => x.id === id), kv);
  if (a.http) { const e = new Error(a.body.error); e.status = a.http; throw e; }
  return JSON.parse(JSON.stringify(a.body));
}
const ctx = {
  console, Map, Set, JSON, Math, String, Error, Promise, Object, encodeURIComponent, Number, Date,
  setTimeout: (f) => 0,
  STORE_INSTALL: '/wizard-os-home/store-install/', UPD_STEPS: ['Starting', 'Installing', 'Restarting', 'Done'],
  catalog: null, me: { version: '0.36.0' }, facts: { apps: {} }, wizFail: {}, wizBusy: new Map(), runs: new Map(),
  onbox: new Set(), cache: {}, view: 'bugs', store: { set() {}, get() {} },
  busyOn: () => () => {}, pop: (b, t, x) => calls.push('pop ' + x), toast() {}, paintWizards() {}, render() {}, checkOnBox() {},
  jobDetail: () => '',
  loadCatalog: async () => { ctx.catalog = { apps: JSON.parse(JSON.stringify(apps)) }; return ctx.catalog; },
  STORE_DATA: '/wizard-os-home/store-data/',
  // 0.37.2: the App Manager's list is how an update is judged done (the new commit, running)
  getJSON: async (u, init) => { if (u === '/wizard-os-home/store-data/wizard/v1/installed-apps') return { wam: apps.map(a => ({ id: a.id, status: a.status,
      version: installedNew ? a.latest : a.version, commit: installedNew && a.release ? a.release.commit : 'a'.repeat(40) })) };
    const key = (init && init.method || 'GET') + ' ' + u; calls.push(key + (init ? ' ' + init.body : '')); return answer(key); },
  newRun: (key, name, to, item, retry) => { const r = { key, name, to, step: 'Starting', detail: '', state: 'running', reason: '', retry, trail: [] }; runsSeen.push(r); ctx.runs.set(key, r); return r; },
  runStep: (r, step, detail) => { if (r.trail[r.trail.length - 1] !== step) r.trail.push(step); r.step = step; r.detail = detail || ''; },
  runEnd: (r, ok, reason) => { r.state = ok ? 'done' : 'failed'; r.reason = reason || ''; },
};
vm.createContext(ctx);
vm.runInContext(src.replace('const sleep = ms => new Promise(r => setTimeout(r, ms));', 'const sleep = ms => Promise.resolve();')
  + '\nthis.updateApp_ = updateApp_;', ctx);
ctx.updateApp_(scen.id, null, null).then(() => {
  const r = runsSeen[0] || {};
  console.log(JSON.stringify({ calls, state: r.state, reason: r.reason, trail: r.trail, steps: r.steps, kind: r.kind,
                               recovered: !!r.recovered, retry: typeof r.retry, fail: ctx.wizFail }));
}, e => { console.log(JSON.stringify({ crash: String(e && e.stack || e), calls })); });
'''

UPD = 'POST /wizard-os-home/store-install/messenger'
JOB = 'GET /wizard-os-home/store-install/messenger'
START = 'POST /wizard-os-home/store-install/_start/messenger'
SJOB = 'GET /wizard-os-home/store-install/_start/messenger'
HEALTH = 'GET /messenger/healthz'
REL = {'source': 'standard', 'repo': 'humanitylabs-org/messenger', 'commit': 'b' * 40}


def app(status='running', update=True):
    return {'id': 'messenger', 'name': 'Messenger', 'version': '0.2.0-unified.16.31', 'latest': '0.2.0-unified.16.53',
            'status': status, 'update': update, 'release': REL if update else None, 'pinned': False}


def run(apps, answers, id='messenger'):
    a, b = JS.index('const sleep = ms =>'), JS.index('async function updateAll(btn)')
    p = subprocess.run(['node', '-e', HARNESS, '--', JS[a:b], json.dumps({'id': id, 'apps': apps, 'answers': answers})],
                       capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, p.stderr
    out = json.loads(p.stdout.strip().splitlines()[-1])
    assert 'crash' not in out, out
    return out


def ok(body):
    return {'body': body}


class Recover(unittest.TestCase):
    def test_robert_update_ends_stopped_then_tracker_starts_and_retries_once(self):
        """What happened to Robert: the first update ends with Messenger stopped on its old version."""
        out = run([app()], {
            UPD: [ok({'app': 'messenger', 'state': 'installing'}),
                  ok({'app': 'messenger', 'state': 'installing'})],
            JOB: [ok({'state': 'installing'}),
                  {'body': {'state': 'failed', 'error': 'finished as stopped'}, 'set': {'messenger': {'status': 'stopped'}}},
                  ok({'state': 'installing'}),
                  {'body': {'state': 'installed', 'status': 'running'}, 'set': {'messenger': {'status': 'running'}}}],
            START: [{'body': {'app': 'messenger', 'state': 'starting'}, 'set': {'messenger': {'status': 'running'}}}],
            SJOB: [ok({'state': 'running', 'status': 'running'})],
            HEALTH: [ok({'version': '0.2.0-unified.16.53'})],
        })
        self.assertEqual(out['state'], 'done', out)
        self.assertTrue(out['recovered'])
        kinds = [('start' if c.startswith(START) else 'update') for c in out['calls'] if c.startswith('POST')]
        self.assertEqual(kinds, ['update', 'start', 'update'], 'update, start it, update once more; never a third')
        for step in ('Installing', 'Starting app', 'Trying again', 'Restarting'):
            self.assertIn(step, out['trail'])
        self.assertEqual(out['steps'], ['Starting', 'Installing', 'Starting app', 'Trying again', 'Restarting', 'Done'])

    def test_update_installed_but_app_stopped_is_recovered(self):
        out = run([app()], {
            UPD: [{'body': {'state': 'installed', 'status': 'stopped'}, 'set': {'messenger': {'status': 'stopped'}}},
                  {'body': {'state': 'installed', 'status': 'running'}, 'set': {'messenger': {'status': 'running'}}}],
            START: [{'body': {'state': 'running', 'status': 'running'}, 'set': {'messenger': {'status': 'running'}}}],
            HEALTH: [ok({'version': '0.2.0-unified.16.53'})],
        })
        self.assertEqual(out['state'], 'done', out)
        self.assertEqual(sum(c.startswith(UPD + ' ') for c in out['calls']), 2)

    def test_second_failure_is_one_line_and_retry_never_a_third_update(self):
        out = run([app()], {
            UPD: [{'body': {'state': 'failed', 'error': 'pull failed: no space left on device\nmore'}, 'set': {'messenger': {'status': 'stopped'}}}],
            START: [{'body': {'state': 'running'}, 'set': {'messenger': {'status': 'running'}}}],
        })
        self.assertEqual(out['state'], 'failed')
        self.assertEqual(out['reason'], 'pull failed: no space left on device')
        self.assertEqual(out['retry'], 'function', 'a Retry button')
        self.assertEqual(sum(c.startswith(UPD + ' ') for c in out['calls']), 2)

    def test_lost_or_still_running_update_is_never_retried_on_top(self):
        out = run([app()], {UPD: [ok({'state': 'installing'})], JOB: [{'http': 404, 'body': {'error': 'no install for that app'}}]})
        self.assertEqual(out['state'], 'failed')
        self.assertIn('lost track', out['reason'])
        self.assertEqual(sum(c.startswith(UPD + ' ') for c in out['calls']), 1)
        self.assertFalse(any(c.startswith(START) for c in out['calls']))

    def test_app_manager_still_updating_refuses_start_and_it_is_said(self):
        out = run([app()], {
            UPD: [{'body': {'state': 'failed', 'error': 'finished as updating'}, 'set': {'messenger': {'status': 'stopped'}}}],
            START: [{'http': 409, 'body': {'error': 'this app is being installed or updated; wait for that to finish'}}],
        })
        self.assertEqual(out['state'], 'failed')
        self.assertIn('wait for that to finish', out['reason'])
        self.assertEqual(sum(c.startswith(UPD + ' ') for c in out['calls']), 1)


    def test_never_a_second_update_while_the_app_manager_still_updates(self):
        out = run([app()], {
            UPD: [{'body': {'state': 'failed', 'error': 'messenger is still updating after 61 min'}, 'set': {'messenger': {'status': 'updating'}}}],
        })
        self.assertEqual(out['state'], 'failed')
        self.assertIn('Messenger is still updating', out['reason'])
        self.assertEqual(sum(c.startswith(UPD + ' ') for c in out['calls']), 1)
        self.assertFalse(any(c.startswith(START) for c in out['calls']))


class Start(unittest.TestCase):
    def test_stopped_app_starts_with_one_tap(self):
        out = run([app('stopped', update=False)], {
            START: [ok({'state': 'starting'})], SJOB: [ok({'state': 'starting'}), {'body': {'state': 'running', 'status': 'running'}, 'set': {'messenger': {'status': 'running'}}}],
            HEALTH: [ok({'version': '0.2.0-unified.16.31'})],
        })
        self.assertEqual(out['state'], 'done', out)
        self.assertEqual(out['kind'], 'start')
        self.assertIn(START + ' {}', out['calls'])
        self.assertFalse(any(c.startswith(UPD) for c in out['calls']))
        self.assertEqual(out['steps'], ['Starting app', 'Restarting', 'Done'])

    def test_stopped_and_behind_starts_then_updates(self):
        out = run([app('stopped')], {
            START: [{'body': {'state': 'running'}, 'set': {'messenger': {'status': 'running'}}}],
            UPD: [ok({'state': 'installed', 'status': 'running'})],
            HEALTH: [ok({'version': '0.2.0-unified.16.53'})],
        })
        self.assertEqual(out['state'], 'done', out)
        self.assertLess(out['calls'].index(START + ' {}'), next(i for i, c in enumerate(out['calls']) if c.startswith(UPD)))
        self.assertEqual(out['steps'], ['Starting app', 'Installing', 'Restarting', 'Done'])
        self.assertFalse(out['recovered'])

    def test_older_app_manager_without_start_says_update_wizardos(self):
        for http, err in ((400, 'bad app id'), (404, 'not found')):
            out = run([app('stopped', update=False)], {START: [{'http': http, 'body': {'error': err}}]})
            self.assertEqual(out['state'], 'failed')
            self.assertIn('update WizardOS, then tap Start', out['reason'])

    def test_failed_start_says_why(self):
        out = run([app('stopped', update=False)], {START: [ok({'state': 'failed', 'error': 'start did not finish (status stopped)'})]})
        self.assertEqual(out['state'], 'failed')
        self.assertEqual(out['reason'], 'Messenger didn’t start: start did not finish (status stopped)')


class Page(unittest.TestCase):
    def test_settings_row_offers_start(self):
        self.assertIn("(stop ? (a.update ? 'Start and update' : 'Start') : 'Update')", JS)
        self.assertIn('Tap Start on', JS)
        self.assertNotIn('ask your Wizard to start', JS)

    def test_settings_shows_the_run_under_its_row(self):
        body = JS[JS.index('function paintWizards'):]
        self.assertIn("const pnl = updPanel(run, null); pnl.classList.add('bd-wiz-run'); list.append(pnl);", body)
        self.assertLess(body.index('Tap Start on'), body.index("const list = make('div', 'bd-list rows bd-wiz-apps')"))
        self.assertIn("f.kind === 'start' ? `${f.name || id} didn’t start", body)

    def test_waits_longer_than_the_app_manager(self):
        self.assertIn('const UPDATE_WAIT_MS = 35 * 60000;', JS)

    def test_panel_says_start_and_retry(self):
        body = JS[JS.index('function updPanel'):]
        self.assertIn("smallBtn('Retry'", body)
        self.assertIn('`Starting ${r.name}`', body)
        self.assertIn("setProperty('--n', steps.length)", body)


if __name__ == '__main__':
    unittest.main()
