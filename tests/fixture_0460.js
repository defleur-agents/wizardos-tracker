// Tracker 0.46.0 fixture (run in the real page by tests/test_0460.py): render the App features and Bugs boards with one
// item waiting in Pending approval and one in Show-and-tell, then read which stages carry the human treatment.
(async () => {
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  window.fetch = async () => new Response('{}', { status: 200, headers: { 'Content-Type': 'application/json' } });
  const out = {};
  const REPO = 'humanitylabs-org/wizard-music';
  const show = { id: REPO + '#3', repo: REPO, number: 3, title: 'Shuffle button', group: 'show', kind: 'feature', category: 'app', labels: ['feature', 'show-and-tell'],
    url: 'https://github.com/' + REPO + '/issues/3', author: 'mistermizel', waiting_on: { who: ['Miguel'], kind: 'person' } };
  const build = { id: REPO + '#4', repo: REPO, number: 4, title: 'Queue view', group: 'building', kind: 'feature', category: 'app', labels: ['feature', 'building'],
    url: 'https://github.com/' + REPO + '/issues/4', author: 'JanMesaric' };
  FeedbackStage._state.items = [{ number: 7, kind: 'feature', title: 'Dark mode please', text: 'It is bright', created: new Date().toISOString(), submitter: 'anonymous' },
    { number: 8, kind: 'bug', title: 'Crash', text: 'It crashed', created: new Date().toISOString(), submitter: 'anonymous' }];
  FeedbackStage._state.at = Date.now();
  const read = () => {
    const bins = [...el('strip').querySelectorAll('.bd-binx')].map(li => ({ key: li.dataset.step, human: li.classList.contains('bd-human'),
      tag: !!li.querySelector('.bd-human-tag'), n: li.querySelector('.bd-bin-n').textContent }));
    const stats = [...el('steps').querySelectorAll('.bd-binx')].map(li => ({ key: li.dataset.step, human: li.classList.contains('bd-human') }));
    const heads = [...el('secs').querySelectorAll('.bd-sec')].map(s => ({ id: s.id, human: s.querySelector('.bd-sec-h').classList.contains('bd-human') }));
    const cards = [...el('secs').querySelectorAll('.bd-icard')].map(c => ({ title: (c.querySelector('.bd-title') || {}).textContent, human: c.classList.contains('bd-human-card'),
      chip: (c.querySelector('.bd-human-chip') || {}).textContent || null }));
    return { bins, stats, heads, cards, row: !!document.getElementById('human-n') };
  };
  for (const v of ['apps', 'bugs']) {
    view = v;
    const d = { view: v, groups: v === 'apps' ? { show: [show], building: [build] } : { building: [] }, stats: { pending: true, items: [] }, steps: [], targets: {}, total: 2, shown: 2 };
    cache[v] = d;
    try { render(d); } catch (e) { out[v] = { error: String(e && e.stack || e) }; continue; }
    await sleep(50);
    out[v] = read();
  }
  // the item pop-up's own flow line
  openItem = show; openId = show.id;
  drawStageFlow({ id: show.id, state: 'open', staged: true, spent: { queued: 60, building: 600 }, spent2: { show: 3600 } }, 'apps');
  out.flow = [...el('d-flow').querySelectorAll('.bd-dbin')].map(li => ({ word: li.querySelector('.bd-dbin-w').textContent, human: li.classList.contains('bd-human'), cur: li.classList.contains('cur') }));
  return out;
})()
