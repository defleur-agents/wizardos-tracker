// Tracker 0.50.1 fixture (run in the real page by tests/test_0501.py): the update banner. Each thing with an update has
// its own Update; every update that runs is shown; a WizardOS update that failed last time says why and is left out of
// Update all; an app update waits while WizardOS installs. The App Manager is stood in for: nothing is installed.
(async () => {
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  // the box answers only for the WizardOS state; everything else never answers, so the fixture's own data stays put
  window.fetch = u => String(u).includes('store-install/_updates') ? Promise.resolve(new Response(JSON.stringify(updates), { status: 200, headers: { 'Content-Type': 'application/json' } })) : new Promise(() => {});
  localStorage.clear(); wizFail = {};
  const app = (id, name, version, latest) => ({ id, name, version, latest, update: true, status: 'running', release: { version: latest } });
  const OS_BAD = { channel: 'latest', installed: null, latest: '0.3.362', update_available: true, installing: false, failed: true, retry_target: '0.3.358',
    failure_reason: 'wizard-agent-service: update to release source failed' };
  const OS_OK = { channel: 'latest', installed: '0.3.350', latest: '0.3.362', update_available: true, installing: false, failed: false };
  const calls = [], peak = { n: 0 };
  let appMs = 250, appFails = {};
  loadCatalog = async () => catalog;
  resumeRuns = async () => {};
  checkVersion = async () => {};
  updateApp_ = async id => {
    calls.push(id);
    const a = fresh(id), r = newRun(id, a.name, a.latest);
    peak.n = Math.max(peak.n, [...runs.values()].filter(x => x.state === 'running').length);
    await sleep(appMs);
    if (appFails[id]) { wizFail[id] = { at: Date.now(), name: a.name, to: a.latest, reason: appFails[id], kind: 'update' }; runEnd(r, false, appFails[id]); }
    else { a.update = false; a.version = a.latest; delete wizFail[id]; runEnd(r, true); }
  };
  updateWizardOS = async btn => { calls.push('os' + (btn ? ':tap' : '')); const r = newRun('os', 'WizardOS', updates.latest); await sleep(150); updates = { ...updates, installed: updates.latest, update_available: false }; runEnd(r, true); };
  const reset = (apps, os) => { runs.clear(); wizBusy.clear(); wizFail = {}; localStorage.clear(); queue = null; calls.length = 0; peak.n = 0; appFails = {}; catalog = { apps }; updates = os; selfUpdate(); };
  const tx = n => n ? n.textContent.replace(/\s+/g, ' ').trim() : null;
  const read = () => { const b = el('selfupd'); return { hidden: b.hidden, title: tx(b.querySelector('span.bd-selfupd-t')), all: tx(el('selfupd-go')),
    rows: [...b.querySelectorAll('.bd-selfupd-row')].map(r => [r.dataset.updRow, tx(r.querySelector('.bd-selfupd-n')), tx(r.querySelector('button'))]),
    why: Object.fromEntries([...b.querySelectorAll('[data-upd-why]')].map(p => [p.dataset.updWhy, tx(p)])),
    panels: [...b.querySelectorAll('.bd-upd')].map(p => [p.dataset.upd, p.className.replace('bd-upd ', '')]), q: tx(el('selfupd-q')),
    notes: [...b.querySelectorAll('p.bd-upd-note.bd-selfupd-q')].map(tx), calls: calls.slice() }; };
  const idle = async () => { for (let i = 0; i < 100 && (draining || [...runs.values()].some(r => r.state === 'running')); i++) await sleep(50); await sleep(60); };
  const one = k => el('selfupd').querySelector(`[data-upd-one="${k}"]`);
  const out = {};

  // 1. this Wizard today: two apps and a WizardOS update that failed last time
  reset([app('wizard-tinfoil', 'Tinfoil', '0.3.16', '0.3.17'), app('wisdom', 'Wisdom', '0.4.38', '0.4.39')], OS_BAD);
  out.offered = read();
  one('wizard-tinfoil').click(); await sleep(80);
  out.oneRunning = read();
  await idle();
  out.oneDone = read();

  // 2. Update all on the same Wizard: the apps, never the WizardOS update that failed
  reset([app('wizard-tinfoil', 'Tinfoil', '0.3.16', '0.3.17'), app('wisdom', 'Wisdom', '0.4.38', '0.4.39')], OS_BAD);
  el('selfupd-go').click(); await sleep(80);
  out.allBadRunning = read();
  await idle();
  out.allBadDone = read();

  // 3. a healthy Wizard: four apps and WizardOS. Three at a time, all three shown, WizardOS after the apps
  reset([app('a1', 'Alpha', '1', '2'), app('a2', 'Beta', '1', '2'), app('a3', 'Gamma', '1', '2'), app('a4', 'Delta', '1', '2')], OS_OK);
  out.healthy = read();
  el('selfupd-go').click(); await sleep(80);
  out.allRunning = read(); out.peak = peak.n;
  await idle();
  out.allDone = read();

  // 4. one that fails keeps its line, its reason and a Retry
  reset([app('a1', 'Alpha', '1', '2'), app('a2', 'Beta', '1', '2')], { ...OS_OK, update_available: false });
  appFails = { a2: 'Beta 2 did not work; 1 still runs' };
  el('selfupd-go').click(); await idle();
  out.oneFailed = read();

  // 5. an app update waits while WizardOS installs
  reset([app('a1', 'Alpha', '1', '2')], { ...OS_OK, installing: true });
  queueStart([{ key: 'a1', name: 'Alpha' }]); await sleep(300);
  out.held = read();
  updates = { ...OS_OK, installing: false, update_available: false, installed: '0.3.362' };
  for (let i = 0; i < 100 && !calls.length; i++) await sleep(50);
  await idle();
  out.heldDone = read();

  // 6. the confirm never says 'null →'
  out.confirm = /Update WizardOS\$\{u\.installed \? ' ' \+ u\.installed \+ ' →' : ' to'\}/.test(updateWizardOS_.toString());
  return out;
})()
