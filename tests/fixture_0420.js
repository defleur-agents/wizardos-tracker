// Tracker 0.42.0 fixture (run in the real page by tests/test_0420.py): the reply box and Approve PR #N on an item in
// Needs an answer, with GitHub stubbed (the first comment fails, Retry sends it).
(async () => {
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  me = { connected: true, account: { login: 'mistermizel' } };
  const calls = [];
  let failNext = true;
  const reply = (status, body) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
  const ID = 'humanitylabs-org/wizard-ux#1190', REPO = 'humanitylabs-org/wizard-ux';
  window.fetch = async (path, init) => {
    path = String(path);
    const body = init && init.body ? JSON.parse(init.body) : null;
    calls.push([path, body]);
    if (path.startsWith('api/detail')) return reply(200, { kind: 'bug', id: ID, repo: REPO, number: 1190, title: 'Two systems', url: 'https://github.com/' + REPO + '/issues/1190',
      state: 'open', labels: ['feature', 'builder:blocked'], body_html: '<p>Body</p>', comments_total: 1, can_close: false, close_rule: '',
      comments: [{ author: 'wizardos-builder', created_at: new Date().toISOString(), body_html: '<p>Approve PR #1571?</p>' }],
      approve_prs: [{ repo: REPO, number: 1571, title: 'Skins are look only', url: 'https://github.com/' + REPO + '/pull/1571', author: 'wizardos-builder[bot]', draft: false, mine: false, asked: true }] });
    if (path === 'api/issue/comment') {
      await sleep(150);
      if (failNext) { failNext = false; return reply(403, { error: 'Your GitHub token cannot do that here.' }); }
      return reply(200, { saved: true });
    }
    if (path === 'api/pr/approve') { await sleep(150); return reply(200, { approved: true, warning: null, pr: { number: 1571 } }); }
    return reply(200, {});
  };
  const item = { id: ID, repo: REPO, number: 1190, url: 'https://github.com/' + REPO + '/issues/1190', title: 'Two systems', group: 'answer',
    kind: 'feature', category: 'core', question: 'Approve PR #1571?', labels: ['feature', 'builder:blocked'], comments: 1,
    waiting_on: { who: ['Miguel'], kind: 'person' } };
  const out = {};
  openDetail(item, true);
  await sleep(400);
  out.reply = { shown: !el('d-reply').hidden, label: el('d-reply-l').textContent, sendOff: el('d-reply-go').disabled };
  out.approve = { shown: !el('d-approve').hidden, text: el('d-approve').textContent,
    buttons: [...el('d-approve').querySelectorAll('button')].map(b => b.textContent.trim()) };
  el('d-reply-t').value = 'Yes, go with option (a).';
  el('d-reply-t').dispatchEvent(new Event('input'));
  out.sendOn = !el('d-reply-go').disabled;
  el('d-reply').requestSubmit();
  let li = el('d-comments').lastElementChild;
  out.immediate = { text: li.textContent, pending: li.classList.contains('bd-pending'), answered: !!item.answered, box: el('d-reply-t').value, line: whereLine(item)[0] };
  await sleep(450);
  li = el('d-comments').lastElementChild;
  out.failed = { unsent: li.classList.contains('bd-unsent'), text: li.textContent, answered: !!item.answered, retry: !!li.querySelector('.bd-unsent-l button') };
  li.querySelector('.bd-unsent-l button').click();
  await sleep(450);
  li = el('d-comments').lastElementChild;
  out.retried = { unsent: li.classList.contains('bd-unsent'), pending: li.classList.contains('bd-pending'), text: li.textContent, answered: !!item.answered,
    count: el('d-comments').children.length };
  const ab = [...el('d-approve').querySelectorAll('button')].find(b => /Approve PR/.test(b.textContent));
  ab.click();
  const yes = el('pop').querySelector('.bd-mini-go');
  out.confirm = el('pop').textContent;
  yes.click();
  out.approveBusy = ab.disabled;
  await sleep(450);
  out.approved = el('d-approve').textContent;
  out.calls = calls.filter(c => c[0] === 'api/issue/comment' || c[0] === 'api/pr/approve');
  WzSheet.close(el('detail'));
  return out;
})()
