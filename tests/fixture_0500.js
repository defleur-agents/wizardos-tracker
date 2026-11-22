// Tracker 0.50.0 fixture (run in the real page by tests/test_0500.py): a tab opens on the pipeline alone; a tapped stage
// shows its cards; tapping it again puts them away. What waits on the viewer is an orange count on its tab and stage.
(async () => {
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  window.fetch = () => new Promise(() => {});   // nothing answers: the fixture's own data stays put through every tab change
  const REPO = 'humanitylabs-org/wizard-music';
  const it = (n, group, extra) => Object.assign({ id: REPO + '#' + n, repo: REPO, number: n, title: 'Item ' + n, group, kind: 'feature', category: 'app', labels: ['feature'],
    url: 'https://github.com/' + REPO + '/issues/' + n, author: 'mistermizel' }, extra || {});
  const mine = { turn: true, can_decide: true, decider: 'Miguel', waiting_on: { who: ['Miguel'], kind: 'person' } };
  const his = { can_decide: false, decider: 'James', waiting_on: { who: ['James'], kind: 'person' } };
  const apps = { view: 'apps', me_person: 'Miguel', groups: { show: [it(1, 'show', mine), it(2, 'show', mine), it(3, 'show', his)], queued: [it(4, 'queued'), it(5, 'queued')], building: [it(6, 'building')] },
    stats: { pending: true, items: [] }, steps: [], targets: {}, total: 6, shown: 6 };
  const core = { view: 'core', me_person: 'Miguel', groups: { answer: [it(7, 'answer', Object.assign({ category: 'core' }, mine))], queued: [it(8, 'queued', { category: 'core' })] },
    stats: { pending: true, items: [] }, steps: [], targets: {}, total: 2, shown: 2 };
  const goals = { view: 'goals', groups: { goals: [it(20, 'goals', { category: 'goal' }), it(21, 'goals', { category: 'goal' })] }, total: 2 };
  cache.apps = apps; cache.core = core; cache.bugs = { view: 'bugs', groups: {}, stats: { pending: true, items: [] } }; cache.goals = goals;
  const read = () => ({ stage: stage[view], cards: el('secs').querySelectorAll('.bd-icard').length, divider: (el('secs').querySelector('.bd-turn-div') || {}).textContent || '',
    heads: [...el('secs').querySelectorAll('.bd-sec-h')].map(h => h.textContent.replace(/\s+/g, ' ').trim()),
    tools: getComputedStyle(document.querySelector('.bd-tools')).display !== 'none', empty: el('empty').hidden ? null : el('empty').textContent,
    strip: Object.fromEntries([...el('strip').querySelectorAll('.bd-binx')].map(li => [li.dataset.step, [li.querySelector('.bd-bin-n').textContent, (li.querySelector('.bd-wait-n') || {}).textContent || null, li.querySelector('.bd-bin-w').textContent.trim()]])),
    waiton: [...el('secs').querySelectorAll('.bd-waiton')].map(p => p.textContent) });
  const out = {};
  view = 'apps'; stage.apps = null; markView(); render(apps); goalsBadge(); waitBadges(); await sleep(50);
  out.opened = read();
  el('strip').querySelector('.bd-binx[data-step="show"]').click(); await sleep(50);
  out.tapped = read();
  el('strip').querySelector('.bd-binx[data-step="queued"]').click(); await sleep(50);
  out.other = read();
  el('strip').querySelector('.bd-binx[data-step="queued"]').click(); await sleep(50);
  out.again = read();
  el('strip').querySelector('.bd-binx[data-step="show"]').click(); await sleep(20);
  pickView('core'); await sleep(50);
  out.core = read();
  pickView('apps'); await sleep(50);
  out.back = read();
  out.tabs = Object.fromEntries([...document.querySelectorAll('[data-wait]')].map(n => [n.dataset.wait, n.hidden ? null : n.textContent]));
  out.goals = el('goals-t').textContent;
  out.me = !!document.getElementById('me-btn');
  // an old #me link: the tab and the stage with the most waiting on you
  view = 'bugs'; stage.apps = null; wantMine = true; goMine(); await sleep(50);
  out.mine = { view, stage: stage[view], cards: el('secs').querySelectorAll('.bd-icard').length };
  return out;
})()
