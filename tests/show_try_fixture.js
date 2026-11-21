// Tracker 0.48.1 fixture (run in the real page by tests/test_0481.py): show-and-tell cards carry Try it again.
(() => {
  const now = Date.now();
  const A = (id, name, repo) => ({ id, name, repo: 'humanitylabs-org/' + repo, version: '1.0.0', commit: '', source: 'standard' });
  catalog = { apps: [A('wizard-calendar', 'Calendar', 'wizard-calendar'), A('movies', 'Movies', 'movies')] };
  catalogAt = now;
  takeSwitches({ locked: false, switches: [{ id: 'wizard/agent-inbox', name: 'Agent inbox', on: false, kind: 'core', issues: [] }] });
  appSw['wizard-calendar'] = { at: now, ok: true, status: 200, switches: [{ id: 'three-day', name: 'Three days', on: false, issues: [] }] };
  appSw['movies'] = { at: now, ok: true, status: 200, switches: [] };
  updates = { installed: '1.0.0', update_available: false, installing: false, channel: 'latest' };
  const item = (repo, n, extra) => Object.assign({ id: `humanitylabs-org/${repo}#${n}`, repo: `humanitylabs-org/${repo}`, number: n,
    title: `${repo} #${n}`, group: 'show', kind: 'feature', category: 'core', can_decide: true, decider: 'Miguel', labels: ['show-and-tell'],
    pitch: 'A pitch.', before: [], after: [], created_at: new Date(now - 864e5).toISOString(),
    delivers: [{ repo: `humanitylabs-org/${repo}`, number: n + 100 }], open_prs: 0 }, extra);
  const named = text => ({ category: 'app', switch_how: text, switch_place: { kind: 'other', text } });
  const cases = {
    core: item('wizard-ux', 1569, { switch: 'wizard/agent-inbox' }),
    core_other_decides: item('wizard-ux', 1570, { switch: 'wizard/agent-inbox', can_decide: false, decider: 'James' }),
    core_missing: item('wizard-ux', 1236, { switch: 'wizard/desktop-chats' }),
    app: item('wizard-calendar', 47, named('wizard-calendar:three-day')),
    app_missing: item('movies', 23, named('movies:bump-existing')),
    needs_update: item('wizard-ux', 1445, { switch: 'wizard/agent-inbox' }),
    none: item('wizard-os', 676, {}),
    other_waits: item('wizard-ux', 1571, { switch: 'wizard/agent-inbox', can_decide: false, decider: 'James', waiting_on: { who: ['James'], kind: 'person' } }),
    other_waits_no_switch: item('wizard-os', 677, { can_decide: false, decider: 'James', waiting_on: { who: ['James'], kind: 'person' } }),
  };
  const ob = { state: 'yes', text: 'On your Wizard ✓', fix: null, apps: [] };
  for (const [k, i] of Object.entries(cases)) {
    onbox.set(i.id, { at: now, key: factsKey(), v: k === 'needs_update' ? { state: 'no', text: 'Not on your Wizard yet', fix: 'Update WizardOS', apps: [] } : ob });
  }
  const out = {};
  for (const [k, i] of Object.entries(cases)) {
    const card = itemCard(i), t = card.querySelector('.bd-act .bd-try');
    out[k] = { act: !!card.querySelector('.bd-act'), head: (card.querySelector('.bd-waiton') || {}).textContent || '', toggle: !!t, grey: !!(t && t.getAttribute('aria-disabled') === 'true'), label: (t && t.textContent) || '',
      coreSwitch: (t && t.dataset.switch) || '', appSwitch: (t && t.dataset.appSwitch) || '',
      why: [...card.querySelectorAll('.bd-act .bd-why-s')].map(x => x.textContent).join(' | '),
      buttons: [...card.querySelectorAll('.bd-act .bd-mini')].map(x => x.textContent) };
  }
  return out;
})()
